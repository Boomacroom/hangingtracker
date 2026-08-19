#!/usr/bin/env python3
"""
Curate the candidate queue: cluster syndicated duplicates, then promote a
cluster into a case record.

    python curate.py              review clustered candidates
    python curate.py --cases      list existing cases
    python curate.py --promote    build a case from a cluster

Why clustering: Urban One and similar networks run identical copy across
dozens of station sites. Without grouping, one story looks like forty
candidates and triage becomes data entry. Grouping is presentation only,
every underlying URL is still stored and still becomes a separate source
row on the resulting case.

This script can create cases, which makes it the one place where the
human-in-the-loop rule actually lives. It never infers a field. Anything
you do not type stays NULL, and verification stays 'unverified' until
you have checked the sources yourself.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import pathlib
import re
import sqlite3
import sys

DB = pathlib.Path("data/tracker.db")
STOP = {"a", "an", "the", "in", "on", "at", "of", "from", "to", "for", "and",
        "or", "is", "was", "be", "been", "as", "by", "it", "its", "say", "says",
        "said", "police", "after", "new", "report", "reports"}


def connect() -> sqlite3.Connection:
    if not DB.exists():
        print("No data/tracker.db here. Run from the repo root.")
        sys.exit(1)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def normalize(title: str) -> str:
    t = re.sub(r"[^a-z0-9 ]", " ", (title or "").lower())
    words = [w for w in t.split() if w not in STOP and len(w) > 2]
    return " ".join(sorted(set(words)))


def cluster(rows: list[sqlite3.Row], threshold: float = 0.55) -> list[list[sqlite3.Row]]:
    """Greedy similarity grouping. Good enough for syndicated copy."""
    groups: list[list[sqlite3.Row]] = []
    keys: list[str] = []
    for r in rows:
        norm = normalize(r["title"])
        placed = False
        for i, key in enumerate(keys):
            if difflib.SequenceMatcher(None, norm, key).ratio() >= threshold:
                groups[i].append(r)
                placed = True
                break
        if not placed:
            groups.append([r])
            keys.append(norm)
    groups.sort(key=len, reverse=True)
    return groups


def show_clusters(conn: sqlite3.Connection, status: str = "new"):
    rows = conn.execute(
        "select * from candidates where triage = ? order by seendate desc",
        (status,),
    ).fetchall()
    if not rows:
        print(f"\nNothing with triage='{status}'.\n")
        return []

    groups = cluster(rows)
    print(f"\n{len(rows)} candidates -> {len(groups)} distinct stories\n")
    for i, g in enumerate(groups, 1):
        head = g[0]
        title = (head["title"] or "(no title)")[:68]
        domains = sorted({r["domain"] for r in g})
        print(f"[{i:>2}] {title}")
        print(f"     {len(g)} source(s): {', '.join(domains[:4])}"
              + (f" +{len(domains) - 4} more" if len(domains) > 4 else ""))
        print(f"     {head['seendate'] or ''}")
    print()
    return groups


def mark_cluster(conn: sqlite3.Connection, group: list[sqlite3.Row], status: str):
    ids = [r["id"] for r in group]
    conn.executemany(
        "update candidates set triage = ? where id = ?",
        [(status, i) for i in ids],
    )
    conn.commit()
    print(f"  marked {len(ids)} row(s) as {status}")


def ask(prompt: str, default: str | None = None) -> str | None:
    """Empty input means NULL. Unknown stays unknown; that is the point."""
    suffix = f" [{default}]" if default else " (blank = leave empty)"
    val = input(f"  {prompt}{suffix}: ").strip()
    if not val:
        return default
    return val


def promote(conn: sqlite3.Connection):
    groups = show_clusters(conn)
    if not groups:
        return

    pick = input("Cluster number to promote (or 'q'): ").strip()
    if pick.lower() == "q" or not pick.isdigit():
        return
    idx = int(pick) - 1
    if not 0 <= idx < len(groups):
        print("Out of range.")
        return
    group = groups[idx]

    print(f"\nBuilding a case from {len(group)} source(s).")
    print("Leave anything blank that the reporting does not establish.")
    print("A NULL is honest. A guess is not.\n")

    name = ask("decedent name")
    state = ask("state (2-letter)")
    if not name and not state:
        print("Need at least a name or a state to slug this. Aborting.")
        return

    year = (group[0]["seendate"] or "")[:4] or str(dt.date.today().year)
    base = re.sub(r"[^a-z0-9]+", "-", f"{name or 'unknown'}-{state or 'xx'}-{year}".lower())
    slug = ask("slug", base.strip("-"))

    age = ask("age")
    date_found = ask("date found (YYYY-MM-DD)")
    city = ask("city")
    county = ask("county (the ME/coroner jurisdiction, worth digging for)")
    location_type = ask("location type (wooded area / campus / park / ...)")

    print("\n  official_manner: what an authority actually RULED.")
    print("  Police 'investigating as a suicide' is NOT a ruling -> use 'pending'.")
    manner = ask("official manner (suicide/undetermined/homicide/pending)")
    if manner and manner not in ("suicide", "undetermined", "homicide", "pending"):
        print(f"  '{manner}' isn't a recognised value; storing NULL instead.")
        manner = None
    ruled_by = ask("ruled by (name the office)")

    print("\n  days_to_ruling: only from a PUBLISHED ruling date.")
    print("  Never inferred from an article date.")
    days = ask("days to ruling")

    fam = ask("family contests the ruling? (y/N)")
    orgs = ask("orgs contesting (semicolon separated)")
    indep = ask("independent autopsy commissioned? (y/N)")
    notes = ask("notes (conflicts, ambiguity, what's unresolved)")

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        cur = conn.execute(
            """
            INSERT INTO cases
                (slug, decedent_name, age, date_found, city, county, state,
                 location_type, official_manner, official_ruled_by,
                 days_to_ruling, independent_autopsy, family_contests,
                 org_contests, notes, verification, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'unverified', ?, ?)
            """,
            (slug, name, int(age) if age and age.isdigit() else None,
             date_found, city, county, state.upper() if state else None,
             location_type, manner, ruled_by,
             int(days) if days and days.isdigit() else None,
             1 if (indep or "").lower().startswith("y") else 0,
             1 if (fam or "").lower().startswith("y") else 0,
             orgs, notes, now, now),
        )
    except sqlite3.IntegrityError:
        print(f"\n  A case with slug '{slug}' already exists. Aborting.")
        return

    case_id = cur.lastrowid
    for r in group:
        conn.execute(
            """
            INSERT INTO case_sources
                (case_id, url, outlet, title, published_at, source_type, retrieved_at)
            VALUES (?,?,?,?,?, 'news', ?)
            ON CONFLICT (case_id, url) DO NOTHING
            """,
            (case_id, r["url"], r["domain"], r["title"], r["seendate"], now),
        )
    conn.executemany(
        "update candidates set triage='relevant', promoted_case=? where id=?",
        [(case_id, r["id"]) for r in group],
    )
    conn.commit()

    print(f"\n  Created case {case_id} ({slug}) with {len(group)} source(s).")
    print("  verification='unverified'. It will not export until you have")
    print("  checked every field against those sources yourself.")
    print("\n  Still to do: archive each source URL at web.archive.org and")
    print("  record the snapshot in case_sources.archived_url.")


def list_cases(conn: sqlite3.Connection):
    rows = conn.execute("""
        select c.id, c.slug, c.state, c.official_manner, c.verification,
               count(s.id) n
        from cases c left join case_sources s on s.case_id = c.id
        group by c.id order by c.date_found desc
    """).fetchall()
    print(f"\n{len(rows)} cases\n")
    for r in rows:
        print(f"  [{r['id']:>2}] {r['slug'][:38]:38} {r['state'] or '--':3} "
              f"{(r['official_manner'] or '-'):12} {r['verification']:11} {r['n']} src")
    print()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--promote", action="store_true")
    p.add_argument("--cases", action="store_true")
    args = p.parse_args()

    conn = connect()
    if args.cases:
        list_cases(conn)
        return
    if args.promote:
        promote(conn)
        return

    groups = show_clusters(conn)
    if not groups:
        return
    print("Mark clusters: number then r/i/d, e.g. '3 i'. 'p' to promote. 'q' to quit.")
    while True:
        cmd = input("> ").strip().lower().split()
        if not cmd or cmd[0] == "q":
            break
        if cmd[0] == "p":
            promote(conn)
            groups = show_clusters(conn)
            continue
        if len(cmd) == 2 and cmd[0].isdigit():
            idx = int(cmd[0]) - 1
            m = {"r": "relevant", "i": "irrelevant", "d": "duplicate"}
            if 0 <= idx < len(groups) and cmd[1] in m:
                mark_cluster(conn, groups[idx], m[cmd[1]])
                continue
        print("  format: '<number> r|i|d', or 'p', or 'q'")


if __name__ == "__main__":
    main()
