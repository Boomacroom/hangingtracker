#!/usr/bin/env python3
"""
Load a CDC WONDER TSV export into mortality_agg.

    python load_wonder.py data/wonder/<export>.xls

WONDER's "xls" export is actually tab-separated text. The file has a
header row, a data block, then a "---" delimited footnote block holding
the query parameters and caveats. We parse the data and read the
footnotes, because two of those messages decide whether the numbers mean
anything:

    "Rows with zero Deaths are hidden"
    "Rows with suppressed Deaths are hidden"

When both are on, an absent row is ambiguous: it is EITHER zero deaths OR
one-to-nine deaths withheld for confidentiality. Those mean opposite
things about a jurisdiction's classification practice, and no downstream
query can recover the difference. This script refuses to guess and warns
loudly when it detects that state.

Re-export with Show Zero Values and Show Suppressed both True to remove
the ambiguity.
"""

from __future__ import annotations

import csv
import datetime as dt
import re
import pathlib
import sqlite3
import sys

DB = pathlib.Path("data/tracker.db")


def parse(path: pathlib.Path):
    data, footer = [], []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        in_footer = False
        for row in reader:
            if not row:
                continue
            if row[0].startswith("---") or (len(row) > 1 and not row[1].strip() and not in_footer and len(row) < 8):
                in_footer = True
            if in_footer:
                footer.append("\t".join(row))
                continue
            if len(row) < 8 or not row[1].strip():
                in_footer = True
                footer.append("\t".join(row))
                continue
            data.append(row)
    return header, data, footer


def col(header, *candidates):
    for c in candidates:
        if c in header:
            return header.index(c)
    return None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    path = pathlib.Path(sys.argv[1])
    if not path.exists():
        print(f"No such file: {path}")
        return 1
    if not DB.exists():
        print("No data/tracker.db. Run from the repo root.")
        return 1

    header, data, footer = parse(path)
    ftext = "\n".join(footer)

    print(f"\nparsed {len(data)} data rows from {path.name}")

    # --- the part that decides whether any of this is interpretable ---
    zeros_hidden = "Rows with zero Deaths are hidden" in ftext
    supp_hidden = "Rows with suppressed Deaths are hidden" in ftext
    grouped_by_year = col(header, "Year", "Year Code") is not None

    if zeros_hidden and supp_hidden:
        print("\n  WARNING: this export hides BOTH zero rows and suppressed rows.")
        print("  An absent row is therefore either 0 deaths or 1-9 deaths. Those")
        print("  are not the same claim and nothing downstream can tell them")
        print("  apart. Loading anyway, but do NOT compute ratios from this file.")
        print("  Re-export with Show Zero Values and Show Suppressed both True.")
    elif zeros_hidden:
        print("\n  Note: zero rows hidden, suppressed rows shown. Absent = 0 deaths.")
    elif supp_hidden:
        print("\n  Note: suppressed rows hidden, zero rows shown. Absent = 1-9 deaths.")
    else:
        print("\n  Good: zeros and suppressed rows both present. Absence is unambiguous.")

    if grouped_by_year:
        print("  Note: grouped by Year. At state-year granularity most Y20 cells")
        print("  fall under the suppression threshold. Pool years for ratios.")

    # Pooled exports have no Year column; take the span from the dataset
    # line so pooled rows are never silently compared to single-year rows.
    m = re.search(r"(\d{4})\s*-\s*(\d{4})", ftext)
    period_label = f"{m.group(1)}-{m.group(2)}" if m else None

    i_state = col(header, "State")
    i_year = col(header, "Year Code", "Year")
    i_code = col(header, "Underlying Cause of death Code")
    i_deaths = col(header, "Deaths")
    i_pop = col(header, "Population")
    i_rate = col(header, "Crude Rate")

    if i_code is None or i_deaths is None:
        print("\n  Could not find the expected columns. Header was:")
        print("   ", header)
        return 1

    conn = sqlite3.connect(DB)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    dataset = f"WONDER-MCD-expanded:{path.name}"
    loaded = supp = 0

    for row in data:
        def get(i):
            return row[i].strip() if i is not None and i < len(row) else None

        deaths_raw = (get(i_deaths) or "").replace(",", "")
        is_supp = deaths_raw in ("Suppressed", "Missing", "Not Applicable")
        deaths = None if (is_supp or not deaths_raw.isdigit()) else int(deaths_raw)
        supp += is_supp

        pop_raw = (get(i_pop) or "").replace(",", "")
        pop = int(pop_raw) if pop_raw.isdigit() else None
        rate_raw = (get(i_rate) or "").replace(",", "")
        try:
            rate = float(rate_raw)
        except ValueError:
            rate = None

        year_raw = (get(i_year) or "").strip()
        year = int(year_raw) if year_raw.isdigit() else None
        period = None if year is not None else period_label

        conn.execute(
            """
            INSERT INTO mortality_agg
                (dataset, year, period, state, race, icd10_code, icd10_label,
                 deaths, population, crude_rate, suppressed, unreliable, fetched_at)
            VALUES (?,?,?,?,NULL,?,?,?,?,?,?,0,?)
            ON CONFLICT DO UPDATE SET
                deaths = excluded.deaths,
                population = excluded.population,
                crude_rate = excluded.crude_rate,
                suppressed = excluded.suppressed,
                fetched_at = excluded.fetched_at
            """,
            (dataset, year, period, get(i_state), get(i_code),
             get(col(header, "Underlying Cause of death")),
             deaths, pop, rate, 1 if is_supp else 0, now),
        )
        loaded += 1

    conn.commit()
    print(f"\nloaded {loaded} rows ({supp} marked suppressed)")

    # Provenance: keep the query parameters with the data.
    out = path.with_suffix(".footnotes.txt")
    out.write_text(ftext, encoding="utf-8")
    print(f"footnotes saved -> {out}")
    print("Commit both. The query parameters are what make the numbers checkable.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
