---
name: ghl-install-pages
description: >
  How to deploy HTML pages into GoHighLevel (Go High Level) or Convert and Flow
  using browser automation. This skill teaches the AI agent how to use
  agent-browser (Vercel Labs, Skill 03) as the primary engine — Playwright as a
  fallback — to start a session already logged-in via a seeded Firebase token,
  navigate the funnel/website page builder, paste code, save, preview, and
  publish-with-approval, all without the human touching the builder.
metadata:
  
  version: "7.2.9"
  priority: HIGH
---

# GoHighLevel / Convert and Flow - Install Pages (Browser Builder)

This skill is about deploying finished HTML code into the GoHighLevel (Go High
Level) or Convert and Flow page builder using browser automation. The AI agent
drives the browser, pastes the code, and handles all the clicks and navigation.

> **ENGINE (v3.0 overhaul):** PRIMARY = `agent-browser` (Vercel Labs, the
> repo-sanctioned tool from Skill 03), run **headless** with an **isolated
> `--session <client>`** so it never touches a personal browser. FALLBACK =
> self-hosted Playwright, a scripted escape hatch for known-hard flows only.
> The previous raw-Playwright-only stack is replaced. The full hardened
> procedure is in `ghl-browser-builder-full.md` (v3.0).

> **STATUS — PENDING-LIVE-RUN.** The login-form DOM (gate #1, used ONLY to DETECT
> a failed seed and STOP — never to log in) and the auth-storage schema (gate #27)
> are LIVE-CAPTURED. The other 26 in-app controls are **runtime snapshot-gates**
> (`tools/gates.json`): the agent snapshots the live DOM and picks the ref at
> runtime — NO invented CSS is shipped as fact. The end-to-end funnel/website
> live test is NOT yet claimed (blocked ONLY on a fresh Firebase refresh token —
> the token-seed is the sole auth path; there is NO login-form / two-factor run,
> attended or otherwise, per the TOKEN-ONLY doctrine in §2/D7).

This is NOT about writing or designing the HTML. The HTML is already done
(usually from a SuperDesign export). This skill is purely about getting that
code into GHL so the page goes live.

## Funnel Template Library (STEP 0 — template-first / reuse-before-reinvent)

This skill ships a **38-template funnel library** at `06-ghl-install-pages/funnel-templates/`
(categories: buyer, event, lead, retention-followup, traffic-advanced). Each template encodes a
proven Brunson-derived `pageStructure`, `copyFramework`, `skill44Widgets`, persona/`books`, and
`whenToUse`/`doNotUseWhen`. **STEP 0 of every build** runs `tools/funnel_matcher.py` (wired into
`tools/v2_dispatcher.py` via `_resolve_step0`; env-gated on `GHL_FUNNEL_CATALOG`/`GHL_FUNNEL_INDEX`,
**never blocks** a build) to match the best-fit template and attach its `pageStructure` + persona
to the task. Flexibility is **guide-not-rule**: an explicit owner choice is HONORED (template is an
optional reference); CREATE_NEW only when nothing fits. The matcher also stamps
`task['funnel_template_id']` and attaches the recommended `linked_automations` from
`44-.../automation-templates/_links/funnel-to-automation.json` for the complete-funnel handoff to
Skill 44. CLI: `python3 tools/funnel_matcher_cli.py --match "<offer summary>" --json`
(`--build-index` rebuilds the committed `tools/catalog-index.json`). See
`funnel-templates/README.md` and `v2-autonomous-build-sop.md` "P0.5 / STEP 0". Every built funnel
is held to the FAB-QC ≥ 8.5 build-quality gate (`qc-built-funnel.sh`; rubric in
`universal-sops/funnel-automation-build-quality-rubric.md`).

## Full-Funnel Pipeline Integration (Skill 44 seam)

When this skill runs as part of a full-funnel build (SOP-07 P4 stage), after page
build and verify pass Gate-3, hand the live `page_ids` + opt-in form IDs to the
Automation Workflow Specialist (CRM) to wire workflows. Invoke Skill 44
(`44-convert-and-flow-operator`) for product creation, form wiring, and GoHighLevel
workflow builds (see `06-ghl-install-pages/v2-autonomous-build-sop.md` §4 for the
Skill-44 ecosystem seam and §2.05 for the method-decision that routes
CALENDAR/FORM/DATA_PUSH pages directly to Skill-44 widget creation before the
page splice). The P4→P5 handoff is documented in v2-autonomous-build-sop.md §4;
do NOT skip this handoff or mark a full-funnel P4 task done without emitting
the board handoff event `{from_dept: "web-development", to_dept: "crm",
artifact: "page_ids+form_ids+funnel_template_id+linked_automations", job_id: "<P5 task id>"}`.
Carrying `funnel_template_id` + `linked_automations` (from STEP 0) across the handoff is what makes
the complete-funnel automation expansion fire in Skill 44; v2_dispatcher persists them to
`routing/skill44-handoff.json` on a verified build.

**Skill-44 widget create+embed flow (in brief):** classify the page (§2.05
method-decision) → if `SKILL44_WIDGET`, call Skill 44 to CREATE the real
GoHighLevel object (calendar, form, or workflow) BEFORE the page splice → capture
the embed snippet from the creation receipt → embed the snippet VERBATIM (no SRI
attributes) into the page blob's code element → verify the snippet tag appears in
the RENDERED DOM via `ghl_verify.render_check`. GoHighLevel objects MUST be real
(status:201, re-GET 200); `status:"PLANNED"` stubs are a hard FAIL.

## When to Use This Skill

- The user asks you to deploy, install, or publish a page in GHL
- The user asks you to put HTML into a Convert and Flow funnel or website
- The user asks you to update an existing GHL page with new code
- The user says "install this page" or "deploy this to GHL"
- You have finished HTML from SuperDesign and need to put it somewhere live

## Prerequisites

- Teach Yourself Protocol (TYP) must be learned first (skill 01)
- Backup Protocol must be learned first (skill 02)
- agent-browser must be installed (skill 03) - PRIMARY browser engine
- GHL Setup must be complete (skill 05) - the account must already exist
- Vercel Setup (skill 08) - only for Mode 2 iframe-embed of rich payloads
- Playwright installed - FALLBACK engine for known-hard flows
- GoHighLevel auth in ~/.openclaw/secrets/.env: a Firebase refresh token
  (GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN — the ONLY auth path; seeds a logged-in
  session with NO login form, NO password, NO two-factor). CLIENT keys only.
  GHL_AGENCY_EMAIL / GHL_AGENCY_PASSWORD (or GHL_EMAIL / GHL_PASSWORD) are a
  DOCUMENTED, MANUAL last resort for a human operator ONLY — they are NEVER
  auto-invoked by this skill, and there is NO automatic UI-login / 2FA fallback.
- **GoHighLevel media/PIT credentials — where they live and how they resolve
  (READ BEFORE the image step).** The image/media pipeline needs three values, all
  in the env stores (resolution order: `~/.openclaw/secrets/.env` →
  `~/clawd/secrets/.env` → `~/.openclaw/workspace/.env`):
  - **LOCATION PIT** (media-scoped): `GOHIGHLEVEL_API_KEY` (preferred) → `GHL_API_KEY`
    → `GOHIGHLEVEL_LOCATION_PIT` → `GHL_LOCATION_PIT`. This is the token media upload
    REQUIRES. The **AGENCY** PIT (`GOHIGHLEVEL_AGENCY_PIT` /
    `GOHIGHLEVEL_AGENCY_API_KEY` / `GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT` /
    `GHL_AGENCY_PIT`) **401s for media** — never substitute it.
  - **Location id**: `GOHIGHLEVEL_LOCATION_ID` → `GHL_LOCATION_ID` →
    `GOHIGHLEVEL_ALLOWED_LOCATION_IDS` → `CAF_ALLOWED_LOCATION_IDS` (first id).
  - **Image key**: `KIE_API_KEY`.
  `ghl_media.resolve_location_pit()` / `resolve_location_id()` search EVERY alias
  across the live env AND the stores above before raising; the image stage's
  `_resolve_kie_api_key()` does the same for KIE. **HARD RULE — never record a GHL
  credential as missing (`honest_fail`) on an empty env var alone.** An empty env
  var means "not loaded", not "absent" — the value is almost always sitting in
  `secrets/.env`. Run `set -a; source ~/.openclaw/secrets/.env; set +a` first, then
  retry. An `honest_fail` is valid ONLY after the full alias × store search comes
  back empty, and it MUST name exactly which vars and stores it checked (the
  resolver's RuntimeError already does). This is the fix for the six-month
  false-fail where the image step reported "GHL LOCATION PIT not found" on a token
  that was in the store the whole time. See v2-autonomous-build-sop.md §2.0.1.

## What This Skill Covers

1. **Browser setup** - Viewport size (minimum 1440x900), isolated headless
   sessions, and anti-detection settings
2. **Token-only session seeding (D7)** - GHL-AUTH-DOCTRINE: TOKEN-ONLY — the
   Firebase refresh token ALONE seeds a logged-in session (mint id_token →
   Firebase IndexedDB record + the six SPA cookies → navigate straight into the
   dashboard). NO login form is rendered, NO password is typed, two-factor is
   NEVER reached. On token failure the builder STOPS and reports — it NEVER
   auto-opens the Sign-in form or a two-factor prompt and NEVER falls back to a
   login/password.
3. **GHL's iframe architecture** - The page builder loads inside nested
   iframes. You cannot just click elements on the main page. The skill
   explains how to find and switch into the correct iframe context.
4. **Selector strategy** - GHL changes their UI frequently. Every button and
   link has a chain of fallback selectors so automation does not break when
   GHL updates a label or class name.
5. **10-phase deployment process** - Navigate to Funnels, create a new funnel,
   add steps, open the builder, dismiss the AI popup, add a blank section with
   a code element, set full width, paste the HTML, save, and preview.
6. **Phase-5 method decision** — Every page is classified before build.
   DEFAULT = DIRECT (native GoHighLevel page blob). Escalate ONLY when the
   classifier positively scores ADVANCED or a widget type. See decision table
   in the "Phase-5 Method Decision" section below and in
   v2-autonomous-build-sop.md §2.05. The old framing of Vercel as a "manual
   last resort" is superseded — Vercel-embed is now a first-class automated
   path for ADVANCED pages; Skill-44 widget is the path for CALENDAR/FORM/DATA_PUSH.
7. **Multi-page funnels** - How to loop through multiple pages (landing, sales,
   checkout, thank you) in a single funnel deployment.
8. **Updating existing pages** - How to find an existing funnel, open the page
   in the builder, replace the code, and save without creating duplicates.
9. **Error recovery** - Retry logic, screenshot capture on failure, and a
   recovery protocol for when things go seriously wrong.
10. **Publishing** - NEVER publish without explicit user approval. Always send
    a deployment report with screenshots first.

## Files in This Folder (Reading Order)

1. **SKILL.md** - You are here. Start with this file.
2. **ghl-browser-builder-full.md** - The v3.0 hardened reference: agent-browser
   engine, auth seeding, the 28-gate runtime contract, the full funnel +
   website + Mode-2 iframe flows, and the ledger/resume mechanics. Read this
   when you are actually about to deploy pages.
3. **tools/** - The code:
   - `seed-ghl-auth.py` - mints a Firebase ID token + browser auth seed (D7).
   - `inject-ghl-auth.sh` - writes the seed into the browser's IndexedDB.
   - `ghl_builder.py` - manifest, per-page ledger/resume, ZHC prefix, sub-account
     gate, publish guard, marker-string verify, runtime-gate loader.
   - `gates.json` - the 28-gate registry (2 captured, 26 runtime snapshot-gates).
4. **ghl-install-pages-full.md** - LEGACY v2.0 raw-Playwright reference, kept for
   historical click-path detail only. Superseded by ghl-browser-builder-full.md.
5. **INSTRUCTIONS.md** - Operational quick-start.
6. **INSTALL.md** - Installation steps if any tools are missing.
7. **EXAMPLES.md** - Example deployments and common scenarios.
8. **CORE_UPDATES.md** - What to add to AGENTS.md, TOOLS.md, and MEMORY.md.
9. **references/client-facing-phrasebook.md** - MANDATORY translation layer.
   Maps every engineer term (funnel, embed, draft, preview URL, HTTP, Firebase,
   iframe, px, etc.) to the plain 7th-grade word the agent must use when
   messaging the client. Also contains the four client delivery templates:
   Template A (draft ready + tappable link + mobile screenshot), Template B
   (live), Template C (security hold), and Template D (pre-build confirm).
   Read this before sending any message to a client. NOTHING from the
   Deployment Report goes to the client — operator log only.

## Critical Things to Know

- PRIMARY engine is agent-browser, headless, with an isolated `--session
  <client>`. It never touches a personal browser (NO-COMINGLING). Playwright is
  the fallback only; if you use it, `launchPersistentContext()` never `launch()`.
- SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown, reaper backstop.
  Route EVERY agent-browser call through the single mandatory
  gateway `tools/browser_manager.sh` (`bash tools/browser_manager.sh ensure`
  then `... eval|open|snapshot ...`); NEVER invoke `agent-browser` directly and
  NEVER invent a per-iteration session name. The gateway owns the ONE canonical
  session, the box-wide lock, the lease, the TTL, the pool ceiling, the
  circuit-breaker, and a guaranteed `trap _bm_teardown EXIT`; the hourly host
  reaper `scripts/agent-browser-reaper.sh` is the backstop for a hard crash.
- GHL-AUTH-DOCTRINE: TOKEN-ONLY (D7) — refresh-token seed is the only auth path; NO auto UI-login / password / 2FA.
  Seed the session logged-in via the Firebase
  refresh token (tools/seed-ghl-auth.py + tools/inject-ghl-auth.sh) BEFORE
  navigating. Auth lives in IndexedDB (firebaseLocalStorageDb) + the six SPA
  cookies, NOT localStorage. The refresh token ALONE logs the SPA in — NO Sign-in
  form is rendered, NO password is typed, two-factor is NEVER reached.
- GHL-AUTH-DOCTRINE: TIER-2 EMAIL-2FA FALLBACK — gated (auth+gmail-proven+email-2fa+creds), bounded, self-heals to TOKEN-ONLY.
  The canonical auth entry point is the orchestrator `tools/ghl_auth.py` (a 3-tier
  ladder). Tier 1 (token-only, above) stays PRIMARY and is the only path a normal
  build takes. Tier 2 is a GATED, audited, ONE-TIME bootstrap that runs ONLY when
  there is no valid refresh token AND four gates pass — (A) recorded client
  authorization, (B) the box PROVES it can read the client's own Gmail (a live
  read, BEFORE any login, so a misconfigured box never starts a login it can't
  finish), (C) GHL's selected 2FA is email, (D) agency creds are in the client
  store. It logs in headless, reads the freshest email-2FA code from the client's
  own Gmail, and on success SELF-HEALS a fresh refresh token to the client store
  so the next run is Tier 1 again. Bounded (MAX_LOGIN_ATTEMPTS <= 3, backoff,
  hard-stop on lockout/captcha). Any gate fail or hard stop -> Tier 3: fail loud,
  non-zero exit, precise client instruction. ALL login/password/2FA code lives in
  EXACTLY ONE module (tools/ghl_auth_fallback.py + its browser helper
  tools/ghl_login_browser.py); CI guard `scripts/guard-ghl-auth-fallback.sh` locks
  the invariants.
- HARD RULE: NEVER ask for, type, or fall back to a GHL login/email/password or a
  two-factor (2FA) prompt. On token failure (no token / revoked / seed does not
  log in) the builder STOPS and reports (non-zero exit) — it MUST NOT auto-open
  the Sign-in form or a two-factor prompt. Fix = re-grab a fresh refresh token via
  the Convert and Flow Token Grabber Chrome extension, then retry the seed.
  GHL_AGENCY_EMAIL / GHL_AGENCY_PASSWORD = MANUAL operator-only last resort, never
  auto-invoked.
- Always verify you are in the correct sub-account before building
  (ghl_builder.py subaccount). Wrong sub-account = the client never sees pages.
  REFUSE on mismatch.
- Default to Funnels, not Websites, unless the user specifically says Website.
- Every funnel/website/step name MUST carry the `zhc` prefix (standing build
  approval) — use ghl_builder.py ensure_zhc_prefix.
- NEVER hardcode invented CSS for an in-app control. Snapshot the live DOM and
  pick the ref at runtime (the 26 runtime gates in tools/gates.json).
- Set large HTML payloads via the code-editor value API (eval), never key-by-key.
- **MANDATORY theme/colors object on EVERY page blob.** Every page blob POSTed to
  GoHighLevel MUST carry a populated `defaultSettings.colors` object. Without it
  GoHighLevel reads `.colors` off `undefined` and returns HTTP 500 — the page
  cannot display even if the bytes stored as 201. The `colors` field MUST be an
  object (e.g. `{"bodyBgColor":"#FFF","btnBgColor":"#0E8C8C",...}`), NEVER a flat
  hex list. Elements MUST nest `section → row → column → element`; flat structure
  is not rendered. The `rawCustomCode` in a code element MUST be an HTML fragment,
  not a full `<!DOCTYPE html>…</html>` document (a full document renders blank).
  `ghl_rest_canvas.new_page_blob()` enforces the golden rule: it MUST load a
  reference from `references/golden/`, assert a populated colors object
  (`assert len(ref["defaultSettings"]["colors"]) >= 3`), and raise
  `GoldenReferenceError` if the assertion fails — it NEVER produces a theme-less
  blob. A 201 autosave status does NOT prove a page renders; it only proves bytes
  were stored.
- **Sealed un-fakeable verification.** A page PASS requires ONLY: `ghl_verify.render_check`
  returns HTTP 200, marker present in the RENDERED (JavaScript-hydrated) DOM, and
  zero render errors — captured as real DOM snapshot + PNG + console artifacts.
  `ghl_gate require-pass` reads ONLY `scorecard/verify-summary.json` written by
  `ghl_verify`; it ignores ledger files and `.md` files. A 201 autosave, a marker
  grep on stored bytes, a hand-written ledger, or a non-200 re-labeled "API
  difference" are each EXPLICITLY REJECTED as pass criteria. Any non-200 is a
  hard FAIL with no escape. A build CANNOT self-declare PASS — the producer runs
  `ghl_verify`, `ghl_verify` writes the scorecard, `ghl_gate` reads it.
- NEVER publish without explicit approval. Default = draft + report the preview
  URL (ghl_builder.py may-publish).
- Long runs fire detached; the agent exits and resumes via the per-page ledger.
- Credentials go in ~/.openclaw/secrets/.env. CLIENT keys only. Never hardcode.

---

## Phase-5 Method Decision Table

Every page MUST be classified before the build begins. The decision is recorded
in `routing/method-decision.json` (required — no build proceeds without it).

| Classifier score | Method | Path |
|---|---|---|
| `SIMPLE` — static content, CSS fits GoHighLevel builder, no third-party JS | `DIRECT` | Native GoHighLevel page blob with §2.06 theme/colors object and HTML fragment in code element |
| `ADVANCED` — rich interactivity, third-party JavaScript, CSS that GoHighLevel builder overrides | `VERCEL_EMBED` | Build + host on Vercel; run `prepare → deploy → disable_sso → assert_embeddable` gates; paste iframe snippet into a DIRECT code element |
| `CALENDAR` / `FORM` / `DATA_PUSH` — needs a real GoHighLevel calendar, form, or CRM write | `SKILL44_WIDGET` | Call Skill 44 to create the GoHighLevel object; embed the GoHighLevel-generated snippet verbatim (no SRI); verify snippet tag appears in RENDERED DOM |

**DEFAULT is DIRECT.** Escalate only when the classifier positively scores ADVANCED
or a widget type. Do NOT use Vercel-embed for simple static pages.

For VERCEL_EMBED: `assert_embeddable` is a hard gate — if `X-Frame-Options` is
`SAMEORIGIN` or `DENY`, the build halts and flags; it does NOT bypass and embed.
The Vercel page MUST be publicly accessible (SSO wall disabled) before the iframe
snippet is generated.

For SKILL44_WIDGET: the GoHighLevel form embed snippet is emitted verbatim WITHOUT
`integrity`/`crossorigin` attributes — GoHighLevel rotates the embed script and
SRI hashes break on the next GoHighLevel deploy. The GoHighLevel object itself
MUST be real (status:201, re-GET 200 in `ecosystem/`); a `status:"PLANNED"` stub
is a hard FAIL.

This table supersedes any prior description of Vercel as a "manual last resort."
