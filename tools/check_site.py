#!/usr/bin/env python3
"""
Render site/index.html against the real exported JSON and fail on errors.

    python tools/check_site.py

This exists because of a bug that shipped: the suppression callout was
rewritten and lost its `<span id="undercount">`, while the script still
did `$('#undercount').textContent = ...`. In a browser that is a
TypeError on null, so render() aborted after drawing the first figure and
every table below it stayed empty -- and the catch block reported it as
"Could not load data/tracker.json", sending anyone reading it after a
missing file that was not missing.

It survived a hand-rolled Node check because that harness returned a
fresh stub object for *any* selector, so a missing element looked exactly
like a present one. A test that cannot fail the way production fails is
not a test. This one parses the ids actually present in the HTML and
returns null for everything else, which is what a browser does.

Requires node on PATH. Skips with a warning if it is absent, since the
repo's only hard dependency is httpx.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
HTML = ROOT / "site" / "index.html"
DATA = ROOT / "site" / "data" / "tracker.json"

HARNESS = r"""
const fs = require('fs');
const ids = new Set(JSON.parse(process.argv[2]));
const data = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const js = fs.readFileSync(process.argv[4], 'utf8');

const made = new Map();
const el = () => ({
  innerHTML: '', textContent: '', hidden: true, href: '', style: {},
});
// The whole point: unknown selectors return null, exactly as
// document.querySelector does, so writing to one throws like it would
// in a browser.
global.document = {
  querySelector: (sel) => {
    const id = sel.startsWith('#') ? sel.slice(1) : null;
    if (id === null || !ids.has(id)) return null;
    if (!made.has(id)) made.set(id, el());
    return made.get(id);
  },
};
global.location = { origin: 'https://example.test', pathname: '/index.html' };

// Drop the fetch call; we invoke render() directly with real data.
eval(js.replace(/let fetched = false;[\s\S]*?\}\);\s*$/m, '') + '\nrender(data);');

const out = {};
for (const [id, node] of made) {
  out[id] = (node.innerHTML || '').length + (node.textContent || '').length;
}
console.log(JSON.stringify(out));
"""


def main() -> int:
    if shutil.which("node") is None:
        print("node not on PATH; skipping site render check")
        return 0
    for p in (HTML, DATA):
        if not p.exists():
            print(f"missing {p}. Run tools/export_site.py first.")
            return 1

    html = HTML.read_text(encoding="utf-8")
    ids = sorted(set(re.findall(r'id="([A-Za-z0-9_-]+)"', html)))
    js = html[html.rindex("<script>") + len("<script>"):html.rindex("</script>")]

    referenced = sorted(set(re.findall(r"\$\('#([A-Za-z0-9_-]+)'\)", js)))
    missing = [r for r in referenced if r not in ids]
    if missing:
        print(f"FAIL: script writes to elements that do not exist: {missing}")
        print("      querySelector returns null and render() aborts partway,")
        print("      leaving every section below it blank.")
        return 1
    print(f"ok  : all {len(referenced)} referenced elements exist")

    with tempfile.TemporaryDirectory() as td:
        h = pathlib.Path(td) / "harness.js"
        j = pathlib.Path(td) / "page.js"
        h.write_text(HARNESS, encoding="utf-8")
        j.write_text(js, encoding="utf-8")
        r = subprocess.run(
            ["node", str(h), json.dumps(ids), str(DATA), str(j)],
            capture_output=True, text=True)

    if r.returncode != 0:
        print("FAIL: render() threw")
        print(r.stderr.strip()[:1500])
        return 1

    filled = json.loads(r.stdout)
    print(f"ok  : render() completed, wrote to {len(filled)} elements")

    # A section that renders zero characters is a section nobody sees.
    empty = [k for k, v in filled.items() if v == 0]
    core = [k for k in ("sgrid", "nattable", "statetable", "systable", "cases")
            if filled.get(k, 0) == 0]
    if core:
        print(f"FAIL: core sections rendered empty: {core}")
        return 1
    print("ok  : every core section rendered content")
    if empty:
        print(f"note: empty but non-core: {empty}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
