# GoHighLevel Browser-Driven Page / Funnel / Website Builder — Hardened Reference (v3.0)

**Engine:** `agent-browser` (Vercel Labs, Skill 03) PRIMARY, headless + isolated
`--session`. Playwright (self-hosted) FALLBACK for known-hard flows only.
**This replaces the raw-Playwright-only stack** of the previous reference
(`ghl-install-pages-full.md`, v2.0), aligning Skill 06 to the Skill 03
agent-browser-first convention (GOAL §2.2 / §4.2.2).

> **D6 — HEADLESS-ONLY, HARD GUARD (non-negotiable, dev OR client).** Never open
> a VISIBLE browser window — taking over a screen is forbidden, especially on a
> client box. agent-browser is headless by default, but an inherited
> `AGENT_BROWSER_HEADED` env var OR a `{"headed": true}` config file can silently
> force a headed window (this is exactly how a live run once opened a visible
> Chromium). EVERY agent-browser invocation in this skill MUST:
> 1. start with **`agent-browser --headed false`** — `--headed false` is the
>    documented override that also disables a config-file `"headed": true`
>    (agent-browser 0.27.0); and
> 2. run with the env stripped: **`unset AGENT_BROWSER_HEADED`** (the wrappers
>    `tools/inject-ghl-auth.sh` and the `tools/ghl_builder.py headless-guard`
>    helper do this and ABORT — exit 75 — if a headed signal survives).
> There is NO supported path — not first login, not two-factor, not Playwright —
> that may open a visible window. Two-factor that genuinely needs a human is
> handled by the headless seed path (§2) so the form is never even rendered; a
> truly-blocked two-factor PAUSES and surfaces to the operator, it does NOT pop a
> window. Emit every browser line via `ghl_builder.py browser-cmd ...` (it
> prepends `--headed false`) or by hand with the prefix above.

> **STATUS — PENDING-LIVE-RUN.** Gate #1 (login form) and gate #27 (auth-storage
> keys) are LIVE-CAPTURED and real. Gates #2–#26 and #28 are **runtime
> snapshot-gates** (`gates.json` status=`runtime`) — they were BLOCKED behind
> two-factor authentication in the 2026-06-21 capture pass and have **NOT** been
> verified live. No invented CSS is shipped as fact for them. The end-to-end
> funnel/website live test (GOAL D9–D13) is **NOT** claimed — it is blocked on a
> fresh Firebase refresh token or an attended two-factor-authentication run.

---

## 0. WHY BROWSER AUTOMATION (no shortcut)

GoHighLevel exposes NO API — public or internal — for building Funnels,
Websites, or Pages. The builder is a UI-only surface. The only way to create or
edit a funnel/website page programmatically is to drive the browser through the
human click-path. The Convert and Flow CLI (Skill 44) is relevant ONLY for the
post-build verification READ of a published URL — never for the build itself.
This is **Tier 4** in Skill 36's access chain (browser via Skill 03).

---

## 1. ENGINE + MODEL + ISOLATION

### 1.1 PRIMARY: agent-browser (Vercel Labs), headless
- Already the repo's sanctioned tool (Skill 03) — no new dependency.
- **HEADLESS-FORCED (D6)** — every invocation passes `--headed false` and runs
  with `AGENT_BROWSER_HEADED` unset. `--headed` is NEVER used here, not even for
  two-factor (see §2 — the headless token seed means no login form is rendered).
- `--session <client-id>` → isolated instance + own profile dir. NEVER touches a
  personal Chrome. Enforces NO-COMINGLING.
- Stable accessibility refs (`@e1`, `@e2`) survive GoHighLevel's React re-renders
  far better than CSS selectors (the #1 cause of GoHighLevel automation
  flakiness).
- **Auto-inlines iframes** into the snapshot (v0.27.0) and exposes `frame @ref` /
  `frame main` — this handles the nested-editor iframe boundary (gate #12)
  without manual frame switching.
- Native auth seeding: `state save/load` captures cookies + localStorage +
  **IndexedDB**; `--state <file>` loads a saved auth state; `eval --stdin` writes
  IndexedDB directly; `--headers` sets the `token-id` header.

Core commands (full surface in `agent-browser skills get core --full`).
**Note the `--headed false` on EVERY line (D6) — it is mandatory, not optional:**
```
unset AGENT_BROWSER_HEADED          # D6: strip any inherited headed signal first
agent-browser --headed false --session <c> open <url>
agent-browser --headed false --session <c> snapshot -i              # interactive refs only
agent-browser --headed false --session <c> snapshot -i --json       # machine-parseable refs
agent-browser --headed false --session <c> find role button name "Sign in" click
agent-browser --headed false --session <c> fill @e1 "text"
agent-browser --headed false --session <c> wait "<text>"            # poll for a node (NOT fixed sleep)
agent-browser --headed false --session <c> eval --stdin             # write IndexedDB / set editor value
agent-browser --headed false --session <c> state save ./auth.json   # persist a logged-in session
agent-browser --headed false --session <c> --state ./auth.json open <url>
agent-browser --headed false --session <c> screenshot out.png
```
Or emit any of these headless-forced via `python3 tools/ghl_builder.py browser-cmd
--session <c> snapshot -i` (prepends `--headed false`; refuses with exit 75 if the
env would force headed).

### 1.2 FALLBACK: Playwright (self-hosted, scripted)
Drop to a deterministic Playwright script ONLY for flows too fiddly for
ref-clicking (drag-drop canvas widgets, file uploads, a CodeMirror/Monaco value
set that agent-browser cannot reach). Use `launchPersistentContext()` (never
`launch()`), own `user-data-dir`, **`headless=True` ALWAYS (D6 — never
`headless=False`, no exception)**, `--disable-blink-features=AutomationControlled`.
Keep it a scripted escape hatch, NOT the default loop. The headless token seed
(§2) removes the only old reason `headless=False` was ever considered.

Both engines may point at **Browserbase** as a remote CDP backend (`-p
browserbase`) for fully detached/offloaded runs — that is the cloud tier, not a
different engine.

### 1.3 Model (fleet doctrine: Opus=think, Sonnet=build, Haiku=mechanical)
- **PRIMARY: Sonnet** — the snapshot→pick-ref→act→verify build loop.
- **ESCALATION: Opus** — only for a NEEDS-LIVE-SELECTOR ambiguity / unseen UI
  variant / recovery pause that needs reasoning over the raw snapshot.
- **Haiku: mechanical only** — `ghl_builder.py` ledger/manifest/verify, file
  reads, URL/string checks. NEVER live UI navigation.
- Every dispatch NAMES its model in the agent name; declare the agent count up
  front with a hard cap.

### 1.4 Silent / detached
Headless, isolated `--session`. Long live-test runs fire DETACHED and the agent
EXITS — resume via the per-page ledger (§5). Never hijack a screen, never
babysit.

---

## 2. AUTH SEEDING — start already logged in (D7)

> **D7 — TOKEN-SEED-INTO-INDEXEDDB IS THE DEFAULT (no UI login).** The DEFAULT
> and ONLY-by-default auth path is: mint the Firebase ID/refresh token from the
> client's refresh token, write it straight into IndexedDB
> (`firebaseLocalStorageDb` → `firebaseLocalStorage` → `fbase_key` →
> `value.stsTokenManager`), then navigate STRAIGHT INTO the dashboard. **No login
> form is ever rendered** on this path — which is what tempted the earlier visible
> window. **UI login (the Sign-in form, §2.2 / A1) is the LAST-RESORT FALLBACK
> ONLY**, used solely when no usable refresh token exists; it is still headless
> and still never opens a visible window (D6).

**Corrected by the 2026-06-21 live capture:** GoHighLevel stores Firebase auth in
**IndexedDB, NOT localStorage.** Seeding localStorage does nothing.

```
IndexedDB database : firebaseLocalStorageDb
  object store     : firebaseLocalStorage   (keyPath = "fbase_key")
    entry.value.stsTokenManager.refreshToken   <- Firebase refresh token
    entry.value.stsTokenManager.accessToken    <- Firebase ID token (short-lived JWT)
    entry.value.stsTokenManager.expirationTime <- epoch millis
    entry.value.uid                            <- user id
localStorage (origin): deviceId, proxyLoginCount, debug_sentry, locale  (NO token)
```

### 2.1 Flow
1. `python3 tools/seed-ghl-auth.py --print-seed --out /tmp/<session>/ghl-auth-seed.json`
   — reuses the SAME Firebase refresh→ID exchange Skill 44 does in
   `transport.py` (same `securetoken.googleapis.com` endpoint, same hardcoded
   `FIREBASE_API_KEY = AIzaSyB_w3vXmsI7WeQtrIOkjR6xTRVN5uOieiE`, same
   `grant_type=refresh_token`, same env order
   `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` → `CAF_FIREBASE_REFRESH_TOKEN` →
   `GHL_FIREBASE_REFRESH_TOKEN`). It does NOT import or modify Skill 44's engine.
2. `bash tools/inject-ghl-auth.sh <session> /tmp/<session>/ghl-auth-seed.json --pre-open`
   — opens the GoHighLevel origin (so IndexedDB exists), writes the seed entry
   into `firebaseLocalStorageDb`/`firebaseLocalStorage` via `eval`, reloads. This
   script is HEADLESS-FORCED (D6): it `unset`s `AGENT_BROWSER_HEADED`, runs every
   agent-browser call through a wrapper that appends `--headed false`, and ABORTS
   (exit 75) if a headed signal survives. No login form is rendered on this path.
3. `agent-browser --headed false --session <session> snapshot -i` → confirm the
   **dashboard**, NOT the Sign in form. If the form shows → token revoked → fall
   back to A1 (the LAST-RESORT UI login, still headless).
4. Once a real logged-in session exists, `agent-browser --headed false --session
   <session> state save ./<client>-auth.json` and reuse via `--state` (captures
   the verbatim post-login cookie set, which a freshly minted token alone cannot
   provide).

ID token is short-lived (~50–60 min). On a 401 mid-build, re-run
`seed-ghl-auth.py` and re-inject (retry-once, mirrors transport.py).

### 2.2 Documented fallback (LAST RESORT — UI login)
**UI login is the LAST-RESORT fallback only** (the default is the headless token
seed in §2.1; this path renders the Sign-in form and is used ONLY when no usable
refresh token exists). No usable refresh token → login form (A1) with
`GHL_AGENCY_EMAIL` / `GHL_AGENCY_PASSWORD` (real fleet var names;
`GHL_EMAIL`/`GHL_PASSWORD` also accepted). The form is filled **headless** (D6 —
still `--headed false`, still no visible window). **Two-factor authentication is
NEVER bypassed:** if a code is genuinely required and cannot be satisfied
headless, the run PAUSES, captures a screenshot to disk, and surfaces to the
operator — it does NOT open a window. Prefer fixing auth by re-grabbing the
client's refresh token (Token Grabber) so the default §2.1 seed path applies.
`state save` after a successful login so it persists.

### 2.3 Credential model
CLIENT keys ONLY. Every client box runs on the client's own funded GoHighLevel
creds + the client's own captured refresh token. The operator's keys must NEVER
appear on a client box.

---

## 3. RUNTIME GATE CONTRACT (D8) — snapshot-driven selection

The builder NEVER hardcodes invented CSS for an in-app control. The gate
registry `tools/gates.json` holds 28 gates:
- **2 CAPTURED** (status=`captured`): gate #1 login form + gate #27 auth storage.
  Real, snapshot-verified.
- **26 RUNTIME** (status=`runtime`): the agent MUST, at the moment it needs the
  control, run `agent-browser snapshot -i --json`, match the live nodes against
  the gate's `find` hint (accessibility role/name/text — NOT confirmed CSS), and
  act on the returned `@ref`. The `find` hints are SEARCH SEEDS, not facts.

`python3 tools/ghl_builder.py gates --runtime` lists the 26 capture-at-runtime
gates; `--captured` lists the 2 real ones. This is the D8 contract made
machine-checkable: no runtime gate may be turned into a hardcoded selector
without a fresh live capture that flips its status to `captured`.

**Login route correction (gate #1):** navigate to root
`https://app.convertandflow.com/` — NOT `/login` (the `/login` path renders a
permanently-blank "Initializing…" shell in automated Chromium; the form never
mounts).

---

## PART A — FUNNEL PAGE BUILD (default, ~90% of cases)

Each step: ACTION / GATE (from gates.json) / VERIFY / EDGE. Resolve every
`runtime` gate by live snapshot before acting.

### A0. Preflight
- A0.1 Auth: `seed-ghl-auth.py --check` reports `refresh-token` (preferred) or
  `login-form`. At least one path must be present.
- A0.2 Payloads exist on disk, one per page, self-contained (inline CSS/`<style>`,
  no React/build deps). `ghl_builder.build_manifest` enforces non-empty + file
  exists. A payload too rich for a code block → route to Mode 2 (Part C).
- A0.3 Launch isolated session, HEADLESS-FORCED (D6): `unset
  AGENT_BROWSER_HEADED` then `agent-browser --headed false --session <client> set
  viewport 1440 900` then open. (Playwright fallback: `launchPersistentContext`,
  never `launch`, **`headless=True`**, `--disable-blink-features=AutomationControlled`.)
  Optionally gate the whole launch with `python3 tools/ghl_builder.py
  headless-guard` (exit 75 = headed would open → refuse).
- A0.4 Build the MANIFEST up front (`ghl_builder.build_manifest`): ordered
  `{name, path, payload_path, mode}` — the loop driver AND resume ledger key.

### A1. Login + session
- A1.1 Navigate to root `https://app.convertandflow.com/` (GATE #1, captured).
- A1.2 If auth was seeded (§2) and snapshot shows the dashboard → skip to A2.
  Else fill `input#email` / `input#password` (captured) → click `button "Sign
  in"`.
- A1.3 VERIFY: URL reaches the dashboard within timeout.
- EDGE not-logged-in/expired: re-auth once (prefer re-seeding the token, §2.1);
  still failing → PAUSE + screenshot + surface to operator. Never loop silently.
- EDGE two-factor: detect the "Verify Security Code" screen → PAUSE up to 5 min,
  capture a screenshot to disk, and surface to the operator. **Stay headless
  (D6) — NEVER open a window.** NEVER bypass. `state save` after the operator
  resolves it.

### A2. Sub-account selection — HARD GATE
- A2.1 Read the current sub-account label (top-left).
- A2.2 If mismatch: open account switcher (GATE #2, runtime) → search target →
  click match → re-verify.
- A2.3 `ghl_builder.subaccount_matches(label, target)` must return MATCH.
  **Refuse to proceed on MISMATCH** (NO-COMINGLING).

### A3. Sites → Funnels
- A3.1 Click Sites (GATE #3). A3.2 Click Funnels tab (GATE #4).
- A3.3 VERIFY: funnel list region present — poll for the node (`wait "<text>"`),
  NEVER a fixed sleep.

### A4. New Funnel + `zhc` name
- A4.1 Click + New Funnel (GATE #5).
- A4.2 Set name via `ghl_builder.ensure_zhc_prefix(name)` (e.g. `zhc test`) into
  the name input (GATE #6). If a "Blank Funnel" option is present in this modal,
  select it; else defer the blank choice to the step (A7) — support BOTH
  variants.
- A4.3 Click Create (GATE #7).
- A4.4 VERIFY: workspace loads; capture + store `funnel_workspace_url` (re-entry
  anchor for every page + resume).
- EDGE duplicate name: before A4.1 search the list for the `zhc` name; if found
  and intent=edit → A14; if intent=new → append disambiguator (`zhc test 2`) and
  record in manifest. Never blindly create a second identical name.

### A5. Loop — FOR EACH page in manifest (A6–A13)
Write the per-page ledger after each phase (§5).

### A6. Add new step (NOT Import)
- A6.1 Click Add New Step (GATE #8 — must positively distinguish from the
  adjacent Import control; match exact name).
- A6.2 Fill Step Name + Step Path (GATE #9; path lowercase/hyphenated/unique —
  `build_manifest` already normalizes).
- A6.3 VERIFY: step appears in the list.
- EDGE duplicate step path: catch the inline error, append disambiguator, retry
  once, record in ledger.

### A7. Blank / open editor
- A7.1 If a template chooser appears, select Blank (GATE #10).
- A7.2 Open the page editor (GATE #11).
- A7.3 VERIFY: editor canvas iframe present (GATE #12 — use `frame @ref`).
- EDGE nested iframe: enter the correct frame before any canvas action;
  agent-browser auto-inlines frames into the snapshot — locate, then scope.

### A8. Add blank Section
- A8.1 Add a blank Section (GATE #13). A8.2 VERIFY: a section node exists.

### A9. Full-width
- A9.1 Open section settings, enable the full-width toggle (GATE #14 — label is
  EITHER "Allow rows to take up full length" OR "Allow rows to take entire
  width"; match either, verify by toggle STATE not label text).
- A9.2 VERIFY: toggle reads ON.

### A10. Code element + paste HTML (Mode 1 — direct)
- A10.1 Add a Custom Code / HTML element into the section (GATE #15).
- A10.2 Open the code editor, paste the payload VERBATIM from `payload_path`
  (GATE #16). For CodeMirror/Monaco set the value via the editor API through
  `eval` — NOT key-by-key typing (large payloads). The editor modal renders on
  the MAIN page, not inside the builder iframe.
- A10.3 Save the code element (GATE #17).
- A10.4 VERIFY: rendered preview shows a known marker string from the payload.
  Ledger → `code-saved`.
- EDGE payload too large / rejected: fall back to Mode 2 (Part C); set manifest
  `mode: iframe`.
- EDGE AI popup: dismiss on first editor open (GATE #18); absent is fine, do not
  crash.

### A11. Save page
- A11.1 Click editor Save (GATE #19).
- A11.2 VERIFY: save-confirmation toast/state; no unsaved indicator. Ledger →
  `page-saved`. EDGE save race: wait for the toast (not a sleep), retry once on a
  transient error.

### A12. Preview
- A12.1 Open Preview (GATE #20). A12.2 VERIFY:
  `ghl_builder.verify_url(preview_url, marker)` → HTTP 200 + marker present.
  Ledger → `previewed`.

### A13. Publish — REQUIRES APPROVAL
- A13.1 GATE: `ghl_builder.may_publish(approval)` must return PUBLISH. Default =
  leave DRAFT and report the preview URL. NEVER publish without an explicit LIVE
  answer.
- A13.2 Publish (GATE #21). A13.3 VERIFY: capture public URL;
  `verify_url(public_url, marker)` → 200 + marker. Ledger → `published`.

### A14. Existing-page UPDATE (edit, not create)
- A14.1 Open the existing `zhc` funnel by `funnel_workspace_url` (preferred) or
  exact name (GATE #22).
- A14.2 Open the step's editor → Code element → REPLACE payload → save (A10–A11);
  verify as A11–A12.
- EDGE multiple matching steps: refuse to guess; surface the list, require
  disambiguation.

---

## PART B — WEBSITE PAGE BUILD (only when client says "Website")

Default is Funnels. Website mirrors Part A with substitutions:
- B3 Sites → Websites tab (GATE #23). B4 + New Website → `zhc` name → Blank →
  Create (GATE #24); capture `website_workspace_url`.
- B6–B13 same step/section/code/save/preview/publish flow (GATE #25). **Do NOT
  assume Website selectors equal Funnel selectors — snapshot the Website editor
  independently.** All runtime gates carry over.

---

## PART C — MODE 2: IFRAME EMBED (payload too rich for a Code block)

For full Vercel builds (React/external deps) that cannot live in a Code element.
- C1 Host externally on Vercel (Skill 08). VERIFY: public Vercel URL returns 200.
- C2 In the GoHighLevel page (Part A through A9), the Code element's payload is a
  single responsive `<iframe src="<vercel-url>">` sized to the section (GATE #26,
  same element as A10).
- C3 Save → Preview → Publish (A11–A13). VERIFY the Vercel URL directly (200 +
  marker) AND visually confirm the embed renders inside the published page.
- EDGE X-Frame-Options / CSP: if the Vercel app sends `X-Frame-Options: DENY` or
  a restrictive `frame-ancestors`, the embed is blank → set the Vercel headers to
  allow GoHighLevel's published domain as a frame ancestor (GATE #28 — the
  domain is only knowable from a published page).

---

## PART D — MULTI-PAGE LOOP + RESUME (D10 / D12)

- The MANIFEST (A0.4) is the single source of truth for what to build + order.
- The per-page LEDGER lives at `/tmp/<run-id>/<funnel>/<step>.json` with state
  `created | code-saved | page-saved | previewed | published | FAILED`
  (`ghl_builder.ledger_write`, which only ADVANCES, never rewinds).
- On partial failure / resume: `ghl_builder.resume_point(run_id, manifest)`
  returns, per page, `resume_at` + `skip_create`. Re-enter at
  `funnel_workspace_url`; NEVER re-create a step whose ledger state is ≥
  `created` (`skip_create:true`). Verify the funnel step-list order after the
  loop.
- One funnel/website at a time per `--session`; sequential WITHIN a funnel.
  Independent clients run in parallel isolated sessions.
- Report after EACH page completes: name, state reached, preview/published URL.

---

## EDGE CASES (consolidated — all handled above)
sub-account mismatch (A2.3 hard gate) · two-factor pause (A1, never bypass) ·
token expiry mid-build (re-seed, retry-once) · duplicate funnel/website name +
duplicate step path (search-first, disambiguate, record) · nested-iframe editor
(frame scope) · AI popup (dismiss) · payload too large (→ Mode 2) ·
X-Frame-Options/CSP (frame-ancestors) · full-width label drift (verify by state)
· save race (wait toast, retry once) · publish-without-approval (NEVER) ·
partial-failure resume (ledger) · fixed-sleep flakiness (poll nodes) · persistent
context (never fresh launch) · marker-string verification (every save/preview/
publish) · multi-page ordering (verify step list) · Website≠Funnel parity
(snapshot both) · detached long runs (resume via ledger) · client keys only ·
CodeMirror/Monaco value-set via API.

---

## DEPLOYMENT REPORT TEMPLATE
```
DEPLOYMENT REPORT
Date / Sub-account / Surface (Funnel|Website) / Run-id
PAGES: | Name | Path | State reached | Preview URL | Published URL |
VERIFY: per page — HTTP code + marker-string found (from ghl_builder verify)
PUBLISH STATUS: Draft (awaiting approval) | Published
ISSUES / NEXT STEPS
```
