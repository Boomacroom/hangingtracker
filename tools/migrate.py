#!/usr/bin/env python3
"""
Bring an existing data/tracker.db up to the current schema.sql.

    python tools/migrate.py

`schema.sql` is written with CREATE TABLE IF NOT EXISTS, which is right
for a fresh database and does nothing at all for one that already has the
table with an older column list. Views and indexes in schema.sql are
dropped and rebuilt on every apply, but a rebuilt index that references a
column the table does not have yet fails the whole script -- so column
additions have to happen first, and they cannot be expressed in plain
SQL because SQLite has no ALTER TABLE ADD COLUMN IF NOT EXISTS.

Hence this: add missing columns, then apply schema.sql. Idempotent, safe
to run twice, and safe to run on a fresh database.

Adding a column here is not a schema change on its own. Add it to
schema.sql as well, or a fresh clone and a migrated one will disagree.
"""

from __future__ import annotations

import io
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "tracker.db"
SCHEMA = ROOT / "schema.sql"

# table -> column -> DDL fragment. Keep in sync with schema.sql.
COLUMNS = {
    "mortality_agg": {
        # What the query restricted to, as opposed to what it grouped by.
        # Without it a 15+ pooled row and an all-ages pooled row are
        # identical in every other column and get summed together.
        "age_filter": "TEXT NOT NULL DEFAULT 'all ages'",
    },
}


def ensure_columns(conn: sqlite3.Connection, verbose: bool = True) -> int:
    added = 0
    for table, cols in COLUMNS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if not have:
            continue  # table does not exist yet; schema.sql will create it
        for name, ddl in cols.items():
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                added += 1
                if verbose:
                    print(f"  + {table}.{name} {ddl}")
    if added:
        conn.commit()
    return added


def main() -> int:
    if not DB.exists():
        print("No data/tracker.db. Run: python -m tracker.cli init")
        return 1
    conn = sqlite3.connect(DB)

    print("\ncolumns:")
    added = ensure_columns(conn)
    if not added:
        print("  nothing to add")

    print("\nschema.sql:")
    conn.executescript(io.open(SCHEMA, encoding="utf-8").read())
    conn.commit()
    print("  applied (views and indexes rebuilt)")

    counts = dict(conn.execute(
        "SELECT age_filter, COUNT(*) FROM mortality_agg GROUP BY 1"))
    if counts:
        print("\nmortality_agg by age_filter:")
        for k, v in sorted(counts.items()):
            print(f"  {k:<12}{v:>6} rows")
    conn.close()
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
