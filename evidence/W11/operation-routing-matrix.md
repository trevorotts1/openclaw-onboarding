# GHL-110 — operation-routing matrix (community MCP → supported routes)

Source revision: `bcd3efbd2372acac891d7d8464958d2f3deaaecc` (`ghlupd/integration`).
Frozen registry: `44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py`
(GU-004, fetched 2026-10-18). Alias map: `.../public/aliases.py` (GU-004 §4).
Machine manifest: `evidence/W11/operation-routing-manifest.json`.
Gate: `python3 -I evidence/W11/test_operation_routing_matrix.py`.

Every replacement below is an operation id in the frozen registry with its own
`Version` literal. There is no global version header and no prefix fallback in
the public adapter: `public/transport.py` strips caller-supplied `Version` and
sends only the row literal. The legacy CLI (`utils/ghl_client.py`) still carries
a prefix map; divergences are listed at the end and were **not** changed.

## Before → after

| | Before (retired) | After (supported) |
|---|---|---|
| Tier 0 | Skill 44 `caf` | Skill 44 `caf` — unchanged |
| Tier 1 | Official MCP (`ghl-mcp`) | Official MCP — four documented tools: `list_locations`, `search_operations`, `describe_operation`, `execute_operation` |
| Tier 2 | Community MCP `ghl-community-mcp`, loopback `127.0.0.1:8765`, profile `curated` (43 crm tools), JSON-RPC `tools/call` / `POST /execute` | **Unassigned. Not a route.** No registration, no unit, no listener, no `GHL_COMMUNITY_MCP_URL` |
| Tier 3 | Raw REST | Public REST through `PublicGhlAdapter`, one Version per operation row (in-tree wiring today: `utils/workflow_builder.py`; the CLI command groups still use the legacy client — see divergences) |
| Tier 4 | Browser | Browser — Skill 06 authoring only (forms, surveys, funnels, pages, communities, courses, channels) |

## Caller matrix — one row per former caller

`Version` is the frozen row literal; `(alt …)` is the only permitted rollback
literal. “Fallback” answers whether Skill 44 / Skill 06 orchestration remains a
required path, and why.

| ID | Former caller (file:line) | Operation performed | Replacement (operation id — METHOD path) | Version header | Skill 44/06 required fallback? | Why |
|---|---|---|---|---|---|---|
| C01 | `29-ghl-convert-and-flow/CORE_UPDATES.md:26` | Tier 2 rung: any community tool | Route policy: Tier 0 `caf` → Tier 1 official MCP → Tier 3 public REST; Tier 2 removed | Per operation; no global default | **44 + 06 required** | Skill 44 is the only verified workflow authoring path (internal Build API); Skill 06 is the only create path for forms/surveys/funnels/communities/courses/channels |
| C02 | `35-social-media-planner/INSTRUCTIONS.md:353-354` | `get_social_accounts` over `$GHL_COMMUNITY_MCP_URL` + JSON-RPC `tools/call` | `social.accounts.list` — GET `/social-media-posting/{locationId}/accounts` | `2021-07-28` (alt `v3`) | No | One documented public read replaces the smoke test; `caf social accounts` is preferred Tier 0, not required |
| C03 | `35-social-media-planner/INSTALL.md:276` | Same connection/smoke read | `social.accounts.list` — GET `/social-media-posting/{locationId}/accounts` | `2021-07-28` (alt `v3`) | No | The public read is the scored access check |
| C04 | `35-social-media-planner/references/playbook.md:1751,1757` | Former Tier 2 rung: `create_social_post`, `get_social_accounts`, JSON-RPC `tools/call` | `social.posts.create` — POST `/social-media-posting/{locationId}/posts`; `social.accounts.list` — GET `/social-media-posting/{locationId}/accounts` | `2021-07-28` (alt `v3`) | No (44 preferred) | `caf social create-post` stays Tier 0 when present; public REST and the official MCP tool cover it without `caf` |
| C05 | `docs/CONTENT-CONVERSATION-LATTICE.md:35` | Documented 6-tier ladder placing `create_social_post` at Tier 2 | `social.posts.create` — POST `/social-media-posting/{locationId}/posts` | `2021-07-28` (alt `v3`) | No (44 preferred) | Ladder must skip Tier 2: `caf` → official MCP `social-media-posting_create-post` → public REST |
| C06 | `35-social-media-planner/CORE_UPDATES.md:9,27` | Retired tool set: `create_social_post`, `update_social_post`, `bulk_delete_social_posts`, `upload_media_file`, `bulk_update_media_files`, `create_email_template`, `view_email_center`, `view_campaign_stats` | `social.posts.create`; `media.upload` — POST `/medias/upload-file`; official MCP `search_operations`; **capability gaps** for update/bulk/view/stats tools | `2021-07-28` social; `v3` media; none for official MCP | No (44 preferred) | Update/bulk/view/stats have no audited row; discover with official MCP or report the gap — never revive Tier 2 |
| C07 | `36-ghl-mcp-setup/EXAMPLES.md:187` | `ghl_list_products` via POST `$GHL_COMMUNITY_MCP_URL/execute` | `products.list` — GET `/products/` | `v3` (alt `2021-07-28`) | No (44 preferred) | Public REST read stands alone; `caf` is Tier 0 |
| C08 | `36-ghl-mcp-setup/EXAMPLES.md:196` | `list_invoice_schedules` via `/execute` | Official MCP `search_operations`; **capability gap** for list/get/update schedules | none (official MCP row) | No | Only `invoices.schedules.create` is audited; no contract exists for the lists |
| C09 | `36-ghl-mcp-setup/EXAMPLES.md:237` | `ghl_create_product` + `ghl_create_price` via `/execute` | `products.create` — POST `/products/`; `products.prices.create` — POST `/products/{productId}/price` | `v3` (alt `2021-07-28`) | No (44 preferred) | Both are approval-gated public writes (`B-PRODUCT-422`, `B-PRICE-KEY`) |
| C10 | `36-ghl-mcp-setup/EXAMPLES.md:270` | `create_invoice` + `send_invoice` via `/execute` | `invoices.create` — POST `/invoices/`; `invoices.send` — POST `/invoices/{invoiceId}/send` | `v3` (alt `2021-07-28`) | No | Approval-gated; `invoices.create` has readback plan `invoices.get` |
| C11 | `36-ghl-mcp-setup/EXAMPLES.md:278` | Tool discovery: GET `$GHL_COMMUNITY_MCP_URL/tools` | Official MCP `search_operations` | none (official MCP row) | No | The documented catalog is four tools; counts from the retired endpoint are not an interface |
| C12 | `36-ghl-mcp-setup/EXAMPLES.md:318` | `get_webhook_logs` via `/execute` | Official MCP `search_operations`; **capability gap** | none (official MCP row) | No | No webhook-log operation row exists; report the gap |
| C13 | `06-ghl-install-pages/tools/ghl_object_router.py:104` (product/media routes at 369-402) | Community-MCP-first product create/read and media upload fallback | `products.list` GET `/products/`; `products.create` POST `/products/`; `media.upload` POST `/medias/upload-file`; `media.folders.create` POST `/medias/folder`; `media.files.list` GET `/medias/files` | `v3` | **06 + 44 required** | Skill 06 remains required for browser-only authoring (forms, surveys, funnels/pages, communities, courses, channels); Skill 44 remains the workflow build rail |
| C14 | `config/ghl-mcp-pin.env:135,144` | Smoke tool `crm_list_workspaces`; loopback port `8765` for the retired service | Official MCP `list_locations` | none (official MCP row) | No | The pin is a rollback reference; required end state is absence. Skill 36 retirement checks own disposition |
| C15 | `README.md:294` | Skill index still advertises a 5-tier chain with Community MCP (588 tools) and `$GHL_COMMUNITY_MCP_URL` | Route policy: official MCP (four tools) → public REST → browser; community tier absent | Per operation | **44 + 06 required** | Stale description must match retirement; authoring fallbacks unchanged |
| C16 | `ONBOARDING-TRIGGERS.md:68` | Trigger text advertises Community MCP on port 8765 and a launchd/systemd server | Same route policy | Per operation | **44 + 06 required** | Same stale-claim correction; no service to supervise |
| C17 | `44-convert-and-flow-operator/tools/siglaunch/provisioning/provisioning.py:29-36` | Signature-funnel Phase-A catalog: list/create tags, custom fields, products through injected `Catalog` | `tags.list` GET `/locations/{locationId}/tags`; `tags.create` POST `/locations/{locationId}/tags`; `custom_fields.list` GET `/locations/{locationId}/customFields`; `custom_fields.create` POST `/locations/{locationId}/customFields`; `products.list` GET `/products/`; `products.create` POST `/products/` | `v3` | **44 + 06 required** | Skill 44 owns launch engine + workflow build; Skill 06 owns downstream form/survey/funnel authoring. **No production Catalog binding exists in this tree** — protocol is injected; binding to `PublicGhlAdapter` is the remaining gap |
| C18 | `tests/fixtures/ghl_compat/aliases.json:110,137-140` | Machine fixture of community tool → operation ids | `products.list`; `workflows.list` GET `/workflows/`; `workflows.enroll` POST `/contacts/{contactId}/workflow/{workflowId}` | `v3` | **44 required** | `ghl_get_workflow` / `ghl_publish_workflow` map to `v4` staging rows; production fallback is Skill 44 private `workflows.private.get` / `workflows.private.publish` (Version `2021-07-28`), never staging |

### Historical catalog references (not live callers)

| ID | Reference (file:line) | Former operation | Replacement | Version header | Skill 44/06 required fallback? | Why |
|---|---|---|---|---|---|---|
| D01 | `36-ghl-mcp-setup/ghl-mcp-setup-full.md:983,986,1025,1026` | Catalog: `create_opportunity`, `get_forms`, `get_form_submissions`, `ghl_get_surveys`, `ghl_trigger_workflow`, `ghl_publish_workflow` | `opportunities.create` POST `/opportunities/`; `opportunities.search` GET `/opportunities/search`; `pipelines.list` GET `/opportunities/pipelines`; `forms.list` GET `/forms/`; `forms.submissions.list` GET `/forms/submissions`; `surveys.list` GET `/surveys/`; `surveys.submissions.list` GET `/surveys/submissions`; `workflows.enroll` POST `/contacts/{contactId}/workflow/{workflowId}` | `v3` | **06 + 44 required** | Forms, surveys and funnel authoring have no public create API; workflow build/edit is Skill 44 only |
| D02 | `36-ghl-mcp-setup/GHL-LOOKUP-SOP.md:239-240` | `ghl_create_workflow`, `ghl_update_workflow_actions` (undocumented internal wrapper) | **Capability gap** for authoring; `workflows.list` GET `/workflows/` for reads | `v4` is staging-only; list is `v3` | **44 required** | Skill 44 internal Build API is the only verified programmatic workflow build path |

### Domain coverage

| Domain | Former rail evidence | Supported reads/writes (method + path, Version) | Required fallback |
|---|---|---|---|
| Social Planner accounts/posts | C02–C06 | `GET /social-media-posting/{locationId}/accounts`, `POST /social-media-posting/{locationId}/posts`, `POST .../posts/list`, `GET/DELETE .../posts/{id}` — `2021-07-28` (alt `v3`); `POST /social-media-posting/statistics` — `v3` | No; `caf` preferred |
| Products / prices | C07, C09, C13, C17 | `GET/POST /products/`, `GET/PUT/DELETE /products/{productId}`, `GET/POST /products/{productId}/price` — `v3` (alt `2021-07-28`) | No |
| Media | C06, C13 | `POST /medias/upload-file`, `POST /medias/folder`, `GET /medias/files` — `v3` | No; Skill 06 never routes media through the browser |
| Forms | D01, C13 | `GET /forms/`, `GET /forms/submissions` — `v3` | **Yes — Skill 06** browser builder: no public create API (`forms.update` is undocumented, `B-NO-CONTRACT`) |
| Surveys | D01, C13 | `GET /surveys/`, `GET /surveys/submissions` — `v3`; `surveys.get`/`surveys.write` are internal/browser (`B-INTERNAL`/`B-NO-CONTRACT`) | **Yes — Skill 06** browser builder |
| Opportunities / pipelines | D01 | `GET /opportunities/search`, `GET/POST /opportunities/`, `PUT /opportunities/{id}`, `PUT /opportunities/{id}/status`, `GET /opportunities/pipelines` — `v3` | No |
| Workflows | C18, D02 | `GET /workflows/`, `POST/DELETE /contacts/{contactId}/workflow/{workflowId}` — `v3` | **Yes — Skill 44** internal Build API for create/edit. `workflows.definition.*` are `v4` staging-only (`B-V4-S`) and are not production operations |
| Signature funnel consumers | C17 | `caf` (Tier 0) + the public rows above; `CafExecutor` drives `caf workflows build/list/export` | **Yes — 44 + 06**; production `Catalog` binding absent |

## Explicit gaps and staging warnings

- **Capability gaps** (no audited row; do not invent, do not route to the retired rail):
  `update_social_post`, `bulk_delete_social_posts`, `bulk_update_media_files`,
  `view_email_center`, `view_campaign_stats`, `list_invoice_schedules`,
  `get_invoice_schedule`, `update_invoice_schedule`, `get_webhook_logs`,
  `ghl_create_product_collection`, `ghl_list_product_collections`,
  `ghl_list_inventory`, `ghl_bulk_edit_products`, `ghl_create_workflow`,
  `ghl_update_workflow_actions`.
- **Staging-only, never production:** `workflows.definition.read`,
  `workflows.definition.create`, `workflows.definition.update`,
  `workflows.status.publish`, `workflows.definition.delete` — Version `v4`,
  level `S`, blocker `B-V4-S`, staging marketplace docs. The alias fixture
  records the private Skill 44 fallback for the read/publish pair.
- **Official MCP rows carry no `Version` header** (registry `version=None`).
  The `/mcp/` transport examples in Skill 36 send `Version: 2021-07-28` at the
  HTTP layer, but no per-operation version is recorded. Do not invent one.

## Version-header divergences (recorded, not changed)

The legacy CLI (`utils/ghl_client.py`) still resolves some headers from a prefix
map. The frozen registry is authoritative for the public adapter; these
divergences are named so they are not mistaken for parity:

| Operation family | Registry row | Legacy CLI prefix map | Disposition |
|---|---|---|---|
| `products.*` | `v3` (alt `2021-07-28`) | `2021-07-28` | Permitted alternate — no change |
| `invoices.*`, `payments.*`, `orders.*`, `transactions.*`, `subscriptions.*`, `coupons.*`, `estimates.*` | `v3` (alt `2021-07-28`) | `2021-07-28` | Permitted alternate — no change |
| `forms.list`, `forms.submissions.list` | `v3` | `2021-07-28` | Divergence — left unchanged (no global sweep) |
| `surveys.list`, `surveys.submissions.list` | `v3` | `2021-07-28` (default) | Divergence — left unchanged |
| `media.*` | `v3` | `2021-07-28` (default) | Divergence — left unchanged |
| `workflows.list` | `v3` | `2021-07-28` | Divergence — left unchanged |
| `opportunities.search` | `v3` | `2021-07-28` (deliberately absent from overrides) | Documented as version-coupled/unverified in `ghl_client.py` |
| `social.*` | `2021-07-28` (alt `v3`) | `2021-07-28` | Match |

## Machine check

`evidence/W11/test_operation_routing_matrix.py` scans the tree for the retired
rail (`GHL_COMMUNITY_MCP_URL`, `ghl-community-mcp`, `crm_list_workspaces`,
`tools/call`, standalone `8765`), requires every matching file to be classified,
requires every caller line to be declared or explicitly exempted as a retirement
guard, and validates every replacement against the frozen registry — including a
hard refusal to accept a `v4`/staging row as a production replacement.

Current result:

```
RESULT: PASS — 18 former callers and 2 domain references all carry a mapped
replacement; 60 files classified.
```

Non-caller retired-rail references are enumerated, with a reason each, in
`operation-routing-manifest.json` → `files` (retirement guards, retirement docs,
historical catalogs, changelogs, deny lists, mapping tables).
