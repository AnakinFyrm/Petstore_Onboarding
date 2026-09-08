-- Schema for pet-agent.
--
-- This file is the schema of record and is applied on every start, so every
-- statement must be idempotent. There is no migration tool: evolve the schema
-- by adding statements here, additively.
--
--   new table   -> CREATE TABLE IF NOT EXISTS
--   new column  -> ALTER TABLE ... ADD COLUMN IF NOT EXISTS
--   new index   -> CREATE INDEX IF NOT EXISTS
--
-- Dropping or retyping a column is not safe to run repeatedly against live data.
-- Do those deliberately, by hand, with a backup.

-- Example table. Replace it with the real schema.
CREATE TABLE IF NOT EXISTS example_records (
    id         BIGSERIAL PRIMARY KEY,
    key        TEXT        NOT NULL UNIQUE,
    payload    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS example_records_created_at_idx ON example_records (created_at);
