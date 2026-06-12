# SOP-DIU-302 — Model Routing & API Execution

**ID:** SOP-DIU-302
**Classification:** Vendor SOP — thin wrapper
**Owner Role:** Generation Operator
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** MODEL-SPECS v1.2 (§§2, 5 verified 2026-06-12)

---

## Role Mission

The Generation Operator resolves which Kie.ai endpoint receives each job, executes the correct JSON template with no structural edits, and records the `taskId` in a receipt before exiting. Routing is deterministic — the MODEL-SPECS routing table is the authority. The Operator never improvises endpoint choices, never silently downgrades resolution, and never substitutes an out-of-spec model.

---

## Governing Library Files (source-of-truth — do NOT duplicate content)

| File | Sections used | What it governs |
|---|---|---|
| `_system/MODEL-SPECS.md` | §1 (roster + aspect-ratio table), §2 (routing table + Editing Hierarchy), §3 (tier compatibility), §4 (endpoint prompting notes), §5 (JSON templates), §6 (model-update protocol) | All routing decisions, endpoint capabilities, API templates, future-model additions |
| `_system/MASTER-SOP.md` | §3.2 (assembly packet), §5 (submit + exit rule) | Assembly packet requirements handed to the Operator; submit-and-exit discipline |

Routing decisions are made by reading MODEL-SPECS §2 **at runtime**. Do not cache routing logic in any other file — MODEL-SPECS changes, this SOP does not.

---

## Procedure (ordered)

1. **Read the assembly packet.** Confirm it contains: style card ID + version, all filled `{VARIABLE}` tokens, model preference or `auto-route` flag, aspect ratio, resolution, tier, and budget cap. If any field is missing, return to the requestor — do not proceed.

2. **Resolve the endpoint.** Open MODEL-SPECS §2 routing table. Match the task category (text-heavy design, typography, ultra-wide banner, surgical edit, portrait, draft/variant, etc.) to the FIRST CHOICE column. Use the BACKUP column only if the primary is flagged `degraded` in current receipts or confirmed down.

3. **Verify aspect ratio compatibility.** Cross-reference the requested aspect ratio against MODEL-SPECS §1 aspect-ratio table for the resolved endpoint. If the ratio is unsupported on the primary, check the backup endpoint. If neither supports it, return to the requestor with the list of supported ratios for each endpoint — do not silently alter the ratio.

4. **Apply the LONG-to-MEDIUM fallback rule (MODEL-SPECS §3).** If the primary endpoint's LONG tier is unavailable, fall back to MEDIUM on the same endpoint with explicit CDO notification. If MEDIUM is also unavailable, route to the backup endpoint with CDO notification. Never silently downgrade resolution.

5. **Select the JSON template.** Open MODEL-SPECS §5 for the resolved endpoint (§5.1–5.7). Copy the template exactly. Fill only the designated variable slots. Do not alter template structure, add fields, or remove fields.

6. **Verify the API key.** Check all env stores per the client-box-env-stores protocol before submitting. A missing or unreachable key is a hard stop — do not guess at key locations or proceed without confirmation.

7. **Run SOP-DIU-601 preflight.** Do not submit until SOP-DIU-601 (Preflight & Postflight Mechanical Gates) returns a clean pass. Any preflight failure halts submission and returns an itemized failure list to the requestor.

8. **Submit via `createTask`.** POST to `https://api.kie.ai/api/v1/jobs/createTask` with `Authorization: Bearer {API_KEY}` and the completed JSON template body. Extract `data.taskId` from the response immediately.

9. **Write the receipt file.** Record the following in `_local/receipts/{receipt-id}.json` at submit time: endpoint, model ID (from MODEL-SPECS §1), tier, resolution, `taskId`, cost class, `state: submitted`, `submitted_at` (ISO 8601). Do not exit without writing the receipt.

10. **Exit.** The cron poller handles completion detection via `GET /api/v1/jobs/recordInfo?taskId={taskId}`. Do not hold the session open polling for results.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Assembly packet with filled prompt | Yes | Requestor (CDO / producing role) |
| Model preference or `auto-route` flag | Yes | Assembly packet |
| Aspect ratio + resolution | Yes | Assembly packet |
| Tier (SHORT / MEDIUM / LONG) | Yes | Assembly packet |
| Budget cap | Yes | Assembly packet or client `budget_config` block |
| Identity Lock Block (if `likeness: true`) | Conditional | Photo Shoot Director via SOP-DIU-608 |
| SOP-DIU-601 preflight pass verdict | Yes | SOP-DIU-601 execution immediately prior |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| Receipt file | `_local/receipts/{receipt-id}.json` | `state: submitted` |
| Submitted task | Kie.ai API | Processing |
| Compiled negatives artifact (if multi-asset) | `_local/jobs/{job-id}/compiled-negatives.json` | Written by SOP-DIU-303 before this SOP runs |

---

## Handoff Conditions

- **Normal completion:** Receipt written with `taskId`; Operator exits; cron poller takes over via `getTaskInfo`. When the poller detects `state: success`, SOP-DIU-601 postflight runs and flips the receipt to `complete`; CDO and requestor are notified.
- **Off-style result after postflight:** Hand to Fidelity Tester (SOP-DIU-501a / SOP-DIU-501b).
- **Hard-rule violation detected in postflight visual inspection:** Hand to SOP-DIU-604 (Hard-Rule Quarantine & Incident Response) immediately.
- **Fallback or degradation event:** Hand to SOP-DIU-603 (Fallback Ladder & Graceful Degradation) for ladder execution and CDO notification.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| API key missing from all env stores | Hard stop. Escalate to CDO with list of all stores checked. |
| Both primary and backup endpoints unavailable | Hard stop. Preserve all manifests and receipts. Escalate to CDO. Do not attempt a third-endpoint substitution without explicit CDO direction. |
| `createTask` returns a non-2xx error | Log error code and response body. Apply SOP-DIU-603 fallback ladder. Escalate if fallback ladder exhausted. |
| Requested aspect ratio unsupported on all viable endpoints | Return to requestor with supported-ratio list. Do not generate at wrong ratio. |
| Resolution silently downgraded by any path | This is a violation, not a fallback. Escalate to CDO immediately. |
| SOP-DIU-601 preflight fails | Do not submit. Return itemized failure list to the requestor. |
| Budget cap missing or `budget_config` block absent | Halt all generation. Ask CDO to provide config. Never generate without a defined budget cap. |
| Model-swap mid-deck attempted for any reason | Hard stop. A Slide Manifest is a cohesion contract. Escalate to CDO. |

---

*Library-version pin: MODEL-SPECS v1.2, MASTER-SOP v1.0 (§-refs verified 2026-06-12).*
