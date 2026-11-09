# Workflow monitoring — logs, windows, cursors and honest metrics

> **Authority.** The executable registry (`44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py`) is the only implementation authority. This reference is a derived, source-indexed view. Reading it cannot enable an operation; enablement is per `(operation_id, tenant)` in the capability gate.
>
> **Evidence state (2026-11-08).** Pages were not refetched in this lane. `ghl-contract-sources.json` labels each source `inherited`/`reopened-at-spec-time`, never "verified live". A source-reported capability is not a measured entitlement of this or any client account. Machine-readable rows: `ghl-hybrid-capability-index.json`.

## Contract constraints

- Permission: `workflows.logs` (separate from `workflows.readonly`).
- Query windows: at most **30 days**; retention **60 days**. Expose these as versioned constraints, not hidden assumptions.
- Continuation values are opaque. Carry them forward verbatim; never reconstruct or offset them.
- Split larger periods into non-overlapping windows; keep the same filters across a scan.
- Deduplicate on a stable documented record identity when windows/pages can overlap.
- Distinguish failed steps, waiting states, completed contacts and removals. Do not collapse every non-completed status into "error".

## Metrics that are not conversion

Aggregate results count log events by requested grouping. A same-window completions ÷ enrollments ratio is not a cohort conversion rate: contacts can enter before the window and finish inside it. A ratio above 100% is not automatically a platform defect. Report exact metric definitions. If cohort completion is required, implement and validate cohort analysis from records; do not relabel a ratio.

## Runtime states (keep separate)

```text
definition_validated
stored_definition_verified
published_status_verified
builder_rehearsal_verified
controlled_live_execution_verified
ongoing_monitoring_configured
```

A builder rehearsal legitimately lacks production logs. A controlled live test needs an approved test contact and suppression/isolation of unintended customer communications. Empty logs never satisfy live proof.

## Minimal request / failure / readback

Request (synthetic):
```text
GET /workflows/SYNTHETIC_WORKFLOW_ID/logs?locationId=SYNTHETIC_LOCATION&startDate=2026-11-01T00:00:00Z&endDate=2026-11-08T00:00:00Z
```

Failure: end − start > 30 days → refuse locally with the exact constraint. Failure: missing `workflows.logs` → record scope state; never retry as another tenant.

Readback: page to exhaustion using the returned cursor; assert dedupe count and window coverage; return a redacted summary, not message bodies or PII.

## Registry state

No `workflows.logs.*` registry row exists at this base; `documented_unregistered` carries logs and statistics as documented-unimplemented gaps owned by **WF25**. Implement bounded polling and rate limits; persistent monitoring is a separately installed runtime job, not a chat promise.
