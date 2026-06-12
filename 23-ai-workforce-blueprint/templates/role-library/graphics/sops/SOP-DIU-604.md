# SOP-DIU-604 — Hard-Rule Quarantine & Incident Response

**ID:** SOP-DIU-604
**Classification:** ZHC SOP — thin wrapper
**Owner Role:** Generation Operator (primary); Photo Shoot Director (input on identity incidents)
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** PHOTO-SHOOT-SOP v1.0, NEGATIVE-PROMPTING-SOP v1.0, TEST-PROTOCOL v1.0 (§-refs verified 2026-06-12)

---

## Role Mission

The Generation Operator detects hard-rule violations in generated outputs, moves the offending asset out of all delivery and sourcing paths immediately, writes an incident receipt, and notifies the CDO. Quarantine is non-negotiable and has no override path. The Photo Shoot Director reviews every identity-related incident for consent-scope implications. Quarantined assets never reach a client, never seed a future generation, and never leave the quarantine directory without CDO written authorization.

This SOP closes the worst cascading failure mode in the DIU: an undetected hard-fail output left in a delivery or media-library folder is later picked up by PHOTO-SHOOT-SOP §2's identity-sourcing hierarchy, poisoning every subsequent shoot for that client.

---

## Governing Library Files (source-of-truth — do NOT duplicate content)

| File | Sections used | What it governs |
|---|---|---|
| `_system/PHOTO-SHOOT-SOP.md` | §1 (Identity Lock principles), §2 (sourcing hierarchy — the poisoning vector this SOP protects), §4 (Identity Lock Block verbatim rule), §10 (hard-fail classification) | Hard-rule definitions, identity-drift criteria, consent-gap detection, the media-folder sourcing paths this SOP must keep clean |
| `_system/NEGATIVE-PROMPTING-SOP.md` | §5 (avoid-list growth protocol) | How detected violations feed the avoid-list so the same failure cannot recur |
| `_system/TEST-PROTOCOL.md` | §3 (hard-rule fail classification in the Test Log) | How the Fidelity Tester classifies hard-rule fails; the incident evidence packet format |

All violation definitions, identity-drift criteria, and avoid-list growth procedures are read from the library files above at runtime. Do not reproduce or paraphrase those definitions in this SOP.

---

## Procedure (ordered)

### A. Quarantine (triggered immediately on detection)

1. **Identify the violation.** Confirm the output matches at least one hard-rule trigger listed in the section below. Do not proceed on suspicion alone — if uncertain, pause and escalate to the CDO with the asset for decision.

2. **Move the asset immediately.** Transfer the output file to `_local/quarantine/{incident-id}/`. The `incident-id` is a UUID generated at detection time. Do not copy — move. The asset must not remain in `_local/results/`, any delivery folder, any media-library folder, or any path reachable by PHOTO-SHOOT-SOP §2's sourcing hierarchy.

3. **Write the incident receipt.** Create `_local/quarantine/{incident-id}/incident.json` with the following fields:
   - `incident_id`: UUID
   - `asset_path`: absolute path in quarantine
   - `task_id`: Kie.ai taskId from the generation receipt
   - `card_id` + `card_version`: from the generation receipt
   - `model`: model ID (MODEL-SPECS §1 slug)
   - `tier`: SHORT / MEDIUM / LONG
   - `filled_prompt`: exact positive prompt submitted (not a summary)
   - `seed`: value or `"no-seed-endpoint"`
   - `violation_type`: one of the hard-rule trigger labels below
   - `detection_method`: `postflight-visual-inspection` | `fidelity-tester-diagnosis` | `cdo-review` | `post-delivery-discovery`
   - `detected_at`: ISO 8601 timestamp
   - `detected_by`: role slug

4. **Flip the generating receipt state.** Update the original receipt in `_local/receipts/` to `state: quarantined`.

5. **Notify CDO.** Send the incident receipt path and a one-line violation summary immediately. CDO notification is never deferred.

6. **Notify Photo Shoot Director (identity incidents only).** If the violation is lightened skin tone, identity drift, or a consent gap, also notify the Photo Shoot Director for consent-scope review per PHOTO-SHOOT-SOP §§1–2.

7. **Feed avoid-list growth.** Pass the violation type and filled prompt to the Fidelity Tester's avoid-list growth protocol per NEGATIVE-PROMPTING-SOP §5. The same failure must not recur in the next generation.

### B. Post-Delivery Discovery (output was delivered before detection)

1. Notify CDO immediately upon discovery. Do not contact the client — CDO leads all client communication.
2. Move the delivered asset into quarantine per steps A.2–A.4. Record `detection_method: post-delivery-discovery`.
3. Regenerate a compliant replacement via normal Workflow B (SOP-DIU-301). Do not re-use any element of the quarantined job without CDO written direction.
4. Log a `delivered-hard-fail` flag on the generation receipt and in the card's Test Log.
5. The Fidelity Tester reviews the card's avoid-list and Test Log for systemic causes before the card is used again.

---

## Hard-Rule Triggers

Any of the following requires immediate quarantine with no override path:

- Lightened or altered skin tone vs the identity reference
- Text rendered on a subject's face
- Identity drift — the generated person does not match the identity reference
- Consent gap discovered mid-job (a non-consented person appears in the output)
- Any output the Fidelity Tester has classified as a hard-rule fail in the Test Log (TEST-PROTOCOL §3)

If an output triggers a hard rule, quarantine precedes everything else — including completion of the delivery, CDO approval, or any other step in the normal workflow.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Generated output asset flagged during postflight visual inspection | Yes | SOP-DIU-601 postflight (step 6 visual check) |
| OR: Fidelity Tester hard-rule-fail diagnosis | Yes | SOP-DIU-501a / SOP-DIU-501b |
| Generation receipt for the asset | Yes | `_local/receipts/` — written at submit time (SOP-DIU-602) |
| Card ID + version, model, tier, filled prompt | Yes | Generation receipt fields |
| Consent record (identity incidents) | Conditional | `_local/consent/{client-id}.json` — read by Photo Shoot Director |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| Quarantined asset | `_local/quarantine/{incident-id}/` | Moved from results; isolated |
| Incident receipt | `_local/quarantine/{incident-id}/incident.json` | Written |
| Generating receipt (state updated) | `_local/receipts/{receipt-id}.json` | `state: quarantined` |
| CDO notification | Via OpenClaw `message send` | Sent |
| Photo Shoot Director notification (identity incidents) | Via OpenClaw `message send` | Sent (if applicable) |
| Avoid-list growth trigger | Fidelity Tester (NEGATIVE-PROMPTING-SOP §5) | Dispatched |

---

## Handoff Conditions

- **Normal quarantine:** CDO receives the incident receipt and decides next steps (regenerate, investigate, close). Generation Operator awaits CDO direction before submitting a replacement.
- **Identity incident:** Photo Shoot Director receives the incident receipt and reviews the consent record. No further generation using that identity reference until Photo Shoot Director clears the consent scope.
- **Post-delivery discovery:** CDO leads client communication and replacement delivery. Fidelity Tester reviews the card's Test Log before re-use.
- **Avoid-list growth:** Fidelity Tester closes the loop — the card must pass a re-test with the updated avoid-list before the next production generation.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| Output cannot be moved to quarantine (filesystem permission error) | Halt all further generation immediately. Escalate to CDO. Do not proceed with any additional generations while a hard-rule violation is unresolved. |
| Uncertain whether output meets a hard-rule trigger | Pause. Send the asset and the candidate trigger label to CDO for decision. Do not guess. |
| Identity drift on a self-likeness job with a standing consent release | Quarantine as normal. Consent status does not change the quarantine requirement — the output is a style/identity failure regardless. |
| CDO is unreachable and a hard-rule violation is undetected | Halt delivery of the entire deliverable. Write a blocking incident receipt. Resume only on CDO acknowledgment. |
| Quarantine directory contains unescalated incidents older than 48 hours | SOP-DIU-615 (Healer-Graphics integrity sweep) flags this. Escalate to CDO immediately on Healer alert. |
| Delivered-hard-fail incident on a card used across multiple clients | Escalate to CDO + all affected Photo Shoot Directors. Review fleet-wide before the card is restored to production. |

---

## What Quarantined Assets May Never Do

- Be delivered to any client
- Be used as a reference image in any future generation
- Be embedded in the style library, INDEX.md, or any card
- Be moved back to a results or delivery folder without CDO written authorization
- Be re-submitted to Kie.ai as an input reference in any capacity

---

*Library-version pin: PHOTO-SHOOT-SOP v1.0, NEGATIVE-PROMPTING-SOP v1.0, TEST-PROTOCOL v1.0 (§-refs verified 2026-06-12).*
