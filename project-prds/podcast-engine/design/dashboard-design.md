# Podcast Production Engine, Client Dashboard: DESIGN SPEC v1.0

Status: DESIGN COMPLETE, READY FOR BUILD.
This document is the definitive design and data-model specification for the client-facing
podcast dashboard of the Podcast Production Engine OpenClaw skill. It is NOT the build.
A Fable sub-agent builds from this spec during /goal execution. Every decision below is
grounded in one of three sources, cited inline:

- SPEC: `PODCAST_EPISODE_GENERATION_SYSTEM.md` (Master AI Instructions v3.1), especially
  the `client_dashboard`, `credit_out_queue`, `custom_field_map`, `input_payload_reference`,
  `episode_construction_workflow`, and `qc_protocol` sections.
- BRIEF: `CLAUDE_CODE_BUILD_BRIEF.md` v1.0 (build orchestration, Cloudflare hosting decision,
  preserve-these-rules list).
- CC: the live BlackCEO Command Center checkout at
  `/Users/blackceomacmini/canary/command-center` (v4.53.2), which supplies the design system
  the dashboard must visually match.

Writing rules honored in this spec and binding on the build: never use the em dash
character in any output the skill produces; the dashboard is read-only over engine records;
never expose secrets, tokens, API keys, or internal credentials in any dashboard surface.

---

## 1. Purpose and scope

The engine turns an intake survey submission into a fully produced, published podcast
episode (research, script, QC, cover art, audio, documents, Podbean publish, GoHighLevel
link-back, workflow enrollment). SPEC `client_dashboard` requires "a visually clean,
aesthetically pleasing view of every episode submission and its status" showing submitter
identity, pipeline status including credit-out queue holds and their age, and aged-out
(over 60 days) visibility.

In scope for this dashboard:

1. Live pipeline view of every submission with its stage (Section 7).
2. Credit-out queue view with age, countdown to the 60-day drop, and aged-out flag (Section 8).
3. Per-client scoping of all data (Section 10).
4. The persistence layer the engine writes and the dashboard reads (Section 5). This is
   a real gap in SPEC: the doc says the dashboard "reads from the same episode records the
   engine already produces" but defines no datastore anywhere. This spec closes that gap.
5. PII (Personally Identifiable Information) isolation, retention, and deletion-on-churn
   (Section 10).
6. Auth plus a revocable dashboard token that ties into the Cloudflare revocation
   runbook (Section 11).
7. Responsive layout (mobile, tablet, desktop) consistent with the Command Center (Section 12).

Explicitly OUT of scope (guardrails the build must enforce):

- No data entry of any kind. The dashboard has zero write paths to episode records.
- No pipeline re-run, retry, or cancel buttons. The engine owns its own retry logic and
  its three-strike QC failure cap (SPEC `qc_protocol`). Operators intervene through the
  engine, never through this dashboard.
- No customer messaging surface. Convert and Flow (the white-label name for GoHighLevel)
  owns all customer messaging (SPEC `where_openclaw_responsibility_ends`).
- No display of credentials, API keys, token values, webhook URLs, or internal prompts.
- No cross-client data, ever.

---

## 2. Product decisions (made per BRIEF decision authority)

BRIEF grants autonomous decision authority on routine build decisions. These are the
decisions this design locks in, with reasoning:

### D1. The dashboard is a route group inside the Command Center app, not a separate app.

The Command Center (Next.js 14.2, App Router, React 18, Tailwind 3.4, better-sqlite3)
already runs on every client box, already carries the full design system, already has the
Cloudflare-fronted auth middleware, and already has the client's public
`<client>.zerohumanworkforce.com` hostname wired. Building the podcast dashboard as a new
`/podcast` route group inside that app gives pixel-identical visual consistency for free,
reuses the layered auth middleware, and satisfies BRIEF's "work in complete harmony with
the command center repo." A standalone app would duplicate all of that and drift.

### D2. Hosting: served from the client box, exposed through BlackCEO's Cloudflare zone.

BRIEF asks for a decision between BlackCEO-hosted and client-hosted Cloudflare. The answer
is a hybrid that is already the fleet's proven pattern: the app runs locally on the client
box (data locality keeps PII on the client's own machine) and is exposed through a
Cloudflare Tunnel on a hostname in BlackCEO's own Cloudflare zone
(`<client>.zerohumanworkforce.com`). Because BlackCEO owns the zone and the Access
policies, revocation is central and instant (Section 11.4), which is exactly the "central
benefit of BlackCEO hosting" SPEC `client_dashboard` calls out. No client-owned Cloudflare
configuration is required for the dashboard.

### D3. The engine is the ONLY writer; the dashboard is a strictly read-only consumer.

SPEC: "reflects live state without a separate data entry step." The engine writes every
state change through one writer module (Section 5.4). The dashboard opens the database
read-only. This is enforced mechanically, not by convention (better-sqlite3
`{ readonly: true, fileMustExist: true }`).

### D4. One SQLite database file per client box, separate from mission-control.db.

The podcast engine gets its own database file rather than tables inside
`mission-control.db`. Reasons: (a) the engine (an OpenClaw skill, shell plus Python) and
the Command Center (Node) have independent lifecycles and the engine must never be able to
corrupt Command Center state; (b) deletion-on-churn becomes "delete one file" (Section 10.4);
(c) the Command Center DB already has a WAL (Write-Ahead Logging) mtime gotcha in fleet
memory, and isolating the podcast writer keeps blast radius zero. Per-client isolation is
physical: each client box has its own file, so cross-client leakage is impossible by
construction.

### D5. Two view modes from one data source: client-clean and operator-verbose.

Fleet doctrine: move in silence, operator-verbose, never client-spam. The same records
power both a client-facing view (friendly labels, no internals) and an operator view
(costs, attempts, errors, model names, service names). Section 9 defines exactly which
fields appear where.

---

## 3. Naming and identifiers

- Skill name: Podcast Production Engine.
- Route group: `/podcast` (client view) and `/podcast/ops` (operator view).
- Database file: `podcast-engine.db`.
- Database location resolution (mirrors CC `src/lib/db/index.ts` conventions):
  1. `PODCAST_DB_PATH` environment variable (explicit override).
  2. Default: `~/.openclaw/podcast-engine/podcast-engine.db` on the client box.
  The Command Center reads the same resolved path; the onboarding wiring exports
  `PODCAST_DB_PATH` into both the engine environment and the Command Center environment so
  they can never disagree.
- File permissions: `0600`, owned by the OpenClaw runtime user. The directory is `0700`.

---

## 4. Visual design system (extracted from the Command Center, binding)

The podcast dashboard must be indistinguishable from the rest of the Command Center. The
build reuses the existing `tailwind.config.ts` and `globals.css` as-is (no forking, no new
config). Everything below is extracted from the live checkout and is the authoritative
token set the build consumes.

### 4.1 Foundation

- Framework: Next.js 14.2.21 App Router, React 18, Tailwind CSS 3.4.17, better-sqlite3
  ^12.10.0, lucide-react ^0.468.0 icons, `date-fns` for time formatting.
- Fonts: Inter (400 to 900) via `next/font/google` as `--font-inter`; JetBrains Mono as
  `--font-jetbrains-mono` for identifiers and timestamps. Body: 16px, line-height 1.6.
- Theme: LIGHT theme. Page background `#F8F9FB` (`bcc-bg`), surfaces `#FFFFFF`
  (`bcc-white`), borders `#E5E7EB` (`bcc-border`) and `#F3F4F6` (`bcc-border-light`).
- Text: primary `#1A1D26` (`bcc-text`), secondary `#6B7280` (`bcc-text-secondary`), muted
  `#9CA3AF` (`bcc-text-muted`).
- Brand: green scale `brand-50 #E8F5E9` through `brand-950 #0D3B13`, primary
  `#43A047` (`bcc-primary`), hover `#388E3C`. IMPORTANT: brand colors are driven by CSS
  variables (`--brand-*`, `--bcc-primary`) that the existing `<BrandTheme/>` component
  overrides per client at runtime. The podcast dashboard MUST use the Tailwind `brand-*`
  utilities and `--bcc-*` variables, never hard-coded greens, so each client's own brand
  color flows through automatically.
- Semantic colors: success `#10B981`, successLight `#D1FAE5`, warning `#F59E0B`,
  warningLight `#FEF3C7`, danger `#EF4444`, dangerLight `#FEE2E2`, info `#3B82F6`,
  infoLight `#DBEAFE`.

### 4.2 Typography scale (Tailwind fontSize extensions, use these names)

| Token | Size / weight | Use in this dashboard |
|---|---|---|
| `text-page-title` | 32px / 800 | "Podcast Studio" page heading |
| `text-section` | 24px / 700 | Section headings ("In production", "Published") |
| `text-card-title` | 20px / 700 | Episode card titles |
| `text-sub-heading` | 18px / 600 | Detail drawer section labels |
| `text-kpi-value` | 56px / 900 | KPI numbers on the overview row |
| `text-body` | 16px / 400 | Default copy |
| `text-label` | 14px / 500 | Field labels, table headers |
| `text-caption` | 14px / 400 | Helper text |
| `text-badge` | 14px / 500 | Stage pills |

Floor rule from `globals.css`: `text-xs` is globally overridden to 13px and is for badges
only; 12px exists only as `.timestamp-only` for timestamps in dense lists. Never go below.

### 4.3 Surfaces, radii, shadows, motion

- Cards: `bg-white rounded-2xl border border-gray-200 shadow-card p-4 sm:p-5` (16px radius).
  Hover cards add `card-hover` (translateY(-2px) plus `shadow-card-hover`) or the CEO board
  variant `transition-all hover:-translate-y-0.5 hover:shadow-lg`.
- Shadows: `shadow-card` `0 1px 3px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.04)`;
  `shadow-card-hover`; `shadow-pill` for floating pills.
- Radii: `rounded-xl` 12px, `rounded-2xl` 16px, `rounded-3xl` 24px.
- Loading: skeletons as `bg-gray-100 rounded-2xl animate-pulse` blocks; inline spinners as
  `<Loader2 className="h-5 w-5 animate-spin" />` with gray-500 text (CEODashboard pattern).
- Error blocks: `rounded-2xl border border-red-200 bg-red-50 px-4 py-5 text-sm text-red-700`.
- Empty states: dashed border pattern
  `rounded-2xl border border-dashed border-gray-200 bg-gray-50` with centered icon + copy.
- Entry animation: `.animate-slide-in` (0.2s ease-out) for drawers and toasts.

### 4.4 Navigation shell

Reuse the existing `Header.tsx` (h-14 top bar: logo, breadcrumb, SystemStatusPill,
mount-gated live clock) and the existing sidebar/nav conventions:

- Add one nav item: label "Podcast", route `/podcast`, icon `Mic` from lucide-react
  (`<Mic className="w-5 h-5" />`), placed after "Departments".
- Active nav state: `bg-brand-50 text-brand-700 border-l-[3px] border-brand-500`;
  inactive: `text-gray-600 hover:bg-gray-50` with transparent left border.
- Mobile (max-width 767px): existing mobile top bar plus 72px bottom padding for the
  bottom nav and `.safe-area-bottom` (env safe-area-inset).
- Operator view `/podcast/ops` appears in nav ONLY for operator sessions (Section 9.3).

### 4.5 Stage pill component (new, but composed from existing conventions)

Stage pills follow the Command Center priority-badge pattern: light tinted background plus
strong text of the same hue, `rounded-full px-2.5 py-0.5 text-badge` (visual match to
`.priority-*` classes and the kanban column pills). The exact stage color map is in
Section 7.2. Where a gradient header is needed (board column headers), reuse the
`.column-pill-*` 135deg gradient convention.

### 4.6 Horizontal scroll (pipeline board)

If the pipeline board scrolls horizontally on desktop, apply the existing `.kanban-scroll`
class plus `.kanban-fade-left` / `.kanban-fade-right` overlays and `.kanban-scroll-btn`
chevrons exactly as MissionQueue does. Do not invent a second scroll treatment.

---

## 5. THE PERSISTENCE LAYER (the gap this spec closes)

SPEC never defines a datastore. The engine currently has nowhere durable to record job
state, which also means the credit-out queue ("hold the job in a queue with all of its
input payload") and the 60-day age-out have no defined home. This section defines that
layer. The engine WRITES it at every pipeline step; the dashboard READS it. It is also the
engine's idempotency ledger and the queue's physical form.

### 5.1 Schema (SQLite, WAL mode, foreign_keys ON)

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ============================================================
-- podcast_jobs: one row per episode submission. THE core table.
-- Written only by the engine's writer module. Read-only to the dashboard.
-- ============================================================
CREATE TABLE IF NOT EXISTS podcast_jobs (
  job_id            TEXT PRIMARY KEY,          -- 'pj_' + 26-char ULID (sortable by time)
  client_id         TEXT NOT NULL,             -- client slug, matches Command Center company slug
  location_id       TEXT NOT NULL,             -- client's own GHL Location ID (input_payload_reference)
  contact_id        TEXT NOT NULL,             -- GHL contact record this episode belongs to
  submission_fingerprint TEXT NOT NULL,        -- sha256 of (contact_id + style + q1..qN answers), idempotency key

  -- What was submitted
  mode              TEXT NOT NULL CHECK (mode IN ('personal_podcast_style','interview_style_podcast')),
  style             TEXT NOT NULL CHECK (style IN ('counter_intuitive','vulnerable','provocative','passionate')),
  show_name         TEXT,                      -- Interview mode
  host_name         TEXT,                      -- Interview mode

  -- Submitter PII (Section 10 governs handling). Nullable so rows can be
  -- PII-scrubbed on churn/age-out while preserving the audit tombstone.
  submitter_first_name TEXT,
  submitter_last_name  TEXT,
  submitter_email      TEXT,
  submitter_phone      TEXT,

  -- Pipeline state
  status            TEXT NOT NULL DEFAULT 'received' CHECK (status IN (
                      'received','researching','writing','in_qc','generating_art',
                      'producing_audio','publishing','enrolling','complete',
                      'failed','queued_credit_out')),
  resume_stage      TEXT,                      -- stage to resume at when leaving the queue; NULL otherwise
  attempt_count     INTEGER NOT NULL DEFAULT 0, -- QC attempts; engine hard-stops at 3 (qc_protocol)
  failed_step       TEXT,                      -- machine step name when status='failed'
  last_error        TEXT,                      -- operator-only; sanitized, never contains secrets or PII

  -- Credit-out queue (credit_out_queue section of SPEC)
  queue_state       TEXT NOT NULL DEFAULT 'none' CHECK (queue_state IN
                      ('none','held','resumed','aged_out')),
  queued_at         TEXT,                      -- ISO 8601 UTC; set when queue_state -> 'held'
  queued_service    TEXT,                      -- 'kie_ai' | 'ollama_cloud' | 'openrouter' | 'fish_audio'
  queue_deadline    TEXT,                      -- queued_at + 60 days, precomputed for cheap queries
  aged_out_at       TEXT,                      -- set when the 60-day cap drops the job

  -- Cost + audit (operator-only surface)
  cost_accrued_usd  REAL NOT NULL DEFAULT 0,   -- running paid-API spend for this job
  writing_model     TEXT,                      -- model actually used (incl. substitutions per model_routing_policy)
  research_tool     TEXT,                      -- e.g. 'perplexity', 'builtin_web_search'

  -- Outputs (written as each step completes; power the client links panel)
  episode_title       TEXT,
  episode_description TEXT,
  episode_number      INTEGER,
  podbean_permalink   TEXT,                    -- -> contact.podcast_survey_episode_url
  episode_package_url TEXT,                    -- -> contact.finish_podcast_google_doc_link
  speech_script_url   TEXT,                    -- -> contact.podcast_transcript_link
  book_teaser_url     TEXT,                    -- Interview mode only -> contact.book_teaser
  mp3_media_url       TEXT,                    -- GHL media library URL
  cover_image_url     TEXT,                    -- GHL media library URL
  spoken_word_count   INTEGER,                 -- honest count, tags excluded (length_and_pacing)
  runtime_minutes     REAL,
  publish_timestamp   TEXT,                    -- scheduled publish if contact.date_for_release was future

  -- Timestamps
  created_at        TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
  completed_at      TEXT,
  pii_scrubbed_at   TEXT,                      -- set when PII columns are nulled (Section 10)

  UNIQUE (client_id, submission_fingerprint)   -- idempotency: same submission never runs twice
);

CREATE INDEX IF NOT EXISTS idx_pj_client_status  ON podcast_jobs(client_id, status);
CREATE INDEX IF NOT EXISTS idx_pj_queue          ON podcast_jobs(queue_state, queue_deadline)
  WHERE queue_state = 'held';
CREATE INDEX IF NOT EXISTS idx_pj_contact        ON podcast_jobs(contact_id);
CREATE INDEX IF NOT EXISTS idx_pj_created        ON podcast_jobs(client_id, created_at DESC);

-- ============================================================
-- podcast_job_events: append-only stage/audit timeline per job.
-- Powers the detail drawer timeline and the operator debug trail.
-- ============================================================
CREATE TABLE IF NOT EXISTS podcast_job_events (
  event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id      TEXT NOT NULL REFERENCES podcast_jobs(job_id) ON DELETE CASCADE,
  at          TEXT NOT NULL DEFAULT (datetime('now')),
  from_status TEXT,
  to_status   TEXT,
  note        TEXT,                            -- operator-only free text; sanitized, no secrets, no PII
  cost_delta_usd REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pje_job ON podcast_job_events(job_id, at);

-- ============================================================
-- podcast_job_payloads: the held input payload for queued jobs.
-- Separated from podcast_jobs so the PII-heavy raw payload can be
-- purged independently (age-out, churn) without touching job history.
-- ============================================================
CREATE TABLE IF NOT EXISTS podcast_job_payloads (
  job_id       TEXT PRIMARY KEY REFERENCES podcast_jobs(job_id) ON DELETE CASCADE,
  payload_json TEXT NOT NULL,                  -- full inbound webhook payload (input_payload_reference)
  partial_state_json TEXT,                     -- any work already completed, for resume-from-where-left-off
  stored_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================
-- podcast_dashboard_tokens: revocable client access tokens (Section 11).
-- Raw token values are NEVER stored; only sha256 hashes.
-- ============================================================
CREATE TABLE IF NOT EXISTS podcast_dashboard_tokens (
  token_id     TEXT PRIMARY KEY,               -- 'pdt_' + ULID
  client_id    TEXT NOT NULL,
  token_hash   TEXT NOT NULL UNIQUE,           -- sha256(hex) of the raw token
  label        TEXT,                           -- e.g. 'primary client access'
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),
  last_used_at TEXT,
  revoked_at   TEXT,                           -- non-NULL = dead, immediately
  revoked_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_pdt_client ON podcast_dashboard_tokens(client_id);

-- ============================================================
-- podcast_client_state: the engine-side kill switch (Section 11.4).
-- ============================================================
CREATE TABLE IF NOT EXISTS podcast_client_state (
  client_id   TEXT PRIMARY KEY,
  active      INTEGER NOT NULL DEFAULT 1,      -- 0 = churned: engine rejects new submissions,
                                               -- dashboard auth fails closed
  deactivated_at TEXT,
  note        TEXT
);
```

### 5.2 Status enum semantics (single source of truth)

`status` values map 1:1 onto SPEC's dashboard stage list ("received, researching, writing,
in QC, generating art, producing audio, publishing, enrolling, complete") plus the two
terminal/holding states the pipeline needs:

| status | Engine workflow steps (episode_construction_workflow) |
|---|---|
| `received` | Webhook ingested, Step 0/1 smoke test + ingest |
| `researching` | Step 3 Research Assistant stage |
| `writing` | Steps 2, 4 to 8 (engines, sizing, blueprint, draft, improvement, read-aloud) |
| `in_qc` | Step 9 QC protocol (increments `attempt_count` per failed attempt) |
| `generating_art` | Step 10 Kie.ai cover art + ffmpeg finalize |
| `producing_audio` | Step 11 Fish Audio MP3 |
| `publishing` | Steps 12 to 16 (documents, book teaser, media upload, Podbean, link-back) |
| `enrolling` | Step 17 Skill 44 workflow enrollment or Personal spreadsheet update |
| `complete` | Step 18 delivered. `completed_at` set. Terminal. |
| `failed` | Three-strike QC stop or unrecoverable publishing failure after retries; founder already alerted by the engine. Terminal unless the operator re-dispatches through the engine. |
| `queued_credit_out` | A paid service reported insufficient credits mid-run. `queue_state='held'`, `queued_at`, `queued_service`, `queue_deadline` set, `resume_stage` records where to resume. |

Legal transitions (the writer module enforces this matrix; anything else raises):

- Forward path: `received -> researching -> writing -> in_qc -> generating_art ->
  producing_audio -> publishing -> enrolling -> complete`.
- QC loop: `in_qc -> writing` (revision) up to 3 attempts, then `in_qc -> failed`.
- Any non-terminal stage `-> queued_credit_out`; on credit restore
  `queued_credit_out -> <resume_stage>` and `queue_state='resumed'`.
- 60-day cap: `queued_credit_out -> failed` with `queue_state='aged_out'`,
  `aged_out_at` set, payload purged, founder notified (SPEC credit_out_queue).
- Any stage `-> failed` on unrecoverable error after the engine's own retries.

### 5.3 Idempotency

The inbound webhook handler computes `submission_fingerprint` before creating a job. The
`UNIQUE (client_id, submission_fingerprint)` constraint makes duplicate webhook deliveries
a no-op (the writer catches the constraint violation, logs an event on the existing job,
and exits 0). `job_id` is a ULID so job listings sort chronologically without a join.

### 5.4 Writer contract (engine side)

One writer module, `scripts/podcast_state.py` (ships with the skill), is the ONLY code
that opens `podcast-engine.db` read-write. Every pipeline step calls it. This is a
BRIEF-mandated guardrail ("Python scripts needed to keep the skill from bypassing its own
process"). Subcommands the build must implement:

```
podcast_state.py create   --client-id --location-id --contact-id --mode --style \
                          --payload-file <json> [--show-name --host-name] \
                          [--first-name --last-name --email --phone]
podcast_state.py advance  --job-id --to <status> [--note ...] [--cost-delta 0.12]
podcast_state.py output   --job-id --field <output_column> --value <url|text|number>
podcast_state.py hold     --job-id --service <kie_ai|ollama_cloud|openrouter|fish_audio>
podcast_state.py resume   --job-id
podcast_state.py fail     --job-id --step <name> --error <sanitized text>
podcast_state.py sweep-aged-out          # cron daily alongside the credit smoke test:
                                         # drops >60d holds, purges payloads, alerts founder
podcast_state.py scrub-pii --job-id | --client-id   # Section 10
podcast_state.py token    mint|revoke|list --client-id ...   # Section 11
podcast_state.py deactivate-client --client-id --note ...    # Section 11.4
```

Rules baked into the writer: transition matrix enforcement, `updated_at` maintenance,
automatic `podcast_job_events` append on every change, `queue_deadline = queued_at + 60
days`, error strings passed through a redaction filter (strips anything matching key-like
patterns and email/phone shapes) before storage, and refusal to write when
`podcast_client_state.active = 0`.

### 5.5 Reader contract (dashboard side)

- The Command Center opens the DB with `new Database(PODCAST_DB_PATH, { readonly: true,
  fileMustExist: true })` in a new `src/lib/podcast/db.ts`. No schema creation, no
  migrations, no writes from the Next.js process, with ONE exception: token
  `last_used_at` touches and token minting/revocation, which go through a separate
  read-write handle used exclusively by the auth layer and the operator token screen
  (Section 11). Episode/job tables remain write-forbidden to the app.
- WAL note (fleet memory: WAL mtime lags): the dashboard must not use file mtime for
  freshness. Poll with a cheap `SELECT MAX(updated_at) FROM podcast_jobs` instead.
- If the DB file does not exist yet (client has never run the engine), the dashboard
  renders the empty state (Section 8.5), never an error.

---

## 6. Information architecture

```
/podcast                      Client view (token + Cloudflare gated)
  |- (overview)               KPI row + live pipeline of all submissions
  |- /episodes/[job_id]       Episode detail (drawer on desktop, page on mobile)
  '- /queue                   Credit-out queue view (client-clean framing: "On hold")

/podcast/ops                  Operator view (operator auth only; NOT in client nav)
  |- (overview)               Same pipeline + costs, attempts, errors, models
  |- /queue                   Queue with service names, deadlines, age-out ledger
  '- /access                  Dashboard tokens: mint, label, revoke; churn runbook launcher

/api/podcast/*                Read-only JSON (Section 13)
```

Breadcrumb (existing `Breadcrumb.tsx`): `Home / Podcast / <Episode title or job id>`.

---

## 7. Screen 1: Pipeline overview (`/podcast`)

### 7.1 Layout

Desktop (lg and up), top to bottom:

1. Page header row: `text-page-title` "Podcast Studio" + caption "Every episode, from
   submission to published." Right side: a live-updating "Updated <relative time>" caption
   (`.timestamp-only`, mount-gated like the Header clock to avoid hydration mismatch).
2. KPI row, 4 cards in `grid grid-cols-2 gap-4 lg:grid-cols-4` (CEODashboard grid):
   - "In production" (count of non-terminal, non-held jobs), icon `Activity`.
   - "Published" (status complete, all time; sub-caption "+N this month"), icon `CheckCircle2`.
   - "On hold" (queue_state held), icon `PauseCircle`, amber accent when > 0.
   - "Needs attention" (status failed; client-clean label, Section 9), icon `AlertTriangle`,
     red accent when > 0. Operator view swaps this card for "Spend this month" (sum of
     cost_accrued_usd), icon `DollarSign`.
   KPI card anatomy: white card, `text-label` gray-500 title, `text-kpi-value` number
   (scaled down to 40px on mobile via responsive class), caption delta line.
3. Episode pipeline: a stage-grouped LIST (default) with a board toggle.
   - List view (default): sections per active stage in pipeline order, each section headed
     by a stage pill + count, containing episode rows (Section 7.3). Complete episodes
     collapse into a "Published" section, newest first, paginated 25 at a time.
   - Board view (toggle, desktop only): kanban-style columns per stage using the
     `.kanban-scroll` conventions and `.column-pill-*` gradient headers. Cards are the
     compact variant of the episode row. No drag-and-drop, columns are display-only
     (guardrail: no pipeline mutation from the dashboard).
4. Filters (right of the section header, existing pill-button style): mode
   (All / Personal / Interview), style (4 styles), search by submitter name or episode
   title. Filtering is client-side over the fetched page.

### 7.2 Stage taxonomy: labels and colors (binding map)

Colors come from the existing palette so pills match the rest of the product. Client label
is what clients see; operator label is the raw status.

| status | Client label | Pill bg / text | Hex basis (existing token) |
|---|---|---|---|
| `received` | Received | blue-50 / blue-600 | `bcc-inbox #3B82F6` |
| `researching` | Researching | indigo-50 / indigo-600 | `bcc-planning #6366F1` |
| `writing` | Writing | emerald-50 / emerald-600 | `bcc-progress #10B981` |
| `in_qc` | Quality review | amber-50 / amber-600 | `bcc-review #F59E0B` |
| `generating_art` | Creating artwork | violet-50 / violet-600 | `bcc-assigned #8B5CF6` |
| `producing_audio` | Producing audio | cyan-50 / cyan-600 | `bcc-testing #06B6D4` |
| `publishing` | Publishing | brand-50 / brand-700 | `--brand-*` (client brand) |
| `enrolling` | Finalizing | teal-50 / teal-600 | `#0D9488` family |
| `complete` | Live | emerald-50 / emerald-700 + `CheckCircle2` | `bcc-done #059669` |
| `queued_credit_out` | On hold | orange-50 / orange-600 + `PauseCircle` | `bcc-high #EA580C` |
| `failed` | Needs attention | red-50 / red-600 + `AlertTriangle` | `bcc-important #DC2626` |
| aged_out (queue_state) | Expired | gray-100 / gray-600 + red ring `ring-1 ring-red-200` | `bcc-low #6B7280` |

A thin horizontal progress meter under each in-flight row shows pipeline position: 9
segments (received through complete), filled segments in `brand-500`, current segment
pulsing (`animate-pulse`), using the stage order above.

### 7.3 Episode row anatomy (list view)

White card row (`rounded-xl border border-gray-200 bg-white px-4 py-3`, hover
`hover:border-brand-300 hover:shadow-card`), grid columns on desktop:

1. Avatar: initials circle using the existing `.avatar-gradient-{1..5}` classes (index =
   hash of submitter name mod 5).
2. Identity block: `text-body` semibold "First Last"; `.timestamp-only` mono sub-line
   `email · phone` (client view shows these in full per SPEC client_dashboard: "first
   name, last name, email address, and phone number of each person who submitted").
3. Episode block: `text-label` episode title (or italic gray "Untitled, in progress"
   before Step 5 sets it); caption `Mode · Style` ("Interview · Provocative").
4. Stage pill (Section 7.2) + progress meter.
5. Timing: caption "Submitted <relative>" and, when complete, "Published <relative>".
6. Chevron to detail.

Operator view appends: `cost_accrued_usd` (mono, right-aligned), `attempt_count` as
"QC xN" badge (amber at 2, red at 3), `writing_model` caption, and on failed rows the
`failed_step` in red mono.

### 7.4 Real-time behavior

Polling, not websockets (matches Command Center norms and keeps the build simple):
`GET /api/podcast/jobs?since=<max updated_at>` every 15 seconds while the tab is visible
(pause on `document.hidden`). Rows animate in/update with `.animate-slide-in`. No sound,
no toasts to clients (move in silence); the operator view MAY toast on new failures.

---

## 8. Screen 2: Episode detail. Screen 3: Queue.

### 8.1 Episode detail (`/podcast/episodes/[job_id]`)

Desktop: right-side drawer (480px, `bg-white border-l border-gray-200 shadow-card-hover`,
slide-in). Mobile: full page. Content, top to bottom:

1. Header: cover art thumbnail (64px, `rounded-xl`, from `cover_image_url`, gray
   placeholder with `ImageIcon` until it exists), episode title (`text-card-title`),
   stage pill, submitter identity line.
2. "Your episode" links panel (only links whose columns are non-NULL appear, in this
   order): Listen on Podbean (`podbean_permalink`, primary button style
   `bg-brand-600 hover:bg-brand-700 text-white rounded-xl`), Episode Package
   (`episode_package_url`), Speech Script (`speech_script_url`), Book Teaser
   (`book_teaser_url`, Interview mode only, with a small "Bonus" brand badge), Cover image
   (`cover_image_url`), Audio file (`mp3_media_url`). Secondary links use the outline
   button style (`border border-gray-200 hover:border-brand-300 text-gray-700`).
   All external links `target="_blank" rel="noopener noreferrer"`.
3. Facts grid (2-col, `text-label` keys, `text-body` values): Mode, Style, Episode number,
   Runtime ("about N minutes" from `runtime_minutes`), Word count, Submitted, Published,
   Scheduled for (if `publish_timestamp` is future).
4. Timeline: vertical stepper fed by `podcast_job_events`. Client view shows stage
   transitions only, with friendly labels and relative times. Operator view also shows
   event notes, cost deltas, QC attempt markers, and hold/resume events with service names.
5. Hold banner (when queue_state = held): amber callout, client copy per Section 8.3.
6. Failed banner (client): red-50 callout: "This episode needs attention. Our team has
   been notified and is on it. Nothing is required from you." Never shows the error text.
   Operator variant shows `failed_step`, `last_error`, `attempt_count`.

### 8.2 Credit-out queue (`/podcast/queue`)

Purpose (SPEC credit_out_queue): nothing silently stalls; a held job is visible with its
age; past 60 days it is dropped and shown as aged out.

Layout: header caption explains the view. Then two groups:

1. ON HOLD (queue_state = held), sorted oldest first. Each row: episode identity (as in
   7.3), hold age ("Held for 12 days"), and an age meter: horizontal bar 0 to 60 days,
   segments colored green (< 30d), amber (30 to 45d), red (> 45d), with the numeric
   "N of 60 days" in mono. At >= 50 days the row gains a red left border
   (`border-l-[3px] border-red-500`) and the operator view shows "Ages out on <date>".
2. EXPIRED (queue_state = aged_out), collapsed by default, last 90 days: gray rows with the
   Expired pill, `aged_out_at` date, and client copy "This submission expired before it
   could be completed. Please resubmit when ready." (The founder was already notified by
   the engine at drop time; the payload has been purged, Section 10.3.)

Client view NEVER names the depleted service or says "credits". Operator view shows
`queued_service`, `queue_deadline`, `resume_stage`, and payload presence.

### 8.3 Client-facing hold copy (fixed strings, build verbatim)

- Row/pill: "On hold".
- Detail banner: "Production is briefly paused. Your episode is safe, nothing you
  submitted has been lost, and it will resume automatically. Held for {N} days."

### 8.4 Queue mechanics recap (engine-owned, dashboard-displayed)

Hold: writer `hold` sets status queued_credit_out, stores payload + partial state in
`podcast_job_payloads`. Resume: daily credit smoke test (SPEC daily_credit_smoke_test)
detects restored funds; engine calls `resume`, which returns the job to `resume_stage`.
Age-out: `sweep-aged-out` runs daily on the same cron; drops anything past
`queue_deadline`, purges its payload row, marks aged_out, alerts the founder. The
dashboard displays all of this and mutates none of it.

### 8.5 Empty, loading, error states (all screens)

- Empty (no jobs ever / no DB file): dashed-border block, `Mic` icon in a brand-50 circle,
  "No episodes yet. Your first submission will appear here the moment it arrives."
- Loading: 4 KPI skeletons + 5 row skeletons (`animate-pulse`).
- Fetch error: the standard red-50 error block with a Retry text button. Never renders a
  stack trace.

---

## 9. Client-clean vs operator-verbose (binding field matrix)

| Field | Client `/podcast` | Operator `/podcast/ops` |
|---|---|---|
| Submitter first/last/email/phone | YES (SPEC requires) | YES |
| Episode title, mode, style, stage, progress | YES (friendly labels) | YES (raw + friendly) |
| Output links (Podbean, docs, teaser, media) | YES | YES |
| Hold status + age + 60-day meter | YES ("On hold", no service name) | YES + service, deadline, resume_stage |
| Aged-out flag | YES ("Expired") | YES + drop ledger |
| `cost_accrued_usd`, cost deltas | NEVER | YES |
| `attempt_count`, QC attempt markers | NEVER | YES |
| `last_error`, `failed_step` | NEVER (generic banner) | YES (sanitized) |
| `writing_model`, `research_tool` | NEVER | YES |
| `queued_service` | NEVER | YES |
| Token management | NEVER | YES (`/podcast/ops/access`) |
| Any credential/secret/webhook URL | NEVER | NEVER (secrets never render anywhere) |

### 9.3 How the split is enforced

Not by hiding columns in the client, but at the API boundary: `/api/podcast/*` strips
operator-only fields unless the session is an operator session. Operator = Cloudflare
Access authenticated operator email (the `Cf-Access-Authenticated-User-Email` header the
existing middleware already surfaces) matching the box's operator allowlist, or a valid
`MC_API_TOKEN` bearer. Client dashboard tokens NEVER unlock operator fields. The React
components for the two views consume different serializer outputs, so a client bundle
never even receives verbose data.

---

## 10. PII isolation, retention, deletion-on-churn

PII here = submitter first/last name, email, phone, plus the raw intake payload (which
contains survey answers and consent language).

### 10.1 Isolation

1. Physical: one `podcast-engine.db` per client box. There is no fleet-central podcast
   PII store. Cross-client queries are impossible because other clients' data is on other
   machines. Never co-mingle clients (fleet doctrine).
2. Logical: every table still carries `client_id`, and every query in the dashboard is
   parameterized by the box's own client_id, so even a mis-copied database cannot leak
   into another client's view.
3. Transport: PII renders only behind the two auth layers (Section 11). API responses set
   `Cache-Control: no-store`. No PII in URLs (job_id only), no PII in logs (the writer's
   redaction filter also applies to the dashboard's server logs), no PII in error messages,
   no analytics/telemetry on these routes.
4. The intake payload (`podcast_job_payloads`) exists ONLY while a job is held or in
   flight; it is deleted on completion, on age-out, and on churn.

### 10.2 Retention (active client)

- Job rows and output links: kept indefinitely while the client is active; the published
  episode list IS the client's episode history and the Personal mode running-spreadsheet
  counterpart.
- `podcast_job_payloads`: deleted by the writer when a job reaches `complete` or `failed`
  (after founder notification captures what it needs), and at age-out.
- Aged-out and failed rows: PII columns are scrubbed (`scrub-pii`) 90 days after the
  terminal event; the row remains as a tombstone (counts, dates, stage history) with
  `pii_scrubbed_at` set. Events `note` fields for that job are cleared at the same time.

### 10.3 Age-out privacy

When `sweep-aged-out` fires: payload row purged immediately, founder alerted (engine
side), PII columns scrubbed after the 90-day tombstone window per 10.2.

### 10.4 Deletion-on-churn (runbook step, wired to Section 11.4)

When a client relationship ends, the churn runbook runs, in order:

1. `podcast_state.py deactivate-client` (engine stops accepting submissions; dashboard
   auth fails closed).
2. `podcast_state.py token revoke --client-id <id> --all` (all dashboard tokens dead).
3. Cloudflare revocation (Section 11.4) so the hostname stops resolving to the box.
4. After the contractual retention window (default 30 days, founder-configurable), delete
   `podcast-engine.db*` (db, -wal, -shm) from the box. Episode content already delivered
   into the client's own GoHighLevel and Podbean accounts is the client's property and is
   NOT touched (never touch client credentials or their own accounts, fleet doctrine).
5. Log the churn completion in the operator ledger (no PII in the log entry).

---

## 11. Auth and the revocable dashboard token

### 11.1 Two layers, matching the Command Center's existing posture

The existing `middleware.ts` pattern is reused and extended, fail-closed:

- Layer 1: Cloudflare Access on the `<client>.zerohumanworkforce.com` hostname (BlackCEO's
  zone). All page and API traffic must arrive with `Cf-Access-Jwt-Assertion` present.
  `/api/health` remains the only bypass.
- Layer 2: the podcast dashboard token, scoped to `/podcast` and `/api/podcast/*`.

### 11.2 Token design

- Format: `pdt_<client_slug>_<32 random hex chars>` (prefix makes accidental leaks
  greppable and identifiable, mirrors the `pit-` convention clients already know).
- Storage: sha256 hash only, in `podcast_dashboard_tokens` (Section 5.1). The raw value is
  shown exactly once at mint time on `/podcast/ops/access` and never persisted or logged.
- Presentation: the client visits `/podcast`, pastes the token once into a gate screen
  (card-styled, brand button); the app sets an HttpOnly, Secure, SameSite=Lax cookie
  containing a session reference (NOT the token) valid 30 days, re-validated against the
  token row on every request. Tokens never appear in URLs or query strings.
- Every successful use updates `last_used_at` (the one permitted dashboard write path,
  via the dedicated auth DB handle, Section 5.5).
- Validation order per request: Cloudflare header present -> client active
  (`podcast_client_state.active = 1`) -> token row exists, `revoked_at IS NULL` -> serve.
  Any failure = 401 with a clean branded "Access unavailable" page, no detail.

### 11.3 Operator access

Operators reach `/podcast/ops` via the existing operator auth (Cloudflare Access operator
email or `MC_API_TOKEN` bearer for scripts). `/podcast/ops/access` lists tokens
(token_id, label, created, last used, status), mints new ones, and revokes with a reason.
Revocation is a single UPDATE setting `revoked_at`; effect is immediate on the next
request (no cache of token validity).

### 11.4 Cloudflare revocation runbook tie-in

The dashboard's kill switch has three independent blades, executed by the churn runbook
(10.4) and individually usable:

1. Application blade: revoke all `podcast_dashboard_tokens` rows for the client and set
   `podcast_client_state.active = 0`. Dashboard and engine both fail closed even if
   Cloudflare were misconfigured.
2. Edge blade: via the Cloudflare API on BlackCEO's zone (fleet memory: the client public
   link lives in Cloudflare, manage via the Cloudflare API), disable or delete the
   client's Cloudflare Access application/policy for the hostname, then remove the tunnel
   ingress/DNS record. The hostname goes dark centrally, without touching the client box.
3. Engine blade: with `active = 0`, the inbound webhook handler answers new submissions
   with a polite rejection and does not create jobs.

The build must add these steps to the existing fleet Cloudflare revocation runbook
document rather than creating a competing runbook.

---

## 12. Responsive specification

Breakpoints: Tailwind defaults; the shell switches at `md` (768px) exactly like AppShell.

- Desktop (lg, 1024px+): sidebar shell (w-56, collapsible to w-16), KPI row 4-up, list or
  board view, detail as right drawer (480px). Board view available.
- Tablet (md, 768 to 1023): sidebar auto-collapsed to icons (w-16), KPI row 2x2
  (`grid-cols-2`), list view only (board toggle hidden), detail as right drawer at
  `min(480px, 85vw)`.
- Mobile (< 768): existing mobile top bar (h-14, hamburger) + bottom nav with 72px main
  padding and `.safe-area-bottom`. KPI row 2x2 with `text-kpi-value` scaled to 40px.
  Episode rows become stacked cards (avatar + name on line 1, title line 2, pill +
  progress line 3, timing line 4). Detail is a full page with a back breadcrumb. Queue age
  meter goes full-width. Filters collapse into a `Filter` icon sheet. All touch targets
  >= 44px. Tables are never horizontally scrolled on mobile; card layout instead (the
  page body must never scroll horizontally, matching `overflow-x: hidden` on body).

---

## 13. Read API contract (all read-only, all under the auth of Section 11)

```
GET /api/podcast/jobs?status=&mode=&style=&q=&cursor=&limit=25
  -> { jobs: [JobSummary], nextCursor, lastUpdatedAt }
GET /api/podcast/jobs/[job_id]
  -> { job: JobDetail, events: [Event] }
GET /api/podcast/queue
  -> { held: [QueueRow], agedOut: [QueueRow] }   // agedOut limited to last 90 days
GET /api/podcast/summary
  -> { inProduction, published, publishedThisMonth, held, failed,
       spendThisMonth? }                          // spend only in operator serialization
```

Serializer rule (Section 9.3): two serializers, `toClientJob()` and `toOperatorJob()`;
the client one whitelists fields (never blacklists), so new columns are private by
default. All responses `Cache-Control: no-store`. Errors are `{ error: string }` with
generic messages.

Token management (operator only, the sole write endpoints, guarded by operator auth +
same-origin):
```
POST   /api/podcast/ops/tokens            { label } -> { tokenId, rawTokenShownOnce }
DELETE /api/podcast/ops/tokens/[tokenId]  { reason } -> { revokedAt }
```

---

## 14. Accessibility and quality bar

- Stage is never conveyed by color alone: every pill carries its text label and
  distinct icon where specified (7.2).
- Contrast: all pill text/background pairs above meet WCAG AA on white (they are the
  existing priority-badge pairs, already in production).
- Progress meters carry `role="progressbar"` with `aria-valuenow/min/max`; the queue age
  meter announces "N of 60 days on hold".
- Drawer traps focus, closes on Escape, returns focus to the invoking row.
- Live-updating regions use `aria-live="polite"`.
- Relative times always have a `title` attribute with the absolute timestamp (mono,
  `.timestamp-only` styling in dense lists).
- Keyboard: rows are focusable links; the board view columns are reachable by tab and the
  scroll buttons are real buttons (existing `.kanban-scroll-btn`).

---

## 15. Acceptance criteria for the Fable build sub-agent

The dashboard build is DONE only when all of the following are independently verifiable:

1. Schema in Section 5.1 exists and is created/migrated ONLY by the engine's writer
   module; the Next.js app opens episode data `{ readonly: true }` and throws if asked to
   write episode tables.
2. `podcast_state.py` implements every subcommand in 5.4, enforces the transition matrix
   in 5.2, and refuses illegal transitions with a non-zero exit.
3. Duplicate webhook payload -> exactly one job row (idempotency proven by test).
4. A job driven through the full happy path by the writer shows correct stage pills,
   progress meter, timeline, and links panel at each step, in both view modes.
5. A held job shows age and the 60-day meter; a simulated 61-day hold is swept, shown as
   Expired, its payload row gone, and its PII scrub scheduled.
6. Client view renders NONE of the operator-only fields in Section 9's matrix (verify the
   serialized JSON, not just the UI).
7. Token mint/revoke round-trip works; a revoked token gets 401 on the very next request;
   `podcast_client_state.active = 0` blocks both dashboard auth and new engine jobs.
8. Cloudflare revocation steps are appended to the existing fleet revocation runbook.
9. Visual QA: side-by-side with the CEO Board, the podcast pages use the same shell,
   header, fonts, card treatments, pills, shadows, and brand variables; `<BrandTheme/>`
   recoloring flows through (test with a non-green client brand).
10. Responsive QA at 375px, 768px, 1280px per Section 12; no horizontal body scroll.
11. No secret, credential, token value, webhook URL, or internal error string renders on
    any client surface; grep the client bundle and serialized responses.
12. Empty, loading, and error states render per 8.5, including the no-DB-file case.
13. Zero em dash characters in any skill-produced output surface (BRIEF preserve rule);
    dashboard copy uses the fixed strings in 8.3 verbatim.
14. QC protocol scoring at or above 8.5 across the fleet's 10-category rubric before merge.

END OF DESIGN SPEC v1.0
