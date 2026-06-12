# SOPs Mirror -- Fidelity Tester ("The Critic") -- DIU

**Source:** graphics/fidelity-tester.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Library-version pin:** TEST-PROTOCOL v1.0, MODEL-SPECS v1.0, MASTER-SOP v1.0 (§-refs verified 2026-06-12).

---

## 9. Standard Operating Procedures (Numbered)

### SOP 9.1 -- [SOP-DIU-501a] Fidelity Test Run

**Vendor SOP.** Wraps TEST-PROTOCOL.md §§1-3 (when to run, test design, scoring rubric).
**Library-version pin:** TEST-PROTOCOL.md v1.0 (§-refs verified 2026-06-12).
**When to run:** Any new style card submitted for first-run testing; any card after a prompt-template edit (regression check per TEST-PROTOCOL §1); any production card flagged for diagnosis mode.
**Frequency:** 2-10 test runs per day, depending on card throughput and active patch loops.
**Inputs:** Card file at the current version, generation receipts for the test images (card ID+version, model, tier, exact filled prompt, seed where applicable, taskId, cost class), the three required test generations (near-transfer, far-transfer, text-stress) on locally stored, post-flight verified files. Do NOT accept a test request without a receipt.

**Steps:**
1. Confirm test generation prerequisites are met: receipt present for each test image, images locally stored (not URL links), model matches the card's recommended model.
2. Open the card at the submitted version. Confirm status is `draft` (first-run testing) or `tested`/`production` (regression or diagnosis mode).
3. Score each test image on all 12 dimensions (1-5 per dimension) using the rubric in TEST-PROTOCOL.md §3. Record each dimension score individually before computing the average.
4. Apply pass criteria: average across all 12 dimensions >= 4.0, AND no single dimension below 3, AND zero hard-rule violations. One hard-rule violation is an automatic fail regardless of all other scores.
5. Record the test as a row in the card's Test Log: date, model, tier, test type, test subject description, per-dimension scores, average, pass/fail verdict, notes.
6. Issue verdict:
   - PASS: Update card status to `tested` (first-run pass) or confirm `production` (regression pass). Update INDEX.md status field to match. Notify Style Analyst and Chief Design Officer.
   - FAIL: Enter SOP 9.2 (Patch Loop). Do NOT update the card status. Log the failure clearly in the Test Log before entering the patch loop.

**Outputs:** Test Log row(s), verdict (PASS/FAIL), INDEX.md status update (on PASS), or entry into Patch Loop (on FAIL).
**Hand to:** Style Analyst (on PASS -- card is ready for production promotion and INDEX registration via SOP-DIU-606); Chief Design Officer (on PASS); or enter SOP 9.2 (on FAIL).
**Failure mode:** If test images are missing or receipts are absent, return the entire test request to the sender. Never score from memory, never score from a URL, never accept an unreceipted generation as a test input.

---

### SOP 9.2 -- [SOP-DIU-501b] Patch Loop

**Vendor SOP.** Wraps TEST-PROTOCOL.md §4 (the patch loop).
**Library-version pin:** TEST-PROTOCOL.md v1.0 (§-refs verified 2026-06-12).
**When to run:** Immediately following any FAIL verdict from SOP 9.1.
**Frequency:** 1-3 patch iterations per failing card, then 3-strike escalation if unresolved.
**Inputs:** The failing test images, the per-dimension scores from SOP 9.1, the card at its current version, any prior patch attempt records.

**Steps:**
1. Diagnose: identify the lowest-scoring dimension(s). Articulate exactly which prompt language under-specified the failing dimension. Be precise.
2. Classify the failure root cause before issuing a patch brief:
   a. Card defect (prompt language genuinely insufficient) -> issue a patch brief to the Style Analyst per TEST-PROTOCOL §4 step 2
   b. Operator error (variables unfilled, wrong model, wrong tier, wrong aspect ratio, Identity Lock Block absent) -> return to the Generation Operator; do NOT enter the patch loop for operator errors
   c. Model drift (model has changed behavior) -> do NOT enter the patch loop; flag to CDO and trigger SOP 9.5 (Regression Sweep)
   d. Infrastructure failure (429, 5xx, 402) -> these are NOT style failures; return to the Operator; they NEVER count against the 3-strike limit
3. For confirmed card defects: issue a patch brief to the Style Analyst. The brief must include: the specific dimension(s) that failed, the exact failure mode per TEST-PROTOCOL §6 vocabulary, the recommended patch approach per TEST-PROTOCOL §4 step 2, and the avoid-list addition proposed.
4. When the Style Analyst returns the patched card: re-run only the failed test(s) per TEST-PROTOCOL §4 step 3 (not the full test set). Score and record the patch-attempt row.
5. Count consecutive failed patch attempts on the same dimension. On attempt 3 with no passing score: compile the 3-strike escalation packet and deliver to Chief Design Officer per SOP 9.3.
6. On a passing re-test: update card status to `tested`, update INDEX.md, notify Style Analyst and Chief Design Officer.

**Outputs:** Patch brief to Style Analyst (per failed attempt), Test Log rows (per re-test), 3-strike escalation packet (if limit reached), or PASS verdict.
**Hand to:** Style Analyst (patch briefs); Chief Design Officer (3-strike escalations and PASS verdicts); Generation Operator (operator error corrections).
**Failure mode:** If you cannot distinguish card defect from operator error from model drift, escalate the ambiguity to the Chief Design Officer with the test images, scores, and the specific question requiring producer judgment. Never modify a card based on ambiguous diagnosis.

---

### SOP 9.3 -- 3-Strike Escalation Protocol

**When to run:** Three consecutive failed patch attempts on the same card dimension, or when aggregate test generation spend has reached the per-deliverable budget breaker threshold.
**Frequency:** Rare (<=2 per week on a healthy library).
**Inputs:** All test images from all attempts (locally stored), per-attempt scores from the Test Log, all patch briefs issued, total generation spend on this card to date, the card at its current version.

**Steps:**
1. Verify you have met the escalation threshold: 3 failed patch attempts on the same dimension, OR aggregate test spend has reached the budget-breaker level. Do not escalate early and do not continue past 3 strikes without escalating.
2. Compile the evidence packet: card ID, version, category, status; test images (all attempts, labeled); per-attempt scores for all 12 dimensions (table format); patch briefs issued and changes applied; your diagnosis of the root failure; total generation spend; your recommendation.
3. Deliver the evidence packet to the Chief Design Officer via the department communication channel with subject line: "[DIU 3-STRIKE] Card [ID] -- Dimension [Name] -- [Attempt Count] attempts -- [$spend] consumed."
4. Halt all further test generation on this card. Do NOT continue patching without Chief Design Officer direction.
5. Update the Test Log with an escalation row. Update card status to `escalated` in the Test Log (note: INDEX.md status remains `draft` until the producer resolves the escalation).

**Outputs:** Evidence packet to Chief Design Officer, Test Log escalation row, generation halt.
**Hand to:** Chief Design Officer (for resolution and direction to Style Analyst).
**Failure mode:** If the Chief Design Officer does not respond within 24 hours on a client-deadline-critical card, escalate to the Master Orchestrator. Never restart test generation on an escalated card without explicit written direction from the Chief Design Officer.

---

### SOP 9.4 -- Production Promotion & Golden-Seed Banking

**When to run:** A `tested` card has passed SOP 9.1 and the Chief Design Officer has confirmed it is ready for production status.
**Frequency:** 1-5 times per week as cards graduate from the test cycle.
**Inputs:** The passing Test Log row (from SOP 9.1), the card at the current tested version, MODEL-SPECS.md (to determine seed support for the recommended model).

**Steps:**
1. Confirm the PASS verdict is on record in the Test Log with complete information: date, model, tier, all 12 dimension scores, average, seed (if the model supports it), and a note confirming zero hard-rule violations.
2. Bank the regression golden for seed-capable models (Ideogram V3, Wan 2.7, or any model with seed support per MODEL-SPECS.md): record the passing seed, exact full prompt (all variables filled as used in the passing test), model ID, tier, and the TEST-PROTOCOL §7 note in the golden-seed registry. If the model does not support seeds, store the full assembled prompt + model + tier + test scores as the baseline.
3. Update the card status to `production` in the card file and in INDEX.md. Tag the Changelog entry with the promotion date and the first passing test row reference.
4. Notify the Style Analyst (card is in the library at production status), the Generation Operator (card is available for Workflow B generation requests), and the Chief Design Officer.
5. Trigger SOP-DIU-606 (via the Style Analyst): the card's one-line summary, mood keywords, and palette descriptors must be embedded in the semantic retrieval index. Confirm the embedding was completed before closing the task.

**Outputs:** Updated card status to `production`, INDEX.md status updated, golden-seed entry banked, embedding trigger confirmed.
**Hand to:** Style Analyst (index embedding trigger), Generation Operator (card available for generation), Chief Design Officer (production confirmation).
**Failure mode:** If the golden seed is not recorded at promotion time and the session has already closed, record the test scores, full prompt, and model/tier as the baseline and note that the exact seed was not captured. Never skip the golden-seed step on seed-capable models.

---

### SOP 9.5 -- [SOP-DIU-605] Regression Goldens, Model-Drift Sentinel & Last-Known-Good Rollback

**ZHC SOP.** Wraps TEST-PROTOCOL.md §§3, 5, 7; MODEL-SPECS.md §6; MASTER-SOP.md §8; INDEX.md retire rule.
**Library-version pin:** TEST-PROTOCOL.md v1.0; MODEL-SPECS.md v1.0 (check §6 date on every run; §-refs verified 2026-06-12).
**When to run:** Quarterly (all production cards); after any MODEL-SPECS.md version bump (§6 step 6b); after any cluster of off-style incidents on one model (3+ separate incidents on the same model in a 2-week window); after any provider-side model-update notice.
**Frequency:** Quarterly full sweep; triggered ad hoc on model-change events.
**Inputs:** Golden-seed registry (all production card baseline records), MODEL-SPECS.md current version, cost budget for regression sweep (approved by Chief Design Officer before sweep begins).

**Steps:**
1. Before starting a regression sweep, confirm cost budget approval with Chief Design Officer. A full regression sweep on 10+ production cards at 3 test generations each is real spend; get explicit approval with a dollar estimate before firing.
2. For seed-capable models: re-run the banked golden seed+prompt pair for each production card on the affected model. Score on all 12 dimensions per SOP 9.1. Compare against the banked baseline scores.
3. For non-seed models: re-run the banked full prompt at the same model/tier. Score and compare against baseline.
4. Classify each card result:
   a. Scores within 0.5 of baseline on all dimensions -> PASS, no action; log in the regression sweep record
   b. One or more dimensions dropped by > 0.5 from baseline but card still passes the 4.0/no-dim-below-3 criteria -> WATCH; log drift, flag to CDO, do not re-route yet
   c. Card now fails pass criteria on two consecutive regression test runs -> DEGRADED; proceed to step 5
5. For DEGRADED cards: mark the model as `degraded` in generation receipts for this card. Re-route: update the card's routing note to use the MODEL-SPECS backup column endpoint until the degradation is cleared or patched.
6. For rollback (card was patched after production promotion and the patched version now fails regression): revert the card to the last version whose Test Log shows a passing score. Update the card file to the last-known-good version, update the card's status in INDEX.md, and record a Changelog entry: "ROLLBACK: reverted to v[X.Y] -- failure notes from v[X.Z] preserved per MASTER-SOP §8." Never delete failure notes.
7. Deliver the regression sweep report to the Chief Design Officer: cards swept, pass/watch/degraded counts, rollbacks executed, models flagged as degraded, re-routing actions taken, total sweep cost.

**Outputs:** Regression sweep report to Chief Design Officer, degraded-model flags in receipts, routing updates for degraded cards, rollbacks executed (with Changelog entries).
**Hand to:** Chief Design Officer (sweep report and degradation flags); Style Analyst (rollback notification and preserved failure notes); Generation Operator (updated routing notes for degraded cards).
**Failure mode:** If a regression sweep exhausts the approved budget before all production cards are swept, halt and report to Chief Design Officer. Never continue a sweep past the approved spend. Prioritize the most-used cards (highest generation volume in the past 30 days) and cards associated with active client deliveries.

---

*SOPs owned: [SOP-DIU-501a], [SOP-DIU-501b], [SOP-DIU-605]. sop_count: 5 (including SOP 9.3 and SOP 9.4 as operational non-vendor numbered SOPs).*
