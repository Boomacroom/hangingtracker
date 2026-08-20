"""
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

# Seconds between queries. Spacing is the weaker lever: probing live, five
# queries 12s apart alternated 200/429, and moving to 30s apart did worse,
# not better. The budget is requests-per-window, so the fix that works is
# making fewer requests per run (see QUERIES_PER_RUN), not waiting longer
# between them.
THROTTLE_SECONDS = 30.0
MAX_RETRIES = 4

# Kept broad on purpose. Narrowing here loses cases that got one local
# story and nothing else, which are exactly the ones nobody is counting.
#
# These were revised against the triage record rather than by eye, because
# eyeballing got two of the four backwards. Precision measured over 160
# triaged candidates:
#
#   "independent autopsy" hanging ............... 90%  (45 of 50)
#   "hanging from a tree" (body OR found ...) .... 59%  (58 of 99)
#   "found hanging" (tree OR woods OR park) ...... 33%  (3 of 9)
#   "ruled a suicide" hanging (family OR ...) ..... 0%  (0 of 2)
#
QUERIES = [
    # Was (tree OR woods OR park). Location words were the reason an injured
    # bald eagle and a goat cruelty case scored: things get found hanging in
    # trees that are not people. Constraining on a person instead of a place
    # tested BROADER live (135 hits vs 91) while dropping that noise, and it
    # stops excluding deaths found somewhere that is not a tree or a park.
    '"found hanging" (man OR woman OR teen OR student OR body) sourcecountry:US',
    '"hanging from a tree" (body OR found OR death) sourcecountry:US',
    # Was '"ruled a suicide" hanging (family OR NAACP OR autopsy)', which
    # required three things to co-occur and returned 2 candidates, neither
    # relevant. Dropping the third clause found the Rebecca Zahau verdict,
    # a contested hanging death the narrow form missed entirely.
    '"ruled a suicide" (hanging OR hanged) sourcecountry:US',
    '"modern-day lynching" sourcecountry:US',
    '"independent autopsy" hanging sourcecountry:US',
]

# How many of QUERIES to run per invocation. See todays_queries().
QUERIES_PER_RUN = 2

# Social platforms plus fiction recaps: "10 Creepiest Episodes of Grimm"
# matches a hanging query on the plot summary. Only outlets that publish
# fiction summaries belong here. Tabloids stay out of this set even when
# they are unpleasant, because they do cover real deaths, and for a case
# that got one story nobody else ran, that story is the whole record.
NOISE_DOMAINS = {
    "pinterest.com", "reddit.com", "facebook.com", "x.com",
    "screenrant.com", "collider.com", "cbr.com", "looper.com",
    "gamerant.com", "comicbook.com",
}


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


def todays_queries(day: dt.date | None = None) -> list[str]:
    """
    A rotating slice of QUERIES, advancing each day.

    Running all five in one invocation is what triggers the 429s, and a
    partial collection caused by backoff is silently biased: it is always
    the queries at the END of the list that get dropped. Rotating makes the
    subsetting deliberate and even instead of accidental and lopsided.
    """
    day = day or dt.date.today()
    start = (day.toordinal() * QUERIES_PER_RUN) % len(QUERIES)
    return [QUERIES[(start + i) % len(QUERIES)] for i in range(QUERIES_PER_RUN)]


def _timespan_days(timespan: str) -> float | None:
    """Parse GDELT's '7d' / '48h' / '30min' forms into days. None if unknown."""
    s = timespan.strip().lower()
    for suffix, per_day in (("min", 1440.0), ("h", 24.0), ("d", 1.0), ("w", 1 / 7)):
        if s.endswith(suffix):
            try:
                return float(s[: -len(suffix)]) / per_day
            except ValueError:
                return None
    return None


def check_coverage(timespan: str) -> str | None:
    """
    Rotation is only free while the search window is wider than the time a
    query spends waiting its turn. If timespan drops below the cycle length,
    the days a query sits out become holes in the record that nothing
    downstream can detect: the table just has fewer rows than it should.
    """
    cycle = len(QUERIES) / QUERIES_PER_RUN
    days = _timespan_days(timespan)
    if days is not None and days < cycle:
        return (f"timespan {timespan} ({days:g}d) is shorter than the {cycle:g}d "
                f"query rotation. Each query would miss "
                f"{cycle - days:g}d of every cycle, invisibly. Use at least "
                f"{cycle:g}d; 7d gives margin.")
    return None


def collect(conn: sqlite3.Connection, timespan: str = "7d") -> int:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    inserted = 0

    warning = check_coverage(timespan)
    if warning:
        print(f"  WARNING: {warning}")

    todays = todays_queries()
    for i, q in enumerate(todays, start=1):
        print(f"  [{i}/{len(todays)}] {q[:58]}")
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

        if i < len(todays):
            time.sleep(THROTTLE_SECONDS)

    return inserted
