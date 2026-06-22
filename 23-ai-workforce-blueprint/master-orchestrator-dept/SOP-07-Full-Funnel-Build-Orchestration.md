# SOP-07 — Full-Funnel Build Orchestration
**Version:** 1.0.0 | 2026-06-22
**Applies to:** Master Orchestrator / CEO Agent (all installs — Mac and VPS)
**Status:** CANONICAL — cross-platform fleet standard

---

## Purpose

This SOP is the single owner of the P0→P5 full-funnel value-stream. It is triggered by SOP-00 Step-2 when the owner's request is classified as full-funnel or website-factory intent (see SOP-00 for the trigger condition). It replaces the single-department routing in that context, creating a parent epic with six staged child cards and enforcing the stage-boundary ordering gates.

The Master Orchestrator ROUTES and GATES. It never executes production work. All production stages are dispatched via `POST /api/tasks/ingest` to the PERSISTENT `agent:<dept>` for each department (SOP-00 R11). No inline turn-scoped child is used.

---

## Binding Rules (no exceptions)

| Rule | Statement |
|------|-----------|
| **F1** | The Master Orchestrator is the sole entity that creates the parent funnel epic and the six staged child cards. |
| **F2** | Child cards are dispatched to the PERSISTENT `agent:<dept>` via `POST /api/tasks/ingest` with `department_slug`. NEVER dispatch to an ephemeral inline child. |
| **F3** | A downstream child card MUST NOT be moved to `in_progress` until every `depends_on` card is in `done` or `APPROVED` state. The orchestrator enforces this gate before each dispatch. |
| **F4** | A child card whose upstream dependency is not yet complete is assigned `status=waiting_on_dependency` (see SOP-01 schema extension). This sub-state is NEVER counted against the `qc_reroute_attempts` bounce cap (cap = 3, per SOP-01 O4). |
| **F5** | If ANY child card reaches `FAILED` terminal state, the parent epic does NOT publish. `funnel_rollback` is triggered immediately (see Section 7). |
| **F6** | The parent epic carries the `idempotency_key`. Each child key is derived as `sha256(parent_key + ':' + stage)`. A Telegram retry cannot duplicate the whole funnel or any individual stage. |
| **F7** | The Iron Rule from SOP-00 R11 applies without exception: production work runs in the PERSISTENT per-department agent session, not in the orchestrator's turn. |
| **F8** | Every stage transition emits a board handoff event `{from_dept, to_dept, artifact, job_id}` that bumps `last_progress_at` on the parent epic. |

---

## Step 1 — Detect Full-Funnel Intent

The orchestrator applies this check BEFORE the normal single-department routing in SOP-00 Step 2.

**Intent signals (any of the following):**

- Owner message contains any of: "full funnel," "build me a funnel," "website factory," "sales funnel," "opt-in page + follow-up," "landing page + automation," "funnel + emails," "VSL funnel," "webinar funnel," "lead magnet + sequence."
- Owner message describes a multi-stage conversion flow: top-of-funnel capture → nurture → sales → automation.
- Owner message explicitly names both a page-builder output (landing page, funnel, website) AND a follow-up automation (email sequence, workflow, CRM automation) in the same request.

**If full-funnel intent is detected:** do NOT single-route. Proceed to Step 2. Acknowledge to the owner:

```
Got it — this is a full-funnel build. I'm spinning up the 6-stage pipeline for you now.
I'll keep you posted at each stage gate.
```

**If intent is ambiguous:** apply standard SOP-00 Step-2 single-department routing. When in doubt, single-route.

---

## Step 2 — Create Parent Epic

POST the parent epic to the Command Center:

```
POST {COMMAND_CENTER_URL}/api/tasks/ingest
Content-Type: application/json
x-webhook-signature: {HMAC-SHA256 of body with WEBHOOK_SECRET}

{
  "title": "Full-Funnel Build: <concise offer description>",
  "description": "<owner's full request>",
  "priority": "<priority from SOP-00 priority mapping>",
  "source": "telegram",
  "source_ref": "telegram:msg:{message_id}",
  "department_slug": "master-orchestrator",
  "task_type": "funnel_epic",
  "stage": null,
  "parent_task_id": null,
  "external_session_id": "{session_id}",
  "idempotency_key": "{sha256 of source_ref + normalized_title}"
}
```

On success: capture `parent_task_id`. Log it.

---

## Step 3 — Create Six Staged Child Cards

For each stage below, POST one child card. Derive each child `idempotency_key` as `sha256(parent_task_id + ':' + stage_slug)`.

| Stage | Slug | Department | Artifact produced | Depends on |
|-------|------|------------|-------------------|------------|
| P0 | `p0-offer-spec` | `sales` | `offer-spec.json` | (none — starts immediately) |
| P1 | `p1-funnel-spec` | `marketing` | `funnel-spec.json` + `persona-selection-log.md` | P0 done |
| P2 | `p2-copy` | `marketing` | `copy.md` / `copy.json` APPROVED | P1 done |
| P2e | `p2e-email-copy` | `marketing` | Email sequence copy APPROVED | P1 done (parallel with P2) |
| P3 | `p3-assets` | `graphics` | `assets-manifest.json` | P2 APPROVED |
| P4 | `p4-build` | `web-development` | Page IDs, preview URLs, Gate-3 match | P2 APPROVED + P3 done |
| P5 | `p5-automation` | `crm` | Skill-44 WF-1..21 PASS + rubric ≥ 8.5 | P2e APPROVED + P4 verified |

**Child card POST body (template):**

```
POST {COMMAND_CENTER_URL}/api/tasks/ingest
{
  "title": "<Stage> — <artifact name>: <offer title>",
  "description": "<stage-specific instructions>",
  "priority": "<inherit from parent>",
  "source": "funnel_epic",
  "source_ref": "funnel_epic:{parent_task_id}",
  "department_slug": "<dept from table>",
  "task_type": "funnel_stage",
  "stage": "<slug from table>",
  "parent_task_id": "<parent_task_id>",
  "depends_on": ["<task_id of upstream stage(s)>"],
  "status": "waiting_on_dependency",
  "idempotency_key": "{sha256(parent_task_id + ':' + stage_slug)}"
}
```

**Ordering rules (enforced by the orchestrator before every dispatch):**

- P0 → no dependency. Dispatch immediately after creation.
- P1 → depends on P0 task_id. Dispatch when P0 status = `done`.
- P2 → depends on P1 task_id. Dispatch when P1 status = `done`.
- P2e → depends on P1 task_id. Dispatch when P1 status = `done`. (Runs in parallel with P2.)
- P3 → depends on P2 task_id. Dispatch when P2 status = `APPROVED`.
- P4 → depends on P2 task_id AND P3 task_id. Dispatch when both P2 = `APPROVED` AND P3 = `done`.
- P5 → depends on P2e task_id AND P4 task_id. Dispatch when P2e = `APPROVED` AND P4 status = `verified`.

**waiting_on_dependency:** Any stage card whose upstream conditions are not yet met is assigned `status=waiting_on_dependency`. The stale-task-sweep applies the upstream card's remaining time budget as the threshold (not the default column threshold). This sub-state is NOT counted against `qc_reroute_attempts`.

---

## Step 4 — Gate and Dispatch Each Stage

The orchestrator runs this gate before dispatching any stage to in_progress:

```
for each stage card with status=waiting_on_dependency:
  if ALL depends_on task_ids are in {done, APPROVED, verified}:
    PATCH /api/tasks/{child_task_id}
      { "status": "in_progress" }
    POST /api/tasks/ingest (re-route to dept agent)
    emit board handoff event:
      { "from_dept": "<completing dept>",
        "to_dept": "<receiving dept>",
        "artifact": "<artifact produced by upstream>",
        "job_id": "<child_task_id>" }
```

The orchestrator subscribes to the Command Center SSE stream (`/api/events`) to receive `task_completed`, `task_approved`, and `task_verified` events. On each event, it re-evaluates the gate for all downstream stage cards.

**The orchestrator NEVER asks the agent to execute stage work inline.** It dispatches via the task board and waits for the SSE event.

---

## Step 5 — Stage-Specific Dispatch Instructions

When dispatching each stage, the orchestrator includes these instructions in the task description:

### P0 — Offer Spec (Chief Sales Officer, sales dept)

```
Run SOP 9.9 (chief-sales-officer.md) to emit offer-spec.json.
Output: working/funnels/<slug>/offer-spec.json
Artifact confirms: product name, deliverables, price points, guarantee, bonuses, positioning.
Hand artifact path back via task completion event.
Parent funnel epic: <parent_task_id>
Child idempotency key: <p0_key>
```

### P1 — Funnel Spec (Funnel Strategist, marketing dept)

```
Run SOP 9.5 (funnel-strategist.md) to produce funnel-spec.json.
Input: working/funnels/<slug>/offer-spec.json from P0.
Persona: select hormozi-100m-offers per persona-matching-protocol.md.
Write persona-selection-log.md entry (mandatory).
Output: working/funnels/<slug>/funnel-spec.json
Parent funnel epic: <parent_task_id>
Child idempotency key: <p1_key>
```

### P2 — Page Copy (Conversion Copywriter, marketing dept)

```
Run SOP 9.2 (conversion-copywriter.md) for page copy.
Input: funnel-spec.json from P1.
Run Step 0 persona grounding before any writing.
Output: working/copy/<slug>/copy.md and copy.json, status PENDING-QC.
Gate: copy must reach APPROVED from QC Specialist — Marketing before P3/P4 can start.
Do NOT mark APPROVED yourself. Hand to QC.
Parent funnel epic: <parent_task_id>
Child idempotency key: <p2_key>
```

### P2e — Email Sequence Copy (Email Campaign Strategist, marketing dept)

```
Run SOP-01 (email-campaign-strategist.md) for nurture/follow-up sequence copy.
Input: funnel-spec.json from P1.
Run persona grounding sub-step and write persona-selection-log.md entry.
Output: email sequence copy artifact, status PENDING-QC.
Gate: must reach APPROVED before P5 can start.
Hand to QC Specialist — Marketing.
Parent funnel epic: <parent_task_id>
Child idempotency key: <p2e_key>
```

### P3 — Assets (Graphics dept)

```
Produce assets-manifest.json mapping all copy slot IDs to CDN-hosted image/video links.
Input: approved copy.md from P2.
Output: assets-manifest.json at working/funnels/<slug>/assets-manifest.json.
Parent funnel epic: <parent_task_id>
Child idempotency key: <p3_key>
```

### P4 — Page Build (Web Development dept — Funnel Builder or Landing Page Specialist)

```
Run v2-autonomous-build-sop.md (06-ghl-install-pages).
Inputs: approved copy.md (P2) + assets-manifest.json (P3) + funnel-spec.json (P1).
Gate-3 verbatim copy match required.
Output: page_ids, opt-in form IDs, preview URLs, Gate-3 match confirmed.
After page verify, emit board handoff event to CRM dept (P5 seam).
Hand live page_ids + opt-in form IDs to Automation Workflow Specialist for P5.
Parent funnel epic: <parent_task_id>
Child idempotency key: <p4_key>
```

### P5 — Automation (CRM dept — Automation Workflow Specialist, Skill 44)

```
Wire workflows per Skill 44 (44-convert-and-flow-operator).
Inputs: approved email copy (P2e) + page_ids/form IDs from P4.
Receives APPROVED copy + funnel page IDs from Skill 6 (P4).
Does NOT author copy or business rules — wires only what P2e and P4 produced.
Gate: WF-1..21 PASS + rubric ≥ 8.5 (workflow-quality-rubric.md).
Output: ecosystem receipts (calendar, product-price, optin-form, contact-test, workflow).
Parent funnel epic: <parent_task_id>
Child idempotency key: <p5_key>
```

---

## Step 6 — Parent Rollup and Completion

The parent epic tracks progress as a rollup:

```
{
  "stages_complete": <count of children in done/APPROVED/verified>,
  "stages_total": 6,
  "current_stage": "<slug of active in_progress stage>",
  "rollup_status": "<N>/6 stages complete; current = <P?> build (<dept>)"
}
```

**Parent epic moves to `done` only when ALL six child cards are in `done`, `APPROVED`, or `verified` state AND the canonical verifier (`ghl_builder.py verify-all`) has run and logged `overall_pass:true`.**

**Publish gate:** The parent epic NEVER marks any page as LIVE without explicit owner LIVE approval delivered via Telegram in the current conversation turn. Draft/preview only by default.

---

## Step 7 — funnel_rollback on Child FAILED

If any child card reaches `FAILED` terminal status:

1. Halt dispatch of all downstream stage cards (do not start new stages).
2. Execute `funnel_rollback`:
   - **Revert page autosave baselines:** re-POST the pristine baseline blob for each GHL page that was autosaved during P4 (use `ghl_rest_canvas.blob_md5` to confirm byte-identical restoration). The live pointer must be unmoved.
   - **Delete created-but-unverified ecosystem objects:** any calendar, product, price, or workflow created during P5 that has not received a passing QC receipt is deleted via Skill-44 CLI.
   - **Delete the test contact:** if P5 created a test contact for form→CRM proof, delete it now (`caf contacts delete {id}`).
   - Write `funnel_rollback.json` to the evidence root with: `{triggered_by_stage, failed_task_id, actions_taken, baseline_md5_confirmed, objects_deleted, test_contact_deleted}`.
3. Carry the `parent_task_id` and `idempotency_key` in the rollback record so the build can be retried without duplication.
4. Update parent epic status to `FAILED`.
5. Notify the owner via Telegram: specify which stage failed, what was rolled back, and the next step.

**Rollback is idempotent:** running it twice on the same failed build must not double-delete or double-revert. Check for existence before each delete.

---

## Step 8 — Idempotency (Replay Safety)

| Key | How derived | Effect |
|-----|-------------|--------|
| Parent epic key | `sha256(source_ref + normalized_title)` | Second owner Telegram message with the same content returns the EXISTING parent_task_id; no new epic created |
| P0 child key | `sha256(parent_task_id + ':p0-offer-spec')` | Replay cannot create a duplicate P0 card |
| P1 child key | `sha256(parent_task_id + ':p1-funnel-spec')` | Same |
| P2 child key | `sha256(parent_task_id + ':p2-copy')` | Same |
| P2e child key | `sha256(parent_task_id + ':p2e-email-copy')` | Same |
| P3 child key | `sha256(parent_task_id + ':p3-assets')` | Same |
| P4 child key | `sha256(parent_task_id + ':p4-build')` | Same |
| P5 child key | `sha256(parent_task_id + ':p5-automation')` | Same |

The `POST /api/tasks/ingest` endpoint returns `{ok:true, task_id:"...", deduped:false|true}`. When `deduped:true`, the orchestrator does NOT create a new card — it reads the existing card status and continues from there.

---

## Relationship to Other SOPs

| SOP | Relationship |
|-----|-------------|
| SOP-00 Step 2 | This SOP is triggered when full-funnel intent is detected. SOP-00 hands control here. |
| SOP-01 | The `waiting_on_dependency` sub-state is a SOP-01 schema extension. Bounce cap (qc_reroute_attempts=3) does NOT apply to this sub-state. |
| v2-autonomous-build-sop.md | P4 stage follows this SOP for the page build. The P0/P1/P2 persona stages are inserted before its S2 copy step. |
| funnel-strategist.md SOP 9.5 | P1 owner SOP — produces funnel-spec.json with persona grounding. |
| chief-sales-officer.md SOP 9.9 | P0 owner SOP — produces offer-spec.json. |
| conversion-copywriter.md SOP 9.2 | P2 owner SOP — produces copy.md/copy.json with persona grounding. |
| email-campaign-strategist.md | P2e owner — produces email sequence copy with persona grounding. |
| 44-convert-and-flow-operator | P5 owner — wires workflows (Skill 44, rubric ≥ 8.5). |

---

## CHANGELOG

| Version | Date | Change |
|---------|------|--------|
| 1.0.0 | 2026-06-22 | Initial canonical SOP. Defines P0→P5 value-stream: full-funnel intent detection, parent funnel_epic, 6 staged child cards with depends_on edges, waiting_on_dependency sub-state (not counted against bounce cap), Iron Rule (routes via POST /api/tasks/ingest to persistent agent:<dept>), funnel_rollback on child FAILED, and parent/child idempotency key derivation. Sibling to SOP-00 and SOP-01 in master-orchestrator-dept/. |
