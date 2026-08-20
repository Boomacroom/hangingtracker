"""
Show what's actually in the candidate queue.

    python peek.py

Tells us whether the collector is pulling real material or noise, and
which queries are earning their place.
"""

import sqlite3
import pathlib
import sys

DB = pathlib.Path("data/tracker.db")
if not DB.exists():
    print("No data/tracker.db here. Run this from the repo root.")
    sys.exit(1)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

total = conn.execute("select count(*) from candidates").fetchone()[0]
print(f"\n{total} candidates total\n")

print("--- by query ---")
for r in conn.execute("""
    select matched_terms, count(*) n
    from candidates group by 1 order by n desc
"""):
    label = (r["matched_terms"] or "?")[:55]
    print(f"  {r['n']:>4}  {label}")

print("\n--- by domain (top 15) ---")
for r in conn.execute("""
    select domain, count(*) n
    from candidates group by 1 order by n desc limit 15
"""):
    print(f"  {r['n']:>4}  {r['domain']}")

print("\n--- titles (first 30) ---")
for i, r in enumerate(conn.execute("""
    select title, domain, seendate from candidates
    order by seendate desc limit 30
"""), 1):
    title = (r["title"] or "(no title)")[:72]
    print(f"  {i:>2}. {title}")
    print(f"      {r['domain']}  {r['seendate'] or ''}")

print("\n--- overlap check ---")
dupes = conn.execute("""
    select count(*) from (
        select url from candidates group by url having count(*) > 1
    )
""").fetchone()[0]
print(f"  duplicate urls in table: {dupes} (should be 0)")

seen_states = conn.execute("select count(*) from candidates where triage='new'").fetchone()[0]
print(f"  awaiting triage: {seen_states}")
print()
