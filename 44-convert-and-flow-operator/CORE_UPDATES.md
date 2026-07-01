# Skill 44 — Convert and Flow Operator: Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

Sentinel: <!-- skill:44-convert-and-flow-operator:core-update-applied -->

---

## AGENTS.md — UPDATE REQUIRED

Add this section:

```
## Convert and Flow Operator — Tier 0 (skill 44)

### Pre-flight: model check before any workflow build or modify
Before executing a workflow BUILD or MODIFY (caf workflows build / patch-email /
patch-trigger / restore / Tier 4 agent-browser build): check the active session model.
If it is a lighter/non-high-reasoning model or thinking is not HIGH, surface the
recommendation to the owner first (see INSTRUCTIONS.md Step 0). Then proceed — this
is a recommendation, not a block. Read-only ops skip this check entirely.
NOTE: if Step 9 QC catches a HALLUCINATION-class fail, this recommendation upgrades to
a HARD REQUIREMENT — the redo MUST use a high-reasoning model with thinking=HIGH.

### PLAN MODE — required before any new workflow CREATE/BUILD
Before touching caf workflows build (or the Tier 4 backstop, or skill 38 structure
generation) for a NEW workflow: run PLAN MODE (INSTRUCTIONS.md Step 0.5).
STEPS: THINK (restate client's desired result + expectations + best approach) →
DEPENDENCY PRE-CHECK (GET-verify all tags/fields/values exist in GHL first) →
OUTLINE (ordered trigger→nodes→exit blueprint) →
CHECKLIST (instantiate references/workflow-build-checklist-template.md with all 21 items) →
IMPROVEMENTS (surface optional upgrades, labeled as suggestions) →
PRESENT TO CLIENT + ASK THE TWO GATING QUESTIONS:
  Q1: "Draft or live?" (default = DRAFT matching CAF_DRAFT_ONLY=true)
  Q2: "Re-entry once or allow-multiple?" (default = ONCE / re-entry OFF)
Only after BOTH gating questions are answered may the agent proceed to building.
RUSHING TO A DEFAULT BUILD WITHOUT PLAN MODE IS A VIOLATION.

### QC GATE — required before declaring any workflow done
After building a workflow, do NOT say "done." STEPS:
  1. Send the verbatim client announce: "I've built the workflow. Before I call it done,
     I'm running an independent QC agent to verify it against the checklist item-by-item.
     One moment." (via openclaw message send --channel telegram)
  2. Spawn an independent MiniMax QC sub-agent (via sessions_send, verify model available
     first — prefer minimax/minimax-m3 via OpenRouter or minimax-m3:cloud; fall back to
     next independent high-reasoning model and record which was used).
  3. QC sub-agent runs caf workflows export <id> + qc-built-workflow.sh <id> item-by-item
     (WF-1..WF-21). Returns explicit PASS/FAIL + observed vs expected value per item.
  4. All-PASS → proceed to step 5. Any FAIL → fix + re-run QC.
     HALLUCINATION FAIL (agent claimed X but QC-observed NOT-X) → HARD STOP →
     mandatory redo on high-reasoning model thinking=HIGH → full re-QC → disclose to client →
     log to build-events ledger.
  5. ONLY AFTER ALL-PASS: tell client "QC passed" and hand the FILLED CHECKLIST (every WF
     item with its PASS + observed value) to the client for independent verification.
NEVER declare a workflow done before independent MiniMax QC passes + filled checklist handed over.

Skill 44 is the FIRST STOP in the 6-tier GHL access chain. Try it before any MCP.

### When to use Tier 0

- Any GHL operation the CLI covers (contacts, opportunities, calendars, conversations,
  documents, payments, forms, social, locations, workflow reads): use `caf <command>`.
- Workflow BUILD or EDIT: check Firebase token first (see token-aware routing in skill 36
  AGENTS.md). Present + healthy = Tier 0 builds directly. Absent = Tier 4 backstop.
- AGENCY OPS — TWO DIFFERENT auth paths, do not cross them:
  - CREATE SUB-ACCOUNT (location): `caf --experimental locations create ...` → internal
    Firebase API (`POST backend.leadconnectorhq.com/locations/`, header `token-id`,
    `version: 2021-07-28`). The id-token comes from the Chrome-extension Token Grabber
    (reads GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN from the agency-owner browser session) and is
    SHORT-LIVED — re-grab before writes. This is the ONLY working create-location path
    (public API/PIT cannot create a location).
  - ADD USER: `caf locations add-user ...` → agency PIT + PUBLIC API
    (`POST services.leadconnectorhq.com/users/`, `Authorization: Bearer <agency PIT>`,
    `Version: 2023-02-21`). This is the proven, simpler path (how the real user was added) —
    NO Firebase token / NO Chrome extension. Omit `--password` so GHL sends the invite email.
  - USER TYPE: add-user DEFAULTS to `--type account` (a SUB-ACCOUNT user scoped to
    `--location-id`; `--role admin` = admin of that sub-account ONLY). `--type agency`
    (an AGENCY-wide user) is REFUSED unless `--i-understand-this-is-an-agency-user` is also
    passed. Adding a user to a client's sub-account must NEVER make them an agency user.
  - OAuth marketplace app = DEAD END (`error.noAppVersionIdFound`) — NEVER use it.
  - `companyId` is always the agency's FIRESTORE document id (NOT the relationNumber).
    Approval gate applies to both. See INSTRUCTIONS.md "Agency operations — create
    sub-account / add user".
- Workflow REVIEW / inspect / audit / "check this workflow": Tier 0 FIRST — `caf workflows export <id>`. Escalate to Tier 1/2/3 ONLY for what export cannot show (e.g. trigger-bucket state). NEVER open-ended-pick the Community MCP for a workflow review.
- Media upload: SKIP Tier 0. Always Tier 3 (POST /medias/upload-file).
- Rate limit (429): STOP. Never fall through. Surface reset time in plain English.

### Anti-patterns (mirrored from skill 36)

- ❌ "They said review the workflow → I will use the 834-tool MCP." Wrong. Review = Tier 0 `caf workflows export` first; escalate only for what export cannot show (e.g. trigger-bucket state). Never open-ended-pick the Community MCP for a workflow review.

### Per-operation routing

See the full 6-tier table in skill 36's AGENTS.md block. Skill 44 owns Tier 0;
skill 36 owns the routing law for all 6 tiers.

### Disclosure format

[GHL tier used: 0 — convertandflow <command>]
```

---

## TOOLS.md — UPDATE REQUIRED

Add this section:

```
## Convert and Flow CLI — Tier 0 GHL operator (skill 44)

Commands: caf / convertandflow / ghl

Installed at: ~/.openclaw/tools/convert-and-flow-cli/caf (Mac) or /data/.openclaw/tools/convert-and-flow-cli/caf (VPS)
Health: caf doctor

| Domain | Commands |
|---|---|
| contacts | caf contacts list/get/create/update/tag/untag |
| opportunities | caf opportunities list/get/update |
| calendars | caf calendars list/appointments |
| conversations | caf conversations list/get/send |
| documents | caf documents list/get/send |
| payments | caf payments list (= transactions); invoices/orders/transactions; create-invoice |
| forms | caf forms list/submissions |
| social | caf social accounts/post/schedule |
| locations | caf locations get/search/tags/custom-fields/custom-values |
| locations create (agency, write) | caf --experimental locations create [internal Firebase API; token-id; version:2021-07-28; ONLY path that creates a location; approval gate] |
| locations add-user (agency, write) | caf locations add-user [agency PIT + PUBLIC API services.../users/; Bearer PIT; Version:2023-02-21; omit --password → invite email; defaults to a SUB-ACCOUNT user; approval gate] |
| workflows (read/review) | caf workflows list/get/export — Tier 0 (caf) owns workflow build/edit/review; MCP workflow tools are escalation-only (note: `review` and `triggers` engine subcommands are MVP-deferred; use `export` as the Tier-0 read for review until shipped) |
| workflows (write) | caf workflows build/patch-email/patch-trigger/restore [Firebase token required] |

Agency ops detail — TWO different auth paths, do not cross them:
- CREATE SUB-ACCOUNT (Firebase internal): `caf --experimental locations create --name <NAME> --company-id <AGENCY_FIRESTORE_ID> [--phone --address --timezone]` → POST backend.leadconnectorhq.com/locations/ with header `token-id: <firebase-id-token>` + `version: 2021-07-28` (absent = 401). The id-token comes from the Chrome-extension Token Grabber (reads GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN from the agency-owner browser session) and is SHORT-LIVED — re-grab before writes; on TOKEN_REFRESH_FAILED, re-grab via the Token Grabber. ONLY working create-location path (public API/PIT cannot create a location). Whitelist skipped (no id yet), approval gate applies.
- ADD USER (agency PIT + PUBLIC API): `caf locations add-user --location-id <SUBACCOUNT_ID> --company-id <AGENCY_FIRESTORE_ID> --first-name <FIRST> --last-name <LAST> --email <EMAIL> --role <user|admin>` → POST services.leadconnectorhq.com/users/ with `Authorization: Bearer <agency PIT>` + `Version: 2023-02-21`. CreateUserDto: {companyId, locationIds:[<SUBACCOUNT_ID>], firstName, lastName, email, type, role, permissions}. Omit `--password` → GHL sends the invite email (user sets their own). NO Firebase token / NO Chrome extension needed. Whitelist checked against --location-id.
- USER TYPE: add-user DEFAULTS to `--type account` = a SUB-ACCOUNT user scoped to --location-id (`--role admin` = admin of that sub-account ONLY). `--type agency` = an AGENCY-wide user and is REFUSED unless `--i-understand-this-is-an-agency-user` is also passed. Adding a user to a client's sub-account must NEVER make them an agency user.
- OAuth marketplace app = DEAD END (`error.noAppVersionIdFound`) — NEVER use it for either op. (PIT is a Private Integration Token, NOT OAuth.)
- companyId is the agency FIRESTORE document id, NEVER the relationNumber.

Credentials: GOHIGHLEVEL_API_KEY (agency PIT — used for add-user via the public API), GOHIGHLEVEL_LOCATION_ID, GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN (workflow writes AND agency create-location; create-location's internal path cannot use the PIT). add-user does NOT need the Firebase token.

## Automation template library + matcher (template-first / reuse-before-reinvent)

- 28 proven sequences at `44-convert-and-flow-operator/automation-templates/` (welcome-indoctrination,
  sales-close-sequences, engagement-broadcast, funnel-specific-followups, multichannel-automation).
- Match (INSTRUCTIONS Step 0.4): `python3 .../automation-templates/_matcher/cli.py --match "<outcome>"`.
  Shared core `_matcher/flex.py`; committed lexical index `_matcher/catalog-index.json`.
- Funnel→automation link map: `_links/funnel-to-automation.json` (keyed by funnel_template_id).
- Env wiring (activates the matcher): `tools/engine/wire-ghl-env.sh` exports CAF_AUTOMATION_CATALOG /
  CAF_AUTOMATION_INDEX / CAF_FUNNEL_AUTOMATION_LINKS (+ the Skill-6 GHL_FUNNEL_* vars).
- Build gate: WF-1..21 PASS + FAB-QC ≥ 8.5 (`qc-built-workflow.sh --fab`; shared `shared-utils/fab_qc.py`).
- Flexibility = guide-not-rule: honor explicit spec; CREATE_NEW only when nothing fits; never block.
```

---

## MEMORY.md — UPDATE REQUIRED

```
## Convert and Flow Operator — Installed [DATE]

Skill 44 (Tier 0) installed. CLI at ~/.openclaw/tools/convert-and-flow-cli/.
Credentials: GOHIGHLEVEL_API_KEY (PIT), GOHIGHLEVEL_LOCATION_ID.
Firebase token for workflow writes: GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN (optional at install).
Write safety: GOHIGHLEVEL_DRAFT_ONLY=true, location whitelist, approval gate.
Health: caf doctor
```

---

## SOUL.md — NO UPDATE NEEDED

---

## IDENTITY.md — NO UPDATE NEEDED

---

## HEARTBEAT.md — NO UPDATE NEEDED

---

## USER.md — NO UPDATE NEEDED
