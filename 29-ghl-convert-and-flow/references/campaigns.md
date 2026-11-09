# Campaigns and workflows — public read, beta definition, fallback

> Scope: the campaigns module and the workflow family. Workflow definition semantics live in `workflows.md`; logs in `workflow-monitoring.md`.

## Campaigns

`GET /campaigns/` is a location-scoped read (registry: `campaigns` family, `campaigns.readonly`). Contact-to-campaign membership changes are not campaign authoring. Do not build a campaign object by inventing fields.

Minimal synthetic request:

```bash
curl --request GET 'https://services.leadconnectorhq.com/campaigns/?locationId=SYNTHETIC_LOCATION' \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" -H 'Version: 2021-07-28'
```

Failure: missing `locationId` → refuse locally. Readback: `total` + returned campaign ids.

## Workflows — the accurate boundary

| Operation | Version | Classification |
|---|---|---|
| `workflows.list` (`GET /workflows/`) | `v3` | implemented |
| `workflows.enroll` / `workflows.remove` | `v3` | implemented; writes |
| `workflows.definition.read/create/update/delete` | `v4` | beta-gated (`B-V4-S`) |
| `workflows.status.publish` | `v4` | beta-gated |
| `workflows.private.*` | `2021-07-28` | internal-only |

The old statement "workflows are GET-only" is withdrawn. Definition authoring is a real but **beta/staging** contract; it is not production-available merely because the row exists. `POST /workflows/search` is a read and validation is non-persisting but consumes write quota.

Enrollment is a contact mutation, not workflow authoring:

```bash
curl --request POST 'https://services.leadconnectorhq.com/contacts/SYNTHETIC_CONTACT/workflow/SYNTHETIC_WORKFLOW?locationId=SYNTHETIC_LOCATION' \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" -H 'Version: v3' \
  -H 'Content-Type: application/json' --data '{"eventStartTime":"2026-12-01T12:00:00Z"}'
```

Documented response carries `succeeded` and a misspelled `succeded`. Treat either as transport acceptance, not enrollment proof; re-read enrollment state. No idempotency key is documented.

Failure: removal without approval → refuse; removal ends in-flight progress. Ambiguous enrollment response → reconcile by read, never repeat blindly.

## Folder behavior (internal, not public)

Neither internal nor public listing proves folder identity. A rebuild derives `parentId` from an existing workflow when possible and records that it cannot prove folder uniqueness. Check the UI and pass an explicit folder id.

## Fallback decision

1. Public row implemented → use it.
2. Public definition row beta-gated and beta unavailable → approved internal Firebase path with the same tenant/intent; record `beta_not_enabled`.
3. Internal token unread/misconfigured → managed Tier-4 builder.
4. Token genuinely dead → authorized Tier-2 self-heal; Tier 4 cannot seed without a token.
5. Ambiguous write → reconcile; never re-issue on a second rail.
