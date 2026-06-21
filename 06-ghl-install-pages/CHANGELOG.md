# Changelog - ghl-install-pages

All notable changes to this skill wrapper are documented here.

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

