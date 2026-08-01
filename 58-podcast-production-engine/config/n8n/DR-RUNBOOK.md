# Disaster Recovery Runbook -- n8n Podcast Publish Rail

Last updated: 2026-08-01
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
