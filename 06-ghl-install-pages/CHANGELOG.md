# Changelog - ghl-install-pages

All notable changes to this skill wrapper are documented here.

---

## [v14.3.8] - 2026-06-26 — feat(skill6): cc_board.py producer + INTAKE SOP section — Goal A (card on board)

Closes Goal A of the Skill-6 → Kanban demo path: a customer funnel/website request now becomes a real card on the Command Center Kanban board.

### Added

**`tools/cc_board.py`** — new file. Fail-soft board card producer for the Funnels / Web-Dev dept agent. Modeled on `48-facebook-ad-generator/scripts/cc_board.py`. Posts one card to `POST /api/tasks/ingest` (CC >= v4.52.0). Key design decisions:
- **Fail-soft everywhere** — `ingest_task()` catches all exceptions and returns `None`. The build never stops because the board is unreachable.
- **Single public function `ingest_task()`** — accepts `title`, `description`, `job_type`, `priority`, `idempotency_key`. Maps `job_type` to `department_slug` (`funnel`/`sales-funnel`/`opt-in`/`multistep` → `funnels`; everything else → `web-development`). Posts `title`, `description`, `source`, `department_slug`, `idempotency_key`, `priority` to the ingest route.
- **Auth parity with Skill-48**: `Authorization: Bearer <MC_API_TOKEN>` (global middleware) + `x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody)` (per-route). Both no-ops when unset.
- **Stdlib only** (`urllib`, `hashlib`, `hmac`, `uuid`) — zero third-party deps.
- **`--selftest` flag** (no network; exits 0 on pass — verified).
- **`--demo` flag** for live board proof.

**`v2-autonomous-build-sop.md` — INTAKE section added** (77 lines before `## 0`). Documents the `ingest_task()` call the dept agent MUST make before any gate (P0/P1/P2) or build step, the `job_type` → `department_slug` routing table, the exact JSON payload, credential env vars, selftest/demo CLI usage, and how to write the returned `task_id` to `routing/intake-receipt.json` for downstream steps. Scope note explicitly states this lands Goal A but NOT Goal D (dispatch trigger — that remains `v2_dispatcher.py`, a follow-on).

Selftest: `python3 06-ghl-install-pages/tools/cc_board.py --selftest` exits 0.

**Scope boundary (honest):** Goal A (card created on board) + Goal B routing (server-side `routeTask()` picks the right workspace when `department_slug` is supplied) are covered. Goal C (status moves Backlog → In Progress → Review → Done) depends on the CC dispatcher having a live dept runtime; that is the `~/.openclaw/agents/dept-funnels/` wire-in — separate operator step. Goal D (dispatch message triggers the Skill-6 build recipe) is a follow-on (`v2_dispatcher.py` exists; board dispatch message does not yet call it).

## [v14.1.5] - 2026-06-25 — fix(breaker): DURABLE park marker (survives reboot) + writes the box-level PARK marker on a trip

The agent-browser circuit-breaker's PARK marker no longer lives in TMPDIR (it evaporated on reboot, silently un-parking a qc-failed build). `tools/browser_manager.sh` now keeps the breaker counter + BLOCKED marker AND a canonical box-level PARK marker under the box's DURABLE state dir (`<openclaw-root>/workspace/.park/`); the lock + leases correctly stay ephemeral. `bm_breaker_check` reads the box-level marker too, and a breaker trip WRITES it so the Skill-23 `*/15` resume cron (`resume-workforce-build.sh`) stops re-firing as well. Un-park is operator-only (`scripts/unpark-build.sh`). Falls back to the old ephemeral path when no onboarded root exists, so the 31 singleton tests stay hermetic. See root CHANGELOG v14.1.5.

## [v7.2.9] - June 23, 2026 — SINGLETON POOLED BROWSER (one session, lock=1, TTL, guaranteed teardown, reaper backstop)

### Added
- **`tools/browser_manager.sh`** — THE single mandatory agent-browser gateway. Owns AB_BIN + the lock-asserting `AB()` wrapper (D6 headless guard re-used verbatim), ONE canonical session (`bm_session_name` = `ghl-skill6-<location-id>`, refuses non-canonical unless `AB_SESSION_OVERRIDE=1`), a portable box-wide lock (flock if present, else atomic-mkdir with dead-PID stale reclaim — flock is ABSENT on macOS), a lease (process+mtime liveness, never `.pid`), per-call (`AB_CALL_TIMEOUT`) + per-session (`AB_SESSION_TTL`) timeouts, a pool ceiling (`AB_MAX_SESSIONS`, default 1), a circuit-breaker (`AB_BREAKER_MAX` opens/window → PARK qc-failed + escalate to Rescue Rangers, parked NOT re-fired), and a GUARANTEED `trap _bm_teardown EXIT INT TERM HUP` that closes ONLY the canonical session + `state clear`. Verbs: ensure / eval|open|snapshot|wait|find|fill / run-detached / teardown / session-name.
- **`tools/browser_manager.py`** — emitter-side analogue: `browser_session()` context (atexit + SIGTERM/SIGINT/SIGHUP), `assert_session_active()`, `session_name()` (matches the shell), `emit_teardown_step()`.
- **`scripts/agent-browser-reaper.sh`** — host reaper (hourly cron, `13 * * * *`, via ensure-pipeline-crons.sh): closes expired-lease sessions, `doctor --fix` + `state clean --older-than`, dead-descriptor sweep, and a Chromium tripwire scoped to the agent-browser/Playwright PROFILE TREE ONLY (NEVER a bare chrome/Chrome/Claude proc). Runs as the box user, never root.
- **`scripts/guard-agent-browser-managed.sh`** + **`tests/test_browser_manager_singleton.py`** (24 static/stubbed tests) + **CI** `.github/workflows/agent-browser-lifecycle-guard.yml` + **pre-commit gate 6**.

### Changed
- **`tools/inject-ghl-auth.sh`** now `source`s the gateway and calls `bm_ensure` before the first open, so its 4 non-zero REFUSE aborts ALWAYS tear down via the inherited EXIT trap — closing the orphan gap (verified live: 22 `~/.agent-browser/*.engine`, 357M, on the operator box). D6 guard + D7 token-only auth model BYTE-FOR-BYTE unchanged.
- **`tools/ghl_builder.py`** / **`tools/ghl_rest_canvas.py`** emitters refuse outside a `browser_session()` bracket (exit 75 / RuntimeError); every emitted plan ends with a mandatory close step. New `browser-session` CLI verb.

## [v7.2.3] - June 21, 2026 — VERSION RECONCILIATION (all three markers aligned)

### Changed
- Reconciled all three Skill-06 version markers to **v7.2.3** (skill-version.txt + SKILL.md frontmatter + this CHANGELOG) so they agree — closes the A7 mismatch the Goal-B independent verifier flagged (skill-version was v7.2.2 while frontmatter/CHANGELOG still said 7.2.1).

## [v7.2.1] - June 21, 2026 — VERSION RECONCILIATION

### Changed
- SKILL.md frontmatter `version` updated to `7.2.1` to match skill-version.txt.
- `qc-built-workflow.sh` (Skill 44): WF-4, WF-5, and WF-6 assertions that previously
  called `record_pass` when the observed value was `unknown` now call `record_human`
  (REQUIRES_HUMAN_REVIEW), ensuring unknown export fields never silently count as passes.

---

## [v7.2.0] - June 21, 2026 — TOKEN-ONLY AUTH SEED (no UI login, no 2FA)

The Firebase refresh token alone now produces a logged-in SPA session. Fixed the
root cause of the old `auth/internal-error` (the seeded IndexedDB record omitted
the SDK-asserted boolean fields, so the Firebase Web SDK threw on rehydrate and
bounced the SPA to the login form), and removed every automatic fall-back to the
UI login form / two-factor.

### Fixed — IndexedDB user record now matches the Firebase Web SDK `User` shape
- `tools/seed-ghl-auth.py` `build_seed()`: emits the FULL Firebase Web SDK
  `User._fromJSON()` record under
  `firebase:authUser:AIzaSyB_w3vXmsI7WeQtrIOkjR6xTRVN5uOieiE:[DEFAULT]`
  (`firebaseLocalStorageDb` → `firebaseLocalStorage`, keyPath `fbase_key`). The
  value now ALWAYS includes `emailVerified:false` + `isAnonymous:false` (the SDK
  asserts both as booleans — omitting them was the `auth/internal-error` root
  cause), `providerData:[]` (correct for a custom-token sign-in), full
  `stsTokenManager{refreshToken, accessToken, expirationTime(epoch MILLIS)}`,
  `createdAt`/`lastLoginAt` as epoch-ms STRINGS, `uid` from the live securetoken
  response, plus `apiKey`/`appName`. `email`/`displayName`/`photoURL` are OMITTED
  (custom-auth user has none; null would fail the SDK's string|undefined
  assertion). Refuses to emit a half-record (missing id_token / refresh_token /
  uid raises). No app-token minted and no session cookie required — the id_token
  validates directly via the `token-id` header.

### Fixed — NO automatic UI-login / two-factor fallback (HARD RULE)
- Token-seed is now the ONLY auto-invoked auth path across
  `seed-ghl-auth.py`, `inject-ghl-auth.sh`, `gates.json` #27, and
  `ghl-browser-builder-full.md` (§2, §2.1, §2.2, A0.1, A1, D6/STATUS callouts,
  edge-case recap). If seeding fails to log the SPA in, the builder STOPS and
  reports (non-zero exit). It NEVER auto-fills the Sign-in form or triggers
  two-factor. `GHL_AGENCY_EMAIL`/`GHL_AGENCY_PASSWORD` is retained as a
  DOCUMENTED, operator-only MANUAL last resort, never auto-invoked.
- `tools/inject-ghl-auth.sh`: validates the seed (required boolean fields +
  tokens) and FAILS LOUD before writing; reads the record back after the write
  and aborts non-zero if it did not persist; aborts non-zero if the injector
  returns anything but `seeded:<key>`. The v13.2.4 D6 headless guard is intact
  (`unset`/`export AGENT_BROWSER_HEADED=false`, `AB() --headed false`, abort
  exit 75 on a surviving headed signal).
- `seed-ghl-auth.py --check`: reports `none` (not `login-form`) when no refresh
  token exists, with `manual_login_creds_present` as informational only; exits 2
  so the builder STOPS rather than treating a UI login as an available path.

### Changed — `tools/gates.json` gate #27 (auth_storage_keys)
- Records the confirmed `fbase_key`, the full `value_shape`, the four
  `required_value_fields` (`uid`, `stsTokenManager`, `emailVerified`,
  `isAnonymous`), `app_token_required:false`, `session_cookie_required:false`,
  and the `token-id` auth header; note now states token-seed is the ONLY auth
  path (no UI/2FA fallback).

### Not touched
- Skill 44's `safety_gate` / `VERIFIED_ACTIONS` / `link_steps` were not modified.
  The refresh→ID exchange is re-implemented read-only in `seed-ghl-auth.py` (not
  imported from Skill 44). No client names committed.

---

## [v7.1.0] - June 21, 2026 — HEADLESS HARD-GUARD + REAL UI MAP (repo v13.2.4)

A live run opened a VISIBLE browser window on the operator's screen. agent-browser
is headless by default, but the launch did not ENFORCE it — an inherited
`AGENT_BROWSER_HEADED` env var or a `{"headed": true}` config file can silently
force a headed window. This release closes that door permanently and wires the
real GoHighLevel UI labels from 15 live screenshots.

### Fixed — D6 HARD HEADLESS GUARD (priority)
- `tools/inject-ghl-auth.sh`: forces headless on EVERY agent-browser call —
  `unset AGENT_BROWSER_HEADED` + `export AGENT_BROWSER_HEADED=false`, an `AB()`
  wrapper that appends `--headed false` (the documented agent-browser 0.27.0
  override that also disables a config-file `"headed": true`), and a guard/assert
  that REFUSES to proceed (exit 75) if a headed signal survives. Loud comment:
  "HEADLESS-ONLY — never open a visible window; taking over a screen is forbidden
  (esp. client boxes)."
- `tools/ghl_builder.py`: adds `headed_is_forced()`, `headless_guard()` (raises),
  `browser_cmd()` (emits headless-forced `--headed false` lines), and CLI
  subcommands `headless-guard` (exit 75 if headed would open) + `browser-cmd`.
- Docs (`ghl-browser-builder-full.md` v3.0, `INSTALL.md`, legacy
  `ghl-install-pages-full.md` v2.0): every documented browser invocation is now
  headless-forced; the old `--headed` / `headless=False` two-factor and "keep the
  browser visible" exceptions are REMOVED — no path (login, two-factor,
  Playwright fallback) may open a window. A blocked two-factor PAUSES + screenshots
  + surfaces to the operator instead.

### Confirmed — D7 token-seed-into-IndexedDB is the DEFAULT (no UI login)
- `seed-ghl-auth.py` + `inject-ghl-auth.sh` seed the Firebase ID/refresh token
  straight into IndexedDB (`firebaseLocalStorageDb` → `firebaseLocalStorage` →
  `fbase_key` → `value.stsTokenManager`) and navigate straight in — NO login form
  is rendered (the form was the temptation for the visible window). Documented:
  UI login is the LAST-RESORT fallback ONLY, and still headless.

### Added — D8 real UI map wired into `tools/gates.json`
- Replaced the placeholder/heuristic `find` hints with the REAL visible labels +
  sequence from the operator's 15 live screenshots (`Downloads/ghl-ui-map.md`): Sites
  (left) → Funnels top-tab → "+ New funnel" → "Create new funnel" modal ("From
  blank" + name + Create) → "+ Add new step or import" → "New step in funnel"
  modal ("Name for page" + Path → "Create funnel step") → step CONTROL box ("Use
  existing"/"Create from blank", Edit dropdown = edit path) → close "Ask AI" X →
  "Blank Section" → "+ Add" → Quick Add → "Custom" group → "Code" → "Custom Code"
  → "Open Code Editor" → "Custom Javascript/HTML" modal → paste → Save →
  "Allow Rows to take entire width" → eye=Preview / disk=Save / blue "Publish".
- Each gate now carries `label` + `label_source` (screenshot-confirmed-label vs
  still-runtime-snapshot). **20 of 28 gates carry screenshot-confirmed labels.**
- Recorded `_env`: BlackCEO LLC location id `FIXTURE0LOCATION0000`, preview
  domain `<PREVIEW_DOMAIN>`, Websites mirrors Funnels.
- NO invented CSS: labels are visible-text/role targets the agent confirms at
  runtime; the runtime @ref capture is unchanged.

---

## [v7.0.0] - June 21, 2026 — BROWSER-BUILDER OVERHAUL (Part 2)

### Changed (BREAKING for internal procedure, not for slot/ID/install)
- **Engine realigned to Skill 03**: agent-browser (Vercel Labs) is now PRIMARY
  (headless, isolated `--session`), Playwright is FALLBACK only. The previous
  raw-Playwright-only stack is superseded. New hardened reference
  `ghl-browser-builder-full.md` (v3.0); legacy `ghl-install-pages-full.md` (v2.0)
  retained for historical click-path detail.

### Added
- `tools/seed-ghl-auth.py` (D7) — reuses Skill 44's Firebase refresh→ID-token
  exchange (read-only re-implementation; does not modify Skill 44) and emits a
  browser auth seed. Mints from GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN /
  CAF_FIREBASE_REFRESH_TOKEN / GHL_FIREBASE_REFRESH_TOKEN. Detects revoked
  tokens (exit 3) and absent tokens (exit 2 → login fallback).
- `tools/inject-ghl-auth.sh` (D7) — writes the seed into the browser's
  **IndexedDB** (`firebaseLocalStorageDb` → `firebaseLocalStorage`, keyPath
  `fbase_key`, `stsTokenManager` shape). Corrects the spec's localStorage
  assumption per the 2026-06-21 live capture.
- `tools/gates.json` (D8) — 28-gate runtime contract. 2 CAPTURED (login form +
  auth storage), 26 RUNTIME snapshot-gates (no invented CSS shipped as fact).
- `tools/ghl_builder.py` — manifest, per-page ledger + resume (D10/D12), ZHC
  prefix enforcement, hard sub-account match gate, never-publish-without-approval
  guard, marker-string URL verification, runtime-gate loader.
- Full funnel flow + website flow + Mode-2 iframe-embed path + edge-case handlers
  (two-factor pause, nested iframe, AI-popup dismiss, code-too-large→embed,
  X-Frame-Options, duplicate names, save races).

### Corrections applied from the live-capture pass (2026-06-21)
- Login form renders at root `https://app.convertandflow.com/`, NOT `/login`.
- Auth is in IndexedDB, NOT localStorage.
- Real fallback cred vars are GHL_AGENCY_EMAIL / GHL_AGENCY_PASSWORD.
- FIREBASE_API_KEY is hardcoded in Skill 44 transport.py (not an env var).
- agent-browser 0.27.0 auto-inlines iframes (handles the nested-editor boundary).

### PENDING-LIVE-RUN (NOT claimed done)
- D8 first clause: the 26 runtime gates were BLOCKED behind two-factor
  authentication in the capture pass; they remain runtime snapshot-gates until a
  fresh capture flips them to `captured`.
- D9–D13: end-to-end funnel/website live test, Mode-2 embed test, Website path,
  multi-page resume, and publish-with-approval are NOT yet run — blocked on a
  fresh Firebase refresh token or an attended two-factor-authentication run.

---

## [v1.5.0] - March 7, 2026

### Changed
- Converted INSTALL.md to agent-executable, autonomous execution format.
- Ensured TYP guardrails are present: MANDATORY TYP CHECK, CONFLICT RULE, and TYP file storage instructions.

