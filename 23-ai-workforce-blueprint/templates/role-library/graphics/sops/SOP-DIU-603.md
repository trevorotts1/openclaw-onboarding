# SOP-DIU-603 — Fallback Ladder & Graceful Degradation

**ID:** SOP-DIU-603
**Classification:** ZHC SOP — thin wrapper
**Owner Role:** Generation Operator
**Section 9 slot:** 9.6
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** MODEL-SPECS v1.0, PPT-ANALYSIS-SOP v1.0, TEST-PROTOCOL v1.0 (§-refs verified 2026-06-12)

---

## Role Mission

The Generation Operator executes a deterministic fallback ladder whenever an API error, rate-limit event, or endpoint-unavailability occurs during a generation session. Responses are ordered, logged, and bounded — the Operator never improvises a recovery path, never swaps models mid-deck, and never silently downgrades resolution. Infrastructure failures are explicitly quarantined from style failures: 429 / 5xx / 402 events never pollute the Fidelity Tester's patch loop.

---

## Governing Library Files (source-of-truth — do NOT duplicate content)

| File | Sections used | What it governs |
|---|---|---|
| `_system/MODEL-SPECS.md` | §2 (routing table — PRIMARY + SECONDARY columns, rate-limit guidance), §3 (LONG-to-MEDIUM fallback rule) | Backup endpoint resolution; rate-limit backoff parameters; tier downgrade rules |
| `_system/PPT-ANALYSIS-SOP.md` | §3C (re-route, do not downgrade doctrine) | Library-wide rule against silent resolution downgrade; promoted from deck context to all generation |
| `_system/TEST-PROTOCOL.md` | §5 (patch-loop criteria — style failures only) | Hard boundary that infrastructure noise does not generate Fidelity Tester strikes |

All routing decisions are made by reading MODEL-SPECS §2 at runtime. Do not cache or copy routing column values into this SOP — MODEL-SPECS changes, this SOP does not.

---

## Procedure (ordered)

**Failure class ladder — execute the matching row in sequence; stop at the first response that succeeds or at hard stop:**

| Failure class | First response | Second response | Hard stop |
|---|---|---|---|
| **5xx / timeout (transient)** | Retry once after 30-second backoff | Route to backup endpoint (MODEL-SPECS §2 SECONDARY column) with CDO notification | If backup also fails: hard stop — preserve manifest + all receipts; notify CDO |
| **429 (rate limit)** | Backoff per MODEL-SPECS §2 rate-limit guidance; halve concurrency | Continue at reduced concurrency | If 429 persists for more than 3 events within any 10-minute window: hard stop; notify CDO |
| **Endpoint down (confirmed)** | Route immediately to backup endpoint from MODEL-SPECS §2 SECONDARY column; notify CDO | — | If backup is also down: hard stop — preserve all manifests + receipts; notify CDO |
| **402 / credit exhaustion** | Immediate hard stop — do not retry, do not re-route | Preserve manifest + receipts for resume; notify CDO | — |
| **NSFW checker false positive** | Flag for CDO + human review; halt the specific task; do not auto-retry with prompt mutation | — | CDO decides whether to re-run, modify prompt, or escalate |

**Step-by-step for every fallback event:**

1. **Identify the failure class.** Read the HTTP status code and response body from the Kie.ai API response. Map to the ladder table above. Do not diagnose beyond the HTTP status — infrastructure errors are not style problems.

2. **Log the event.** Write a fallback event entry to `_local/fallback-log.md` immediately: ISO 8601 timestamp, failure class, endpoint affected, HTTP status + response excerpt, action selected from the ladder.

3. **Execute the first response.** Follow the ladder table entry exactly. Do not skip steps or jump to the hard stop before exhausting the ordered responses.

4. **Notify CDO for all non-transient events.** A single successful 30-second retry (5xx / timeout) does not require CDO notification. Every other ladder row — backup re-route, 429 halve, 402 hard stop, NSFW flag — requires CDO notification with the fallback log entry.

5. **Re-route to backup endpoint.** When the ladder directs a backup re-route, open MODEL-SPECS §2 SECONDARY column for the job's task category. Verify the backup endpoint supports the job's requested aspect ratio and tier. If it does not, this is a hard stop — return to CDO with the compatibility gap; do not silently change aspect ratio or tier.

6. **Apply tier downgrade only per MODEL-SPECS §3.** If the backup endpoint's LONG tier is also unavailable, apply the MODEL-SPECS §3 LONG-to-MEDIUM rule with explicit CDO notification. If MEDIUM is also unavailable on the backup, this is a hard stop. Never apply a tier downgrade that was not reached by traversing this rule — do not silently generate at a lower quality level.

7. **On hard stop: preserve all state.** Write a `state: hard-stopped` entry on every in-flight receipt. The manifest (job work-list), all submitted receipts, and all downloaded results must remain intact and addressable. The CDO must be able to resume the job from the preserved state without regenerating completed slides.

8. **Do not route infrastructure failures to the Fidelity Tester.** If the failure class is 429, 5xx, or 402, the job is paused or re-routed — it does not accrue patch-loop strikes. Only a completed generation that fails the SOP 9.4 postflight checklist or fails the Fidelity Tester's style rubric generates a strike.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| HTTP response from Kie.ai API (`createTask` or `getTaskInfo`) | Yes | Kie.ai API at submission or polling time |
| MODEL-SPECS §2 routing table (read at runtime) | Yes | `_system/MODEL-SPECS.md` |
| MODEL-SPECS §3 tier fallback rule (read at runtime) | Yes | `_system/MODEL-SPECS.md` |
| Job manifest (slide work-list for multi-asset jobs) | Yes | `_local/jobs/{job-id}/manifest.json` written by the requesting role |
| All in-flight receipts for the current job | Yes | `_local/receipts/` |
| Client `budget_config` block (for 402 / credit-exhaustion context) | Yes | Client `_local/budget_config.json` or `openclaw.json` |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| Fallback event log entry | `_local/fallback-log.md` | Appended entry per event |
| Updated receipt(s) | `_local/receipts/{receipt-id}.json` | `state: hard-stopped` on hard-stop events; `state: submitted` on successful re-route |
| CDO notification | Via `openclaw message send` | Sent immediately for all non-transient ladder rows |
| Preserved manifest + receipts (hard-stop only) | `_local/jobs/{job-id}/manifest.json` + `_local/receipts/` | Intact; resumable |

---

## Handoff Conditions

- **Successful re-route:** The backup endpoint accepts the re-submitted job. Write a new receipt with the backup endpoint recorded. Hand back to the cron poller for completion detection. CDO receives the re-route notification.
- **Hard stop — infrastructure:** All state preserved. Hand to CDO for decision: resume when the primary endpoint recovers, continue on the backup, or cancel the job. Do not re-submit without CDO direction.
- **Hard stop — 402 / credit exhaustion:** Hand to CDO for budget resolution. The preserved manifest allows exact resume once credits are restored — completed slides are not regenerated.
- **NSFW false positive:** Hand to CDO for prompt review. The specific task is paused; the rest of the job may continue if other tasks are queued.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| Backup endpoint does not support the job's aspect ratio or tier | Hard stop. Return to CDO with the compatibility gap. Do not silently alter the job parameters. |
| Both primary and backup endpoints are simultaneously down | Hard stop. Preserve all state. Notify CDO. Do not attempt a third-endpoint substitution without explicit CDO direction. |
| 429 persists for more than 3 events in any 10-minute window | Hard stop. Notify CDO. Resume only after CDO direction on timing or endpoint change. |
| 402 / credit exhaustion detected | Immediate hard stop. Notify CDO. Never re-route a credit-exhausted account — the problem is account-level, not endpoint-level. |
| Fallback event attempts a mid-deck model swap | This is a hard violation, not a fallback option. Escalate to CDO immediately. A Slide Manifest is a cohesion contract — every slide must use the same model. |
| Any fallback path would require a silent resolution downgrade | This is a hard violation. Re-route to a capable endpoint or hard stop. Escalate to CDO if no capable endpoint exists. |
| An infrastructure failure (429 / 5xx / 402) is about to generate a Fidelity Tester strike | Refuse. Infrastructure noise never counts as a patch-loop strike. Escalate to CDO if the requesting role insists. |

---

## Absolute Rules (no exceptions, no override path short of CDO written authorization)

- **NEVER swap models mid-deck.** A Slide Manifest locks the model for every slide in the job. Halt and escalate.
- **NEVER silently downgrade resolution.** Re-route to a backup endpoint capable of the requested resolution, or hard stop. Notify CDO before any tier change under MODEL-SPECS §3.
- **NEVER route infra failures to the Fidelity Tester.** 429, 5xx, and 402 are infrastructure events — the Fidelity Tester's patch loop scores style only.
- **NEVER auto-retry an NSFW false positive with prompt mutation.** That is prompt authoring work; the Operator does not modify prompts. Escalate to CDO.
- **ALWAYS preserve manifests on every hard stop.** Resumability is non-negotiable.

---

*Library-version pin: MODEL-SPECS v1.0 (§§2, 3), PPT-ANALYSIS-SOP v1.0 (§3C), TEST-PROTOCOL v1.0 (§5) — §-refs verified 2026-06-12.*
