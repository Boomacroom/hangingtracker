# CDC WONDER access reference

## The API cannot serve this project

Per CDC's [API documentation](https://wonder.cdc.gov/wonder/help/wonder-api.html):

> only national data are available for query by the API. Queries for
> mortality and births statistics from the National Vital Statistics
> System cannot limit or group results by any location field, such as
> Region, Division, State or County, or Urbanization.

A state-level API request returns **HTTP 403**. This is not a bad
parameter code and no amount of tuning fixes it. The location fields
(`V9`, `V10`, `V27`) and urbanization fields (`V11`, `V19`) are available
in the web application only.

`tracker wonder` in the CLI still exists but only national queries can
succeed. **The state-level workflow is a manual web export.** That is
acceptable: these data update annually.

## Manual export workflow

Use **Multiple Cause of Death, 2018-2024, Single Race** (`D157`,
mcd-icd10-expanded). Do NOT mix with the 1999-2020 file (`D77`): bridged
race vs single race is a real discontinuity and collapsing it silently
manufactures artifacts. Staying inside 2018-2024 avoids it entirely.

Codes, and the pairing is the whole point:

| Code | Meaning |
|---|---|
| `X70` | Intentional self-harm by hanging/strangulation/suffocation |
| `Y20` | Same mechanism, **undetermined intent** |
| `X91` | Assault by hanging/strangulation/suffocation |

Form settings that matter:

- **UCD - ICD-10 Codes** (`F_D157.V2`), not MCD (`F_D157.V13`). UCD is the
  single ruled underlying cause; MCD is any of 20 contributing causes.
  Only UCD measures the classification decision.
- Group By: `State` (`D157.V9-level1`), `Year` (`D157.V1-level1`),
  `Underlying Cause of death` (`D157.V2-level3`) as needed per export.
- **Show Totals: Disabled** — total rows break the parser.
- **Show Zero Values: True** and **Show Suppressed: True** — see below.

### Three exports, three purposes

| Group by | Answers | Suppression |
|---|---|---|
| State + Cause, pooled | cross-state comparison | 22 states withheld |
| Year + Cause, no state | true national trend | none |
| State + Year + Cause | **unusable for ratios** | 339/357 cells hidden |

## Suppression: the trap that actually bites

WONDER withholds any cell under 10 deaths. Undetermined-intent hangings
are rare enough that this dominates.

**Measured, not theoretical:** at State × Year × Cause, only **18 of 357**
state-year cells had a visible Y20 count. 43 states showed zero visible
Y20 across all seven years. Pooling years brought 29 states into range.

Two distinct failure modes:

1. **Hidden-row ambiguity.** With Show Zeros and Show Suppressed both
   False, WONDER omits the row entirely and an absent row is *either* 0
   deaths *or* 1-9 withheld. Those are opposite claims about a coroner's
   office. Always export with both True. `load_wonder.py` parses the
   footnote messages and warns when it detects this state.
2. **Treating suppressed as zero.** `v_undetermined_ratio` returns NULL,
   never a number, when any cell in the group is suppressed, and exposes
   `suppressed_cells` so coverage is visible. Preserve that in any new
   aggregate. A false zero here reads as "this state never rules
   undetermined," which is exactly the overclaim that would discredit the
   project.

Also: **national sums computed from a state-broken export are floors**,
not counts, since they exclude every hidden cell. Use a no-state export
for real national figures.

## Export file format

The `.xls` is tab-separated text. Header row, data block, then a `---`
delimited footer with query parameters and caveats. `load_wonder.py`
writes the footer to a `.footnotes.txt` sidecar; commit it, since the
query parameters are what make the numbers reproducible.

Columns for a State + Year + Cause export:

```
Notes | State | State Code | Year | Year Code |
Underlying Cause of death | Underlying Cause of death Code |
Deaths | Population | Crude Rate | CI Lower | CI Upper
```

Pooled exports simply omit the Year columns. `mortality_agg.year` is
nullable and `period` records the span (`'2018-2024'`) so pooled rows are
never silently compared against single-year rows.

Suppressed cells contain the literal string `Suppressed`; unreliable
rates contain `Unreliable` (the count is real, the rate is noisy).

## What the numbers support

Measured result, 2018-2024 pooled: undetermined-per-100-suicide ranges
from Colorado 0.56 to Alaska 3.84, roughly sevenfold.

**Mississippi ranks 3rd highest (2.69), not lowest.** If someone proposes
a feature or framing premised on Southern jurisdictions under-using
"undetermined," the data contradicts it. Say so. The explanations the data
cannot distinguish include coroner-vs-ME certification systems, office
resourcing, local convention, and caution under scrutiny.

The spread is a finding about classification practice that warrants
explanation. It is not itself an explanation, and it says nothing about
any individual death.

## Rate limits

If ever hitting the API for national figures, CDC asks for one query at a
time, roughly every 2 minutes. Do not run parallel instances.
