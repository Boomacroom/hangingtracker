# Summing state CDC WONDER figures can undercount a rare cause of death by 100%

*A note for anyone pulling state-level mortality data. Nothing here is
specific to the topic this repo studies; the arithmetic applies to any
cause of death that is uncommon.*

## The short version

CDC WONDER withholds any cell with fewer than 10 deaths, returning the
literal string `Suppressed`. Everyone knows this. What is less obvious is
what it does to a **national total assembled by adding up the states**.

For a common cause of death, nothing. Every state clears 10, nothing is
withheld, the sum is right.

For a rare one, the suppression is not a rounding error. It is most of
the data. Each state contributes 0 to 9 invisible deaths, 50 times over,
and the sum you compute is a floor that can sit **anywhere from 70% to
100% below the actual national count** — in five of the seven years
measured here, the state figures sum to exactly zero.

The trap is that both numbers come from the same tool, look equally
official, and differ by an order of magnitude.

## Worked example

Deaths by hanging, strangulation, or suffocation with **undetermined
intent** (ICD-10 `Y20`), underlying cause, 2018-2024, ages 15+, from the
Multiple Cause of Death 2018-2024 Single Race file.

Two queries. Same file, same years, same cause codes, same age filter.
The only difference is whether *State* is in the Group By.

| Year | Summed from the 50 state figures | Actual national count | Missing |
|---:|---:|---:|---:|
| 2018 | 0 | 85 | **100%** |
| 2019 | 0 | 74 | **100%** |
| 2020 | 0 | 68 | **100%** |
| 2021 | 0 | 76 | **100%** |
| 2022 | 11 | 71 | 85% |
| 2023 | 10 | 91 | 89% |
| 2024 | 0 | 69 | **100%** |

In five of seven years the state-by-state view shows **zero** such deaths
in the entire United States. There were 68 to 91.

Now the same two queries for a **common** cause, suicide by the same
mechanism (`X70`), same age filter:

| Year | Summed from states | Actual national | Missing |
|---:|---:|---:|---:|
| 2018 | 13,471 | 13,471 | 0% |
| 2021 | 12,107 | 12,107 | 0% |
| 2024 | 11,188 | 11,188 | 0% |

Zero error, every year. Every state has well over 10, so nothing is
withheld.

**This is the part that makes it dangerous.** The error does not scale
with the size of the number. It is exactly zero for common causes and can
be total for rare ones, which means a ratio between a common and a rare
category — exactly the kind of comparison people build — is wrong by
whatever factor the suppression happens to impose. If you validate your
pipeline against a common cause of death, it will look perfect.

## It gets worse with each breakdown

Suppression compounds with granularity, because each added dimension
splits the same deaths into more, smaller cells.

For `Y20` at **State x Year**, 357 cells, exported properly with zeros and
suppressed rows both shown:

| | cells |
|---|---:|
| usable published count | **2** |
| withheld (1-9 deaths) | 222 |
| true zero | 133 |

Two. That breakdown cannot support a state comparison at all.

Pooling all seven years into one cell per state brings 20 states into
range. The other 31 remain withheld — meaning fewer than 10 such deaths
across seven years, which is *not* the same as none, and must never be
recorded as 0.

Note the 133 true zeros. Those are real: a state that genuinely recorded
no undetermined-intent deaths of this kind in that year. They are only
distinguishable from the 222 withheld cells because the export was run
with both **Show Zero Values** and **Show Suppressed** enabled. Which
brings us to the trap this project itself fell into.

## The second trap: a missing row is ambiguous

By default, WONDER hides rows with zero deaths *and* rows with suppressed
deaths. When both are hidden, an absent row means **either 0 deaths or
1-9 deaths withheld**.

For classification data those are opposite claims about a jurisdiction.
"This coroner's office never once recorded undetermined intent" and "this
office recorded it up to nine times" are different stories, and no
downstream query can recover which one you have.

In Quick Options, set **Show Zero Values** and **Show Suppressed** to
**True**. Then absence is unambiguous and every cell states its own case.

**This is not a hypothetical failure.** The first version of this analysis
ran the State x Year export with both set to False. 339 of 357 cells came
back absent, and they were reported — on a public page, in a figure whose
whole subject is suppression — as "withheld". Re-running the same query
with both enabled showed that 133 of those absences were true zeros and
222 were withheld. The loader printed a warning about it at the time. The
warning was not acted on for several days.

The lesson is not that the settings matter, which everyone already knows.
It is that the resulting file looks completely normal: correct columns,
plausible counts, no error, and a quiet undercount that survives every
check you would think to run.

## What to do instead

1. **For national figures, run a query with no state breakdown.** Not a
   sum of states. It takes one extra export and it is the difference
   between 0 and 85.
2. **For state comparisons, pool years.** One cell per state clears the
   threshold far more often than one cell per state-year: 20 states
   measurable pooled, against 2 usable cells unpooled.
3. **Always enable Show Zero Values and Show Suppressed**, so a missing
   row is not two different things at once.
4. **Never coerce `Suppressed` to 0.** Carry it as its own state
   through every aggregate. The correct output for a group containing a
   suppressed cell is "unknown", not a number.
5. **Report coverage alongside every rate.** "20 of 51 jurisdictions
   measurable" is part of the finding, not a footnote to it.
6. **Do not validate the pipeline on a common cause of death.** It will
   pass and tell you nothing.

6. **Record what the query filtered to, not just what it grouped by.** A
   filter appears nowhere in the exported rows and changes what every one
   of them means. Two exports that differ only by an age filter are
   indistinguishable once loaded, and will silently sum together.

Concretely, in this repo, the derived view returns `NULL` rather than a
ratio whenever any cell in the group is suppressed, and exposes a
`suppressed_cells` count so coverage is always visible:

```sql
CASE WHEN SUM(suppressed) > 0 THEN NULL ELSE
    CAST(SUM(CASE WHEN icd10_code LIKE 'Y20%' THEN deaths END) AS REAL)
    / NULLIF(SUM(CASE WHEN icd10_code LIKE 'X70%' THEN deaths END), 0)
END AS undetermined_ratio
```

The cost of that rule is that half the states report nothing. The benefit
is that the half reporting something are right.

## Who this affects

Anyone building state comparisons on an uncommon outcome. Maternal
mortality by state. Specific overdose subtypes. Occupational fatalities
by industry. Deaths in custody. Rare pediatric causes. Any cause split by
race within a state, which drops cell sizes by another factor of five.

None of these have anything to do with each other, and all of them break
the same way.

## Reproducing this

Everything above comes from two exports of [Multiple Cause of Death,
2018-2024, Single Race](https://wonder.cdc.gov/mcd-icd10-expanded.html)
(`D157`), UCD ICD-10 codes `X70`, `X91`, `Y20`, Show Totals off, Show
Zero Values and Show Suppressed on:

- Group by Year + Underlying Cause, **no state** → the national counts
- Group by State + Year + Underlying Cause → the summed-from-states
  column, and the 2-usable-of-357 figure

Both filtered to **ages 15+**. That filter matters for this cause: the
codes cover suffocation as well as hanging, and below age 5 they pick up
infant suffocation deaths whose `X70` denominator is structurally zero.
Unfiltered, 36% of the `Y20` numerator is deaths that cannot appear in
the denominator at all. Check whether your own cause has an equivalent
population where the ratio is undefined rather than small.

The exports, the query-parameter footnotes CDC ships with each one, the
loader, and the analysis are in this repository. The numbers in the
tables above are printed by `python tools/analyze.py`.

One note on the API: WONDER's API cannot answer any of this. Per CDC's
own documentation, only national data are available to API queries for
the National Vital Statistics System, and any query grouping or limiting
by state returns HTTP 403. State-level work is a manual web export. These
data update annually, so that is an hour a year, not a daily burden.
