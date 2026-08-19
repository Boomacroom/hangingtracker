# Setup

## 1. Local

```bash
cd hanging-deaths-tracker
pip install -e .
tracker init                 # apply schema.sql -> data/tracker.db
python -m tracker.seed       # 8 sourced cases, all unverified
python tools/check_repo.py   # confirms layout + invariants
```

Expect `Repo looks good.` with one warning about the git remote.

## 2. Git

```bash
git init && git branch -M main
git add -A
git commit -m "init: schema, collectors, seed, skill"
```

Create a **public** repo on GitHub. Public is what makes Actions minutes
unlimited, which is the entire $0 cost model. Then:

```bash
git remote add origin git@github.com:<you>/hanging-deaths-tracker.git
git push -u origin main
```

`data/tracker.db` **is committed on purpose.** It is the dataset, and git
history is the audit trail that makes the data citable.

## 3. Harden, before real data lands

Settings > Branches > add rule for `main`:
- Require a pull request before merging, 1 approval
- Require signed commits
- Block force pushes and deletions
- Include administrators

Settings > Actions > General:
- Workflow permissions: **Read and write**
- "Allow Actions to create and approve pull requests": **off**

## 4. First runs

```bash
tracker news --timespan 30d   # should just work
tracker wonder --years 2019 2020   # the untested one
```

`tracker wonder` has never been exercised against the live API. If it
returns nothing or an HTML error page with HTTP 200, the parameter codes
are wrong for that dataset file. See
`.claude/skills/hanging-deaths-tracker-dev/references/wonder-api.md`.

## 5. Triage

```bash
tracker triage
```

The only step that cannot be automated, and the reason the dataset is
worth anything.

## 6. Publish

Cloudflare Pages > connect repo > build command none, output dir `site/`.
Add a step copying `data/tracker.db` into `site/`.

Then, with no server anywhere:

```
https://lite.datasette.io/?url=https://<pages-domain>/tracker.db
```

## What not to commit

`.gitignore` already covers it: `*.db-wal`, `*.db-shm`, `__pycache__/`,
`*.egg-info/`, `.venv/`. Never commit a WAL file; it makes the database
look changed when it hasn't.
