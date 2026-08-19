---
name: hanging-deaths-tracker-dev
description: "Use this skill whenever the user asks about developing, modifying, debugging, deploying, or extending the hanging-deaths-tracker project — the zero-cost civic dataset tracking how US jurisdictions classify hanging deaths and where those rulings are publicly contested. Trigger for: CDC WONDER API work (request XML, parameter codes, D77/D158 dataset files, suppression handling, ICD-10 X70/Y20/X91), GDELT DOC 2.0 candidate collection and query tuning, the triage workflow that promotes candidates to cases, SQLite schema changes, the undetermined-ratio view, static export and Datasette Lite hosting, or the GitHub Actions refresh cron. Also trigger on tracker.db, schema.sql, wonder.py, gdelt.py, mortality_agg, case_sources, v_undetermined_ratio, the candidates table, triage status, verification status, JULIAN / A Crimson Record, or questions about whether the dataset's claims are defensible. Also trigger when the user asks to add a new data source, seed cases, or harden the repo."
---

# hanging-deaths-tracker Development Guide

A zero-cost civic dataset tracking **how US jurisdictions classify hanging deaths**, and maintaining a sourced case record where official rulings are publicly contested.

The project exists because a real pattern of reporting emerged in 2025-2026 (JULIAN's *A Crimson Record*, Feb 2026; a run of 2026 cases covered by CNN, Capital B, TheGrio, Atlanta Black Star) and there is no open, queryable dataset behind it. Advocacy orgs have case lists. Nobody has the classification-behavior angle.

## The One Rule

**Evidence and conclusions never share a column.**

This is not a style preference. It is the property that determines whether the dataset is citable, and a dataset on this subject that isn't citable is worse than nothing, because the first overclaim gets the whole thing dismissed by exactly the people it needs to reach.

Concretely:

| Answerable with this data | Not answerable, ever |
|---|---|
| Are manner-of-death rulings applied consistently across jurisdictions and demographic groups? | Was this particular death a homicide? |
| How fast do rulings come after a body is found? | Did this coroner cover something up? |
| How often does a jurisdiction use "undetermined" at all? | Is the official ruling wrong? |

Population-level rates cannot determine manner of death in an individual case, in either direction. A lower base rate is not evidence of foul play; a higher one is not evidence of suicide. When a user asks for a feature that crosses this line, say so plainly and offer the defensible version instead.

**Never add a column that encodes our own conclusion about a case.** The moment one exists, someone populates it. `official_manner` records what was ruled, as fact. `family_contests` and `org_contests` record disputes, as attributed claims by named parties. That is the whole vocabulary.

## Architecture

```
GDELT ──> candidates ──[human triage]──> cases ──> case_sources
                                            │
CDC WONDER ──> mortality_agg ───────────────┴──> static JSON / Datasette Lite
```

Three layers, one direction. `gdelt.py` has **no code path to `cases`** and must not acquire one. The only route from a scraped headline to a case record runs through a person marking it in triage.

If asked to automate promotion (LLM classification of candidates, confidence thresholds, auto-verify above some score), push back. An automated pipeline that promotes its own guesses to findings on this subject would be worse than no pipeline. Suggested compromise if the user wants throughput: LLM-assisted *ranking* of the triage queue is fine, because it changes review order without changing review outcome.

## Layout

```
hanging-deaths-tracker/
├── schema.sql                    # source of truth for structure
├── pyproject.toml                # httpx only; datasette is an extra
├── data/tracker.db               # committed to the repo on purpose
├── src/tracker/
│   ├── cli.py                    # init / wonder / news / triage / export
│   └── sources/
│       ├── wonder.py             # CDC WONDER aggregate pulls
│       └── gdelt.py              # news candidate collection
└── .github/workflows/refresh.yml # daily cron
```

## Cost Model

Target is **$0/month** and it holds because every property of this workload inverts what cloud pricing assumes: low thousands of rows ever, one write batch per day, fully cacheable reads, no latency requirement, no availability requirement.

| Component | Choice | Cost |
|---|---|---|
| Compute | GitHub Actions cron | free (unlimited on public repos) |
| Database | SQLite committed to the repo | $0 |
| Sources | CDC WONDER, GDELT | free, no keys |
| Hosting | Cloudflare Pages (static) | free |
| Query UI | Datasette Lite (WASM, browser-side) | $0, no backend |

Datasette Lite runs SQLite in the browser against a static `.db` file, giving faceted browse, arbitrary SQL, and a JSON API with no server:

```
https://lite.datasette.io/?url=https://<pages-domain>/tracker.db
```

**Do not migrate this to AWS.** Lambda + RDS + API Gateway is roughly $15-40/month to serve a few thousand rows that change once a day, and the RDS floor is charged whether or not anyone visits. Aurora Serverless v2 still has a nonzero ACU minimum. If a real write API ever becomes necessary, Fly.io or a $5 VPS beats all of it.

### Why SQLite is correct here, not a compromise

The genuine SQLite constraint is **one writer at a time** — no network access, no concurrent write transactions. This workload is a single cron process writing once daily. Zero contention.

The line to watch: **when a second human can write concurrently.** If the triage UI ever becomes a multi-user web app with several people marking candidates simultaneously, revisit. WAL mode stretches further than people expect, but that is the trigger. Not before.

For a dataset whose value rests on not having been quietly edited, git is a *better* integrity story than a managed database. In Postgres a superuser can `UPDATE cases SET official_manner='suicide'` with no trace absent audit logging nobody checks. In git every change to the `.db` is a commit with an author, timestamp, and hash chain.

## CDC WONDER

**The API cannot serve this project.** Only national data are available
to API queries for NVSS; grouping or limiting by State/County returns
**HTTP 403**. This is not a fixable parameter code. The state-level
workflow is a **manual web export** loaded via `load_wonder.py`, which is
fine since these data update annually.

Read `references/wonder-api.md` before any WONDER work.

The relevant ICD-10 codes, and the pairing is the entire point:

| Code | Meaning |
|---|---|
| `X70` | Intentional self-harm by hanging/strangulation/suffocation |
| `Y20` | Hanging/strangulation/suffocation, **undetermined intent** |
| `X91` | Assault by hanging/strangulation/suffocation |

The ratio of Y20 to X70 by state is the core signal. A jurisdiction that essentially never rules "undetermined" is the finding, and it is a finding about *classification practice*, which is defensible, rather than about any death.

### Suppression is not zero

**WONDER hides any cell under 10 deaths, returning the literal string `Suppressed`.** Broken down by race and state and year, hanging deaths hit this constantly.

A suppressed cell means "fewer than 10", never "none". Treating it as 0 produces "this state never rules undetermined" out of thin air — precisely the overclaim that would discredit the project. `v_undetermined_ratio` returns NULL rather than a ratio whenever a suppressed cell is in the group, and exposes `suppressed_cells` so coverage is visible. Preserve that behavior in any new aggregate.

`Unreliable` (rates computed on fewer than 20 deaths) is a separate, weaker flag — the number is real but the rate is noisy.

### Traps

- **Use D157 (2018-2024, single race), not D77 (1999-2020, bridged race).** Bridged vs single race is a real discontinuity; do not mix them.
- **Use UCD (`F_D157.V2`), not MCD (`F_D157.V13`).** UCD is the single ruled underlying cause and is what measures the classification decision; MCD is any of 20 contributing causes.
- **Export with Show Zero Values and Show Suppressed both True.** Otherwise an absent row is either 0 deaths or 1-9 withheld, and nothing downstream can tell them apart.
- **Every `B_1`..`B_5` slot must be present**, padded with `*None*`. Omitting them returns a 500.
- **Race categories changed** between bridged-race and single-race files. Store WONDER's labels verbatim; do not normalize into a local taxonomy. Collapsing that discontinuity silently manufactures artifacts.

## GDELT

Free, no key, JSON, broad coverage of the open news index. Precision for these queries is poor and that is fine — the job is **recall**. Everything lands in `candidates` at `triage='new'`.

Keep queries broad. Narrowing loses the cases that got one local story and nothing else, which are exactly the ones nobody is counting. Extend `NOISE_DOMAINS` rather than tightening query terms when the queue gets noisy.

Local news is the only source for many of these cases **and it disappears**. Push a web.archive.org snapshot at triage time and store it in `case_sources.archived_url`. Treat link rot as a certainty, not a risk.

## Triage Workflow

```bash
tracker news --timespan 7d    # collect
tracker triage                # review, r/i/d/s/q
```

Promoting a candidate to a case is deliberately manual. When adding a case:

1. Every assertion gets a row in `case_sources` with a real URL. No exceptions.
2. Archive the URL immediately.
3. `verification` stays `unverified` until a human sets otherwise. Nothing automated may set it.
4. Leave fields NULL when unknown. **Partial records are expected and are better than invented completeness.**
5. Check JULIAN's database (julianfreedom.org) first. Duplicating their case list helps nobody.

## Legal Exposure

The real risk here is defamation, not infrastructure. A row naming a county coroner and structurally implying a cover-up is a legal target no amount of database hardening protects against.

Guidance when writing copy, README text, or export formats:

- **Defensible:** "Mississippi recorded undetermined intent in 2% of hanging deaths, against a 15% national rate."
- **Not defensible:** "Mississippi is covering up lynchings."

Same data. The second adds a conclusion the data cannot carry. Keep aggregate framing descriptive and let readers draw inferences.

## Hardening

The threat model is tampering and takedown, not availability. Access control lives at the repo layer since the data is public by design:

- branch protection on `main`, no force push, required PR review
- signed commits so authorship is not spoofable
- Actions token scoped to `contents: write` and nothing more
- case record changes go through PRs, so the `verification` column is not the only gate
- every clone is a full backup, which beats untested RDS snapshots

## Sensitivity

This dataset is about deaths, and some of them are suicides. When generating README copy, dashboards, or any user-facing surface, keep the framing analytical rather than lurid. Do not build features that surface method detail, and do not let the export format turn individual records into a spectacle.

If a user's engagement with this project ever appears personal rather than analytical, respond to the person before the code.

## Reference Files

- `references/wonder-api.md` — full request XML anatomy, dataset ids, parameter code tables, worked examples
- `references/case-fields.md` — field-by-field definition of the `cases` table with the evidentiary standard for each
