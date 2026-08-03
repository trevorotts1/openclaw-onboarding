# GHL Voice AI API Reference

> **Scope of this file:** All endpoints under the `voice-ai` module — Voice AI agents, agent actions, and the call-log/transcript dashboard.
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
> Endpoints below are enumerated from `https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/apps/voice-ai.json` (verified 2026-08-03).

---

### Module: voice-ai

#### POST /voice-ai/actions - Create Agent Action
- Description: Create a new action for a voice AI agent. Actions define specific behaviors and capabilities for the agent during calls.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: voice-ai-agent-goals.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/voice-ai/actions
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/voice-ai/actions' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /voice-ai/actions/{actionId} - Get Agent Action
- Description: Retrieve details of a specific action by its ID. Returns the action configuration including actionParameters.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: voice-ai-agent-goals.readonly
- Required headers: Version
- Required path params: actionId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/voice-ai/actions/{actionId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/voice-ai/actions/{actionId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /voice-ai/actions/{actionId} - Update Agent Action
- Description: Update an existing action for a voice AI agent. Modifies the behavior and configuration of an agent action.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: voice-ai-agent-goals.write
- Required headers: Version
- Required path params: actionId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/voice-ai/actions/{actionId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/voice-ai/actions/{actionId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /voice-ai/actions/{actionId} - Delete Agent Action
- Description: Delete an existing action from a voice AI agent. This permanently removes the action and its configuration.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: voice-ai-agent-goals.write
- Required headers: Version
- Required path params: actionId
- Required query params: locationId, agentId
- Required body fields: None
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/voice-ai/actions/{actionId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/voice-ai/actions/{actionId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /voice-ai/agents - List Agents
- Description: Retrieve a paginated list of agents for given location.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: voice-ai-agents.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/voice-ai/agents
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/voice-ai/agents' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /voice-ai/agents - Create Agent
- Description: Create a new voice AI agent configuration and settings
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: voice-ai-agents.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/voice-ai/agents
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/voice-ai/agents' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /voice-ai/agents/{agentId} - Get Agent
- Description: Retrieve detailed configuration and settings for a specific voice AI agent
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: voice-ai-agents.readonly
- Required headers: Version
- Required path params: agentId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/voice-ai/agents/{agentId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/voice-ai/agents/{agentId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PATCH /voice-ai/agents/{agentId} - Patch Agent
- Description: Partially update an existing voice AI agent
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: voice-ai-agents.write
- Required headers: Version
- Required path params: agentId
- Required query params: locationId
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PATCH
  - URL: https://services.leadconnectorhq.com/voice-ai/agents/{agentId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PATCH 'https://services.leadconnectorhq.com/voice-ai/agents/{agentId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /voice-ai/agents/{agentId} - Delete Agent
- Description: Delete a voice AI agent and all its configurations
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: voice-ai-agents.write
- Required headers: Version
- Required path params: agentId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/voice-ai/agents/{agentId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/voice-ai/agents/{agentId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /voice-ai/dashboard/call-logs - List Call Logs
- Description: Returns call logs for Voice AI agents scoped to a location. Supports filtering by agent, contact, call type, action types, and date range (interpreted in the provided IANA timezone). Also supports sorting and 1-based pagination.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: voice-ai-dashboard.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/voice-ai/dashboard/call-logs
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/voice-ai/dashboard/call-logs' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /voice-ai/dashboard/call-logs/{callId} - Get Call Log
- Description: Returns a call log by callId.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: voice-ai-dashboard.readonly
- Required headers: Version
- Required path params: callId
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/voice-ai/dashboard/call-logs/{callId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/voice-ai/dashboard/call-logs/{callId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security
