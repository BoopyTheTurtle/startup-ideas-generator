-- Phase 3 review fixes.
--
-- pipeline_state: small key/value facts the pipeline publishes for the app. Python
-- writes them (pipeline.db.set_state); the app only reads. Keys in use:
--   active_extract_prompt_id  prompt.id of the extract prompt that
--                             pipeline/prompts/extract.md hashes to now (written by
--                             extract, map, and themes runs). A pain is active when it
--                             belongs to its item's extraction under this prompt, else to
--                             the item's latest extraction (pipeline.embed.ACTIVE_PAIN_SQL).
CREATE TABLE pipeline_state (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Theme naming provenance, as every LLM-derived row records. NULL for 'auto' themes and
-- for themes named before this migration; a carried theme copies its source theme's.
ALTER TABLE theme ADD COLUMN prompt_id INTEGER REFERENCES prompt(id);
ALTER TABLE theme ADD COLUMN model TEXT;
