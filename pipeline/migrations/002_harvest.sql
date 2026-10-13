-- Phase 1: raw items from stream collectors, collector health, and per-collector cursors.

CREATE TABLE raw_item (
    id           INTEGER PRIMARY KEY,
    source       TEXT NOT NULL,             -- collector name, e.g. 'hn'
    source_id    TEXT NOT NULL,             -- the source's own id for the item
    url          TEXT,
    author_hash  TEXT,                      -- salted hash; raw author names are never stored
    created_at   TEXT,                      -- when the source says the item was posted (UTC ISO 8601)
    fetched_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    title        TEXT,
    body         TEXT NOT NULL,
    lang         TEXT,                      -- ISO 639-1 if known
    country      TEXT,                      -- ISO 3166-1 alpha-2, or 'EU' for EU-wide
    metrics_json TEXT NOT NULL DEFAULT '{}',-- engagement: score, votes, signatures, rating...
    extra_json   TEXT NOT NULL DEFAULT '{}',-- source-specific fields worth keeping
    content_hash TEXT NOT NULL,
    license      TEXT NOT NULL,
    tos_class    TEXT NOT NULL CHECK (tos_class IN ('clean', 'gray', 'restricted')),
    run_id       INTEGER NOT NULL REFERENCES run(id),
    UNIQUE (source, source_id)
);

CREATE INDEX raw_item_source_created ON raw_item (source, created_at);
CREATE INDEX raw_item_run ON raw_item (run_id);

CREATE TABLE collector_health (
    source               TEXT PRIMARY KEY,
    last_attempt_at      TEXT,
    last_success_at      TEXT,
    last_status          TEXT,              -- ok, failed, schema_drift, blocked
    last_error           TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    items_last_run       INTEGER NOT NULL DEFAULT 0
);

-- Cursors and other small state a collector keeps between runs.
CREATE TABLE collector_state (
    source TEXT NOT NULL,
    key    TEXT NOT NULL,
    value  TEXT NOT NULL,
    PRIMARY KEY (source, key)
);
