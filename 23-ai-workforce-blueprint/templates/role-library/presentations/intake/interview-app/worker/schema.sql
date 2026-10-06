-- Presentation intake mini-app — Cloudflare D1 schema.
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
  session_id TEXT,
  recipient_chat_id TEXT,
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

-- Single ACTIVE session per composite tenant run.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_open_tenant_run
  ON sessions (company_id, installation_id, presentation_id, run_id)
  WHERE status = 'open' AND tenant_state = 'active';

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
