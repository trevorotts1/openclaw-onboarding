# SOP-DIU-602 — Generation Receipts, Budget Gate & Orphan Recovery

**ID:** SOP-DIU-602
**Classification:** ZHC SOP — thin wrapper
**Owner Role:** Generation Operator
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** MODEL-SPECS v1.0, TEST-PROTOCOL v1.0, PPT-ANALYSIS-SOP v1.0 (§-refs verified 2026-06-12)

---

## Role Mission

The Generation Operator is the sole bookkeeper for every Kie.ai task it fires. It writes a per-task receipt file at the moment of submission, enforces a budget gate before every new job, sweeps for orphaned in-flight tasks at every session start, and trips a circuit breaker when aggregate spend crosses configured thresholds. No generation is invisible; no spend is unaccounted.

---

## Governing Library Files (source-of-truth — do NOT duplicate content)

| File | Sections used | What it governs |
|---|---|---|
| `_system/MODEL-SPECS.md` | §5 (JSON templates + taskId response contract; resultUrls perishability) | API task schema; taskId extraction; result URL lifetime |
| `_system/TEST-PROTOCOL.md` | §4 (cost estimate + test-run accounting), §7 (regression re-check fingerprint reuse) | Cost attribution for test runs; fingerprint-cache rule for free regression re-checks |
| `_system/PPT-ANALYSIS-SOP.md` | §3B (Slide Manifest as the job work-list) | Manifest-as-deliverable-work-list, per-slide receipt accounting |
| `_local/PRICING.md` | Full file (per-client, volatile; authoritative for dollar estimates) | Prices per model/tier; NEVER duplicated into vendor MODEL-SPECS |
| Client `budget_config` block | `monthly_cap`, `per_job_approval_threshold`, `per_deliverable_cap`, `per_day_cap` | All dollar thresholds; never hardcoded in this SOP |

---

## Procedure (ordered)

### A. Receipt — write at submission (per task, not per job)

1. **Create a per-task receipt file** at `_local/receipts/{receipt-id}.json` at the moment `createTask` returns. One file per task, per the fleet-proven rule that shared-append ledgers lose writes under concurrent agents.

2. **Write all required fields** (see Receipt Schema below). The `filled_prompt_hash` field (sha256 of the exact filled positive prompt + seed + card version + model) is the idempotent resubmission key — on recovery, compute this fingerprint first and scan existing receipts before creating a new task.

3. **Set `state: submitted`** immediately. The cron poller will advance the state; the Operator exits after writing this receipt.

4. **Include `company_id` and `dept` fields** for future Command Center telemetry. Populate from the client's box config. Do not skip these fields — they require no re-instrumentation later.

### B. Budget gate — before every new job

1. Read `_local/PRICING.md` for the selected model and tier. Compute `estimated_cost = num_tasks × price_per_task`.

2. Sum all `cost_class` values from receipts in `state: complete` for the current billing period.

3. If `current_period_spend + estimated_cost > monthly_cap`: hard stop. Notify CDO with the spend summary. Do not proceed without a producer override receipt.

4. If `estimated_cost > per_job_approval_threshold`: require a producer approval receipt (CDO or designated producer) before submitting. Attach the approval receipt ID to the job receipt.

5. **First-ever generation per client:** run a 1K SHORT smoke test on the cheapest capable endpoint first. Purpose: validate key reachability, hosting plumbing, and receipt write path for pennies before any real spend. Log the smoke test as a normal receipt with `smoke_test: true`.

### C. Idempotent resubmission

1. Before creating any new task, compute the request fingerprint: `sha256(model + endpoint + tier + full_filled_positive_prompt + seed + card_id + card_version)`.

2. Search existing receipts for a matching `filled_prompt_hash`.

3. If found and `state: complete`: return the existing result. Do not resubmit. Regression re-checks use this path — cost is zero.

4. If found and `state: submitted|polling`: re-poll the recorded `taskId` via `getTaskInfo`. Do not create a duplicate task.

5. Only if no matching fingerprint exists: proceed to create a new task and write a new receipt.

### D. Orphan recovery — at every session start

1. List all receipt files with `state: submitted` or `state: polling`.

2. For each orphaned receipt: call `getTaskInfo(taskId)` from MODEL-SPECS §5.
   - `status: completed` → run SOP-DIU-601 postflight immediately; flip receipt to `complete` on pass.
   - `status: failed` → flip receipt to `postflight-failed`; escalate to CDO with the full receipt.
   - `status: processing` → update `last_polled` (ISO 8601); leave for the cron poller.

3. Any receipt with `last_polled` older than 24 hours and no completion state: escalate to CDO. Do not silently discard.

### E. Aggregate circuit breaker — checked after every spend event

1. After every completed or failed task, sum all `cost_class` values for the current deliverable (keyed by `job_id`).

2. If per-deliverable cap exceeded: halt all remaining tasks for this job, notify CDO, write a circuit-breaker incident receipt at `_local/receipts/circuit-break-{job-id}.json`.

3. If daily aggregate across all jobs exceeds `per_day_cap`: halt all new submissions fleet-wide for this client, notify CDO.

4. Thresholds are always read from the client `budget_config` block — never hardcoded here.

---

## Receipt Schema (required fields)

```
receipt_id:           {uuid}
job_id:               {job-dir-name}
card_id:              {style-card-id}
card_version:         {semver}
model:                {kie.ai-model-id}
endpoint:             {kie.ai-endpoint-slug}
tier:                 {SHORT|MEDIUM|LONG}
resolution:           {WxH or descriptor}
task_id:              {kie.ai-taskId}
requestor:            {role-slug or workspace-slug}
cost_class:           {estimated-cost-dollars}
budget_cap:           {per-job-cap-dollars}
state:                {queued|submitted|polling|complete|postflight-failed|quarantined}
submitted_at:         {iso8601}
last_polled:          {iso8601}
completed_at:         {iso8601 or null}
local_path:           {absolute path or null}
sha256:               {hex or null}
preflight_passed:     {true|false}
postflight_verified:  {true|false}
seed:                 {value or "no-seed-endpoint"}
filled_prompt_hash:   {sha256 of exact filled positive prompt + seed + card_id + card_version + model}
company_id:           {client-box-id}
dept:                 {department-slug}
smoke_test:           {true|false}
```

---

## Inputs

| Input | Required | Source |
|---|---|---|
| `taskId` from `createTask` API response | Yes | MODEL-SPECS §5 JSON template response |
| Style card ID + version | Yes | Assembly packet |
| Filled positive prompt (complete, post-preflight) | Yes | SOP-DIU-601 output |
| Model ID + endpoint slug + tier | Yes | SOP-DIU-302 routing decision |
| `PRICING.md` row for selected model + tier | Yes | `_local/PRICING.md` (client-owned file) |
| Client `budget_config` block | Yes | Client box config — halt if absent |
| Slide Manifest (for deck jobs) | Conditional | PPT-ANALYSIS-SOP §3B — used to enumerate per-slide receipt scope |
| Producer approval receipt ID | Conditional | Required when `estimated_cost > per_job_approval_threshold` |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| Per-task receipt file | `_local/receipts/{receipt-id}.json` | `state: submitted` |
| Circuit-breaker incident receipt (if triggered) | `_local/receipts/circuit-break-{job-id}.json` | Written at breach event |
| Smoke test receipt (first-ever generation per client) | `_local/receipts/{receipt-id}.json` | `smoke_test: true`, `state: submitted` |
| Orphan recovery result (postflight pass) | `_local/results/{job-id}/` | Receipt flipped to `complete` |
| CDO escalation notification | CDO notification channel | Written at: budget gate trip, circuit-breaker trip, orphan >24h, orphan `failed` state |

---

## Handoff Conditions

- **Normal submission:** Receipt written with `state: submitted`; Operator exits; cron poller handles `getTaskInfo` polling until completion; SOP-DIU-601 postflight runs on completion and flips receipt to `complete`.
- **Budget gate trip:** Hard stop before submission; CDO receives spend summary; job paused until CDO issues a producer override receipt.
- **Circuit-breaker trip (per-deliverable):** All remaining tasks for this `job_id` halted; CDO receives incident receipt; resume requires CDO direction with explicit per-task re-authorization.
- **Circuit-breaker trip (per-day):** All new submissions for this client halted; CDO receives escalation; no resume without CDO reset.
- **Orphan recovered (completed):** Receipt flipped to `complete`; CDO + requestor notified; result handed to normal delivery path.
- **Orphan unrecoverable (failed or >24h stale):** CDO receives full receipt; CDO determines whether to regenerate; no silent discard.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| `budget_config` block missing for a client | Hard stop all generation. Escalate to CDO to provide the config. Never generate without a defined budget cap. |
| `current_period_spend + estimated_cost > monthly_cap` | Hard stop. Notify CDO with spend summary + estimated cost. Await producer override receipt. |
| `estimated_cost > per_job_approval_threshold` | Pause submission. Request producer approval receipt from CDO. |
| Per-deliverable cap exceeded mid-job | Halt all remaining tasks for this job. Write circuit-breaker incident receipt. Notify CDO. |
| Per-day aggregate cap exceeded | Halt all new client submissions. Notify CDO. |
| Orphaned receipt `state: failed` | Escalate to CDO with full receipt. Do not silently retry. |
| Orphaned receipt `last_polled` > 24 hours, no completion | Escalate to CDO. Do not discard or silently abandon. |
| Receipt file write fails (filesystem error) | Hard stop all generation immediately. No task should exist without a receipt. Escalate to CDO. |
| Smoke test fails (first-ever generation) | Hard stop. Do not proceed to production generation until the smoke test passes. Diagnose key reachability, hosting plumbing, and receipt write path. Escalate to CDO. |
| Duplicate `filled_prompt_hash` found in `state: submitted` | Do not create a new task. Re-poll the existing `taskId`. Log the dedup event in the existing receipt. |

---

*Library-version pin: MODEL-SPECS v1.0, TEST-PROTOCOL v1.0, PPT-ANALYSIS-SOP v1.0 (§-refs verified 2026-06-12).*
