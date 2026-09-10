# Skill 35 — n8n Workflow Definitions (config/n8n)

> **F17 — weekly-theme trigger SUPERSEDED (social/wf10-weekly-expiry).** The
> live n8n weekly-theme workflow (`VXRfHv2UT6QbD7Sg`) — the one that reads
> Sheet1, filters a `Date To Be Published` value for today by string
> equality, and updates a theme — is a competing entry path with no client
> invitation step and no durable state. It is SUPERSEDED by the durable
> cycle service (ONB `shared-utils/social_cycle_service.py` + the Command
> Center's `cc-cycle-service` node-cron engine). IF that trigger is retained
> at all, it must be pointed at the VERSIONED schema (`schema_version` ≥
> 1.1.0, company/week keys per `run/contracts/sheet_registry.json`) and must
> use LOCAL WEEK boundaries computed in the client's timezone — never string
> equality with today. Disabling the live trigger is a DEPLOYMENT-PHASE step:
> prove the replacement first (exactly one active `cc-cycle-service`
> engine-ownership row per company; verify via
> `register-weekly-cron.sh --verify`), then disable the n8n trigger. The
> handover procedure is documented in `35-social-media-planner/INSTALL.md`
> (Step 9, "Deployment-phase handover").

Skill 35's Google Sheet integration runs through two n8n webhooks hosted on the
BlackCEO Automations hub (`main.blackceoautomations.com`):

| Logical webhook name | When called | Purpose |
|---------|-------------|---------|
| `social-planner-sheet-create` | ONCE, at install (INSTALL.md Step 7) | Copy the fleet template into a new client Google Sheet, apply the requested sharing policy (public by default; explicit private mode supported), return the receipt `{status, deduped, sheetId, sheetUrl, sheetName, sharedWith, provisioning_key, schema_version}`. |
| `social-planner-row-append` | EVERY publish cycle (SKILL.md Media Delivery Contract step 4) | **Upsert** one keyed row per content revision and destination account into the client sheet's **Posts** tab, then derive/update the Weekly Overview summary row, then resize preview columns/rows via a real `spreadsheet.batchUpdate`. |

The table names are logical contracts, not complete deployment URLs. Use the deployment's verified active webhook path and authentication. The current versioned routes are `/webhook/social-planner/v1.1.0/social-planner-sheet-create` and `/webhook/social-planner/v1.1.0/social-planner-row-append`; the compiler applies the configured prefix. Unversioned paths are legacy compatibility routes, not substitutes for the modern contract.

## Status of these files — deployable versioned contracts (F16)

The two JSON files are credential-free source contracts. Their extra `contract`,
`schema_version`, and `meta` fields are repository documentation, not API input.
Use `prepare-import.py` to produce API-ready payloads and bind actual n8n
credential references. Never hand-edit a production graph to make an export
importable. Google credential secrets are never stored in the source or output.

```bash
python3 35-social-media-planner/config/n8n/prepare-import.py \
  --credentials-map /secure/operator/n8n-credential-refs.json \
  --output-dir /secure/operator/social-import-new \
  --webhook-prefix isolated-acceptance
```

The credential file maps `googleDriveOAuth2Api` and `googleSheetsOAuth2Api` to
`{"id":"existing-n8n-id","name":"existing-n8n-name"}`. These are references to
already configured credentials, not access tokens. The output directory must
be new; the compiler refuses to overwrite deployment snapshots. Omit the
sandbox prefix only for an approved production cutover. Verify both credential
classes can access the isolated copied sheet before activating client work.

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

## Sharing contract (F02 — preserve the selected policy)

Provisioning defaults to the existing public compatibility policy: Drive
`type=anyone`, `role=writer`. Existing public planners must not be silently
converted to named-user-only sharing.

An explicit `sharing: "private"` request instead requires `clientEmail` and
uses a named-user writer grant. The workflow records the sticky Drive
appProperty `skill35_sharing=private`; retries and ready replays preserve that
policy even if a later request omits `sharing`. They must never widen a private
sheet to anyone-with-link or domain access to recover a failed operation.
The client opens a private sheet while signed into the granted Google account;
Google writes and readback use the deployment's authorized Google connection.

After permission writes, the workflow reads actual Drive permissions before
reporting success. Private-mode verification rejects public/domain grants,
a missing owner, a mismatched client or an unconfirmed writer grant. Surface a
repair when the intended policy cannot be verified; do not claim success from
an accepted permission request alone. Sharing policy does not change GHL
account ownership or weekly mini-app identity requirements, and server-side
API calls remain company-bound.

## Idempotency contract (F15)

n8n alone cannot persist dedup keys durably, so the contract spans BOTH sides:

1. **Caller side (ONB/CC) owns the durable ledger.** The caller persists the
   operation (provisioning key or row key + intent) BEFORE the HTTP call and
   reconciles the receipt after (INSTALL.md Step 7 4a-bis/4c). The webhooks
   stay stateless-safe.
2. **Webhook side does a Google readback before repeating the side effect:**
   - sheet-create: Drive `files.list` for `appProperties
     skill35_provisioning_key = <company_id>::<planner_kind>` before copying.
     `files.copy` stamps company ownership, the provisioning key and an
     `initializing` state in the same Google request. The copy explicitly goes
     to the operator's root. Initialization removes template-only content and
     provisions the required five tabs. After formatting/sizing succeeds, a
     durable `formatted` checkpoint is written BEFORE sharing. A retry at that
     checkpoint verifies structure and repairs sharing without clearing cells.
     Only then is the sheet marked `ready`. Ready replay verifies ownership,
     required tabs/headers and current sharing; it preserves client notes and
     dimensions. Every replay returns the same artifact with `deduped: true`.
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

## Append-failure repair states (F14)

Before ANY write, the append verifies the sheet's metadata with the SAME
`googleSheetsOAuth2Api` credential the write uses (and sheet-create verifies the
template with the same Drive credential the copy uses). Failures classify into
DISTINCT actionable repair states, never a silent replacement sheet:

| HTTP | `repair_state` | Repair semantics |
|------|----------------|------------------|
| 404 | `sheet_not_found` / `template_not_found` | Identity repair: correct the registered sheet/template ID in the company registry. A replacement sheet is NEVER created silently. |
| 403 | `sheet_access_denied` / `template_access_denied` | Access repair: re-grant the operator credential access to the EXISTING sheet. |
| other | `transient` | Bounded retries (3x, 2s backoff) already applied; the caller keeps the row pending and replays on the next cycle. |

Repair receipts answer HTTP 424 with `{success:false, repair_required:true,
repair_state, repair_action, sheetId}` — the caller surfaces this as a visible
repair task (INSTALL.md Step 7 4d-ter). Once verified access is restored, the
F15 idempotency ledger replays each pending keyed row exactly once: the
readback upsert updates the existing keyed row in place and never duplicates
it, so history is retained.

## Asset manifest + trusted IMAGE formulas (F24)

The row-append persists an asset manifest row per asset (upsert on `asset_key`
in the Images tab): content id, asset id, company, cycle, revision, kind,
stable HTTPS preview URL, full-resolution URL, ratio, dimensions and alt text
— all RAW values. The trusted `=IMAGE("https://…",1)` formula is generated
ONLY for URLs that pass validation (https, no quotes/control chars,
Sheets-fetchable permanent CDN — not private Drive page links, not
soon-expiring URLs) and written ONLY into the Images tab's designated preview
column (P). Posts keeps `preview_url` RAW (F26). Invalid URLs refuse into a
visible repair state (`asset_url_not_https` / `asset_url_unsafe_chars` /
`asset_url_not_fetchable` / `asset_missing_url`) without pretending that asset succeeded. A healthy Posts record may already
be saved; the receipt reports partial work and required asset repair. The
batchUpdate resizes the Images preview column to 220px and the asset row to
275px (SPEC gallery contract).

## Readability + status colors (F25)

Provisioning (sheet-create) applies the `sheet-template.schema.json`
contract as one `spreadsheet.batchUpdate`: TEXT_EQ conditional format rules
(NEVER NUMBER_EQ for text statuses), `setDataValidation` ONE_OF_LIST dropdowns
over the same status list, frozen header rows (Posts also freezes its first
two columns), wrapped copy, a protected Images formula column, and the compact
**This Week** view (~8 client-facing columns: Week, Client, Next Action,
Drafting, QC, Scheduled, Published, Needs Attention). Every status value
(`Complete`, `Failed`, `QC Review`, `Scheduled`, `Published`,
`Needs Attention`) carries BOTH a color and a written label. Re-running the
provisioner/upsert never resets client-changed row sizes or notes.
`config/validate-sheet-format.py` validates the contract + export wiring;
`config/sheet-template.schema.json` is the versioned template contract;
`scripts/migrate-template.py` migrates existing sheets (dry-run default,
backup before `--apply`).

## Video evidence + Watch video links (F38)

Video assets write a Videos-tab row: trusted poster `=IMAGE`, duration, ratio,
version, QC state, captions flag, and a clearly labeled **Watch video**
HYPERLINK to the client-bound Command Center player route
(`/social/media/{assetId}`) — a visible poster plus a real playback
destination, never a promised native in-sheet MP4 player. The PUBLISHED
destination URL is written separately only after posting; a YouTube destination remains a normal separately stored URL; a valid
HYPERLINK is never corrupted by appending a smart-chip hint to its formula. Client drafts
are NEVER uploaded to public YouTube to manufacture a preview. Preview access
is a short-lived signed token bound to company + asset (CC route); expired
access renews by re-fetching while authenticated.
## Existing planners and safe cutover

The append flow requires exactly one Sheets developerMetadata entry named
`skill35_company_id` equal to the canonical caller company. New create flows
also stamp `skill35_planner_kind` and `skill35_template_schema=1.2.0` into
Sheets metadata and Drive appProperties. A matching Drive provisioning key
alone is not sufficient ownership evidence.

Use `compat/README.md` and its compiler to deploy all five credential-bound
workflows. The public router preserves exact legacy document requests under the
operator’s intentional anyone-with-link edit policy. It verifies the actual
Google permission and headers before a fixed RAW Overview write. It does not
claim tenant ownership or publication. Any modern fields select the strict
workflow; a strict failure never falls back to legacy.

Before upgrading an existing client to the strict per-account flow, enumerate its
verified company registry bindings. For each existing sheet: read its ID and
owner from that registry, verify the same Google credentials can read it,
back up values/notes/format metadata, compare the required headers, and stamp
ownership only when all evidence agrees. Do not infer ownership from an
incoming webhook body or create a replacement for an inaccessible sheet.
Missing headers need a preserving structural migration; never run the new-copy
initializer or clear legitimate historical rows. If ownership is ambiguous,
keep that client on the previous compatible route, expose a repair task, and
continue unrelated healthy work. The compatibility router can keep verified public legacy document writes working
while those client upgrades are prepared; this inventory is not a prerequisite
for restoring the legacy public-document service.

The caller must hold a durable lock around the entire readback/write/receipt
operation. Google serializes individual writes, not a read-then-write sequence
across concurrent n8n executions. Copy/append requests have no blind HTTP retry;
a timeout requires readback under the same lock. Fixed-range updates may retry.

Do not declare the program complete from unit tests or an active workflow flag.
Capture the active published graph, actual sandbox execution and Google
readback; bind that proof to the released source and use
`scripts/social-completion-audit.py`. See `docs/social-completion-evidence.md`.


New copies enable the Sheets `importFunctionsExternalUrlAccessAllowed` property
while it is false so trusted IMAGE previews can actually render. A written
formula alone is insufficient proof: acceptance reads effective cell values and
rejects image errors. This Week summaries use whole-column references so Google
row insertion cannot move the counts below newly appended content. See the
[Google Sheets property contract](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets#spreadsheetproperties).
