# NEXT.md

**The project changed shape. Read this before doing anything else.**

This started as a case tracker. It isn't one, and trying to be one was
making it worse. What it actually produced is a research finding plus a
reusable data pipeline, and that's what it should ship as.

Read `.claude/skills/hanging-deaths-tracker-dev/SKILL.md` for the design
rules and WONDER constraints. Those still apply. The scope below is what
changed.

## Why the reframe

The case table is nine unverified records, several duplicating JULIAN's
much larger and better-maintained list. A reporter working the Fortune
story gets more from ten minutes of searching than from that table. It
costs credibility rather than adding it.

Meanwhile three things came out of this that nobody else has assembled:

1. **Summing published state-level CDC counts undercounts a rare cause of
   death by up to 91%**, while common causes are unaffected. Anyone pulling
   state WONDER data on anything uncommon hits this silently.
2. **A national baseline**: 1.1 undetermined-intent hangings per 100 ruled
   suicide, stable 2018-2024.
3. **A sevenfold state spread** in that rate, with Mississippi 3rd highest,
   which contradicts the framing that prompted the whole project.

Databases need maintenance forever and rot when triage stops. Analyses get
read. Ship the analysis, keep the pipeline for annual refresh, stop
pretending the case list is a product.

---

## 1. Explain the state spread (the real work)

Right now the site publishes a ranked table with no explanation of the
variance, on a topic where readers will supply their own. That is not
neutral. "Alaska classifies hanging deaths as undetermined 7x more often
than Colorado" is true, publishable, and meaningless as it stands.

**Join state death-investigation system type.** Some states use elected
county coroners, often without medical training; some use centralized
medical examiners; some are mixed. CDC and NAME both publish this. It is a
small, stable, joinable table, roughly 50 rows, hand-enterable if no clean
download exists.

The hypothesis worth testing: undetermined rates track certification system
rather than region. Mississippi uses elected county coroners. California
uses medical examiners. If that explains the spread, the finding becomes
*"how a state structures death investigation predicts how often intent is
left undetermined"*, which is genuinely useful and much harder to misread
than a regional ranking.

If it doesn't explain it, say so. A ruled-out confound is still a result,
and it makes the remaining variance more interesting rather than less.

Implementation: new table `state_systems (state, system_type, source_url,
notes)`, a view joining it to `v_undetermined_ratio`, and a section on the
site. Keep `source_url` per row; this is exactly the kind of table people
will want to check.

## 2. National breakdown by race, age, sex

Never run, and it is free: **no suppression at the national level.** One
export, Group By Year + Single Race 6 + Underlying Cause, no state.

Whether the undetermined rate differs by race nationally is the question
underneath this entire topic, and it can be answered cleanly rather than
inferred from a suppressed state table.

Handle the result honestly whichever way it falls. If there is no
meaningful difference, publish that; it is a direct, checkable answer to a
widely circulated claim. If there is one, publish it with the same care as
everything else and resist over-explaining it.

Store WONDER's race labels verbatim. Do not normalize.

## 3. Rewrite the site and README around the finding

Current site leads with the suppression grid (keep it, it works), then goes
national, then state, then a thin case table.

New structure:

1. The suppression grid and what it means for anyone using WONDER
2. National trend and baseline
3. State spread **with the system-type explanation from item 1**
4. Race/age breakdown from item 2
5. Case records, demoted, clearly labelled as an appendix

Reframe the case section as *"the cases that prompted this question"* with a
freeze date, not as a live tracker. Nine sourced records with 61 links is a
fine appendix. It is not a product.

Kill any language implying ongoing case collection.

## 4. Freeze case collection

- Turn off the daily schedule in `.github/workflows/refresh.yml`. Keep
  `workflow_dispatch` so it can be run by hand.
- Keep `curate.py` and `followup.py`. They work, and if a ruling lands on
  one of the nine, recording it takes a minute.
- Keep the nine records. Do not delete work that is already sourced.
- Do not verify all nine. If you want the appendix to carry weight, verify
  **Fortune and Raleigh only**: best documented, and two verified records
  demonstrate the standard without committing you to maintaining nine.

## 5. Publish the suppression finding separately

This is the most broadly useful thing here and it currently sits in a
README on a repo about hanging deaths.

Short writeup: state-level CDC WONDER data hides any cell under 10 deaths,
so summing published state figures undercounts rare causes by 70-90% while
leaving common causes untouched. Worked example with the real numbers.
Recommendation: use a no-state export for national figures, pool years for
state comparisons, always enable Show Zero Values and Show Suppressed.

Somewhere data journalists read. It helps people working on maternal
mortality, overdose subtypes, occupational deaths, none of which have
anything to do with this topic.

## 6. Annual refresh, then leave it alone

WONDER updates once a year. Document in the README: which exports, what
settings, which script loads them. Then the pipeline needs an hour annually
and nothing else.

That is the entire ongoing maintenance burden, and it is the right size.

---

## Rules that must not erode

Unchanged. These exist because the only real asset here is being checkable.

1. **`gdelt.py` has no path to `cases`.** Enforced by
   `tools/check_repo.py`. Never add a classifier that writes fields; the
   phrasing that best predicts "a ruling landed" is identical to a family
   *disputing* a ruling. Reed is the live example: recorded `suicide`, new
   coverage is the family contesting. Same keywords, opposite meaning.
2. **No conclusion columns.** No `suspected_lynching`, no `foul_play`, no
   confidence score. Also enforced.
3. **Suppressed is never zero.** `v_undetermined_ratio` returns NULL when
   any cell in the group is suppressed. Preserve in new aggregates.
4. **No source, no change.** `followup.py` discards a whole update without
   a source URL. Keep it. Keep the `verified` confirmation prompt too;
   `verified` is the only value that cannot be re-derived from a source.
5. **Hostile sources belong in `case_sources`** when they contain factual
   reporting.
6. **`official_manner` records what was ruled**, not an assessment of it.
   Police "investigating as a suicide" is `pending`.
7. **Never estimate `days_to_ruling`** from an article date.

## And one more

**Publish results that cut against the framing.** Mississippi ranking 3rd
highest is in the README's opening section on purpose. Item 2 may produce
another one. The willingness to lead with the inconvenient number is the
only reason anyone should believe the convenient ones.

---

## Done

- Previous item 1 (followup.py fields) merged via PR #1
- Branch protection verified enforced on `main` (GH013 on direct push)
- Scripts moved to `tools/`, scratch transfer scripts removed

### 2026-08-20

- **Item 1 complete, and the hypothesis is dead.** `state_systems` built
  from CDC COMEC's county table, weighted by deaths certified per county,
  joined via `v_undetermined_by_system`. Certification structure does not
  explain the spread: Spearman rho = -0.10, p = 0.62, n = 29, and the
  highest and lowest states are both medical examiner jurisdictions.
  Published as a ruled-out confound in the README, the site, and
  `analyze.py`.
- **Item 3 done.** Site reordered to suppression / national / state +
  system test / (race, hidden until loaded) / cases as appendix with a
  freeze date. README rewritten around the four findings. Tracker
  language removed from both.
- **Item 4 done.** Daily cron deleted from `refresh.yml`, dispatch kept.
  Fortune and Raleigh checked field by field against primary sources and
  both hold; `verification` left for a human to set, since nothing
  automated may set it.
- **Item 5 done.** `SUPPRESSION.md`, with the X91 middle case added so the
  error is shown tracking rarity rather than asserted.
- **Item 6 done.** Annual refresh recipe in the README, four exports.
- **Item 2 blocked on a manual export.** cdc.gov returns an edge-level 403
  to every non-browser client here, so even the national API path that the
  NVSS restriction would allow is unreachable. Everything downstream is
  ready: `load_wonder.py` reads Single Race 6 / sex / age columns and
  stores labels verbatim, `v_undetermined_ratio` now groups by sex and
  age_group, and the site renders the section the moment rows land.
  Export 4 in the README's refresh table is the one to run.

### 2026-08-22 — item 2 landed, and it broke the headline

Race, sex and age exports loaded (pooled, no state, one axis each, all
with zeros and suppressed shown). The age export found something that
changes a published number.

**36% of all Y20 deaths are children under 5, whose X70 count is
structurally 0.** X70/X91/Y20 are mechanism codes covering hanging *and
strangulation and suffocation*; under age 5 they are counting infant
suffocation with undetermined intent, which is a different phenomenon
with no denominator here. The national baseline drops from **1.16 to 0.62
per 100 restricted to ages 15+** — the published figure was inflated 1.9x.

README Finding 2 rewritten around this. The site now shows the age table
with the under-5 rows flagged and the corrected rate in the callout.

**Race and sex are loaded but deliberately not published.** Black or
African American shows 3.50 per 100 against White 0.98. That is exactly
the question this project exists to answer honestly, and it cannot be
answered from this export: infant suffocation mortality differs sharply
by race, so the group with the highest ratio is also the group with the
most under-5 deaths in the numerator, and a pooled all-ages export cannot
separate those. Publishing 3.50 as a statement about how hanging deaths
get classified would be the overclaim that discredits everything else
here. `export_site.py` holds them back and says so on stdout.

### Do this next: re-run the exports with an age filter

Same recipe as the README's refresh table, but in Section 3 of the WONDER
form set **Ten-Year Age Groups** to 15+ (or 5+, and report which). All
six exports need it, not just the demographic ones -- every state figure
in the repo is currently all-ages:

1. State + Cause, pooled, ages 15+
2. Year + Cause, no state, ages 15+
3. State + Year + Cause, ages 15+ (for the suppression grid)
4. Single Race 6 + Cause, pooled, no state, ages 15+
5. Ten-Year Age Groups + Cause, pooled, no state (keep the unfiltered one
   too -- it is the evidence for the confound)
6. Sex + Cause, pooled, no state, ages 15+

Load them under new filenames; do not overwrite the all-ages exports.
Then the race question can be answered properly, the state spread can be
recomputed clean, and the certification-structure test should be re-run
against the corrected ratios -- n=29 may change if the age filter pushes
more states under the suppression threshold, which it probably will.

### Watch for

- **Filenames from the WONDER UI collide.** The race export arrived as
  `Multiple Cause of Death, 2018-2024, Single Race.xls`, which is the exact
  name of the already-loaded State x Year export. Loading it as-is would
  have overwritten that export's footnotes sidecar, destroying the query
  parameters for 481 rows, and filed two different queries under one
  dataset id. Renamed to `mcd_national_{race,sex,age}_pooled_2018_2024.xls`
  on the way in. Always rename before loading.
- `v_undetermined_ratio` previously grouped by year/period/state/race only.
  A demographic export would have pooled men and women into one ratio and
  labelled it a breakdown. Views are now dropped and rebuilt on every
  schema apply for this reason.