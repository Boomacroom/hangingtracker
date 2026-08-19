# hanging-deaths-tracker

Tracks how US jurisdictions classify hanging deaths, and maintains a
sourced case record where official rulings are publicly contested.

## What this answers, and what it does not

**Answerable:** are manner-of-death classifications applied consistently
across jurisdictions and demographic groups? How fast do rulings come?
How often is "undetermined" used at all?

**Not answerable:** whether any individual death was a homicide. No
aggregate can establish that, and the schema is built so the data can
never be arranged to imply it. Population-level rates cannot determine
manner of death in a single case, in either direction.

If those two stay separated the dataset is citable. If they blur, it
isn't, and it will be dismissed by exactly the people it needs to reach.

## Cost

Target is $0/month, and it is achievable because every property of this
workload is the opposite of what cloud pricing assumes.

| Property | Value | Consequence |
|---|---|---|
| Row count | low thousands, ever | fits in SQLite with room to spare |
| Write pattern | one batch/day | no connection pool, no RDS |
| Read pattern | static, cacheable | no application server |
| Latency need | none | cron is fine |
| Availability need | none | a failed run retries tomorrow |

So:

| Component | Choice | Cost |
|---|---|---|
| Compute | GitHub Actions cron | free (unlimited on public repos) |
| Database | SQLite committed to the repo | $0 |
| Data sources | CDC WONDER, GDELT | free, no API keys |
| Hosting | Cloudflare Pages static | free |
| Browse/query UI | Datasette Lite (WASM, browser-side) | $0, no backend at all |

**Total: $0.**

Datasette Lite is the trick worth knowing. It runs SQLite in the browser
via WASM against a static `.db` file, so you get faceted search, SQL
queries, and a JSON API with literally no server:

```
https://lite.datasette.io/?url=https://<your-pages-domain>/tracker.db
```

### What to avoid

Do not put this on AWS. Lambda plus RDS plus API Gateway is roughly
$15-40/month to serve a few thousand rows that change once a day, and
the RDS instance is the floor whether anyone visits or not. Even Aurora
Serverless v2 has a nonzero ACU minimum. If you later need a real API,
Fly.io or a $5 VPS beats all of it, but Datasette Lite means you
probably never will.

The one real cost is human time on triage. That is not optimizable and
should not be.

## Design: three layers, one direction

```
GDELT ──> candidates ──[human triage]──> cases ──> case_sources
                                            │
CDC WONDER ──> mortality_agg ───────────────┴──> static JSON / Datasette
```

`gdelt.py` physically cannot write to `cases`. The only path from a
scraped headline to a case record runs through a person marking it. This
is the single most important property of the codebase. An automated
pipeline that promotes its own guesses to findings on this subject would
be worse than no pipeline.

Every case field is nullable. Partial records are expected and are
better than invented completeness. `verification` defaults to
`unverified` and nothing sets it otherwise except a human.

## Usage

```bash
pip install -e .
tracker init                  # create data/tracker.db from schema.sql
tracker news --timespan 7d    # collect candidates from GDELT
tracker triage                # review loop
tracker wonder --years 2018 2019 2020
tracker export                # write site/data/*.json
```

## Known traps

**Suppression is not zero.** CDC WONDER hides any cell under 10 deaths.
Broken down by race, state, and year, hanging deaths hit this
constantly. `v_undetermined_ratio` returns NULL rather than a ratio
whenever a suppressed cell is in the group, and exposes
`suppressed_cells` so you can see coverage. Do not paper over this; a
false zero here would produce exactly the kind of overclaim that gets
the whole project discarded.

**WONDER parameter codes are per-dataset.** D77 covers 1999-2020.
Provisional years live under different file ids with different `V`
codes. The API also rejects some breakdowns the web UI permits. Verify
against wonder.cdc.gov before trusting a pull. Neither this nor GDELT
was live-tested when scaffolded, so the first `tracker wonder` run is
where you find out.

**Link rot.** Local news is the only source for many of these cases and
it disappears. `case_sources.archived_url` exists for a reason. Push a
snapshot to web.archive.org at triage time.

**Race categories.** Store WONDER's labels verbatim. Do not normalize
them into your own taxonomy; the bridged-race vs single-race change
across years is a real discontinuity and collapsing it silently
introduces artifacts.

## Prior work

JULIAN's *A Crimson Record* (Feb 2026) documents 70+ suspected
modern-day lynchings across seven Southern states since 2000, with a
case database at julianfreedom.org. Check it before adding a case here.
Duplicating their work helps nobody; complementing it with the
classification-behavior angle might.
