# hanging-deaths-tracker

An analysis of **how US jurisdictions classify hanging deaths**, built on
CDC WONDER, plus the pipeline that produced it and a frozen appendix of
sourced case records.

Three things came out of this that were not assembled anywhere else:

1. **Summing published state-level CDC counts can undercount a rare cause
   of death by 100%** — in five of seven years the state figures for this
   cause sum to exactly zero — while leaving common causes untouched.
   Anyone pulling state WONDER data on anything uncommon hits this
   silently. Written up separately in [SUPPRESSION.md](SUPPRESSION.md),
   because it has nothing to do with this subject and affects a lot of
   other work.
2. **A national baseline**: 0.62 undetermined-intent deaths per 100 ruled
   suicide, ages 15+, stable across 2018-2024.
3. **A twofold difference by race**: intent is left undetermined about
   twice as often for Black decedents (1.15 vs 0.58 per 100,
   non-overlapping intervals) — the opposite direction to the assumption
   the subject usually carries.
4. **State variation that is mostly not measurable.** Only 5 of 20
   measurable states separate from the national rate; the rest is noise
   at these counts, and an earlier version of this repo published the
   full ranking as if it were a finding.

Two published figures in this repository have already been corrected by
later exports. Both corrections are recorded rather than quietly folded
in: see Finding 2 and Finding 5.

## What this answers, and what it does not

**Answerable:** are manner-of-death classifications applied consistently
across jurisdictions? How often does a jurisdiction use "undetermined
intent" at all? Does the structure of a state's death-investigation
system predict that?

**Not answerable:** whether any individual death was a homicide. No
aggregate can establish that, and the schema is built so the data cannot
be arranged to imply it. Population-level rates cannot determine manner
of death in a single case, in either direction.

If those two stay separated the dataset is citable. If they blur, it
isn't, and it will be dismissed by exactly the people it needs to reach.

## Finding 1: most of the state-level data is withheld

WONDER hides any cell under 10 deaths. At State × Year granularity, of
357 cells for undetermined-intent deaths, **2 carry a usable count**, 222
are withheld as 1-9 deaths, and 133 are true zeros.

The consequence people miss is what this does to a national figure built
by adding up states:

| Year | Summed from states | Actual national | Missing |
|---:|---:|---:|---:|
| 2021 | 0 | 76 | **100%** |
| 2023 | 10 | 91 | 89% |

Meanwhile suicide-ruled hangings (`X70`), a common cause, sum correctly
to the last death — 0% error every year. The error is invisible if you
sanity-check your pipeline against a common cause.

**This repository fell into the adjacent trap first.** The original State
× Year export was run with Show Zero Values and Show Suppressed both
False, so 339 of 357 cells were simply absent — and an absent row is
either a zero or a withheld 1-9. Those were reported as "withheld", on a
page whose subject is suppression. The loader printed a warning at the
time and it went unactioned for several days. Re-running the query
properly separated them: 133 zeros, 222 withheld.

Full worked writeup, including what to do instead:
**[SUPPRESSION.md](SUPPRESSION.md)**.

## Finding 2: the national baseline

From a no-state export, where nothing is suppressed and the counts are
complete:

| Year | X70 suicide | X91 assault | Y20 undetermined | Y20 per 100 X70 |
|---:|---:|---:|---:|---:|
| 2018 | 13,840 | 485 | 154 | 1.11 |
| 2020 | 12,495 | 415 | 133 | 1.06 |
| 2022 | 12,247 | 375 | 159 | 1.30 |
| 2024 | 11,453 | 407 | 131 | 1.14 |

That is **1.16 undetermined-intent deaths per 100 ruled suicide** across
all ages, stable across seven years even as the absolute counts fall.

**But the all-ages figure is wrong for this purpose, and the age
breakdown is how we found out.** Pooled 2018-2024:

| age group | X70 suicide | Y20 undetermined | per 100 |
|---|---:|---:|---:|
| < 1 year | **0** | **329** | no denominator |
| 1-4 years | **0** | 39 | no denominator |
| 5-14 years | 2,121 | 117 | 5.52 |
| 15-24 years | 12,917 | 91 | 0.70 |
| 25-64 years | 65,713 | 387 | ~0.59 |
| 65+ years | 7,295 | 56 | 0.77 |

**368 of 1,019 undetermined-intent deaths — 36% — are children under 5,
and their suicide count is structurally zero.** Intentional self-harm is
not assigned at that age, so a third of the numerator has no denominator
at all.

These are not hangings. `X70`/`X91`/`Y20` are mechanism codes covering
hanging **and strangulation and suffocation**, and under age 5 they are
counting infant suffocation deaths — unsafe sleep, overlay, wedging —
where intent was left undetermined. A real and serious category of death,
and not this one.

Restricted to **ages 15+**, where the ratio is between two things that
can both actually happen:

**X70 85,925 · Y20 534 · 0.62 per 100**

**This has been fixed.** All six exports were re-run with an age filter
and every figure in this repository is now ages 15+. The all-ages exports
are kept and still shipped, because they are the evidence for the
correction rather than a discarded draft. `mortality_agg.age_filter`
records which regime each row came from, so the two can never be summed
together.

## Finding 3: state variation, and how little of it is real

Pooled 2018-2024, ages 15+. 20 of 51 jurisdictions are measurable. The
national rate is **0.62 per 100** (95% CI 0.57-0.68).

**Only 5 of those 20 states have an interval that clears the national
rate.** The counts are 11 to 34 deaths over seven years, and at that size
most states cannot be told apart from the national average or from each
other.

| state | X70 | Y20 | per 100 | 95% CI |
|---|---:|---:|---:|---|
| Mississippi | 614 | 15 | 2.44 | 1.37 – 4.03 |
| Missouri | 1,778 | 25 | 1.41 | 0.91 – 2.08 |
| Arizona | 2,250 | 25 | 1.11 | 0.72 – 1.64 |
| Indiana | 1,824 | 19 | 1.04 | 0.63 – 1.63 |
| California | 9,920 | 43 | 0.43 | 0.31 – 0.58 |

The other 15 measurable states overlap the national rate. They are
published for completeness, and **their order is noise**. An earlier
version of this README and of the site presented all 20 as a ranked
table, which showed structure the data does not contain.

**Montana is not a low outlier.** It recorded 0 undetermined against 426
ruled suicide, and an earlier version called that out as a finding. Its
interval runs 0 – 0.87, which includes the national 0.62. Zero out of 426
is what a small state at the average frequently looks like. The callout
has been removed.

**Mississippi does hold up.** It is the highest measurable state and its
interval clears the national rate, on 15 deaths. That still cuts against
the intuition the project started from — that Southern jurisdictions
would *under*-use "undetermined" — and it is stated here for that reason.

## Finding 4: a twofold difference by race

National, pooled, ages 15+. The counts here are large enough that the
intervals are tight, unlike the state table:

| group | X70 | Y20 | per 100 | 95% CI |
|---|---:|---:|---:|---|
| Black or African American | 5,722 | 66 | 1.15 | 0.89 – 1.47 |
| More than one race | 1,709 | 14 | 0.82 | 0.45 – 1.37 |
| American Indian or Alaska Native | 2,080 | 17 | 0.82 | 0.48 – 1.31 |
| White | 71,963 | 419 | 0.58 | 0.53 – 0.64 |
| Asian | 4,070 | 15 | 0.37 | 0.21 – 0.61 |

| group | X70 | Y20 | per 100 | 95% CI |
|---|---:|---:|---:|---|
| Female | 18,556 | 158 | 0.85 | 0.72 – 1.00 |
| Male | 67,369 | 376 | 0.56 | 0.50 – 0.62 |

The Black and White intervals do not overlap. Among these deaths, intent
was left undetermined about **twice as often** for Black decedents.

**This is the direct opposite of the premise the project started from.**
The claim motivating this subject is that officials reach too readily for
"suicide". Nationally, for Black decedents, they reach for "undetermined"
at roughly double the White rate.

**The first thing to ask about that, and the honest answer.** The mix of
deaths behind the two figures is not the same. Assault by strangulation,
relative to suicide-hanging, is **12.3%** for Black decedents against
**2.4%** for White decedents — five times higher. Where more deaths are
genuinely violent or ambiguous, more may be genuinely hard to classify.
So the difference is consistent with more ambiguous circumstances as much
as with different classification behaviour, and **this data cannot
separate those two explanations.** The direction holds either way.

Also worth knowing: on all-ages data the same comparison gives 3.50
against 0.98, a 3.6x gap. Roughly half of that was infant suffocation
deaths these ICD-10 codes also count, which have no denominator in X70.
The 2x is what survived the age filter. If a gap that large can be half
artefact, "the reasons are not in this data" is a finding about the data,
not a hedge.

## Finding 5: certification structure — this data cannot answer it

A ranked table of states with no explanation attached is not neutral —
readers supply their own. So we tested the readiest explanation: who
certifies deaths. `state_systems` joins CDC's county-level table,
weighting each county by **how many deaths it actually certifies**,
because a state's undetermined rate is a property of its death
certificates and counting counties would let its smallest jurisdictions
outvote the ones doing most of the certifying.

Over the 20 measurable states:

| variable | Spearman ρ | p |
|---|---:|---:|
| share of deaths certified by an elected official | 0.00 | 1.00 |
| share certified by a coroner | +0.40 | 0.08 |
| share certified by a medical examiner | −0.15 | 0.53 |
| state has a state medical examiner | +0.02 | 0.96 |

**An earlier version of this README reported a clean null here**, at
n=29, on all-ages data. Correcting the age contamination removed nine
states from the measurable set and took the statistical power with them.
The coroner-share correlation is now weakly positive and not significant,
and it is not stable: dropping Mississippi moves it to p=0.20, dropping
Arizona to p=0.04. A result whose significance is decided by which single
observation you include is not a result.

The honest statement is that **20 states cannot answer this question** —
not that structure explains the spread, and no longer that it clearly
does not. Reporting the earlier, tidier null would mean quoting a number
computed on data now known to be contaminated.

## Appendix: the cases that prompted this question

Nine sourced records of individual deaths where the ruling was publicly
disputed in reporting, with 79 source links. **Collection is frozen.**
This is a record of what started the analysis, not a live tracker, and
nothing is being added.

For a maintained case database on this subject, see JULIAN's *A Crimson
Record* (Feb 2026) at julianfreedom.org, which documents 70+ suspected
modern-day lynchings across seven Southern states since 2000.

The tooling still works — if a ruling lands on one of the nine,
`python tools/followup.py --update <id>` records it, source-first — but
the daily collection cron is off. See [NEXT.md](NEXT.md) for why the
project was reframed this way.

## Data sources

### CDC WONDER (manual export, not API)

**The WONDER API cannot serve this project.** Per CDC's API
documentation, only national data are available to API queries for the
National Vital Statistics System; queries cannot group or limit by
Region, Division, State, or County. A state-level request returns HTTP
403. Those fields are available in the web application only. (CDC also
blocks non-browser clients entirely from some networks, so even national
API queries may fail with an edge-level 403 that has nothing to do with
the NVSS restriction.)

So the workflow is a manual export, which is fine: these data update
annually, not daily. See **Annual refresh** below for the exact recipe.

### CDC COMEC, for certification structure

`data/systems/County-Death-Investigation-System-2018-1-9-2024.csv`,
verbatim, 3,143 counties: who conducts medicolegal death investigation in
each one, whether that official is elected, and whether the state has a
state medical examiner. County death counts used for weighting come from
Census population estimates. Provenance for both is in
`data/systems/SOURCES.txt`, and every row of `state_systems` carries its
own `source_url`.

```bash
python tools/load_state_systems.py
```

### GDELT (frozen)

Free, no key, broad news coverage. Precision is poor by design — the job
was recall. Everything landed in `candidates` at `triage='new'` and a
human decided what was real. The collection cron is now off; the code
remains and can be run by hand.

## Annual refresh

WONDER updates once a year. That is the entire ongoing maintenance
burden, and it is about an hour.

At [Multiple Cause of Death, 2018-2024, Single
Race](https://wonder.cdc.gov/mcd-icd10-expanded.html) (`D157` — use the
single-race file, not the 1999-2020 bridged-race one; the two are not
comparable and mixing them manufactures artifacts):

- Filter **UCD - ICD-10 Codes** to `X70`, `X91`, `Y20`. Not MCD: UCD is
  the single ruled underlying cause, which is what measures the
  classification decision.
- Uncheck **Show Totals** — total rows break the parser.
- In Quick Options set **Show Zero Values** and **Show Suppressed** both
  to **True**.

Then take these exports, save under `data/wonder/`, and load each with
`python tools/load_wonder.py data/wonder/<file>.xls`:

| # | Group by | Purpose | Suppression |
|---|---|---|---|
| 1 | State + Cause (pooled, no year) | cross-state comparison | 22 states withheld |
| 2 | Year + Cause (no state) | true national trend | none |
| 3 | State + Year + Cause | the suppression grid; *not* usable for ratios | 339 of 357 cells hidden |
| 4 | Single Race 6 + Cause, **pooled, no state, no year** | national breakdown by race | small groups still withheld |
| 5 | Ten-Year Age Groups + Cause, pooled, no state | national breakdown by age | some groups withheld |
| 6 | Sex + Cause, pooled, no state | national breakdown by sex | none |

**Every one of these must be run twice: once unfiltered and once with
Ten-Year Age Groups set to 15+.** The 15+ set is what gets published; the
all-ages set is the evidence for why (Finding 2). `mortality_agg` records
which regime a row came from in `age_filter`, and the derived view groups
by it, so the two can never be summed together. Load the 15+ files under
distinct names — `mcd_*_15plus_*.xls` here.

Two things that will bite:

- **The WONDER UI names files after the dataset, not the query.** Three
  different queries all arrive as `Multiple Cause of Death, 2018-2024,
  Single Race.xls`. Rename before loading or you will overwrite another
  export's footnotes sidecar and file two queries under one dataset id.
- **A new column means a migration.** `python tools/migrate.py` adds
  missing columns and reapplies `schema.sql`; run it before loading if
  you have pulled schema changes.

**Pooled, not by year, and one axis at a time.** "No suppression at the
national level" is true of the national *total* and not of a breakdown of
it. There are about 146 undetermined-intent hangings nationally per year.
Split six ways by race, only the two largest groups clear the
ten-death threshold in a single year; pooling all seven years brings
roughly 1,020 deaths to the split and most groups into range, though the
smallest may still be withheld — and withheld still is not zero. Crossing
race by age by sex at once would suppress nearly everything, which is the
same mistake as the State × Year export in row 3, one level down.

The loader stores WONDER's race labels verbatim — do not normalize them
into a local taxonomy; the categories genuinely changed between the
bridged-race and single-race files and collapsing that silently
manufactures artifacts. The site renders that section only once the data
is present, and the result gets published whichever way it falls.

The loader saves a `.footnotes.txt` sidecar with each file recording the
exact query parameters. Commit those; they are what make the numbers
checkable by someone else.

Then:

```bash
python tools/analyze.py       # re-read the tables
python tools/export_site.py   # rebuild the site
python tools/check_repo.py    # invariants still hold
```

## Design: three layers, one direction

```
GDELT ──> candidates ──[human triage]──> cases ──> case_sources
                                            │
CDC WONDER ──> mortality_agg ───────────────┤
                                            ├──> static JSON / Datasette
CDC COMEC ──> state_systems ────────────────┘
```

`gdelt.py` has no code path to `cases` and must not acquire one. The only
route from a scraped headline to a case record runs through a person
marking it. An automated pipeline that promotes its own guesses to
findings on this subject would be worse than no pipeline.

Every case field is nullable. Partial records are expected and are better
than invented completeness. `verification` defaults to `unverified` and
nothing sets it otherwise except a human.

There is no `suspected_lynching` column and there will not be. The
dataset records what authorities ruled and who disputes it, and lets
readers reason. `state_systems` records structure, never quality: there
is no column saying a coroner system is worse, and adding one is the same
mistake in a new place. `tools/check_repo.py` enforces both.

## Cost

Target is $0/month, and it holds because every property of this workload
inverts what cloud pricing assumes: low thousands of rows ever, one write
batch a year now, cacheable reads, no latency or availability
requirement.

| Component | Choice | Cost |
|---|---|---|
| Compute | GitHub Actions, manual dispatch | free |
| Database | SQLite committed to the repo | $0 |
| Sources | CDC WONDER, CDC COMEC, Census, GDELT | free, no keys |
| Hosting | Cloudflare Pages static | free |
| Query UI | Datasette Lite (WASM, browser-side) | $0, no backend |

Datasette Lite runs SQLite in the browser against a static `.db` file, so
you get faceted browse, SQL, and a JSON API with no server:

```
https://lite.datasette.io/?url=https://<pages-domain>/tracker.db
```

Do not move this to AWS. Lambda + RDS + API Gateway is $15-40/month to
serve a few thousand rows that now change once a year, and the RDS floor
is charged whether anyone visits or not.

For a dataset whose value rests on not having been quietly edited, git
history is a better integrity story than a managed database anyway.

## Usage

```bash
pip install -e .
python -m tracker.cli init                    # create data/tracker.db
python -m tracker.seed                        # seed sourced cases (unverified)
python tools/migrate.py                       # bring an existing db up to schema
python tools/load_wonder.py <export.xls>      # load a WONDER export
python tools/load_state_systems.py            # build state_systems from CDC COMEC
python tools/analyze.py                       # every finding above, printed
python tools/export_site.py                   # rebuild site/ from the db
python tools/check_repo.py                    # verify invariants
python tools/check_site.py                    # render the site and fail on JS errors
```

Frozen but still working, for the appendix:

```bash
python -m tracker.cli news --timespan 30d     # collect GDELT candidates
python tools/curate.py                        # cluster + triage + promote
python tools/followup.py                      # developments on existing cases
python tools/followup.py --update <id>        # record one, with its source
```

`tracker` as a bare command requires the user Scripts dir on PATH; `python
-m tracker.cli` always works.

## Known traps

**Suppression is not zero, and it is worse than it looks.** See
[SUPPRESSION.md](SUPPRESSION.md). `v_undetermined_ratio` returns NULL
rather than a ratio whenever a suppressed cell is in the group, and
exposes `suppressed_cells` so coverage is visible. Preserve that in any
new aggregate.

**Views are rebuilt on every schema apply**, not guarded with `IF NOT
EXISTS`. A view definition that silently stays at the old version in an
existing database is how a fixed query goes on returning the broken
answer. `v_undetermined_ratio` groups by `sex` and `age_group` even
though every currently loaded row has them NULL, because the moment a
demographic export lands, a grouping that omitted them would pool men and
women into one ratio and report it as a breakdown.

**The permutation test canonicalises pair order.** Spearman does not care
what order states arrive in, but a seeded shuffle does, so the same data
reached through two different `ORDER BY` clauses would otherwise report
two different p-values. A published number that moves when a query is
rewritten is not a published number.

**Link rot.** Local news is the only source for many of the case records
and it disappears. `case_sources.archived_url` holds a web.archive.org
snapshot.

**Even CDC's own pages block you.** cdc.gov refuses non-browser clients
from some networks with an edge-level 403. The COMEC table in this repo
was retrieved through the Internet Archive for that reason; the canonical
URL is recorded alongside it.

## Sources and framing

Sources hostile to the premise belong in `case_sources` when they contain
factual reporting. A tracker that only cites sympathetic outlets is one
nobody outside the choir has to engage with. The schema is built so a
hostile source can sit alongside a sympathetic one without either
contaminating a field.

Aggregate framing stays descriptive. "Mississippi recorded undetermined
intent in 2.7 per 100 hanging deaths ruled suicide, third highest among
measurable states" is defensible. Anything adding a conclusion the data
cannot carry is not, and the difference is the whole project.
