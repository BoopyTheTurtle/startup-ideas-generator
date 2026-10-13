-- Phase 2: extraction (stage 2) and mapping (stage 3).

-- Sources whose terms forbid reproduction keep no text: the body is blanked once
-- extraction has run (SPEC decision 7).
ALTER TABLE raw_item ADD COLUMN retain_text INTEGER NOT NULL DEFAULT 1;
ALTER TABLE raw_item ADD COLUMN text_discarded_at TEXT;

-- Prompt registry: every LLM-derived row points at the exact prompt text that made it.
CREATE TABLE prompt (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,                 -- e.g. 'extract'
    version    TEXT NOT NULL,                 -- sha256 of the text, first 12 hex chars
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (name, version)
);

-- One verdict per raw item per prompt version.
CREATE TABLE extraction (
    id          INTEGER PRIMARY KEY,
    raw_item_id INTEGER NOT NULL REFERENCES raw_item(id),
    run_id      INTEGER NOT NULL REFERENCES run(id),
    prompt_id   INTEGER NOT NULL REFERENCES prompt(id),
    model       TEXT NOT NULL,                -- model id, or 'rule' for pre-filter verdicts
    is_pain     INTEGER NOT NULL CHECK (is_pain IN (0, 1)),
    note        TEXT,                         -- e.g. why a rule filtered it
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (raw_item_id, prompt_id)
);

-- The problems an item describes (0-3 per item). These rows are embedded and clustered.
CREATE TABLE pain (
    id             INTEGER PRIMARY KEY,
    extraction_id  INTEGER NOT NULL REFERENCES extraction(id),
    idx            INTEGER NOT NULL,          -- position within the item
    job            TEXT NOT NULL,             -- what the person is trying to get done (English)
    problem        TEXT NOT NULL,             -- the obstacle, free of solution words (English)
    who            TEXT NOT NULL,             -- segment hint: role and context (English)
    workaround     TEXT,                      -- what they do today, if stated
    cost_cue       TEXT,                      -- time, money, or risk, with unit if stated
    intensity      INTEGER NOT NULL CHECK (intensity BETWEEN 1 AND 5),
    evidence_level TEXT NOT NULL CHECK (evidence_level IN ('E1', 'E2', 'E3')),
                                              -- E1 said/wished, E2 past behaviour, E3 spent money
    quote          TEXT NOT NULL,             -- verbatim from the item, original language,
                                              -- or a paraphrase when the source keeps no text
    quote_kind     TEXT NOT NULL CHECK (quote_kind IN ('verbatim', 'paraphrase')),
    quote_start    INTEGER,                   -- offsets into the item's plain text (verbatim only)
    quote_end      INTEGER,
    UNIQUE (extraction_id, idx)
);

CREATE INDEX pain_extraction ON pain (extraction_id);

-- Embedding of each pain's normalized "problem — who" text. float32 little-endian.
CREATE TABLE embedding (
    pain_id INTEGER PRIMARY KEY REFERENCES pain(id),
    model   TEXT NOT NULL,
    dim     INTEGER NOT NULL,
    vec     BLOB NOT NULL
);

-- Canonical problems: stable identities that pains join over time.
CREATE TABLE problem (
    id             INTEGER PRIMARY KEY,
    title          TEXT NOT NULL,             -- job + outcome form, solution-free
    statement      TEXT,
    status         TEXT NOT NULL DEFAULT 'new'
                   CHECK (status IN ('new', 'watching', 'promoted', 'archived', 'merged')),
    merged_into    INTEGER REFERENCES problem(id),
    centroid       BLOB,                      -- mean member embedding, float32
    centroid_model TEXT,
    created_run_id INTEGER NOT NULL REFERENCES run(id),
    updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    title_source   TEXT NOT NULL DEFAULT 'auto' CHECK (title_source IN ('auto', 'curator', 'human'))
);

CREATE TABLE problem_member (
    pain_id         INTEGER PRIMARY KEY REFERENCES pain(id),
    problem_id      INTEGER NOT NULL REFERENCES problem(id),
    similarity      REAL NOT NULL,
    assigned_run_id INTEGER NOT NULL REFERENCES run(id),
    assigned_by     TEXT NOT NULL CHECK (assigned_by IN ('centroid', 'cluster', 'human'))
);

CREATE INDEX problem_member_problem ON problem_member (problem_id);

-- Old ids keep resolving after merges.
CREATE TABLE problem_alias (
    old_id     INTEGER PRIMARY KEY,
    new_id     INTEGER NOT NULL REFERENCES problem(id),
    reason     TEXT NOT NULL,
    decided_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Near-duplicate problem pairs awaiting Edgar's merge decision.
CREATE TABLE merge_candidate (
    a_id       INTEGER NOT NULL REFERENCES problem(id),
    b_id       INTEGER NOT NULL REFERENCES problem(id),
    similarity REAL NOT NULL,
    run_id     INTEGER NOT NULL REFERENCES run(id),
    status     TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'merged', 'rejected')),
    PRIMARY KEY (a_id, b_id),
    CHECK (a_id < b_id)
);

-- One row per problem per mapping run: the history behind trend charts.
CREATE TABLE snapshot (
    run_id           INTEGER NOT NULL REFERENCES run(id),
    problem_id       INTEGER NOT NULL REFERENCES problem(id),
    mentions         INTEGER NOT NULL,        -- member pains, all time
    distinct_authors INTEGER NOT NULL,        -- items without an author count as distinct
    sources          INTEGER NOT NULL,
    countries        INTEGER NOT NULL,
    new_mentions     INTEGER NOT NULL,        -- members assigned in this run
    PRIMARY KEY (run_id, problem_id)
);

-- Edgar's steering actions (written by the app from Phase 3).
CREATE TABLE decision (
    id         INTEGER PRIMARY KEY,
    problem_id INTEGER REFERENCES problem(id),
    action     TEXT NOT NULL,                 -- watch, promote, kill, merge, split, rename, label
    reason     TEXT,                          -- reason code
    note       TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
