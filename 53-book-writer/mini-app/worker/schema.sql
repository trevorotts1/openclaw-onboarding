-- ============================================================================
-- schema.sql — book-writer mini-app KV binding "bw-bindings" key shape contract
--
-- U02 Worker core. Cloudflare Workers KV is a schemaless key-value store, so
-- this file is the DECLARATIVE CONTRACT for every key this Worker (and the
-- box-side ingest poller, U12) reads or writes. It doubles as the seed
-- inventory for U19 deploy.sh (`wrangler kv key put ...`).
--
-- Master-plan section 1 + 3 contract:
--   - The edge is a DUMB RELAY: ZERO client PITs, ZERO API keys, ZERO
--     Anthropic ids. The KV binding row is the SOLE authority for the
--     destination (POSSESSION + BINDING + CREDENTIAL/WHITELIST locks).
--   - Token is single-use per step; per-step consumed counters make replay
--     idempotent (a replayed submit cannot duplicate).
--   - R2 holds app shell + per-client phase configs; KV holds tokens,
--     registry, run state, consumed counters.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. TOKEN BINDINGS  (ttl: 1h per-miss; but expiry is also encoded in the row)
--
-- key:   tk:<opaque-token>        (token_urlsafe(32) hex — Plan 3)
-- value: JSON
--   {
--     "client_id":    string,   -- e.g. "client_FAKE_A"  (never a GHL location id in the request)
--     "location_id":  string,   -- GHL location bound server-side; NEVER read from the request
--     "slug":         string,   -- fleet client slug, e.g. "karen-vaughn"
--     "phase_id":     string,   -- "P0-INTAKE" | "GATE-1-title" | "GATE-2-outline" |
--                               -- "GATE-3-approval" | "GATE-4-approval-r2" | "GATE-433"
--     "mode":         string,   -- "full" | "4x3x3"  (P0-INTAKE only, else null)
--     "run_id":       string,   -- per-run id, e.g. "run_<uuid>"
--     "exp":          number,   -- epoch ms expiry (also KV ttl)
--     "status":       string,   -- "open" | "consumed" | "done" (intake-complete → done)
--     "step":         number    -- per-step consumed counter (dedupe); also lives in ctr: key
--   }
--
-- lookup:  GET tk:<token>  → 401 when missing OR exp < now OR status != "open"
-- update:  PUT tk:<token>  { ...binding, status: "consumed" }   after a step
--          PUT tk:<token>  { ...binding, status: "done" }       after intake complete
--
CREATE TABLE IF NOT EXISTS bw_bindings.tokens (
  key      TEXT PRIMARY KEY,     -- tk:<token>
  value    TEXT NOT NULL,        -- JSON binding row above
  ttl_secs INTEGER               -- 3600 (honor exp row; KV purges after ttl)
);

-- ---------------------------------------------------------------------------
-- 2. CLIENT REGISTRY  (read-only for the edge; seeded by U19)
--
-- key:   reg:<slug>
-- value: JSON { "client_id": string, "slug": string, "contact_seed": {...} }
-- Used to validate that a slug in the URL is known and to map slug→client_id.
-- The edge never holds a GHL API key for the client (dumb relay).
CREATE TABLE IF NOT EXISTS bw_bindings.registry (
  key   TEXT PRIMARY KEY,        -- reg:<slug>
  value TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- 3. PER-RUN STATE  (resume handle; U11/U12 read this)
--
-- key:   run:<run_id>
-- value: JSON
--   {
--     "client_id": string, "slug": string, "mode": string,
--     "phase_order": [ "P0-INTAKE", "GATE-1-title", ... ],   -- derived from manifest gates_order
--     "current_phase": string, "current_question": number,
--     "answered": { "<phase>:<question_id>": true },
--     "intake_id": string|null, "run_dir": string|null,
--     "created_at": number, "updated_at": number
--   }
CREATE TABLE IF NOT EXISTS bw_bindings.run_state (
  key   TEXT PRIMARY KEY,        -- run:<run_id>
  value TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- 4. PER-STEP CONSUMED COUNTERS  (dedupe / single-use per step)
--
-- key:   ctr:<run_id>:<phase_id>:<question_id>
-- value: integer count of submissions already recorded for this step.
--
-- Semantics (master plan section 1 + 3):
--   - First submit: INCR → returns 1 → accepted, answer staged.
--   - Replay (same link / same step again): INCR → returns >1 → 409/401
--     "already answered" — idempotent, no duplicate row, zero GHL calls.
--   - Resume is NOT replay: it advances run: state to the NEXT unanswered
--     question (current_question in run:<run_id>), so the next ctr: key is a
--     fresh step.
CREATE TABLE IF NOT EXISTS bw_bindings.consumed (
  key   TEXT PRIMARY KEY,        -- ctr:<run_id>:<phase_id>:<question_id>
  value INTEGER NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- 5. R2 OBJECT LAYOUT (referenced by this Worker; written by U03/U04/U12)
--
--   app/<version>/index.html        -- SPA shell (version-and-flip atomic unit)
--   app/<version>/app.js            -- SPA bundle
--   app/<version>/app.css           -- SPA styles
--   app/latest                      -- pointer object { "version": "..." }  (flip)
--   config/<slug>/P0-INTAKE:full.json     -- phase config (DATA, never code)
--   config/<slug>/GATE-1-title.json
--   config/<slug>/<phase>.<v>.json  -- versioned; flip by pointer
--   staging/<client>/<run>/<step>.json    -- staged answers (U03)
--   transcripts/<client>/<job>.json       -- async transcript results (U13)
--
-- The Worker serves the SPA + phase config from R2 at request time (U02 GET /
-- route); media PRESIGNED upload (U04) writes straight to R2 never through the
-- Worker request body.
-- ============================================================================
