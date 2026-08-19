-- Design rule for this whole schema:
-- nothing derived automatically is ever stored in the same column as
-- something a human verified. If you blur that line the dataset becomes
-- uncitable, and uncitable is the same as useless for this subject.

PRAGMA journal_mode = WAL;

-- ---------------------------------------------------------------
-- Layer 1: statistical baseline (CDC WONDER)
-- Aggregate counts only. No individuals. This is what supports
-- claims about classification behavior across jurisdictions.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mortality_agg (
    id              INTEGER PRIMARY KEY,
    dataset         TEXT NOT NULL,      -- WONDER file id, e.g. 'D77'
    year            INTEGER NOT NULL,
    state           TEXT,               -- NULL = national
    state_fips      TEXT,
    race            TEXT,               -- as WONDER labels it, unmodified
    sex             TEXT,
    age_group       TEXT,
    icd10_code      TEXT NOT NULL,      -- X70, Y20, etc.
    icd10_label     TEXT,
    deaths          INTEGER,
    population      INTEGER,
    crude_rate      REAL,
    suppressed      INTEGER DEFAULT 0,  -- WONDER hides counts under 10
    unreliable      INTEGER DEFAULT 0,  -- WONDER flags rates under 20 deaths
    fetched_at      TEXT NOT NULL,
    UNIQUE (dataset, year, state, race, sex, age_group, icd10_code)
);

CREATE INDEX IF NOT EXISTS idx_mortality_lookup
    ON mortality_agg (year, state, icd10_code, race);

-- ---------------------------------------------------------------
-- Layer 2: individual cases
-- Every field here is nullable on purpose. Partial records are
-- normal and better than invented completeness.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cases (
    id                  INTEGER PRIMARY KEY,
    slug                TEXT UNIQUE NOT NULL,

    decedent_name       TEXT,
    age                 INTEGER,
    date_found          TEXT,           -- ISO8601
    date_last_seen      TEXT,

    city                TEXT,
    county              TEXT,
    state               TEXT,
    location_type       TEXT,           -- 'wooded area', 'campus', 'residential'

    -- What officials said. Verbatim classification, plus who said it.
    official_manner     TEXT,           -- 'suicide' | 'undetermined' | 'homicide' | 'pending' | NULL
    official_ruled_by   TEXT,           -- 'Cobb County PD', 'MS State ME'
    days_to_ruling      INTEGER,        -- the metric that keeps coming up
    autopsy_public      INTEGER DEFAULT 0,
    independent_autopsy INTEGER DEFAULT 0,

    -- Whether the ruling is contested, and by whom. NOT a verdict.
    family_contests     INTEGER DEFAULT 0,
    org_contests        TEXT,           -- 'NAACP Milwaukee; BLM Georgia'

    -- Provenance and confidence. Never auto-set to 'verified'.
    verification        TEXT NOT NULL DEFAULT 'unverified'
                        CHECK (verification IN ('unverified','review','verified','rejected')),
    verified_by         TEXT,
    verified_at         TEXT,
    notes               TEXT,

    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cases_state_date ON cases (state, date_found);
CREATE INDEX IF NOT EXISTS idx_cases_verification ON cases (verification);

-- Every assertion traces to a URL. No exceptions.
CREATE TABLE IF NOT EXISTS case_sources (
    id           INTEGER PRIMARY KEY,
    case_id      INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    url          TEXT NOT NULL,
    outlet       TEXT,
    title        TEXT,
    published_at TEXT,
    source_type  TEXT,   -- 'news' | 'court' | 'me_report' | 'org_report' | 'foia'
    archived_url TEXT,   -- web.archive.org snapshot; link rot is real here
    retrieved_at TEXT NOT NULL,
    UNIQUE (case_id, url)
);

-- ---------------------------------------------------------------
-- Layer 3: raw candidate hits from automated collection.
-- Deliberately NOT joined to cases. A human promotes rows across.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS candidates (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,   -- 'gdelt'
    url           TEXT UNIQUE NOT NULL,
    title         TEXT,
    seendate      TEXT,
    domain        TEXT,
    snippet       TEXT,
    matched_terms TEXT,
    triage        TEXT NOT NULL DEFAULT 'new'
                  CHECK (triage IN ('new','relevant','irrelevant','duplicate')),
    promoted_case INTEGER REFERENCES cases(id),
    fetched_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_candidates_triage ON candidates (triage, seendate);

-- ---------------------------------------------------------------
-- Derived view: the classification-behavior signal.
-- A jurisdiction that never uses 'undetermined' is the finding.
-- ---------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_undetermined_ratio AS
SELECT
    year,
    state,
    race,
    SUM(CASE WHEN icd10_code LIKE 'X70%' AND suppressed = 0 THEN deaths END) AS suicide_hanging,
    SUM(CASE WHEN icd10_code LIKE 'Y20%' AND suppressed = 0 THEN deaths END) AS undetermined_hanging,
    SUM(suppressed) AS suppressed_cells,
    -- NULL, not 0, when either side is missing or suppressed. A
    -- suppressed cell means "fewer than 10", never "none".
    CASE WHEN SUM(suppressed) > 0 THEN NULL ELSE
        CAST(SUM(CASE WHEN icd10_code LIKE 'Y20%' THEN deaths END) AS REAL)
        / NULLIF(SUM(CASE WHEN icd10_code LIKE 'X70%' THEN deaths END), 0)
    END AS undetermined_ratio
FROM mortality_agg
GROUP BY year, state, race;
