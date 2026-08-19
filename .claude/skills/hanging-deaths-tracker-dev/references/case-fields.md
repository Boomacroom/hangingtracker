# `cases` field reference

Every field is nullable on purpose. The evidentiary standard column is the
important part: it says what you must have in hand before writing a value.

## Identity

| Field | Standard |
|---|---|
| `slug` | `slugify(name-state-year)`. Stable, never reused. |
| `decedent_name` | Named in at least one published news report. Do not add names that appear only on social media. |
| `age` | As reported. Conflicting ages across outlets: leave NULL, note both in `notes`. |

## Timing

| Field | Standard |
|---|---|
| `date_found` | Date the body was found, per reporting. Not the date of the story. |
| `date_last_seen` | Only if explicitly reported. |
| `days_to_ruling` | Computed from published dates only. If the ruling date is not reported, leave NULL rather than estimating from the article date. This field carries a lot of the project's argument, so an estimated value here is worse than a missing one. |

## Location

`city`, `county`, `state`, `location_type`. County matters most — it is the
unit that maps to a coroner or ME office, which is the unit of classification
practice. Fill it even when reporting only gives a city.

`location_type` is a loose bucket: `wooded area`, `campus`, `park`,
`residential`, `golf course`, `roadside`. Do not invent a taxonomy; add
values as they appear.

## Official ruling

| Field | Standard |
|---|---|
| `official_manner` | One of `suicide` / `undetermined` / `homicide` / `pending` / NULL. **Record what was ruled, as fact.** This is the authority's determination, not our assessment of it. |
| `official_ruled_by` | Name the office: `Cobb County PD`, `MS State Medical Examiner`. Police "indicating" suicide preliminarily is not the same as an ME ruling — if only the former is reported, use `pending` and say so in `notes`. |
| `autopsy_public` | 1 only if the report itself is public, not if its conclusion was described. |
| `independent_autopsy` | 1 if a family or org commissioned one, regardless of result. |

## Contestation

| Field | Standard |
|---|---|
| `family_contests` | 1 if a named family member is quoted disputing the ruling in published reporting. |
| `org_contests` | Semicolon-separated named orgs: `NAACP Milwaukee; BLM Georgia`. Named orgs only. |

These record **that a dispute exists and who is making it**. They are not a
verdict and must never be aggregated into anything that reads as one. A count
of contested rulings is a count of disputes, not of wrongful rulings.

## Provenance

| Field | Standard |
|---|---|
| `verification` | `unverified` on creation, always. `review` once someone has started. `verified` only when every non-NULL field traces to a row in `case_sources`. `rejected` for candidates that turned out not to fit. |
| `verified_by` | A human identifier. Never a script name. |
| `notes` | Where ambiguity goes. Conflicting reports, unclear ruling authority, anything a reader would need to interpret the row. Prefer a verbose note over a confident field. |

## What does not exist, and should not

There is no `suspected_lynching` field. No `foul_play_likely`. No confidence
score on whether the official ruling is correct. If someone asks for one, the
answer is that the dataset records rulings and disputes and lets readers
reason. Adding a conclusion column makes every row an assertion we would have
to defend individually.
