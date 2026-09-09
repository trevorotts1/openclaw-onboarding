-- Presentation intake mini-app — Cloudflare D1 schema.
-- Apply once per environment:
--   npx wrangler d1 execute presentation_intake --file=schema.sql
-- The Worker (src/index.js) is the only writer. No client data lives anywhere
-- but here; the box bridge replays it into the run dir's intake_ledger.json.
--
-- PRES-024 (stable session identity vs renewable access-token grants):
--   * sessions.session_id  — the STABLE session identity. Answers are keyed to
--     session_id, never to the capability token, so a renewal (new token, same
--     session) keeps every prior answer. Rows remain per-grant (token = PK);
--     a renewed session has many rows sharing one session_id.
--   * sessions.company_id / recipient_chat_id — the renewal/delivery binding.
--     Renewal must present the same company; retry-link delivery must target
--     the bound recipient.
--   * sessions.revision — monotonic per session; renewal and every correction
--     bump it. Corrections never mix revisions (each correction row records
--     revision_before/revision_after).
--   * sessions.invalidated_at — downstream-invalidation stamp set when a
--     correction lands after production started: outputs built on the old
--     revision require rebuild.
--   * revoked_tokens / corrections / retry_deliveries — audit surfaces.
-- Existing deployments: apply schema-migrate-pres024.sql instead (same shape,
-- ALTER TABLE + backfill form).

CREATE TABLE IF NOT EXISTS sessions (
  token         TEXT PRIMARY KEY,          -- 128-bit capability token (hex); one row per GRANT
  session_id    TEXT,                      -- stable session identity (survives renewal)
  run_id        TEXT NOT NULL,             -- the deck run this intake feeds
  box_id        TEXT NOT NULL,             -- which fleet box opened it
  company_id    TEXT,                      -- renewal binding (wrong-company renew rejected)
  recipient_chat_id TEXT,                  -- bound delivery recipient for retry links
  question_set  TEXT NOT NULL,             -- 'standard' | 'signature'
  questions_json TEXT NOT NULL,            -- the questions_payload (from the box JSONs)
  confirm_code  TEXT,                      -- optional 6-digit high-trust code (unused by this app; kept for schema parity with intake-miniapp)
  status        TEXT NOT NULL DEFAULT 'open', -- 'open' | 'complete' | 'expired' | 'renewed'
  revision      INTEGER NOT NULL DEFAULT 0,   -- monotonic; +1 per renewal/correction
  invalidated_at INTEGER,                  -- downstream outputs invalidated (rebuild required)
  invalidated_reason TEXT,
  created_at    INTEGER NOT NULL,          -- epoch seconds (grant creation/renewal time)
  expires_at    INTEGER NOT NULL,          -- epoch seconds (this grant's expiry)
  completed_at  INTEGER
);

-- Single ACTIVE session per run: at most one 'open' row for a given run_id.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_open_run
  ON sessions (run_id) WHERE status = 'open';

-- Stable-identity lookup (renew endpoint): find any grant of a session fast.
CREATE INDEX IF NOT EXISTS idx_sessions_session_id
  ON sessions (session_id, created_at);

CREATE TABLE IF NOT EXISTS answers (
  id          INTEGER PRIMARY KEY AUTOINCREMENT, -- monotonic poll cursor
  token       TEXT NOT NULL,               -- the grant the answer was written under
  session_id  TEXT,                        -- STABLE identity answers hang off (PRES-024)
  question_id TEXT NOT NULL,
  value       TEXT NOT NULL,
  created_at  INTEGER NOT NULL,
  UNIQUE (session_id, question_id),        -- one answer per question per SESSION (re-answer overwrites, PRES-024)
  FOREIGN KEY (token) REFERENCES sessions (token)
);

CREATE INDEX IF NOT EXISTS idx_answers_token_id ON answers (token, id);
CREATE INDEX IF NOT EXISTS idx_answers_session_id ON answers (session_id, id);

-- PRES-024: tokens whose grant was replaced by a renewal. Looked up when a
-- token matches no 'open' grant, so an old capability is REJECTED (410), never
-- silently treated as unknown.
CREATE TABLE IF NOT EXISTS revoked_tokens (
  token       TEXT PRIMARY KEY,
  session_id  TEXT NOT NULL,
  revoked_at  INTEGER NOT NULL,
  reason      TEXT
);

-- PRES-024: authenticated corrections. One row per correction with the
-- revision it was applied at — downstream invalidation is auditable and two
-- corrections never mix revisions.
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

-- PRES-024: retry-link deliveries, recorded against the BOUND recipient.
-- A delivery record naming any other recipient is refused (fail-closed).
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