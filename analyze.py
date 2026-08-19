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
    print("  NATIONAL TREND BY YEAR (lower bounds, see note)")
    print("=" * 66)
    print(f"\n  {'year':<8}{'X70':>9}{'X91':>8}{'Y20':>8}")
    print("  " + "-" * 33)
    for r in conn.execute("""
        SELECT year,
               SUM(CASE WHEN icd10_code='X70' THEN deaths END) x70,
               SUM(CASE WHEN icd10_code='X91' THEN deaths END) x91,
               SUM(CASE WHEN icd10_code='Y20' THEN deaths END) y20
        FROM mortality_agg WHERE year IS NOT NULL AND deaths IS NOT NULL
        GROUP BY year ORDER BY year
    """):
        print(f"  {r['year']:<8}{r['x70'] or 0:>9}{r['x91'] or 0:>8}{r['y20'] or 0:>8}")

    print("\n  These are sums of VISIBLE state rows in a year-by-state export")
    print("  that hides both zero and suppressed cells. The Y20 column is a")
    print("  FLOOR, not a count: the hidden cells contribute 0-9 each and are")
    print("  excluded here. For true national figures, export grouped by Year")
    print("  and Cause with no State breakdown, which suppresses nothing.")

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
