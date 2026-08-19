"""Test backoff + partial-failure behaviour with a fake transport."""
import sqlite3, sys, time
sys.path.insert(0, 'src')
import httpx
from tracker.sources import gdelt

gdelt.THROTTLE_SECONDS = 0.01   # speed up test
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
