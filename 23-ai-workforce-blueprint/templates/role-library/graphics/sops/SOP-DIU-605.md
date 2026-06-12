# SOP-DIU-605 — Regression Goldens, Model-Drift Sentinel & Last-Known-Good Rollback

**ID:** SOP-DIU-605
**Classification:** ZHC SOP — thin wrapper
**Owner Role:** Fidelity Tester ("The Critic")
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** TEST-PROTOCOL v1.0, MODEL-SPECS v1.0, MASTER-SOP v1.0 (§-refs verified 2026-06-12)

---

## Role Mission

The Fidelity Tester banks a regression golden at every production promotion, sweeps all production cards when model behavior may have changed, and executes last-known-good rollbacks when a card fails regression after patching. This SOP is the primary defense against silent model drift — the risk that a provider silently updates a model behind a Kie.ai endpoint, degrading every production card on it at once while the system continues generating off-style output without error.

The Fidelity Tester owns this SOP end-to-end. The Generation Operator acts on re-routing instructions issued here. The Style Analyst receives rollback notifications and preserves failure notes in the card Changelog. The Chief Design Officer approves sweep budgets and receives the sweep report; re-routing and rollback decisions are the Tester's, not a producer judgment call.

---

## Governing Library Files (source-of-truth — do NOT duplicate content)

| File | Sections used | What it governs |
|---|---|---|
| `_system/TEST-PROTOCOL.md` | §3 (12-dimension scoring rubric + pass criteria), §5 (patch loop and degradation classification), §7 (golden-seed banking requirements) | Scoring rubric, pass thresholds, baseline comparison rules, how goldens are stored and referenced |
| `_system/MODEL-SPECS.md` | §6 (model versioning and deprecation calendar; the §6 bump event that triggers ad-hoc sweeps) | Seed support per endpoint, backup-column routing, the version-bump event that mandates an immediate sweep |
| `_system/MASTER-SOP.md` | §8 (card versioning and rollback discipline; Changelog entry format) | How card versions are numbered, how rollbacks are recorded, that failure notes are never deleted |
| `_system/library/INDEX.md` | retire rule (status sync on rollback) | INDEX.md status must be updated in the same change as any card-status change, including rollbacks |

All scoring rubrics, pass/fail thresholds, seed-support tables, and rollback versioning rules are read from the library files above at runtime. Do not reproduce dimension definitions, char caps, or model-slug lists in this SOP.

---

## Procedure (ordered)

### A. Golden Banking (run at every production promotion — part of SOP 9.4)

1. **Confirm promotion prerequisites.** The card must have a complete PASS row in its Test Log: date, model, tier, all 12 dimension scores, average >= 4.0, no dimension below 3, zero hard-rule violations, and a seed value if the model supports it.

2. **Bank the golden for seed-capable models.** For Ideogram V3, Wan 2.7, or any model whose MODEL-SPECS §6 entry shows seed support: write a golden-seed registry entry at `_local/regression-goldens/{card-id}.json` with the following fields:
   - `card_id` + `card_version`
   - `model` (MODEL-SPECS §1 slug)
   - `tier`
   - `seed` (exact integer)
   - `full_prompt` (exact assembled prompt, all variables filled as used in the passing test)
   - `baseline_scores` (object: all 12 dimension scores from the passing Test Log row)
   - `baseline_average`
   - `banked_at` (ISO 8601 timestamp)
   - `test_log_row_ref` (date + run ID from the Test Log)

3. **Bank the baseline for no-seed endpoints.** For endpoints that do not support seeds (GPT-Image-2, Seedream-3, or any MODEL-SPECS entry without seed support): write the same registry file with `seed: null` and record the full assembled prompt + model + tier + baseline scores. Re-runs on no-seed endpoints use the same prompt/model/tier and compare score distributions rather than exact output reproducibility.

4. **Confirm golden file written before closing promotion.** The golden-seed registry file must exist on disk before the card status is set to `production`. A promotion that completes without banking a golden is an incomplete promotion — SOP-DIU-615 (Healer) will flag the gap.

### B. Regression Sweep (triggered on qualifying events — see Inputs)

1. **Confirm budget approval.** Before firing any regression run, obtain explicit written approval from the Chief Design Officer with a dollar estimate. A full sweep on 10+ production cards at 3 test generations each is real spend. Never begin a sweep without approved budget headroom.

2. **Load the golden-seed registry.** Read all `_local/regression-goldens/*.json` files for production cards on the model(s) under review. Confirm each file is present and complete. Any production card missing a golden-seed entry is a Healer-615 flag — do not skip it silently; log the gap and alert CDO.

3. **Re-run seed-capable goldens.** For each seed-capable card on the affected model: submit the banked seed + full prompt at the banked model/tier. Score all 12 dimensions per TEST-PROTOCOL §3. Do not start scoring until the result is locally downloaded and postflight-verified (per SOP-DIU-601).

4. **Re-run no-seed baselines.** For each no-seed card: submit the banked full prompt at the banked model/tier. Score and compare against baseline score distributions. Because exact reproduction is not possible, classify only if a dimension drops more than 0.5 from the baseline average recorded at promotion.

5. **Classify each card result.** Apply exactly three classifications:
   - **PASS:** All dimension scores within 0.5 of the banked baseline on every dimension. Log in the regression sweep record. No action required.
   - **WATCH:** One or more dimensions dropped by more than 0.5 from baseline, but the card still meets pass criteria (average >= 4.0, no dimension below 3). Log drift note and alert CDO. Do not re-route yet. Schedule a re-check at the next quarterly sweep unless the CDO escalates.
   - **DEGRADED:** Card fails pass criteria (average < 4.0 OR any dimension below 3) on two consecutive regression test runs on the same model. Proceed immediately to step 6.

6. **Flag DEGRADED models and re-route.** For each card classified DEGRADED:
   - Mark the model as `degraded` in the card's generation receipts going forward.
   - Update the card's routing note (in the card file or in a `_local/routing-overrides/{card-id}.json`) to use the MODEL-SPECS §6 backup column endpoint until degradation is cleared.
   - Notify the Generation Operator of the updated routing immediately — no further production generations on the degraded model for this card until cleared.
   - Alert CDO with the DEGRADED classification, the two consecutive failing test rows, and the re-routing action taken.

7. **Deliver the sweep report.** Send to CDO: cards swept, per-card classification (PASS / WATCH / DEGRADED), rollbacks executed, models flagged as degraded, re-routing actions taken, total sweep cost vs approved budget. One report per sweep event.

### C. Last-Known-Good Rollback (triggered when a patched production card fails regression)

1. **Identify the last passing version.** Read the card's Test Log. Find the most recent version with a PASS row meeting full pass criteria (average >= 4.0, no dimension below 3, zero hard-rule violations). This is the last-known-good (LKG) version.

2. **Revert the card file.** Restore the card file to the LKG version content. Do not overwrite the Changelog section — append a rollback entry per MASTER-SOP §8: `"ROLLBACK: reverted to v[X.Y] — failure notes from v[X.Z] preserved."` Failure notes from the failing version are never deleted.

3. **Sync INDEX.md status.** Update the card's status row in INDEX.md in the same change as the card-file revert. A card status change that does not also update INDEX.md is incomplete. If INDEX.md and the card file disagree after this step, SOP-DIU-615 will flag it on the next sweep.

4. **Notify all downstream roles.** Send to Style Analyst (LKG version restored, failure notes preserved), Generation Operator (card is back at LKG version — any in-flight receipts using the failed version are invalid), and CDO (rollback summary: card ID, reverted from version, reverted to version, reason).

5. **Log the rollback in the regression sweep record.** Record the rollback as a ROLLBACK row in the sweep record with card ID, from-version, to-version, LKG Test Log row reference, and ISO 8601 timestamp.

6. **Schedule a post-rollback regression check.** Add the rolled-back card to the next quarterly sweep priority list. A card that has rolled back once is higher risk; it must be validated on the next sweep before being considered stable.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Golden-seed registry files for production cards | Yes | `_local/regression-goldens/{card-id}.json` — banked at promotion time (this SOP, Procedure A) |
| MODEL-SPECS.md current version | Yes | `_system/MODEL-SPECS.md` §6 — read at start of every sweep |
| MODEL-SPECS §6 bump event notice, quarterly calendar trigger, or off-style incident cluster report | Yes (one must be present to trigger a sweep) | CDO dispatch or Healer-615 alert |
| CDO budget approval with dollar estimate | Yes | Written CDO confirmation before any sweep generation fires |
| Passing Test Log row for the card being promoted (golden banking) | Yes | Card file Test Log — from SOP 9.1 (SOP-DIU-501a) |
| Postflight-verified regression test result images (locally stored) | Yes | Downloaded per SOP-DIU-601 — never score from a URL or unverified file |
| Card file at the current and LKG versions (rollback) | Yes | Card file Changelog + version history |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| Golden-seed registry entry | `_local/regression-goldens/{card-id}.json` | Written at production promotion |
| Regression sweep record | `_local/regression-sweeps/{sweep-id}.json` | Written; delivered to CDO as sweep report |
| Degraded-model flag in routing | Card routing note or `_local/routing-overrides/{card-id}.json` | Updated; Generation Operator notified |
| Rolled-back card file | Card file in the style library | Reverted to LKG version; ROLLBACK Changelog entry appended |
| INDEX.md status sync | `_system/library/INDEX.md` | Updated in the same change as any card-status or rollback change |
| CDO sweep report | Via OpenClaw `message send` | Sent after every sweep completion |
| Generation Operator routing update | Via OpenClaw `message send` | Sent immediately on DEGRADED classification |

---

## Handoff Conditions

- **Golden banking complete:** Card is at `production` status with a golden-seed registry entry confirmed on disk. Style Analyst receives the production-promotion notification. Generation Operator receives the card-available-for-generation notification.
- **Regression sweep PASS (all cards):** CDO receives the sweep report. No routing changes. No role action required.
- **Regression sweep WATCH:** CDO receives the drift alert. No re-routing. Re-check scheduled for next quarterly sweep unless CDO escalates.
- **Regression sweep DEGRADED:** Generation Operator receives updated routing notes immediately. CDO receives degradation report. No further production generations on the degraded model for affected cards until CDO clears the degradation or a model update resolves it.
- **Rollback executed:** Style Analyst receives the LKG restoration notice and failure-notes preservation confirmation. Generation Operator receives the version-revert notice with instruction to treat any in-flight receipts from the failed version as invalid. CDO receives the rollback summary.
- **Sweep budget exhausted before all cards swept:** Halt immediately. Report to CDO with cards completed, cards remaining, spend used. Never continue past the approved budget. Prioritize by generation volume and active client delivery exposure before starting any sweep.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| Production card missing a golden-seed registry entry | Flag to CDO. Do not skip or generate a synthetic golden from memory. SOP-DIU-615 independently tracks this — do not wait for the Healer sweep to surface it. |
| Regression sweep budget not approved before sweep fires | Hard stop. No regression test generations without a CDO-approved budget with a dollar estimate. |
| MODEL-SPECS §6 bump received with no CDO sweep approval within 24 hours | Alert CDO. Do not initiate the sweep. Do not re-route any card. Wait for written authorization. |
| Sweep exhausts approved budget before all production cards are swept | Halt immediately. Report remaining cards to CDO with prioritization recommendation. Never exceed approved spend. |
| Two consecutive DEGRADED results on a model affecting more than one client's production cards | Escalate to CDO as a fleet-level degradation event. Propose a re-route for all affected cards simultaneously rather than card-by-card. |
| LKG version cannot be identified (no passing Test Log row exists) | Hard stop. Escalate to CDO. Do not attempt a rollback without a verified LKG. The card may need to be retired from production pending re-analysis. |
| INDEX.md status and card file status disagree after a rollback | Treat as an incomplete rollback. Correct the discrepancy immediately. Alert CDO and Healer-Graphics. |
| Off-style incident cluster (3+ separate incidents on the same model in a 2-week window) | Treat as a DEGRADED-candidate trigger. Request CDO budget approval for an immediate targeted sweep on the flagged model rather than waiting for the quarterly cycle. |

---

*Library-version pin: TEST-PROTOCOL v1.0, MODEL-SPECS v1.0, MASTER-SOP v1.0 (§-refs verified 2026-06-12).*
