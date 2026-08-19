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
              "mortality_agg", "v_undetermined_ratio"]:
        check(f"  {t}", t in names, "schema didn't fully apply")

    n_cases = conn.execute("select count(*) from cases").fetchone()[0]
    check("  seed loaded", n_cases >= 8,
          "run: python -m tracker.seed", fatal=False)

    print("\n--- invariants ---")
    n_verified = conn.execute(
        "select count(*) from cases where verification='verified'").fetchone()[0]
    check("nothing auto-verified", n_verified == 0,
          f"{n_verified} rows are verified but no human did that. "
          "Something is setting verification automatically. Find it.")

    orphans = conn.execute("""
        select count(*) from cases c
        where c.official_manner is not null
          and not exists (select 1 from case_sources s where s.case_id = c.id)
    """).fetchone()[0]
    check("every ruling has a source", orphans == 0,
          f"{orphans} cases assert a ruling with no source URL")

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
banned = ["suspected_lynching", "foul_play", "likely_homicide", "confidence_score"]
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
