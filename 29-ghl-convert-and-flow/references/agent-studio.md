# GHL AI Agent Studio API Reference

> **Scope of this file:** All endpoints under the `agent-studio` module — the full AI agent lifecycle: create, version, publish, execute, delete.
> Base URL: `https://services.leadconnectorhq.com`
> Auth: `Authorization: Bearer $GOHIGHLEVEL_API_KEY` — the LOCATION PIT from `~/.openclaw/secrets/.env`. In the cURL templates below, substitute `$GOHIGHLEVEL_API_KEY` for `<PRIVATE_INTEGRATION_TOKEN>` and use double quotes so it expands. See SKILL.md "Credentials" for the fail-loud resolver.
> Version header: `Version: 2021-04-15` (required on all calls)
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
> Endpoints below are enumerated from `https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/apps/agent-studio.json` (verified 2026-08-03).

---

### Module: agent-studio

#### GET /agent-studio/agent - List Agents
- Description: Lists all active agents for the specified location. locationId is required parameter to ensure optimal performance. Supports pagination using limit and offset. Optionally filter by isPublished=true to return only agents with a published production version.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: agent-studio.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId, limit, offset
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/agent-studio/agent
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/agent-studio/agent' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /agent-studio/agent - Create Agent
- Description: Creates a new agent with staging version. The agent will be created with an initial staging version that can later be promoted to production.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: agent-studio.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/agent-studio/agent
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/agent-studio/agent' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PATCH /agent-studio/agent/versions/{versionId} - Update Agent
- Description: Updates a specific agent version by versionId. Supports updating nodes, edges, variables, and configuration.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: agent-studio.write
- Required headers: Version
- Required path params: versionId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PATCH
  - URL: https://services.leadconnectorhq.com/agent-studio/agent/versions/{versionId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PATCH 'https://services.leadconnectorhq.com/agent-studio/agent/versions/{versionId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /agent-studio/agent/versions/{versionId}/publish - Promote to Production
- Description: Promotes a draft version to production.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: agent-studio.write
- Required headers: Version
- Required path params: versionId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/agent-studio/agent/versions/{versionId}/publish
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/agent-studio/agent/versions/{versionId}/publish' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /agent-studio/agent/{agentId} - Get Agent
- Description: Gets a specific agent by its ID for the specified location with all its versions. Returns complete agent metadata and all non-deleted versions (draft, staging, production). locationId is required parameter. The agent must have active status.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: agent-studio.readonly
- Required headers: Version
- Required path params: agentId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/agent-studio/agent/{agentId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/agent-studio/agent/{agentId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PATCH /agent-studio/agent/{agentId} - Update Agent Metadata
- Description: Updates agent metadata such as name, description, and status.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: agent-studio.write
- Required headers: Version
- Required path params: agentId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PATCH
  - URL: https://services.leadconnectorhq.com/agent-studio/agent/{agentId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PATCH 'https://services.leadconnectorhq.com/agent-studio/agent/{agentId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /agent-studio/agent/{agentId} - Delete Agent
- Description: Deletes an agent and all its versions.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: agent-studio.write
- Required headers: Version
- Required path params: agentId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/agent-studio/agent/{agentId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/agent-studio/agent/{agentId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /agent-studio/agent/{agentId}/execute - Execute Agent
- Description: Executes the specified agent and returns a non-streaming JSON response with the complete agent output. The agent must be in active status and belong to the specified location. locationId is required in the request body. 
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: agent-studio.write
- Required headers: Version
- Required path params: agentId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/agent-studio/agent/{agentId}/execute
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/agent-studio/agent/{agentId}/execute' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /agent-studio/public-api/agents - List Agents (Deprecated)
- Description: **Deprecated endpoint - use GET /agent instead.**
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: agent-studio.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId, limit, offset
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/agent-studio/public-api/agents
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/agent-studio/public-api/agents' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /agent-studio/public-api/agents/{agentId} - Get Agent (Deprecated)
- Description: **Deprecated endpoint - use GET /agent/:agentId instead.**
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: agent-studio.readonly
- Required headers: Version
- Required path params: agentId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/agent-studio/public-api/agents/{agentId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/agent-studio/public-api/agents/{agentId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /agent-studio/public-api/agents/{agentId}/execute - Execute Agent (Deprecated)
- Description: **Deprecated endpoint - use POST /agent/:agentId/execute instead.**
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: agent-studio.write
- Required headers: Version
- Required path params: agentId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/agent-studio/public-api/agents/{agentId}/execute
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/agent-studio/public-api/agents/{agentId}/execute' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security
