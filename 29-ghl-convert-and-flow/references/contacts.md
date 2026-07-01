# GHL Contacts API Reference

> **Scope of this file:** All endpoints under the `contacts` module.
> Base URL: `https://services.leadconnectorhq.com`
> Auth: `Authorization: Bearer $GOHIGHLEVEL_API_KEY` — the LOCATION PIT from `~/.openclaw/secrets/.env`. In the cURL templates below, substitute `$GOHIGHLEVEL_API_KEY` for `<PRIVATE_INTEGRATION_TOKEN>` and use double quotes so it expands. See SKILL.md "Credentials" for the fail-loud resolver.
> Version header: `Version: 2021-04-15` (required on all calls)

---

### Module: contacts

#### GET /contacts/ - Get Contacts
- Description: Get Contacts   **Note:** This API endpoint is deprecated. Please use the [Search Contacts](https://highlevel.stoplight.io/docs/integrations/dbe4f3a00a106-search-contacts) endpoint instead.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/contacts/
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/contacts/' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /contacts/ - Create Contact
- Description: Please find the list of acceptable values for the `country` field  <a href="https://highlevel.stoplight.io/docs/integrations/ZG9jOjI4MzUzNDIy-country-list" target="_blank">here</a>
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/contacts/
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/contacts/' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /contacts/bulk/business - Add/Remove Contacts From Business
- Description: Add/Remove Contacts From Business . Passing a `null` businessId will remove the businessId from the contacts
- Security: Not specified
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: Not explicitly listed
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/contacts/bulk/business
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/contacts/bulk/business' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /contacts/bulk/tags/update/{type} - Update Contacts Tags
- Description: Allows you to update tags to multiple contacts at once, you can add or remove tags from the contacts
- Security: Not specified
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: Not explicitly listed
- Required headers: Version
- Required path params: type
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/contacts/bulk/tags/update/{type}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/contacts/bulk/tags/update/{type}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /contacts/business/{businessId} - Get Contacts By BusinessId
- Description: Get Contacts By BusinessId
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.readonly
- Required headers: Version
- Required path params: businessId
- Required query params: locationId
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/contacts/business/{businessId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/contacts/business/{businessId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /contacts/search - Search Contacts
- Description: Search contacts based on combinations of advanced filters. Documentation Link - https://doc.clickup.com/8631005/d/h/87cpx-158396/6e629989abe7fad
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.readonly
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/contacts/search
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/contacts/search' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /contacts/search/duplicate - Get Duplicate Contact
- Description: Get Duplicate Contact.<br/><br/>If `Allow Duplicate Contact` is disabled under Settings, the global unique identifier will be used for searching the contact. If the setting is enabled, first priority for search is `email` and the second priority will be `phone`.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/contacts/search/duplicate
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/contacts/search/duplicate' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /contacts/upsert - Upsert Contact
- Description: Please find the list of acceptable values for the `country` field  <a href="https://highlevel.stoplight.io/docs/integrations/ZG9jOjI4MzUzNDIy-country-list" target="_blank">here</a><br/><br/>The Upsert API will adhere to the configuration defined under the “Allow Duplicate Contact” setting at the Location level. If the setting is configured to check
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/contacts/upsert
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/contacts/upsert' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /contacts/{contactId} - Get Contact
- Description: Get Contact
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.readonly
- Required headers: Version
- Required path params: contactId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/contacts/{contactId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /contacts/{contactId} - Update Contact
- Description: Please find the list of acceptable values for the `country` field  <a href="https://highlevel.stoplight.io/docs/integrations/ZG9jOjI4MzUzNDIy-country-list" target="_blank">here</a>
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/contacts/{contactId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /contacts/{contactId} - Delete Contact
- Description: Delete Contact
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/contacts/{contactId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /contacts/{contactId}/appointments - Get Appointments for Contact
- Description: Get Appointments for Contact
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.readonly
- Required headers: Version
- Required path params: contactId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/appointments
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/contacts/{contactId}/appointments' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /contacts/{contactId}/campaigns/removeAll - Remove Contact From Every Campaign
- Description: Remove Contact From Every Campaign
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/campaigns/removeAll
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/contacts/{contactId}/campaigns/removeAll' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /contacts/{contactId}/campaigns/{campaignId} - Add Contact to Campaign
- Description: Add contact to Campaign
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId, campaignId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/campaigns/{campaignId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/contacts/{contactId}/campaigns/{campaignId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /contacts/{contactId}/campaigns/{campaignId} - Remove Contact From Campaign
- Description: Remove Contact From Campaign
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId, campaignId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/campaigns/{campaignId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/contacts/{contactId}/campaigns/{campaignId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /contacts/{contactId}/followers - Add Followers
- Description: Add Followers
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/followers
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/contacts/{contactId}/followers' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /contacts/{contactId}/followers - Remove Followers
- Description: Remove Followers
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/followers
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/contacts/{contactId}/followers' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /contacts/{contactId}/notes - Get All Notes
- Description: Get All Notes
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.readonly
- Required headers: Version
- Required path params: contactId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/notes
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/contacts/{contactId}/notes' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /contacts/{contactId}/notes - Create Note
- Description: Create Note
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/notes
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/contacts/{contactId}/notes' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /contacts/{contactId}/notes/{id} - Get Note
- Description: Get Note
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.readonly
- Required headers: Version
- Required path params: contactId, id
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/notes/{id}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/contacts/{contactId}/notes/{id}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /contacts/{contactId}/notes/{id} - Update Note
- Description: Update Note
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId, id
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/notes/{id}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/contacts/{contactId}/notes/{id}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /contacts/{contactId}/notes/{id} - Delete Note
- Description: Delete Note
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId, id
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/notes/{id}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/contacts/{contactId}/notes/{id}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /contacts/{contactId}/tags - Add Tags
- Description: Add Tags
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/tags
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/contacts/{contactId}/tags' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /contacts/{contactId}/tags - Remove Tags
- Description: Remove Tags
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/tags
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/contacts/{contactId}/tags' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /contacts/{contactId}/tasks - Get all Tasks
- Description: Get all Tasks
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.readonly
- Required headers: Version
- Required path params: contactId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/tasks
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/contacts/{contactId}/tasks' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /contacts/{contactId}/tasks - Create Task
- Description: Create Task
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/tasks
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/contacts/{contactId}/tasks' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /contacts/{contactId}/tasks/{taskId} - Get Task
- Description: Get Task
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.readonly
- Required headers: Version
- Required path params: contactId, taskId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/tasks/{taskId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/contacts/{contactId}/tasks/{taskId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /contacts/{contactId}/tasks/{taskId} - Update Task
- Description: Update Task
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId, taskId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/tasks/{taskId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/contacts/{contactId}/tasks/{taskId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /contacts/{contactId}/tasks/{taskId} - Delete Task
- Description: Delete Task
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId, taskId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/tasks/{taskId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/contacts/{contactId}/tasks/{taskId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /contacts/{contactId}/tasks/{taskId}/completed - Update Task Completed
- Description: Update Task Completed
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId, taskId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/tasks/{taskId}/completed
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/contacts/{contactId}/tasks/{taskId}/completed' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /contacts/{contactId}/workflow/{workflowId} - Add Contact to Workflow
- Description: Add Contact to Workflow
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId, workflowId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/workflow/{workflowId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/contacts/{contactId}/workflow/{workflowId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /contacts/{contactId}/workflow/{workflowId} - Delete Contact from Workflow
- Description: Delete Contact from Workflow
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: contacts.write
- Required headers: Version
- Required path params: contactId, workflowId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/contacts/{contactId}/workflow/{workflowId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/contacts/{contactId}/workflow/{workflowId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

