# Summing state CDC WONDER figures undercounts rare causes of death by up to 91%

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
and the sum you compute is a floor that can sit **70-90% below the actual
national count**.

The trap is that both numbers come from the same tool, look equally
official, and differ by an order of magnitude.

## Worked example

Deaths by hanging, strangulation, or suffocation with **undetermined
intent** (ICD-10 `Y20`), underlying cause, 2018-2024, from the Multiple
Cause of Death 2018-2024 Single Race file.

Two queries. Same file, same years, same cause codes. The only difference
is whether *State* is in the Group By.

| Year | Summed from the 50 state figures | Actual national count | Missing |
|---:|---:|---:|---:|
| 2018 | 23 | 154 | 85% |
| 2019 | 38 | 156 | 76% |
| 2020 | 33 | 133 | 75% |
| 2021 | 13 | 144 | **91%** |
| 2022 | 39 | 159 | 75% |
| 2023 | 44 | 143 | 69% |
| 2024 | 21 | 131 | 84% |

In 2021 the state-by-state view shows 13 such deaths in the entire United
States. There were 144.

Now the same two queries for a **common** cause, suicide by the same
mechanism (`X70`), for comparison:

| Year | Summed from states | Actual national | Missing |
|---:|---:|---:|---:|
| 2018 | 13,840 | 13,840 | 0% |
| 2021 | 12,431 | 12,431 | 0% |
| 2024 | 11,453 | 11,453 | 0% |

Zero error. Every state has well over 10, so nothing is withheld.

And a category in between, assault by the same mechanism (`X91`), a few
hundred deaths a year nationally rather than a few thousand or a few
dozen:

| Year | Summed from states | Actual national | Missing |
|---:|---:|---:|---:|
| 2018 | 356 | 485 | 27% |
| 2022 | 216 | 375 | 42% |
| 2024 | 274 | 407 | 33% |

The error tracks rarity smoothly: 0% at thousands of deaths a year, about
a third at hundreds, four fifths at around a hundred. There is no
threshold at which it switches on, and no size at which you are safe
without checking.

**This is the part that makes it dangerous.** The error does not scale
with the size of the number. It is near-zero for common causes and
enormous for rare ones, which means a ratio between a common and a rare
category — exactly the kind of comparison people build — is wrong by
whatever factor the suppression happens to impose. If you validate your
pipeline against a common cause of death, it will look correct.

## It gets worse with each breakdown

Suppression compounds with granularity, because each added dimension
splits the same deaths into more, smaller cells.

For `Y20` at **State × Year**, 357 cells: **18 were published. 339 were
withheld.** Forty-three states showed no visible count in any of the
seven years. That breakdown cannot support a state comparison at all;
there is essentially nothing in it.

Pooling all seven years into one cell per state brings 29 states into
range. The other 22 remain withheld — meaning fewer than 10 such deaths
across seven years, which is *not* the same as none, and must never be
recorded as 0.

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

## What to do instead

1. **For national figures, run a query with no state breakdown.** Not a
   sum of states. It takes one extra export and it is the difference
   between 13 and 144.
2. **For state comparisons, pool years.** One cell per state clears the
   threshold far more often than one cell per state-year.
3. **Always enable Show Zero Values and Show Suppressed**, so a missing
   row is not two different things at once.
4. **Never coerce `Suppressed` to 0.** Carry it as its own state
   through every aggregate. The correct output for a group containing a
   suppressed cell is "unknown", not a number.
5. **Report coverage alongside every rate.** "29 of 51 jurisdictions
   measurable" is part of the finding, not a footnote to it.
6. **Do not validate the pipeline on a common cause of death.** It will
   pass and tell you nothing.

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
  column, and the 18-of-357 figure

The exports, the query-parameter footnotes CDC ships with each one, the
loader, and the analysis are in this repository. The numbers in the
tables above are printed by `python tools/analyze.py`.

One note on the API: WONDER's API cannot answer any of this. Per CDC's
own documentation, only national data are available to API queries for
the National Vital Statistics System, and any query grouping or limiting
by state returns HTTP 403. State-level work is a manual web export. These
data update annually, so that is an hour a year, not a daily burden.
