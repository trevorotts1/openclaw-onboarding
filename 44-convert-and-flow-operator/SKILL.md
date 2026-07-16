---
name: convert-and-flow-operator
description: Tier 0 GHL operator — the Convert and Flow CLI (caf/convertandflow/ghl) gives the agent direct CRM access for contacts, opportunities, calendars, conversations, documents, payments, forms, social, locations, and workflow builds via internal API (no MCP overhead). Standard ops run on the PIT alone. Workflow writes additionally require the Firebase refresh token; when absent, falls through to Tier 4 agent-browser as the backstop. Write-safe by default (dry-run, draft-only, location whitelist, approval gate).
---

> **GHL PIT aliases:** `GOHIGHLEVEL_API_KEY` is the preferred name; 10 additional aliases resolve the same LOCATION PIT. See **`TERMINOLOGY.md`** (repo root) for the canonical alias set and backend-equivalence notes (Convert & Flow / leadconnectorhq.com = one platform).

# Skill 44 — Convert and Flow Operator (Tier 0)

## READ-BEFORE-ACT — Model Check + PLAN MODE + QC GATE (workflow builds)

**Full-Funnel Pipeline Role (P5 seam):** In a full-funnel build (SOP-07 P5 stage), this
skill receives APPROVED copy + funnel page IDs from Skill 6 (06-ghl-install-pages). It
does NOT author copy or business rules — it wires ONLY what P2e (Email Campaign Strategist)
and P4 (Skill 6 / funnel builder) have produced and delivered. The P4→P5 handoff is:
`page_ids` + opt-in form IDs from Skill 6, plus the APPROVED email sequence copy from P2e.
The P5 task MUST verify: subaccount_matches (location whitelist gate), WF-1..21 PASS, rubric
≥ 8.5. Never begin P5 without confirmed APPROVED copy from P2e and verified page_ids from P4.

**Step 0 — Model Check (before any BUILD or MODIFY):** If the active session model is a
lighter/non-high-reasoning model or thinking is not HIGH, surface the recommendation to the
owner first, then proceed. Recommendation gate, not a hard block. Read-only ops skip this.
NOTE: If Step 9 QC catches a HALLUCINATION, this recommendation FLIPS TO A HARD REQUIREMENT.

**Step 0.5 — PLAN MODE (before any new workflow CREATE/BUILD):** BINDING GATE — do NOT
touch `caf workflows build` or the Tier 4 backstop until the plan is presented and the two
gating questions are answered. Steps: THINK (result + expectations + best approach) →
DEPENDENCY PRE-CHECK → OUTLINE → CHECKLIST (instantiate references/workflow-build-checklist-template.md) →
IMPROVEMENTS → PRESENT + GATING QUESTIONS (publish: DRAFT vs LIVE? / re-entry: once vs
allow-multiple?). Rushing to a default build is NOT the best outcome and is a VIOLATION.

**Step 9 — QC GATE (before declaring done):** BINDING GATE — the build agent MUST NOT say
"done" until an independent MiniMax QC sub-agent passes all checklist items and the filled
checklist is handed to the client. Sequence: announce to client → spawn MiniMax sub-agent
(via sessions_send, verify model available first) → QC runs `caf workflows export` +
`qc-built-workflow.sh <wf-id>` item-by-item → all WF-1..21 PASS → THEN compute the **weighted
quality rubric** (`references/workflow-quality-rubric.md`, 8 dimensions, ≥ 8.5 to ship) → hand
client the filled checklist + the rubric score. The rubric is a SUPERSET OVERLAY computed AFTER
WF-1..21, never instead of it. Any WF FAIL: fix + re-run QC. Rubric below 8.5: loop, naming the
specific low dimension. HALLUCINATION FAIL: hard stop + redo on reasoning-model thinking=HIGH.

---

## Teach Yourself Protocol read-order

1. **SKILL.md** (this file) — overview, CLI surface, credential model, write-safety posture
2. **INSTALL.md** — autonomous setup, venv, wrapper, `caf doctor`
3. **INSTRUCTIONS.md** — day-to-day usage, Step 0.5 PLAN MODE, natural language intents,
   TRINITY routing, Step 9 QC GATE (including hallucination escalation), rollback
3b. **automation-templates/** — the **28-template automation library** (template-first / reuse-
   before-reinvent) + `automation-templates/README.md`. Matched at INSTRUCTIONS Step 0.4 via
   `_matcher/cli.py --match` (shared core `_matcher/flex.py`, committed lexical index
   `_matcher/catalog-index.json`). `_links/funnel-to-automation.json` is the canonical funnel→
   automation map. Flexibility = guide-not-rule (honor explicit spec; CREATE_NEW only when nothing fits).
4. **references/workflow-build-checklist-template.md** — canonical WF-1..WF-21 checklist
   (instantiate at PLAN MODE Step D; hand to client after QC passes)
4b. **references/workflow-quality-rubric.md** — 8-dimension weighted quality rubric (SUPERSET
   overlay on WF-1..21; each dimension cites its WF evidence source; ≥ 8.5 to ship; computed at
   Step 9 AFTER WF-1..21)
4c. **universal-sops/funnel-automation-build-quality-rubric.md** — the library-aware FAB-QC ≥ 8.5
   overlay (shared scorer `shared-utils/fab_qc.py`); run at Step 9.3c via `qc-built-workflow.sh --fab`
5. **qc-built-workflow.sh** — per-build QC script (mechanically asserts WF-3,4,5,6,7,12,15,18,21;
   then emits the weighted rubric floor score + the FAB-QC overlay with `--fab`); invoked by the
   MiniMax QC sub-agent at Step 9
6. **CORE_UPDATES.md** — exact text to merge into AGENTS.md / TOOLS.md / MEMORY.md
7. **QC.md** — human-readable checklist (authoritative install-QC script is `qc-convert-and-flow.sh`)
8. **CHANGELOG.md** — skill version history

Store only lean references in core files; full runtime docs live in this folder + master-files.

---

## What This Skill Is

Skill 44 is the **Tier 0** in the 6-tier GHL access chain (skill 36). It wraps the
Convert and Flow CLI engine and exposes it through three aliases:

```
caf           # shortest
convertandflow
ghl
```

The CLI gives the agent DIRECT CRM access over the GHL internal API — no MCP schema
overhead, no browser, no manual paste. Natural-language requests in Telegram map to CLI
commands automatically; operators never need to memorize command syntax.

### What Tier 0 covers (standard ops — PIT only)

- **contacts** — search, get, create, update, tag, untag, bulk operations
- **opportunities** — list, get, update, move pipeline stage
- **calendars** — list calendars, get appointments, create/update bookings
- **conversations** — list, get, send message, read threads
- **documents** — list, get, send
- **payments** — list invoices, create invoice, send invoice, list transactions
- **forms** — list, get submissions
- **social** — list accounts, schedule post, get post status
- **locations** — get location info, list custom fields, list custom values
- **workflows** — `list` is READ-ONLY on the LOCATION PIT (Tier 0). BUT `get` and `export`
  route through the INTERNAL Firebase client and REQUIRE the Firebase refresh token — they are
  NOT PIT reads (see "Workflow BUILD and EDIT" below; the same token gates read-back). With no
  Firebase token, `get`/`export` cannot run and workflow QC falls to the Tier-4 agent-browser
  read-back (fail-closed — "no token" never means "skip QC").

### Sub-agent contact lookup rule (CRITICAL)

MCP tools (`ghl-mcp__*`) are available ONLY in the orchestrating agent session. Spawned
sub-agents receive NO MCP tool injection. **Any contact lookup inside a sub-agent MUST
use `caf contacts search/get` (the CLI) or raw HTTPS to `services.leadconnectorhq.com`.**

The CLI is a subprocess — it works identically in the orchestrator and in sub-agents.
This is the primary reason Tier 0 CLI is preferred over the orchestrator-only MCP path
for lookups. See `36-ghl-mcp-setup/GHL-LOOKUP-SOP.md` for the full lookup routing table.

### Workflow BUILD and EDIT (Firebase token required)

`workflows build`, `workflows patch-email`, `workflows patch-trigger`, `workflows restore`
require the `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN`. When that token is:
- **present + healthy** — Tier 0 builds/edits the workflow directly via the internal API.
- **unread / misconfigured** (e.g. the token exists in a store the process did not resolve, or a
  key-name/env-store mismatch) — BUILD falls to **Tier 4: Skill 6's GATED, MANAGED Automations builder**
  (the designated path, IMPLEMENTED — `06-ghl-install-pages/tools/ghl_workflow_builder.py`, routed through the
  `browser_manager.sh` singleton gateway, resolving its steps from the `automations_builder_gates` registry
  in `tools/gates.json` — NEVER bare agent-browser freehand at `app.gohighlevel.com`), and the
  owner is nudged: "I need you to grab the Convert and Flow token to build workflows directly." Nothing is
  silent.
  > **Tier-4 builder implementation status (P3-08):** the HARNESS is BUILT and unit-tested —
  > `06-ghl-install-pages/tools/ghl_workflow_builder.py` drives the Automations builder end-to-end through
  > the `browser_manager.sh` singleton gateway (guaranteed teardown, reaper backstop) and REFUSES
  > (`MissingGateError`) if a required gate is absent rather than freehand-navigate. Proof:
  > `06-ghl-install-pages/tests/test_ghl_workflow_builder.py` drives a **token-unset** build through the
  > gated path, quotes the built workflow id, and asserts zero-orphan teardown; `python3
  > 06-ghl-install-pages/tools/ghl_workflow_builder.py --selftest` is the runnable one-liner. The Automations
  > STEP SELECTORS ship `status: runtime` (accessibility role/name find hints the harness resolves against
  > the live DOM) — Skill 6's "NO invented CSS is shipped as fact" law forbids asserting them as captured, so
  > a live-capture hardening pass on the operator's own GHL location flips each to `captured` in
  > `SELECTORS-LIVE-automations.md` (the ordinary runtime-gate follow-on). The CI guard protecting this path
  > is live — `06-ghl-install-pages/` and `44-convert-and-flow-operator/` are scan roots of
  > `scripts/guard-agent-browser-managed.sh`, so any unmanaged spawn here FAILS CI (P3-08 step 1). When even
  > the managed browser session cannot seed, the human-in-loop Build-with-AI paste (Skill 41 Layer 0) is the
  > fallback.
- **genuinely dead / revoked / expired** — Tier 4 does NOT help (see the token-circularity note below);
  route to `06-ghl-install-pages/tools/ghl_auth.py`'s gated Tier-2 email-2FA self-heal, which mints a
  fresh token so the next run is Tier 0 again.

> **TOKEN CIRCULARITY (P3-08 — read this before relying on Tier 4).** Tier 4 is NOT a universal
> no-token backstop. The managed browser session Tier 4 needs is **seeded from the SAME
> `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN`** whose absence supposedly triggered Tier 4 (Skill 6's
> `browser_manager.sh` reuses the Firebase-token session seed). So Tier 4 only helps when the token is
> **unread or misconfigured** — present but not resolved by the process. When the token is **genuinely
> dead** (revoked, expired, wrong client), Tier 4 cannot seed a session either, and the ONLY recovery is
> `ghl_auth.py`'s gated Tier-2 email-2FA self-heal (gated on recorded authorization + a live Gmail
> read-proof + email-2FA method + client-owned creds), which logs in headless, reads the freshest 2FA code
> from the client's own Gmail, and SELF-HEALS a fresh refresh token into the client store. Decision rule:
> **token unread/misconfigured → Tier 4 gated builder; token genuinely dead → ghl_auth.py Tier-2
> self-heal, never Tier 4.** (Skill 36 `GHL-LOOKUP-SOP.md` RULE 6 encodes the same routing.)

> **GHL-AUTH-DOCTRINE: TIER-2 EMAIL-2FA FALLBACK — gated (auth+gmail-proven+email-2fa+creds), bounded, self-heals to TOKEN-ONLY.**
> The canonical auth entry point Skill 44 calls when a workflow write needs a session is the shared
> orchestrator `06-ghl-install-pages/tools/ghl_auth.py` (a 3-tier ladder) — Skill 06 and Skill 44 both call
> it, never the fallback directly. Tier 1 (token-only — the `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` seed above)
> stays PRIMARY; almost every build takes it. ONLY when Tier 1 has no usable token (absent / revoked /
> expired) does the orchestrator evaluate the GATED Tier-2 email-2FA bootstrap: gate A a recorded client
> authorization, gate B the box PROVES it can read the client's OWN Gmail via a live read BEFORE any login
> (so a misconfigured box never starts a login it can't finish), gate C email is the selected 2FA method,
> gate D agency creds resolve from the CLIENT's own secret store. On all four green it logs in headless,
> reads the freshest email-2FA code from the client's own Gmail, submits it, and on success SELF-HEALS a
> fresh `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` into the client store so the very next run is Tier 1 again.
> Bounded: `MAX_LOGIN_ATTEMPTS <= 3`, backoff, hard-stop on any lockout/captcha. Any gate fail or hard
> stop → Tier 3: fail loud, non-zero exit, precise client instruction (then the Tier-4 agent-browser
> backstop / Token-Grabber nudge above). ALL login/password/2FA code lives in EXACTLY ONE module
> (`tools/ghl_auth_fallback.py`) plus its browser helper (`tools/ghl_login_browser.py`); CI guard
> `scripts/guard-ghl-auth-fallback.sh` locks the invariants. Client uses their OWN creds/keys ONLY;
> secrets NEVER in repo/logs/stdout.

### Media

The CLI has NO media upload commands. Media NEVER routes to Tier 0 — always Tier 3
(`POST /medias/upload-file` — see `29-ghl-convert-and-flow/references/medias.md`).

---

## Credential model

| Env var | Required for | Canonical name |
|---|---|---|
| `GOHIGHLEVEL_API_KEY` | All ops (location PIT) | canonical; `CAF_API_KEY` accepted as alias |
| `GOHIGHLEVEL_LOCATION_ID` | All ops | canonical; `CAF_LOCATION_ID` accepted |
| `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` | Workflow write/edit | canonical; `CAF_FIREBASE_REFRESH_TOKEN` accepted |
| `GOHIGHLEVEL_ALLOWED_LOCATION_IDS` | Write whitelist | comma-separated; empty = single-location default |
| `GOHIGHLEVEL_DRAFT_ONLY` | Write safety | `true` = no live publishes without approval |

The wrapper at `~/.openclaw/tools/convert-and-flow-cli/caf` maps the canonical env names
to whatever the engine expects at runtime (engine internals untouched).

**Unified 11-alias scan (as of this update):** `ghl_client._get_token()` now scans all 11
env-var names in the LOCATION-PIT alias set (`GOHIGHLEVEL_API_KEY` canonical + 10 aliases)
before raising a credential error. This closes the prior crash-loop where a box storing the
token under a legacy alias (e.g. `GHL_API_KEY` or `PIT_TOKEN`) would surface
`CredentialNotFoundError` and spin the agent into a retry loop. Agency PITs and the Firebase
refresh token (`GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN`) are not part of this scan and remain
on separate paths.

---

## Write-safety posture

1. **Dry-run flag** — `--dry-run` shows the API call without firing it. The agent ALWAYS
   dry-runs a destructive write first and surfaces the diff before executing.
2. **Draft-only default** — `GOHIGHLEVEL_DRAFT_ONLY=true` means content writes (workflows,
   social posts) default to draft status; a second approval step is required to publish.
3. **Location whitelist** — writes are restricted to `GOHIGHLEVEL_ALLOWED_LOCATION_IDS`; a
   cross-location write attempt is rejected before the API call.
4. **Approval gate** — `ZHC-` and `ZHC_` prefixed objects carry standing approval per skill
   41's contract; all other programmatic creates surface to the owner for confirmation.
5. **Workflow-write data rollback** — every `workflows update`/`patch-email`/`patch-trigger`
   writes a timestamped snapshot to
   `~/.openclaw/tools/convert-and-flow-cli/data/snapshots/<location>/<workflow-id>/<ts>.json`
   BEFORE mutating. `workflows restore <snapshot-path>` replays the snapshot.
6. **Internal-write serialization** — a lock file under the data dir prevents concurrent builds
   from the same box.

---

## TRINITY rule (skill 38 auto-invoke)

Any workflow that contains a conversational node MUST produce all three legs:
1. GHL automation (skill 44 builds the structure)
2. Communications playbook (skill 38 auto-invoked for the brain)
3. Workflow-AI / Build-with-AI prompt (skill 38 generates)

All three legs ship together or the build is NOT registered. Skill 44's per-build QC ENFORCES
this mechanically: run `./qc-built-workflow.sh <workflow-id> --conversational`, which EXECUTES
`38/scripts/qc-trinity-registry.sh` and FAILs WF-19 on any non-zero exit (incomplete TRINITY or
missing `conversation-workflows/` folder). Without `--conversational`, WF-19 is N/A (human
review) — correct for a purely mechanical workflow with no conversational leg.

---

## Dependency-first contract (from skill 41)

Skill 44 REFUSES to build a workflow whose dependencies (tags, custom fields, custom
values) do not yet exist in GHL. It checks each dependency with a GET first (skill 41
Step 2 pattern) and surfaces missing items before touching the workflow builder.

---

## Chrome Extension: Token Grabber (load unpacked)

The skill ships the Token Grabber Chrome extension at `tools/chrome-extension/`.

**This extension is NOT on the Chrome Web Store.** Clients load it via Chrome's
"load unpacked" developer method (see INSTALL.md Action 5b for the full steps).

**What it does:** reads `stsTokenManager.refreshToken` from the page's
`firebaseLocalStorageDb` IndexedDB on `convertandflow.com`, `gohighlevel.com`, or
`leadconnectorhq.com`, and copies it to clipboard. Makes **zero network calls**.

**Token env var:** `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN`

The files in `tools/chrome-extension/`:
- `manifest.json` — MV3 manifest (permissions: activeTab, scripting, clipboardWrite)
- `popup.html` — extension popup UI
- `popup.js` — IndexedDB reader
- `icon48.png` — extension icon

These are identical to the `convert-and-flow-token-grabber.zip` the operator ships.
The same four files also exist inside `tools/engine/chrome-extension/` (that copy is
for the engine's own reference); `tools/chrome-extension/` is the client-facing copy.

### Owner-facing setup guide

For walking an OWNER through grabbing the token (warm, plain-English, 8 steps + the
public download link), send or read from `references/owner-token-grabber-guide.md`.
That doc is what a client agent uses to get a non-technical owner from zero to a working
Firebase token; it also carries a clearly-separated **FOR THE AGENT** section on wiring
the pasted token into the gateway-inherited env and building the first DRAFT-only,
`ZHC-` prefixed test workflow.

### Fleet announcement (standardized owner message + send runbook)

Once a box has been **given Skill 44**, the owner gets the standardized announcement in
`references/fleet-announcement-template.md` — the canonical **3-message** template
(placeholders `[OWNER_NAME]` / `[AGENT_NAME]`: congratulations + what it unlocks, then the
🔑 FINAL SETUP Part 1 of 2 and Part 2 of 2 walkthrough that reuses the Token Grabber steps
above). The same file carries the **operator-facing fleet-send runbook**: the GATE (only
announce when the box's ledger shows skill44 remediation complete — engine ≥ 2.1.1 with a
live `caf` read, or explicitly token-pending), SEND MECHANICS (always the client's own
gateway via `openclaw message send`, one client at a time, verify each send), and per-client
RECEIPTS to the operator ledger. Do NOT paste the runbook section to an owner.

---

## Daily Firebase Token Liveness Check (Skills 44 + 46)

A daily cron (`ghl-token-liveness`, registered by `scripts/ensure-pipeline-crons.sh` at
08:00 UTC) runs `tools/check-ghl-token-liveness.sh` on every client box where Skill 44
is installed. The check:

1. Resolves `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` (env-store order: `secrets/.env` →
   `openclaw.json env.vars` → `workspace/.env`, matching the same order as
   `seed-ghl-auth.py` and the transport engine).
2. POSTs a `grant_type=refresh_token` exchange to
   `securetoken.googleapis.com/v1/token?key=FIREBASE_API_KEY` (the public Firebase web
   API key hardcoded in transport.py — not a secret).
3. Classifies the response:
   - **VALID** (HTTP 200 + `id_token` present) → logs `PASS`, writes a day-stamp file,
     exits 0. No notification is sent.
   - **INVALID** (HTTP 400, error codes `TOKEN_EXPIRED` / `USER_DISABLED` /
     `INVALID_REFRESH_TOKEN`) → sends a plain-English re-grab notification to the
     **CLIENT's own Telegram chat** (never to operator IDs) and exits 1.
4. Is idempotent: a `~/.openclaw/workspace/ghl-token-liveness/ghl-token-liveness-<date>.ok`
   stamp prevents the notification from firing more than once per calendar day.

**What the client sees if their token dies:**

> Hi — just a heads-up from your AI agent. Your workflow automation connection to
> Convert and Flow needs a quick refresh. The secure key that lets me build automations
> for you has expired. Here is how to refresh it (same steps as your original setup):
> log into Convert and Flow fresh, click the Token Grabber icon, click "Grab the token"
> then "Copy the token," and send me the copied key.

The notification guides them through the same 8-step Token Grabber flow documented in
`references/owner-token-grabber-guide.md`.

Per operator instruction this daily check is cross-referenced from **Skill 46 (Kie
Callback Relay)** as well. Note: Skill 46 does not itself use the GHL Firebase token —
the token and this check are owned by Skill 44; the cross-reference is only for
discoverability.

---

## Files in this folder

1. SKILL.md (this)
2. INSTALL.md — setup + `caf doctor` + Chrome extension load-unpacked steps (Action 5b)
3. INSTRUCTIONS.md — runtime usage, Step 0.5 PLAN MODE, TRINITY routing, Step 9 QC GATE,
   hallucination escalation, rollback recipe
4. CORE_UPDATES.md — text to merge into core files
5. QC.md — checklist (authoritative install-QC: `qc-convert-and-flow.sh`)
6. CHANGELOG.md
7. skill-version.txt
8. qc-convert-and-flow.sh — automated install-level QC validator (static + live modes)
9. qc-built-workflow.sh — per-build QC script (takes workflow-id, asserts WF-3/4/5/6/7/12/15/18/21,
   emits per-item PASS/FAIL JSON AND the weighted quality-rubric floor score; invoked by MiniMax
   QC sub-agent at Step 9)
10. platform/mac/ — Mac-specific paths + auto-re-grab recipe
11. platform/vps/ — VPS-specific paths
12. tools/engine/ — de-branded CLI engine (vendored from Jay's zip)
13. tools/chrome-extension/ — Token Grabber Chrome extension (client-facing; load unpacked)
14. tools/check-ghl-token-liveness.sh — daily Firebase token health check (Skills 44 + 46);
    VALID → exit 0 + day-stamp; INVALID → client notification via `openclaw message send`
15. references/owner-token-grabber-guide.md — owner-facing Token Grabber walkthrough (8 steps + download link) + agent wiring notes
16. references/fleet-announcement-template.md — standardized owner announcement (canonical 3-message template, `[OWNER_NAME]`/`[AGENT_NAME]`) + operator fleet-send runbook (gate, send mechanics, receipts)
17. references/workflow-build-checklist-template.md — canonical WF-1..WF-21 reusable checklist
    (agent self-check at PLAN MODE Step D + client hand-over after QC passes)
18. references/workflow-quality-rubric.md — 8-dimension weighted quality rubric (SUPERSET overlay
    on WF-1..21; each dimension cites its WF evidence; ≥ 8.5 to ship; computed at Step 9 AFTER
    WF-1..21)

> **Relationship lattice (GK-27):** see `docs/CONTENT-CONVERSATION-LATTICE.md` for how this skill's build path relates to Skill 38 and its backstop rail relates to Skill 3.
