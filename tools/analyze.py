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
from statistics import median

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import stats  # noqa: E402

DB = pathlib.Path("data/tracker.db")

# Everything published is ages 15+. The all-ages exports are still loaded
# and are still the evidence for why: below 15, X70 is structurally near
# zero while Y20 is not, because these ICD-10 codes cover suffocation as
# well as hanging, so an all-ages ratio is inflated by infant suffocation
# deaths that have no denominator. See the age section below.
AGE = "15+"
ALL = "all ages"


def main():
    if not DB.exists():
        print("No data/tracker.db. Run from the repo root.")
        return 1
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    print("\n" + "=" * 66)
    print("  UNDETERMINED-INTENT HANGINGS PER 100 SUICIDE-RULED HANGINGS")
    print("  CDC WONDER MCD 2018-2024, pooled, ages 15+. Underlying cause.")
    print("=" * 66)

    rows = list(conn.execute("""
        SELECT state, suicide_hanging x, undetermined_hanging y,
               suppressed_cells s, undetermined_ratio r
        FROM v_undetermined_ratio
        WHERE period IS NOT NULL AND state IS NOT NULL AND age_filter = ?
        ORDER BY (r IS NULL), r DESC
    """, (AGE,)))
    meas = [r for r in rows if r["r"] is not None]
    supp = [r for r in rows if r["r"] is None]

    print(f"\n  {'state':<22}{'X70':>7}{'Y20':>7}{'per 100':>10}")
    print("  " + "-" * 44)
    for r in meas:
        print(f"  {r['state']:<22}{r['x']:>7}{r['y']:>7}{r['r']*100:>10.2f}")

    if meas:
        hi = meas[0]
        # A state can have a visible, real zero -- Montana records 0
        # undetermined against 426 ruled suicide, and that cell is shown,
        # not suppressed. Dividing by it prints inf and reads as a spread
        # of infinity, so the fold-difference is quoted against the lowest
        # NON-zero state and the zero is reported as the finding it is.
        nonzero = [r for r in meas if r["r"] > 0]
        print(f"\n  highest: {hi['state']} {hi['r']*100:.2f} per 100")
        if len(nonzero) > 1:
            lo_nz = nonzero[-1]
            print(f"  lowest non-zero: {lo_nz['state']} {lo_nz['r']*100:.2f}"
                  f"   ({hi['r']/lo_nz['r']:.1f}x)")
        for z in [r for r in meas if r["r"] == 0]:
            print(f"  true zero: {z['state']} recorded 0 undetermined against "
                  f"{z['x']} ruled suicide")
            print("             (that cell is visible, not suppressed)")

    print(f"\n  measurable: {len(meas)} states")
    print(f"  unmeasurable: {len(supp)} states (Y20 under 10 even pooled)")
    print("    " + ", ".join(sorted(r["state"] for r in supp)))
    print("\n  Unmeasurable does NOT mean zero. It means fewer than 10 deaths")
    print("  across seven years, withheld under confidentiality rules.")

    print("\n" + "=" * 66)
    print("  NATIONAL TREND BY YEAR, AGES 15+")
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
          AND age_filter = ?
        GROUP BY year ORDER BY year
    """, (AGE,)))
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
              AND icd10_code='Y20' AND deaths IS NOT NULL AND age_filter = ?
            GROUP BY year
        """, (AGE,))}
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
    print("  NATIONAL BREAKDOWN BY RACE, SEX AND AGE (15+)")
    print("  Pooled 2018-2024, no state, so nothing is a floor.")
    print("=" * 66)

    def axis(col, label, af=AGE):
        rows = list(conn.execute(f"""
            SELECT {col} g, suicide_hanging x, assault_hanging a,
                   undetermined_hanging y, suppressed_cells s, undetermined_ratio r
            FROM v_undetermined_ratio
            WHERE state IS NULL AND {col} IS NOT NULL AND age_filter = ?
            ORDER BY (r IS NULL), r DESC
        """, (af,)))
        if not rows:
            return []
        print(f"\n  {label}")
        print(f"  {'group':<36}{'X70':>7}{'X91':>6}{'Y20':>6}{'Y20/100':>9}")
        print("  " + "-" * 64)
        for r in rows:
            rr = f"{r['r']*100:.2f}" if r["r"] is not None else (
                "withheld" if r["s"] else "n/a")
            f = lambda v: v if v is not None else "-"  # noqa: E731
            print(f"  {r['g']:<36}{f(r['x']):>7}{f(r['a']):>6}{f(r['y']):>6}{rr:>9}")
        return rows

    axis("race", "BY RACE, ages 15+")
    axis("sex", "BY SEX, ages 15+")
    axis("age_group", "BY AGE, within 15+")

    print("\n" + "=" * 66)
    print("  WHY EVERYTHING ABOVE IS 15+ AND NOT ALL AGES")
    print("=" * 66)
    ages = axis("age_group", "ALL AGES -- the export that found the problem",
                af=ALL)

    if ages:
        under5 = [r for r in ages if r["g"] in ("< 1 year", "1-4 years")]
        y_u5 = sum(r["y"] or 0 for r in under5)
        x_u5 = sum(r["x"] or 0 for r in under5)
        y_all = sum(r["y"] or 0 for r in ages)
        adult = [r for r in ages
                 if r["g"] not in ("< 1 year", "1-4 years", "5-14 years", "Not Stated")]
        ax_, ay_ = sum(r["x"] or 0 for r in adult), sum(r["y"] or 0 for r in adult)
        if y_all and ax_:
            print(f"""
  READ THIS BEFORE USING THE NATIONAL RATE.

  {y_u5} of {y_all} undetermined-intent deaths ({y_u5/y_all*100:.0f}%) are children
  under 5. Their X70 count is {x_u5}, and it cannot be anything else:
  intentional self-harm is not assigned at that age. So a third of the
  numerator of the national ratio has no denominator at all.

  These are not hangings. X70/X91/Y20 are mechanism codes covering
  hanging AND strangulation AND suffocation, and under age 5 the code is
  picking up infant suffocation deaths -- unsafe sleep, overlay, wedging
  -- where intent was left undetermined. That is a real and serious
  category of death. It is not the one this project measures, and it
  behaves nothing like it.

  Restricted to ages 15+, where the ratio is between two things that can
  actually both happen:

      X70 {ax_}   Y20 {ay_}   {ay_/ax_*100:.2f} per 100

  against {y_all}/{sum(r['x'] or 0 for r in ages)} = \
{y_all/max(sum(r['x'] or 0 for r in ages),1)*100:.2f} across all ages.

  The all-ages figure is inflated by roughly {(y_all/max(sum(r['x'] or 0 for r in ages),1))/(ay_/ax_):.1f}x. Every
  national and state number elsewhere in this output is all-ages and
  carries the same inflation, and infant suffocation mortality varies by
  state and by race, so the state spread and the race breakdown are
  contaminated by it too, in unknown proportion.

  The fix is an age filter on the WONDER exports, not an adjustment here.
  Until those are re-run, the race and sex tables above are NOT
  publishable: the group with the highest ratio is also the group with
  the highest infant suffocation mortality, and this data cannot separate
  those. See NEXT.md.""")

    print("\n" + "=" * 66)
    print("  DOES CERTIFICATION STRUCTURE EXPLAIN THE SPREAD?")
    print("  Undetermined rate vs who certifies deaths in the state.")
    print("=" * 66)

    sysrows = [dict(r) for r in conn.execute("""
        SELECT * FROM v_undetermined_by_system
        WHERE undetermined_ratio IS NOT NULL AND system_type IS NOT NULL
          AND age_filter = ?
    """, (AGE,))]
    if not sysrows:
        print("\n  No state_systems rows. Run tools/load_state_systems.py.")
    else:
        y = [r["undetermined_ratio"] for r in sysrows]
        print(f"\n  {'variable':<40}{'rho':>7}{'p':>9}")
        print("  " + "-" * 56)
        labels = {
            "elected_share": "share certified by elected official",
            "coroner_share": "share certified by a coroner",
            "me_share": "share certified by a medical examiner",
            "has_state_me": "state has a state medical examiner",
        }
        for var, label in labels.items():
            s = stats.correlate([r[var] for r in sysrows], y)
            print(f"  {label:<40}{s['rho']:>+7.3f}{s['p']:>9.3f}")
        print(f"\n  n = {len(sysrows)} states. Spearman rank correlation,")
        print("  p from a 20,000-shuffle permutation test.")

        groups: dict[str, list[float]] = {}
        for r in sysrows:
            groups.setdefault(r["system_type"], []).append(
                r["undetermined_ratio"] * 100)
        print(f"\n  {'system type':<24}{'n':>4}{'median':>9}{'range':>16}")
        print("  " + "-" * 53)
        for k in sorted(groups, key=lambda k: -median(groups[k])):
            v = groups[k]
            print(f"  {k:<24}{len(v):>4}{median(v):>9.2f}"
                  f"{min(v):>10.2f}-{max(v):.2f}")

        # Leave-one-out, because at this n a single state can manufacture
        # or destroy the whole correlation, and reporting one p-value
        # without saying so would be reporting an artefact.
        base = stats.correlate([r["coroner_share"] for r in sysrows], y)
        loo = []
        for i, r in enumerate(sysrows):
            sub = sysrows[:i] + sysrows[i + 1:]
            s2 = stats.correlate([q["coroner_share"] for q in sub],
                                 [q["undetermined_ratio"] for q in sub])
            loo.append((s2["rho"], s2["p"], r["state"]))
        loo.sort()

        print(f"""
  DO NOT read this as either result yet.

  On the all-ages data this section reported a clean null: every
  correlation indistinguishable from chance at n=29. Restricting to 15+
  removed the infant-suffocation contamination and also removed nine
  states from the measurable set, and the coroner-share correlation moved
  to rho = {base['rho']:+.3f}, p = {base['p']:.3f}. That is not significant, and it is
  also no longer nothing.

  It is not stable either. Dropping any single state moves it to:

      lowest   rho = {loo[0][0]:+.3f}, p = {loo[0][1]:.3f}   (without {loo[0][2]})
      highest  rho = {loo[-1][0]:+.3f}, p = {loo[-1][1]:.3f}   (without {loo[-1][2]})

  A result whose significance is decided by which single observation you
  include is not a result. With n={len(sysrows)} and four variables tested, the
  honest statement is that this data cannot answer the question -- not
  that structure explains the spread, and no longer that it clearly
  does not.

  The earlier null was reported at n=29 on contaminated data. The right
  correction is to say the test lost its power when the contamination was
  removed, not to keep quoting the tidier answer.""")

    print("\n" + "=" * 66)
    print("  WHAT THIS DOES NOT SHOW")
    print("=" * 66)
    print("""
  Not whether any ruling is correct. Not whether any death was a
  homicide. A high undetermined rate is not evidence of diligence and
  a low one is not evidence of cover-up; both are consistent with
  several explanations. One of them -- who certifies deaths in a
  state -- is tested above and does not account for the spread. The
  ones still standing, which this data cannot distinguish, include
  office resourcing, autopsy rates, local certification convention,
  and classification becoming more cautious under public scrutiny.

  The spread is a finding about practice that warrants explanation.
  It is not itself an explanation.
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
