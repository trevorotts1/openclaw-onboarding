# Disaster Recovery Runbook -- n8n Podcast Publish Rail

Last updated: 2026-08-04
Workflows exported from: main.blackceoautomations.com

## Restore Procedure

1. **Credentials first.** Restore n8n credential records in the target instance BEFORE importing workflows. Each credential must exist by name exactly as listed in the Credential Inventory below. Credential IDs will differ between instances; the import step rebinds name-matched references.

2. **Workflow import.** Import the four workflow JSON files in this order:
   - `podcast-standing-check.workflow.json`
   - `podcast-draft-cleanup.workflow.json`
   - `podcast-draft-test.workflow.json`
   - `podbean-publish.workflow.json`

3. **Rebind webhook credentials.** After import, open each workflow and confirm that the "Podcast Publish Gate (restored 2026-08-01)" header-auth credential is mapped to the matching Credential record in the target instance. All four workflows share this webhook credential.

4. **Activate.** Toggle each workflow Active. Activation order does not matter, but the publish rail will not accept requests until all gates are active.

## Credential Inventory

| Credential Name | n8n Credential Type | Purpose |
|---|---|---|
| Podcast Publish Gate (restored 2026-08-01) | Header Auth | Shared webhook auth for all four workflows. The caller must send the matching header. |
| Podbean BlackCEO (client_credentials) | HTTP Basic Auth | Podbean API OAuth token endpoint. Used by publish, draft-test, and draft-cleanup workflows. |
| trevor@blackceo.com | Gmail OAuth2 | Sends success and failure notification emails from the publish workflow. |
| fleetStandingCheck Header Auth | Header Auth | Authenticates outbound HTTP calls from publish and standing-check workflows to the fleet standing webhook. |

## Required Data Tables

These n8n-native data tables must exist and contain the expected schema. Restore them from n8n data table exports or recreate manually.

| Table Name | n8n Data Table ID | Purpose |
|---|---|---|
| podcast_publish_roster | UWjpksxU2b6TjKow | Client roster with email-based standing and identity lookup. Referenced by the Standing Gate in publish, standing-check, and draft-test workflows. |
| podcast_publish_ledger | 3anOzegbKtLcgVud | Idempotency and audit ledger. Every publish attempt is tracked here with status (received, in_flight, completed, failed, refused). Referenced by publish and standing-check workflows. |
| fleet_standing | aoLFsegM1aDIrcDj | Fleet standing lookup table for the Fleet Standing Gate. Referenced by publish and standing-check workflows. |

## Known Live-vs-Export Drift

- The exported workflows are sanitized: credential values are replaced with `{id, name}` references only. Restoration requires re-creating credential records in the target n8n instance by hand.
- `staticData` and `pinData` are stripped. If pinData was used for cached values (auth tokens, lookup results), the first execution after restore will repopulate it automatically.
- Node names in the exported JSON use double-hyphen (` -- `) instead of em dashes found in the live instance. This is a cosmetic-only difference and does not affect execution.
- The `dataTableId` references use id-mode values (e.g. `3anOzegbKtLcgVud`). These are instance-specific and must be updated if the target instance generates different IDs for the same data tables.
- The publish workflow (`podbean-publish.workflow.json`) was exported from an active live deployment on 2026-08-01 and is the authoritative export. The standing-check, draft-test, and draft-cleanup workflows were exported from the same instance on the same date. The stale pre-audit export is preserved as `podbean-publish.workflow.legacy-2026-07.json` (51 nodes) and must not be imported; it predates the idempotency ledger, standing gate, and media preflight added to the live workflow.

### 2.5 Legacy ungated workflow deactivation (COfgxe6HXRcWOleV)

The legacy workflow `COfgxe6HXRcWOleV` ("Podbean Channel IDs to Google Doc") is **NOT part of this config/n8n set** and must never be restored from here. It carries its own independent, ungated Podbean publish chain (OAuth → upload → `Publish Episode`) that bypasses the roster check, entry guard, and media preflight entirely — an empty-audio/empty-image episode can be created through it. It is **NEVER-PRINT** (holds plaintext Podbean OAuth credentials; see the config/n8n/README.md "Canonical publish path" section for the full ruling record `GK-D4`/`D19` and the `K6-U74-r2` operator-gated disposition). Verified live 2026-08-04: it is **deactivated (`active: false`)** on main.blackceoautomations.com, which blocks production-mode Execute-Workflow calls but NOT manual/chat-mode reachability. **Deactivation is an operator-live action and must be re-verified before any DR drill:** a human clicking "Execute workflow" in the n8n UI, or any chat-triggered execution, can still fire the ungated publish chain. Do not import, do not read its node contents, do not print its credential values.

### 2.6 Drift re-sync (MULTIROW + FIX-RESCUE-19) — 2026-08-04

The repo export now carries the two functional node drifts that landed live on 2026-08-03 and were absent from the 2026-08-01 export:

1. **DRIFT-1 — Standing Gate MULTIROW (two-show fleet model):** the `Standing Gate  --  Determine Verdict` node now selects the roster row whose `podbean_channel_id` equals the payload `podcast_id` (channel-preferred), falling back to the first last-name row only when the payload carries no `podcast_id`. A DR restore that previously took `matched[0]` could pick the wrong row for a client with two shows.
2. **DRIFT-2 — Fleet Gate FIX-RESCUE-19 denylist:** the `Fleet Gate  --  Resolve Identity + Verdict` node now carries the shared identity placeholder denylist (`'', 'tbd', 'n/a', 'na', 'none', 'unknown', 'null', '-', '?', 'tba'`), whitespace collapse, and the `fleet_roster_rows` diagnostic. A placeholder identifier can no longer function as a real identity.

These were applied to the repo export from a live API read of `TkL0rn2SH3q32SeB` (59 nodes, active) on 2026-08-04; the export keeps its double-hyphen node-name format (see the cosmetic drift note above) — the functional graph now matches live. A DR restore from this file carries both drifts.

### 2.7 Stale pinData (contract-v2 re-pin — operator-live)

The repo export carries **no pinData** (stripped during sanitization), so there is nothing stale to strip here. **The LIVE workflow's pinned webhook payload is stale** — it predates the contract-v2 guard (missing `contract_version: "2"` and `idempotency_key`) and would be REFUSED by the current guard. This is an operator-live action: re-pin the webhook node on the live workflow with a contract-v2 fixture containing a real `description` and a valid `idempotency_key`, or delete the pin entirely. This repo file needs no change for that.
