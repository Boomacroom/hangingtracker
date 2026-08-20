#!/usr/bin/env python3
"""
Build `state_systems` from the CDC COMEC county table.

    python tools/load_state_systems.py

Answers one question and no others: in each state, who certifies deaths?
Some states elect county coroners who need no medical training, some run
a centralized medical examiner office staffed by forensic pathologists,
and most are a mixture. That is a structural fact about a state, it is
published by CDC at county granularity, and it is the first thing worth
testing against the spread in undetermined-intent classification.

Nothing here evaluates a system. A coroner state is not a worse state.
The table records structure so the reader can see whether structure
explains the variation, and the answer is allowed to be no.

Two design decisions worth knowing about:

1. **Weighted by deaths, not counties.** A state's undetermined rate is a
   property of its death certificates. California has 58 counties, 48 of
   them sheriff-coroner, but Los Angeles County alone certifies more
   deaths than most of those 48 combined. Counting counties would let the
   smallest jurisdictions outvote the ones doing most of the certifying.

2. **`system_type` is derived by rule, not typed in.** A state is labelled
   by a mode only when that mode certifies at least 90% of its deaths;
   below that it is 'mixed'. The threshold is arbitrary and the
   continuous shares are what the analysis actually uses, so the label is
   a convenience for reading, not a finding.

Inputs live in data/systems/ with a SOURCES.txt recording where each came
from. Re-run only when CDC publishes a new table.
"""

from __future__ import annotations

import csv
import datetime as dt
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "tracker.db"
SYS = ROOT / "data" / "systems"
MDI = SYS / "County-Death-Investigation-System-2018-1-9-2024.csv"
POP = SYS / "county-deaths-2023.csv"

SOURCE_URL = ("https://www.cdc.gov/nchs/comec/"
              "County-Death-Investigation-System-2018-1-9-2024.csv")

# CDC's three categories, kept verbatim. 'Other County Official' covers
# justices of the peace, county attorneys, and sheriffs acting ex officio.
TYPES = {"Medical Examiner": "medical examiner",
         "Coroner": "coroner",
         "Other County Official": "other county official"}

DOMINANT = 0.90  # share of certified deaths a mode needs to name the state


def load_weights() -> dict[str, int]:
    """FIPS -> deaths certified in that county, 2023."""
    if not POP.exists():
        return {}
    w = {}
    with open(POP, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                w[r["FIPS_CODE"].zfill(5)] = int(r["DEATHS2023"])
            except (ValueError, KeyError):
                continue
    return w


def main() -> int:
    for p in (DB, MDI):
        if not p.exists():
            print(f"missing {p}. Run from the repo root.")
            return 1

    weights = load_weights()
    states: dict[str, dict] = {}
    unmatched: list[str] = []

    with open(MDI, newline="", encoding="utf-8") as f:
        # CDC ships trailing spaces in two header names. Strip rather than
        # hardcode them; a future re-export may well fix it.
        reader = csv.DictReader(f)
        reader.fieldnames = [h.strip() for h in reader.fieldnames]
        for r in reader:
            st = r["STATE_NAME"].strip()
            s = states.setdefault(st, {
                "abbr": r["VS_STATE_CODE"].strip(), "counties": 0,
                "n": {v: 0 for v in TYPES.values()}, "elected": 0,
                "w": {v: 0 for v in TYPES.values()}, "w_elected": 0,
                "w_total": 0, "state_me": 0, "unweighted": 0,
            })
            raw = r["Medicolegal Death Investigation Type"].strip()
            kind = TYPES.get(raw)
            if kind is None:
                print(f"  unknown system type {raw!r}, skipped")
                continue
            elected = r["ELECTED"].strip() == "Yes"

            s["counties"] += 1
            s["n"][kind] += 1
            s["elected"] += elected
            if r["State Medical Examiner and County Official"].strip() == "Yes":
                s["state_me"] = 1

            fips = r["FIPS_CODE"].strip().zfill(5)
            d = weights.get(fips)
            if d is None:
                # Connecticut replaced counties with planning regions in the
                # 2022 estimates, so its eight county FIPS have no match.
                # Recorded, not silently dropped: an unweighted county is a
                # gap in the denominator and the state falls back below.
                unmatched.append(f"{st}/{fips}")
                s["unweighted"] += 1
                continue
            s["w"][kind] += d
            s["w_elected"] += d if elected else 0
            s["w_total"] += d

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    conn = sqlite3.connect(DB)
    conn.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))

    rows = []
    for st, s in sorted(states.items()):
        # Fall back to county counts only if death weights are missing for
        # any county in the state; a partial weighting is a biased one.
        by_deaths = s["unweighted"] == 0 and s["w_total"] > 0
        basis = "deaths" if by_deaths else "counties"
        tot = s["w_total"] if by_deaths else s["counties"]
        share = {k: (s["w"][k] if by_deaths else s["n"][k]) / tot for k in s["n"]}
        elected_share = (s["w_elected"] if by_deaths else s["elected"]) / tot

        top = max(share, key=share.get)
        system_type = top if share[top] >= DOMINANT else "mixed"

        note = f"{s['counties']} counties; shares weighted by {basis}"
        if s["unweighted"]:
            note += f"; {s['unweighted']} counties had no death weight"

        rows.append((
            st, s["abbr"], system_type, s["counties"],
            s["n"]["medical examiner"], s["n"]["coroner"],
            s["n"]["other county official"], s["elected"],
            round(share["medical examiner"], 4), round(share["coroner"], 4),
            round(elected_share, 4), basis, s["state_me"], SOURCE_URL,
            note, now,
        ))

    conn.executemany("""
        INSERT INTO state_systems
            (state, state_abbr, system_type, counties, counties_me,
             counties_cor, counties_other, counties_elected, me_share,
             coroner_share, elected_share, weight_basis, has_state_me,
             source_url, notes, loaded_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(state) DO UPDATE SET
            state_abbr=excluded.state_abbr, system_type=excluded.system_type,
            counties=excluded.counties, counties_me=excluded.counties_me,
            counties_cor=excluded.counties_cor,
            counties_other=excluded.counties_other,
            counties_elected=excluded.counties_elected,
            me_share=excluded.me_share, coroner_share=excluded.coroner_share,
            elected_share=excluded.elected_share,
            weight_basis=excluded.weight_basis,
            has_state_me=excluded.has_state_me, source_url=excluded.source_url,
            notes=excluded.notes, loaded_at=excluded.loaded_at
    """, rows)
    conn.commit()

    counts: dict[str, int] = {}
    for r in rows:
        counts[r[2]] = counts.get(r[2], 0) + 1
    print(f"\nloaded {len(rows)} jurisdictions from {MDI.name}")
    for k in sorted(counts):
        print(f"  {k:<24}{counts[k]:>3}")
    weighted = sum(1 for r in rows if r[11] == "deaths")
    print(f"\n  weighted by deaths certified: {weighted}/{len(rows)} states")
    if unmatched:
        seen = sorted({u.split("/")[0] for u in unmatched})
        print(f"  county-count fallback: {', '.join(seen)} "
              f"({len(unmatched)} counties without a death weight)")

    orphans = [r[0] for r in conn.execute("""
        SELECT DISTINCT state FROM mortality_agg WHERE state IS NOT NULL
          AND state NOT IN (SELECT state FROM state_systems)
    """)]
    if orphans:
        print(f"\n  WARNING: no system row for {orphans}. The join will be "
              "silently incomplete for those states.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
