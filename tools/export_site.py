#!/usr/bin/env python3
"""
Export the dataset as static JSON for the public site.

    python tools/export_site.py

Audience is reporters, which changes one thing from the original design:
unverified cases ARE exported. A lead list is useful to someone working a
story; silently withholding it is not. But `verification` ships on every
record and the site labels it on every row, because an unlabelled lead
presented as a finding is how this dataset would get someone burned.

Everything here is re-derivable from tracker.db. Nothing is computed that
isn't already in a view.
"""

from __future__ import annotations

import io
import json
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import stats  # noqa: E402

# Everything published is ages 15+. The all-ages exports stay loaded and
# stay exported as `age_all`, because they are the evidence for why: these
# ICD-10 codes cover suffocation as well as hanging, so below 15 the
# numerator fills with infant suffocation deaths whose denominator is
# structurally zero.
AGE = "15+"
ALL = "all ages"

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "tracker.db"
OUT = ROOT / "site" / "data"


def main():
    if not DB.exists():
        print("No data/tracker.db. Run from the repo root.")
        return 1
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    OUT.mkdir(parents=True, exist_ok=True)

    # --- cases, all statuses, verification always present ---
    cases = [dict(r) for r in conn.execute("""
        SELECT c.*, (SELECT COUNT(*) FROM case_sources s WHERE s.case_id = c.id) AS source_count
        FROM cases c ORDER BY c.date_found DESC NULLS LAST, c.id DESC
    """)]
    for c in cases:
        c["sources"] = [dict(r) for r in conn.execute(
            "SELECT url, outlet, title, source_type, archived_url "
            "FROM case_sources WHERE case_id = ? ORDER BY outlet", (c["id"],))]

    # --- state comparison, pooled ---
    states = [dict(r) for r in conn.execute("""
        SELECT state, suicide_hanging, undetermined_hanging, assault_hanging,
               suppressed_cells, undetermined_ratio
        FROM v_undetermined_ratio
        WHERE period IS NOT NULL AND state IS NOT NULL AND age_filter = ?
        ORDER BY (undetermined_ratio IS NULL), undetermined_ratio DESC
    """, (AGE,))]

    # --- true national trend (no-state export only) ---
    national = [dict(r) for r in conn.execute("""
        SELECT year,
               SUM(CASE WHEN icd10_code='X70' THEN deaths END) AS x70,
               SUM(CASE WHEN icd10_code='X91' THEN deaths END) AS x91,
               SUM(CASE WHEN icd10_code='Y20' THEN deaths END) AS y20
        FROM mortality_agg
        WHERE state IS NULL AND year IS NOT NULL AND deaths IS NOT NULL
          AND age_filter = ?
        GROUP BY year ORDER BY year
    """, (AGE,))]

    # National rate first: every state and group interval is judged against
    # it, and "separates from national" is the only honest summary of a
    # 20-row table where most rows are indistinguishable from each other.
    nat_tot = conn.execute("""
        SELECT SUM(CASE WHEN icd10_code='X70' THEN deaths END),
               SUM(CASE WHEN icd10_code='Y20' THEN deaths END)
        FROM mortality_agg WHERE state IS NULL AND year IS NOT NULL
          AND age_filter = ?
    """, (AGE,)).fetchone()
    national_rate = (nat_tot[1] / nat_tot[0]) if nat_tot[0] else None
    national_ci = stats.rate_ci(nat_tot[1], nat_tot[0]) if nat_tot[0] else None

    def annotate(rows, k="undetermined_hanging", n="suicide_hanging"):
        """Attach an exact Poisson interval and whether it clears the
        national rate. Without this the table is a ranking, and a ranking
        of these counts is mostly noise."""
        for r in rows:
            # A suppressed row has no computable ratio, and coercing its
            # withheld numerator to 0 would hand it a confident interval
            # near zero -- turning "we are not allowed to know" into "this
            # state is unusually low". That is the project's founding
            # mistake, committed by a helper function.
            usable = (r.get("undetermined_ratio") is not None
                      and r.get(n) and r.get(k) is not None)
            ci = stats.rate_ci(r[k], r[n]) if usable else None
            r["ci_low"], r["ci_high"] = (ci if ci else (None, None))
            r["separates"] = bool(
                ci and national_rate is not None
                and (ci[0] > national_rate * 100 or ci[1] < national_rate * 100))
        return rows

    annotate(states)

    # --- certification structure, and whether it explains the spread ---
    systems = [dict(r) for r in conn.execute("""
        SELECT * FROM v_undetermined_by_system
        WHERE system_type IS NOT NULL AND age_filter = ?
        ORDER BY (undetermined_ratio IS NULL), undetermined_ratio DESC
    """, (AGE,))]
    meas = [s for s in systems if s["undetermined_ratio"] is not None]
    correlations = {}
    if len(meas) >= 3:
        y = [s["undetermined_ratio"] for s in meas]
        for var in ("elected_share", "coroner_share", "me_share", "has_state_me"):
            correlations[var] = stats.correlate([s[var] for s in meas], y)

    by_type: dict[str, list[float]] = {}
    for s in meas:
        by_type.setdefault(s["system_type"], []).append(s["undetermined_ratio"])
    system_groups = [
        {"system_type": k, "n": len(v),
         "median": sorted(v)[len(v) // 2] if len(v) % 2 else
                   (sorted(v)[len(v) // 2 - 1] + sorted(v)[len(v) // 2]) / 2,
         "min": min(v), "max": max(v)}
        for k, v in sorted(by_type.items())
    ]

    # Source per row, because "who certifies deaths here" is the kind of
    # claim a reader should be able to check without taking our word.
    system_rows = [dict(r) for r in conn.execute(
        "SELECT state, state_abbr, system_type, counties, counties_me, "
        "counties_cor, counties_other, me_share, coroner_share, "
        "elected_share, weight_basis, has_state_me, source_url, notes "
        "FROM state_systems ORDER BY state")]

    # --- national demographic breakdown, if that export has been loaded ---
    # National only. At national scale nothing is suppressed, so this is
    # the one place a race or age breakdown can be reported as counts
    # rather than as a floor. Absent until someone runs the export; the
    # site simply omits the section rather than showing an empty shell.
    # The age-filtered exports have landed, so race and sex are publishable
    # now. They were held back on the all-ages data for a real reason and
    # the correction was large: Black or African American read 3.50 per 100
    # against White 0.98 all-ages, and 1.15 against 0.58 at 15+. Roughly
    # half the apparent gap was infant suffocation, which these ICD-10 codes
    # also count and which has no denominator in X70. The remaining
    # difference is real and is published; the discarded half is why nothing
    # went out before the age filter existed.
    def demo(col, af=AGE):
        return [dict(r) for r in conn.execute(f"""
            SELECT {col} AS grp, suicide_hanging, undetermined_hanging,
                   assault_hanging, suppressed_cells, undetermined_ratio
            FROM v_undetermined_ratio
            WHERE state IS NULL AND {col} IS NOT NULL AND age_filter = ?
            ORDER BY (undetermined_ratio IS NULL), undetermined_ratio DESC
        """, (af,))]

    demographics = {
        "race": annotate(demo("race")),
        "sex": annotate(demo("sex")),
        "age": annotate(demo("age_group")),
        # Shipped so the correction is checkable rather than asserted: this
        # is the table that showed the problem, under-5 rows included.
        "age_all_ages": demo("age_group", ALL),
    }

    # --- the suppression grid: which state-year cells are visible at all ---
    years = sorted({r[0] for r in conn.execute(
        "SELECT DISTINCT year FROM mortality_agg WHERE year IS NOT NULL "
        "AND state IS NOT NULL AND age_filter = ?", (AGE,))})
    all_states = sorted({r[0] for r in conn.execute(
        "SELECT DISTINCT state FROM mortality_agg WHERE state IS NOT NULL "
        "AND age_filter = ?", (AGE,))})
    # Three states, not two. The original export was run with Show Zero
    # Values and Show Suppressed both False, so 339 of 357 cells were simply
    # absent -- and an absent row is EITHER zero deaths OR 1-9 withheld.
    # That is the exact ambiguity this project documents as the trap, and
    # the grid was labelling all of it "withheld". With a complete export
    # the two are separable and they are not close to the same thing.
    cell_state = {}
    for st, yr, deaths, supp in conn.execute(
            "SELECT state, year, deaths, suppressed FROM mortality_agg "
            "WHERE icd10_code='Y20' AND state IS NOT NULL AND year IS NOT NULL "
            "AND age_filter = ?", (AGE,)):
        cell_state[(st, yr)] = (2 if supp else (1 if (deaths or 0) > 0 else 0))
    grid = {
        "years": years,
        "states": all_states,
        # 0 = a real zero, 1 = a usable published count, 2 = withheld (1-9)
        "cells": [[cell_state.get((s, y), 2) for y in years] for s in all_states],
        "published": sum(1 for v in cell_state.values() if v == 1),
        "zero": sum(1 for v in cell_state.values() if v == 0),
        "withheld": sum(1 for v in cell_state.values() if v == 2),
        "total": len(all_states) * len(years),
    }
    grid["visible"] = grid["published"]

    # Floors vs truth, so the methods warning is data rather than a claim.
    floors = {r[0]: r[1] for r in conn.execute("""
        SELECT year, SUM(deaths) FROM mortality_agg
        WHERE state IS NOT NULL AND year IS NOT NULL
          AND icd10_code='Y20' AND deaths IS NOT NULL AND age_filter = ?
        GROUP BY year
    """, (AGE,))}
    for n in national:
        n["y20_state_sum"] = floors.get(n["year"], 0)

    payload = {
        "cases": cases,
        "states": states,
        "national": national,
        "grid": grid,
        "demographics": demographics,
        # Event mix, because it is the first thing anyone should ask about
        # the race result. Assault-by-strangulation relative to
        # suicide-hanging is five times higher for Black decedents, so a
        # higher undetermined rate is consistent with genuinely more
        # ambiguous circumstances as well as with different classification
        # behaviour, and this data cannot separate the two.
        "event_mix": [dict(r) for r in conn.execute("""
            SELECT race,
                   SUM(CASE WHEN icd10_code='X70' THEN deaths END) AS x70,
                   SUM(CASE WHEN icd10_code='X91' THEN deaths END) AS x91,
                   SUM(CASE WHEN icd10_code='Y20' THEN deaths END) AS y20
            FROM mortality_agg
            WHERE state IS NULL AND race IS NOT NULL AND age_filter = ?
            GROUP BY race
        """, (AGE,))],
        "national_rate": national_rate,
        "national_ci": national_ci,
        "age_filter": AGE,
        "systems": {
            "states": system_rows,
            "joined": systems,
            "correlations": correlations,
            "groups": system_groups,
        },
        # The case list is frozen. Ship the date of the last change to it so
        # the appendix can say so on its face rather than in a caption
        # somebody edits and forgets.
        "case_freeze_date": (conn.execute(
            "SELECT MAX(substr(updated_at,1,10)) FROM cases").fetchone()[0]),
        "counts": {
            "cases": len(cases),
            "verified": sum(1 for c in cases if c["verification"] == "verified"),
            "measurable_states": sum(1 for s in states if s["undetermined_ratio"] is not None),
            "suppressed_states": sum(1 for s in states if s["undetermined_ratio"] is None),
        },
    }

    # Explicit LF. On Windows the default translates every newline to CRLF,
    # .gitattributes normalises it straight back on commit, and the working
    # tree is left permanently dirty after an export. A diff that is always
    # there is a diff nobody reads, which is how a real change to this file
    # goes unnoticed.
    with io.open(OUT / "tracker.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, indent=1)

    # Ship the db itself so Datasette Lite can open it.
    import shutil
    shutil.copy(DB, ROOT / "site" / "tracker.db")

    c = payload["counts"]
    print(f"exported {c['cases']} cases ({c['verified']} verified), "
          f"{len(states)} states, {len(national)} years")
    print(f"suppression grid: {grid['published']} usable, {grid['withheld']} "
          f"withheld, {grid['zero']} true zero, of {grid['total']}")
    seps = [s_["state"] for s_ in states if s_.get("separates")]
    meas_n = sum(1 for s_ in states if s_["undetermined_ratio"] is not None)
    print(f"states separating from the national rate: {len(seps)} of {meas_n} "
          f"measurable -> {', '.join(seps)}")
    if correlations:
        e = correlations["elected_share"]
        print(f"system-type test: n={e['n']}, elected-share rho={e['rho']:+.3f} "
              f"(p={e['p']:.3f})")
    print("demographics: " + ", ".join(
        f"{k} {len(v)}" for k, v in demographics.items() if v) or "none loaded")
    print(f"wrote {OUT / 'tracker.json'} and site/tracker.db")
    return 0


if __name__ == "__main__":
    sys.exit(main())
