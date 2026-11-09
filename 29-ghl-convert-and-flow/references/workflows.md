# Workflows — public read, beta definition contract, private fallback

> **Authority.** The executable registry (`44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py`) is the only implementation authority. This reference is a derived, source-indexed view. Reading it cannot enable an operation; enablement is per `(operation_id, tenant)` in the capability gate.
>
> **Evidence state (2026-11-08).** Pages were not refetched in this lane. `ghl-contract-sources.json` labels each source `inheritented`/`reopened-at-spec-time`, never "verified live". A source-reported capability is not a measured entitlement of this or any client account. Machine-readable rows: `ghl-hybrid-capability-index.json`.

## The accurate boundary (replaces the old "GET-only" statement)

At this branch base the registry carries:

| Operation | Method / path | Version | Classification |
|---|---|---|---|
| `workflows.list` | `GET /workflows/` | `v3` | implemented |
| `workflows.enroll` | `POST /contacts/{contactId}/workflow/{workflowId}` | `v3` | implemented |
| `workflows.remove` | `DELETE /contacts/{contactId}/workflow/{workflowId}` | `v3` | implemented |
| `workflows.definition.read` | `GET /workflows/{workflowId}/definition` | `v4` | beta-gated (`B-V4-S`) |
| `workflows.definition.create` | `POST /workflows/` | `v4` | beta-gated (`B-V4-S`) |
| `workflows.definition.update` | `PUT /workflows/{workflowId}/definition` | `v4` | beta-gated (`B-V4-S`) |
| `workflows.status.publish` | `PUT /workflows/{workflowId}/status` | `v4` | beta-gated (`B-V4-S`) |
| `workflows.definition.delete` | `DELETE /workflows/{workflowId}` | `v4` | beta-gated (`B-V4-S`) |
| `workflows.restore` | — | — | unresolved (`B-RESTORE-NONE`) |
| `workflows.private.*` | internal `/workflow/{loc}/...` | `2021-07-28` | internal-only |

So: workflow **listing and contact enrollment** are public. Workflow **definition authoring** is a documented staging (`S`) v4 contract, beta-gated, not a production public operation on this branch. The internal Firebase path remains a proven fallback, and the managed browser remains the backstop. `v4` is a staging contract literal; it is never added to the five-version supported set.

## Private-beta facts

- Access is requested through the official Workflows API private-beta form (S02). A 403 on definition writes is classified `beta_not_enabled`, recorded, and routed to the approved fallback; it is never called a bad token.
- Scopes: the public catalog names definition/log/publish permissions; the registry keeps UNKNOWN where the evidence did not settle a scope. Do not synthesize `.write` from `.readonly`. `workflows.logs` is its own permission.
- Validation is non-persisting but consumes the workflow write quota. `POST /workflows/search` is a read. Neither is classified by the verb.

## Graph semantics

- A definition update is a **whole-graph replacement**: preserve opaque, fractional versions and provider step ids; do not silently delete unapproved nodes.
- Stale revision: re-read the current graph and reapply intent; never retry the identical stale payload.
- Published workflow: a 409 preserves live state; do not auto-pause. Draft transition needs explicit authorization.
- Folders have no proven public listing. The internal path derives a folder from an existing workflow; it cannot prove uniqueness. Check the UI and pass an explicit folder id when rebuilding.
- `source.system` and unsupported/no-op actions must be surfaced, not normalized away.
- Safe publish: `PUT /workflows/{workflowId}/status` is beta-gated; without it, publish remains a UI/approved manual step. No doc may say "publish by API" without the beta record.

## Minimal synthetic request

```json
{"name":"ZHC Welcome Sequence","locationId":"SYNTHETIC_LOCATION","steps":[{"id":"SYNTHETIC_STEP","type":"sms","body":"Approved copy"}]}
```

Failure event: submit a graph missing a provider-required step field → local validation refuses before transport. Second failure: apply an update with an old revision → 422/409; re-read, reapply, never blind retry.

Readback: `GET /workflows/{workflowId}/definition` (beta) or the managed-browser export, then compare step ids, order and the published flag. An HTTP 200 create is not a saved graph.

## Fallbacks and diagnostics

- Public beta unavailable → approved Firebase/internal implementation (same tenant, same intent).
- Internal token unread/misconfigured → managed Tier-4 builder (Skill 6, gated).
- Token genuinely dead → authorized Tier-2 self-heal; Tier 4 cannot seed without a token.
- Ambiguous write outcome → reconcile by ids/fingerprints/reads; never re-issue on a second rail.

Logs and statistics are documented in `workflow-monitoring.md`; they are not part of `GET /workflows/`.
