# hanging-deaths-tracker

An analysis of **how US jurisdictions classify hanging deaths**, built on
CDC WONDER, plus the pipeline that produced it and a frozen appendix of
sourced case records.

Three things came out of this that were not assembled anywhere else:

1. **Summing published state-level CDC counts undercounts a rare cause of
   death by up to 91%**, while leaving common causes untouched. Anyone
   pulling state WONDER data on anything uncommon hits this silently.
   Written up separately in [SUPPRESSION.md](SUPPRESSION.md), because it
   has nothing to do with this subject and affects a lot of other work.
2. **A national baseline**: 1.1 undetermined-intent hangings per 100
   ruled suicide, stable across 2018-2024.
3. **A sevenfold spread between states** in that rate — and, on testing,
   *not* explained by whether a state elects lay coroners or runs a
   medical examiner system.

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

WONDER hides any cell under 10 deaths. At State × Year granularity, **18
of 357** cells for undetermined-intent hangings are published; 339 are
withheld, and 43 states show no visible count in any year.

The consequence people miss is what this does to a national figure built
by adding up states:

| Year | Summed from states | Actual national | Missing |
|---:|---:|---:|---:|
| 2021 | 13 | 144 | **91%** |
| 2023 | 44 | 143 | 69% |

Meanwhile suicide-ruled hangings (`X70`), a common cause, sum correctly
to the last death — 0% error every year. The error is invisible if you
sanity-check your pipeline against a common cause.

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

About **1.1 undetermined-intent hangings per 100 ruled suicide**, and
that ratio is stable across seven years even as the absolute counts fall.

## Finding 3: a sevenfold state spread

Pooled 2018-2024, so more states clear the suppression threshold:

| | state | X70 | Y20 | per 100 |
|---|---|---|---|---|
| highest | Alaska | 417 | 16 | 3.84 |
| | Arizona | 2311 | 63 | 2.73 |
| | Mississippi | 632 | 17 | 2.69 |
| | North Carolina | 2276 | 49 | 2.15 |
| … | | | | |
| | New Jersey | 2043 | 15 | 0.73 |
| | California | 10109 | 64 | 0.63 |
| lowest | Colorado | 2331 | 13 | 0.56 |

29 states measurable, 22 withheld even pooled across seven years — those
are reported as unmeasurable, never as zero. `python tools/analyze.py`
prints the full table.

**Note where Mississippi lands.** The intuitive hypothesis behind a
project like this is that Southern jurisdictions close these cases as
suicide too readily and under-use "undetermined". The data says the
reverse: Mississippi ranks 3rd highest, and the lowest users are
Colorado, California, and New York.

This is stated up front deliberately. The willingness to lead with the
inconvenient number is the only reason anyone should believe the
convenient ones.

## Finding 4: certification structure does not explain the spread

A ranked table of states with no explanation attached is not neutral —
readers supply their own. So we tested the readiest explanation.

States differ in who certifies deaths. Some elect county coroners who
need no medical training; some run a centralized medical examiner office
staffed by forensic pathologists; most are a mixture, county by county.
CDC publishes this at county level. `state_systems` joins it to the
mortality data, with each county weighted by **how many deaths it
actually certifies** — a state's undetermined rate is a property of its
death certificates, and counting counties would let a state's smallest
jurisdictions outvote the ones doing most of the certifying.

The result, over the 29 measurable states:

| variable | Spearman ρ | p |
|---|---:|---:|
| share of deaths certified by an elected official | −0.10 | 0.62 |
| share certified by a coroner | +0.04 | 0.82 |
| share certified by a medical examiner | +0.04 | 0.84 |
| state has a state medical examiner | +0.25 | 0.20 |

| system type | n | median per 100 | range |
|---|---:|---:|---|
| coroner | 6 | 1.71 | 1.28 – 2.69 |
| medical examiner | 10 | 1.61 | 0.73 – 3.84 |
| mixed | 13 | 1.10 | 0.56 – 2.08 |

*p from a 20,000-shuffle permutation test; rank correlation because 29
bounded, right-skewed rates are not a job for Pearson.*

**Nothing here is distinguishable from chance**, and the categorical
medians overlap across nearly their whole range — the highest and lowest
states in the table are *both* medical examiner jurisdictions.

A ruled-out confound is still a result. It removes the readiest
explanation and leaves the variation needing a different one, plausibly
at the level of individual offices rather than state law: caseload,
autopsy rate, local convention, or how one large county certifies.

What it does **not** show is that structure never matters. n=29 has
little power, half the states are unmeasurable, and a "mixed" state is an
average of counties that differ from each other. The explanation is ruled
out as the driver of this spread, not out of the picture.

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

Exports 4-6 are the ones to run next and have not been loaded yet.

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
python tools/load_wonder.py <export.xls>      # load a WONDER export
python tools/load_state_systems.py            # build state_systems from CDC COMEC
python tools/analyze.py                       # every finding above, printed
python tools/export_site.py                   # rebuild site/ from the db
python tools/check_repo.py                    # verify invariants
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
