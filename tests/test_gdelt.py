"""Test backoff + partial-failure behaviour with a fake transport."""
import sqlite3, sys, time
sys.path.insert(0, 'src')
import httpx
from tracker.sources import gdelt

gdelt.THROTTLE_SECONDS = 0.01   # speed up test
# Rotation would otherwise run only QUERIES_PER_RUN of these, leaving the
# 404 and later handler branches below unexercised.
gdelt.QUERIES_PER_RUN = len(gdelt.QUERIES)
calls = {"n": 0}

def handler(request):
    calls["n"] += 1
    n = calls["n"]
    if n <= 2:                       # first query: 429 twice then succeed
        return httpx.Response(429)
    if n == 3:
        return httpx.Response(200, json={"articles":[
            {"url":"https://ex.com/a","title":"A","domain":"ex.com","seendate":"20260819T000000Z"},
            {"url":"https://reddit.com/b","title":"B","domain":"reddit.com"},
        ]})
    if n == 4:                       # second query: HTML with 200
        return httpx.Response(200, text="<html>error</html>")
    if n == 5:                       # third: 404, skip
        return httpx.Response(404)
    return httpx.Response(200, json={"articles":[
        {"url":f"https://ex.com/{n}","title":f"T{n}","domain":"ex.com"}]})

transport = httpx.MockTransport(handler)
_orig = httpx.get
httpx.get = lambda url, **kw: httpx.Client(transport=transport).get(url, **kw)

conn = sqlite3.connect(":memory:")
conn.executescript(open('schema.sql').read())
n = gdelt.collect(conn, timespan="7d")
httpx.get = _orig

print(f"\ninserted: {n}")
rows = list(conn.execute("select url, triage from candidates"))
print("rows:", rows)
assert not any("reddit" in r[0] for r in rows), "noise domain leaked"
assert all(r[1]=="new" for r in rows), "triage not defaulting to new"
print("\nPASS: backoff recovered, bad queries skipped, noise filtered, all triage=new")


# --- rotation ------------------------------------------------------------
# The rotation trades completeness-per-run for staying under GDELT's request
# budget. That trade is only sound if every query still comes up within a
# cycle; a query silently dropped from the rotation would look exactly like
# a quiet news week.
import datetime as dt

gdelt.QUERIES_PER_RUN = 2
cycle = -(-len(gdelt.QUERIES) // gdelt.QUERIES_PER_RUN)   # ceil
d0 = dt.date(2026, 1, 1)
ran = {q for k in range(cycle) for q in gdelt.todays_queries(d0 + dt.timedelta(days=k))}
missed = set(gdelt.QUERIES) - ran
assert not missed, f"queries never run within a {cycle}-day cycle: {missed}"

per_run = {len(gdelt.todays_queries(d0 + dt.timedelta(days=k))) for k in range(20)}
assert per_run == {gdelt.QUERIES_PER_RUN}, f"uneven run sizes: {per_run}"

# A window shorter than the rotation leaves gaps nothing downstream can see,
# which is the failure this guard exists to make loud.
assert gdelt.check_coverage("2d"), "2d timespan must warn against a 2.5d rotation"
assert gdelt.check_coverage("48h"), "hour-denominated timespans must parse"
assert gdelt.check_coverage("7d") is None, "7d covers the rotation and must not warn"
assert gdelt.check_coverage("garbage") is None, "unparseable timespan must not crash"

print(f"PASS: every query runs within {cycle} days, short timespans warn")
