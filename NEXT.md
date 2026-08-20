# NEXT.md

Working notes for picking this up in Claude Code. Delete or rewrite freely;
this is a handoff, not a spec.

**Start by reading `.claude/skills/hanging-deaths-tracker-dev/SKILL.md`.** It
has the design rules, the WONDER constraints, and the reasoning behind the
schema. Everything below assumes it.

## State as of handoff

Live at https://boomacroom.github.io/hangingtracker/ — Pages builds from
`publish.yml` on every push to `main`, running `tools/export_site.py` in CI.

- 9 case records, **0 verified**, 61 sources attached
- 634 rows in `mortality_agg` from three WONDER exports
- ~150 candidates triaged, most marked
- `main` is protected: PR required, no force push, no direct pushes

The finding that holds up: undetermined-intent hangings per 100 ruled
suicide runs Colorado 0.56 to Alaska 3.84 across 2018-2024 pooled, against
a national rate of ~1.1. Mississippi is 3rd highest, which cuts against the
intuitive framing and is stated up front in the README on purpose.

---

## 1. Finish `tools/followup.py` — DONE

`--update` now exposes `notes` (dated append, never overwrite),
`verification`, `verified_by`/`verified_at`, `autopsy_public`,
`independent_autopsy`, `date_last_seen`.

- Source URL is the **first** prompt. Blank aborts before anything else is
  typed, instead of after.
- Attach and update are one transaction. Ctrl-C mid-prompts rolls back the
  attached sources too.
- Setting `verification='verified'` requires typing `yes` to a prompt that
  states what verified means, and warns how many sources still lack an
  `archived_url`.

The Fortune and Reed developments that dead-ended before are now writable
as dated notes, which is what they were: an arrest and an attorney
complaint, neither of them a manner-of-death change.

## 2. Verify cases (no tooling can do this)

Zero of nine are verified. This is the weakest part of the public site and
the main thing between it and a citable case list.

Per case: open every source, check every field against it, archive each URL
at web.archive.org and store the snapshot in `case_sources.archived_url`,
then set `verification='verified'` with `verified_by`.

Three verified beats thirty unverified. Start with Fortune (52 sources) and
Raleigh (case 9, 8 sources) — best-documented.

Nzita (case 4) is still a near-empty stub with 7 sources attached but no
date, city, or ruling. Either fill it or mark it `rejected`.

## 3. GDELT query tuning — DONE

The quality column in the old version of this section was eyeballed, and it
had two of the four backwards. Measuring precision against the 160 triaged
candidates instead:

| query | n | precision | old guess |
|---|---|---|---|
| `"independent autopsy" hanging` | 50 | **90%** | "loose" |
| `"hanging from a tree" (body OR found OR death)` | 99 | 59% | "poor" |
| `"found hanging" (tree OR woods OR park)` | 9 | 33% | "decent" |
| `"ruled a suicide" hanging (family OR NAACP OR autopsy)` | 2 | **0%** | "best precision" |

The plan of "narrow the loose ones, protect the precise one" would have
narrowed the 90% query and protected the 0% one. The Grimm episodes were
also under `"found hanging"`, not `"hanging from a tree"`.

Changes made:

- `"found hanging"`: `(tree OR woods OR park)` → `(man OR woman OR teen OR
  student OR body)`. The location words let in an injured bald eagle and a
  goat cruelty case. Constraining on a person tested **broader** live, 135
  hits vs 91, and stops excluding deaths found somewhere other than a tree.
- `"ruled a suicide"`: dropped the third clause. The narrow form returned 2
  candidates in 30 days, neither relevant; the wider one surfaced the
  Rebecca Zahau verdict, a contested hanging death it had been missing.
- `NOISE_DOMAINS` gained fiction-recap sites only. Tabloids stay out: they
  cover real deaths, and for a case that got one story, that story is the
  record.

Rate limiting is a **request budget over a window, not spacing**. Probed
live: five queries 12s apart alternate 200/429, and 30s apart did worse.
So `todays_queries()` rotates two queries per run and `THROTTLE_SECONDS` is
30. `refresh.yml` moved 2d → 7d, because rotation is only free while the
window is wider than the 2.5d a query waits its turn — otherwise the days a
query sits out are never searched and the gap is invisible.
`check_coverage()` warns if that ever stops holding, and it is tested.

**Still true: do not narrow so far that single-local-story cases vanish.**

## 4. Small stuff

- ~~Move the root scripts into `tools/`; update README usage block.~~ Done.
  The four using CWD-relative `data/tracker.db` still expect to be run from
  the repo root, which is what the README shows.
- Delete `mk.py`, `mk2.py`, `mk3.py`, `bootstrap.py` if still present —
  they carry stale base64 copies and running one would revert a file.
- `src/tracker/cli.py` still has a `wonder` subcommand that always 403s.
  Either delete it or make it print the manual-export instructions.
- `tests/` has one test. `tools/check_repo.py` invariants could move into
  it and run in CI.

## 5. Worth considering separately

The WONDER suppression finding generalizes well beyond this topic: **summing
published state-level counts undercounts a rare cause of death by up to 91%**,
while common causes are unaffected. Any journalist pulling state CDC data on
something rare will make that error silently.

It's currently buried in this README. A short standalone writeup would help
people working on entirely unrelated stories.

---

## Rules that must not erode

These exist because the dataset's only real asset is being checkable.

1. **`gdelt.py` has no path to `cases`.** Scraped headlines become case
   records only when a person promotes them. `tools/check_repo.py` asserts
   this. Don't add an LLM classifier that writes fields — the phrasing that
   best predicts "a ruling landed" is identical to a family *disputing* a
   ruling. Reed is the live example: recorded `suicide`, new coverage is the
   family contesting. Same keywords, opposite meaning.

2. **No conclusion columns.** No `suspected_lynching`, no `foul_play`, no
   confidence score. The dataset records what authorities ruled and who
   disputes it. `check_repo.py` asserts this too.

3. **Suppressed is never zero.** `v_undetermined_ratio` returns NULL when
   any cell in the group is suppressed. Preserve that in new aggregates.

4. **No source, no change.** `followup.py` discards a whole update if no
   source URL is given. Keep that.

5. **Hostile sources belong in `case_sources`** when they contain factual
   reporting. A tracker citing only sympathetic outlets is one nobody
   outside the choir has to engage with.

6. **`official_manner` records what was ruled, not an assessment of it.**
   Police "investigating as a suicide" is not a ruling — that's `pending`.

7. **Never estimate `days_to_ruling`** from an article date. Two published
   dates or NULL.