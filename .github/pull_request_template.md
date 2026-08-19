## What changed

<!-- If this touches `cases` or `case_sources`, fill in everything below. -->

## Case record changes

**Every non-NULL field must trace to a URL in `case_sources`.**

- [ ] Every asserted field has a source row
- [ ] Every source URL has a web.archive.org snapshot in `archived_url`
- [ ] Unknown fields left NULL, not estimated
- [ ] `days_to_ruling` from published ruling dates only (NULL if not reported)
- [ ] `official_manner` records what was ruled, not an assessment of it
- [ ] Checked JULIAN's database (julianfreedom.org) for an existing record
- [ ] No new column encodes a conclusion about a case

## Aggregate / query changes

- [ ] Suppressed WONDER cells yield NULL, never 0
- [ ] Any new claim is about classification practice, not individual deaths
