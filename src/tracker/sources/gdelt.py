"""
GDELT DOC 2.0 candidate collector.

Free, no key, JSON out, covers most of the open web news index. It is a
firehose with terrible precision for a query like this, which is fine.
The job here is recall. Everything lands in `candidates` with triage
status 'new' and a human decides what is real.

Deliberate design choice: this module cannot write to `cases`. The only
path from a scraped headline to a case record goes through a person.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from urllib.parse import urlparse

import httpx

GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"

# Kept broad on purpose. Narrowing here loses cases that got one local
# story and nothing else, which are exactly the ones nobody is counting.
QUERIES = [
    '"found hanging" (tree OR woods OR park) sourcecountry:US',
    '"hanging from a tree" (body OR found OR death) sourcecountry:US',
    '"ruled a suicide" hanging (family OR NAACP OR autopsy) sourcecountry:US',
    '"modern-day lynching" sourcecountry:US',
    '"independent autopsy" hanging sourcecountry:US',
]

# Reject list for obvious noise. Extend as you triage.
NOISE_DOMAINS = {"pinterest.com", "reddit.com", "facebook.com", "x.com"}


def search(query: str, timespan: str = "7d", maxrecords: int = 250) -> list[dict]:
    resp = httpx.get(
        GDELT_DOC,
        params={
            "query": query,
            "mode": "artlist",
            "format": "json",
            "timespan": timespan,
            "maxrecords": maxrecords,
            "sort": "datedesc",
        },
        timeout=60.0,
        headers={"User-Agent": "hanging-deaths-tracker (research; contact in repo)"},
    )
    resp.raise_for_status()
    if not resp.text.strip():
        return []
    try:
        return resp.json().get("articles", [])
    except ValueError:
        # GDELT sometimes returns an HTML error page with a 200.
        return []


def collect(conn: sqlite3.Connection, timespan: str = "7d") -> int:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    inserted = 0

    for q in QUERIES:
        for art in search(q, timespan=timespan):
            url = art.get("url")
            if not url:
                continue
            domain = (art.get("domain") or urlparse(url).netloc).lower()
            if any(domain.endswith(n) for n in NOISE_DOMAINS):
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
            inserted += cur.rowcount if cur.rowcount > 0 else 0

    conn.commit()
    return inserted
