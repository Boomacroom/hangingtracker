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

## 1. Finish `tools/followup.py` (highest value, well-defined)

Two update attempts tonight both dead-ended because the fields that
actually needed changing aren't exposed. Concretely:

- **Fortune (case 3):** a person of interest was arrested. Not a manner
  change. Belongs in `notes`. No way to write it.
- **Reed (case 7):** family says their attorney never sent autopsy
  results. Not a ruling dispute — `family_contests` was already 1 and
  setting it again would assert the wrong thing. Belongs in `notes`.

Add to `--update`: `notes` (append with a date prefix, don't overwrite),
`verification`, `autopsy_public`, `independent_autopsy`, `date_last_seen`.

Two fixes while in there:

- **Ask for the source URL first.** It's currently last, so you type
  everything then lose it all if you don't have the link. Both sessions
  tonight hit this.
- **Make attach and update one transaction.** Attach runs before the
  prompts, so an abandoned session still links sources. Safe direction to
  fail, but surprising.

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

## 3. GDELT query tuning

In `src/tracker/sources/gdelt.py`. Current results, 30-day window:

| query | hits | quality |
|---|---|---|
| `"hanging from a tree"` | 99 | poor — Grimm episodes, an F/A-18 crash, boredpanda |
| `"independent autopsy"` | 50 | loose |
| `"found hanging"` | 9 | decent |
| `"ruled a suicide" hanging (family OR NAACP OR autopsy)` | 2 | **best precision** |

The budget is spent in the wrong place, and the best query keeps getting
429'd out. Needs iterating against live results — narrow the loose ones,
protect the precise one, maybe run it first.

Rate limiting: `THROTTLE_SECONDS = 15` and it still 429s. Raising it made
things worse, so it's likely a rolling window rather than per-request
spacing. Consider fewer queries per run, rotating across days.

**Do not narrow so far that single-local-story cases vanish.** Those are
exactly the ones nobody else is counting.

## 4. Small stuff

- Move `curate.py`, `peek.py`, `analyze.py`, `load_wonder.py`,
  `migrate_pooled.py` into `tools/`; update README usage block.
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