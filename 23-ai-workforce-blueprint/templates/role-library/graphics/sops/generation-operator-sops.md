# SOPs Mirror -- Generation Operator ("The Operator") -- DIU

**Source:** graphics/generation-operator.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Library-version pin:** MASTER-SOP v1.0, MODEL-SPECS v1.0, NEGATIVE-PROMPTING-SOP v1.0, PHOTO-SHOOT-SOP v1.0, TEST-PROTOCOL v1.0, PPT-ANALYSIS-SOP v1.0 (§-refs verified 2026-06-12).

---

## 9. Standard Operating Procedures (Numbered)

### SOP 9.1 -- [SOP-DIU-301] Style-Based Generation (Workflow B)

**Vendor SOP.** Wraps `_system/MASTER-SOP.md` Workflow B.
**Library-version pin:** MASTER-SOP v1.0 (§-refs verified 2026-06-12).
**When to run:** On receipt of a validated assembly packet requesting generation using an existing style card.
**Frequency:** On-demand, per generation request.
**Inputs:** Style card ID + version (resolved in INDEX.md); all filled `{VARIABLE}` tokens; model + tier; aspect ratio; resolution; budget cap; Identity Lock Block (if likeness job, assembled by Photo Shoot Director and included verbatim).

**Steps:**
1. Confirm the style card ID exists in INDEX.md with `status: production`. If the card is `draft` or `tested`, halt and return to requesting role: production cards only ship to clients.
2. Read the card file at the specified version. Do not use any other version without explicit requester instruction.
3. Assemble the positive prompt per MASTER-SOP Workflow B step order: Foundation Block -> Subject Block -> Style DNA (copy verbatim from card) -> variables filled -> Identity Lock Block appended last if present.
4. Confirm `expand_prompt: false` is set (Ideogram) or `thinking_mode` is off (Wan) unless the requestor has explicitly flagged `mode: exploratory` (non-production run). In production, MagicPrompt and thinking-mode re-writes corrupt the card's style contract.
5. Select model and tier per MODEL-SPECS routing table. Verify the selected endpoint supports the requested aspect ratio.
6. Run SOP 9.4 (SOP-DIU-601) preflight before submitting. Do not proceed if preflight fails.
7. Submit via `createTask` with the exact JSON template from MODEL-SPECS §5 for the selected endpoint. Write the receipt file at submit time with all required fields.
8. Exit. The cron poller handles completion detection. Do not hold the session open.

**Outputs:** Receipt file in `_local/receipts/` with state `submitted`; job directory with compiled negatives artifact.
**Hand to:** CDO/requestor when the cron poller completes postflight verification and flips the receipt to `complete`. Off-style results after postflight -> Fidelity Tester (SOP 9.5). Hard-rule violations -> quarantine (SOP 9.7).
**Failure mode:** Any preflight failure returns an itemized failure list to the requestor and logs the rejection in the receipt. Never submit a failing preflight. Never improvise a fix to a preflight failure -- that is prompt authoring, not operator work.

---

### SOP 9.2 -- [SOP-DIU-302] Model Routing & API Execution

**Vendor SOP.** Wraps `_system/MODEL-SPECS.md` §§2, 5.
**Library-version pin:** MODEL-SPECS v1.0 (§-refs verified 2026-06-12).
**When to run:** As part of every generation workflow; determines which Kie.ai endpoint receives the task.
**Frequency:** On-demand, per job.
**Inputs:** Generation request with model preference or "auto-route" flag, resolution, tier, aspect ratio.

**Steps:**
1. Read the PRIMARY column of the MODEL-SPECS routing table for the requested category and tier. Use the primary endpoint unless it is flagged `degraded` in current receipts or is explicitly down.
2. Verify the primary endpoint supports the requested aspect ratio and resolution. If not, check the SECONDARY (backup) column. If neither supports the request, return to the requestor with a list of supported aspect ratios -- do not silently change the ratio.
3. Apply the LONG-to-MEDIUM fallback rule (MODEL-SPECS §3): if the primary endpoint's LONG tier is unavailable, fall back to MEDIUM on the same endpoint. If MEDIUM is also unavailable, fall to the backup endpoint with explicit CDO notification. Never silently downgrade resolution.
4. Select the exact JSON template from MODEL-SPECS §5 for the resolved endpoint. Do not edit the template structure -- only fill the designated variable slots.
5. Verify the API key is reachable (check all env stores per the client-box-env-stores protocol) before submitting. A missing key is a hard stop -- do not guess at key locations.
6. Submit via `createTask`. Record the returned `taskId` in the receipt immediately.

**Outputs:** Task submitted with receipt file recording endpoint, model ID, tier, resolution, `taskId`, and cost class.
**Hand to:** Cron poller for completion detection via `getTaskInfo`.
**Failure mode:** If the API key is missing from all env stores, escalate to CDO with the list of stores checked. Never proceed without a verified key. If both primary and backup endpoints are unavailable, escalate to CDO -- do not substitute an out-of-spec model.

---

### SOP 9.3 -- [SOP-DIU-303] Negative Prompt Assembly

**Vendor SOP.** Wraps `_system/NEGATIVE-PROMPTING-SOP.md` §§1-3.
**Library-version pin:** NEGATIVE-PROMPTING-SOP v1.0 (§-refs verified 2026-06-12).
**When to run:** Before every generation; for multi-asset jobs, compiled once and cached.
**Frequency:** Per job (multi-asset: once at job start).
**Inputs:** Style card avoid-list entries (from card body), category `_RULES.md` hard-rule avoid list, universal baseline avoid-list from NEGATIVE-PROMPTING-SOP §2.

**Steps:**
1. Pull Layer 1 (universal baseline negatives) from NEGATIVE-PROMPTING-SOP §2. This layer is non-negotiable and appears in every generation.
2. Pull Layer 2 (category-specific negatives) from the relevant category `_RULES.md` avoid-list section.
3. Pull Layer 3 (card-specific negatives) from the style card's avoid-list entries.
4. Merge all three layers. Deduplicate exact-string matches. Preserve semantically distinct entries even if they address similar concerns.
5. Run the contradiction audit (NEGATIVE-PROMPTING-SOP §4): scan for any negative-prompt entry that directly contradicts a term in the positive Foundation Block or Style DNA. Any contradiction halts assembly and returns to the prompt author -- do not resolve contradictions by guessing which term to drop.
6. Select the per-model rendering format: Ideogram -> `negative_prompt` field; Wan/Seedream -> inline "Do not..." paragraph (top 10 items max for Seedream, per its character budget). Record the rendering format in the compiled artifact.
7. For multi-asset jobs: write the compiled negative artifact to the job directory as `compiled-negatives.json`. Every asset in this job references this file -- do not re-derive.

**Outputs:** Compiled negative artifact (cached for multi-asset jobs); negative-prompt payload ready for injection into the JSON template.
**Hand to:** SOP 9.1 (Workflow B) step 4 -- injected into the final assembled prompt before preflight.
**Failure mode:** If a contradiction is found in step 5, return the full conflict (positive term vs negative term, both with source citations) to the prompt author. Never resolve a contradiction unilaterally.

---

### SOP 9.4 -- [SOP-DIU-601] Preflight & Postflight Mechanical Gates

**ZHC SOP.** Wraps MODEL-SPECS §§1, 3, 4, 5; MASTER-SOP §3.2, §5; NEGATIVE-PROMPTING-SOP §4; PHOTO-SHOOT-SOP §4.
**Library-version pin:** MODEL-SPECS v1.0, MASTER-SOP v1.0, NEGATIVE-PROMPTING-SOP v1.0, PHOTO-SHOOT-SOP v1.0 (§-refs verified 2026-06-12).
**When to run:** Preflight -- before every API submission. Postflight -- immediately after every result download.
**Frequency:** Every single generation, no exceptions.

**Preflight checklist (run in this order -- any failure = halt and return itemized list to sender):**

1. **Char count:** Count actual characters in the fully assembled positive prompt. Verify against the endpoint's cap from MODEL-SPECS §1 (Seedream: 3,000-char hard ceiling -- silent fail above this). Return "PREFLIGHT FAIL: char count {actual} exceeds endpoint cap {cap}" if over.
2. **Unfilled variables:** Grep for any `{[A-Z_]+}` token remaining in the assembled prompt. Return "PREFLIGHT FAIL: unfilled variables: {list}" if any found.
3. **Aspect ratio supported:** Verify the requested aspect ratio appears in the endpoint's supported-ratio table (MODEL-SPECS §1). Return "PREFLIGHT FAIL: aspect ratio {ratio} not supported by {endpoint}" if absent.
4. **Required params set:** Verify all endpoint-required params are present in the JSON template: `aspect_ratio` for Seedream; `expand_prompt: false` + `aspect_ratio` resolving to a preset for Ideogram production runs; `watermark: false` for Wan. Return "PREFLIGHT FAIL: missing required param {param}" for each absent param.
5. **Style-reference-only directive:** If `image_input` / `input_urls` / `image_urls` are set, verify `style_reference_only: true` (or equivalent per-endpoint field) is also set per MODEL-SPECS §4. Return "PREFLIGHT FAIL: reference images present but style_reference_only not set" if absent.
6. **Identity Lock Block presence:** If the job is flagged `likeness: true`, verify the Identity Lock Block is present verbatim at the end of the positive prompt. Return "PREFLIGHT FAIL: likeness job missing Identity Lock Block" if absent.
7. **Avoid-list contradiction audit:** Confirm the compiled negatives artifact has been produced for this job and the contradiction audit in SOP 9.3 step 5 passed. Return "PREFLIGHT FAIL: compiled negatives missing or contradiction audit not completed" if absent.
8. **Budget headroom:** Verify estimated job cost (from PRICING.md) does not exceed remaining budget headroom for this period. If within the per-job approval threshold, require producer approval receipt before proceeding.

**Postflight checklist (run immediately on receipt of a `completed` task result):**

1. **Download immediately.** Call `getResultInfo` and download all `resultUrls` to `_local/results/{job-id}/`. Do not log anything as complete before local files exist.
2. **Nonzero size.** Verify each downloaded file has size > 0 bytes.
3. **Decodable image.** Open and decode each file.
4. **Dimensions match request.** Verify the actual pixel dimensions match the requested resolution and aspect ratio.
5. **Record sha256.** Hash each verified file and record in the receipt.
6. **Flip receipt state.** Only after all five postflight checks pass: update the receipt `state` to `complete`, record delivery path, and notify the requesting role and CDO.

**Outputs:** Preflight: pass/fail verdict with itemized failure list if failed. Postflight: verified local files with sha256; receipt flipped to `complete`.
**Hand to:** SOP 9.1 (Workflow B) after preflight pass. CDO + requesting role after postflight completion. Hard-rule violations detected during postflight visual inspection -> SOP 9.7 (quarantine).
**Failure mode:** Any preflight failure halts submission. Never submit with a known preflight violation. Postflight verification failure flips the receipt to `postflight-failed` and escalates to CDO -- do not re-submit without CDO direction.

---

### SOP 9.5 -- [SOP-DIU-602] Generation Receipts, Budget Gate & Orphan Recovery

**ZHC SOP.** Wraps MODEL-SPECS §5; TEST-PROTOCOL §4, §7; PPT-ANALYSIS-SOP §3B.
**Library-version pin:** MODEL-SPECS v1.0, TEST-PROTOCOL v1.0, PPT-ANALYSIS-SOP v1.0 (§-refs verified 2026-06-12).
**When to run:** Receipt written at submission; orphan recovery at every session start; budget gate before every job; circuit breaker checked against every new spend event.
**Frequency:** Continuous (receipt lifecycle); session-start (orphan sweep); per-job (budget gate).

**Receipt schema (required fields):**

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
filled_prompt_hash:   {sha256 of exact filled positive prompt}
```

**Budget gate (before every new job):**
1. Estimate cost: `num_tasks x price_per_task` from `_local/PRICING.md` for the selected model and tier.
2. Sum all `complete` receipt `cost_class` values for the current billing period.
3. If `current_period_spend + estimated_cost > monthly_cap`: hard stop. Notify CDO. Do not proceed without a producer override receipt.
4. If `estimated_cost > per_job_approval_threshold`: require a producer approval receipt before submitting.
5. First-ever generation for this client: run a 1K SHORT smoke test on the cheapest capable endpoint first.

**Orphan recovery (session start):**
1. List all receipts with `state: submitted` or `state: polling`.
2. For each: call `getTaskInfo(taskId)`. If `status: completed`: proceed to SOP 9.4 postflight. If `status: failed`: escalate to CDO. If `status: processing`: update `last_polled` and leave for the cron.
3. Any receipt with `last_polled` older than 24 hours with no completion: escalate to CDO.

**Circuit breaker:**
1. After every completed or failed task, sum all spend for the current deliverable.
2. If spend has exceeded the per-deliverable cap: halt all remaining tasks, notify CDO, write a circuit-breaker incident receipt.
3. If daily aggregate spend exceeds the per-day cap: halt all new submissions, notify CDO.
4. Thresholds live in the client's `budget_config` block -- never hardcoded in this SOP.

**Outputs:** Receipt files persisted in `_local/receipts/`; recovered orphan results where available; CDO escalation for unrecoverable orphans and circuit-breaker trips.
**Hand to:** Cron poller (pending receipts); CDO + requestor (completed receipts); CDO (circuit-breaker and orphan-escalation events).
**Failure mode:** If the budget_config block is missing for a client, halt all generation and ask CDO to provide the config. Never generate without a budget cap defined.

---

### SOP 9.6 -- [SOP-DIU-603] Fallback Ladder & Graceful Degradation

**ZHC SOP.** Wraps MODEL-SPECS §2, §3; PPT-ANALYSIS-SOP §3C; TEST-PROTOCOL §5.
**Library-version pin:** MODEL-SPECS v1.0, PPT-ANALYSIS-SOP v1.0, TEST-PROTOCOL v1.0 (§-refs verified 2026-06-12).
**When to run:** On any API error response, rate-limit event, or endpoint-unavailability during a generation session.
**Frequency:** On-demand, triggered by failures.

**Failure class ladder (execute in order):**

| Failure class | First response | Second response | Hard stop |
|---|---|---|---|
| **5xx / timeout (transient)** | Retry once after 30-second backoff | Route to backup endpoint (MODEL-SPECS §2 SECONDARY column) with CDO notification | If backup also fails: hard stop, preserve manifest + receipts, notify CDO |
| **429 (rate limit)** | Backoff per MODEL-SPECS §2 rate-limit guidance; halve concurrency | Continue with reduced concurrency | If 429 persists >3 events in 10 minutes: hard stop, notify CDO |
| **Endpoint down** | Route to backup endpoint from MODEL-SPECS §2 SECONDARY column; notify CDO | -- | If backup also down: hard stop, preserve all manifests + receipts |
| **402 / credit exhaustion** | Immediate hard stop -- do not retry | Preserve manifest + receipts for resume; notify CDO | -- |
| **NSFW checker false positive** | Flag for CDO + human review; never auto-retry with prompt mutation | -- | CDO decides |

**Absolute rules (violations are escalation events, not judgment calls):**
- **NEVER swap models mid-deck.** A Slide Manifest is a cohesion contract. Halt and escalate.
- **NEVER silently downgrade resolution.** Re-route to a backup endpoint; do not generate at lower resolution without explicit producer approval.
- **NEVER route infra failures to the Fidelity Tester.** 429, 5xx, 402 are infrastructure noise, not style failures.
- **Preserve manifests on every stop.** Any hard stop must leave the manifest + all receipts intact.

**Outputs:** Fallback event logged to `_local/fallback-log.md` with timestamp, failure class, endpoint affected, and action taken. CDO notified for all non-transient events.
**Hand to:** Backup endpoint for successful re-route; CDO for all hard-stop events.
**Failure mode:** If both primary and backup endpoints are unavailable, the job is paused with all state preserved. CDO is notified. Do not attempt a third-endpoint substitution without explicit CDO direction.

---

### SOP 9.7 -- [SOP-DIU-604] Hard-Rule Quarantine & Incident Response

**ZHC SOP.** Wraps PHOTO-SHOOT-SOP §§1, 2, 4, 10; NEGATIVE-PROMPTING-SOP §5; TEST-PROTOCOL §3.
**Library-version pin:** PHOTO-SHOOT-SOP v1.0, NEGATIVE-PROMPTING-SOP v1.0, TEST-PROTOCOL v1.0 (§-refs verified 2026-06-12).
**When to run:** Immediately upon detection of any hard-rule violation in a generated output.
**Frequency:** On-demand, triggered by postflight visual inspection or Fidelity Tester diagnosis.

**Hard-rule triggers (any of these requires immediate quarantine -- no override path):**
- Lightened skin tone vs identity reference
- Text rendered on a subject's face
- Identity drift -- generated person does not match the identity reference
- Consent gap discovered mid-job (a non-consented person appears in the output)
- Any other output the Fidelity Tester has classified as a hard-rule fail in the Test Log

**Steps:**
1. Move the output asset immediately to `_local/quarantine/{incident-id}/`. Do not leave it in `_local/results/`, any delivery folder, or any media-library folder accessible to PHOTO-SHOOT-SOP §2's sourcing hierarchy.
2. Write an incident receipt in `_local/quarantine/{incident-id}/incident.json`: asset path, taskId, card ID + version, model, tier, filled prompt, nature of violation, detection method.
3. Notify CDO immediately with the incident receipt.
4. If the violation is identity-related: also notify the Photo Shoot Director for consent-scope review.
5. Update the generating receipt `state` to `quarantined`.
6. Feed the violation type to the Fidelity Tester's avoid-list growth protocol (NEGATIVE-PROMPTING-SOP §5).

**For post-delivery discoveries:**
1. Notify CDO immediately. CDO leads client communication.
2. Regenerate a compliant replacement via normal Workflow B.
3. Log the delivered-then-discovered incident in the incident receipt and in the card's Test Log with a `delivered-hard-fail` flag.
4. The Fidelity Tester reviews the card's avoid-list and Test Log for systemic causes.

**What quarantined assets may NEVER do:**
- Be delivered to any client
- Be used as a reference image in any future generation
- Be embedded in the style library, INDEX.md, or any card
- Leave the quarantine directory without CDO written authorization

**Outputs:** Quarantined asset in `_local/quarantine/{incident-id}/`; incident receipt; CDO + Photo Shoot Director notification (identity incidents); avoid-list growth trigger to Fidelity Tester.
**Hand to:** CDO (all incidents); Photo Shoot Director (identity incidents); Fidelity Tester (avoid-list growth).
**Failure mode:** If the output cannot be moved to quarantine (filesystem permission issue), halt all further generation immediately and escalate to CDO. Never proceed with additional generations while a hard-rule violation is unresolved.

---

*SOPs owned: [SOP-DIU-301], [SOP-DIU-302], [SOP-DIU-303], [SOP-DIU-601], [SOP-DIU-602], [SOP-DIU-603], [SOP-DIU-604]. sop_count: 7.*
