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
    year            INTEGER,            -- NULL for pooled multi-year rows
    period          TEXT,               -- e.g. '2018-2024' when pooled
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
    fetched_at      TEXT NOT NULL
);

-- COALESCE'd so upserts still dedupe when year/state/race are NULL.
CREATE UNIQUE INDEX IF NOT EXISTS idx_mortality_key ON mortality_agg (
    dataset, COALESCE(year, -1), COALESCE(period, ''), COALESCE(state, ''),
    COALESCE(race, ''), COALESCE(sex, ''), COALESCE(age_group, ''), icd10_code
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
-- Views are derived, so they are dropped and rebuilt on every schema
-- apply rather than guarded with IF NOT EXISTS. A view definition that
-- silently stays at the old version in an existing database is how a
-- fixed query goes on returning the broken answer.
DROP VIEW IF EXISTS v_undetermined_ratio;
CREATE VIEW v_undetermined_ratio AS
SELECT
    year,
    period,
    state,
    race,
    sex,
    age_group,
    SUM(CASE WHEN icd10_code LIKE 'X70%' AND suppressed = 0 THEN deaths END) AS suicide_hanging,
    SUM(CASE WHEN icd10_code LIKE 'Y20%' AND suppressed = 0 THEN deaths END) AS undetermined_hanging,
    SUM(CASE WHEN icd10_code LIKE 'X91%' AND suppressed = 0 THEN deaths END) AS assault_hanging,
    SUM(suppressed) AS suppressed_cells,
    -- NULL, never a guess, when any cell in the group is suppressed.
    CASE WHEN SUM(suppressed) > 0 THEN NULL ELSE
        CAST(SUM(CASE WHEN icd10_code LIKE 'Y20%' THEN deaths END) AS REAL)
        / NULLIF(SUM(CASE WHEN icd10_code LIKE 'X70%' THEN deaths END), 0)
    END AS undetermined_ratio
FROM mortality_agg
-- sex and age_group belong in the grouping even while every loaded row
-- has them NULL. The moment a demographic export lands, a GROUP BY that
-- omitted them would pool men and women into one ratio and report it as
-- if it were a breakdown.
GROUP BY year, period, state, race, sex, age_group;

-- ---------------------------------------------------------------
-- Layer 1b: how each state structures death investigation.
-- Joins to mortality_agg.state. Every row carries its own source_url
-- because this is exactly the kind of table a reader will want to
-- check, and because "who certifies deaths here" is contestable in a
-- way a death count is not.
--
-- These are counts of counties from a published federal table, not an
-- assessment of any office. No column here says whether a system is
-- good, and none should be added.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS state_systems (
    state           TEXT PRIMARY KEY,   -- full name, matches mortality_agg.state
    state_abbr      TEXT,

    -- Categorical label, derived by an explicit rule from the county
    -- counts below, never hand-assigned. See tools/load_state_systems.py.
    system_type     TEXT NOT NULL
                    CHECK (system_type IN ('medical examiner','coroner',
                                           'other county official','mixed')),

    counties        INTEGER NOT NULL,
    counties_me     INTEGER NOT NULL,
    counties_cor    INTEGER NOT NULL,
    counties_other  INTEGER NOT NULL,
    counties_elected INTEGER NOT NULL,

    -- Shares weighted by how many deaths each county certifies, because
    -- a state's undetermined rate is a property of its death
    -- certificates. NULL when county deaths could not be matched.
    me_share        REAL,
    coroner_share   REAL,
    elected_share   REAL,
    weight_basis    TEXT,               -- 'deaths' | 'counties'
    has_state_me    INTEGER,

    source_url      TEXT NOT NULL,
    notes           TEXT,
    loaded_at       TEXT NOT NULL
);

-- The join item 1 exists to make: classification practice against
-- certification structure. Inherits the suppression rule from
-- v_undetermined_ratio, so a state with any suppressed cell still
-- comes back NULL rather than as a convenient data point.
DROP VIEW IF EXISTS v_undetermined_by_system;
CREATE VIEW v_undetermined_by_system AS
SELECT
    r.state,
    s.system_type,
    s.me_share,
    s.coroner_share,
    s.elected_share,
    s.has_state_me,
    r.suicide_hanging,
    r.undetermined_hanging,
    r.suppressed_cells,
    r.undetermined_ratio
FROM v_undetermined_ratio r
LEFT JOIN state_systems s ON s.state = r.state
WHERE r.period IS NOT NULL AND r.state IS NOT NULL;
