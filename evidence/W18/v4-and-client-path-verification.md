# GHL-160 — V4 staging refusal and client call-path verification

Unit: GHL-160. Branch: `ghlupd/W18-v4`, cut from `origin/main`
(`727fb0a83`, 2026-10-19). Worktree:
`/Volumes/mac mini m4/Downloads/GHL updates/worktrees/W18-v4`.

**Proof labels.** Every statement carries one:

- **SOURCE-VERIFIED** — read from the repository at the revision above.
- **RECORDED-LIVE-EVIDENCE** — taken from `GHL_UPDATES_live-ledger.md`; not
  re-run by this unit. No live API call was made here, no workflow activated,
  no communication sent, no secret printed.

**Verdict summary.**

1. All five public V4 workflow operations are frozen at documented level `S`
   (staging), Version `v4`, blocker `B-V4-S`, with staging-marketplace doc
   URLs. The capability gate is default-deny and a V4 write additionally needs
   `canary_verified`. No code path labels them production. **SOURCE-VERIFIED**
2. Skill 44 is the only named consumer wired to the V4 adapter, and its route
   selection cannot choose the public V4 path on a fresh adapter even when a
   capability record admits every operation (finding **F1**). Skill 58 is an
   extra consumer with a correct direct-read path. Skill 35, Skill 06 and the
   signature-funnel consumers are not wired to the adapter at all.
   **SOURCE-VERIFIED**
3. Eight CLI call sites use a route with no registry row; one still uses the
   retired `contacts.list` row. Each is listed with a replacement or a named
   gap in §5. **SOURCE-VERIFIED**

Machine check: `python3 -I evidence/W18/check-v4-and-paths.py` → `RESULT: PASS
— 138 checks`, exit 0. **SOURCE-VERIFIED**

---

## 1. V4 operation inventory

Source: `44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py:691-709`.
**SOURCE-VERIFIED**

| Operation id | Method / path | Level | Version | Blocker | Staging doc | Write | Approval |
|---|---|---|---|---|---|---|---|
| `workflows.definition.read` | GET `/workflows/{workflowId}/definition` | `S` | `v4` | `B-V4-S` | `staging.marketplace.gohighlevel.com/docs/ghl/workflows/get-workflow-definition/index.html` | no | no |
| `workflows.definition.create` | POST `/workflows/` | `S` | `v4` | `B-V4-S` | `.../create-workflow/index.html` | yes | yes |
| `workflows.definition.update` | PUT `/workflows/{workflowId}/definition` | `S` | `v4` | `B-V4-S` | `.../update-workflow-definition/index.html` | yes | yes |
| `workflows.status.publish` | PUT `/workflows/{workflowId}/status` | `S` | `v4` | `B-V4-S` | `.../update-workflow-status/index.html` | yes | yes |
| `workflows.definition.delete` | DELETE `/workflows/{workflowId}` | `S` | `v4` | `B-V4-S` | `.../delete-workflow/index.html` | yes | yes |

The staging base is declared once: `operations.py:50` (`STAGING_DOCS =
"https://staging.marketplace.gohighlevel.com/docs"`). **SOURCE-VERIFIED**

`v4` is deliberately absent from the production Version vocabulary:
`operations.py:53` says "``v4`` is staging-only and is never added here", and
`SUPPORTED_VERSIONS` at `operations.py:54-56` contains only `v3`,
`2023-02-21`, `2021-07-28`, `2021-04-15`, `legacy`. **SOURCE-VERIFIED**

Named gaps sit beside the rows, never invented: `validation.read` and
`restore` map to `NONE` in `public/workflow_v4.py:80-88` and raise
`WorkflowGap` through `GAP_RULES` (`workflow_v4.py:95-112`).
**SOURCE-VERIFIED**

## 2. Why the adapter cannot present V4 as production

Five independent guards, all in source. **SOURCE-VERIFIED**

1. **Row metadata.** Level `S`, Version `v4`, blocker `B-V4-S`, staging doc
   URL (§1).
2. **Default-deny capability gate.** `CapabilityGate.get`
   (`public/capability.py:199-211`) returns a disabled `Capability` carrying
   `DEFAULT_BLOCK` when no row exists. `Capability.__post_init__`
   (`capability.py:126-135`) makes `enabled=True` together with an activation
   block impossible.
3. **Evidence rule.** `Capability.evidence_ok` (`capability.py:137-152`)
   requires `contract_verified AND adapter_built AND offline_tests_passed AND
   read_verified`. `write_ready` (`capability.py:163-164`) additionally
   requires `canary_verified`. A V4 write therefore cannot be enabled by
   offline evidence alone.
4. **Tenant-bound refusal before transport.** `PublicGhlAdapter.call`
   resolves the gate for the call tenant (`public/adapter.py:468-469`,
   `_gate_for` at `:763-775`), refuses a foreign-tenant capability
   (`:474-500`, rule `capability_tenant_mismatch`), then for a write requires
   `capability.write_ready()` (`:502-503`). A refusal returns
   `Status.denied`, rule `capability_disabled` (`:505-521`), with
   `refused_before_transport: True`; the transport is never reached.
5. **Workflow adapter pre-check.** `WorkflowV4Adapter._require_operation`
   refuses a named gap (`public/workflow_v4.py:267-283`); each write checks
   `_enabled` and returns a receipt through `_disabled_result`
   (`workflow_v4.py:387, 518, 792, 923`, `:1228-1265`) with
   `capability_enabled: False` and no HTTP status.

The checked-in record admits nothing and contains no V4 row:
`44-convert-and-flow-operator/tools/engine/state/ghl-public-capabilities.json:3`
records tenant `XCgFTEA1oDvsPnTqqgoB`, `:7-49` holds four rows
(`locations.get`, `contacts.list`, `contacts.search`, `custom_fields.list`),
all `enabled: false`. **SOURCE-VERIFIED**

**Ceiling of the enforcement.** There is no runtime branch that says "v4 is
staging": the registry validation at `operations.py:824` explicitly permits
the literal `v4` on *any* documented row
(`row.version not in SUPPORTED_VERSIONS and row.version != "v4"`), without
requiring level `S` or blocker `B-V4-S`. Current rows are correct; a future
`D`+`v4` row would pass validation. Recorded as finding **F4**.
**SOURCE-VERIFIED**

## 3. Findings

| Id | Severity | Finding | Evidence |
|---|---|---|---|
| **F1** | MAJOR | V4 write enablement is probed without a tenant. `WorkflowV4Adapter._enabled` (`public/workflow_v4.py:288-289`) calls `self._public.capability(operation_id)` with no tenant; `PublicGhlAdapter.capability` (`public/adapter.py:756-760`) then answers from an explicit gate, or from the single record gate already loaded, otherwise default-deny. `workflow_route` (`utils/workflow_builder.py:96-131`, probe at `:121`) uses the same call, so on a fresh adapter every V4 surface routes to `skill44_private_fallback` even when a record admits all five operations. Proven below. | SOURCE-VERIFIED |
| **F2** | MAJOR | V4 write reachability is order-dependent. After any tenant-scoped call loads exactly one record gate, `adapter.py:758-760` makes `_enabled` return the admitted value; before that it returns false. A route decision must not depend on whether an unrelated read happened first. | SOURCE-VERIFIED |
| **F3** | MAJOR | The checked-in record is bound to tenant `XCgFTEA1oDvsPnTqqgoB`, not the live tenant `Mct54Bwi1KlNouGXQcDX`; `load_capability_record` fails closed on the mismatch (`capability.py:303-347`), so on `origin/main` every read and write is denied for BlackCEO LLC. RECORDED-LIVE-EVIDENCE says GHL-150 bound the record to `Mct54...` and enabled six operations with observed 200s (ledger `:745, :752-762, :796`); that state is not on the checked-out `origin/main`. | MIXED |
| **F4** | MINOR | Registry validation does not tie `v4` to level `S` / `B-V4-S` (`operations.py:824`); staging-only is a data convention, not a validator rule. | SOURCE-VERIFIED |
| **F5** | MINOR | `Capability.evidence_ok` has an unreachable second `return (...)` that references an undefined name `tenant_read` (`capability.py:153-158`). Dead code; no behavioural escape, but it should be deleted. | SOURCE-VERIFIED |
| **F6** | MAJOR (activation lane) | `workflows.list` is registered at Version `v3` (`operations.py:680-682`), but the recorded live 200 was observed with `2021-07-28` (ledger `:759`). Enabling that row on this record would claim capability for a request shape the adapter never sends. | MIXED |
| **F7** | MINOR | Media Version drift: registry `media.upload` is `v3` with no alternate (`operations.py:591-593`), while Skill 06 sends `Version: 2021-07-28` (`06-ghl-install-pages/tools/ghl_media.py:140, 859`). | SOURCE-VERIFIED |
| **F8** | MINOR | The router note "Media LIST has no implementation … UNSUPPORTED" (`06-ghl-install-pages/tools/ghl_object_router.py:381-384`) is stale against RECORDED-LIVE-EVIDENCE: `GET /medias/files?type=file` returned 200 and the bare call returned 422 requiring `type` (ledger `:757-758, :762`). The client is missing; the API is not unsupported. | MIXED |
| **F9** | INFO | No shipped CLI verb calls `publish_workflow` or `delete_workflow`; they exist only as adapter methods (`workflow_v4.py:865, 905`) and tests. Both are denied by F1 on a fresh adapter. | SOURCE-VERIFIED |

### F1/F2 proof (fake transport, no network, no credential)

A synthetic record for tenant `Mct54Bwi1KlNouGXQcDX` enabled
`workflows.definition.read` and `workflows.definition.create`/
`update` with `canary_verified: true`, then a fresh `WorkflowV4Adapter` was
built over `PublicGhlAdapter(capability_record=...)`. **SOURCE-VERIFIED**

```
definition.read => skill44_private_fallback | capability disabled; using the named Skill 44 private fallback
create          => skill44_private_fallback | capability disabled; ...
update          => skill44_private_fallback | capability disabled; ...
status.change   => skill44_private_fallback | capability disabled; ...
delete          => skill44_private_fallback | capability disabled; ...

fresh v4._enabled(workflows.definition.update): False
fresh update status: denied rule: capability_disabled
read status (record admits): ok
after-load v4._enabled(workflows.definition.update): True
```

The last two lines are F2: the same adapter flips from deny to admit only
because the preceding tenant-scoped read loaded the record. No secret was
read; the fake transport returned fixed bytes.

## 4. Consumer call-path traces

### 4.1 Skill 44 — Convert-and-Flow orchestration (wired, blocked by F1)

Call path, all **SOURCE-VERIFIED**:

1. CLI resolves the adapter: `gohighlevel_cli.py:799-808` `_get_public_v4`
   → `utils/workflow_builder.py:134-163` `load_public_v4`, which constructs
   `PublicGhlAdapter(auth=..., transport=..., capability=None)` at `:160-162`
   and wraps it in `WorkflowV4Adapter`.
2. Operation id lookup: `workflow_builder.py:86-93` reads
   `WorkflowV4Adapter.OPERATION_MAP` (`workflow_v4.py:80-88`).
3. Route decision: `workflow_builder.py:96-131`; the probe is
   `capability = v4.capability(key)` at `:121`.
4. V4 adapter surface:
   - read → `read_definition_document` (`workflow_v4.py:311-331`) →
     `read_definition` (`:295-308`) → `PublicGhlAdapter.call`.
   - create → `create_workflow` (`:372-472`) → `_enabled` gate at `:387` →
     `_write` (`:1366-1400`) → `PublicGhlAdapter.call`.
   - update → `update_definition` (`:483-773`) → gate at `:518` → `_write`.
   - publish → `publish_workflow` (`:865-881`) → `set_status`
     (`:775-863`) → gate at `:792` → `_write`.
   - delete → `delete_workflow` (`:905-1008`) → gate at `:923` → `_write`.
5. CLI call sites: create `gohighlevel_cli.py:880`; get `:1034`; export
   `:1073`; update `:1135`; build `:1299`; builder create path
   `workflow_builder.py:685-739` → `self.public_v4.create_workflow` at `:711`.

**Reachability verdict.**

- **Reads:** `read_definition` does not consult `_enabled`; it calls
  `PublicGhlAdapter.call`, which binds the gate to `tenant.location_id`
  (`adapter.py:468-469`). A V4 read is therefore reachable **once the
  capability record admits it** — but only if the caller bypasses
  `workflow_route`, which on a fresh adapter answers "disabled" (F1). The
  shipped `workflows get` / `export` verbs do not bypass it.
  **SOURCE-VERIFIED**
- **Writes (`create`, `update`, `status.publish`, `delete`):** denied on a
  fresh adapter regardless of the record (F1), and admitted only after an
  unrelated tenant-scoped call has loaded the record (F2). Writes also need
  `canary_verified` at the adapter layer (`adapter.py:502-503`).
  **SOURCE-VERIFIED**

### 4.2 Skill 58 — Podcast production (extra consumer, correct direct-read path)

`58-podcast-production-engine/scripts/activate-podcast-fb-workflows.py`
builds an explicit tenant-bound `CapabilityGate` from the record (`:170-186`,
gate at `:185`) and calls the adapter directly:
`workflows.list` at `:202`, `workflows.definition.read` at `:220`.
Reads are reachable once the record admits them; the module states the fill +
publish path stays on the private rail because V4 writes are staging-only
(`:24-29`). **SOURCE-VERIFIED**

### 4.3 Skill 35 — Social Media Planner (registered operations, no adapter path)

- Tier 0 is `caf`: `35-social-media-planner/CORE_UPDATES.md:7`.
- `caf social accounts` → `gohighlevel_cli.py:1942-1947`
  `api.get("/social-media-posting/{loc}/accounts")`.
- `caf social posts` → `gohighlevel_cli.py:1956-1972`
  `api.post("/social-media-posting/{loc}/posts/list")`.
- `caf social create-post` → `gohighlevel_cli.py:2013-2074`
  `api.post("/social-media-posting/{loc}/posts")`.
- `api` is the legacy client: import at `gohighlevel_cli.py:12`,
  `utils/ghl_client.py:20` base URL, Version chosen by path prefix at
  `ghl_client.py:23-38` and overrides at `:54-96`.
- Registry rows exist for these operations: `social.accounts.list`,
  `social.posts.list`, `social.posts.create`
  (`operations.py:616-629`). **SOURCE-VERIFIED**

**Verdict.** No file under `35-social-media-planner` constructs or imports
`PublicGhlAdapter` (machine check §6). The operations are **not reachable
from the skill through the adapter**, and the legacy route bypasses the
capability gate entirely. If the skill were re-pointed to the adapter, the
two reads and the write would each be reachable subject to §4.1's rules.
**SOURCE-VERIFIED**

### 4.4 Skill 06 — Install Pages, products and media (raw REST, no adapter path)

- Router: `06-ghl-install-pages/tools/ghl_object_router.py:369-385`
  (`m["media"]`, rail `REST_SERVICES`, injected runners) and `:387-404`
  (`m["product"]`, same rail shape).
- Media transport: `06-ghl-install-pages/tools/ghl_media.py:135` upload path,
  `:139` folder path, `:140` Version `2021-07-28`, `:792-920` upload,
  `:922-990` folder create.
- `media.files.list`: no client implementation; router note at
  `ghl_object_router.py:381-384`.
- Product operations have rows (`products.list`, `products.create`,
  `products.prices.create` at `operations.py:410-432`), media rows exist at
  `:591-599`. **SOURCE-VERIFIED**

**Verdict.** No adapter wiring; the skill calls `services.leadconnectorhq.com`
directly with its own Version constant. Not reachable through the adapter,
and ungated. Version drift recorded as F7/F8. **SOURCE-VERIFIED**

### 4.5 Signature-funnel consumers (protocol only, no production binding)

- `44-convert-and-flow-operator/tools/siglaunch/provisioning/provisioning.py:29-36`
  defines `Catalog` as a `Protocol`; `provision()` at `:45-90` consumes it.
- The only implementation in-tree is `FakeCatalog`
  (`.../provisioning/test_provisioning.py:13`).
- `49-signature-funnel` contains no GHL route or operation id; its "catalog"
  references are image/product catalog prose, not API calls.
  **SOURCE-VERIFIED**

**Verdict.** No consumer path to any adapter operation id. The binding to
`PublicGhlAdapter` (`tags.list`, `tags.create`, `custom_fields.list`,
`custom_fields.create`, `products.list`, `products.create`) remains a **named
gap**, matching the W11 C17 record. **SOURCE-VERIFIED**

## 5. Routes with no registry row or a retired row

Registry normalization: `{param}` and `%s` both collapse to `{}`; matching is
method + path. The machine check fails if any `api.<verb>("…")` call in the
Skill 44 CLI is neither a registered row nor declared below.
**SOURCE-VERIFIED**

| File:line | Call | Registry status | Disposition |
|---|---|---|---|
| `gohighlevel_cli.py:185` | GET `/contacts/` | **retired** `contacts.list` (`operations.py:217-221`, `B-DEPRECATED`) | Replace with `contacts.search` — POST `/contacts/search`, row at `operations.py:236-240`. Live evidence recorded 200 for both calls (ledger `:753-754`). |
| `gohighlevel_cli.py:689` | GET `/calendars/events/appointments` | no GET row; `appointments.create` is POST-only (`operations.py:376-378`) | **Named gap.** Do not invent a row; use the registered read `calendars.events.list` (GET `/calendars/events`, `operations.py:373-375`) if its shape fits, else report the gap. |
| `gohighlevel_cli.py:1511` | GET `/proposals/document` | no row | **Named gap** (no audited public operation). |
| `gohighlevel_cli.py:1530` | GET `/proposals/templates` | no row | **Named gap.** |
| `gohighlevel_cli.py:1553` | POST `/proposals/document/send` | no row | **Named gap.** |
| `gohighlevel_cli.py:1578` | POST `/proposals/templates/send` | no row | **Named gap.** |
| `gohighlevel_cli.py:1712` | GET `/campaigns/` | no row | **Named gap.** |
| `gohighlevel_cli.py:2113` | GET `/locations/search` | no row; `locations.get` is by id (`operations.py:208-210`) | **Named gap.** |
| `gohighlevel_cli.py:2308` | POST `/users/` | no row | **Named gap.** |
| `06-ghl-install-pages/tools/ghl_rest_canvas.py:126` | GET `/funnels/page/{page_id}` | `funnels.pages.get` is an internal row with `UNKNOWN` path (`operations.py:582-583`) | **Named gap**, Skill 06 authoring rail. |
| `.../ghl_rest_canvas.py:141` | POST `/funnels/builder/autosave/{page_id}` | `funnels.pages.autosave` internal, path `UNKNOWN` (`operations.py:584-585`) | **Named gap**, authoring rail. |
| `.../ghl_rest_canvas.py:154` | GET `/workflow/{loc}/{wf}?includeTriggers=true` | matches `workflows.private.get` (`operations.py:714-716`) | Private Skill 44 rail — registered, not a gap. |
| `.../ghl_rest_canvas.py:166` | PUT `/workflow/{loc}/trigger/{id}` | **second call** of the two-call freeze row; registry records only the first (`operations.py:672-678`, first call at `:723-725`) | **Named gap**, documented in the registry comment; Skill 44 private rail. |
| `.../ghl_rest_canvas.py:193` | POST `/funnels/funnel/create` | `funnels.create` internal, path `/funnels/` (`operations.py:574-575`) | **Named gap**, authoring rail. |
| `.../ghl_rest_canvas.py:206` | POST `/funnels/funnel/create-step` | `funnels.steps.create` internal, path `/funnels/{funnelId}/steps` (`operations.py:576-577`) | **Named gap**, authoring rail. |
| `.../ghl_rest_canvas.py:218` | GET `/funnels/funnel/fetch/{funnel_id}` | `funnels.get` internal, path `/funnels/{funnelId}` (`operations.py:578-579`) | **Named gap**, authoring rail. |
| `.../ghl_rest_canvas.py:228` | GET `/funnels/page/list?…` | `funnels.pages.list` is public `/funnels/{funnelId}/pages`; `funnels.pages.list_internal` is retired with `UNKNOWN` path (`operations.py:586-588`) | **Named gap**; the internal list route has no public equivalent. |
| `.../ghl_rest_canvas.py:240` | POST `/funnels/funnel/delete` | `funnels.delete` internal, path `/funnels/{funnelId}` (`operations.py:580-581`) | **Named gap**, authoring rail. |
| `06-ghl-install-pages/tools/ghl_funnels_read.py:138` | GET `/funnels/funnel/list` | no row | **Named gap**, authoring read. |
| `06-ghl-install-pages/tools/ghl_funnels_read.py:139` | GET `/funnels/page` | no row | **Named gap**, authoring read. |
| `06-ghl-install-pages/tools/ghl_survey_rest.py:76` | GET `/surveys/?locationId=…` on `backend.leadconnectorhq.com` | public row `surveys.list` is `services…/surveys/` (`operations.py:554-556`); the internal read has no public row | **Rail mismatch**, named gap; the public row is the replacement if the call can move to `services`. |

No retired route other than `contacts.list` is called by the scanned surfaces;
`conversations.list_legacy`, `opportunities.list_probe` and
`funnels.pages.list_internal` have no live caller in these files.
**SOURCE-VERIFIED**

Version drift outside route identity: `media.upload` is `v3` with no alternate
(`operations.py:591-593`) while Skill 06 sends `2021-07-28`
(`ghl_media.py:140, 859`); `workflows.list` is `v3` while the recorded live 200
was `2021-07-28` (F6). **SOURCE-VERIFIED / RECORDED-LIVE-EVIDENCE**

## 6. Machine check

`evidence/W18/check-v4-and-paths.py` — stdlib only, read-only, no network.

- Asserts the five V4 rows keep level `S`, Version `v4`, blocker `B-V4-S`,
  staging doc URL, write/approval flags; `v4` stays out of
  `SUPPORTED_VERSIONS`; `validation.read`/`restore` stay named gaps.
- Asserts default-deny, `enabled`+block impossible, `read_verified` required
  for reads, `canary_verified` required for writes, and that the checked-in
  record carries no V4 row and does not load for BlackCEO LLC.
- Pins the refusal path (`capability_disabled`, `refused_before_transport`,
  `write_ready`, tenant mismatch) and the four `_enabled` write guards.
- Pins the declared defect F1 at `workflow_v4.py:289` and
  `workflow_builder.py:121`; if either is fixed, the check fails and this
  evidence must be refreshed.
- Pins every consumer line cited in §4 and fails if `PublicGhlAdapter` appears
  under Skill 35, Skill 06, Skill 49 or `tools/siglaunch`.
- Re-derives the CLI route map and fails on any undeclared no-row or retired
  caller; pins the Skill 06 internal authoring gaps.

Result: **PASS — 138 checks, exit 0**. **SOURCE-VERIFIED**

## 7. Test evidence

Run in `44-convert-and-flow-operator/tools/engine`. No live call, no secret.
**SOURCE-VERIFIED**

```
$ python3 -I -m pytest tests/test_workflow_v4_disabled.py tests/test_public_capability_record.py -q
39 passed, 13 subtests passed in 0.07s

$ python3 -m pytest tests/test_public_adapter_contract.py tests/test_workflow_v4_export_roundtrip.py -q
35 passed, 46 subtests passed in 0.17s

$ python3 -I evidence/W18/check-v4-and-paths.py
RESULT: PASS - 138 checks
```

`tests/test_workflow_v4_disabled.py:137-199` is the executable statement of
§2 for the write surfaces: each V4 write returns `Status.denied`, rule
`capability_disabled`, `refused_before_transport`, and zero transport calls;
`:202-220` shows that enabling the read rows does not enable any write.
**SOURCE-VERIFIED**

## 8. Recorded live evidence boundary

These are the only live facts this unit relies on, quoted from
`GHL_UPDATES_live-ledger.md`; they were not re-observed here.
**RECORDED-LIVE-EVIDENCE**

- Tenant `Mct54Bwi1KlNouGXQcDX` resolves to "BlackCEO LLC" (ledger `:745`).
- Observed 200s (ledger `:752-759`): `locations.get` (`2021-07-28`),
  `contacts.list` (`2021-07-28`), `contacts.search` (`v3`),
  `custom_fields.list` (`v3`, 1701 rows), `pipelines.list` (`v3`, 41),
  `media.files.list?type=file` (`v3`), `workflows.list` (`2021-07-28`, 747).
- `media.files.list` without `type` returned 422 (ledger `:757`); `type` is
  required and the registry row does not encode it (ledger `:762`).
- GHL-150 bound the record to `Mct54...` and enabled six operations; W17 QC
  PASS at `920ce3fd4` (ledger `:765, :796`). That state is **not** on the
  `origin/main` used here (F3).

No workflow was activated, no message sent, and no live result is claimed in
this document beyond these recorded lines. **SOURCE-VERIFIED**

## 9. Reproduction

```
cd "/Volumes/mac mini m4/Downloads/GHL updates/worktrees/W18-v4"
python3 -I evidence/W18/check-v4-and-paths.py
cd 44-convert-and-flow-operator/tools/engine
python3 -I -m pytest tests/test_workflow_v4_disabled.py tests/test_public_capability_record.py -q
```
