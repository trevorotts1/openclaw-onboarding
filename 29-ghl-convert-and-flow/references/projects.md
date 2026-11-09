# Projects — API/UI availability, task rules and one-way Command Center projection

> **Authority.** The executable registry (`44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py`) is the only implementation authority. This reference is a derived, source-indexed view. Reading it cannot enable an operation; enablement is per `(operation_id, tenant)` in the capability gate.
>
> **Evidence state (2026-11-08).** Pages were not refetched in this lane. `ghl-contract-sources.json` labels each source `inheritented`/`reopened-at-spec-time`, never "verified live". A source-reported capability is not a measured entitlement of this or any client account. Machine-readable rows: `ghl-hybrid-capability-index.json`.

## Availability is three separate facts

1. UI: Project Management behind the plan/Labs setting.
2. API: sub-account **Private Beta** access for the Projects API (V15); a visible UI or a general MCP connection does not imply it.
3. MCP: the official client-specific hosted endpoint with OAuth (V07), scoped per connection.

Record each separately. Trevor's owner-supplied Agency Pro fact prevents an unnecessary upgrade recommendation; it is not a measured API entitlement for any client.

## Contract details that are not generalizable

- OAuth/PIT location is **token-derived**. Do not send `locationId` indiscriminately in path/body/headers.
- Create responses can be HTTP 200; do not assume 201 means success and 200 means failure.
- Pagination differs per endpoint: cursor, search-after, skip/limit. Never reuse one paginator for the module.
- Creating a space may create a default list server-side; discover it rather than creating a duplicate.
- Task create requires `title` and a real `dueDate`; accepts at most **one** assignee; `parentTaskId` for subtasks; status group derives from the selected status.
- Preserve opaque sort values. Do not invent numeric ordering.
- Private-space membership is explicit; omitting a member in an additive update is not revocation.
- Adding a task to another list preserves identity; the home list controls status configuration.
- Comments and recurring tasks have separate documented operations; do not tunnel an RRULE through a generic task write.

## Synthetic minimal task request

```json
{"title":"Verify course delivery","dueDate":"2026-12-01T17:00:00-05:00","assigneeId":"SYNTHETIC_USER_ID"}
```

Failure: two assignees → refuse locally. Failure: no due date → leave projection pending; never fabricate one. Readback: re-read the task's home list, status, due date and assignee.

## Command Center projection — one way in this release

- Command Center remains authoritative for build state, evidence and QC.
- Mapping key: `company_id + location_id + cc_task_id` → `project_space_id + project_home_list_id + project_task_id`.
- Field ownership defaults: CC owns verified completion and approved evidence links; human-entered GHL notes/dates are not overwritten unless explicitly CC-owned.
- A Projects task marked done does not certify a course/page/workflow and does not move CC to Done.
- Duplicate events reuse the mapping; a lost create response is reconciled before another create.
- Projects outage blocks only the projection, not the business work.

Required tests: correct-company source → one mapped task; duplicate/reordered event → no duplicate; remote Done → no CC completion; beta unavailable → explicit pending; missing date → no guessed date; one-way echo protection.

## Registry state

No `projects.*` registry row exists at this base; `documented_unregistered` carries `projects.spaces.create` and `projects.tasks.create` as **beta-gated** gaps (WF32). WF33 owns the CC mapping module. Do not add a second credentialed GHL client in React.
