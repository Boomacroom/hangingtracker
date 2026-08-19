#!/usr/bin/env python3
"""
Migrate mortality_agg to support pooled multi-year rows.

    python migrate_pooled.py

Why: a pooled export (State x Cause across 2018-2024) has no single year,
but the original table declared year NOT NULL. Pooling is not a workaround
here, it is the only way most state-level cells clear WONDER's suppression
threshold, so the schema has to represent it as a first-class case rather
than forcing a fake year value.

Changes:
  - year becomes nullable
  - new `period` column records the span ('2018-2024') for pooled rows
  - unique index rebuilt over COALESCE'd keys so upserts still dedupe
    correctly when year or state is NULL

mortality_agg holds only re-derivable import data, so this rebuilds the
table rather than trying to patch constraints in place. Nothing in `cases`
or `case_sources` is touched.
"""

from __future__ import annotations

import pathlib
import sqlite3
import sys

DB = pathlib.Path("data/tracker.db")

NEW = """
CREATE TABLE mortality_agg_new (
    id              INTEGER PRIMARY KEY,
    dataset         TEXT NOT NULL,
    year            INTEGER,              -- NULL for pooled rows
    period          TEXT,                 -- e.g. '2018-2024' when pooled
    state           TEXT,
    state_fips      TEXT,
    race            TEXT,
    sex             TEXT,
    age_group       TEXT,
    icd10_code      TEXT NOT NULL,
    icd10_label     TEXT,
    deaths          INTEGER,
    population      INTEGER,
    crude_rate      REAL,
    suppressed      INTEGER DEFAULT 0,
    unreliable      INTEGER DEFAULT 0,
    fetched_at      TEXT NOT NULL
);
"""

IDX = """
CREATE UNIQUE INDEX idx_mortality_key ON mortality_agg_new (
    dataset,
    COALESCE(year, -1),
    COALESCE(period, ''),
    COALESCE(state, ''),
    COALESCE(race, ''),
    COALESCE(sex, ''),
    COALESCE(age_group, ''),
    icd10_code
);
"""

# A pooled row cannot be compared against a single-year row, so the view
# groups on period as well. Suppressed cells still poison a ratio: if any
# cell in the group is suppressed the ratio is NULL, never a guess.
VIEW = """
DROP VIEW IF EXISTS v_undetermined_ratio;
CREATE VIEW v_undetermined_ratio AS
SELECT
    year,
    period,
    state,
    race,
    SUM(CASE WHEN icd10_code LIKE 'X70%' AND suppressed = 0 THEN deaths END) AS suicide_hanging,
    SUM(CASE WHEN icd10_code LIKE 'Y20%' AND suppressed = 0 THEN deaths END) AS undetermined_hanging,
    SUM(CASE WHEN icd10_code LIKE 'X91%' AND suppressed = 0 THEN deaths END) AS assault_hanging,
    SUM(suppressed) AS suppressed_cells,
    CASE WHEN SUM(suppressed) > 0 THEN NULL ELSE
        CAST(SUM(CASE WHEN icd10_code LIKE 'Y20%' THEN deaths END) AS REAL)
        / NULLIF(SUM(CASE WHEN icd10_code LIKE 'X70%' THEN deaths END), 0)
    END AS undetermined_ratio
FROM mortality_agg
GROUP BY year, period, state, race;
"""


def main():
    if not DB.exists():
        print("No data/tracker.db. Run from the repo root.")
        return 1

    conn = sqlite3.connect(DB)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(mortality_agg)")}
    if "period" in cols:
        print("Already migrated.")
        return 0

    before = conn.execute("select count(*) from mortality_agg").fetchone()[0]
    print(f"mortality_agg rows before: {before}")

    conn.executescript(NEW)
    # The old view references mortality_agg, which blocks the rename.
    # Drop it first and rebuild from VIEW at the end.
    conn.execute("DROP VIEW IF EXISTS v_undetermined_ratio")
    conn.execute("""
        INSERT INTO mortality_agg_new
            (id, dataset, year, state, state_fips, race, sex, age_group,
             icd10_code, icd10_label, deaths, population, crude_rate,
             suppressed, unreliable, fetched_at)
        SELECT id, dataset, year, state, state_fips, race, sex, age_group,
               icd10_code, icd10_label, deaths, population, crude_rate,
               suppressed, unreliable, fetched_at
        FROM mortality_agg
    """)
    conn.execute("DROP TABLE mortality_agg")
    conn.execute("ALTER TABLE mortality_agg_new RENAME TO mortality_agg")
    conn.executescript(IDX.replace("mortality_agg_new", "mortality_agg"))
    conn.executescript(VIEW)
    conn.commit()

    after = conn.execute("select count(*) from mortality_agg").fetchone()[0]
    print(f"mortality_agg rows after:  {after}")
    print("year is now nullable; `period` added; unique index and view rebuilt.")
    print("\nUpdate schema.sql to match before committing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
