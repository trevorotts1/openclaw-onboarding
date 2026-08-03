# GHL Conversation AI API Reference

> **Scope of this file:** All endpoints under the `conversation-ai` module — the API layer that configures the conversational agent itself: agents, agent actions, and follow-up settings.
> Base URL: `https://services.leadconnectorhq.com`
> Auth: `Authorization: Bearer $GOHIGHLEVEL_API_KEY` — the LOCATION PIT from `~/.openclaw/secrets/.env`. In the cURL templates below, substitute `$GOHIGHLEVEL_API_KEY` for `<PRIVATE_INTEGRATION_TOKEN>` and use double quotes so it expands. See SKILL.md "Credentials" for the fail-loud resolver.
> Version header: `Version: 2021-04-15` (required on all calls)
>
> **Version header is per-app, not global.** `2021-07-28` is the default (33 of the 41
> published app specs). The ONLY apps on `2021-04-15` are: conversations, calendars,
> saas-api, voice-ai, agent-studio, conversation-ai, knowledge-base. `links` accepts
> both; `store` declares no Version parameter. Never apply one value across all calls.
> Source: `https://github.com/GoHighLevel/highlevel-api-docs/tree/main/apps` (verified 2026-08-03).
> Endpoints below are enumerated from `https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/apps/conversation-ai.json` (verified 2026-08-03).

---

### Module: conversation-ai

#### POST /conversation-ai/agents - Create an Agent
- Description: Creates a new AI agent for the location. The agent will be created with the specified configuration including name, role, actions, and behavior settings.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversation-ai.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/conversation-ai/agents
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/conversation-ai/agents' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /conversation-ai/agents/search - Search Agents
- Description: Searches for AI agents based on various criteria including name, status, and configuration. Supports advanced filtering and full-text search capabilities.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversation-ai.readonly
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/conversation-ai/agents/search
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/conversation-ai/agents/search' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /conversation-ai/agents/{agentId} - Get Agent
- Description: Retrieves a specific AI agent by its ID. Returns the complete agent configuration including name, status, actions, and settings.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversation-ai.readonly
- Required headers: Version
- Required path params: agentId
- Required query params: None
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /conversation-ai/agents/{agentId} - Update Agent
- Description: Updates an existing AI agent's configuration. All fields in the agent configuration can be updated including name, status, actions, and behavior settings.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversation-ai.write
- Required headers: Version
- Required path params: agentId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /conversation-ai/agents/{agentId} - Delete Agent
- Description: Deletes an AI agent permanently. This action cannot be undone. All associated configurations and conversation history will be removed.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversation-ai.write
- Required headers: Version
- Required path params: agentId
- Required query params: None
- Required body fields: None
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /conversation-ai/agents/{agentId}/actions - Attach Action to Agent
- Description: Creates and attach a new action for an AI agent. Actions define specific tasks or behaviors that the agent can perform, such as booking appointments, sending follow-ups, or collecting information.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversation-ai.write
- Required headers: Version
- Required path params: agentId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}/actions
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}/actions' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /conversation-ai/agents/{agentId}/actions/list - List Actions for an Agent
- Description: List for actions for an agent
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversation-ai.readonly
- Required headers: Version
- Required path params: agentId
- Required query params: None
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}/actions/list
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}/actions/list' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /conversation-ai/agents/{agentId}/actions/{actionId} - Get Action by ID
- Description: Retrieves detailed information about a specific action using its unique identifier. Returns the action configuration, associated agents, and performance metrics.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversation-ai.readonly
- Required headers: Version
- Required path params: actionId, agentId
- Required query params: None
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}/actions/{actionId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}/actions/{actionId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /conversation-ai/agents/{agentId}/actions/{actionId} - Update Action
- Description: Updates an existing action's configuration. This includes modifying the action name, description, trigger conditions, and behavior settings.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversation-ai.write
- Required headers: Version
- Required path params: actionId, agentId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}/actions/{actionId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}/actions/{actionId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /conversation-ai/agents/{agentId}/actions/{actionId} - Remove Action from Agent
- Description: Permanently deletes an action. This will remove the action from all associated agents and cannot be undone.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversation-ai.write
- Required headers: Version
- Required path params: actionId, agentId
- Required query params: None
- Required body fields: None
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}/actions/{actionId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}/actions/{actionId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PATCH /conversation-ai/agents/{agentId}/followup-settings - Update Followup Settings
- Description: Update the followup settings for an action
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversation-ai.write
- Required headers: Version
- Required path params: agentId
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PATCH
  - URL: https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}/followup-settings
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PATCH 'https://services.leadconnectorhq.com/conversation-ai/agents/{agentId}/followup-settings' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /conversation-ai/generations - Get the generation details
- Description: Retrieves detailed information about AI responses including the System Prompt, Conversation history, Knowledge base, website, FAQ chunks, and Rich Text chunks.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversation-ai.readonly
- Required headers: Version
- Required path params: None
- Required query params: messageId, source
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/conversation-ai/generations
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/conversation-ai/generations' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security
