# GHL Campaigns + Workflows API Reference

> **Scope of this file:** Campaigns module (campaign triggers) and Workflows module (automation workflows).
> Base URL: `https://services.leadconnectorhq.com`
> Auth: `Authorization: Bearer $GOHIGHLEVEL_API_KEY` — the LOCATION PIT from `~/.openclaw/secrets/.env`. In the cURL templates below, substitute `$GOHIGHLEVEL_API_KEY` for `<PRIVATE_INTEGRATION_TOKEN>` and use double quotes so it expands. See SKILL.md "Credentials" for the fail-loud resolver.
> Version header: `Version: 2021-07-28` (required on all calls)
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
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/workflows/' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
