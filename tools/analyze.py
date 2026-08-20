#!/usr/bin/env python3
"""
Report what the mortality data can actually support.

    python analyze.py

Every number here is about classification practice: how often a
jurisdiction records a hanging death as undetermined intent rather than
suicide. None of it bears on any individual death, and nothing in this
output should be quoted as if it did.

Suppressed cells are never treated as zero. A state whose Y20 count stays
under 10 even pooled across seven years is reported as unmeasurable, not
as having none.
"""

from __future__ import annotations

import pathlib
import sqlite3
import sys

DB = pathlib.Path("data/tracker.db")


def main():
    if not DB.exists():
        print("No data/tracker.db. Run from the repo root.")
        return 1
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    print("\n" + "=" * 66)
    print("  UNDETERMINED-INTENT HANGINGS PER 100 SUICIDE-RULED HANGINGS")
    print("  CDC WONDER MCD 2018-2024, pooled. Y20 vs X70, underlying cause.")
    print("=" * 66)

    rows = list(conn.execute("""
        SELECT state, suicide_hanging x, undetermined_hanging y,
               suppressed_cells s, undetermined_ratio r
        FROM v_undetermined_ratio
        WHERE period IS NOT NULL AND state IS NOT NULL
        ORDER BY (r IS NULL), r DESC
    """))
    meas = [r for r in rows if r["r"] is not None]
    supp = [r for r in rows if r["r"] is None]

    print(f"\n  {'state':<22}{'X70':>7}{'Y20':>7}{'per 100':>10}")
    print("  " + "-" * 44)
    for r in meas:
        print(f"  {r['state']:<22}{r['x']:>7}{r['y']:>7}{r['r']*100:>10.2f}")

    if meas:
        lo, hi = meas[-1], meas[0]
        print(f"\n  spread: {hi['state']} {hi['r']*100:.2f} vs "
              f"{lo['state']} {lo['r']*100:.2f}  "
              f"({hi['r']/lo['r']:.1f}x)")

    print(f"\n  measurable: {len(meas)} states")
    print(f"  unmeasurable: {len(supp)} states (Y20 under 10 even pooled)")
    print("    " + ", ".join(sorted(r["state"] for r in supp)))
    print("\n  Unmeasurable does NOT mean zero. It means fewer than 10 deaths")
    print("  across seven years, withheld under confidentiality rules.")

    print("\n" + "=" * 66)
    print("  NATIONAL TREND BY YEAR")
    print("  From a no-state export: nothing suppressed, these are counts.")
    print("=" * 66)
    print(f"\n  {'year':<8}{'X70':>9}{'X91':>8}{'Y20':>8}{'Y20 per 100 X70':>18}")
    print("  " + "-" * 51)
    nat = list(conn.execute("""
        SELECT year,
               SUM(CASE WHEN icd10_code='X70' THEN deaths END) x70,
               SUM(CASE WHEN icd10_code='X91' THEN deaths END) x91,
               SUM(CASE WHEN icd10_code='Y20' THEN deaths END) y20
        FROM mortality_agg
        WHERE state IS NULL AND year IS NOT NULL AND deaths IS NOT NULL
        GROUP BY year ORDER BY year
    """))
    if not nat:
        print("\n  No national rows loaded. Export grouped by Year + Cause with")
        print("  no State breakdown, then load it. Summing the state export")
        print("  gives floors, not counts: it undercounts Y20 by 70-90%.")
    else:
        for r in nat:
            ratio = (r["y20"] / r["x70"] * 100) if r["x70"] else 0
            print(f"  {r['year']:<8}{r['x70']:>9}{r['x91']:>8}{r['y20']:>8}{ratio:>18.2f}")

        # Why the separate export exists, shown rather than asserted.
        floors = {r[0]: r[1] for r in conn.execute("""
            SELECT year, SUM(deaths) FROM mortality_agg
            WHERE state IS NOT NULL AND year IS NOT NULL
              AND icd10_code='Y20' AND deaths IS NOT NULL
            GROUP BY year
        """)}
        if floors:
            print("\n  Why this export is separate: summing the state-broken")
            print("  export instead would have given these Y20 figures --")
            worst = 0
            for r in nat:
                f = floors.get(r["year"], 0)
                pct = (r["y20"] - f) / r["y20"] * 100 if r["y20"] else 0
                worst = max(worst, pct)
                print(f"    {r['year']}: {f:>4} vs {r['y20']:>4} actual  ({pct:.0f}% missing)")
            print(f"\n  Up to {worst:.0f}% of undetermined-intent hangings vanish when you")
            print("  sum visible state cells. X70 is unaffected (never suppressed).")
            print("  Rare categories are exactly where suppression bites hardest,")
            print("  and rare is what this project measures.")

    print("\n" + "=" * 66)
    print("  WHAT THIS DOES NOT SHOW")
    print("=" * 66)
    print("""
  Not whether any ruling is correct. Not whether any death was a
  homicide. A high undetermined rate is not evidence of diligence and
  a low one is not evidence of cover-up; both are consistent with
  several explanations this data cannot distinguish, including who
  certifies deaths in a state (elected coroner vs medical examiner),
  ME office resourcing, and local certification convention.

  The spread is a finding about practice that warrants explanation.
  It is not itself an explanation.
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
