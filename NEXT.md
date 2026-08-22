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

### 2026-08-22 (later) — age-filtered exports loaded; two figures corrected

All six exports re-run at 15+ and loaded. Findings 2-5 in the README are
rewritten. Two previously published numbers were wrong and both
corrections are recorded in place rather than folded in silently.

**1. The suppression grid was mislabelled.** The original State x Year
export was run with Show Zero Values and Show Suppressed both **False**,
so 339 of 357 cells were absent — and an absent row is either a zero or a
withheld 1-9. The site called all 339 "withheld", in a figure whose whole
subject is suppression. `load_wonder.py` printed its warning at load time
and it went unactioned for days. Re-run properly: **2 usable counts, 222
withheld, 133 true zeros**. The grid now renders three states, not two.

**2. The certification null did not survive.** At 15+ the measurable set
drops from 29 states to 20, and coroner share moves to rho = +0.40,
p = 0.084 — not significant, and not stable: without Mississippi p = 0.20,
without Arizona p = 0.035. The README now says this data cannot answer the
question, instead of the tidier null it reported before. Re-check this if
the measurable set ever grows.

Other results: national baseline 0.62 per 100 at 15+ (all-ages 1.16).
Mississippi is now the **highest** measurable state at 2.44, up from 3rd.
Montana is a true published zero, 0 undetermined against 426 ruled
suicide. Race gap survives correction at about 2x (Black 1.15, White 0.58)
against 3.6x all-ages, so roughly half the apparent gap was infant
suffocation; that half is documented rather than dropped.

**Schema:** `mortality_agg.age_filter` records what a query *restricted*
to, as opposed to what it grouped by. Without it a 15+ pooled state row
and an all-ages pooled state row are identical in every other column and
the view sums them into a number that counts nothing. Added to the unique
index and the view's GROUP BY. `tools/migrate.py` is new: `schema.sql`
alone cannot add a column to an existing database, and a rebuilt index
referencing a missing column fails the whole script.

### 2026-08-22 (later still) — the site broke, and the test that missed it

Rewriting the suppression callout removed `<span id="undercount">` while
the script still wrote to it. `querySelector` returns null, the write
throws, and `render()` aborted right after the first figure -- so the grid
drew, its stat line filled in, and every table below it stayed empty.

Worse, the `.catch()` reported it as "Could not load data/tracker.json".
The data had loaded fine. Anyone debugging that message goes looking for a
missing file, a bad path, or a web server. Fixed: the handler now
distinguishes a fetch that failed from a render that failed, and says
which.

**The Node check I had been running gave a false pass**, because its stub
`querySelector` returned a fresh object for any selector -- so a missing
element was indistinguishable from a present one. A test that cannot fail
the way production fails is not a test.

`tools/check_site.py` replaces it: parses the ids actually present in the
HTML, returns null for anything else, runs `render()` against the real
exported JSON, and fails if any referenced element is missing, if render
throws, or if a core section comes out empty. Verified it catches the
original bug by reintroducing it.

Also: the callout numbers are now read from the data instead of typed
into the prose. "2 of 357" and "68-91" were hardcoded a few hours after
being computed, which is how a figure goes stale the next time an export
is re-run.

### 2026-08-22 — confidence intervals; the state ranking was mostly noise

An external review of the numbers, verified independently here, was right
on every checkable claim.

**The state table was a ranking that the counts do not support.** Exact
Poisson intervals on all 20 measurable states: **only 5 clear the national
rate** (Mississippi, Missouri, Arizona, Indiana, California). The other 15
overlap it, on numerators of 11 to 34 deaths over seven years, and their
order was noise presented as structure. The site now groups them as
distinguishable / not distinguishable instead of ranking them.

**The Montana callout was wrong and is gone.** 0 against 426 ruled suicide
has an interval of 0-0.87, which includes the national 0.62. Zero is what
a small state at the average often looks like. Calling it "the low end of
the spread" was reading noise as a finding -- the same error as treating
suppressed as zero, one step further along.

**Mississippi survives**, at 2.44 with an interval of 1.37-4.03, on 15
deaths. Still the inconvenient result, still published.

**Race is the strongest result and now carries its caveat.** Black 1.15
(0.89-1.47) against White 0.58 (0.53-0.64), non-overlapping. Added: the
event mix differs sharply -- assault-by-strangulation relative to
suicide-hanging is 12.3% for Black decedents against 2.4% for White, five
times higher. So the higher undetermined rate is as consistent with
genuinely more ambiguous circumstances as with different classification
behaviour, and this data cannot separate them. That caveat is now on the
site, in the README, and in analyze.py output.

`tools/stats.py` gained exact Poisson intervals (Garwood, via incomplete
gamma, no scipy). Normal approximations would be wrong in the flattering
direction at these counts and cannot represent a zero at all.

One trap worth recording: the first version of the annotation helper
coerced a suppressed numerator to 0, which handed 18 withheld states a
confident interval near zero -- converting "not allowed to know" into
"unusually low". The project's founding mistake, reintroduced by a helper
function. Fixed; suppressed rows get no interval.

**The review's one wrong claim** was that the race section is absent from
the site. It has been there since the demographic exports landed -- but
until the `#undercount` fix an hour earlier, `render()` threw before
reaching it, so on the deployed page it genuinely never drew. Right
observation, and the cause was the render bug.

### Still open

- Cases 3 and 9 remain `unverified`; that is a human confirmation.
- `check_repo.py` warns on `kyle-bassinga-ga-2026` and
  `tory-medley-wi-2025`, both recording a manner ruled on a police
  statement rather than a coroner or ME certification.
- The 5-14 age band sits at 5.52 per 100, far above every adult band. It
  is inside the published 15+ cut only by exclusion, and nobody has looked
  at what it is. Likely the same mechanism-code problem in a milder form.
- Whether the race gap holds *within* age bands is untested and needs a
  race x age export, which will suppress heavily.

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