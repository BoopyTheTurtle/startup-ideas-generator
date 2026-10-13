-- Phase 0: runs and metrics. Later phases add their tables in new numbered files.

CREATE TABLE run (
    id          INTEGER PRIMARY KEY,
    kind        TEXT NOT NULL,              -- smoke, collect, extract, map, reassess, ...
    started_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    finished_at TEXT,
    status      TEXT NOT NULL DEFAULT 'running'
                CHECK (status IN ('running', 'ok', 'failed')),
    git_sha     TEXT,
    note        TEXT
);

-- One row per measurement. Stage 8 reads this table to audit the system.
CREATE TABLE metric (
    id          INTEGER PRIMARY KEY,
    run_id      INTEGER NOT NULL REFERENCES run(id),
    layer       TEXT NOT NULL,              -- sources, coverage, extraction, mapping, judgment, methodology
    name        TEXT NOT NULL,
    subject     TEXT NOT NULL DEFAULT '',   -- e.g. a source name or a problem id
    value       REAL NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX metric_lookup ON metric (layer, name, subject, run_id);
