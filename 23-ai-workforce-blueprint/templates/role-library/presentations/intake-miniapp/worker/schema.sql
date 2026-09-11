-- Presentation intake mini-app — Cloudflare D1 schema.
-- Apply once per environment:
--   npx wrangler d1 execute presentation_intake --file=schema.sql
-- The Worker (src/index.js) is the only writer. No client data lives anywhere
-- but here; the box bridge replays it into the run dir's intake_ledger.json.
--
-- PRES-009 TENANT ISOLATION: sessions are keyed by the composite tenant tuple
-- (company_id, installation_id, presentation_id, run_id) minted server-side.
-- run_id stored on the row is the server-minted opaque run id; the caller's
-- human name rides as display_name. The old run_id-alone uniqueness let two
-- companies (or two simultaneous decks of one company) reuse one run name and
-- collapse onto a single capability token / answer stream.

CREATE TABLE IF NOT EXISTS sessions (
  token            TEXT PRIMARY KEY,       -- 128-bit capability token (hex)
  run_id           TEXT NOT NULL,          -- server-minted opaque run id (display-only name in display_name)
  display_name     TEXT,                   -- caller-supplied human run name; NEVER a storage key
  box_id           TEXT NOT NULL,          -- which fleet box opened it (back-compat display column)
  company_id       TEXT,                   -- tenant company (PRES-009; NULL only for un-migrated legacy rows)
  installation_id  TEXT,                   -- fleet installation (PRES-009)
  presentation_id  TEXT,                   -- deck/presentation identity (PRES-009)
  intake_session_id TEXT,                  -- server-minted opaque intake session id (PRES-009)
  schema_fp        TEXT,                   -- question-schema fingerprint gating link reuse (PRES-009)
  tenant_state     TEXT DEFAULT 'active',  -- 'active' | 'quarantined' (PRES-009 legacy migration)
  quarantine_reason TEXT,                  -- explicit remediation reason when quarantined (PRES-009)
  question_set  TEXT NOT NULL,             -- 'standard' | 'signature'
  questions_json TEXT NOT NULL,            -- the questions_payload (from the box JSONs)
  confirm_code  TEXT,                      -- optional 6-digit high-trust code
  status        TEXT NOT NULL DEFAULT 'open', -- 'open' | 'complete' | 'expired'
  created_at    INTEGER NOT NULL,          -- epoch seconds
  expires_at    INTEGER NOT NULL,          -- epoch seconds
  completed_at  INTEGER
);

-- Single ACTIVE session per composite tenant run: at most one 'open' row for
-- a given (company, installation, presentation, run). Two companies reusing
-- one human run name, or one company launching two simultaneous decks, never
-- collide — the tuple differs.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_open_tenant_run
  ON sessions (company_id, installation_id, presentation_id, run_id)
  WHERE status = 'open' AND (tenant_state IS NULL OR tenant_state = 'active');

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