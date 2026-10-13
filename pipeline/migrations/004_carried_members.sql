-- Re-extraction keeps problem identity (docs/research/04): when an item is re-extracted,
-- its new pain inherits the problem its predecessor pain belonged to, with
-- assigned_by = 'carried' and the predecessor's assigned_run_id (pipeline.mapping).
--
-- SQLite cannot alter a CHECK constraint, so problem_member is rebuilt: create, copy,
-- drop, rename, re-index. db.migrate runs this file in one transaction. No table
-- references problem_member, so the rebuild works with foreign keys on.
--
-- Note on snapshot (003): snapshot.mentions counts a problem's ACTIVE member pains (see
-- pipeline.embed.ACTIVE_PAIN_SQL), not all members ever; superseded pains drop out.
-- snapshot.new_mentions counts active members whose assigned_run_id is that run, so
-- carried members never count as new.

CREATE TABLE problem_member_new (
    pain_id         INTEGER PRIMARY KEY REFERENCES pain(id),
    problem_id      INTEGER NOT NULL REFERENCES problem(id),
    similarity      REAL NOT NULL,
    assigned_run_id INTEGER NOT NULL REFERENCES run(id),
    assigned_by     TEXT NOT NULL CHECK (assigned_by IN ('centroid', 'cluster', 'human', 'carried'))
);

INSERT INTO problem_member_new (pain_id, problem_id, similarity, assigned_run_id, assigned_by)
SELECT pain_id, problem_id, similarity, assigned_run_id, assigned_by FROM problem_member;

DROP TABLE problem_member;

ALTER TABLE problem_member_new RENAME TO problem_member;

CREATE INDEX problem_member_problem ON problem_member (problem_id);
