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

import json
import pathlib
import sqlite3
import sys

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
        "counts": {
            "cases": len(cases),
            "verified": sum(1 for c in cases if c["verification"] == "verified"),
            "measurable_states": sum(1 for s in states if s["undetermined_ratio"] is not None),
            "suppressed_states": sum(1 for s in states if s["undetermined_ratio"] is None),
        },
    }

    (OUT / "tracker.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")

    # Ship the db itself so Datasette Lite can open it.
    import shutil
    shutil.copy(DB, ROOT / "site" / "tracker.db")

    c = payload["counts"]
    print(f"exported {c['cases']} cases ({c['verified']} verified), "
          f"{len(states)} states, {len(national)} years")
    print(f"suppression grid: {grid['visible']}/{grid['total']} cells visible")
    print(f"wrote {OUT / 'tracker.json'} and site/tracker.db")
    return 0


if __name__ == "__main__":
    sys.exit(main())
