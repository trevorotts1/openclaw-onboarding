# GHL Ad Publishing (Ad Manager) API Reference

> **Scope of this file:** All endpoints under the `ad-publishing` module — Facebook, Google and LinkedIn campaigns, adsets, ads, custom audiences, pixels, lead forms, reporting, targeting search and keyword ideas.
> Base URL: `https://services.leadconnectorhq.com`
> Auth: `Authorization: Bearer $GOHIGHLEVEL_API_KEY` — the LOCATION PIT from `~/.openclaw/secrets/.env`. In the cURL templates below, substitute `$GOHIGHLEVEL_API_KEY` for `<PRIVATE_INTEGRATION_TOKEN>` and use double quotes so it expands. See SKILL.md "Credentials" for the fail-loud resolver.
> Version header: `Version: 2021-07-28` (required on all calls)
>
> **Version header is per-app, not global.** `2021-07-28` is the default (33 of the 41
> published app specs). The ONLY apps on `2021-04-15` are: conversations, calendars,
> saas-api, voice-ai, agent-studio, conversation-ai, knowledge-base. `links` accepts
> both; `store` declares no Version parameter. Never apply one value across all calls.
> Source: `https://github.com/GoHighLevel/highlevel-api-docs/tree/main/apps` (verified 2026-08-03).
> Endpoints below are enumerated from `https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/apps/ad-manager.json` (verified 2026-08-03).

---

### Module: ad-publishing

#### GET /ad-publishing/facebook/ad-accounts - Get ad accounts
- Description: Retrieve Facebook ad accounts available for the connected user
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/ad-accounts
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/ad-accounts' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/facebook/ad-accounts/{adAccountId} - Get ad account details
- Description: Retrieve details of a specific Facebook ad account
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: adAccountId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/ad-accounts/{adAccountId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/ad-accounts/{adAccountId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /ad-publishing/facebook/ad-accounts/{adAccountId} - Delete ad account
- Description: Remove a Facebook ad account connection from a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: adAccountId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/ad-accounts/{adAccountId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/ad-publishing/facebook/ad-accounts/{adAccountId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /ad-publishing/facebook/ads-v2 - Upsert ad
- Description: Create or update a Facebook ad (v2)
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/ads-v2
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/ad-publishing/facebook/ads-v2' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /ad-publishing/facebook/ads/{adId} - Delete ad
- Description: Delete a Facebook ad by ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: adId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/ads/{adId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/ad-publishing/facebook/ads/{adId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/facebook/ads/{adId}/duplicate - Duplicate ad
- Description: Duplicate an existing Facebook ad
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: adId
- Required query params: None
- Required body fields: None
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/ads/{adId}/duplicate
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/facebook/ads/{adId}/duplicate' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/facebook/ads/{adId}/pause - Pause ad
- Description: Pause a running Facebook ad
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: adId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/ads/{adId}/pause
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/facebook/ads/{adId}/pause' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/facebook/ads/{adId}/resume - Resume ad
- Description: Resume a paused Facebook ad
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: adId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/ads/{adId}/resume
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/facebook/ads/{adId}/resume' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /ad-publishing/facebook/adsets - Upsert adset
- Description: Create or update a Facebook ad set
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/adsets
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/ad-publishing/facebook/adsets' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /ad-publishing/facebook/adsets/{adsetId} - Delete ad set
- Description: Delete a Facebook ad set by ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: adsetId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/adsets/{adsetId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/ad-publishing/facebook/adsets/{adsetId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/facebook/adsets/{adsetId}/duplicate - Duplicate ad set
- Description: Duplicate an existing Facebook ad set
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: adsetId
- Required query params: None
- Required body fields: None
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/adsets/{adsetId}/duplicate
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/facebook/adsets/{adsetId}/duplicate' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/facebook/adsets/{adsetId}/pause - Pause ad set
- Description: Pause a running Facebook ad set
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: adsetId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/adsets/{adsetId}/pause
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/facebook/adsets/{adsetId}/pause' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/facebook/adsets/{adsetId}/resume - Resume ad set
- Description: Resume a paused Facebook ad set
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: adsetId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/adsets/{adsetId}/resume
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/facebook/adsets/{adsetId}/resume' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/facebook/campaign/{campaignId} - Get campaign with linked entities
- Description: Retrieve a Facebook campaign with its linked adsets and ads
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: campaignId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/campaign/{campaignId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/campaign/{campaignId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /ad-publishing/facebook/campaigns - Upsert campaign
- Description: Create or update a Facebook campaign
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/campaigns
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/ad-publishing/facebook/campaigns' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /ad-publishing/facebook/campaigns/{campaignId} - Delete campaign
- Description: Delete a Facebook campaign by ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: campaignId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/campaigns/{campaignId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/ad-publishing/facebook/campaigns/{campaignId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/facebook/campaigns/{campaignId}/duplicate - Duplicate campaign
- Description: Duplicate an existing Facebook campaign
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: campaignId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/campaigns/{campaignId}/duplicate
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/facebook/campaigns/{campaignId}/duplicate' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/facebook/campaigns/{campaignId}/pause - Pause campaign
- Description: Pause a running Facebook campaign
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: campaignId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/campaigns/{campaignId}/pause
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/facebook/campaigns/{campaignId}/pause' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/facebook/campaigns/{campaignId}/publish - Publish campaign
- Description: Publish a Facebook campaign and push it live to Facebook
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: campaignId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/campaigns/{campaignId}/publish
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/facebook/campaigns/{campaignId}/publish' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/facebook/campaigns/{campaignId}/resume - Resume campaign
- Description: Resume a paused Facebook campaign
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: campaignId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/campaigns/{campaignId}/resume
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/facebook/campaigns/{campaignId}/resume' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/facebook/conversation-forms - Get conversation forms
- Description: Retrieve Facebook conversation lead forms for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/conversation-forms
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/conversation-forms' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/facebook/conversation-forms - Create conversation form
- Description: Create a new Facebook conversation lead form
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/conversation-forms
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/facebook/conversation-forms' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/facebook/custom-audience - Get custom audiences
- Description: Retrieve Facebook custom audiences for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId, type, adAccountId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/custom-audience
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/custom-audience' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/facebook/custom-audience/{audienceId} - Get custom audience by ID
- Description: Retrieve a specific Facebook custom audience by its ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: audienceId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/custom-audience/{audienceId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/custom-audience/{audienceId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /ad-publishing/facebook/custom-audience/{audienceId} - Update custom audience
- Description: Update name or description of a Facebook custom audience
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: audienceId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/custom-audience/{audienceId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/ad-publishing/facebook/custom-audience/{audienceId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /ad-publishing/facebook/custom-audience/{audienceId} - Delete custom audience
- Description: Delete a Facebook custom audience by ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: audienceId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/custom-audience/{audienceId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/ad-publishing/facebook/custom-audience/{audienceId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /ad-publishing/facebook/custom-audience/{audienceId}/member - Add custom audience member
- Description: Add a member to a Facebook custom audience
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: audienceId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/custom-audience/{audienceId}/member
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/ad-publishing/facebook/custom-audience/{audienceId}/member' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /ad-publishing/facebook/custom-audience/{audienceId}/member - Remove custom audience member
- Description: Remove a member from a Facebook custom audience
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: audienceId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/custom-audience/{audienceId}/member
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/ad-publishing/facebook/custom-audience/{audienceId}/member' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /ad-publishing/facebook/custom-audience/{audienceId}/member/batch - Batch update audience members
- Description: Add or remove members in bulk from a Facebook custom audience via CSV or smart lists
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: audienceId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/custom-audience/{audienceId}/member/batch
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/ad-publishing/facebook/custom-audience/{audienceId}/member/batch' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/facebook/entity - Get entities
- Description: Retrieve Facebook campaigns, adsets, or ads based on entity type
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId, type, entityType
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/entity
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/entity' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/facebook/integration - Get Facebook integration
- Description: Retrieve the Facebook ad integration details for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/integration
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/integration' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/facebook/integration - Create Facebook integration
- Description: Create a Facebook ad integration for a location with page and ad account
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/integration
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/facebook/integration' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /ad-publishing/facebook/integration - Delete Facebook integration
- Description: Remove the Facebook ad integration from a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/integration
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/ad-publishing/facebook/integration' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/facebook/lead-form/{leadFormId} - Get lead form by ID
- Description: Retrieve a specific Facebook lead form by its ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: leadFormId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/lead-form/{leadFormId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/lead-form/{leadFormId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/facebook/me - Get current Facebook user
- Description: Retrieve the authenticated Facebook user profile for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/me
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/me' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /ad-publishing/facebook/page - Delete page connection
- Description: Remove a Facebook page connection from a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: locationId, pageId
- Required body fields: None
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/page
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/ad-publishing/facebook/page' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /ad-publishing/facebook/page/default - Set default page
- Description: Set the default Facebook page for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/page/default
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/ad-publishing/facebook/page/default' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/facebook/page/{pageId}/forms - Get page lead forms
- Description: Retrieve lead gen forms for a specific Facebook page
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: pageId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/page/{pageId}/forms
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/page/{pageId}/forms' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/facebook/page/{pageId}/forms - Create page lead form
- Description: Create a new lead gen form on a Facebook page
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: pageId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/page/{pageId}/forms
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/facebook/page/{pageId}/forms' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/facebook/page/{pageId}/instagram - Get Instagram accounts for page
- Description: Retrieve Instagram accounts linked to a specific Facebook page
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: pageId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/page/{pageId}/instagram
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/page/{pageId}/instagram' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/facebook/pages - Get Facebook pages
- Description: Retrieve Facebook pages associated with the connected account
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/pages
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/pages' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/facebook/pixels - Get conversion pixels
- Description: Retrieve Facebook conversion pixels for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/pixels
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/pixels' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /ad-publishing/facebook/pixels - Upsert conversion pixel
- Description: Create or update a Facebook conversion pixel configuration
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/pixels
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/ad-publishing/facebook/pixels' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/facebook/reporting - Get reporting data
- Description: Retrieve aggregated Facebook ad reporting metrics for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId, groupBy, startDate, endDate, type, fields
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/reporting
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/reporting' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/facebook/reporting/campaign/{campaignId} - Get campaign reporting
- Description: Retrieve reporting metrics for a specific Facebook campaign
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: campaignId
- Required query params: locationId, startDate, endDate
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/reporting/campaign/{campaignId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/reporting/campaign/{campaignId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/facebook/reporting/list - Get reporting list
- Description: Retrieve a list of Facebook campaigns, adsets, or ads with reporting data
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId, listType, startDate, endDate, campaignId, type
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/reporting/list
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/reporting/list' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/facebook/targeting/search - Search targeting options
- Description: Search Facebook geo-locations and interests for ad targeting
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: (none declared in spec)
- Required headers: Version
- Required path params: None
- Required query params: type, query
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/facebook/targeting/search
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/facebook/targeting/search' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/ad-accounts - Get Google ad accounts
- Description: Retrieve Google Ads accounts available for the connected user
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/ad-accounts
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/ad-accounts' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/ad-accounts/{adAccountId} - Get ad account details
- Description: Retrieve details of a specific Google Ads account
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: adAccountId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/ad-accounts/{adAccountId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/ad-accounts/{adAccountId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /ad-publishing/google/ad-accounts/{adAccountId} - Delete ad account
- Description: Remove a Google Ads account connection from a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: adAccountId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/ad-accounts/{adAccountId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/ad-publishing/google/ad-accounts/{adAccountId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /ad-publishing/google/ads - Upsert Google campaign
- Description: Create or update a full Google Ads campaign structure
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/ads
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/ad-publishing/google/ads' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/ads/{adId} - Get Google campaign by ID
- Description: Retrieve a specific Google Ads campaign by ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: adId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/ads/{adId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/ads/{adId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/google/ads/{adId}/publish - Publish ad
- Description: Publish a Google ad and push it live
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: adId
- Required query params: None
- Required body fields: None
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/ads/{adId}/publish
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/google/ads/{adId}/publish' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/assets - Get assets
- Description: Retrieve Google Ads creative assets for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId, type
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/assets
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/assets' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/google/assets - Upsert assets
- Description: Create or update Google Ads creative assets
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/assets
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/google/assets' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/audiences - Get audiences
- Description: Retrieve Google Ads combined audiences for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/audiences
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/audiences' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /ad-publishing/google/audiences - Upsert audience
- Description: Create or update a Google Ads combined audience
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/audiences
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/ad-publishing/google/audiences' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/audiences/{audienceId} - Get audience by ID
- Description: Retrieve a specific Google Ads combined audience by ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: audienceId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/audiences/{audienceId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/audiences/{audienceId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/conversion-goals - Get conversion goals
- Description: Retrieve Google Ads conversion goals for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/conversion-goals
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/conversion-goals' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/conversions - Get conversions
- Description: Retrieve Google Ads conversion actions for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/conversions
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/conversions' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /ad-publishing/google/conversions - Upsert conversion
- Description: Create or update a Google Ads conversion action
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/conversions
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/ad-publishing/google/conversions' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/conversions/{conversionId} - Get conversion by ID
- Description: Retrieve a specific Google Ads conversion action by ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: conversionId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/conversions/{conversionId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/conversions/{conversionId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /ad-publishing/google/conversions/{conversionId} - Delete conversion
- Description: Delete a Google Ads conversion action by ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: conversionId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/conversions/{conversionId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/ad-publishing/google/conversions/{conversionId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/entity - Get entities
- Description: Retrieve Google campaigns, ad groups, or ads based on entity type
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId, type, entityType
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/entity
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/entity' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/integration - Get Google integration
- Description: Retrieve the Google Ads integration details for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/integration
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/integration' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/google/integration - Create Google integration
- Description: Create a Google Ads integration for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/integration
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/google/integration' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/google/keyword-ideas - Get keyword ideas
- Description: Retrieve keyword suggestions for Google Ads campaigns
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/keyword-ideas
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/google/keyword-ideas' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/me - Get current Google user
- Description: Retrieve the authenticated Google user info for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/me
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/me' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/reporting - Get reporting data
- Description: Retrieve aggregated Google Ads reporting metrics for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId, startDate, endDate, type, fields
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/reporting
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/reporting' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/reporting/campaign/{campaignId} - Get campaign reporting
- Description: Retrieve reporting metrics for a specific Google campaign
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: campaignId
- Required query params: locationId, startDate, endDate
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/reporting/campaign/{campaignId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/reporting/campaign/{campaignId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/reporting/list - Get reporting list
- Description: Retrieve a list of Google campaigns or ad groups with reporting data
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId, listType, startDate, endDate, type
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/reporting/list
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/reporting/list' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/segments - Get segments
- Description: Retrieve Google Ads audience segments for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/segments
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/segments' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /ad-publishing/google/segments - Upsert segment
- Description: Create or update a Google Ads audience segment
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: locationId, type
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/segments
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/ad-publishing/google/segments' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/google/segments/offline-user-list-job - Create offline user list job
- Description: Create a job to upload users to a Google customer match list
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/segments/offline-user-list-job
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/google/segments/offline-user-list-job' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/segments/{segmentId} - Get segment by ID
- Description: Retrieve a specific Google Ads audience segment by ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: segmentId
- Required query params: locationId, type
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/segments/{segmentId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/segments/{segmentId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /ad-publishing/google/segments/{segmentId} - Delete segment
- Description: Delete a Google Ads audience segment by ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: segmentId
- Required query params: locationId, type
- Required body fields: None
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/segments/{segmentId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/ad-publishing/google/segments/{segmentId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/target-interests - Get target interests
- Description: Retrieve affinity and in-market audience options for Google Ads targeting
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId, type, advertisingChannelType
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/target-interests
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/target-interests' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/google/targeting/search - Search targeting options
- Description: Search Google geo-locations for ad targeting
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: type, locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/google/targeting/search
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/google/targeting/search' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/linkedin/ad-account - Get ad account details
- Description: Retrieve details of a specific LinkedIn ad account
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId, adAccountId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/linkedin/ad-account
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/linkedin/ad-account' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /ad-publishing/linkedin/ad-account - Delete ad account
- Description: Remove a LinkedIn ad account connection from a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: locationId, adAccountId
- Required body fields: None
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/ad-publishing/linkedin/ad-account
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/ad-publishing/linkedin/ad-account' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/linkedin/ad-accounts - Get LinkedIn ad accounts
- Description: Retrieve LinkedIn Ads accounts available for the connected user
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/linkedin/ad-accounts
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/linkedin/ad-accounts' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /ad-publishing/linkedin/ads - Upsert ad campaign group
- Description: Create or update a LinkedIn ad campaign group with campaigns and ads
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/ad-publishing/linkedin/ads
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/ad-publishing/linkedin/ads' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/linkedin/ads/{adId} - Get ad campaign group
- Description: Retrieve a LinkedIn ad campaign group by ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: adId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/linkedin/ads/{adId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/linkedin/ads/{adId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/linkedin/ads/{adId}/publish - Publish ad campaign group
- Description: Publish a LinkedIn ad campaign group and push it live
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: adId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/linkedin/ads/{adId}/publish
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/linkedin/ads/{adId}/publish' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/linkedin/integration - Get LinkedIn integration
- Description: Retrieve the LinkedIn Ads integration details for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/linkedin/integration
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/linkedin/integration' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/linkedin/integration - Create LinkedIn integration
- Description: Create a LinkedIn Ads integration for a location with ad account details
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/linkedin/integration
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/linkedin/integration' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/linkedin/me - Get current LinkedIn user
- Description: Retrieve the authenticated LinkedIn user info for a location
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/linkedin/me
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/linkedin/me' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/linkedin/reporting - Get ad analytics
- Description: Retrieve LinkedIn Ads analytics data with configurable pivot and time grouping
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId, startDate, endDate
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/linkedin/reporting
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/linkedin/reporting' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/linkedin/reporting/campaign-group/{campaignGroupId} - Get campaign group reporting
- Description: Retrieve reporting metrics for a specific LinkedIn campaign group
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: campaignGroupId
- Required query params: locationId, startDate, endDate
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/linkedin/reporting/campaign-group/{campaignGroupId}
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/linkedin/reporting/campaign-group/{campaignGroupId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/linkedin/reporting/list - Get reporting list
- Description: Retrieve a list of LinkedIn campaigns or campaign groups with reporting data
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId, listType, campaignId, campaignGroupId, startDate, endDate
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/linkedin/reporting/list
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/linkedin/reporting/list' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/linkedin/targeting/search - Search targeting options
- Description: Search LinkedIn targeting facets such as locations, industries, and job titles
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId, facet
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/linkedin/targeting/search
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/linkedin/targeting/search' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /ad-publishing/linkedin/{accountId}/form - Create lead form
- Description: Create a new LinkedIn lead gen form for an ad account
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/ad-publishing/linkedin/{accountId}/form
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/ad-publishing/linkedin/{accountId}/form' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /ad-publishing/linkedin/{accountId}/forms - Get lead forms
- Description: Retrieve LinkedIn lead gen forms for an ad account
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.readonly
- Required headers: Version
- Required path params: accountId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/ad-publishing/linkedin/{accountId}/forms
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/ad-publishing/linkedin/{accountId}/forms' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PATCH /ad-publishing/linkedin/{adId}/status - Update ad status
- Description: Pause or resume a LinkedIn ad, campaign, or ad group
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: adPublishing.write
- Required headers: Version
- Required path params: adId
- Required query params: locationId
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PATCH
  - URL: https://services.leadconnectorhq.com/ad-publishing/linkedin/{adId}/status
  - Headers: Authorization + Version (2021-07-28)
- cURL template:
```bash
curl --request PATCH 'https://services.leadconnectorhq.com/ad-publishing/linkedin/{adId}/status' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security
