# Runtime adapter contract (Skill 78)

`scripts/selection_runtime.py` is the single entry point the launch
runtime calls. It adds no behavior: each action dispatches to one
shipped module, and every failure returns a structured envelope instead
of a traceback.

## Envelope

Request: `{"action": <name>, ...action fields}`.
Success: `{"ok": true, "action": <name>, "result": ...}`.
Failure: `{"ok": false, "error": {"code": "S78-*", "message": ...}}`.

CLI exit codes mirror the house convention: 0 ok, 2 violation, 3
fail-closed (bad request, unknown action, storage failure).

## Actions

| Action | Fields | Result |
| --- | --- | --- |
| `invocation` | launch | `{"mode": "proceed"}` or the single-offer decline verdict |
| `plan` | launch, recommendation?, production? | selection plan (or the declined_single_offer plan) |
| `preview` | plan, state? | `{"html": ...}` for default / selected / error / reconfirm |
| `select` | launch, offer_id, price_choice_id, quantity?, selected_at, source_page_id, session_ref | selection.json intent (approval re-checked inside the core) |
| `validate_binding` | selection, launch, expected_revision | `{"valid": true}` or a violation (A05 handoff revalidation) |
| `reject_query_authority` | query | `{"accepted": true}` or `S78-QUERY-PRICE-AUTHORITY` |
| `binding_plan` | launch, targets, route? | per-price-choice binding plan for S79 / S06 |
| `page_result` | plan, author_session, request_id, page_id, input_hash (or a nested `page_request` / `request` document carrying them), test_only? | packet page-result 1.0 document: `page_id` and `input_hash` echoed from the request, no `outcome` field; a call with no echo source fails closed |
| `session_create` | selection, now | `{"session_ref": ...}` |
| `session_resume` | session_ref, tenant_id, launch_id, launch, now | resumed / reconfirm_required / expired |
| `session_confirm` | session_ref, tenant_id, launch_id, launch, now | confirmed (idempotent) / reconfirm_required / expired |

## Construction-time configuration

`Runtime(store=...)` fixes the session store before any request is
handled: `{"kind": "memory"}` (default) or
`{"kind": "durable", "base_dir": <path>}` (production; see
`references/session-storage-contract.md`). Request fields cannot change
the store, its location, or its TTL.

## Registry

`runtime-manifest.json` at the skill root describes this adapter
(entry module, actions, schemas, stores) for INTEGRATION's registry
wiring. Discoverability in the installed registry remains
INTEGRATION-owned; the manifest is the descriptor S78 supplies.

## Descriptor is not an installation

A runtime descriptor is NOT an installation. `runtime-manifest.json`
carries `descriptor_only: true`, `proof_level: "descriptor_only"`, and
`installation.state: "not_installed"` with null proof/evidence fields.
Registering or reading the manifest proves only that the entry module
and action set exist; it proves no native page, route, or price is
installed in any tenant.

Installation and live proof come only from an authorized install run
that emits `installed_test_verified` or later. Until such a run exists,
`page_result` stays L1 (`authored` / `locally_verified` / `blocked`),
and no descriptor field may be read as installation or live evidence.

