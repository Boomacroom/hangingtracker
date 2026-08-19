from __future__ import annotations

import argparse
import pathlib
import sqlite3
import sys

from tracker.sources import gdelt, wonder

DB_PATH = pathlib.Path("data/tracker.db")
SCHEMA = pathlib.Path("schema.sql")


def connect(path: pathlib.Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def cmd_init(args):
    conn = connect()
    conn.executescript(SCHEMA.read_text())
    conn.commit()
    print(f"initialized {DB_PATH}")


def cmd_wonder(args):
    conn = connect()
    q = wonder.WonderQuery(years=tuple(args.years) if args.years else ())
    rows = wonder.parse(wonder.fetch(q))
    n = wonder.load(conn, q.dataset, rows)
    print(f"loaded {n} mortality rows")


def cmd_news(args):
    conn = connect()
    n = gdelt.collect(conn, timespan=args.timespan)
    print(f"{n} new candidates")


def cmd_triage(args):
    """Minimal review loop. Nothing reaches `cases` any other way."""
    conn = connect()
    rows = conn.execute(
        "SELECT id, title, domain, url FROM candidates "
        "WHERE triage = 'new' ORDER BY seendate DESC LIMIT ?",
        (args.limit,),
    ).fetchall()

    if not rows:
        print("nothing to triage")
        return

    for r in rows:
        print(f"\n[{r['id']}] {r['domain']}\n  {r['title']}\n  {r['url']}")
        choice = input("  (r)elevant / (i)rrelevant / (d)uplicate / (s)kip / (q)uit > ").strip().lower()
        if choice == "q":
            break
        mapping = {"r": "relevant", "i": "irrelevant", "d": "duplicate"}
        if choice in mapping:
            conn.execute("UPDATE candidates SET triage = ? WHERE id = ?", (mapping[choice], r["id"]))
            conn.commit()


def cmd_export(args):
    """Dump verified cases + aggregates to JSON for the static site."""
    import json

    conn = connect()
    out = pathlib.Path("site/data")
    out.mkdir(parents=True, exist_ok=True)

    cases = [dict(r) for r in conn.execute(
        "SELECT * FROM cases WHERE verification = 'verified' ORDER BY date_found DESC"
    )]
    ratios = [dict(r) for r in conn.execute("SELECT * FROM v_undetermined_ratio")]

    (out / "cases.json").write_text(json.dumps(cases, indent=2))
    (out / "ratios.json").write_text(json.dumps(ratios, indent=2))
    print(f"exported {len(cases)} verified cases, {len(ratios)} aggregate rows")


def main(argv=None):
    p = argparse.ArgumentParser(prog="tracker")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)

    w = sub.add_parser("wonder")
    w.add_argument("--years", nargs="*", type=int)
    w.set_defaults(func=cmd_wonder)

    n = sub.add_parser("news")
    n.add_argument("--timespan", default="7d")
    n.set_defaults(func=cmd_news)

    t = sub.add_parser("triage")
    t.add_argument("--limit", type=int, default=25)
    t.set_defaults(func=cmd_triage)

    sub.add_parser("export").set_defaults(func=cmd_export)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
