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

## Full-Funnel Pipeline Integration (Skill 44 seam)

When this skill runs as part of a full-funnel build (SOP-07 P4 stage), after page
build and verify pass Gate-3, hand the live `page_ids` + opt-in form IDs to the
Automation Workflow Specialist (CRM) to wire workflows. Invoke Skill 44
(`44-convert-and-flow-operator`) for product creation, form wiring, and GHL
workflow builds (see `06-ghl-install-pages/v2-autonomous-build-sop.md` S4 for the
Skill-44 ecosystem seam). The P4→P5 handoff is documented in v2-autonomous-build-sop.md
S4; do NOT skip this handoff or mark a full-funnel P4 task done without emitting
the board handoff event `{from_dept: "web-development", to_dept: "crm",
artifact: "page_ids+form_ids", job_id: "<P5 task id>"}`.

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
6. **Iframe deployment method** - For complex pages where GHL's own CSS
   conflicts with your code, host the HTML externally and embed it via iframe.
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
- Verify every save/preview/publish with a marker string from the payload, not
  "no error" alone (ghl_builder.py verify).
- NEVER publish without explicit approval. Default = draft + report the preview
  URL (ghl_builder.py may-publish).
- Long runs fire detached; the agent exits and resumes via the per-page ledger.
- Credentials go in ~/.openclaw/secrets/.env. CLIENT keys only. Never hardcode.
