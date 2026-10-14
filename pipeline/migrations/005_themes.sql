-- Phase 3: themes, the radar's broad entry point. Themes are loose topic clusters over
-- active pains, recomputed by every themes run (run.kind = 'themes'); they are a
-- browsing aid, never stable identities like problems. The current themes are those of
-- the latest themes run with status 'ok'.

CREATE TABLE theme (
    id               INTEGER PRIMARY KEY,
    run_id           INTEGER NOT NULL REFERENCES run(id),
    title            TEXT NOT NULL,
    statement        TEXT,
    title_source     TEXT NOT NULL DEFAULT 'auto'
                     CHECK (title_source IN ('auto', 'curator', 'carried')),
    carried_from     INTEGER REFERENCES theme(id),  -- previous run's theme with mostly the same members
    size             INTEGER NOT NULL,              -- member pains
    distinct_authors INTEGER NOT NULL,              -- items without an author count as distinct
    sources          INTEGER NOT NULL,
    countries        INTEGER NOT NULL,
    cohesion         REAL                           -- mean pairwise cosine of members
);

CREATE INDEX theme_run ON theme (run_id);

CREATE TABLE theme_member (
    theme_id INTEGER NOT NULL REFERENCES theme(id),
    pain_id  INTEGER NOT NULL REFERENCES pain(id),
    PRIMARY KEY (theme_id, pain_id)
);

CREATE INDEX theme_member_pain ON theme_member (pain_id);
