# GHL / Convert and Flow - Install Pages - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

Doctrine sentinels (ALL MUST appear verbatim in AGENTS.md + TOOLS.md after applying):
`GHL-AUTH-DOCTRINE: TOKEN-ONLY (D7) — refresh-token seed is the only auth path; NO auto UI-login / password / 2FA`
`GHL-AUTH-DOCTRINE: TIER-2 EMAIL-2FA FALLBACK — gated (auth+gmail-proven+email-2fa+creds), bounded, self-heals to TOKEN-ONLY`
`SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown, reaper backstop`

Sentinel: <!-- skill:06-ghl-install-pages:core-update-applied -->

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## GHL Page Deployment [PRIORITY: HIGH]
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/06-ghl-install-pages/ghl-browser-builder-full.md
- Engine: agent-browser (PRIMARY, headless, isolated `--session <client>`); Playwright is FALLBACK only and uses launchPersistentContext (NEVER launch()).
- SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown, reaper backstop.
  Route EVERY agent-browser call through the single mandatory gateway tools/browser_manager.sh (`bash tools/browser_manager.sh ensure` then `... eval|open|snapshot ...`). NEVER invoke agent-browser directly, NEVER invent a per-iteration session name (that leaked 22 orphan ~/.agent-browser/*.engine descriptors, 357M). The gateway owns the ONE canonical session (bm_session_name = ghl-skill6-<location-id>), the box-wide lock (lock=1), the lease, the per-call + per-session TTL, the pool ceiling, the circuit-breaker (PARKS a flaky build after AB_BREAKER_MAX opens — loud STOP via Rescue Rangers, parked NOT re-fired), and a guaranteed `trap _bm_teardown EXIT`. The host reaper scripts/agent-browser-reaper.sh (hourly cron, 13 * * * *) is the backstop for a hard crash (closes expired leases, doctor --fix, state clean, dead-descriptor sweep, scoped-Chromium tripwire — NEVER kills unrelated Chrome/Claude).
- GHL-AUTH-DOCTRINE: TOKEN-ONLY (D7) — refresh-token seed is the only auth path; NO auto UI-login / password / 2FA.
  Funnel/website/page builds authenticate by minting a Firebase id_token from GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN, reconstructing the SPA session (Firebase IndexedDB record + the six SPA cookies), then navigating straight into the dashboard. NO login form is rendered, NO password is typed, two-factor is NEVER reached.
  HARD RULE: NEVER ask for, type, or fall back to a GHL login/email/password or a two-factor (2FA) prompt for a page build. On token failure (no token / revoked / seed does not log in) the builder STOPS and reports — it does NOT auto-open the Sign-in form. Re-grab a fresh refresh token via the Convert and Flow Token Grabber Chrome extension, then retry the seed.
  GHL_AGENCY_EMAIL / GHL_AGENCY_PASSWORD are a DOCUMENTED, MANUAL last resort for a human operator ONLY — never auto-invoked by any agent or script.
- GHL-AUTH-DOCTRINE: TIER-2 EMAIL-2FA FALLBACK — gated (auth+gmail-proven+email-2fa+creds), bounded, self-heals to TOKEN-ONLY.
  The canonical auth entry point is the orchestrator tools/ghl_auth.py (a 3-tier ladder). Tier 1 (token-only, above) stays PRIMARY. Tier 2 is a GATED, audited, one-time email-2FA bootstrap that runs ONLY when there is no valid refresh token AND four gates pass (A recorded client authorization, B Gmail-access PROVEN by a live read BEFORE any login, C email is the selected 2FA method, D agency creds in the client store). On success it SELF-HEALS a fresh refresh token to the client store so the next run is Tier 1. Bounded (<=3 attempts, backoff, hard-stop on lockout/captcha). Any gate fail / lockout -> Tier 3: fail loud, non-zero exit, precise client instruction. ALL login/2FA code lives in tools/ghl_auth_fallback.py + tools/ghl_login_browser.py; CI guard scripts/guard-ghl-auth-fallback.sh.
- Always verify the correct sub-account before building (refuse on mismatch).
- Credentials: ~/.openclaw/secrets/.env — GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN (canonical; CLIENT key only). Never the operator's keys on a client box.
- Surveys + Forms are the SAME ONE GHL rail: tools/ghl_survey_builder.py (surveys) and tools/ghl_form_builder.py (forms). Two-layer split — a reasoning layer PRE-CREATES every custom field + tag via Skill 44 (`caf`, LOCATION PIT) with a `zhc_` marker + idempotent create-vs-reuse; a dumb browser operator runs the locked click list (a11y-ref-first selectors, visible-text fallback, explicit waits), captures the Copy-Embed-Code snippet, and splices it VERBATIM (no SRI) into the host page via the SKILL44_WIDGET→FORM path; tags attach on submit via a Skill-44 "Form Submitted → Add Contact Tag" workflow. Custom fields NEVER created on the fly in the browser. Per-build gate: qc-built-form.sh (render_check 200 + marker in the RENDERED DOM). Locked selectors: tools/SELECTORS-LIVE-{funnel,page,survey,form}.md.
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## GHL Page Builder (Browser Automation)
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/06-ghl-install-pages/ghl-browser-builder-full.md
- Engine: agent-browser PRIMARY (headless, isolated `--session <client>`, never a personal browser); Playwright FALLBACK only (launchPersistentContext, never launch()).
- SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown, reaper backstop.
  THE single mandatory gateway is tools/browser_manager.sh (shell) + tools/browser_manager.py (the python emitter analogue). Use it for EVERY agent-browser call:
  1. `bash tools/browser_manager.sh ensure` — circuit-breaker check → acquire the box-wide lock (flock if present, else atomic-mkdir; portable: flock is ABSENT on macOS) → write the lease → start the TTL self-kill timer → open the ONE canonical session → install `trap _bm_teardown EXIT INT TERM HUP`.
  2. `bash tools/browser_manager.sh eval|open|snapshot|wait|find|fill -- <args>` — thin lock-asserting pass-throughs (force `--headed false`, per-call timeout).
  3. `bash tools/browser_manager.sh run-detached -- <build-cmd>` — detach safely (the subtree owns lock+lease+TTL+trap, so detach-and-exit can never orphan).
  4. `SESSION="$(bash tools/browser_manager.sh session-name)"` or `python3 tools/ghl_builder.py browser-session` — print the canonical name.
  - The python emitters (ghl_builder.browser_cmd / ghl_rest_canvas.agent_browser_eval_cmd) REFUSE (exit 75) outside a `browser_manager.browser_session()` bracket, and every emitted plan ends with a mandatory close step (emit_teardown_step) so a detach-and-exit still tears down.
  - ADVISORY config (openclaw.json `browser.agentBrowser`, deep-merged by install.sh): {maxSessions:1, idleReapMin:60, maxOpensPerHour:12, maxChromeProcs:3, sessionTtlSec:1800}. ADVISORY-ONLY — agent-browser ignores it natively; the REAL cap lives in the manager + reaper (env-overridable: AB_MAX_SESSIONS, AB_SESSION_TTL, AB_CALL_TIMEOUT, AB_BREAKER_MAX, AB_MAX_LIVE, AB_HARD_AGE_MIN, AB_PROC_HARD_AGE_MIN). browser.headless:true is untouched.
  - Host reaper scripts/agent-browser-reaper.sh runs hourly (13 * * * *, wired by ensure-pipeline-crons.sh): closes expired leases, runs `agent-browser doctor --fix` + `state clean --older-than`, sweeps dead *.engine descriptors, and tripwires Chromium UNDER the agent-browser/Playwright profile tree ONLY (AB_REAPER_PLAYWRIGHT_DIR for the Playwright profile) — it NEVER kills a bare chrome/Chrome/Claude process. Run as the box user, NEVER root.
- GHL-AUTH-DOCTRINE: TOKEN-ONLY (D7) — refresh-token seed is the only auth path; NO auto UI-login / password / 2FA.
  How to authenticate a build:
  1. `python3 tools/seed-ghl-auth.py --print-seed --out /tmp/<sess>/seed.json` — mints a fresh Firebase id_token from GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN (env order: GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN → CAF_FIREBASE_REFRESH_TOKEN → GHL_FIREBASE_REFRESH_TOKEN) and emits the browser auth seed. NO password, NO 2FA.
  2. `bash tools/inject-ghl-auth.sh <sess> /tmp/<sess>/seed.json --pre-open` — seeds the Firebase IndexedDB User record, fetches /oauth/2/login/current in-browser (token-id header), reconstructs the six SPA cookies (cookie `a` is the authoritative logged-in signal), and activates via the SPA's own store/router. NEVER reload after seeding (the boot gate would sign the seeded session out).
  3. Build the funnel/website per the full guide; resolve each runtime gate (tools/gates.json) by live DOM snapshot — NEVER ship invented CSS.
  - On token failure (exit 2 = no token; exit 3 = revoked/expired) the builder STOPS and reports. It MUST NOT auto-open the Sign-in form or a two-factor prompt. Fix = re-grab a fresh refresh token via the Convert and Flow Token Grabber Chrome extension (44-convert-and-flow-operator/tools/chrome-extension/) from the CLIENT's own logged-in browser, update ~/.openclaw/secrets/.env, retry the seed.
  - GHL_AGENCY_EMAIL / GHL_AGENCY_PASSWORD = DOCUMENTED MANUAL last resort for a human operator only; NEVER auto-invoked by an agent or script. There is NO automatic UI-login / 2FA fallback for a normal build.
- GHL-AUTH-DOCTRINE: TIER-2 EMAIL-2FA FALLBACK — gated (auth+gmail-proven+email-2fa+creds), bounded, self-heals to TOKEN-ONLY.
  Canonical auth entry = orchestrator `python3 tools/ghl_auth.py --session <sess> --out /tmp/<sess>/seed.json` (3-tier ladder). It runs Tier 1 (the seed→inject above) and ONLY on token-absent/invalid evaluates the gated Tier-2 ladder: gate A authorization, gate B Gmail-access PROVEN by a live read BEFORE any login, gate C email-2FA selected, gate D agency creds in the client store. On success Tier 2 SELF-HEALS a fresh GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN into the client store so subsequent runs are Tier 1. Bounded (<=3 attempts, backoff, hard-stop on lockout/captcha). Any gate fail / lockout -> Tier 3 fail-loud (non-zero) with a precise client instruction. ALL login/2FA code is contained in tools/ghl_auth_fallback.py (+ helper tools/ghl_login_browser.py); locked by scripts/guard-ghl-auth-fallback.sh. Client uses their OWN creds/keys only; secrets NEVER in repo/logs/stdout.
- Viewport minimum: 1440x900. Builder loads inside nested iframes — use get_builder_frame().
- Default to Funnels over Websites. Every funnel/website/step name carries the `zhc` prefix.
- Verify every save/preview/publish with a payload marker string (not "no error"). NEVER publish without explicit approval. Generate a deployment report after every deployment.
- Survey builder `tools/ghl_survey_builder.py` + Form builder `tools/ghl_form_builder.py` share the rail. Reasoning layer pre-creates custom fields + tags via Skill 44 (`caf`, LOCATION PIT; `zhc_` key/tag marker, lowercase; container NAME carries UPPERCASE `ZHC `; idempotent GET-first reuse). Browser layer only DRAGS pre-created fields via **Add Object Fields** (never create-on-the-fly), then captures the embed snippet and splices it VERBATIM (no SRI) via SKILL44_WIDGET→FORM. `--dry-run` (default) + `--selftest` need no network/browser; live build gated by qc-built-form.sh (render_check 200 + marker in RENDERED DOM). Each builder names its locked selector doc: tools/SELECTORS-LIVE-{funnel,page,survey,form}.md.
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## GHL Page Deployment Skill - Installed [DATE]
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/06-ghl-install-pages/ghl-browser-builder-full.md
- GHL-AUTH-DOCTRINE: TOKEN-ONLY (D7) — refresh-token seed is the only auth path; NO auto UI-login / password / 2FA. Builds seed a logged-in session from GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN; on token failure STOP + re-grab via Token Grabber. NEVER fall back to GHL login/password/2FA.
- Covers: funnel creation, multi-page deploy, existing page updates, agent-browser engine, runtime snapshot-gates, sub-account gate, deployment reporting.
```

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

---

## USER.md - NO UPDATE NEEDED

---

## SOUL.md - NO UPDATE NEEDED
