# SOP-DIU-501 — Fidelity Testing & Patch Loop

**ID:** SOP-DIU-501
**Type:** Vendor SOP (thin wrapper) — split into subsections 501a and 501b
**Owner Role:** Fidelity Tester ("The Critic")
**Namespace band:** 5xx (Vendor — reserved, DEPARTMENT-BUILD-BRIEF §3)
**Status:** Active
**Version:** 1.0
**Date:** 2026-06-12
**Library-version pin:** TEST-PROTOCOL v1.0 (§§1–4, 6–7 — verified 2026-06-12). If this file's version advances, re-verify all §-refs in this wrapper before executing.

---

## Role Mission (Fidelity Tester)

Nothing reaches production untested; failures become institutional memory. The Fidelity Tester's job is to score every draft card against the 12-dimension rubric, route PASS verdicts forward, and run an evidence-based patch loop on FAIL verdicts until the card earns its status. The Tester never creates cards, never generates API requests, and never delivers to clients. Every scoring decision is grounded in test images and receipts on disk — never memory, never URLs.

---

## Governing Library Files (Source of Truth — Do NOT Duplicate Content Here)

All scoring rubrics, pass criteria, patch procedures, diagnosis protocols, failure-mode vocabulary, and reproducibility rules live in these files. This SOP points; the library governs.

| File | Repo Path | Sections Governing This SOP |
|---|---|---|
| TEST-PROTOCOL | `45-design-intelligence-library/library/_system/TEST-PROTOCOL.md` | §1 (when to run), §2 (test design — near/far/text-stress), §3 (12-dimension scoring rubric + pass criteria), §4 (patch loop — diagnose, patch-with-redundancy, re-run, log), §5 (diagnosis mode for production cards), §6 (common failure modes + standard fixes), §7 (reproducibility + seed banking) |
| MASTER-SOP | `45-design-intelligence-library/library/_system/MASTER-SOP.md` | §8 (changelog rules — never delete failure notes; version bump on every card edit) |
| MODEL-SPECS | `45-design-intelligence-library/library/_system/MODEL-SPECS.md` | §1 (model roster — seed-support flags for golden-seed banking), §6 (model-update protocol — triggers regression sweep) |
| INDEX.md | `45-design-intelligence-library/library/INDEX.md` | Status field authority (draft → tested → production → escalated); retire-never-delete rule |

**Rule:** If this wrapper and a library file disagree, the library file wins. Raise a flag to the CDO — do not silently follow the wrapper.

---

## Inputs

**For SOP-DIU-501a (Fidelity Test Run):**
- Style card file at the submitted version (status must be `draft`, `tested`, or `production`)
- Generation receipts for every test image: card ID + version, model, tier, exact filled prompt, seed if applicable, taskId, cost class
- Three test generations (near-transfer, far-transfer, text-stress) — locally stored, post-flight verified files only
- Any flags from the Style Analyst's handoff note (dedupe score, provenance class, likeness flags)

**For SOP-DIU-501b (Patch Loop):**
- Failing test images from SOP-DIU-501a, locally stored with receipts
- Per-dimension scores from the SOP-DIU-501a test run
- Card file at current version
- All prior patch attempt records for this card (if any)

**Hard prerequisite:** Do not accept any test request without a receipt for every test image. Missing receipt = return the entire request to the sender before beginning.

---

## Procedure (Ordered Steps)

### SOP-DIU-501a — Fidelity Test Run (wraps TEST-PROTOCOL §§1–3)

**Step 1 — Confirm Prerequisites**
Verify: (a) a receipt exists for each test image with all required fields; (b) images are locally stored and post-flight verified — not URL links; (c) the model used matches the card's recommended model per MODEL-SPECS §1; (d) the card status is appropriate for the test mode (`draft` for first-run, `tested` or `production` for regression or diagnosis).

If any prerequisite fails, return the entire test request to the sender with an itemized list of what is missing. Do not begin scoring.

**Step 2 — Open and Verify the Card Version**
Open the card file at the exact submitted version. Confirm the version matches the receipt. If there is a version mismatch between the card file and the receipts, halt and return to the sender.

**Step 3 — Score All 12 Dimensions (TEST-PROTOCOL §3)**
Score each of the three test images on all 12 dimensions, 1–5 per dimension, using the rubric in TEST-PROTOCOL §3. Record each individual dimension score before computing any average. Do not round or estimate — compute the exact average across all 12 dimensions per image.

**Step 4 — Apply Pass Criteria (TEST-PROTOCOL §3)**
A card PASSES if and only if ALL three conditions are met:
- Average across all 12 dimensions >= 4.0
- No single dimension below 3
- Zero hard-rule violations (one violation = automatic fail regardless of all other scores)

A hard-rule violation — such as text on a face, lightened skin tone, identity drift, or a consent gap — is a non-negotiable fail. Score the remaining dimensions for the record but issue the FAIL verdict immediately.

**Step 5 — Record the Test Log Row**
Write a row in the card's Test Log before issuing any verdict. The row must contain: date, model, tier, test type (near-transfer / far-transfer / text-stress), test subject description, per-dimension scores, average, pass/fail verdict, and any notes. Do not issue a verdict without this row on disk.

**Step 6 — Issue the Verdict**
- **PASS:** Update the card status field to `tested` (first-run pass) or confirm `production` (regression pass). Update the INDEX.md status field to match. Notify the Style Analyst and Chief Design Officer with the card ID, version, average score, and the test log row reference.
- **FAIL:** Do NOT update the card status. Log the failure row (Step 5) first. Then enter SOP-DIU-501b (Patch Loop) immediately. Hard-rule violations go directly to SOP-DIU-604 (Hard-Rule Quarantine & Incident Response) — do not enter the patch loop for hard-rule failures.

---

### SOP-DIU-501b — Patch Loop (wraps TEST-PROTOCOL §4)

Run this SOP only after a FAIL verdict from SOP-DIU-501a on a confirmed card defect. Do not enter the patch loop for operator errors, model drift, or infrastructure failures — those are routed separately (see Escalation Triggers below).

**Step 1 — Diagnose Root Cause**
Identify the lowest-scoring dimension(s). Articulate exactly which prompt language under-specified the failing dimension. Use the failure-mode vocabulary from TEST-PROTOCOL §6. Classify the failure root cause before issuing any patch brief:

- **Card defect** (prompt language genuinely insufficient): proceed to Step 2
- **Operator error** (variables unfilled, wrong model, wrong tier, wrong aspect ratio, Identity Lock Block absent): return to the Generation Operator with an itemized list — do NOT enter the patch loop; operator errors never count against the 3-strike limit
- **Model drift** (model behavior has changed): do NOT enter the patch loop — flag to CDO and trigger SOP-DIU-605 (Regression Goldens, Model-Drift Sentinel & Last-Known-Good Rollback)
- **Infrastructure failure** (429 rate-limit, 5xx server error, 402 credit exhaustion): return to the Generation Operator via SOP-DIU-603 — these are NOT style failures and never count against the 3-strike limit

If you cannot distinguish between these failure classes, escalate the ambiguity to the Chief Design Officer with the test images, scores, and the specific diagnostic question. Never modify a card based on ambiguous diagnosis.

**Step 2 — Issue the Patch Brief**
For confirmed card defects: write a patch brief to the Style Analyst. The brief must include:
- The specific dimension(s) that failed (by dimension name)
- The exact failure mode per TEST-PROTOCOL §6 vocabulary
- The recommended patch approach per TEST-PROTOCOL §4 step 2 (strengthen adjective → repeat at end → add to avoid-list → add model note — apply in this order of force)
- The proposed avoid-list addition

**Step 3 — Re-Run the Failed Tests**
When the Style Analyst returns the patched card at the new version: re-run ONLY the failed test(s) per TEST-PROTOCOL §4 step 3. Do not re-run the full set. Score and record a new Test Log row for each re-test.

**Step 4 — Count Attempts and Apply the 3-Strike Rule**
Count consecutive failed patch attempts on the same dimension. On the third consecutive failure with no passing score: compile the 3-strike escalation packet and escalate to the Chief Design Officer per the escalation procedure below. Halt all further test generation on this card immediately.

**Step 5 — On a Passing Re-Test**
Update the card status to `tested`. Update INDEX.md status. Notify the Style Analyst and Chief Design Officer. If CDO has confirmed production readiness, proceed to golden-seed banking (TEST-PROTOCOL §7 + SOP 9.4 in the Fidelity Tester role file).

---

## Outputs

| Output | Format | Destination |
|---|---|---|
| Test Log row (per run) | In-card Test Log table | Disk — card file (do not skip this step) |
| PASS verdict + status update | Card file + INDEX.md | Style Analyst, CDO, Generation Operator (on production status) |
| Patch brief | Written itemized brief | Style Analyst |
| Avoid-list addition | NEGATIVE-PROMPTING-SOP §5 append | Style Analyst to execute |
| 3-strike escalation packet | Evidence packet | Chief Design Officer |
| Hard-rule failure | Hand to SOP-DIU-604 | CDO + Photo Shoot Director (if likeness involved) |

---

## Handoff Conditions

**Hand off to Style Analyst when:**
- PASS verdict issued — card is ready for production promotion and INDEX registration via SOP-DIU-606
- Patch brief issued for a confirmed card defect — Analyst returns patched card for re-test

**Hand off to Chief Design Officer when:**
- PASS verdict issued (notification copy)
- 3-strike limit reached (escalation packet, halt all generation on this card)
- Hard-rule violation on a production card requires producer judgment

**Hand off to Generation Operator when:**
- Operator error identified — return with itemized list; do not patch the card
- Infrastructure failure detected — route to SOP-DIU-603

**Hand off to SOP-DIU-604 when:**
- Hard-rule violation detected in any test image (quarantine path, not patch loop)

**Hand off to SOP-DIU-605 when:**
- Model drift classified as root cause

**Do not hand off** while any test log row is missing from disk. The log row must be written before the verdict leaves this role.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| Test images missing or receipts absent | Return entire test request to sender before scoring. Never score from memory or URL. |
| Card version in receipt mismatches card file version | Halt. Return to sender with mismatch details. |
| Hard-rule violation in any test image | Automatic FAIL. Hand to SOP-DIU-604 immediately. Do not enter patch loop. |
| Cannot classify failure as card defect vs. operator error vs. model drift | Escalate ambiguity to CDO with test images, scores, and the specific diagnostic question. |
| 3 consecutive failed patch attempts on the same dimension | Compile 3-strike escalation packet. Deliver to CDO with subject line: "[DIU 3-STRIKE] Card [ID] — Dimension [Name] — [N] attempts — [$spend] consumed." Halt all generation on this card. |
| Aggregate test generation spend reaches per-deliverable budget-breaker threshold | Halt. Compile spend report. Escalate to CDO — this is a budget escalation, not a style escalation. |
| CDO does not respond within 24 hours on a client-deadline-critical escalated card | Escalate to Master Orchestrator. Never restart generation on an escalated card without written CDO direction. |
| MODEL-SPECS §6 version bump detected | Flag to CDO. Trigger SOP-DIU-605 (Regression Sweep) for all production cards on the updated model before running new tests on that model. |

---

## Library-Version Pin

```
TEST-PROTOCOL v1.0 (§§1,2,3,4,5,6,7 — verified 2026-06-12)
MASTER-SOP v1.0 (§8 changelog/failure-note rules — verified 2026-06-12)
MODEL-SPECS v1.0 (§1 seed-support flags, §6 model-update protocol — verified 2026-06-12)
INDEX.md v1.0 (status lifecycle authority — verified 2026-06-12)
```

If any pinned file version advances, the Healer-Graphics SOP-DIU-615 sweep will flag the stale pin. The Fidelity Tester must re-verify all §-refs against the new version before executing this SOP again. Do not execute against an unverified version bump.

---

*SOP-DIU-501 is a vendor SOP covering the full fidelity test and patch cycle (501a = test run, 501b = patch loop). The library files listed above are the single source of truth. This wrapper provides role context, intake/output contracts, and escalation triggers only. Do not duplicate library content here.*
