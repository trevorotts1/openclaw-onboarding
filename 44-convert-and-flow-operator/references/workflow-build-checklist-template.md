# Skill 44 — Workflow Build Checklist Template (WF-1..WF-21)

## Purpose

This is the canonical reusable checklist for every Skill 44 workflow build. It serves TWO
purposes:
1. **Agent self-check** — filled by the build agent at PLAN MODE (Step D) and verified by the
   independent QC sub-agent at Step 9.
2. **Client hand-over** — the completed checklist (with PASS + observed values for every item)
   is delivered to the client after QC passes, so the client can independently verify every
   setting themselves.

Copy this template for each new workflow build. Fill all `[...]` placeholders.

---

## Build Metadata

| Field | Value |
|---|---|
| Workflow Name | `[FILL: exact workflow name, including ZHC- prefix if managed build]` |
| Workflow ID | `[FILL: after build — GHL workflow id]` |
| GHL Location ID | `[FILL: location id]` |
| Build Date | `[FILL: YYYY-MM-DD]` |
| Build Agent | `[FILL: agent name + model]` |
| QC Agent | `[FILL: MiniMax model slug used for QC, e.g. minimax/minimax-m3]` |
| Client PUBLISH decision | `[FILL: DRAFT / LIVE — from gating question 1 answer]` |
| Client RE-ENTRY decision | `[FILL: ONCE / ALLOW-MULTIPLE — from gating question 2 answer]` |
| Snapshot path | `[FILL: ~/.openclaw/tools/convert-and-flow-cli/data/snapshots/<loc>/<wf-id>/<ts>.json]` |

---

## Checklist Items

### WF-1 — Workflow Name

- Expected: `[FILL: exact agreed name from plan/outline, ZHC- prefix if applicable]`
- Observed: `[FILL after QC: name as returned by caf workflows export]`
- Status: `[ ] PASS  [ ] FAIL`
- Notes: `[FILL if FAIL: discrepancy]`

### WF-2 — Tags Present

For each tag the workflow adds/removes/branches-on:

| Tag Name | Used For (add/remove/branch) | GET-Verified Exists? | QC Status |
|---|---|---|---|
| `[FILL: tag name]` | `[FILL: add/remove/If-Else condition]` | `[FILL: YES/NO — pre-build GET check]` | `[ ] PASS  [ ] FAIL` |

- Notes: `[FILL: any missing tags, spelling discrepancies (case-sensitive)]`

### WF-3 — Trigger Present + Correct Type + Filters

- Expected trigger type: `[FILL: Contact Created / Form Submitted / Tag Added / etc.]`
- Expected filter values: `[FILL: form name, tag name, field value, etc.]`
- Observed trigger type: `[FILL after QC: from caf workflows export]`
- Observed filter values: `[FILL after QC]`
- Status: `[ ] PASS  [ ] FAIL`
- Notes: `[FILL if FAIL]`

### WF-4 — Trigger ACTIVE State (THE WF-ACTIVE GATE)

**Critical:** Under CAF_DRAFT_ONLY=true the engine ships the trigger active:false
(safety_gate.draft_only_active_flag()). If the client chose LIVE/PUBLISH, the trigger MUST be
active:true or the workflow silently never fires.

- Client PUBLISH decision: `[FILL: DRAFT / LIVE]`
- Expected trigger active state: `[FILL: true (if LIVE) / false (if DRAFT)]`
- Observed trigger active flag (from export): `[FILL after QC]`
- Status: `[ ] PASS  [ ] FAIL`
- Notes: `[FILL: "PASS: client chose DRAFT, trigger inactive is expected" OR "FAIL: client chose LIVE but trigger is inactive — workflow will silently never fire"]`

### WF-5 — Publish State

- Client PUBLISH decision: `[FILL: DRAFT / LIVE]`
- Expected workflow status: `[FILL: draft / published]`
- Observed workflow status (from export): `[FILL after QC]`
- Status: `[ ] PASS  [ ] FAIL`
- Notes: `[FILL: Never published without an explicit YES from the client]`

### WF-6 — Re-Entry / Allow-Multiple

- Client RE-ENTRY decision: `[FILL: ONCE / ALLOW-MULTIPLE]`
- Expected allow-multiple setting: `[FILL: false (once) / true (allow-multiple)]`
- Observed allow-multiple (from export): `[FILL after QC]`
- Status: `[ ] PASS  [ ] FAIL`
- Notes: `[FILL: recorded explicitly, not left at an unverified default]`

### WF-7 — Action Sequence Matches Outline

Expected node order (from plan outline):
1. `[FILL: node 1 — type + key config]`
2. `[FILL: node 2 — type + key config]`
3. `[FILL: node 3 — etc.]`
...

- Observed sequence (from export): `[FILL after QC]`
- link_steps ordering applied (no 400 corrupted order): `[ ] CONFIRMED`
- Status: `[ ] PASS  [ ] FAIL`
- Notes: `[FILL: any nodes dropped, added, or out of order]`

### WF-8 — If/Else Conditions

For each If/Else branch in the workflow:

| Branch | Expected Field | Expected Operator | Expected Value | Both Branches Configured? | QC Status |
|---|---|---|---|---|---|
| `[FILL: branch name]` | `[FILL]` | `[FILL: is/is not/contains/etc.]` | `[FILL]` | `[ ] YES  [ ] NO` | `[ ] PASS  [ ] FAIL` |

- Notes: `[FILL if FAIL: observed discrepancy]`

### WF-9 — Wait Steps

For each Wait node in the workflow:

| Wait Node | Expected Duration | Timeout Branch Configured? | QC Status |
|---|---|---|---|
| `[FILL: wait node label]` | `[FILL: N minutes/hours/days]` | `[ ] YES  [ ] NO  [ ] N/A` | `[ ] PASS  [ ] FAIL` |

- Notes: `[FILL if no Wait nodes: "N/A — no Wait nodes in this workflow"]`

### WF-10 — Custom Fields

For each Update-Contact-Field action:

| Field Name | Expected Data Type | Exists in GHL? | QC Status |
|---|---|---|---|
| `[FILL: field name]` | `[FILL: text/number/date/dropdown]` | `[ ] YES  [ ] NO` | `[ ] PASS  [ ] FAIL` |

- Notes: `[FILL if no custom fields: "N/A"]`

### WF-11 — Custom Values

For each merge field referencing a custom value:

| Custom Value Name | Non-Empty? | QC Status |
|---|---|---|
| `[FILL: custom value name]` | `[ ] YES  [ ] NO` | `[ ] PASS  [ ] FAIL` |

- Notes: `[FILL if no custom values: "N/A"]`

### WF-12 — SMS From-Number (THE WF-SMS-FROM GATE — silent fail without this)

For each SMS node in the workflow:

| SMS Node | Expected From-Number | Observed From-Number | Non-Empty? | QC Status |
|---|---|---|---|---|
| `[FILL: SMS node label]` | `[FILL: phone number or "location default"]` | `[FILL after QC]` | `[ ] YES  [ ] NO` | `[ ] PASS  [ ] FAIL` |

- Notes: `[FILL if no SMS nodes: "N/A — no SMS nodes in this workflow"]`
- CRITICAL: an SMS node with no From-number silently fails to send.

### WF-13 — Email Sender Details

For each Email node in the workflow:

| Email Node | Expected From Name | Expected From Email | Observed From Name | Observed From Email | QC Status |
|---|---|---|---|---|---|
| `[FILL: email node label]` | `[FILL]` | `[FILL]` | `[FILL after QC]` | `[FILL after QC]` | `[ ] PASS  [ ] FAIL` |

- Notes: `[FILL if no email nodes: "N/A"]`

### WF-14 — Webhook Nodes

For each Webhook node:

| Webhook Node | URL | Method | Content-Type Header | Auth Header | QC Status |
|---|---|---|---|---|---|
| `[FILL: webhook label]` | `[FILL: exact URL]` | `[FILL: GET/POST/PUT/DELETE]` | `[FILL: application/json or N/A]` | `[FILL: present/absent/N/A]` | `[ ] PASS  [ ] FAIL` |

- Notes: `[FILL if no webhook nodes: "N/A"]`

### WF-15 — Delivery Chain Wired End-to-End

- Trigger → first step (targetActionId linked): `[ ] CONFIRMED`
- Each step linked to next (no orphaned/unlinked nodes): `[ ] CONFIRMED`
- Exit node present and reachable: `[ ] CONFIRMED`
- Message-bearing nodes (SMS/email) reachable from trigger: `[ ] CONFIRMED`
- Status: `[ ] PASS  [ ] FAIL`
- Notes: `[FILL if FAIL: which node is orphaned or unreachable]`

### WF-16 — Advanced Settings

| Setting | Expected | Observed | QC Status |
|---|---|---|---|
| Stop-on-Response | `[FILL: enabled/disabled/N/A]` | `[FILL after QC]` | `[ ] PASS  [ ] FAIL` |
| Time window / business hours | `[FILL: configured/none/N/A]` | `[FILL after QC]` | `[ ] PASS  [ ] FAIL` |
| Timezone | `[FILL: e.g. America/New_York or N/A]` | `[FILL after QC]` | `[ ] PASS  [ ] FAIL` |
| Enrollment filters | `[FILL: configured/none]` | `[FILL after QC]` | `[ ] PASS  [ ] FAIL` |

- Notes: `[FILL: any setting explicitly defaulted and recorded]`

### WF-17 — Edge Cases Covered / Decided

| Edge Case | Handling Decision |
|---|---|
| Empty/missing field on trigger contact | `[FILL: handled by If/Else / accepted by client / N/A]` |
| Contact already in workflow | `[FILL: governed by WF-6 re-entry setting]` |
| Reply mid-sequence | `[FILL: governed by Stop-on-Response (WF-16) / accepted]` |
| Wait spanning outside business hours | `[FILL: governed by time window (WF-16) / accepted]` |
| Failed-send branch | `[FILL: branch configured / accepted by client]` |

- Status: `[ ] PASS  [ ] FAIL`
- Notes: `[FILL: any unresolved edge case]`

### WF-18 — Dependencies All Pre-Existed or Created With Approval

- All tags, custom fields, custom values GET-verified before build: `[ ] CONFIRMED`
- Any missing items created with client approval: `[ ] N/A — all existed`
- ZHC-/ZHC_ standing-approval objects noted: `[FILL: list any ZHC objects or "none"]`
- Status: `[ ] PASS  [ ] FAIL`

### WF-19 — TRINITY Complete (conversational workflows only)

- GHL automation built (skill 44 — the HANDS): `[ ] DONE  [ ] N/A`
- Communications playbook built (skill 38 — the BRAIN): `[ ] DONE  [ ] N/A`
- Build-with-AI / Workflow-AI prompt built (skill 38): `[ ] DONE  [ ] N/A`
- qc-trinity-registry.sh hard gate passed: `[ ] DONE  [ ] N/A`
- Status: `[ ] PASS  [ ] FAIL  [ ] N/A (purely-mechanical workflow)`

### WF-20 — No Hallucinated Artifacts

For every artifact the build agent CLAIMED to have set, independently confirmed via
`caf workflows export <id>` (and escalation where export cannot show):

| Claimed Artifact | Claimed Value | Independently Verified? | QC Status |
|---|---|---|---|
| `[FILL: e.g. SMS From-number]` | `[FILL: value agent claimed]` | `[FILL after QC: CONFIRMED/NOT-FOUND/DIFFERS]` | `[ ] PASS  [ ] FAIL` |
| `[FILL: e.g. trigger type]` | `[FILL: value agent claimed]` | `[FILL after QC]` | `[ ] PASS  [ ] FAIL` |
| `[FILL: e.g. tag name]` | `[FILL: value agent claimed]` | `[FILL after QC]` | `[ ] PASS  [ ] FAIL` |

- HALLUCINATION flag: `[ ] NONE  [ ] HALLUCINATION DETECTED — see Step 9 escalation`
- Status: `[ ] PASS  [ ] FAIL`
- Notes: `[FILL: any claimed-true-but-observed-false item. Claims are NEVER accepted as truth.]`

### WF-21 — Snapshot Taken

- Pre-build snapshot path: `[FILL: path from Build Metadata table above]`
- Snapshot verified to exist on disk: `[ ] CONFIRMED`
- Build is reversible via `caf workflows restore <snapshot-path>`: `[ ] CONFIRMED`
- Status: `[ ] PASS  [ ] FAIL`

---

## Overall QC Result

| Item | Status |
|---|---|
| WF-1 Name | `[ ] PASS  [ ] FAIL  [ ] N/A` |
| WF-2 Tags | `[ ] PASS  [ ] FAIL  [ ] N/A` |
| WF-3 Trigger Present | `[ ] PASS  [ ] FAIL  [ ] N/A` |
| WF-4 Trigger Active (WF-ACTIVE GATE) | `[ ] PASS  [ ] FAIL` |
| WF-5 Publish State | `[ ] PASS  [ ] FAIL` |
| WF-6 Re-Entry | `[ ] PASS  [ ] FAIL` |
| WF-7 Action Sequence | `[ ] PASS  [ ] FAIL` |
| WF-8 If/Else Conditions | `[ ] PASS  [ ] FAIL  [ ] N/A` |
| WF-9 Wait Steps | `[ ] PASS  [ ] FAIL  [ ] N/A` |
| WF-10 Custom Fields | `[ ] PASS  [ ] FAIL  [ ] N/A` |
| WF-11 Custom Values | `[ ] PASS  [ ] FAIL  [ ] N/A` |
| WF-12 SMS From-Number | `[ ] PASS  [ ] FAIL  [ ] N/A` |
| WF-13 Email Sender | `[ ] PASS  [ ] FAIL  [ ] N/A` |
| WF-14 Webhook Nodes | `[ ] PASS  [ ] FAIL  [ ] N/A` |
| WF-15 Delivery Chain | `[ ] PASS  [ ] FAIL` |
| WF-16 Advanced Settings | `[ ] PASS  [ ] FAIL` |
| WF-17 Edge Cases | `[ ] PASS  [ ] FAIL` |
| WF-18 Dependencies | `[ ] PASS  [ ] FAIL` |
| WF-19 TRINITY | `[ ] PASS  [ ] FAIL  [ ] N/A` |
| WF-20 No Hallucinated Artifacts | `[ ] PASS  [ ] FAIL` |
| WF-21 Snapshot | `[ ] PASS  [ ] FAIL` |

**Final verdict:** `[ ] ALL-PASS — QC APPROVED  [ ] FAIL — see items above`

---

## Cross-reference: Skill 41 12-Point Checklist

This WF-1..WF-21 checklist is a SUPERSET of Skill 41's 12-point verification-checklist.md,
extended for caf-built workflows with Skill 44-specific gates (trigger active state,
re-entry/publish gating questions, SMS From-number, delivery-chain linkage, hallucination
detection, and snapshot verification). The mapping is:

| Skill 41 Point | WF Item(s) |
|---|---|
| 1. Workflow name matches prompt | WF-1 |
| 2. Trigger correct type + filters | WF-3, WF-4 |
| 3. Tags present + spelled correctly | WF-2 |
| 4. Custom fields exist + correct type | WF-10 |
| 5. Custom values exist + set | WF-11 |
| 6. Action sequence matches prompt | WF-7 |
| 7. If/Else conditions correct | WF-8 |
| 8. Wait steps correct duration | WF-9 |
| 9. Webhook URL + method | WF-14 |
| 10. Webhook Content-Type + Auth headers | WF-14 |
| 11. Re-entry / stop-on-response / time windows | WF-6, WF-16 |
| 12. Test with test contact | WF-20 (independent read via export) |

For caf-built workflows, use THIS checklist (WF-1..WF-21) as the authoritative source.
Skill 41's 12-point checklist applies to Build-with-AI (manual browser) builds only.
