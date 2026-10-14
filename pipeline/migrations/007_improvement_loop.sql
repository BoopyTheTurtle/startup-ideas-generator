-- Phase 4: the reassess-and-improve loop (SPEC stage 8).
--
-- improvement_card: one proposed change. The auditor (or Python, for revert and
-- broken-metric cards) writes it through `pipeline card-add`; Edgar approves, rejects,
-- and approves merges in the app; the builder and reviewer move it along through the
-- CLI. The trigger below allows only legal status moves, whoever writes the row.
--
-- Lifecycle:  proposed -> approved -> building -> built -> ready -> merged -> reverted
--             proposed/approved -> rejected;  building/built/ready -> abandoned;
--             built/ready -> building (the builder reworks after review).
-- Edgar alone moves proposed -> approved/rejected, sets merge_approved_at and
-- heldout_check; the CLI offers no command for any of the three.
CREATE TABLE improvement_card (
    id               INTEGER PRIMARY KEY,
    created_run_id   INTEGER NOT NULL REFERENCES run(id),
    week             TEXT NOT NULL,                  -- ISO week of creation, '2026-W42'
    kind             TEXT NOT NULL CHECK (kind IN
                     ('extraction', 'mapping', 'source', 'coverage', 'labeling',
                      'instrument', 'revert', 'other')),
    touches          TEXT NOT NULL CHECK (touches IN ('system', 'eval')),
                                                     -- a change touches one, never both
    title            TEXT NOT NULL,
    observation      TEXT NOT NULL,                  -- what the metrics show
    evidence_json    TEXT NOT NULL DEFAULT '[]',     -- [{metric, subject, value, run_id}]
    hypothesis       TEXT NOT NULL,
    change           TEXT NOT NULL,                  -- the proposed change
    expected_effect  TEXT NOT NULL,
    expected_metric  TEXT,                           -- 'layer.name' the change should move
    expected_subject TEXT NOT NULL DEFAULT '',
    expected_direction TEXT CHECK (expected_direction IN ('up', 'down')),
    risk             TEXT NOT NULL,
    size             TEXT NOT NULL CHECK (size IN ('S', 'M', 'L')),
    value            INTEGER NOT NULL CHECK (value BETWEEN 1 AND 5),
    rank_score       REAL NOT NULL,                  -- value / size weight (S 1, M 2, L 4)
    dedupe_key       TEXT NOT NULL,                  -- one open card per key
    reverts_card_id  INTEGER REFERENCES improvement_card(id),
    proposed_by      TEXT NOT NULL DEFAULT 'auditor',
    status           TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN
                     ('proposed', 'approved', 'rejected', 'building', 'built', 'ready',
                      'merged', 'reverted', 'abandoned')),
    decided_at       TEXT,                           -- Edgar's approve or reject
    decision_reason  TEXT,
    decision_note    TEXT,
    build_week       TEXT,                           -- ISO week the build started
    branch           TEXT,
    worktree_path    TEXT,
    base_branch      TEXT,
    base_sha         TEXT,
    base_extract_version TEXT,                       -- extract prompt version at the base, for the eval diff
    head_sha         TEXT,
    verify_json      TEXT,                           -- tests, diff class, eval diff
    needs_heldout    INTEGER NOT NULL DEFAULT 0,     -- set by verify from the diff
    heldout_check    TEXT NOT NULL DEFAULT 'pending' CHECK (heldout_check IN
                     ('pending', 'pass', 'fail', 'not_needed')),   -- Edgar's call
    review_verdict   TEXT CHECK (review_verdict IN ('approve', 'changes')),
    review_notes     TEXT,
    merge_approved_at TEXT,                          -- Edgar's merge approval
    merged_at        TEXT,
    merged_sha       TEXT,
    baseline_json    TEXT,                           -- expected metric at merge time
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX improvement_card_status ON improvement_card (status);
CREATE UNIQUE INDEX improvement_card_open_key ON improvement_card (dedupe_key)
    WHERE status IN ('proposed', 'approved', 'building', 'built', 'ready');

CREATE TRIGGER improvement_card_transition
BEFORE UPDATE OF status ON improvement_card
WHEN OLD.status != NEW.status
BEGIN
    SELECT RAISE(ABORT, 'illegal improvement_card status change')
    WHERE NOT (
        (OLD.status = 'proposed'  AND NEW.status IN ('approved', 'rejected')) OR
        (OLD.status = 'approved'  AND NEW.status IN ('building', 'rejected')) OR
        (OLD.status = 'building'  AND NEW.status IN ('built', 'abandoned')) OR
        (OLD.status = 'built'     AND NEW.status IN ('ready', 'building', 'abandoned')) OR
        (OLD.status = 'ready'     AND NEW.status IN ('merged', 'building', 'abandoned')) OR
        (OLD.status = 'merged'    AND NEW.status = 'reverted')
    );
    -- Only a decided card builds; only a merge-approved, held-out-cleared card merges.
    SELECT RAISE(ABORT, 'card was never approved')
    WHERE NEW.status = 'building' AND OLD.status = 'approved' AND OLD.decided_at IS NULL;
    SELECT RAISE(ABORT, 'merge needs Edgar''s approval and a cleared held-out check')
    WHERE NEW.status = 'merged'
      AND (NEW.merge_approved_at IS NULL OR NEW.heldout_check NOT IN ('pass', 'not_needed'));
    SELECT RAISE(ABORT, 'ready needs a review verdict of approve')
    WHERE NEW.status = 'ready' AND NEW.review_verdict IS NOT 'approve';
END;

-- Append-only history of what happened to a card, and who did it.
CREATE TABLE card_event (
    id      INTEGER PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES improvement_card(id),
    at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    actor   TEXT NOT NULL,          -- auditor, builder, reviewer, system, edgar
    event   TEXT NOT NULL,
    note    TEXT
);

CREATE INDEX card_event_card ON card_event (card_id, id);

-- Weekly fault injection: each row is one known fault applied to a scratch copy of the
-- database and whether the metric that should notice it did (SPEC, "Mutation tests").
CREATE TABLE mutation (
    id        INTEGER PRIMARY KEY,
    run_id    INTEGER NOT NULL REFERENCES run(id),
    name      TEXT NOT NULL,        -- the fault
    metric    TEXT NOT NULL,        -- 'layer.name' expected to react
    subject   TEXT NOT NULL DEFAULT '',
    direction TEXT NOT NULL CHECK (direction IN ('up', 'down')),
    baseline  REAL,
    mutated   REAL,
    caught    INTEGER NOT NULL CHECK (caught IN (0, 1)),
    detail    TEXT
);

CREATE INDEX mutation_run ON mutation (run_id);
