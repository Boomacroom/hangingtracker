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
        WHERE period IS NOT NULL AND state IS NOT NULL
        ORDER BY (undetermined_ratio IS NULL), undetermined_ratio DESC
    """)]

    # --- true national trend (no-state export only) ---
    national = [dict(r) for r in conn.execute("""
        SELECT year,
               SUM(CASE WHEN icd10_code='X70' THEN deaths END) AS x70,
               SUM(CASE WHEN icd10_code='X91' THEN deaths END) AS x91,
               SUM(CASE WHEN icd10_code='Y20' THEN deaths END) AS y20
        FROM mortality_agg
        WHERE state IS NULL AND year IS NOT NULL AND deaths IS NOT NULL
        GROUP BY year ORDER BY year
    """)]

    # --- certification structure, and whether it explains the spread ---
    systems = [dict(r) for r in conn.execute("""
        SELECT * FROM v_undetermined_by_system
        WHERE system_type IS NOT NULL
        ORDER BY (undetermined_ratio IS NULL), undetermined_ratio DESC
    """)]
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
    # Age only, deliberately. The race and sex exports are loaded and the
    # numbers are in the database, but they are not publishable yet and the
    # age table is the reason why: 36% of all undetermined-intent deaths are
    # children under 5, whose X70 count is structurally 0, because these are
    # ICD-10 mechanism codes and under age 5 they are picking up infant
    # suffocation rather than hanging. Infant suffocation mortality differs
    # by race, so the group with the highest ratio in the race table is also
    # the group with the highest infant suffocation mortality, and this
    # export cannot separate the two. Publishing that ratio as a statement
    # about how hanging deaths are classified would be exactly the overclaim
    # this project exists not to make.
    #
    # The fix is an age filter on the WONDER exports, not an adjustment here.
    # When the age-restricted exports land, widen this filter.
    demographics = [dict(r) for r in conn.execute("""
        SELECT year, race, sex, age_group, suicide_hanging, undetermined_hanging,
               assault_hanging, suppressed_cells, undetermined_ratio
        FROM v_undetermined_ratio
        WHERE state IS NULL AND age_group IS NOT NULL
        ORDER BY suicide_hanging DESC
    """)]
    held = [r[0] for r in conn.execute("""
        SELECT DISTINCT CASE WHEN race IS NOT NULL THEN 'race' ELSE 'sex' END
        FROM v_undetermined_ratio
        WHERE state IS NULL AND (race IS NOT NULL OR sex IS NOT NULL)
    """)]

    # --- the suppression grid: which state-year cells are visible at all ---
    years = sorted({r[0] for r in conn.execute(
        "SELECT DISTINCT year FROM mortality_agg WHERE year IS NOT NULL AND state IS NOT NULL")})
    all_states = sorted({r[0] for r in conn.execute(
        "SELECT DISTINCT state FROM mortality_agg WHERE state IS NOT NULL")})
    visible = {(r[0], r[1]) for r in conn.execute(
        "SELECT state, year FROM mortality_agg "
        "WHERE icd10_code='Y20' AND state IS NOT NULL AND year IS NOT NULL "
        "AND deaths IS NOT NULL")}
    grid = {
        "years": years,
        "states": all_states,
        "cells": [[1 if (s, y) in visible else 0 for y in years] for s in all_states],
        "visible": len(visible),
        "total": len(all_states) * len(years),
    }

    # Floors vs truth, so the methods warning is data rather than a claim.
    floors = {r[0]: r[1] for r in conn.execute("""
        SELECT year, SUM(deaths) FROM mortality_agg
        WHERE state IS NOT NULL AND year IS NOT NULL
          AND icd10_code='Y20' AND deaths IS NOT NULL GROUP BY year
    """)}
    for n in national:
        n["y20_state_sum"] = floors.get(n["year"], 0)

    payload = {
        "cases": cases,
        "states": states,
        "national": national,
        "grid": grid,
        "demographics": demographics,
        "demographics_held": held,
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
    print(f"suppression grid: {grid['visible']}/{grid['total']} cells visible")
    if correlations:
        e = correlations["elected_share"]
        print(f"system-type test: n={e['n']}, elected-share rho={e['rho']:+.3f} "
              f"(p={e['p']:.3f})")
    if demographics:
        print(f"demographic rows: {len(demographics)} (age)")
    else:
        print("no national demographic export loaded yet (item 2); "
              "the site omits that section")
    if held:
        print(f"HELD BACK from the site: {', '.join(sorted(held))} -- "
              "confounded by under-5 suffocation deaths, see analyze.py")
    print(f"wrote {OUT / 'tracker.json'} and site/tracker.db")
    return 0


if __name__ == "__main__":
    sys.exit(main())
