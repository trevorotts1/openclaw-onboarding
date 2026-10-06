# SOPs Mirror -- Generation Operator ("The Operator") -- DIU

**Source:** graphics/generation-operator.md
**Extract:** Section 9 (Standard Operating Procedures), condensed mirror: SOP numbers, gate numbers, state names, field names, windows and ownership match the role file; prose is shortened in 9.5 to 9.7.
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
7. Submit through Skill 74 (`kie_live_adapter.py submit --request <req.json> --mode active`) with the exact JSON template from MODEL-SPECS §5 for the selected endpoint, after the live `validate`, `prompt-budget --check` and `preflight` calls pass (SOP 9.4). Write the receipt file at submit time from the returned `task_id`, with all required fields.
8. Exit. The Render Dispatcher's poller handles completion detection. Do not hold the session open.

**Outputs:** Receipt file in `_local/receipts/` with state `submitted`; job directory with compiled negatives artifact.
**Hand to:** CDO/requestor when the Render Dispatcher's poller completes postflight verification and flips the receipt to `complete`. Off-style results after postflight -> Fidelity Tester (SOP-DIU-501a). Hard-rule violations -> quarantine (SOP 9.7).
**Failure mode:** Any preflight failure returns an itemized failure list to the requestor and appends a `preflight-failed` line to the shared `_local/dispatch-log.md` (no receipt exists before submission). Never submit a failing preflight. Never improvise a fix to a preflight failure -- that is prompt authoring, not operator work.

---

### SOP 9.2 -- [SOP-DIU-302] Model Routing & API Execution

**Vendor SOP.** Wraps `_system/MODEL-SPECS.md` §§2, 5.
**Library-version pin:** MODEL-SPECS v1.0 (§-refs verified 2026-06-12).
**When to run:** As part of every generation workflow; determines which Kie.ai endpoint receives the task.
**Frequency:** On-demand, per job.
**Inputs:** Generation request with model preference or "auto-route" flag, resolution, tier, aspect ratio.

**Steps:**
1. Read the First-choice column of the MODEL-SPECS routing table for the requested category and tier. Use the primary endpoint unless it is flagged `degraded` in current receipts or is explicitly down.
2. Verify the primary endpoint supports the requested aspect ratio and resolution. If not, check the Backup column. If neither supports the request, return to the requestor with a list of supported aspect ratios -- do not silently change the ratio.
3. Apply the LONG-to-MEDIUM fallback rule (MODEL-SPECS §3): if the primary endpoint's LONG tier is unavailable, fall back to MEDIUM on the same endpoint. If MEDIUM is also unavailable, fall to the backup endpoint with explicit CDO notification. Never silently downgrade resolution.
4. Select the exact JSON template from MODEL-SPECS §5 for the resolved endpoint. Do not edit the template structure -- only fill the designated variable slots.
5. Verify the API key is reachable (check all env stores per the client-box-env-stores protocol) before submitting. A missing key is a hard stop -- do not guess at key locations.
6. Submit through Skill 74 (`submit --mode active`; this is the only `createTask` call in the department). Record the returned `task_id` in the receipt immediately. When the department or the request pins no model, resolve the GPT Image default with `latest-family --family gpt-image` (rule 13) and record the resolved id; never type a model id from memory.

**Outputs:** Task submitted with receipt file recording endpoint, model ID, tier, resolution, `taskId`, and cost class.
**Hand to:** The Render Dispatcher's poller for completion detection via `recordInfo`.
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
**Full form:** the standalone `sops/SOP-DIU-601.md` is the complete ten-step preflight. Its step 1 verifies the API key across all env stores first, its step 2 is the band gate (item 1 below), and its step 10 checks the exploratory-mode tag; run those too. This list is the condensed form and never overrides that file.

**Preflight checklist (run in this order -- any failure = halt and return itemized list to sender):**

1. **API key reachable:** Verify `KIE_API_KEY` (or any alias in the KIE family in `shared-utils/secret_names.json`) is present in every env store before any other check. A key absent from all stores is a hard stop; do not guess at key location.
2. **Char count -- MIN floor AND MAX cap, both hard-gated (mirrors presentations' `build_deck.py` fail-closed shape):** Run `python3 45-design-intelligence-library/scripts/diu_validator.py prompt-band --band <asset-class band> --prompt-file <assembled-prompt>` against `45-design-intelligence-library/library/_system/prompt-bands.json` BEFORE any endpoint-cap check. The requesting role's assembly packet declares the band (`text_bearing_long` for copy-bearing deliverables on GPT-Image T2I/I2I (2.5 `sunburst` by default per N43; the retained legacy GPT-Image-2 only for 3:1, 1:3, 9:21), `text_bearing_medium` for the Ideogram V3 DESIGN route mandatory on quote-card/text-led posts, `visual_long` for photoreal/brand imagery without baked text, `medium` for non-text-bearing Seedream quick posts, `short_draft` for internal drafts ONLY, never a client deliverable; the band names and the quality teeth below still apply; the length numbers (target, floor, ceiling) are defined only by rule 12 of `07-kie-setup/references/kie-common-rules.md` and read from `kie_live_adapter.py prompt-budget --check`, so run that call too, and when its verdict and the band validator's differ, the stricter one blocks the submit; the thresholds inside `prompt-bands.json` and `diu_validator.py` are owned by the prompt-band code work, not by this role). A prompt under its band MIN is refused (exit 3, AF-GIP-PROMPT-FLOOR) before you even look at the endpoint's own cap -- this is the floor that was previously missing entirely (G1). A prompt that clears length but fails the length-independent quality teeth (8-class negative block, per-string spelling-locks on text-bearing bands, distinct-word density, style-reference-only directive, no hardcoded demographic split) is also refused (exit 6, AF-GIP-PROMPT-QUALITY). Only after the band gate passes, verify against the endpoint's own cap from MODEL-SPECS §1 (Seedream 4.5 text-to-image and edit: 3,000 characters, the vendor's published maxLength on docs.kie.ai, verified 2026-10-06 (Seedream 5.0 Lite 3,000; 5.0 Pro and Flash 5,000). Skill 66's NOT_PUBLISHED entry for Seedream is stale and Skill 74's live schema is the ongoing source). Return "PREFLIGHT FAIL: char count {actual} exceeds endpoint cap {cap}" if over the endpoint cap; return the validator's own exit-3/exit-6 message verbatim if the band gate fails. Never submit a floor-failed or quality-failed prompt back to the requesting role's original text -- send the itemized gate failure, never a silent pass-through.
3. **Unfilled variables:** Grep for any `{[A-Z_]+}` token remaining in the assembled prompt. Return "PREFLIGHT FAIL: unfilled variables: {list}" if any found.
4. **Aspect ratio supported:** Verify the requested aspect ratio appears in the endpoint's supported-ratio table (MODEL-SPECS §1). Return "PREFLIGHT FAIL: aspect ratio {ratio} not supported by {endpoint}" if absent.
5. **Required params set:** Verify all endpoint-required params are present in the JSON template: `aspect_ratio` for Seedream; `expand_prompt: false` + `aspect_ratio` resolving to a preset for Ideogram production runs; `watermark: false` for Wan. Return "PREFLIGHT FAIL: missing required param {param}" for each absent param.
6. **Style-reference-only directive:** If `image_input` / `input_urls` / `image_urls` are set, verify `style_reference_only: true` (or equivalent per-endpoint field) is also set per MODEL-SPECS §4. Return "PREFLIGHT FAIL: reference images present but style_reference_only not set" if absent.
7. **Identity Lock Block presence:** If the job is flagged `likeness: true`, verify the Identity Lock Block is present verbatim at the end of the positive prompt. Return "PREFLIGHT FAIL: likeness job missing Identity Lock Block" if absent.
8. **Avoid-list contradiction audit:** Confirm the compiled negatives artifact has been produced for this job and the contradiction audit in SOP 9.3 step 5 passed. Return "PREFLIGHT FAIL: compiled negatives missing or contradiction audit not completed" if absent.
9. **Schema validity, budget headroom and credit:** Run `kie_live_adapter.py validate --model <id> --payload <input.json>` and fix every listed error; then `price --model <id> [--units N]` for the estimate (the live `pricingDesc`, the only price authority) and verify it does not exceed remaining budget headroom for this period; then `preflight --model <id> [--units N]`, which passes only when the live credit balance covers the estimate x 1.30 (rule 6 of the canonical rules). If within the per-job approval threshold, require producer approval receipt before proceeding.
10. **Exploratory mode tag:** If the requestor flagged `mode: exploratory` (non-production `expand_prompt: true` or thinking-mode run), verify the packet carries the exploratory tag so the receipt records the output as non-production and it never enters the style library.

**Postflight checklist (run by the Render Dispatcher's poller immediately on a `success` task result, recorded in the Operator's receipt):**

1. **Download immediately.** Read `resultUrls` from the `recordInfo` response (`data.resultJson` is a JSON string) and download all of them to `_local/results/{job-id}/`. Do not log anything as complete before local files exist.
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
**When to run:** Receipt created at submission; budget gate before every job; circuit breaker checked against every new spend event. Orphan recovery is run by the Render Dispatcher (its SOP 9.7), not by the Operator.
**Frequency:** Continuous (receipt lifecycle); per-job (budget gate).

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
actual_cost:          {dollars or null}
state:                {queued|held|preflight-failed|submitted|polling|complete|failed|postflight-failed|quarantined|hard-stopped|orphaned}
submitted_at:         {iso8601}
last_polled:          {iso8601}
completed_at:         {iso8601 or null}
local_path:           {absolute path or null}
sha256:               {hex or null}
preflight_passed:     {true|false}
postflight_verified:  {true|false}
seed:                 {value or "no-seed-endpoint"}
filled_prompt_hash:   {request fingerprint: sha256(model + endpoint + tier + full_filled_positive_prompt + seed + card_id + card_version); the one formula, defined here}
prompt_path:         {path to the stored filled prompt file in the job dir}
company_id:         {client-box-id}
dept:               {department-slug}
smoke_test:         {true|false}
```

The Operator creates the receipt at submit time; the Dispatcher only advances lifecycle fields on it. `queued`, `held` and `preflight-failed` happen before any task exists and are not receipt states: the Operator appends a `preflight-failed` line to the shared `_local/dispatch-log.md` when its own preflight rejects a packet, and the Dispatcher logs `queued`, `held` and its own pre-dispatch failures there; they stay in the enum so one vocabulary serves both files.

**Budget gate (before every new job):**
1. Estimate cost: `num_tasks x price_per_task` using the live `pricingDesc` for the selected model and tier (the only price authority; `_local/PRICING.md` holds billed actuals and budget config, not authoritative prices).
2. Sum all `complete` receipts for the current billing period (`actual_cost` where set, else `cost_class`).
3. If `current_period_spend + estimated_cost > monthly_cap`: hard stop. Notify CDO. Do not proceed without a producer override receipt.
4. If `estimated_cost > per_job_approval_threshold`: require a producer approval receipt before submitting.
5. First-ever generation for this client: run a 1K SHORT smoke test on the cheapest capable endpoint first. The smoke-test prompt is sized per rule 12 like any other (a smoke test saves money through the cheapest capable model and 1K resolution, never through a short prompt).

**Orphan recovery (owned by the Render Dispatcher, its SOP 9.7; the Operator does not poll):**
1. List all receipts with `state: submitted` or `state: polling`.
2. For each: call `recordInfo` for the taskId. If `state: success`: proceed to SOP 9.4 postflight. If `state: fail`: flip the receipt to `failed` and escalate to CDO. Otherwise (`waiting`, `queuing`, `generating`): update `last_polled` and leave for the cron.
3. Any receipt still without a completion state past its max-in-flight window (2 hours standard jobs, 8 hours deck fan-outs): escalate to CDO; a `submitted` receipt older than 30 days is a confirmed orphan (`state: orphaned`).

**Circuit breaker:**
1. After every completed or failed task, sum all spend for the current deliverable.
2. If spend has exceeded the per-deliverable cap: halt all remaining tasks, notify CDO, write a circuit-breaker incident receipt.
3. If daily aggregate spend exceeds the per-day cap: halt all new submissions, notify CDO.
4. Thresholds live in the client's `budget_config` block -- never hardcoded in this SOP.

**Outputs:** Receipt files persisted in `_local/receipts/`; CDO escalation for circuit-breaker trips (orphan results and escalations come from the Render Dispatcher).
**Hand to:** Render Dispatcher's poller (submitted receipts); CDO + requestor (completed receipts, after the Dispatcher's postflight); CDO (circuit-breaker events).
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
| **5xx / timeout (transient)** | Before any `createTask` response arrives (connection refused, DNS or TLS failure): retry once after 30-second backoff. After `createTask` was sent and no `task_id` came back: do NOT resubmit (it may already be charged); hand the packet to the Render Dispatcher to check for an orphan before any new submit | If the retry fails: route to backup endpoint (MODEL-SPECS §2 Backup column) with CDO notification | If backup also fails: hard stop, preserve manifest + receipts, notify CDO |
| **429 (rate limit)** | Back off and halve concurrency, staying inside the canonical Kie limits (createTask 20 per 10 seconds per account; rule 3 of the canonical rules; MODEL-SPECS carries no rate-limit guidance) | Continue with reduced concurrency | If 429 persists >3 events in 10 minutes: hard stop, notify CDO |
| **Endpoint down** | Route to backup endpoint from MODEL-SPECS §2 Backup column; notify CDO | -- | If backup also down: hard stop, preserve all manifests + receipts |
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
5. Ask the Render Dispatcher (it advances every receipt's lifecycle fields; you created the receipt and never rewrite it) to set the generating receipt `state` to `quarantined`.
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
