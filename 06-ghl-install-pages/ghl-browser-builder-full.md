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
> that may open a visible window. The build loop never renders the Sign-in form
> at all: the headless token seed (§2) is the ONLY auth path, so two-factor is
> never reached. If the seed fails to log in, the builder STOPS and surfaces to
> the operator (NO auto UI-login / two-factor); it does NOT pop a window. Emit
> every browser line via `ghl_builder.py browser-cmd ...` (it prepends
> `--headed false`) or by hand with the prefix above.

> **STATUS — PENDING-LIVE-RUN.** Gate #1 (login form) and gate #27 (auth-storage
> keys) are LIVE-CAPTURED and real. Gate #27's full record shape — the
> `firebase:authUser:<apiKey>:[DEFAULT]` key and the Firebase Web SDK `User` value
> (with the REQUIRED `emailVerified`/`isAnonymous` booleans that fix the old
> `auth/internal-error`) — is confirmed against the Firebase JS SDK source and the
> live token exchange (securetoken HTTP 200, id_token validates via the `token-id`
> header). The refresh token alone seeds a logged-in SPA session — **no UI login,
> no two-factor.** Gates #2–#26 and #28 are **runtime snapshot-gates**
> (`gates.json` status=`runtime`) — they were BLOCKED behind two-factor
> authentication in the 2026-06-21 capture pass and have **NOT** been verified
> live. No invented CSS is shipped as fact for them. The end-to-end funnel/website
> live test (GOAL D9–D13) is **NOT** claimed — it is blocked on a fresh Firebase
> refresh token (seed path), NOT on a UI/two-factor run, which is now disabled.

---

## 0. WHY BROWSER AUTOMATION (no shortcut)

> **SUPERSEDED for content edits (2026-06-22) — primary path is now REST autosave.**
> The claim below that "the only way is to drive the canvas" held until the
> internal SPA REST surface was cracked. Two capabilities once believed to need
> canvas-driving are in fact plain `token-id`-authenticated XHRs against the GHL
> SPA's own internal REST routes (proven live, lands-and-verifies, byte-identical
> revert): **(1)** page/funnel/website content read+edit+SAVE via
> `GET /funnels/page/<id>` + `POST /funnels/builder/autosave/<id>`, and **(2)**
> workflow trigger read+rewire via `GET /workflow/<loc>/<wf>?includeTriggers=true`
> + `PUT /workflow/<loc>/trigger/<id>`. **Primary = REST autosave** (see §0.1 and
> the REST recipe at the end of Part A); **canvas-driving (Part A A8–A13 visual
> click-path) is RETAINED as the documented FALLBACK** for any UI-only action
> with no REST equivalent (placing a non-code visual element, drag-only widgets,
> anything the page-data blob cannot express). Source of truth + raw evidence:
> `Downloads/GHL-HEADLESS-CANVAS-SOLUTION-2026-06-22.md`.

GoHighLevel exposes no *public* API for building Funnels, Websites, or Pages,
and the builder presents as a UI-only surface — so the **fallback** path is to
drive the browser through the human click-path. The Convert and Flow CLI
(Skill 44) is relevant for the post-build verification READ of a published URL —
never for the build itself. This is **Tier 4** in Skill 36's access chain
(browser via Skill 03). The **primary** path below (§0.1) uses the SPA's own
internal REST surface, executed *inside* the agent-browser (the routes are
Cloudflare-WAF gated, so they must inherit the browser's CF clearance + UA).

### 0.1 PRIMARY: REST autosave (the cracked canvas-REST path)

For any content edit the page-data blob can express (image swap, Code/Custom-Code
element value, tracking code), the canonical build/edit flow is the REST
autosave recipe, wired into the tooling as
`ghl_builder.emit_rest_save_plan` (orchestrating the proven
`tools/ghl_rest_canvas.py` primitives). The agent runs the emitted, ordered
eval-steps INSIDE the seeded agent-browser:

**read → splice → autosave (DRAFT) → verify → revert-baseline.**

- It is faster, deterministic, needs no pixel coordinates, survives UI redraws,
  and round-trips to **byte-identical** (the canvas Save re-serializes the blob,
  so a canvas round-trip is content-correct but NOT byte-identical — both live
  validators used the REST path for the exact-bytes restore even after driving
  the canvas).
- The same module emits `emit_workflow_rewire_plan` (workflow trigger
  read→rewire→re-read) and `emit_revert_plan` (byte-identical restore).
- Every write plan is gated behind `subaccount_matches()` (MISMATCH = refuse,
  zero steps), keeps the autosave a DRAFT via `may_publish()` (default), and
  verifies the preview with `verify_url()` (HTTP 200 AND marker). The full
  step-by-step recipe + the load-bearing gotchas are at the **end of Part A**
  ("REST autosave recipe").

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

**SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown, reaper backstop.**
Route EVERY agent-browser call through the single mandatory
gateway `tools/browser_manager.sh` — NEVER invoke `agent-browser` (or a raw
per-call `AB --session`) directly, and NEVER invent a per-iteration session name
(that is exactly what leaked 22 orphan `~/.agent-browser/*.engine` descriptors,
357M, on the operator box). The gateway owns the ONE canonical session
(`bm_session_name` = `ghl-skill6-<location-id>`), the box-wide lock (lock=1), the
lease, the per-call + per-session TTL, the pool ceiling, the circuit-breaker, and
a GUARANTEED `trap _bm_teardown EXIT` (close + state clear). The host reaper
(`scripts/agent-browser-reaper.sh`, hourly cron — `13 * * * *`) is the backstop for a hard crash.

Core commands (full surface in `agent-browser skills get core --full`).
**Note the `--headed false` on EVERY line (D6) — it is mandatory, not optional —
and route them through the gateway:**
```
# 1. one canonical session, lock+lease+TTL+teardown-trap acquired here:
bash tools/browser_manager.sh ensure
# 2. then every verb goes through the gateway (it asserts the lock + forces
#    --headed false; the EXIT trap guarantees teardown even on a non-zero abort):
bash tools/browser_manager.sh open -- <url>
bash tools/browser_manager.sh snapshot -- -i              # interactive refs only
bash tools/browser_manager.sh snapshot -- -i --json       # machine-parseable refs
bash tools/browser_manager.sh find -- role button name "Sign in" click
bash tools/browser_manager.sh fill -- @e1 "text"
bash tools/browser_manager.sh wait -- "<text>"            # poll for a node (NOT fixed sleep)
bash tools/browser_manager.sh eval -- --stdin             # write IndexedDB / set editor value
```
Print the canonical session name for a shell caller via
`SESSION="$(bash tools/browser_manager.sh session-name)"` (or
`python3 tools/ghl_builder.py browser-session`). Or emit a single headless-forced
line via `python3 tools/ghl_builder.py browser-cmd --session <c> snapshot -i`
(prepends `--headed false`; refuses with exit 75 if the env would force headed OR
if no `browser_session()` is active).

### 1.2 FALLBACK: Playwright (self-hosted, scripted)
Drop to a deterministic Playwright script ONLY for flows too fiddly for
ref-clicking (drag-drop canvas widgets, file uploads, a CodeMirror/Monaco value
set that agent-browser cannot reach). Use `launchPersistentContext()` (never
`launch()`), own `user-data-dir`, **`headless=True` ALWAYS (D6 — never
`headless=False`, no exception)**, `--disable-blink-features=AutomationControlled`.
Keep it a scripted escape hatch, NOT the default loop. The headless token seed
(§2) removes the only old reason `headless=False` was ever considered. **The
SINGLETON POOLED BROWSER lifecycle covers Playwright too:** the reaper
(`scripts/agent-browser-reaper.sh`) scopes its Chromium tripwire + leaked-proc
kill to the Playwright `user-data-dir` (set `AB_REAPER_PLAYWRIGHT_DIR` to its
profile path) as well as `~/.agent-browser`, and the circuit-breaker gates the
build loop regardless of which engine drives it — so a Playwright escape hatch
can never reopen the orphan path.

Both engines may point at **Browserbase** as a remote CDP backend (`-p
browserbase`) for fully detached/offloaded runs — that is the cloud tier, not a
different engine.

### 1.3 Model (client-provider doctrine — Ollama Cloud preferred, OpenRouter backup; thinking=HIGH; NEVER Anthropic)
- **PRIMARY (browser control + tool calls + QC): MiniMax 3** — the
  snapshot→pick-ref→act→verify build loop and every tool/REST call. Ollama Cloud
  preferred (`…:cloud`, baseUrl `ollama.com`), OpenRouter as backup. The build
  loop is deterministic Python (REST canvas + gates), so the model only has to
  drive tool calls reliably — MiniMax 3 is the tool-calling primary, PROBE-GATED
  by `tools/model_router.py` because MiniMax priors are flagged-suspect (probe =
  a tiny task that REQUIRES a tool-call/JSON return).
- **ESCALATION (reasoning over the raw snapshot): DeepSeek v4 pro or GLM 5.2** —
  only for a NEEDS-LIVE-SELECTOR ambiguity / unseen UI variant / recovery pause.
  Ollama Cloud preferred (`ollama/deepseek-v4-pro:cloud`), OpenRouter backup
  (`openrouter/deepseek/deepseek-v4-pro`). thinking/reasoning effort = HIGH.
- **Page/HTML content writing or a broken-code fix: GLM 5.2** — Ollama Cloud
  preferred, OpenRouter backup (matches the install-pages doc §10 STEP 3).
- **Mechanical only — model-agnostic (client's configured/default model):**
  `ghl_builder.py` ledger/manifest/verify, file reads, URL/string checks. NEVER
  live UI navigation.
- **NEVER Anthropic on a client box.** Clients run their OWN providers (Ollama
  Cloud / OpenRouter / MiniMax / DeepSeek / GLM); `tools/model_router.py` is the
  probe-gated fallback ladder and HARD-GUARDS against any Anthropic id.
- Every dispatch NAMES its model in the agent name; declare the agent count up
  front with a hard cap.

### 1.4 Silent / detached
Headless, ONE canonical `--session` (never a per-iteration name). Long live-test
runs fire DETACHED THROUGH THE GATEWAY so the detached subtree OWNS the
lock+lease+TTL+teardown-trap and a detach-and-exit can never orphan a browser:
```
bash tools/browser_manager.sh run-detached -- <build-cmd>
```
The agent then EXITS — resume via the per-page ledger (§5). The circuit-breaker
PARKS a flaky build (qc-failed) after `AB_BREAKER_MAX` opens without a verified
pass (loud STOP via Rescue Rangers, parked NOT re-fired); the hourly reaper sweeps
any descriptor a hard crash still leaks. Never hijack a screen, never babysit.

---

## 2. AUTH SEEDING — start already logged in (D7)

> **D7 — TOKEN-SEED-INTO-INDEXEDDB IS THE *ONLY* AUTH PATH (no UI login, no 2FA).**
> The client's Firebase **refresh token ALONE** produces a logged-in SPA session:
> mint a fresh ID token from the refresh token, write the **full Firebase Web SDK
> User record** into IndexedDB (`firebaseLocalStorageDb` → `firebaseLocalStorage`
> → `fbase_key` → `value{…}`), then navigate STRAIGHT INTO the dashboard. **No
> Sign-in form is ever rendered, no password is typed, two-factor is never
> reached.**
>
> **HARD RULE — NO AUTOMATIC UI-LOGIN / 2FA FALLBACK.** The token-seed is the ONLY
> auto-invoked auth path. If seeding fails (no token / revoked token / the seeded
> record does not log the SPA in), the builder **STOPS and reports** (non-zero
> exit) — it MUST NOT auto-open the Sign-in form or a two-factor prompt. The
> operator re-grabs a fresh refresh token (Token Grabber) and retries the seed.
> `GHL_AGENCY_EMAIL` / `GHL_AGENCY_PASSWORD` remain a **DOCUMENTED, MANUAL last
> resort only** (operator-initiated, never auto-invoked, §2.2).

**Corrected by the 2026-06-21 live capture + Firebase JS SDK source:** GoHighLevel
stores Firebase auth in **IndexedDB, NOT localStorage.** Seeding localStorage does
nothing. The persisted record is the Firebase Web SDK `User._fromJSON()` shape and
**must** include `emailVerified` + `isAnonymous` as booleans — the SDK asserts
both; omitting them was the root cause of the old `auth/internal-error` that
bounced the SPA back to the login form.

```
IndexedDB database : firebaseLocalStorageDb
  object store     : firebaseLocalStorage   (keyPath = "fbase_key")
    entry.fbase_key = "firebase:authUser:AIzaSyB_w3vXmsI7WeQtrIOkjR6xTRVN5uOieiE:[DEFAULT]"
    entry.value = {                            <- full Firebase Web SDK User JSON
      uid               : <user_id from securetoken response>
      emailVerified     : false               <- REQUIRED boolean (SDK assertion)
      isAnonymous       : false               <- REQUIRED boolean (SDK assertion)
      providerData      : []                   <- custom sign-in -> empty array
      stsTokenManager.refreshToken            <- Firebase refresh token
      stsTokenManager.accessToken             <- Firebase ID token (short-lived JWT)
      stsTokenManager.expirationTime          <- epoch MILLISECONDS
      createdAt / lastLoginAt                 <- epoch-ms STRINGS (not numbers)
      apiKey  = AIzaSyB_w3vXmsI7WeQtrIOkjR6xTRVN5uOieiE
      appName = "[DEFAULT]"
    }
    (email/displayName/photoURL OMITTED — a custom-auth user has none; null fails
     the SDK's string|undefined assertion.)
localStorage (origin): deviceId, proxyLoginCount, debug_sentry, locale  (NO token,
  not auth-bearing — do NOT seed). Cookies: none required (auth rides the
  `token-id` header sourced from the IndexedDB record; no app-token to mint).
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
   — opens the GoHighLevel origin (so IndexedDB exists), validates the seed has
   the required boolean fields + tokens (FAIL LOUD otherwise), writes the entry
   into `firebaseLocalStorageDb`/`firebaseLocalStorage` via `eval`, **reads it
   back to confirm it persisted**, fetches `/oauth/2/login/current` in-browser
   (token-id header) to obtain the logged-in object and writes the six SPA
   cookies from it, then **activates via the SPA's OWN `$store.dispatch('auth/get')`
   + `$router.push('/')` — it NEVER reloads or re-opens the app root** (a reload
   re-runs the boot IIFE, which `signOut()`s and wipes the seeded session →
   login bounce). Activation is RESILIENT: a warm-store readiness gate (poll
   `#app.__vue_app__` for `$store`+`$router`) plus a bounded jittered retry, and
   success requires the decoded cookie `a` to carry an `apiKey` matching the
   logged-in user (NOT merely "no password box"). This script is HEADLESS-FORCED
   (D6): it `unset`s `AGENT_BROWSER_HEADED`, runs every agent-browser call through
   a wrapper that appends `--headed false`, and ABORTS (exit 75) if a headed
   signal survives. No login form is rendered on this path. If the write/readback
   or activation fails it exits **non-zero** — the builder STOPS (no auto UI-login
   fallback). CI-enforced by `scripts/guard-ghl-activation-resilience.sh`.
3. `agent-browser --headed false --session <session> snapshot -i` → confirm the
   **dashboard**, NOT the Sign in form. **If the form shows → token revoked → STOP
   and report (non-zero).** Do NOT auto-fill the form or trigger two-factor. The
   operator re-grabs a fresh refresh token (Token Grabber) and retries this
   token-seed path.
4. Once a real logged-in session exists, `agent-browser --headed false --session
   <session> state save ./<client>-auth.json` and reuse via `--state` (captures
   the verbatim post-login cookie set, which a freshly minted token alone cannot
   provide).

ID token is short-lived (~50–60 min). On a 401 mid-build, re-run
`seed-ghl-auth.py` and re-inject (retry-once, mirrors transport.py).

### 2.2 MANUAL last resort (operator only — NEVER auto-invoked)
**The token-seed (§2.1) is the ONLY automatic auth path.** There is **no
automatic UI-login / two-factor fallback** — neither `seed-ghl-auth.py` nor
`inject-ghl-auth.sh` ever drives the Sign-in form. When the token-seed cannot run
or cannot log in, the builder **STOPS and reports** (non-zero exit). The correct
fix is for the operator to re-grab the client's refresh token (Token Grabber) and
re-run §2.1.

`GHL_AGENCY_EMAIL` / `GHL_AGENCY_PASSWORD` (real fleet var names;
`GHL_EMAIL`/`GHL_PASSWORD` also accepted) are retained **only as a documented,
operator-initiated manual recovery** for the rare case the refresh token cannot be
re-grabbed at all. They are **never** invoked automatically by the build loop. If
an operator runs that manual path by hand, it stays headless (D6 — `--headed
false`, no visible window) and two-factor is **never bypassed**: a genuinely
required code PAUSES, screenshots to disk, and surfaces to the operator. After a
successful manual login, `state save` so it persists and the §2.1 path resumes.

### 2.3 Credential model
CLIENT keys ONLY. Every client box runs on the client's own funded GoHighLevel
creds + the client's own captured refresh token. The operator's keys must NEVER
appear on a client box.

### 2.4 DOCTRINE — Layer-2 activation MUST be resilient (CI-ENFORCED)
> **STANDING RULE (BANNED REGRESSIONS, CI-enforced):** GHL Layer-2 activation
> (the SPA app-session establishment + SPA activation in `inject-ghl-auth.sh`)
> MUST be resilient — a **warm-store readiness gate** (wait until the SPA auth
> store is booted AND cookie `a` is readable) + a **bounded jittered retry** (NOT
> single-shot) + a **token-only cookie re-assert** (on a cookie-`a` wipe, re-fetch
> `/oauth/2/login/current` with the same id_token and re-write the cookies —
> never a UI login) + a **positive cookie-`a`+apiKey liveness check** (success
> requires cookie `a` present and its decoded `apiKey` matching the logged-in
> user). The Layer-1 mint (the securetoken POST in `seed-ghl-auth.py`) likewise
> uses a bounded retry. **A single-shot activate** (`auth/get` + `router.push`
> with no surrounding retry), **a post-seed reload / re-navigation to the app
> root**, a **`hasPwd`-only ("no password box") liveness** test, and a
> **hardcoded `/location/<id>` route** in the activate path are **BANNED
> REGRESSIONS**. They caused the intermittent `ACTIVATE-BOUNCED-TO-LOGIN` race
> (the activate fired before the Vuex auth store warmed up and re-read the
> freshly-written cookies). All of the above is CI-enforced by
> **`scripts/guard-ghl-activation-resilience.sh`**, which sits alongside the
> auth-MODEL guard **`scripts/guard-ghl-token-only.sh`** (refresh-token seed
> ONLY — no auto UI-login / password / 2FA). The two GHL auth guardrails are
> companions: one protects the auth *model*, the other the activation *resilience*.

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
- A0.1 Auth: `seed-ghl-auth.py --check` must report `refresh-token` — that is the
  ONLY automatic auth path. Any other result (`none`) means **STOP**: the operator
  re-grabs the client's refresh token (Token Grabber). The check NEVER authorizes
  an automatic UI login; `manual_login_creds_present` is informational only.
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

### A1. Session — token-seed ONLY (no UI login)
- A1.1 Seed auth via §2 (`seed-ghl-auth.py` → `inject-ghl-auth.sh`) BEFORE
  navigating. `inject-ghl-auth.sh` opens the origin ONCE (`--pre-open`, so
  IndexedDB exists + the SPA mounts), then activates IN-APP via
  `$store.dispatch('auth/get')` + `$router.push('/')`. The refresh token alone
  logs the SPA in. **Do NOT reload or re-`open`/re-navigate to the app root after
  the seed** — that re-runs the boot IIFE, which `signOut()`s and wipes the
  seeded session (login bounce). Activate via the SPA's own router only.
- A1.2 After activation, `snapshot -i` → confirm the **dashboard** (a manual
  visual check). Gate #1 (the Sign-in form) is captured ONLY so the agent can
  DETECT it and STOP — it is **never filled** by the build loop.
- A1.3 VERIFY (positive liveness — NOT "no password box"): success requires
  cookie `a` to be present AND its decoded `apiKey` to match the logged-in user
  (the `inject-ghl-auth.sh` activation already asserts this and prints
  `activated:userId=…`). Treat "no password field visible" alone as INSUFFICIENT.
  CI-enforced by `scripts/guard-ghl-activation-resilience.sh`.
- EDGE not-logged-in / expired token: re-seed ONCE (re-run §2.1 to mint a fresh
  ID token from the same refresh token). If the dashboard still does not appear →
  **STOP and report (non-zero)**. Do NOT fill the Sign-in form, do NOT trigger
  two-factor. The operator re-grabs a fresh refresh token (Token Grabber) and
  retries the seed. Never loop silently, never auto-open the form.
- EDGE Sign-in form / two-factor screen shows: this means the seed did not log in
  (token revoked). **STOP and report** — capture a screenshot to disk and surface
  to the operator. **Stay headless (D6) — NEVER open a window. NEVER auto-fill the
  form or bypass two-factor.** The fix is a fresh refresh token, not a UI login.
- MANUAL recovery (operator only, §2.2): `GHL_AGENCY_EMAIL`/`GHL_AGENCY_PASSWORD`
  is a documented last resort the operator may run BY HAND; the build loop never
  invokes it.

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

**PARALLEL SAVES (cap 5) — PRIMARY approach:** SINGLETON POOLED BROWSER — one
session, lock=1, TTL, guaranteed teardown, reaper backstop. When executing REST
autosave (§5.2) across multiple pages, use
`ghl_builder.emit_batch_rest_save_plan(pages, session)` + `parallel_saves.sh
run-batch` to fan out up to `AB_SAVE_CONCURRENCY` (default 5, hard-clamped
[1,5]) concurrent `agent-browser eval` calls against the ONE singleton session.
`AB_MAX_SESSIONS` STAYS 1. The batch plan carries EXACTLY ONE teardown_browser
step at the end. The lock / TTL / breaker / EXIT-trap teardown from
browser_manager.sh cover the entire batch unchanged — no per-iteration session
names, no per-page teardown during the fan-out.

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

> **SUPERSEDED-FOR-CONTENT:** the A8–A13 visual click-path (blank section →
> full-width → Custom Code element → paste → Save → Preview → Publish) is the
> **fallback**. For any edit the page-data blob can express (image swap,
> Custom-Code value, tracking code), use the **REST autosave recipe below** — it
> is the primary path and round-trips to byte-identical. Keep A8–A13 only for
> UI-only actions with no REST equivalent.

### A-REST. REST autosave recipe (primary — the cracked canvas-REST path)

The canonical content build/edit flow. Emitted as an ordered eval-step plan by
`ghl_builder.emit_rest_save_plan(...)` (which orchestrates `tools/ghl_rest_canvas.py`);
the agent runs each step's `eval`/`argv` **inside the seeded agent-browser**.
All routes here are on `backend.leadconnectorhq.com` and are **Cloudflare-WAF
gated (error 1010 from bare Python)** — they MUST run in-browser so the request
inherits the CF clearance + browser UA. (The media-upload + Skill-44 ecosystem
routes are a *separate* auth model — `services.leadconnectorhq.com` + a Bearer
location PIT — and run from bare Python; never route those through this plan.)

**0. Auth (token-only — reuse verbatim, never reload).** `seed-ghl-auth.py` mints
   the Firebase `id_token`; that value is the `token-id` header on every call
   here. `Authorization: Bearer <id_token>` is the WRONG scheme (401). Activate
   the session via `inject-ghl-auth.sh` (`store.dispatch('auth/get')` +
   `$router.push`) and navigate onto the GHL origin first — **never reload** (a
   reload re-runs the boot IIFE → `signOut()` → login bounce).

**1. Stage the token via a python-WRITTEN JS file** (`rc.write_token_js_file` →
   `window.__VT = <json.dumps(token)>`), fed to `agent-browser eval --stdin`.
   **NEVER bash `${VAR@Q}`** — zsh mangles a JWT under `${VAR@Q}` to an
   empty/garbled token → a spurious 401 that looks exactly like an auth failure
   but is not (this was the single thing that initially looked like auth breakage
   in validation and wasn't).

**2. READ** `GET /funnels/page/<PAGE_ID>?locationId=<LOC>` (`token-id`; channel
   `APP`, source `WEB_USER`, version `2021-07-28`) → 200. The body carries the
   **numeric** `pageVersion` (the LIVE pointer) and a signed
   `pageDataDownloadUrl`. Fetch that signed URL **with NO auth header** to get
   the editable DOM blob. Keep this pristine blob — it is the revert baseline.

**3. SPLICE** the edit (pure transform, `rc.edit_element_customcode`): set
   `sections[s].elements[e].extra.customCode.value.rawCustomCode` to the new
   value (e.g. the marker + a real `<img src=<public CDN url>>`). The transform
   returns a COPY — the pristine baseline is never mutated.

**4. AUTOSAVE (DRAFT)** `POST /funnels/builder/autosave/<PAGE_ID>` with body
   `{funnelId, pageData:<edited>, pageVersion:<numeric n+1>, pageType:"draft",
   manualSave:true, integrations:<passthrough>}` → 201 (returns a new signed
   `pageDataDownloadUrl` + `traceId`). `pageVersion` MUST be a **number** (a UUID
   422s: "pageVersion must be a number"). `pageType:"draft"` is what keeps it
   UNPUBLISHED — the LIVE `pageVersion` pointer never moves; only the append-only
   draft `versionHistory` advances. `publish` is gated by `may_publish(approval)`
   — **default DRAFT**.

**5. VERIFY** — re-read the **canonical record's OWN** `pageDataDownloadUrl`
   (re-issue step 2) and confirm the edit is present AND (when draft) the record
   `pageVersion` is unchanged. For the preview, `ghl_builder.verify_url(preview_url,
   marker)` → HTTP 200 AND marker present (never trust no-error). Ledger →
   `previewed`.

**6. REVERT (reversibility, byte-identical)** — re-POST the **pristine** baseline
   `pageData` (the bytes from step 2) as a new draft version → 201; the canonical
   re-read is byte-identical (`rc.is_byte_identical` / `blob_md5`). The live
   pointer never moves. Residual: this appends a draft history row — there is no
   clean single-version delete (GHL auto-prunes draft history at ~30); the
   reversibility bar is "live pointer unchanged + content byte-identical", NOT
   "zero extra draft rows".

**Workflow read+rewire (`emit_workflow_rewire_plan`):**
`GET /workflow/<LOC>/<WF>?includeTriggers=true` (read — the `?includeTriggers=true`
query is **LOAD-BEARING**; the bare detail omits `triggers[]`, and a verifier
reading the bare call sees zero triggers and wrongly reports the rewire failed)
→ `PUT /workflow/<LOC>/trigger/<TR>` with the whole trigger record + the changed
fields → 200 `{"status":"success","message":"Trigger updated successfully"}` →
re-read WITH `?includeTriggers=true` and assert the changed field is present.

**Load-bearing gotchas (both live validators hit these — §4 of the solution doc):**
1. **Cloudflare WAF (1010):** the GET/POST/PUT MUST run inside the agent-browser
   `eval` (it carries CF clearance + browser UA). Bare Python to the
   funnels/builder origin is blocked. Navigate onto the GHL origin first.
2. **Token staging — NOT bash `${VAR@Q}`** (mangles the JWT → spurious 401);
   stage via a python-written JS file (`window.__VT = <json.dumps(token)>`).
3. **`pageVersion` is a NUMBER** on the page record; draft save = `n+1`; a UUID
   422s.
4. **`pageType:"draft"` keeps it unpublished** — the live pointer never moves;
   only append-only draft `versionHistory` rows accrue (auto-pruned ~30).
5. **Signed page-data URL has no auth** — fetch the blob directly from the
   read/save response's `pageDataDownloadUrl` (no header).
6. **Never reload after seeding** (re-runs the boot IIFE → `signOut()` → login
   bounce); activate via the SPA's own `$router.push`.

**Honest residual (unchanged):** going LIVE still requires a CLIENT "Connect
Domain" step — never automated. Automation only ever produces `/preview/<PAGE_ID>`
URLs; preview + draft saves are the bar. Never fake go-live.

---

## PART B — WEBSITE PAGE BUILD (only when client says "Website")

Default is Funnels. Website mirrors Part A but with the following DIFFERENCES,
all **LIVE-CONFIRMED** by the 2026-06-21 D11 end-to-end run on the BlackCEO LLC
operator test fixture (Website created → page built → Code element → preview
HTTP 200 + marker rendered, left DRAFT):
- B3 **Websites tab (GATE #23)** is an ANCHOR `<a href=".../funnels-websites/
  websites">`, NOT an ARIA `role=tab` (so `find role tab name Websites` MISSES it).
  Click the `<a>` whose exact trimmed text is `Websites` (same orange top-tab row
  as Funnels). It navigates to `.../funnels-websites/websites`.
- B4 **+ New website (GATE #24)**: blue `+ New website` button top-right (do NOT
  click the adjacent `Build with AI`). The `Create new website` modal has TWO
  cards only — `From blank` (carries the `Website name *` input, placeholder
  `e.g. Sales website`) and `From templates` (NO `Build with AI` card inside the
  modal). Type the `zhc` name → `Create`. The SPA then lands on the website
  DETAIL view `.../funnels-websites/websites/<WEBSITE_ID>/pages` (sub-tabs
  Pages|Stats|Sales|Security|Events|Settings) — it does NOT open a builder yet.
- B5 **Add page (GATE #25)**: on the detail view click blue `+ Add new page` →
  `New page for website` modal (`Name for page *`, `Path`, optional ClickFunnels
  import) → `Create new page`. The new page appears as a CONTROL box (`Use
  existing` | `Create from blank`); click **`Create from blank`** to open the
  builder at `/location/<LOCID>/page-builder/<PAGE_ID>?source=website`.
- B6–B13 the builder is the **SAME editor as the Funnel builder** — every editor
  gate (13 Blank Section, 15 Quick Add→Custom→Code, 16 Open Code Editor, 17 modal
  Save, 18 close Ask AI, 19 page Save disk, 20 Preview eye, 21 Publish) works
  IDENTICALLY. The Quick Add `Custom` group → `Code` drops a `Custom HTML/
  Javascript` element; right-panel `Open Code Editor` (renders on the MAIN page)
  opens the `Custom Javascript/HTML` CodeMirror modal. Preview URL pattern:
  `https://www.<preview-domain>/preview/<PAGE_ID>`.
- **ENGINE LIMIT (same as Funnels):** the canvas + Quick Add live in a
  CROSS-ORIGIN iframe (`page-builder.leadconnectorhq.com`) whose interior the
  a11y snapshot does NOT enumerate. Drive the section `+` Add and the `Code` tile
  with REAL pointer events (double-click-add); synthetic JS clicks / drag do NOT
  land. Set the CodeMirror value via `.CodeMirror.setValue()` inside the editor
  frame, not key-by-key. (Refs that the top-level snapshot DOES expose — e.g.
  `Close Ask AI`, `Blank Section`, the main-page `Open Code Editor` — are
  clickable normally.)
- **Do NOT assume every Website selector equals the Funnel selector** — the
  tab/create/add-page LABELS differ (above). The editor itself is identical.

---

## PART C — MODE 2: IFRAME EMBED (payload too rich for a Code block)

For full Vercel builds (React/external deps) that cannot live in a Code element.
**LIVE-CONFIRMED** by the 2026-06-21 D10 run on the BlackCEO LLC operator test
fixture (iframe Code element built → preview rendered the embed live, embed
child-frame HTTP 200 + real content, left DRAFT).
- C1 Host externally on Vercel (Skill 08). VERIFY **first, with `curl -D-`**: the
  target must return HTTP 200 AND carry NO `X-Frame-Options: DENY` and NO
  restrictive CSP `frame-ancestors`. **Vercel trap:** a default Vercel deployment
  has Deployment Protection (SSO) ON → it returns `HTTP 401` + a
  `_vercel_sso_nonce` cookie + `x-frame-options: DENY` and is NOT embeddable. Only
  a PUBLIC Vercel deployment (protection disabled) with no frame-blocking headers
  can be embedded — confirm before building.
- C2 In the GoHighLevel page (Part A through A9, or the Website builder Part B),
  the Code element's payload is a single responsive
  `<iframe src="<embeddable-url>" style="width:100%;height:600px;border:0">` sized
  to the section (GATE #26, same element as A10/gate 16). Set it via CodeMirror
  `.setValue()`.
- C3 Save (gate 17) → page Save (gate 19) → Preview (gate 20). VERIFY both: (a)
  `ghl_builder.verify_url(preview_url, <embed-src-substring>)` → 200 + the iframe
  src present in the GHL page body; AND (b) load the preview in the headless
  browser, locate the embed `<iframe>`, and confirm its CHILD FRAME actually
  loaded (child-frame HTTP 200, real content text length > 0) — never report
  "embed works" on the iframe tag alone. Publish only with approval (A13).
- EDGE X-Frame-Options / CSP: if the source app sends `X-Frame-Options: DENY` or
  a restrictive `frame-ancestors`, the embed is blank → set the source app's
  headers to allow GoHighLevel's published domain as a frame ancestor (GATE #28 —
  the domain is only knowable from a published page).

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
sub-account mismatch (A2.3 hard gate) · seed fails to log in / Sign-in form or
two-factor screen shows (A1 — STOP + report, NO auto UI login/2FA; operator
re-grabs the refresh token) · token expiry mid-build (re-seed from the same
refresh token, retry-once) · duplicate funnel/website name +
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
