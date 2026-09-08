# Skill 35 — n8n Workflow Definitions (config/n8n)

Skill 35's Google Sheet integration runs through two n8n webhooks hosted on the
BlackCEO Automations hub (`main.blackceoautomations.com`):

| Webhook | When called | Purpose |
|---------|-------------|---------|
| `social-planner-sheet-create` | ONCE, at install (INSTALL.md Step 7) | Copy the fleet template into a new client Google Sheet, grant anyone-with-the-link edit access, return the receipt `{status, deduped, sheetId, sheetUrl, sheetName, sharedWith, provisioning_key, schema_version}`. |
| `social-planner-row-append` | EVERY publish cycle (SKILL.md Media Delivery Contract step 4) | **Upsert** one keyed row per content revision and destination account into the client sheet's **Posts** tab, then derive/update the Weekly Overview summary row, then resize preview columns/rows via a real `spreadsheet.batchUpdate`. |

## Status of these files — deployable versioned contracts (F16)

The two `*.json` files here are **sanitized, importable, parameterized exports**
derived from the reviewed live workflows (Sheet Creator `INyGjT8jQ6JjrZSh`, row
append `myXde6jbIIkaG5zW`; sanitized definitions in
`run/sandbox/n8n/`). They are NOT reconstructed placeholders. A clean n8n
sandbox can import them directly; the only post-import step is selecting the
operator Google Drive/Sheets OAuth2 credentials on the credential-bearing nodes
(credential values are never committed — every node references a credential
*placeholder*, and `verify-exports.py` fails any export that carries one).

Versioned export contract:

- `schema_version: "1.1.0"` at the top level of each export, and echoed in every
  response receipt. Input schema changes bump this version; the webhook rejects
  rows declaring a different version.
- `contract` block in each export documents: live source workflow ID, webhook
  path, input schema (all required/optional fields), output receipt schema,
  idempotency contract, sharing contract and credential references.
- No literal template/folder IDs, no literal webhook hosts, no credential
  values: the template sheet ID is a **required input field**
  (`templateSheetId`) on sheet-create, and Google endpoints are parameterized
  per request.
- `verify-exports.py` (this directory) validates node types, required auth
  wiring, payload mappings, the real `updateDimensionProperties` resize, the
  absence of placeholder IDs/URLs and of committed credentials, and the
  response receipt keys. Run it after any manual edit:

```bash
python3 35-social-media-planner/config/n8n/verify-exports.py   # exit 0 = valid
```

After importing into a sandbox, export again and compare the semantic workflow
definition against these files before promoting (QC-F16).

## Sharing contract (F02 — preserve, never migrate)

The `Set Anyone Can Edit` node (Drive permission `type=anyone`, `role=writer`)
is **intentional**. A person with the planner link can edit without an
individual invitation; provisioning must create planners with this setting and
must **never** migrate existing planners to named-user-only sharing. The
sharing setting does not change GHL account ownership or weekly mini-app
identity requirements, and it does not authorize API access to another
company's data (server-side API calls stay company-bound).

## Idempotency contract (F15)

n8n alone cannot persist dedup keys durably, so the contract spans BOTH sides:

1. **Caller side (ONB/CC) owns the durable ledger.** The caller persists the
   operation (provisioning key or row key + intent) BEFORE the HTTP call and
   reconciles the receipt after (INSTALL.md Step 7 4a-bis/4c). The webhooks
   stay stateless-safe.
2. **Webhook side does a Google readback before repeating the side effect:**
   - sheet-create: Drive `files.list` for `appProperties
     skill35_provisioning_key = <company_id>::<planner_kind>` before copying.
     A crash after Google succeeded + replay returns the existing sheet with
     `deduped: true` instead of creating a second one.
   - row-append: read `Posts!A2:N`, look up `row_key =
     cycle_id::content_revision::account_id`. Existing row → `values.update`
     on exactly that row (upsert); missing row → one append. A new content
     revision (same cycle/account, new revision) touches only its own keyed
     row.
3. **Keys:** `provisioning_key = company_id::planner_kind` (unique per
   `run/contracts/sheet_registry.json`); `row_key =
   cycle_id::content_revision::account_id`; overview summary rows key on
   `OV::<cycle_id>::<content_revision>` in column U.

## Posts table schema (F23)

The Posts tab is the normalized source of truth: one row per content revision
and destination account, upserted on `row_key`. Weekly Overview is a summary
derived from the Posts rows; new summary rows carry their key in column U and
legacy overview rows are retained untouched.

`Posts` columns (A–N), `schema_version 1.1.0`:

| Column | Field | Notes |
|--------|-------|-------|
| A | `row_key` | `cycle_id::content_revision::account_id` — upsert key |
| B | `company_id` | company registry identity |
| C | `cycle_id` | weekly cycle |
| D | `content_revision` | revision within the cycle |
| E | `account_id` | GHL Social account ID |
| F | `platform` | **verbatim** label — no generic→TikTok fallback; multiple accounts per platform and unfamiliar labels get their own rows |
| G | `account_name` | display name |
| H | `format` | post format |
| I | `scheduled_local` | client-local time |
| J | `scheduled_utc` | UTC time |
| K | `state` | draft/scheduled/published/failed |
| L | `qc_state` | QC status |
| M | `preview_url` | approved preview (RAW; caller wraps IMAGE formulas in trusted preview cells) |
| N | `remote_url` | published remote URL |

Platforms with no Weekly Overview column (X, Google Business Profile,
unfamiliar labels) appear only in the Posts table — the mapping contains no
generic-platform fallback into any named column.