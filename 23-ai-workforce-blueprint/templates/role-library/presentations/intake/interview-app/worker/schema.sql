-- Presentation Interview app — Cloudflare D1 schema.
-- Apply once per environment:
--   npx wrangler d1 execute presentation_intake --file=schema.sql
-- The Worker (src/index.js) is the only writer.
--
-- PRES-009 TENANT ISOLATION: identity is the composite tuple
-- (company_id, installation_id, presentation_id, run_id) minted server-side
-- and immutable. run_id stored here is the server-minted opaque id; the
-- caller's human name is display-only. The old run_id-alone open-session
-- uniqueness let two companies (or two decks of one company) sharing a run
-- name collapse onto ONE capability token / answer stream.

CREATE TABLE IF NOT EXISTS sessions (
  token            TEXT PRIMARY KEY,       -- 128-bit capability token (hex)
  run_id           TEXT NOT NULL,          -- server-minted opaque run id
  display_name     TEXT,                   -- caller human run name; NEVER a storage key
  box_id           TEXT NOT NULL,          -- legacy display column (box that opened it)
  company_id       TEXT,                   -- tenant company (PRES-009; NULL only for un-migrated legacy)
  installation_id  TEXT,                   -- fleet installation (PRES-009)
  presentation_id  TEXT,                   -- deck/presentation identity (PRES-009)
  intake_session_id TEXT,                  -- server-minted opaque intake session id (PRES-009)
  schema_fp        TEXT,                   -- question-schema fingerprint gating link reuse (PRES-009)
  tenant_state     TEXT DEFAULT 'active',  -- 'active' | 'quarantined' (PRES-009 legacy migration)
  quarantine_reason TEXT,
  question_set  TEXT NOT NULL,             -- 'standard' | 'signature'
  questions_json TEXT NOT NULL,            -- the questions_payload (from the box JSONs)
  status        TEXT NOT NULL DEFAULT 'open', -- 'open' | 'complete' | 'expired'
  created_at    INTEGER NOT NULL,          -- epoch seconds
  expires_at    INTEGER NOT NULL,          -- epoch seconds
  completed_at  INTEGER
);

-- Single ACTIVE session per composite tenant run.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_open_tenant_run
  ON sessions (company_id, installation_id, presentation_id, run_id)
  WHERE status = 'open' AND tenant_state = 'active';

CREATE TABLE IF NOT EXISTS answers (
  id          INTEGER PRIMARY KEY AUTOINCREMENT, -- monotonic poll cursor
  token       TEXT NOT NULL,
  question_id TEXT NOT NULL,
  value       TEXT NOT NULL,
  created_at  INTEGER NOT NULL,
  UNIQUE (token, question_id),             -- one answer per question (re-answer overwrites)
  FOREIGN KEY (token) REFERENCES sessions (token)
);

CREATE INDEX IF NOT EXISTS idx_answers_token_id ON answers (token, id);

-- Finished intake records (from POST /api/intake) + dept-start trigger state.
-- PRES-009: every row carries its tenant tuple; the intake record must name
-- company_id/installation_id/presentation_id/run_id (opaque, validated) or the
-- store is REFUSED, never guessed. Ambiguous legacy rows are quarantined by
-- the worker's runLegacyMigration with an explicit remediation reason.
CREATE TABLE IF NOT EXISTS intakes (
  session_id       TEXT PRIMARY KEY,        -- the server-minted intake_session_id
  file_name        TEXT NOT NULL,
  intake_json      TEXT NOT NULL,           -- the dept-format intake record
  company_id       TEXT,                    -- tenant company (PRES-009)
  installation_id  TEXT,                    -- fleet installation (PRES-009)
  presentation_id  TEXT,                    -- deck identity (PRES-009)
  run_id           TEXT,                    -- server-minted run id (PRES-009)
  tenant_state     TEXT DEFAULT 'active',   -- 'active' | 'quarantined' (PRES-009)
  quarantine_reason TEXT,
  quarantine_remediation TEXT,
  dept_trigger     TEXT DEFAULT 'pending',  -- 'pending' | 'fired' | 'deferred'
  dept_task_id     TEXT,
  dept_trigger_note TEXT,
  created_at       INTEGER NOT NULL,
  updated_at       INTEGER
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_intakes_tenant_session
  ON intakes (company_id, session_id) WHERE tenant_state = 'active';

-- PRES-007 (W1 WF03) — durable dept-start handoff outbox. One row per intake
-- session; the single idempotency anchor for worker→CC delivery. States:
--   firing             POST /api/tasks/ingest in flight
--   fired              CC ack received and scope-bound (dept_task_id recorded)
--   failed_retryable   5xx / transport — retried on a later dept-start call
--   failed_nonretryable 4xx / missing credential / ack binding mismatch —
--                      human action required, never auto-retried
-- A 'fired' row makes every later /api/dept-start for the session an idempotent
-- ack replay (no second card). The interrupted-ack case (crash between POST and
-- ack write) leaves 'firing'; the retry is deduped by the REMOTE ingest
-- idempotency key derived from dest|company|source_ref|title.
CREATE TABLE IF NOT EXISTS handoff_outbox (
  session_id   TEXT PRIMARY KEY,
  status       TEXT NOT NULL,             -- 'firing' | 'fired' | 'failed_retryable' | 'failed_nonretryable'
  dept_task_id TEXT,                      -- bound CC task id once acked
  dest_box     TEXT,                      -- destination box binding (dest_box in signed payload)
  attempts     INTEGER NOT NULL DEFAULT 0,
  last_error   TEXT,
  updated_at   INTEGER
);
