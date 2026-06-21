# Changelog - ghl-install-pages

All notable changes to this skill wrapper are documented here.

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
- Recorded `_env`: BlackCEO LLC location id `Mct54Bwi1KlNouGXQcDX`, preview
  domain `blackceolinks.com`, Websites mirrors Funnels.
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

