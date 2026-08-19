"""
Bootstrap seed of publicly reported cases.

Everything here enters as `unverified` with a real source URL. This is a
starting point for triage, not a finding. Several fields are deliberately
NULL because reporting did not establish them, and guessing would defeat
the purpose of the dataset.

Run once:  python -m tracker.seed
"""

from __future__ import annotations

import datetime as dt

from tracker.cli import connect

NOW = dt.datetime.now(dt.timezone.utc).isoformat()

# (slug, name, age, date_found, city, county, state, location_type,
#  official_manner, ruled_by, days_to_ruling, indep_autopsy,
#  family_contests, org_contests, notes)
CASES = [
    (
        "kyle-bassinga-ga-2026", "Kyle Bassinga", 21, "2026-02-18",
        "Marietta", "Cobb", "GA", "wooded area",
        "suicide", "Cobb County Police Department", None, 0,
        0, None,
        "Reported missing Feb 14; found Feb 18 at Fair Oaks Park. Police cited "
        "surveillance video showing him entering the area alone, plus witness "
        "and autopsy findings. Family stated through police that they trust the "
        "process. Exact ruling date not published, so days_to_ruling left NULL.",
    ),
    (
        "isaac-carlos-aguirre-dc-2026", "Isaac Carlos Aguirre", 19, "2026-04-01",
        "Washington", None, "DC", "tree near police station",
        "pending", "Metropolitan Police Department", None, 0,
        1, None,
        "Found near MPD Fourth District station. MPD treated it as a suicide "
        "investigation and said no foul play suspected; a formal ME ruling was "
        "not reported, so official_manner is 'pending' rather than 'suicide'. "
        "Reporting noted a three-day delay before any public statement. Exact "
        "date_found not established in available reporting; April 2026 only.",
    ),
    (
        "tasia-fortune-ms-2026", "Tasia Fortune", 29, "2026-08-03",
        "Jackson", "Hinds", "MS", "behind vacant home",
        "pending", "Mississippi State Medical Examiner", None, 0,
        1, None,
        "Found Aug 3 behind a vacant home. No cause or manner released as of "
        "mid-August 2026. A person of interest was reported arrested. Mother "
        "Christy Spivey publicly disputed suicide. This is the open case.",
    ),
    (
        "juliana-nzita-nc-2026", "Juliana Nzita", 16, None,
        None, None, "NC", None,
        None, None, None, 0,
        0, None,
        "Named in aggregate 2026 coverage. Date, location, and ruling not yet "
        "sourced to a primary report. Needs verification before any use.",
    ),
    (
        "tonea-nicole-miller-fl-2026", "Tonea Nicole Miller", None, None,
        None, None, "FL", None,
        None, None, None, 0,
        0, None,
        "Named in aggregate 2026 coverage. Details not yet sourced to a primary "
        "report. Needs verification before any use.",
    ),
    # Pre-2026 context cases. Useful for days_to_ruling comparison.
    (
        "tory-medley-wi-2025", "Tory Medley", 39, "2025-11-13",
        "Brookfield", "Waukesha", "WI", "golf course",
        "suicide", "local police (preliminary)", None, 1,
        1, "NAACP Milwaukee; NAACP Waukesha",
        "Police said preliminary investigation indicated suicide and later cited "
        "a mental health crisis, saying reviewed video did not substantiate foul "
        "play. Family and NAACP chapters questioned how he reached a suburban "
        "course without a car and commissioned an independent autopsy. Phone and "
        "ID were not found.",
    ),
    (
        "trey-reed-ms-2025", "Demartravion 'Trey' Reed", 25, "2025-09-15",
        "Cleveland", "Bolivar", "MS", "campus",
        "suicide", "Bolivar County Coroner", None, 0,
        1, None,
        "Delta State University student. Coroner ruled suicide. Family and local "
        "advocates dispute. This case drove much of the subsequent national "
        "coverage and JULIAN's report timing. date_found approximate.",
    ),
    (
        "javion-magee-nc-2024", "Javion Magee", 21, "2024-09-12",
        "Henderson", "Vance", "NC", "base of tree",
        "suicide", "North Carolina Medical Examiner", None, 0,
        1, None,
        "Found with a rope around his neck. Family attorneys called an early "
        "suicide conclusion premature; a later state ME report classified it a "
        "suicide. date_found approximate.",
    ),
]

SOURCES = {
    "kyle-bassinga-ga-2026": [
        ("https://atlantablackstar.com/2026/08/13/at-least-six-black-people-found-hanging/",
         "Atlanta Black Star", "news"),
        ("https://thegrio.com/2026/08/10/black-people-are-being-found-hanging-from-trees-why-are-officials-so-quick-to-call-it-suicide/",
         "TheGrio", "news"),
    ],
    "isaac-carlos-aguirre-dc-2026": [
        ("https://davisvanguard.org/2026/08/modern-day-lynching-report/",
         "Davis Vanguard", "news"),
    ],
    "tasia-fortune-ms-2026": [
        ("https://www.cnn.com/2026/08/11/us/video/tasia-fortune-mississippi-hanging-tree-vrtc",
         "CNN", "news"),
    ],
    "juliana-nzita-nc-2026": [
        ("https://emeraldbook.org/news/aug-1526/", "Emerald Book", "news"),
    ],
    "tonea-nicole-miller-fl-2026": [
        ("https://emeraldbook.org/news/aug-1526/", "Emerald Book", "news"),
    ],
    "tory-medley-wi-2025": [
        ("https://thegrio.com/2026/08/10/black-people-are-being-found-hanging-from-trees-why-are-officials-so-quick-to-call-it-suicide/",
         "TheGrio", "news"),
    ],
    "trey-reed-ms-2025": [
        ("https://www.wbez.org/in-the-loop-with-sasha-ann-simons/2026/03/04/a-crimson-record-a-new-report-finds-modern-day-lynchings-on-the-rise",
         "WBEZ", "news"),
        ("https://www.julianfreedom.org/press-releases/new-crimson-record-chronicles-over-70-recent-lynchings-in-deep-south-reveals-new-evidence-in-cases",
         "JULIAN", "org_report"),
    ],
    "javion-magee-nc-2024": [
        ("https://balleralert.com/black-people-found-hanging-2026-suicide-rulings/",
         "Baller Alert", "news"),
    ],
}


def main():
    conn = connect()
    for row in CASES:
        conn.execute(
            """
            INSERT INTO cases
                (slug, decedent_name, age, date_found, city, county, state,
                 location_type, official_manner, official_ruled_by,
                 days_to_ruling, independent_autopsy, family_contests,
                 org_contests, notes, verification, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'unverified', ?, ?)
            ON CONFLICT (slug) DO NOTHING
            """,
            row + (NOW, NOW),
        )

    for slug, srcs in SOURCES.items():
        cid = conn.execute("SELECT id FROM cases WHERE slug = ?", (slug,)).fetchone()
        if not cid:
            continue
        for url, outlet, stype in srcs:
            conn.execute(
                """
                INSERT INTO case_sources
                    (case_id, url, outlet, source_type, retrieved_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT (case_id, url) DO NOTHING
                """,
                (cid[0], url, outlet, stype, NOW),
            )

    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    s = conn.execute("SELECT COUNT(*) FROM case_sources").fetchone()[0]
    print(f"{n} cases, {s} sources, all unverified")


if __name__ == "__main__":
    main()
