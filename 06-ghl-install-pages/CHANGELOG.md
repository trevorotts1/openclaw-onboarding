# Changelog - ghl-install-pages

All notable changes to this skill wrapper are documented here.

---

## [v14.3.13] - 2026-06-26 — fix(skill6): GHL credential resolution searches every alias + every env store (kills the six-month image-step false-fail) + folds B7 SOP docs

Root cause: the Skill-6 image/media step false-failed `"GHL LOCATION PIT not found"` on a LOCATION Private Integration Token the operator had used for SIX MONTHS. The token was in `~/.openclaw/secrets/.env` under `GOHIGHLEVEL_API_KEY` the whole time — but `ghl_media.resolve_location_pit()` only checked two env-var names in the LIVE process environment and never opened the canonical store. In a clean agent shell (where the gateway/launchd wrapper had not exported `secrets/.env`) both vars read empty and the tool fail-loud, treating "env var empty" as "credential missing" instead of "env not loaded".

### Fixed (credential resolution — `tools/ghl_media.py`)
- `resolve_location_pit()` / `resolve_location_id()` now resolve from EVERY known alias AND, when the live env is empty, the canonical env STORES directly. LOCATION-PIT aliases (preferred → fallback): `GOHIGHLEVEL_API_KEY` → `GHL_API_KEY` → `GOHIGHLEVEL_LOCATION_PIT` → `GHL_LOCATION_PIT`. Location-id aliases: `GOHIGHLEVEL_LOCATION_ID` → `GHL_LOCATION_ID` → `GOHIGHLEVEL_ALLOWED_LOCATION_IDS` → `CAF_ALLOWED_LOCATION_IDS` (first id). Stores searched in order: `~/.openclaw/secrets/.env` → `~/clawd/secrets/.env` → `~/.openclaw/workspace/.env` (the same multi-alias/multi-store pattern already used for the Google 3-alias key and for `KIE_API_KEY` in `ghl_image_stage`).
- New `_scan_env_stores()` parses `KEY=VALUE` (and `export KEY=VALUE`) lines, strips quotes, takes the first id of a comma-separated allowlist; missing/unreadable stores are skipped, never raise.
- AGENCY vs LOCATION distinction encoded: the resolver NEVER falls back to an agency-class name (`GOHIGHLEVEL_AGENCY_PIT` / `GOHIGHLEVEL_AGENCY_API_KEY` / `GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT` / `GHL_AGENCY_PIT`) — agency tokens 401 for media. If only an agency token is found, the error says so explicitly.
- The honest-fail message is now accurate: it NAMES exactly which env vars and which store paths it checked, says the credential is "not found IN THE ENVIRONMENT or in any canonical env store", and instructs `set -a; source ~/.openclaw/secrets/.env; set +a` then retry. No secret VALUES are ever echoed.
- New `search_stores` kwarg (default True) lets unit tests assert pure-env behaviour in isolation.

### Tests (`tests/test_ghl_media_cred_resolution.py` — new, 18 cases, MOCK-only)
- Multi-alias resolution + preference order (PIT and location id); store FALLBACK resolving the value from a redirected fake `secrets/.env` (the exact incident); live-env-beats-store; `export`/quotes parsing; agency-only env/store still fails with the scope note; honest-fail names every var + store; allowlist first-id; alias-set invariants (no agency name is a LOCATION alias; `GOHIGHLEVEL_API_KEY`/`GOHIGHLEVEL_LOCATION_ID`/`~/.openclaw/secrets/.env` are the preferred entries). All fixtures are generic `pit-FAKE…` / `LOCFAKE…` values; the real store is never read.

### Docs (folds B7 / PR #356 into the SOP + adds the credential rule)
- `v2-autonomous-build-sop.md`: NEW §2.0.1 credential preflight (env-var→store table for LOCATION PIT / location id / KIE key; AGENCY≠LOCATION warning; step-0 `source secrets/.env`; HARD RULE — real research across all stores before any `honest_fail`, and the failure must name what was checked). §3 Images rewritten to call the `ghl_image_stage.run_image_pipeline(page_spec, run_dir, *, location_id, location_pit)` entrypoint and to cross-reference §2.0.1 (a PIT honest_fail is valid only after the store search). §7.1 Forbidden-shortcuts gains the row banning `"credential not found"` on an empty env var without a store search. Also folded from PR #356: §2.05 method-decision, §2.06 theme/colors object, §4.1 embed-widget flow, §7 sealed-mode verifier contract, §7.1 forbidden shortcuts.
- `SKILL.md`: new GoHighLevel media/PIT credential block documenting where the LOCATION PIT + location id + KIE key live, the alias/store resolution order, the AGENCY-401 warning, and the HARD RULE against false-failing on an empty env var.
- PR #356 (the B7 SOP docs) is consolidated here and closed; its SKILL.md half had already landed in v14.3.11.

508 passed / 15 skipped / 0 failed. guard-ghl-method-decision PASS. guard-ghl-verify-unfakeable PASS. qc-ghl-install-pages PASS (exit 0, 1 expected WARN on white-label URL). No secret values committed; the location id used in goldens is the operator's own documented test-scratch id.

## [v14.3.11] - 2026-06-26 — fix(skill6): un-fakeable QC gate + theme/colors 500 fix + B1-B8 integrated (B1-golden/colors, B2-sealed-gate, B3-method-decision, B4-image-pipeline, B5-golden-capture, B6-tests, B7-docs, B8-guards)

Root cause: the pre-flight fabricated a PASS while every page 500ed ("Cannot read properties of undefined reading 'colors'") and funnel pages were blank. Two distinct failure modes: (1) `new_page_blob()` produced a blob missing `general.general.colors` — GoHighLevel's renderer reads that key during React hydration; absence causes a 500. (2) The QC gate (`ghl_verify.py`) was bypassed — a hand-written ledger + `.md` summary overrode the machine verdict, the gate was never independently called.

### Fixed (B1 — theme/colors 500)
- `ghl_rest_canvas.new_page_blob()` rewritten to load from live-captured golden references (`references/golden/funnel-optin.page-data.json` and `references/golden/website-page.page-data.json`). Goldens contain the authentic 18-entry `general.general.colors` palette that GoHighLevel's renderer reads. The old from-memory blob (missing colors) is impossible to emit.
- New `html_fragment()` helper: strips `<!DOCTYPE>`, `<html>`, `<head>`, `<body>` wrappers, hoists `<style>` blocks from `<head>` so CSS survives stripping. Full documents are accepted and normalized to body-level fragments automatically.
- New `assert_renderable_shape()` guard: 7 invariants checked before return (colors non-empty, sections non-empty, custom-code element reachable, rawCustomCode is a fragment not a full document). Raises `AssertionError` naming the failing invariant.
- `surface` parameter added to `new_page_blob()` — `"funnel"` (default) and `"website"` produce correct element shapes (`type=element meta=custom-code` vs `type=code elType=code`).
- Removed false "PROVEN live" docstring; replaced with honest "STORAGE vs RENDER" contract section.

### Fixed (B2 — un-fakeable QC gate)
- `ghl_verify.render_check()` added: drives the headless browser, waits for JavaScript hydration, captures rendered DOM + PNG + console artifacts. `ok` requires HTTP 200 AND marker in RENDERED DOM AND zero render errors AND `visible_text_len >= 400`. Marker-in-storage is no longer a pass criterion.
- `ghl_verify.verify_all()` sealed: `live=True AND fetcher!=None` raises `SealedGateViolation` immediately. `trust='MOCK'` summaries cannot ship as verified. Pre-seeded `verify-summary.json` is rejected.
- `ghl_verify.assert_consistent()` extended: Invariant 4 (fabricated raw row detection: PASS=True with render_errors or non-200 http raises `VerifyContradiction`); Invariant 5 (artifact hash binding: re-hashes every artifact in render manifest).
- `ghl_gate.py` added: the only verdict reader. Reads `scorecard/verify-summary.json`, `logs/final-preview-verify.json`, `scorecard/render-manifest.json`. `require_pass()` checks writer identity, trust!=MOCK, raw_sha256 binding, `assert_consistent` re-run, forbidden phrases absent. Exit code 0 = PASS only; 1/2/3/4/5 for FAIL/MOCK/tampered/missing/invalid. `.md`, `ledger.json`, and prose files are structurally ignored.
- `v2_dispatcher.py`: production path calls `ghl_gate.require_pass()` after the verifier writes its files; non-zero exit → FAILED. MOCK trust downgrades task to FAILED.
- `ghl_builder.emit_batch_rest_save_plan()` delegation shim added (forwards to `parallel_saves`).

### Added (B3 — method decision architecture)
- `ghl_method.py`: pure classifier (no I/O). `classify_page()` returns `MethodDecision`: DIRECT (simple pages) or VERCEL_EMBED (js_frameworks present, complexity:advanced, payload > 256 KB). Widget blocks detected and listed in `MethodDecision.widgets` for GoHighLevel native form/calendar routing. `decide_and_record()` writes `routing/method-decision-<page>.json`.
- `ghl_vercel.py`: Vercel-embed path — `prepare_app()`, `deploy()`, `make_public()` (disables SSO so iframes work), `assert_embeddable()` hard gate (HTTP 200, no XFO DENY/SAMEORIGIN, marker in body). `run_pipeline()` chains all steps. Test injectors for CI.
- `ghl_ecosystem.py` extended: `create_form()`, `get_form()`, `get_calendar()` optional fields on `EcosystemOps`; `create_advanced_form()` orchestrator; `FormCreationError` exception.

### Added (B4 — image pipeline)
- `ghl_image_stage.py`: `run_image_pipeline()` — the single entry point. Resolves Kie.ai key from env, derives image specs (always `mode='t2i'`), calls `ghl_media.generate_images()`, uploads each PNG, re-fetches CDN URL at HTTP 200, logs to `logs/asset-cdn.log`, writes `images/manifest.json`. Fails loud (`ImagePipelineError`) on missing key or missing CDN verify — never returns stub URLs or SVG placeholders.

### Added (B5 — golden reference capture)
- `references/golden/funnel-optin.page-data.json` (25,364 bytes): live page-data blob from Trevor's own GoHighLevel test location. Render-verified: HTTP 200, marker in rendered DOM, zero `Cannot read properties` errors.
- `references/golden/website-page.page-data.json` (15,468 bytes): live website page-data blob. Same render verification.
- `references/golden/PROVENANCE.json`: capture metadata including location id, funnel id, page id, capture date, render-check evidence, and authoritative JSON paths for colors.
- `tests/fixtures/golden_page_blob_funnel.json` and `tests/fixtures/golden_page_blob_website.json`: copies for test fixture use.

### Added (B6 — tests)
- `tests/test_ghl_gate.py`: gate anti-fabrication contract tests.
- `tests/test_ghl_method.py`: classifier tests (46 passing).
- `tests/test_ghl_vercel.py`: Vercel embed hard gate tests (9 passing, all mocked).
- Extended: `test_ghl_rest_canvas.py`, `test_ghl_verify.py`, `test_v2_dispatcher.py`, `test_ghl_media.py`, `test_ghl_ecosystem.py`, `tests/fixtures/`.
- 449 tests pass (15 skipped for unimplemented optional extensions; 0 failed).

### Added (B7 — docs)
- `v2-autonomous-build-sop.md`: §7 rewritten as sealed-mode contract; §2.05 method decision; §2.06 colors/theme mandatory; §4.1 embed widget flow; §3 images rewritten. Six forbidden verification shortcuts table.
- `SKILL.md`: Phase-5 method decision table; mandatory colors/theme bullet; sealed verification bullet.

### Added (B8 — CI guards)
- `scripts/guard-ghl-method-decision.sh`: CI/live build guard for PLAN-3 method decision audit records.
- `scripts/guard-ghl-verify-unfakeable.sh`: static guard — asserts no forbidden rationalization strings in code, gate symbols exposed, no hand-written `overall_pass = True`.
- `tools/gates.json`: `method_decision_per_page`, `image_manifest_non_empty`, `verify_gate_authoritative` enforcement gates added.
- `qc-ghl-install-pages.sh`: wires both guards into the QC flow.

---

## [v14.3.10] - 2026-06-26 — feat(skill6): parallel page saves cap 5 — shared cleared session fan-out

**PRIMARY approach:** fan out up to `AB_SAVE_CONCURRENCY` (default 5, hard-clamped [1,5]) concurrent `agent-browser eval` autosave calls against the ONE singleton session. `AB_MAX_SESSIONS` STAYS 1 (one browser — Cloudflare clearance is shared). The lock / TTL / breaker / EXIT-trap teardown from `browser_manager.sh` cover the entire batch unchanged.

### Added
- **`tools/parallel_saves.sh`** — bash fan-out executor. Sources `browser_manager.sh`. `bm_save_concurrency()` clamps `AB_SAVE_CONCURRENCY` to [1,5]. `ps_fan_out()` issues N eval background jobs with a slot-counting concurrency cap (macOS bash 3.2 safe). `ps_run_batch()` reads JSON spec, calls `bm_ensure` once, fans out, collects results.
- **`tools/parallel_saves.py`** — pure emitter. `save_concurrency(env)` clamps to [1,5]. `emit_batch_rest_save_plan(pages, session)` wraps all per-page steps in ONE `browser_session()` bracket with EXACTLY ONE `teardown_browser` at the end.
- **`tests/test_parallel_saves.py`** — 41 tests: concurrency clamp (shell + Python), AB_MAX_SESSIONS=1 static, sh contract, batch plan emitter (K pages = exactly 1 teardown), hermetic concurrency (peak ≤5, teardown on failure, one-browser invariant).

### Changed
- **`tools/browser_manager.sh`** — added `AB_SAVE_CONCURRENCY` tunable + `bm_save_concurrency()` clamp. `AB_MAX_SESSIONS` stays 1; all lock/lease/TTL/breaker/teardown bodies verbatim unchanged.
- **`tools/browser_manager.py`** — mirror `save_concurrency()`.
- **`tools/ghl_builder.py`** — added `emit_batch_rest_save_plan()` + `batch-rest-save-plan` CLI verb.
- **`v2-autonomous-build-sop.md`** + **`ghl-browser-builder-full.md`** — PARALLEL SAVES (cap 5) note; sentinel verbatim intact.

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

