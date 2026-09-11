-- PRES-024 migration for EXISTING deployments (apply once after the tenant-isolation migration):
--   npx wrangler d1 execute presentation_intake --remote --file=schema-migrate-pres024.sql
--
-- Separates stable session identity (session_id) from renewable access-token
-- grants, and adds the correction / renewal / delivery audit surfaces.
-- Fresh installs just use schema.sql.

ALTER TABLE sessions ADD COLUMN session_id TEXT;
-- company_id is already supplied by the tenant-isolation migration.
ALTER TABLE sessions ADD COLUMN recipient_chat_id TEXT;
ALTER TABLE sessions ADD COLUMN revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sessions ADD COLUMN invalidated_at INTEGER;
ALTER TABLE sessions ADD COLUMN invalidated_reason TEXT;

ALTER TABLE answers ADD COLUMN session_id TEXT;

CREATE TABLE IF NOT EXISTS revoked_tokens (
  token       TEXT PRIMARY KEY,
  session_id  TEXT NOT NULL,
  revoked_at  INTEGER NOT NULL,
  reason      TEXT
);

CREATE TABLE IF NOT EXISTS corrections (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id      TEXT NOT NULL,
  question_id     TEXT NOT NULL,
  old_value       TEXT,
  new_value       TEXT NOT NULL,
  revision_before INTEGER NOT NULL,
  revision_after  INTEGER NOT NULL,
  actor           TEXT NOT NULL DEFAULT 'client',
  corrected_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS retry_deliveries (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id       TEXT NOT NULL,
  recipient_chat_id TEXT NOT NULL,
  channel          TEXT NOT NULL DEFAULT 'telegram',
  delivered_at     INTEGER NOT NULL,
  token            TEXT,
  recorded_at      INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_retry_deliveries_session ON retry_deliveries (session_id, id);
CREATE INDEX IF NOT EXISTS idx_answers_session_id ON answers (session_id, id);
CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON sessions (session_id, created_at);

-- Backfill: every pre-PRES-024 grant row becomes its own stable identity and
-- carries its answers onto that identity.
UPDATE sessions SET session_id = token WHERE session_id IS NULL;
UPDATE answers SET session_id = (SELECT s.session_id FROM sessions s WHERE s.token = answers.token)
  WHERE session_id IS NULL;