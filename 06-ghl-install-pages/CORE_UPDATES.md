# GHL / Convert and Flow - Install Pages - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

Doctrine sentinels (BOTH MUST appear verbatim in AGENTS.md + TOOLS.md after applying):
`GHL-AUTH-DOCTRINE: TOKEN-ONLY (D7) — refresh-token seed is the only auth path; NO auto UI-login / password / 2FA`
`GHL-AUTH-DOCTRINE: TIER-2 EMAIL-2FA FALLBACK — gated (auth+gmail-proven+email-2fa+creds), bounded, self-heals to TOKEN-ONLY`

Sentinel: <!-- skill:06-ghl-install-pages:core-update-applied -->

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## GHL Page Deployment [PRIORITY: HIGH]
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/06-ghl-install-pages/ghl-browser-builder-full.md
- Engine: agent-browser (PRIMARY, headless, isolated `--session <client>`); Playwright is FALLBACK only and uses launchPersistentContext (NEVER launch()).
- GHL-AUTH-DOCTRINE: TOKEN-ONLY (D7) — refresh-token seed is the only auth path; NO auto UI-login / password / 2FA.
  Funnel/website/page builds authenticate by minting a Firebase id_token from GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN, reconstructing the SPA session (Firebase IndexedDB record + the six SPA cookies), then navigating straight into the dashboard. NO login form is rendered, NO password is typed, two-factor is NEVER reached.
  HARD RULE: NEVER ask for, type, or fall back to a GHL login/email/password or a two-factor (2FA) prompt for a page build. On token failure (no token / revoked / seed does not log in) the builder STOPS and reports — it does NOT auto-open the Sign-in form. Re-grab a fresh refresh token via the Convert and Flow Token Grabber Chrome extension, then retry the seed.
  GHL_AGENCY_EMAIL / GHL_AGENCY_PASSWORD are a DOCUMENTED, MANUAL last resort for a human operator ONLY — never auto-invoked by any agent or script.
- GHL-AUTH-DOCTRINE: TIER-2 EMAIL-2FA FALLBACK — gated (auth+gmail-proven+email-2fa+creds), bounded, self-heals to TOKEN-ONLY.
  The canonical auth entry point is the orchestrator tools/ghl_auth.py (a 3-tier ladder). Tier 1 (token-only, above) stays PRIMARY. Tier 2 is a GATED, audited, one-time email-2FA bootstrap that runs ONLY when there is no valid refresh token AND four gates pass (A recorded client authorization, B Gmail-access PROVEN by a live read BEFORE any login, C email is the selected 2FA method, D agency creds in the client store). On success it SELF-HEALS a fresh refresh token to the client store so the next run is Tier 1. Bounded (<=3 attempts, backoff, hard-stop on lockout/captcha). Any gate fail / lockout -> Tier 3: fail loud, non-zero exit, precise client instruction. ALL login/2FA code lives in tools/ghl_auth_fallback.py + tools/ghl_login_browser.py; CI guard scripts/guard-ghl-auth-fallback.sh.
- Always verify the correct sub-account before building (refuse on mismatch).
- Credentials: ~/.openclaw/secrets/.env — GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN (canonical; CLIENT key only). Never the operator's keys on a client box.
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## GHL Page Builder (Browser Automation)
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/06-ghl-install-pages/ghl-browser-builder-full.md
- Engine: agent-browser PRIMARY (headless, isolated `--session <client>`, never a personal browser); Playwright FALLBACK only (launchPersistentContext, never launch()).
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
