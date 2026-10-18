# GHL Campaigns + Workflows API Reference

> **Scope of this file:** Campaigns module (campaign triggers) and Workflows module (automation workflows).
> Base URL: `https://services.leadconnectorhq.com`
> Auth: `Authorization: Bearer $GOHIGHLEVEL_API_KEY` — the LOCATION PIT from `~/.openclaw/secrets/.env`. In the cURL templates below, substitute `$GOHIGHLEVEL_API_KEY` for `<PRIVATE_INTEGRATION_TOKEN>` and use double quotes so it expands. See SKILL.md "Credentials" for the fail-loud resolver.
> Version header: **per operation**. Workflow list, contact enrollment and removal are documented at `v3`; campaign operations keep their documented dated version. Never send one value for every call — see `references/api-generations.md`.
>
> **Version is per-OPERATION, and FIVE versions are supported concurrently** — `v3`
> (June 11, 2026), `2023-02-21`, `2021-07-28`, `2021-04-15` and `legacy`, every one
> "Supported until: **TBD**". An older supported version is NOT a defect; only a blanket
> "one value for everything" rule is.
> `2021-07-28` is the pre-v3 default (32 of 41 specs exclusively, 33 accept it). The ONLY
> apps on `2021-04-15` are: agent-studio, calendars, conversation-ai, conversations,
> knowledge-base, saas-api, voice-ai. `links` accepts both; `store` declares none.
> Full rule + v3 capability: `references/api-generations.md`.
> Sources: `https://marketplace.gohighlevel.com/docs/Versioning/` and the per-app specs
> (verified 2026-08-03). ⚠ The spec repo lags the live docs — check the docs site first.

---

### Module: campaigns

#### GET /campaigns/ - Get Campaigns
- Description: Get Campaigns
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: campaigns.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None 
> Version UNVERIFIED for this operation - read the operation page before use: https://marketplace.gohighlevel.com/docs/ghl/campaigns/
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/campaigns/
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/campaigns/' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

### Module: workflows

#### GET /workflows/ - Get Workflow
- Description: Get Workflow
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: workflows.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/workflows/
  - Headers: Authorization + Version (v3)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/workflows/' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: v3' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required

#### POST /contacts/{contactId}/workflow/{workflowId} - Add Contact to Workflow
- Description: Enroll a contact in a workflow. This is a contact mutation, not workflow authoring.
- Documented at: `https://marketplace.gohighlevel.com/docs/ghl/contacts/add-contact-to-workflow/`
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: Not stated on the operation page (UNKNOWN).
- Required headers: Version (`v3`)
- Required path params: contactId, workflowId
- Required query params: locationId
- Required body fields: eventStartTime (ISO-8601)
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/workflow/{workflowId}
  - Headers: Authorization + Version (v3)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/contacts/{contactId}/workflow/{workflowId}?locationId=<LOCATION_ID>' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: v3' \
  -H 'Content-Type: application/json' \
  --data '{"eventStartTime":"2026-10-18T12:00:00Z"}'
```
- Documented response: 200 with `{succeeded, succeded}` (both spellings appear in the documentation).
- No idempotency key is documented; reconcile by reading enrollment state before retrying.
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Body without `eventStartTime`
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /contacts/{contactId}/workflow/{workflowId} - Remove Contact from Workflow
- Description: Remove a contact from a workflow. Operator-gated: removal ends in-flight workflow progress.
- Documented at: `https://marketplace.gohighlevel.com/docs/ghl/contacts/delete-contact-from-workflow/`
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: Not stated on the operation page (UNKNOWN).
- Required headers: Version (`v3`)
- Required path params: contactId, workflowId
- Required query params: locationId
- Required body fields: eventStartTime (ISO-8601)
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/workflow/{workflowId}
  - Headers: Authorization + Version (v3)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/contacts/{contactId}/workflow/{workflowId}?locationId=<LOCATION_ID>' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: v3' \
  -H 'Content-Type: application/json' \
  --data '{"eventStartTime":"2026-10-18T12:00:00Z"}'
```
- Documented response: 200 with `{succeeded, succeded}` (both spellings appear in the documentation).
- No idempotency key is documented; reconcile by re-reading enrollment state, never by blind retry.
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Body without `eventStartTime`
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security
