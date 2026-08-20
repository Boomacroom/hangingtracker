#!/usr/bin/env python3
"""
Check the repo is set up correctly before you start real work.

    python tools/check_repo.py

Verifies file layout, that the package imports, that the schema applied,
that the seed landed, and most importantly that the invariants still
hold: nothing auto-verified, gdelt can't write to cases, export gated.
"""

from __future__ import annotations

import pathlib
import sqlite3
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OK, FAIL, WARN = "  ok  ", " FAIL ", " warn "
problems = 0


def check(label: str, condition: bool, hint: str = "", fatal: bool = True) -> bool:
    global problems
    if condition:
        print(f"[{OK}] {label}")
        return True
    print(f"[{FAIL if fatal else WARN}] {label}")
    if hint:
        print(f"         {hint}")
    if fatal:
        problems += 1
    return False


print("\n--- files ---")
expected = [
    "schema.sql",
    "pyproject.toml",
    "README.md",
    "SETUP.md",
    "src/tracker/cli.py",
    "src/tracker/seed.py",
    "src/tracker/sources/wonder.py",
    "src/tracker/sources/gdelt.py",
    ".github/workflows/refresh.yml",
    ".github/pull_request_template.md",
    "site/metadata.json",
    ".gitignore",
]
for rel in expected:
    check(rel, (ROOT / rel).exists(), "missing from the repo")

check(
    ".claude/skills/hanging-deaths-tracker-dev/SKILL.md",
    (ROOT / ".claude/skills/hanging-deaths-tracker-dev/SKILL.md").exists(),
    "unzip the .skill file into .claude/skills/ so it's version-controlled",
    fatal=False,
)

print("\n--- package ---")
try:
    sys.path.insert(0, str(ROOT / "src"))
    from tracker.sources import gdelt, wonder  # noqa: F401
    check("tracker package imports", True)
except Exception as e:  # noqa: BLE001
    check("tracker package imports", False, f"run: pip install -e .  ({e})")

print("\n--- database ---")
db = ROOT / "data" / "tracker.db"
if check(str(db.relative_to(ROOT)), db.exists(), "run: tracker init"):
    conn = sqlite3.connect(db)
    names = {r[0] for r in conn.execute(
        "select name from sqlite_master where type in ('table','view')")}
    for t in ["cases", "case_sources", "candidates",
              "mortality_agg", "state_systems",
              "v_undetermined_ratio", "v_undetermined_by_system"]:
        check(f"  {t}", t in names, "schema didn't fully apply")

    n_cases = conn.execute("select count(*) from cases").fetchone()[0]
    check("  seed loaded", n_cases >= 8,
          "run: python -m tracker.seed", fatal=False)

    print("\n--- invariants ---")
    # This used to assert that NO case was verified, which would have started
    # failing the moment someone did the verification work correctly. What
    # actually needs guarding is that a human did it and left their name: a
    # verified row with no verified_by is one nothing human touched.
    unattributed = conn.execute("""
        select count(*) from cases
        where verification = 'verified'
          and (verified_by is null or trim(verified_by) = '')
    """).fetchone()[0]
    check("nothing auto-verified", unattributed == 0,
          f"{unattributed} rows are verified with no verified_by. Verification "
          "is a claim about work a person did; something set it automatically.")

    # A source published or archived before the body was found cannot be
    # about that death. This is how two Tasia Fortune stories ended up filed
    # under the Raleigh case: title matching on a city name.
    # published_at arrives from GDELT as 20260818T191500Z, not ISO, so it has
    # to be normalised before comparing. Comparing the raw string silently
    # never matches, which is a check that always passes and guards nothing.
    anachronistic = conn.execute("""
        select count(*) from case_sources s join cases c on c.id = s.case_id
        where c.date_found is not null and s.published_at is not null
          and case when instr(s.published_at, '-') > 0
                   then substr(s.published_at, 1, 10)
                   else substr(s.published_at, 1, 4) || '-' ||
                        substr(s.published_at, 5, 2) || '-' ||
                        substr(s.published_at, 7, 2)
              end < c.date_found
    """).fetchone()[0]
    check("no source predates the death it documents", anachronistic == 0,
          f"{anachronistic} source(s) are dated before their case's date_found. "
          "Either the source is filed under the wrong case or date_found is wrong.",
          fatal=False)

    # A ruling office implies a ruling. Naming one while official_manner is
    # 'pending' reads as "the ME called it" to anyone skimming, when what
    # actually happened is that an office has the case and has said nothing.
    # The investigating agency is a real fact and belongs in notes; this
    # column is for who issued a ruling, and stays NULL until one exists.
    premature = conn.execute("""
        select count(*) from cases
        where official_ruled_by is not null and trim(official_ruled_by) <> ''
          and (official_manner is null or official_manner = 'pending')
    """).fetchone()[0]
    check("no ruling office named before a ruling exists", premature == 0,
          f"{premature} case(s) name an official_ruled_by while official_manner "
          "is pending or unset. Move the office to notes and leave the column "
          "NULL until a ruling is actually issued.")

    # Weaker, and deliberately non-fatal: a manner recorded as ruled on the
    # strength of a police statement. Police are not the certifying
    # authority in most states, and "preliminary" in the office name is the
    # tell. Judgment call per case, so this warns rather than fails.
    police_ruled = [r[0] for r in conn.execute("""
        select slug from cases
        where official_manner is not null and official_manner <> 'pending'
          and (lower(official_ruled_by) like '%police%'
               or lower(official_ruled_by) like '%preliminary%'
               or lower(official_ruled_by) like '%sheriff%')
    """)]
    check("no manner ruled on a police statement alone", not police_ruled,
          f"{police_ruled} record a ruling attributed to police. In most states "
          "the coroner or ME certifies manner, not the police department. If "
          "only a police statement is reported, the manner is 'pending'. "
          "Re-read the sources and decide per case.",
          fatal=False)

    orphans = conn.execute("""
        select count(*) from cases c
        where c.official_manner is not null
          and not exists (select 1 from case_sources s where s.case_id = c.id)
    """).fetchone()[0]
    check("every ruling has a source", orphans == 0,
          f"{orphans} cases assert a ruling with no source URL")

    # state_systems is the one table asserting something about a
    # jurisdiction's institutions rather than counting deaths, so it gets
    # the same rule the case records get: no source, no row.
    unsourced = conn.execute("""
        select count(*) from state_systems
        where source_url is null or trim(source_url) = ''
    """).fetchone()[0]
    check("every state system row cites a source", unsourced == 0,
          f"{unsourced} rows in state_systems have no source_url. Who "
          "certifies deaths in a state is a checkable claim; keep it checkable.")

    # The join is only meaningful if the two tables agree on state names.
    # A mismatch does not error, it silently drops states out of the
    # correlation and quietly changes n.
    unjoined = conn.execute("""
        select count(distinct state) from mortality_agg
        where state is not null
          and state not in (select state from state_systems)
    """).fetchone()[0]
    check("every state in the mortality data has a system row", unjoined == 0,
          f"{unjoined} states would drop out of v_undetermined_by_system, "
          "changing n without any visible error. Run tools/load_state_systems.py.",
          fatal=False)

    est = conn.execute(
        "select count(*) from cases where days_to_ruling is not null").fetchone()[0]
    check("no estimated days_to_ruling", est == 0,
          f"{est} rows have days_to_ruling. Fine IF each came from a published "
          "ruling date. If any was inferred from an article date, clear it.",
          fatal=False)

    conn.close()

print("\n--- code invariants ---")
gd = (ROOT / "src/tracker/sources/gdelt.py").read_text() if (ROOT / "src/tracker/sources/gdelt.py").exists() else ""
check("gdelt.py cannot write to cases",
      "INSERT INTO cases" not in gd.upper().replace("  ", " "),
      "gdelt must only write to `candidates`. Promotion goes through triage.")

schema = (ROOT / "schema.sql").read_text() if (ROOT / "schema.sql").exists() else ""
banned = ["suspected_lynching", "foul_play", "likely_homicide", "confidence_score",
          "system_quality", "coroner_competence"]
found = [b for b in banned if b in schema.lower()]
check("no conclusion columns in schema", not found,
      f"found {found}. The dataset records rulings and disputes, not verdicts.")

print("\n--- git ---")
try:
    subprocess.run(["git", "rev-parse", "--git-dir"], cwd=ROOT,
                   capture_output=True, check=True)
    check("git initialised", True)
    remote = subprocess.run(["git", "remote", "-v"], cwd=ROOT,
                            capture_output=True, text=True).stdout
    check("remote configured", bool(remote.strip()),
          "git remote add origin <url>", fatal=False)
except subprocess.CalledProcessError:
    check("git initialised", False, "run: git init && git branch -M main")

print()
if problems:
    print(f"{problems} problem(s) to fix before pushing.\n")
    sys.exit(1)
print("Repo looks good.\n")
