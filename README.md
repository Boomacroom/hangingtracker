# hanging-deaths-tracker

Tracks how US jurisdictions classify hanging deaths, and maintains a
sourced case record where official rulings are publicly contested.

## What this answers, and what it does not

**Answerable:** are manner-of-death classifications applied consistently
across jurisdictions? How often does a jurisdiction use "undetermined
intent" at all? How fast do rulings come?

**Not answerable:** whether any individual death was a homicide. No
aggregate can establish that, and the schema is built so the data cannot
be arranged to imply it. Population-level rates cannot determine manner
of death in a single case, in either direction.

If those two stay separated the dataset is citable. If they blur, it
isn't, and it will be dismissed by exactly the people it needs to reach.

## Current finding

Across 2018-2024, pooled, the rate at which a hanging death is recorded
as **undetermined intent (Y20)** rather than **suicide (X70)** varies
about sevenfold between states:

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

29 states measurable. 22 have fewer than 10 Y20 deaths even pooled across
seven years and are withheld under confidentiality rules; those are
reported as unmeasurable, never as zero. Run `python tools/analyze.py` for the
full table.

**Note where Mississippi lands.** The intuitive hypothesis behind a
project like this is that Southern jurisdictions close these cases as
suicide too readily and under-use "undetermined." The data says the
reverse: Mississippi ranks 3rd highest, and the lowest users are
Colorado, California, and New York.

This is stated up front deliberately. Several explanations are consistent
with the spread and this data distinguishes none of them: who certifies
deaths in a state (elected county coroner vs medical examiner office),
office resourcing, local certification convention, or classification
becoming more cautious under public scrutiny. **The spread is a finding
about practice that warrants explanation. It is not itself an
explanation.**

## Data sources

### CDC WONDER (manual export, not API)

**The WONDER API cannot serve this project.** Per CDC's API
documentation, only national data are available to API queries for the
National Vital Statistics System; queries cannot group or limit by
Region, Division, State, or County. A state-level request returns HTTP
403. Those fields are available in the web application only.

So the workflow is a manual export, which is fine: these data update
annually, not daily.

1. Go to [Multiple Cause of Death, 2018-2024, Single
   Race](https://wonder.cdc.gov/mcd-icd10-expanded.html). Use the
   single-race file, not the 1999-2020 bridged-race one; the two are not
   comparable and mixing them manufactures artifacts.
2. Filter **UCD - ICD-10 Codes** to `X70`, `X91`, `Y20`.
3. Group as below, uncheck **Show Totals**, and in Quick Options set
   **Show Zero Values** and **Show Suppressed** to **True**.
4. Export, save under `data/wonder/`, and run
   `python tools/load_wonder.py data/wonder/<file>.xls`.

Three exports, each answering something the others can't:

| Group by | Purpose | Suppression |
|---|---|---|
| State + Cause (pooled, no year) | cross-state comparison | 22 states withheld |
| Year + Cause (no state) | true national trend | none |
| State + Year + Cause | *not usable for ratios* | 339 of 357 cells hidden |

The loader saves a `.footnotes.txt` sidecar with each file recording the
exact query parameters. Commit those; they are what make the numbers
checkable by someone else.

### GDELT (automated)

Free, no key, broad news coverage. Precision is poor by design — the job
is recall. Everything lands in `candidates` at `triage='new'` and a human
decides what is real. Throttled to 15s between queries with backoff;
GDELT 429s readily.

## Design: three layers, one direction

```
GDELT ──> candidates ──[human triage]──> cases ──> case_sources
                                            │
CDC WONDER ──> mortality_agg ───────────────┴──> static JSON / Datasette
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
readers reason.

## Cost

Target is $0/month, and it holds because every property of this workload
inverts what cloud pricing assumes: low thousands of rows ever, one write
batch per day, cacheable reads, no latency or availability requirement.

| Component | Choice | Cost |
|---|---|---|
| Compute | GitHub Actions cron | free (unlimited on public repos) |
| Database | SQLite committed to the repo | $0 |
| Sources | CDC WONDER, GDELT | free, no keys |
| Hosting | Cloudflare Pages static | free |
| Query UI | Datasette Lite (WASM, browser-side) | $0, no backend |

Datasette Lite runs SQLite in the browser against a static `.db` file, so
you get faceted browse, SQL, and a JSON API with no server:

```
https://lite.datasette.io/?url=https://<pages-domain>/tracker.db
```

Do not move this to AWS. Lambda + RDS + API Gateway is $15-40/month to
serve a few thousand rows that change once a day, and the RDS floor is
charged whether anyone visits or not.

SQLite's real constraint is one writer at a time. This is a single daily
cron process, so there is no contention. Revisit only if a multi-user
triage UI lets several people write concurrently. For a dataset whose
value rests on not having been quietly edited, git history is a better
integrity story than a managed database anyway.

The one real cost is human time on triage. That is not optimizable and
should not be.

## Usage

```bash
pip install -e .
python -m tracker.cli init                 # create data/tracker.db
python -m tracker.seed                     # seed sourced cases (unverified)
python -m tracker.cli news --timespan 30d  # collect GDELT candidates
python tools/curate.py                     # cluster + triage + promote
python tools/load_wonder.py <export.xls>   # load a WONDER export
python tools/analyze.py                    # the ratio table
python tools/followup.py                   # developments on existing cases
python tools/followup.py --update <id>     # record one, with its source
python tools/export_site.py                # rebuild site/ from the db
python tools/check_repo.py                 # verify invariants
```

`tracker` as a bare command requires the user Scripts dir on PATH; `python
-m tracker.cli` always works.

`python -m tracker.cli wonder` exists but **cannot work** for state-level
data — see the 403 note above. Use the manual export path.

## Known traps

**Suppression is not zero, and it is worse than it looks.** WONDER hides
any cell under 10 deaths. At State × Year × Cause granularity, 339 of 357
cells are hidden, so that breakdown cannot support a ratio at all.
Pooling all years is what makes 29 states measurable. `v_undetermined_ratio`
returns NULL rather than a ratio whenever a suppressed cell is in the
group, and exposes `suppressed_cells` so coverage is visible.

**Hidden rows are ambiguous unless you ask.** With Show Zero Values and
Show Suppressed both False, an absent row is *either* 0 deaths *or* 1-9
withheld. Those are opposite claims about a coroner's office and nothing
downstream can recover the difference. Always export with both True.
`load_wonder.py` reads the footnotes and warns when it detects this.

**National sums from a state-broken export are floors.** They exclude
every hidden cell. Use a no-state export for real national figures.

**Link rot.** Local news is the only source for many of these cases and it
disappears. Push a web.archive.org snapshot at triage time and record it
in `case_sources.archived_url`.

**Syndication inflates the queue.** Station networks run identical copy
across dozens of sites; one story can look like forty candidates.
`curate.py` clusters by title similarity before presenting.

## Sources and framing

Sources hostile to the premise belong in `case_sources` when they contain
factual reporting. A tracker that only cites sympathetic outlets is one
nobody outside the choir has to engage with. The schema is built so a
hostile source can sit alongside a sympathetic one without either
contaminating a field.

## Prior work

JULIAN's *A Crimson Record* (Feb 2026) documents 70+ suspected modern-day
lynchings across seven Southern states since 2000, with a case database at
julianfreedom.org. Check it before adding a case. Duplicating their case
list helps nobody; the classification-behavior angle above is what this
adds.
