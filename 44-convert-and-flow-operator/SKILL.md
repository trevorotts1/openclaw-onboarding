---
name: convert-and-flow-operator
description: Tier 0 GHL operator — the Convert and Flow CLI (caf/convertandflow/ghl) gives the agent direct CRM access for contacts, opportunities, calendars, conversations, documents, payments, forms, social, locations, and workflow builds via internal API (no MCP overhead). Standard ops run on the PIT alone. Workflow writes additionally require the Firebase refresh token; when absent, falls through to Tier 4 agent-browser as the backstop. Write-safe by default (dry-run, draft-only, location whitelist, approval gate).
---

# Skill 44 — Convert and Flow Operator (Tier 0)

## Teach Yourself Protocol read-order

1. **SKILL.md** (this file) — overview, CLI surface, credential model, write-safety posture
2. **INSTALL.md** — autonomous setup, venv, wrapper, `caf doctor`
3. **INSTRUCTIONS.md** — day-to-day usage, natural language intents, TRINITY routing, rollback
4. **CORE_UPDATES.md** — exact text to merge into AGENTS.md / TOOLS.md / MEMORY.md
5. **QC.md** — human-readable checklist (authoritative script is `qc-convert-and-flow.sh`)
6. **CHANGELOG.md** — skill version history

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
- **workflows** (READ-ONLY on PIT) — list, get, export

### Workflow BUILD and EDIT (Firebase token required)

`workflows build`, `workflows patch-email`, `workflows patch-trigger`, `workflows restore`
require the `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN`. When that token is:
- **present + healthy** — Tier 0 builds/edits the workflow directly via the internal API.
- **missing or expired** — reads fall through Tiers 1-3; BUILD falls to Tier 4 (agent-browser) as the
  no-token backstop, and the owner is nudged: "I need you to grab the Convert and Flow token to build
  workflows directly." Nothing is silent.

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

All three legs ship together or the build is NOT registered. Skill 44's QC calls
`38/scripts/qc-trinity-registry.sh` as a hard gate before registration.

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

---

## Files in this folder

1. SKILL.md (this)
2. INSTALL.md — setup + `caf doctor` + Chrome extension load-unpacked steps (Action 5b)
3. INSTRUCTIONS.md — runtime usage, TRINITY routing, rollback recipe
4. CORE_UPDATES.md — text to merge into core files
5. QC.md — checklist (authoritative: `qc-convert-and-flow.sh`)
6. CHANGELOG.md
7. skill-version.txt
8. qc-convert-and-flow.sh — automated QC validator
9. platform/mac/ — Mac-specific paths + auto-re-grab recipe
10. platform/vps/ — VPS-specific paths
11. tools/engine/ — de-branded CLI engine (vendored from Jay's zip)
12. tools/chrome-extension/ — Token Grabber Chrome extension (client-facing; load unpacked)
