# Skill 29 — Usage Instructions

> How to answer a GHL question and execute the right call without guessing. The registry row is the contract; this file is the procedure.

## Step 1 — classify the request

Match the task to a domain family, then open the one reference. Do not read every file, and never paste this skill or the document spec into a core file.

| Request | Family | Reference |
|---|---|---|
| Course/module/lesson/offer/enrollment/import | courses | `references/courses.md` |
| Workflow read/build/publish/enroll | workflows | `references/workflows.md` |
| Group/channel/Learning/member | communities | `references/communities.md` |
| Post/schedule/comment/member author | social-planner | `references/social-planner.md` |
| Logs/statistics/runtime proof | workflow-monitoring | `references/workflow-monitoring.md` |
| Room setup/join links | meeting-rooms | `references/meeting-rooms.md` |
| Voice agent/action/call log | voice-ai | `references/voice-ai.md` |
| Conversation AI/responder | conversation-ai | `references/conversation-ai.md` |
| Studio graph/promote/execute | agent-studio | `references/agent-studio.md` |
| KB source/train/attach/retrieve | knowledge-base | `references/knowledge-base.md` |
| Widget create/embed/thread | chat-widgets | `references/chat-widgets.md` |
| Projects space/list/task | projects | `references/projects.md` |
| Invoice/payment/order/subscription | payments | `references/payments.md` |
| Calendar/appointment/services | calendars | `references/calendars.md` |

## Step 2 — look up the operation in the index

Open `references/ghl-hybrid-capability-index.json` and find the operation id. Read `classification` before anything else:

- `implemented` → the registered rail is the intended route; still check the row's `blocker` and `required_query`.
- `beta-gated` → the operation is a documented staging/beta contract. Do not present it as production-available. Record `beta_not_enabled` and use the approved fallback.
- `documented-unimplemented` → the vendor contract may exist but this branch has no adapter row. Stop; do not call it. Use the documented fallback or report the gap.
- `browser-backed` → managed browser only, with captured/runtime selectors.
- `internal-only` → approved private path, not "public API".
- `unresolved` / `retired` / `excluded` → do not execute; report the classification.

If the family has no row, read `documented_unregistered` for its labelled gap.

## Step 3 — build the request

Take from the row, not memory: method, path template, `version`, tenant binding, required query, auth class. Substitute only synthetic/real ids; never invent a field.

Request rules:
- Send only supplied fields plus the documented tenant field. Never send empty/null/blank values that can wipe data.
- Contact writes: generic add/save → `POST /contacts/upsert` with match keys; explicit NEW → `POST /contacts/`; known id → read then PUT only supplied fields. Never put a `tags` array in an upsert/update body.
- Every write ends with the row's `readback_plan` (or the reference's readback): capture id, GET, confirm intended fields. A succeeded write with failed readback is "WRITE SUCCEEDED — VERIFICATION INCOMPLETE"; never re-fire to check.
- Pagination: use the endpoint's own style — cursor, search-after, or skip/limit. Never reuse one paginator across a module.
- Opaque cursors and revisions are carried verbatim, never reconstructed.

## Step 4 — execute and classify the response

| Status | Meaning | Action |
|---|---|---|
| 200/201 | accepted | read back before calling it complete |
| 400/422 | bad request / stale revision | fix the stated field; re-read stale graph and reapply intent |
| 401 | credential | run the resolver; never emit an empty Bearer |
| 403 | scope/role/tenant | classify exact cause; record; repair authorization; never switch tenant |
| 404 | missing object vs wrong route vs unsupported | distinguish before creating anything |
| 409 | conflict/published | preserve live state; draft transition needs authorization |
| 429 | rate limit | stop, surface reset, do not tier-hop |
| 5xx/timeout after write | ambiguous | mark `unknown_outcome`; reconcile by ids/fingerprints/reads |

Explicit beta denial (`WORKFLOW_API_NOT_ENABLED_FOR_LOCATION`) → `beta_not_enabled`; select the approved private fallback; queue the access request separately. It is not a bad token.

## Step 5 — one minimal example per family

Every reference carries one minimal request, one meaningful failure and one readback with **synthetic** ids. Follow those shapes. They prove DTO separation, not live readiness or supported rich formatting.

## Step 6 — report

Report: operation id, selected rail, version, location scope (not a secret), outcome, readback state, evidence path, and any activation gap. Do not report an adapter as a live capability, and do not report a plan as a delivery.

## Contacts — write routing (unchanged and binding)

| Intent | Call |
|---|---|
| Generic "add/save this person" | `POST /contacts/upsert` (match keys; omit createNewIfDuplicateAllowed) |
| Explicit "create a NEW contact" | `POST /contacts/` |
| Known contactId "update" | GET then PUT only supplied fields; `--tag` refused destructive |

Upsert matching is resolved by HighLevel's Location-level Allow Duplicate Contact configuration; never claim a fixed email/phone rule.

## Safety checklist before a destructive call

- [ ] Correct object id and tenant.
- [ ] Explicit instruction for delete/void/cancel/release.
- [ ] Phone release: Trevor-only.
- [ ] Billing/payment change: Trevor-only.
- [ ] Readback plan ready.

## Testing a documentation change

Run the A18 test and the affected family test selection. A docs change that edits a route must regenerate `ghl-hybrid-capability-index.json` in the same commit; the test fails on a hash mismatch.
