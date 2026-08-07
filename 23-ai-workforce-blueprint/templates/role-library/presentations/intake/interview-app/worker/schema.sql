-- Presentation Interview app — Cloudflare D1 schema.
-- Apply once per environment:
--   npx wrangler d1 execute presentation_intake --file=schema.sql
-- The Worker (src/index.js) is the only writer.

CREATE TABLE IF NOT EXISTS sessions (
  token         TEXT PRIMARY KEY,          -- 128-bit capability token (hex)
  run_id        TEXT NOT NULL,             -- the deck run this intake feeds
  box_id        TEXT NOT NULL,             -- which fleet box opened it
  question_set  TEXT NOT NULL,             -- 'standard' | 'signature'
  questions_json TEXT NOT NULL,            -- the questions_payload (from the box JSONs)
  status        TEXT NOT NULL DEFAULT 'open', -- 'open' | 'complete' | 'expired'
  created_at    INTEGER NOT NULL,          -- epoch seconds
  expires_at    INTEGER NOT NULL,          -- epoch seconds
  completed_at  INTEGER
);

-- Single ACTIVE session per run: at most one 'open' row for a given run_id.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_open_run
  ON sessions (run_id) WHERE status = 'open';

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
CREATE TABLE IF NOT EXISTS intakes (
  session_id       TEXT PRIMARY KEY,        -- the intake_session_id
  file_name        TEXT NOT NULL,
  intake_json      TEXT NOT NULL,           -- the dept-format intake record
  dept_trigger     TEXT DEFAULT 'pending',  -- 'pending' | 'fired' | 'deferred'
  dept_task_id     TEXT,
  dept_trigger_note TEXT,
  created_at       INTEGER NOT NULL,
  updated_at       INTEGER
);
