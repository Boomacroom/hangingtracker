#!/usr/bin/env python3
"""
Writes the corrected gdelt.py into place.

Run this from the repo root (Desktop\\files):

    python fix_gdelt.py

It overwrites src/tracker/sources/gdelt.py with the throttled version and
verifies the result, so there is no download-name collision to get wrong.
"""

import pathlib
import sys

TARGET = pathlib.Path("src/tracker/sources/gdelt.py")

CONTENT = r'''"""
GDELT DOC 2.0 candidate collector.

Free, no key, JSON out, covers most of the open web news index. It is a
firehose with terrible precision for a query like this, which is fine.
The job here is recall. Everything lands in `candidates` with triage
status 'new' and a human decides what is real.

Deliberate design choice: this module cannot write to `cases`. The only
path from a scraped headline to a case record goes through a person.

Rate limiting: GDELT does not publish a limit but starts returning 429
somewhere around one request every few seconds. We throttle between
queries and back off on 429 rather than hammering it. A partial
collection is fine, since this runs daily and misses get picked up
tomorrow.
"""

from __future__ import annotations

import datetime as dt
import random
import sqlite3
import time
from urllib.parse import urlparse

import httpx

GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"

# Seconds between queries. Raise it if you still see 429s; there is no
# prize for finishing the pull quickly.
THROTTLE_SECONDS = 6.0
MAX_RETRIES = 4

# Kept broad on purpose. Narrowing here loses cases that got one local
# story and nothing else, which are exactly the ones nobody is counting.
QUERIES = [
    '"found hanging" (tree OR woods OR park) sourcecountry:US',
    '"hanging from a tree" (body OR found OR death) sourcecountry:US',
    '"ruled a suicide" hanging (family OR NAACP OR autopsy) sourcecountry:US',
    '"modern-day lynching" sourcecountry:US',
    '"independent autopsy" hanging sourcecountry:US',
]

NOISE_DOMAINS = {"pinterest.com", "reddit.com", "facebook.com", "x.com"}


def _is_noise(domain: str) -> bool:
    """
    Match on a dot boundary, never a bare suffix. A plain endswith() means
    'x.com' silently swallows vox.com and fox.com, which are real outlets
    for this beat. Losing candidates invisibly is the worst failure mode
    this collector has, since nothing downstream can tell you it happened.
    """
    return any(domain == n or domain.endswith("." + n) for n in NOISE_DOMAINS)


def search(query: str, timespan: str = "7d", maxrecords: int = 250) -> list[dict]:
    """
    One query, with backoff on 429/5xx. Returns [] rather than raising if
    the query cannot be satisfied, because one bad query should not abort
    a whole run.
    """
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "timespan": timespan,
        "maxrecords": maxrecords,
        "sort": "datedesc",
    }
    headers = {"User-Agent": "hanging-deaths-tracker (research; contact in repo)"}

    for attempt in range(MAX_RETRIES):
        try:
            resp = httpx.get(GDELT_DOC, params=params, timeout=60.0, headers=headers)
        except httpx.RequestError as e:
            wait = 2 ** attempt + random.random()
            print(f"      network error ({e.__class__.__name__}), retry in {wait:.0f}s")
            time.sleep(wait)
            continue

        if resp.status_code == 429 or resp.status_code >= 500:
            wait = (2 ** attempt) * THROTTLE_SECONDS + random.random() * 2
            print(f"      HTTP {resp.status_code}, backing off {wait:.0f}s "
                  f"(attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(wait)
            continue

        if resp.status_code != 200:
            print(f"      HTTP {resp.status_code}, skipping this query")
            return []

        if not resp.text.strip():
            return []
        try:
            return resp.json().get("articles", [])
        except ValueError:
            # GDELT sometimes returns an HTML error page with a 200.
            print("      non-JSON response, skipping this query")
            return []

    print("      gave up after retries")
    return []


def collect(conn: sqlite3.Connection, timespan: str = "7d") -> int:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    inserted = 0

    for i, q in enumerate(QUERIES, start=1):
        print(f"  [{i}/{len(QUERIES)}] {q[:58]}")
        articles = search(q, timespan=timespan)
        got = 0

        for art in articles:
            url = art.get("url")
            if not url:
                continue
            domain = (art.get("domain") or urlparse(url).netloc).lower()
            if _is_noise(domain):
                continue

            cur = conn.execute(
                """
                INSERT INTO candidates
                    (source, url, title, seendate, domain, snippet,
                     matched_terms, triage, fetched_at)
                VALUES ('gdelt', ?, ?, ?, ?, NULL, ?, 'new', ?)
                ON CONFLICT (url) DO NOTHING
                """,
                (url, art.get("title"), art.get("seendate"), domain, q, now),
            )
            if cur.rowcount > 0:
                got += 1

        # Commit per query so a later failure never loses earlier work.
        conn.commit()
        inserted += got
        print(f"      {len(articles)} articles, {got} new")

        if i < len(QUERIES):
            time.sleep(THROTTLE_SECONDS)

    return inserted
'''


def main() -> int:
    if not pathlib.Path("schema.sql").exists():
        print("Run this from the repo root (the folder containing schema.sql).")
        return 1

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    if TARGET.exists():
        backup = TARGET.with_suffix(".py.bak")
        backup.write_text(TARGET.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"backed up existing file -> {backup}")

    TARGET.write_text(CONTENT, encoding="utf-8")

    text = TARGET.read_text(encoding="utf-8")
    checks = [
        ("is the collector, not the test", "GDELT DOC 2.0 candidate collector" in text),
        ("has throttling", "THROTTLE_SECONDS" in text),
        ("has the domain fix", "_is_noise" in text),
        ("has collect()", "def collect(" in text),
        ("cannot write to cases", "INSERT INTO cases" not in text.upper()),
    ]
    print(f"\nwrote {TARGET} ({len(text)} bytes)")
    ok = True
    for label, passed in checks:
        print(f"  [{'ok' if passed else 'FAIL'}] {label}")
        ok &= passed

    if not ok:
        return 1
    print("\nNow run:  python -m tracker.cli news --timespan 30d")
    return 0


if __name__ == "__main__":
    sys.exit(main())
