#!/usr/bin/env python3
"""
Track developments on cases you already have.

    python tools/followup.py            new coverage matching existing cases
    python tools/followup.py --pending  cases awaiting a ruling
    python tools/followup.py --update N record a development on case N

The collector finds new cases well enough. What it could not do until now
is notice that today's candidates are about a case already in the table.
Most of this dataset's value is longitudinal: a death ruled `pending` in
August and `suicide` in November is the whole point, and `days_to_ruling`
cannot be filled in any other way.

Every field change is written to `case_updates` with the source that
justified it. A ruling recorded without a source URL is not recorded.
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "tracker.db"

AUDIT = """
CREATE TABLE IF NOT EXISTS case_updates (
    id          INTEGER PRIMARY KEY,
    case_id     INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    field       TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    source_url  TEXT,
    changed_at  TEXT NOT NULL,
    changed_by  TEXT
);
CREATE INDEX IF NOT EXISTS idx_updates_case ON case_updates (case_id, changed_at);
"""


def connect():
    if not DB.exists():
        print("No data/tracker.db. Run from the repo root.")
        sys.exit(1)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(AUDIT)
    return conn


# Phrases that suggest a case moved, not just that it was covered again.
# These RANK the queue. They never write a field: "ruled a suicide" in a
# headline can be a family disputing the ruling, a lawyer announcing an
# independent autopsy, or an opinion column. Only a person can tell which.
SIGNALS = [
    (3, r"\bruled?\b.{0,24}\b(suicide|homicide|undetermined|accident)"),
    (3, r"\bcause of death\b.{0,20}\b(released|determined|revealed|announced)"),
    (3, r"\bautopsy (results?|report)\b.{0,20}\b(released|show|reveal)"),
    (3, r"\bmedical examiner\b.{0,24}\b(rules?|ruled|determin|releas)"),
    (2, r"\b(arrest|charged|indicted|person of interest)\b"),
    (2, r"\blawsuit\b|\bsues?\b|\bfiled suit\b"),
    (2, r"\bindependent autopsy\b"),
    (2, r"\b(reopen|reopened|new investigation)\b"),
    (1, r"\b(family|mother|father|sister|brother)\b.{0,45}\b(dispute|reject|question|demand)"),
    (1, r"\bstill no answers\b|\bno cause\b|\bhas ?n.t (revealed|released)\b"),
]


def signal_score(title: str) -> tuple[int, list[str]]:
    """Rank a headline by how likely it marks a development. Never decides one."""
    t = (title or "").lower()
    score, why = 0, []
    for weight, pat in SIGNALS:
        if re.search(pat, t):
            score += weight
            why.append(re.sub(r"\\b|\.\{0,\d+\}", " ", pat)[:26].strip())
    return score, why


def terms_for(case: sqlite3.Row) -> list[str]:
    """Distinctive strings that would appear in coverage of this case."""
    out = []
    if case["decedent_name"]:
        parts = [p for p in re.split(r"[\s,]+", case["decedent_name"]) if len(p) > 2]
        if parts:
            out.append(parts[-1].lower())          # surname
            out.append(case["decedent_name"].lower())
    if case["city"]:
        out.append(case["city"].lower())
    return [t for t in out if t]


def find_new_coverage(conn):
    """Candidates that look like they concern a case already on file."""
    cases = conn.execute("SELECT * FROM cases").fetchall()
    cands = conn.execute("""
        SELECT * FROM candidates
        WHERE promoted_case IS NULL AND triage IN ('new','relevant')
    """).fetchall()

    hits = {}
    for case in cases:
        terms = terms_for(case)
        if not terms:
            continue
        matched = [c for c in cands
                   if any(t in (c["title"] or "").lower() for t in terms)]
        if matched:
            hits[case["id"]] = (case, matched)
    return hits


def show_new_coverage(conn):
    hits = find_new_coverage(conn)
    if not hits:
        print("\nNo unlinked candidates match an existing case.\n")
        return
    # Rank by strongest signal, so the case most likely to have moved is first.
    ranked = []
    for cid, (case, matched) in hits.items():
        scored = sorted(((signal_score(m["title"])[0], m) for m in matched),
                        key=lambda x: -x[0])
        ranked.append((scored[0][0] if scored else 0, cid, case, scored))
    ranked.sort(key=lambda x: -x[0])

    print(f"\nNew coverage matching {len(hits)} case(s), most likely development first:\n")
    for top, cid, case, scored in ranked:
        name = case["decedent_name"] or case["slug"]
        mark = "**" if top >= 3 else ("* " if top >= 2 else "  ")
        print(f"{mark}[{cid}] {name}  (recorded: {case['official_manner'] or 'no ruling'})"
              f"   {len(scored)} new item(s)")
        for sc, m in scored[:4]:
            flag = f" <- signal {sc}" if sc >= 2 else ""
            print(f"     {(m['title'] or '')[:64]}{flag}")
            print(f"       {m['domain']}  {m['seendate'] or ''}")
        if len(scored) > 4:
            print(f"     ... {len(scored) - 4} more")
        print()

    strong = [r for r in ranked if r[0] >= 3]
    if strong:
        print("** = a headline suggests the ruling may have changed. Read it before")
        print("     recording anything; the phrasing that scores highest is also")
        print("     what a family disputing a ruling sounds like.\n")
    print("Attach all sources:   python tools/followup.py --attach <id>")
    print("Record a change:      python tools/followup.py --update <id>\n")


def show_pending(conn):
    rows = conn.execute("""
        SELECT id, slug, decedent_name, state, date_found, official_manner,
               days_to_ruling,
               (SELECT COUNT(*) FROM case_sources s WHERE s.case_id = cases.id) n
        FROM cases
        WHERE official_manner IS NULL OR official_manner = 'pending'
        ORDER BY date_found DESC NULLS LAST
    """).fetchall()
    if not rows:
        print("\nNo cases awaiting a ruling.\n")
        return
    print(f"\n{len(rows)} case(s) awaiting a ruling:\n")
    today = dt.date.today()
    for r in rows:
        age = ""
        if r["date_found"]:
            try:
                d = dt.date.fromisoformat(r["date_found"])
                age = f"{(today - d).days}d since found"
            except ValueError:
                pass
        print(f"  [{r['id']:>2}] {(r['decedent_name'] or r['slug'])[:34]:34} "
              f"{r['state'] or '--':3} {age:>18}  {r['n']} src")
    print("\nThese are the rows that make the dataset worth maintaining.")
    print("A ruling that lands and never gets recorded is a lost data point.\n")


def attach_all(conn, case_id: int):
    """
    Link every matching candidate to a case as a source. Mechanical work,
    no judgment: it only records that an outlet covered this case. It
    touches no case field, so it cannot change what the dataset claims.
    """
    hits = find_new_coverage(conn)
    if case_id not in hits:
        print(f"\nNo unlinked candidates match case {case_id}.\n")
        return
    case, matched = hits[case_id]
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    n = 0
    for m in matched:
        cur = conn.execute("""
            INSERT INTO case_sources (case_id, url, outlet, title, published_at,
                                      source_type, retrieved_at)
            VALUES (?,?,?,?,?, 'news', ?)
            ON CONFLICT (case_id, url) DO NOTHING
        """, (case_id, m["url"], m["domain"], m["title"], m["seendate"], now))
        n += cur.rowcount if cur.rowcount > 0 else 0
        conn.execute("UPDATE candidates SET promoted_case = ?, triage = 'relevant' "
                     "WHERE id = ?", (case_id, m["id"]))
    conn.commit()
    name = case["decedent_name"] or case["slug"]
    print(f"\n  Attached {n} source(s) to [{case_id}] {name}.")
    print(f"  Ruling still recorded as: {case['official_manner'] or 'none'}")

    flagged = [(s_, m) for s_, m in ((signal_score(m["title"])[0], m) for m in matched) if s_ >= 3]
    if flagged:
        print(f"\n  {len(flagged)} of these suggest a ruling may have landed:")
        for s_, m in flagged[:5]:
            print(f"    {(m['title'] or '')[:62]}")
        print(f"\n  Read them, then: python tools/followup.py --update {case_id}")
    print()


def ask(prompt, default=None):
    s = f" [{default}]" if default else " (blank = skip)"
    v = input(f"  {prompt}{s}: ").strip()
    return v or default


def ask_bool(prompt, current):
    """y/n prompt returning '1'/'0', or None to leave the field alone."""
    v = ask(f"{prompt} (y/n)")
    if not v:
        return None
    if v.lower()[0] not in "yn":
        print(f"    '{v}' is not y or n. Leaving unchanged.")
        return None
    new = "1" if v.lower().startswith("y") else "0"
    return new if new != str(current or 0) else None


def ask_date(prompt, current):
    """ISO date prompt. A date that won't parse is refused, not stored."""
    v = ask(prompt)
    if not v:
        return None
    try:
        dt.date.fromisoformat(v)
    except ValueError:
        print(f"    '{v}' is not YYYY-MM-DD. Leaving unchanged.")
        return None
    return v if v != current else None


# Fields stored as INTEGER. Everything else is written as text.
INT_FIELDS = ("days_to_ruling", "family_contests",
              "autopsy_public", "independent_autopsy", "age")

# Blank means "leave this alone", which gave no way to empty a field that
# should never have been filled. A field asserting something false is worse
# than an empty one, so clearing has to be expressible.
CLEAR = "-"

VERIFICATION_VALUES = ("unverified", "review", "verified", "rejected")


def _short(v, n=46, tail=False):
    """
    Collapse a value for the change summary. `tail` shows the end rather than
    the start, which is the only informative part of an appended note: both
    versions share a long identical head.
    """
    if v is None:
        return "None"
    s = " ".join(str(v).splitlines()[-1].split()) if tail else " ".join(str(v).split())
    return s if len(s) <= n else s[:n - 3] + "..."


def _confirm_verified(conn, case_id: int) -> bool:
    """
    'verified' is the one value in this table that is a claim about the work
    done, not about the case. It means a person opened every source and
    checked every field against it. The prompt states that, because a
    verified row that nobody actually checked is worse than an unverified
    one: it spends credibility the dataset has not earned.
    """
    n_src, n_arch = conn.execute("""
        SELECT COUNT(*), COUNT(archived_url) FROM case_sources WHERE case_id = ?
    """, (case_id,)).fetchone()
    print(f"\n    'verified' means: every one of these {n_src} source(s) opened,")
    print("    every populated field checked against them, every URL archived.")
    if n_arch < n_src:
        print(f"    {n_src - n_arch} of {n_src} source(s) have no archived_url yet.")
        print("    Local coverage disappears; archive them before verifying.")
    return (input("    Confirm you did that (yes): ").strip().lower() == "yes")


def append_note(existing: str | None, addition: str) -> str:
    """
    Notes accumulate. Overwriting one would silently drop the context that
    justified an earlier reading of the record, so entries are dated and
    appended.
    """
    entry = f"[{dt.date.today().isoformat()}] {addition}"
    return f"{existing.rstrip()}\n{entry}" if existing else entry


def update_case(conn, case_id: int):
    case = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    if not case:
        print(f"No case {case_id}.")
        return

    name = case["decedent_name"] or case["slug"]
    print(f"\n  Case {case_id}: {name}")
    print(f"  current ruling: {case['official_manner'] or 'none recorded'}")
    print(f"  found: {case['date_found'] or 'unknown'}")
    print(f"  verification: {case['verification']}"
          f"{' by ' + case['verified_by'] if case['verified_by'] else ''}")
    if case["notes"]:
        last = case["notes"].strip().splitlines()[-1]
        print(f"  last note: {last[:66]}")
    print()

    # The source is asked for before anything else on purpose. It used to be
    # the last prompt, which meant discovering you had no link only after
    # typing the whole update, and losing all of it. Nothing below is worth
    # collecting without it.
    src = ask("source URL justifying this update")
    if not src:
        print("\n  No source given. Nothing recorded. This is deliberate:")
        print("  an unsourced ruling is exactly what this dataset must not hold.\n")
        return
    who = ask("your name or handle", "unattributed")

    # Offer to attach matching candidates as sources.
    chosen_any = False
    hits = find_new_coverage(conn)
    if case_id in hits:
        _, matched = hits[case_id]
        print(f"  {len(matched)} unlinked candidate(s) mention this case:")
        for i, m in enumerate(matched, 1):
            print(f"    {i}. {(m['title'] or '')[:60]}  [{m['domain']}]")
        pick = input("\n  Attach which? (numbers, 'a' for all, blank to skip): ").strip().lower()
        chosen = matched if pick == "a" else [
            matched[int(x) - 1] for x in re.findall(r"\d+", pick)
            if 0 < int(x) <= len(matched)]
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        for m in chosen:
            conn.execute("""
                INSERT INTO case_sources (case_id, url, outlet, title, published_at,
                                          source_type, retrieved_at)
                VALUES (?,?,?,?,?, 'news', ?)
                ON CONFLICT (case_id, url) DO NOTHING
            """, (case_id, m["url"], m["domain"], m["title"], m["seendate"], now))
            conn.execute("UPDATE candidates SET promoted_case = ?, triage = 'relevant' "
                         "WHERE id = ?", (case_id, m["id"]))
        # Deliberately not committed here. The attach and the field changes
        # land together or not at all, so abandoning the prompts below leaves
        # no trace rather than half an edit.
        chosen_any = bool(chosen)
        if chosen:
            print(f"  attached {len(chosen)} source(s) (pending)")

    print("\n  Record a development. Blank leaves a field unchanged.")
    print("  A ruling needs a source URL, or it is not recorded.\n")

    changes = []
    manner = ask("new official manner (suicide/undetermined/homicide/pending)")
    if manner and manner != case["official_manner"]:
        if manner not in ("suicide", "undetermined", "homicide", "pending"):
            print(f"  '{manner}' is not a recognised value. Skipping.")
        else:
            changes.append(("official_manner", case["official_manner"], manner))

    ruled_by = ask(f"ruled by (office; '{CLEAR}' to clear)")
    if ruled_by == CLEAR:
        if case["official_ruled_by"] is not None:
            changes.append(("official_ruled_by", case["official_ruled_by"], None))
    elif ruled_by and ruled_by != case["official_ruled_by"]:
        changes.append(("official_ruled_by", case["official_ruled_by"], ruled_by))

    ruling_date = ask("date of ruling (YYYY-MM-DD, from the reporting)")
    if ruling_date and case["date_found"]:
        try:
            d0 = dt.date.fromisoformat(case["date_found"])
            d1 = dt.date.fromisoformat(ruling_date)
            days = (d1 - d0).days
            print(f"    -> days_to_ruling = {days}")
            changes.append(("days_to_ruling", case["days_to_ruling"], str(days)))
        except ValueError:
            print("    couldn't parse dates; days_to_ruling left alone")

    contests = ask("family contests? (y/n)")
    if contests:
        v = "1" if contests.lower().startswith("y") else "0"
        if v != str(case["family_contests"]):
            changes.append(("family_contests", str(case["family_contests"]), v))

    orgs = ask("orgs contesting (replaces existing)")
    if orgs and orgs != case["org_contests"]:
        changes.append(("org_contests", case["org_contests"], orgs))

    # date_found is corrected often enough to need a sourced path here: the
    # common error is recording the article's publication date, which runs a
    # day or more late. Fixing it by hand in SQL would leave no audit row.
    found = ask_date("date body was found (YYYY-MM-DD)", case["date_found"])
    if found:
        changes.append(("date_found", case["date_found"], found))
        if case["days_to_ruling"] is not None:
            print("    NOTE: days_to_ruling was computed from the old date_found")
            print("    and is now wrong. Re-enter the ruling date to recompute it.")

    last_seen = ask_date("date last seen alive (YYYY-MM-DD)", case["date_last_seen"])
    if last_seen:
        changes.append(("date_last_seen", case["date_last_seen"], last_seen))

    age = ask("age at death")
    if age and age != str(case["age"] or ""):
        if not age.isdigit():
            print(f"    '{age}' is not a number. Leaving unchanged.")
        else:
            changes.append(("age", case["age"], age))

    autopsy = ask_bool("autopsy public?", case["autopsy_public"])
    if autopsy is not None:
        changes.append(("autopsy_public", str(case["autopsy_public"]), autopsy))

    indep = ask_bool("independent autopsy?", case["independent_autopsy"])
    if indep is not None:
        changes.append(("independent_autopsy", str(case["independent_autopsy"]), indep))

    # Most developments are not field changes. An arrest, an attorney who
    # never forwarded results, a hearing date: all real, none of them a
    # manner-of-death change. Without somewhere to put them the tool forces
    # a choice between losing the fact and asserting something stronger.
    # Appending is the default because notes accumulate context. But a note
    # that states something the sources do not support cannot be fixed by
    # adding a correction underneath it: the wrong sentence stays on the
    # public page. '!' replaces instead, and the old text is preserved in
    # case_updates, which is where the audit trail actually lives.
    note = ask("note ('!' prefix replaces, otherwise dated append)")
    if note == CLEAR:
        if case["notes"] is not None:
            changes.append(("notes", case["notes"], None))
    elif note and note.startswith("!"):
        changes.append(("notes", case["notes"], note[1:].strip()))
    elif note:
        changes.append(("notes", case["notes"], append_note(case["notes"], note)))

    ver = ask(f"verification ({'/'.join(VERIFICATION_VALUES)})")
    if ver and ver != case["verification"]:
        if ver not in VERIFICATION_VALUES:
            print(f"  '{ver}' is not a recognised value. Skipping.")
        elif ver == "verified" and not _confirm_verified(conn, case_id):
            print("  Not marking verified.")
        else:
            changes.append(("verification", case["verification"], ver))
            if ver == "verified":
                changes.append(("verified_by", case["verified_by"], who))
                changes.append(("verified_at", case["verified_at"],
                                dt.date.today().isoformat()))

    if not changes:
        if chosen_any:
            conn.commit()
            print("\n  No field changes. Attached sources committed.\n")
        else:
            print("\n  No changes.\n")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    for field, old, new in changes:
        val = int(new) if field in INT_FIELDS else new
        conn.execute(f"UPDATE cases SET {field} = ?, updated_at = ? WHERE id = ?",
                     (val, now, case_id))
        conn.execute("""
            INSERT INTO case_updates (case_id, field, old_value, new_value,
                                      source_url, changed_at, changed_by)
            VALUES (?,?,?,?,?,?,?)
        """, (case_id, field, str(old) if old is not None else None, new, src, now, who))

    conn.execute("""
        INSERT INTO case_sources (case_id, url, source_type, retrieved_at)
        VALUES (?,?, 'news', ?) ON CONFLICT (case_id, url) DO NOTHING
    """, (case_id, src, now))
    conn.commit()

    print(f"\n  Recorded {len(changes)} change(s) with source.")
    for f, o, n in changes:
        if f == "notes":
            if n is None:
                print("    notes: cleared")
            elif o and n.startswith(o.rstrip()):
                print(f"    notes: appended {_short(n, tail=True)}")
            else:
                print(f"    notes: REPLACED (old text kept in case_updates)")
                print(f"      was: {_short(o, 60)}")
                print(f"      now: {_short(n, 60)}")
        else:
            print(f"    {f}: {_short(o)} -> {_short(n)}")
    if not any(f == "verification" for f, _, _ in changes):
        print("\n  Verification reset is NOT automatic. If this case was verified,")
        print("  re-check it: the record has changed since someone last confirmed it.\n")
    else:
        print()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pending", action="store_true")
    p.add_argument("--update", type=int, metavar="ID")
    p.add_argument("--attach", type=int, metavar="ID",
                   help="link all matching candidates as sources; changes no fields")
    a = p.parse_args()

    conn = connect()
    if a.attach:
        attach_all(conn, a.attach)
    elif a.update:
        try:
            update_case(conn, a.update)
        except (KeyboardInterrupt, EOFError):
            conn.rollback()
            print("\n\n  Abandoned. Nothing written, including source attachments.\n")
            return 1
    elif a.pending:
        show_pending(conn)
    else:
        show_new_coverage(conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
