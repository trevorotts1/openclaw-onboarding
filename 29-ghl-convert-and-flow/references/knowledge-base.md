# GHL Knowledge Base API Reference

> **Scope of this file:** All endpoints under the `knowledge-bases` module — knowledge bases, the web crawler, and FAQs. Feeds both Conversation AI and Voice AI.
> Base URL: `https://services.leadconnectorhq.com`
> Auth: `Authorization: Bearer $GOHIGHLEVEL_API_KEY` — the LOCATION PIT from `~/.openclaw/secrets/.env`. In the cURL templates below, substitute `$GOHIGHLEVEL_API_KEY` for `<PRIVATE_INTEGRATION_TOKEN>` and use double quotes so it expands. See SKILL.md "Credentials" for the fail-loud resolver.
> Version header: `Version: 2021-04-15` (required on all calls)
>
> **Version header is per-app, not global.** `2021-07-28` is the default (33 of the 41
> published app specs). The ONLY apps on `2021-04-15` are: conversations, calendars,
> saas-api, voice-ai, agent-studio, conversation-ai, knowledge-base. `links` accepts
> both; `store` declares no Version parameter. Never apply one value across all calls.
> Source: `https://github.com/GoHighLevel/highlevel-api-docs/tree/main/apps` (verified 2026-08-03).
> Endpoints below are enumerated from `https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/apps/knowledge-base.json` (verified 2026-08-03).

---

### Module: knowledge-base

#### GET /knowledge-bases/ - Get all knowledge bases for a location by location Id (paginated)
- Description: Get all knowledge bases for a location by location Id (paginated)
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: (none declared in spec)
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/knowledge-bases/
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/knowledge-bases/' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /knowledge-bases/ - Create a new knowledge base (max 15 knowledge bases per location)
- Description: Create a new knowledge base (max 15 knowledge bases per location)
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: (none declared in spec)
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/knowledge-bases/
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/knowledge-bases/' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /knowledge-bases/crawler - Get all trained page links by knowledge base
- Description: Get all trained page links by knowledge base
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: (none declared in spec)
- Required headers: Version
- Required path params: None
- Required query params: knowledgeBaseId, locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/knowledge-bases/crawler
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/knowledge-bases/crawler' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /knowledge-bases/crawler - Start crawling and discover pages for training
- Description: Start crawling and discover pages for training
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: (none declared in spec)
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/knowledge-bases/crawler
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/knowledge-bases/crawler' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /knowledge-bases/crawler - Delete trained pages
- Description: Delete trained pages
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: (none declared in spec)
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/knowledge-bases/crawler
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/knowledge-bases/crawler' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /knowledge-bases/crawler/status - Get crawling status for the latest operation
- Description: Get crawling status for the latest operation
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: (none declared in spec)
- Required headers: Version
- Required path params: None
- Required query params: locationId, operationId, knowledgeBaseId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/knowledge-bases/crawler/status
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/knowledge-bases/crawler/status' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /knowledge-bases/crawler/train - Train discovered website pages and ingest into the knowledge base
- Description: Train discovered website pages and ingest into the knowledge base
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: (none declared in spec)
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/knowledge-bases/crawler/train
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/knowledge-bases/crawler/train' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /knowledge-bases/faqs - Get all FAQs by knowledge base with pagination support
- Description: Retrieves FAQs for a knowledge base. Supports pagination using limit and lastFaqId parameters.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: (none declared in spec)
- Required headers: Version
- Required path params: None
- Required query params: knowledgeBaseId, locationId
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/knowledge-bases/faqs
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/knowledge-bases/faqs' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /knowledge-bases/faqs - Create a new FAQ inside knowledge base
- Description: Create a new FAQ inside knowledge base
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: (none declared in spec)
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/knowledge-bases/faqs
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/knowledge-bases/faqs' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /knowledge-bases/faqs/{id} - Update an existing knowledge base FAQ
- Description: Update an existing knowledge base FAQ
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: (none declared in spec)
- Required headers: Version
- Required path params: id
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/knowledge-bases/faqs/{id}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/knowledge-bases/faqs/{id}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /knowledge-bases/faqs/{id} - Delete an existing knowledge base FAQ
- Description: Delete an existing knowledge base FAQ
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: (none declared in spec)
- Required headers: Version
- Required path params: id
- Required query params: None
- Required body fields: None
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/knowledge-bases/faqs/{id}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/knowledge-bases/faqs/{id}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /knowledge-bases/{id} - Update a knowledge base
- Description: Update a knowledge base
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: (none declared in spec)
- Required headers: Version
- Required path params: id
- Required query params: None
- Required body fields: see request schema in the spec
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/knowledge-bases/{id}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/knowledge-bases/{id}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /knowledge-bases/{knowledgeBaseId} - Get knowledge base by ID
- Description: Get knowledge base by ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: (none declared in spec)
- Required headers: Version
- Required path params: knowledgeBaseId
- Required query params: None
- Required body fields: None
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/knowledge-bases/{knowledgeBaseId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/knowledge-bases/{knowledgeBaseId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /knowledge-bases/{knowledgeBaseId} - Delete a knowledge base
- Description: Delete a knowledge base
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: (none declared in spec)
- Required headers: Version
- Required path params: knowledgeBaseId
- Required query params: None
- Required body fields: None
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/knowledge-bases/{knowledgeBaseId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/knowledge-bases/{knowledgeBaseId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security
