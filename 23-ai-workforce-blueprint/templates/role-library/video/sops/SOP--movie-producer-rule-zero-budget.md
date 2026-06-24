# SOP -- Movie Producer (Automated Video Production) — Rule-Zero & Budget Control

**Source:** video/automated-video-production-specialist-openmontage.md (registered slug UNCHANGED; display title "Movie Producer (Automated Video Production)").
**Authority:** This is the binding safety SOP for the Movie Producer role. It applies to EVERY production job regardless of pipeline type. The per-pipeline-type SOPs (`documentary-montage`, `short-form`, `vsl`) call back into this SOP before any paid call. Violations of Rule Zero are hard stops, not warnings.
**Department:** Video
**Reports to:** Head of Video Production
**Skill:** 47-movie-producer (installs the upstream OpenMontage engine on the client box at runtime — AGPLv3 source is NEVER vendored into this template)
**Generated for:** {{COMPANY_NAME}}
**Last updated:** {{GENERATION_DATE}}

> **Rule Zero (binding):** Announce provider + model identifier + estimated cost in USD BEFORE any paid API call. Pass a human-approval checkpoint (`config.yaml` `require_approval_for_new_paid_tool: true`, `single_action_approval_usd: 0.50`) before each paid action. `ffprobe` validates every rendered MP4 before delivery. The client `config.yaml` budget cap (`budget.mode: cap`, `budget.total_usd`) MUST NOT be exceeded. Kie.AI is the ONLY generative provider on the client box; native paid providers (FAL/Runway/HeyGen/OpenAI/Google) report UNAVAILABLE. The CLIENT's own `KIE_API_KEY` is used; the operator's key NEVER appears on the client box.

---

## DMAIC Coverage Map

These controls are organized around DMAIC (Define, Measure, Analyze, Improve, Control). Each phase below is a binding section.

- **Define** — establish the budget envelope and approval authority for the job (SOP RZ-1).
- **Measure** — quantify the dollar cost of every planned paid call and the remaining budget (SOP RZ-2).
- **Analyze** — gate the planned paid calls behind the explicit Rule-Zero announce/approve step (SOP RZ-3).
- **Improve** — enforce the gate during execution: per-call approval at the `single_action_approval_usd` threshold (SOP RZ-4).
- **Control** — reconcile actual spend, trip the circuit breaker, and log the audit trail (SOP RZ-5).

---

## Define

*DMAIC phase: Define. Establish exactly what spend is authorized, by whom, and under what cap before any work begins.*

### SOP RZ-1 -- [VID-MP-RZ-1] Budget Envelope and Approval Authority

**DMAIC phase:** Define
**When to run:** At the start of every production job, before the pipeline-type SOP begins.
**Frequency:** Per production job.
**Inputs:** The job brief's budget ceiling, the client `config.yaml` `budget` block, the designated approval authority (Head of Video Production).

**Steps:**

1. Read the client `config.yaml` `budget` block. Confirm `budget.mode: cap` is set. If it is not `cap`, HARD STOP — do not run any job until the cap mode is configured. A box without `budget.mode: cap` could spend unbounded client money.
2. Record the authorized envelope: `budget.total_usd` (the absolute ceiling), `single_action_approval_usd` (default `0.50`), and `require_approval_for_new_paid_tool` (must be `true`).
3. Identify the approval authority for this job (Head of Video Production by default; or the explicitly named approver in the brief). Rule-Zero approvals are only valid from this authority.
4. Confirm the brief's stated budget ceiling does not exceed `budget.total_usd`. If it does, return a gap to the requestor: the brief asks for more than the configured cap; the cap must be raised with explicit client approval, or the brief scope reduced.

**Outputs:** Recorded budget envelope (`total_usd`, `single_action_approval_usd`, `require_approval_for_new_paid_tool`, approval authority) attached to the job manifest.
**Hand to:** SOP RZ-2 (cost measurement).
**Failure mode:** Starting a job on a box where `budget.mode` is not `cap`. The cap is the only structural guarantee against an unbounded spend; never bypass this Define step.

---

## Measure

*DMAIC phase: Measure. Quantify the exact dollar cost of every planned paid call against the envelope before committing.*

### SOP RZ-2 -- [VID-MP-RZ-2] Cost Estimation and Remaining-Budget Computation

**DMAIC phase:** Measure
**When to run:** After the pipeline-type SOP has enumerated the planned Kie API calls and before SOP RZ-3.
**Frequency:** Per production job that involves at least one paid call.
**Inputs:** The list of planned Kie image/video calls (count + model per call), the per-call price from `07-kie-setup/EXAMPLES.md` or the client's `_local/PRICING.md`, the budget envelope from SOP RZ-1.

**Steps:**

1. For each planned Kie image call (`gpt-image-2-image-to-image` / `gpt-image-2-text-to-image`), multiply count by the current per-task price.
2. For each planned Kie video call (`gemini-omni-video` / `veo3` / `veo3_fast`), multiply count by the current per-task price.
3. Sum to a single `estimated_cost_usd`. Free `documentary-montage.yaml` paths estimate `$0.00` and skip the rest of this multi-SOP's paid gates.
4. Compute `remaining_usd = budget.total_usd - cumulative_spend_to_date - estimated_cost_usd`. If `remaining_usd < 0`, the job over-spends the cap: HARD STOP, escalate to the approval authority per SOP RZ-1 step 4.
5. Write `estimated_cost_usd`, `remaining_usd`, and the per-call breakdown to the job manifest.

**Outputs:** `estimated_cost_usd`, `remaining_usd`, per-call price breakdown in the job manifest.
**Hand to:** SOP RZ-3 (announce/approve) for paid jobs; the pipeline-type SOP's render step directly for free jobs.
**Failure mode:** Estimating from memory instead of the current price source. Kie prices change; always read `07-kie-setup/EXAMPLES.md` or the client `_local/PRICING.md` at estimation time.

---

## Analyze

*DMAIC phase: Analyze. Gate the planned spend behind an explicit human announce/approve step before any money moves.*

### SOP RZ-3 -- [VID-MP-RZ-3] Rule-Zero Announce and Approval Gate

**DMAIC phase:** Analyze
**When to run:** For every job with at least one paid Kie call. SKIP for zero-cost free pipelines.
**Frequency:** Per paid job; plus a scoped second approval for any new paid tool type (`require_approval_for_new_paid_tool: true`).
**Inputs:** Job manifest with `estimated_cost_usd`, the planned-call list, the budget envelope.

**Steps:**

1. Post the Rule-Zero announcement to the approval authority. It MUST contain: job ID, pipeline selected, per-capability call counts + models, provider (`Kie.AI`), endpoint(s), estimated per-call and total cost, the client budget cap, the remaining budget, and the explicit statement that the CLIENT's `KIE_API_KEY` is used (operator key never used). End with `WAITING FOR APPROVAL`.
2. Do NOT proceed until the authority returns `APPROVE` (case-insensitive). On `REJECT`, cancel and record `status: rejected`, `rejected_at`, `rejection_reason` in the manifest.
3. If this job introduces a paid tool type (model ID) not previously approved on this client box, obtain a SECOND scoped approval for that tool type before proceeding.
4. Record `rule_zero_announced_at`, `approval_received_at`, `approved_by`, `approved_total_usd` in the manifest.

**Outputs:** Approval receipt in the job manifest, or a cancellation record.
**Hand to:** SOP RZ-4 (in-run enforcement) / the pipeline-type SOP's generation step upon approval.
**Failure mode:** Submitting a Kie call without the announcement and approval. This is a hard violation: halt the job, record the already-submitted call as an unauthorized-spend incident, and escalate to the owner.

---

## Improve

*DMAIC phase: Improve. Enforce the approval gate per-call during execution so the control actually binds the run, not just the plan.*

### SOP RZ-4 -- [VID-MP-RZ-4] Per-Call Threshold Enforcement During Execution

**DMAIC phase:** Improve
**When to run:** During pipeline execution, immediately before each paid Kie call is submitted.
**Frequency:** Once per paid call.
**Inputs:** The approved manifest, the running cumulative spend, the `single_action_approval_usd` threshold.

**Steps:**

1. Before submitting any single Kie call estimated at or above `single_action_approval_usd` ($0.50 default), obtain that call's own individual approval. A batch approval does not cover an individual call at or above the threshold.
2. After each call returns, add its actual cost to the running cumulative spend in the manifest. Record the `kie_task_id` and `kie_result_url` as the render-proof receipt — never fabricate either.
3. After each call, re-check cumulative spend against the cap. If cumulative spend reaches 80% of `budget.total_usd`, PAUSE the run and notify the approval authority before any further paid call.
4. NEVER switch to a native paid provider mid-job if Kie is unavailable — the job pauses; it does not silently fall back to a different paid provider.

**Outputs:** Per-call approval records and `kie_task_id`/`kie_result_url` receipts in the manifest; running cumulative-spend field kept current.
**Hand to:** SOP RZ-5 (reconciliation) after the last call; the pipeline-type SOP's ffprobe step after render.
**Failure mode:** Letting a run proceed past 80% of cap without a pause and notification. The 80% pause is what prevents a silent overrun; it is mandatory.

---

## Control

*DMAIC phase: Control. Reconcile actual vs. estimated spend, trip the circuit breaker at the cap, and preserve the audit trail.*

### SOP RZ-5 -- [VID-MP-RZ-5] Spend Reconciliation, Circuit Breaker, and Audit Trail

**DMAIC phase:** Control
**When to run:** After every job's last paid call (or at job completion for free jobs).
**Frequency:** End of every production job.
**Inputs:** All per-call receipts, the manifest's `estimated_cost_usd`, the `config.yaml` budget config.

**Steps:**

1. Sum all actual Kie charges for the job. Compare to `estimated_cost_usd`. If actual > estimated, log the variance to `_local/budget-log.md` with job ID, estimated vs. actual, and cause.
2. If cumulative client spend has reached or exceeded `budget.total_usd`: trip the circuit breaker — halt all further production on this client box, write a circuit-breaker entry to `_local/budget-log.md`, and notify the approval authority. Do not resume until the authority provides written authorization and updates the cap.
3. Write final budget fields to the job manifest: `actual_cost_usd`, `budget_remaining`, the list of `kie_task_ids` and `kie_result_urls`.
4. Retain `render-receipt.json` and `job-manifest.json` permanently as the budget audit trail. These are the anti-fabrication proof for every paid generation.

**Outputs:** Reconciliation entry in `_local/budget-log.md`, finalized budget fields in the manifest, permanent audit-trail files.
**Hand to:** The cross-role handoff SOP (`SOP--movie-producer-cross-role-handoff.md`) for delivery routing.
**Failure mode:** Treating a missing `kie_task_id`/`kie_result_url` as acceptable. A missing receipt means either the generation did not happen (fabrication) or it was not logged (a logging failure). Either is a hard fail — recover the receipt from the API log or rerun the generation before delivering.

---

*SOPs owned: [VID-MP-RZ-1], [VID-MP-RZ-2], [VID-MP-RZ-3], [VID-MP-RZ-4], [VID-MP-RZ-5]. sop_count: 5.*
*Token inventory: `{{COMPANY_NAME}}`, `{{GENERATION_DATE}}`. All other tokens live in the parent role file.*
