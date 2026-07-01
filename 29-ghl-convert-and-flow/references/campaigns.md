# GHL Campaigns + Workflows API Reference

> **Scope of this file:** Campaigns module (campaign triggers) and Workflows module (automation workflows).
> Base URL: `https://services.leadconnectorhq.com`
> Auth: `Authorization: Bearer $GOHIGHLEVEL_API_KEY` — the LOCATION PIT from `~/.openclaw/secrets/.env`. In the cURL templates below, substitute `$GOHIGHLEVEL_API_KEY` for `<PRIVATE_INTEGRATION_TOKEN>` and use double quotes so it expands. See SKILL.md "Credentials" for the fail-loud resolver.
> Version header: `Version: 2021-04-15` (required on all calls)

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
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/campaigns/' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
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
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/workflows/' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
