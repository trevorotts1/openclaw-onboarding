# GHL Payments, Invoices + Subscriptions API Reference

> **Scope of this file:** Invoices module (41 endpoints) and Payments module (24 endpoints).
> Covers: invoices, invoice items, schedules, templates, orders, order fulfillments, transactions, subscriptions, coupons, custom provider integrations, payment integrations.
> Base URL: `https://services.leadconnectorhq.com`
> Auth: `Authorization: Bearer $GOHIGHLEVEL_API_KEY` — the LOCATION PIT from `~/.openclaw/secrets/.env`. In the cURL templates below, substitute `$GOHIGHLEVEL_API_KEY` for `<PRIVATE_INTEGRATION_TOKEN>` and use double quotes so it expands. See SKILL.md "Credentials" for the fail-loud resolver.
> Version header: `Version: 2021-04-15` (required on all calls)

---

### Module: invoices

#### GET /invoices/ - List invoices
- Description: API to get list of invoices
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices.readonly
- Required headers: Version
- Required path params: None
- Required query params: altId, altType, limit, offset
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/invoices/
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/invoices/' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /invoices/ - Create Invoice
- Description: API to create an invoice
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/invoices/
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/invoices/' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /invoices/estimate - Create New Estimate
- Description: Create a new estimate with the provided details
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/estimate.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/invoices/estimate
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/invoices/estimate' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /invoices/estimate/list - List Estimates
- Description: Get a paginated list of estimates
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/estimate.readonly
- Required headers: Version
- Required path params: None
- Required query params: altId, altType, limit, offset
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/invoices/estimate/list
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/invoices/estimate/list' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /invoices/estimate/number/generate - Generate Estimate Number
- Description: Get the next estimate number for the given location
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/estimate.readonly
- Required headers: Version
- Required path params: None
- Required query params: altId, altType
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/invoices/estimate/number/generate
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/invoices/estimate/number/generate' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PATCH /invoices/estimate/stats/last-visited-at - Update estimate last visited at
- Description: API to update estimate last visited at by estimate id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: Not explicitly listed
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PATCH
  - URL: https://services.leadconnectorhq.com/invoices/estimate/stats/last-visited-at
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PATCH 'https://services.leadconnectorhq.com/invoices/estimate/stats/last-visited-at' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /invoices/estimate/template - List Estimate Templates
- Description: Get a list of estimate templates or a specific template by ID
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/estimate.readonly
- Required headers: Version
- Required path params: None
- Required query params: altId, altType, limit, offset
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/invoices/estimate/template
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/invoices/estimate/template' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /invoices/estimate/template - Create Estimate Template
- Description: Create a new estimate template
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/estimate.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/invoices/estimate/template
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/invoices/estimate/template' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /invoices/estimate/template/preview - Preview Estimate Template
- Description: Get a preview of an estimate template
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/estimate.readonly
- Required headers: Version
- Required path params: None
- Required query params: altId, altType, templateId
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/invoices/estimate/template/preview
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/invoices/estimate/template/preview' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /invoices/estimate/template/{templateId} - Update Estimate Template
- Description: Update an existing estimate template
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/estimate.write
- Required headers: Version
- Required path params: templateId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/invoices/estimate/template/{templateId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/invoices/estimate/template/{templateId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /invoices/estimate/template/{templateId} - Delete Estimate Template
- Description: Delete an existing estimate template
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/estimate.write
- Required headers: Version
- Required path params: templateId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/invoices/estimate/template/{templateId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/invoices/estimate/template/{templateId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /invoices/estimate/{estimateId} - Update Estimate
- Description: Update an existing estimate with new details
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/estimate.write
- Required headers: Version
- Required path params: estimateId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/invoices/estimate/{estimateId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/invoices/estimate/{estimateId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /invoices/estimate/{estimateId} - Delete Estimate
- Description: Delete an existing estimate
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/estimate.write
- Required headers: Version
- Required path params: estimateId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/invoices/estimate/{estimateId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/invoices/estimate/{estimateId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /invoices/estimate/{estimateId}/invoice - Create Invoice from Estimate
- Description: Create a new invoice from an existing estimate
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/estimate.write
- Required headers: Version
- Required path params: estimateId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/invoices/estimate/{estimateId}/invoice
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/invoices/estimate/{estimateId}/invoice' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /invoices/estimate/{estimateId}/send - Send Estimate
- Description: API to send estimate by estimate id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/estimate.write
- Required headers: Version
- Required path params: estimateId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/invoices/estimate/{estimateId}/send
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/invoices/estimate/{estimateId}/send' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /invoices/generate-invoice-number - Generate Invoice Number
- Description: Get the next invoice number for the given location
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices.readonly
- Required headers: Version
- Required path params: None
- Required query params: altId, altType
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/invoices/generate-invoice-number
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/invoices/generate-invoice-number' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /invoices/schedule - List schedules
- Description: API to get list of schedules
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/schedule.readonly
- Required headers: Version
- Required path params: None
- Required query params: altId, altType, limit, offset
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/invoices/schedule
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/invoices/schedule' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /invoices/schedule - Create Invoice Schedule
- Description: API to create an invoice Schedule
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/schedule.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/invoices/schedule
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/invoices/schedule' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /invoices/schedule/{scheduleId} - Get an schedule
- Description: API to get an schedule by schedule id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/schedule.readonly
- Required headers: Version
- Required path params: scheduleId
- Required query params: altId, altType
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/invoices/schedule/{scheduleId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/invoices/schedule/{scheduleId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /invoices/schedule/{scheduleId} - Update schedule
- Description: API to update an schedule by schedule id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/schedule.write
- Required headers: Version
- Required path params: scheduleId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/invoices/schedule/{scheduleId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/invoices/schedule/{scheduleId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /invoices/schedule/{scheduleId} - Delete schedule
- Description: API to delete an schedule by schedule id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/schedule.write
- Required headers: Version
- Required path params: scheduleId
- Required query params: altId, altType
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/invoices/schedule/{scheduleId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/invoices/schedule/{scheduleId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /invoices/schedule/{scheduleId}/auto-payment - Manage Auto payment for an schedule invoice
- Description: API to manage auto payment for a schedule
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/schedule.write
- Required headers: Version
- Required path params: scheduleId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/invoices/schedule/{scheduleId}/auto-payment
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/invoices/schedule/{scheduleId}/auto-payment' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /invoices/schedule/{scheduleId}/cancel - Cancel an scheduled invoice
- Description: API to cancel a scheduled invoice by schedule id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/schedule.write
- Required headers: Version
- Required path params: scheduleId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/invoices/schedule/{scheduleId}/cancel
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/invoices/schedule/{scheduleId}/cancel' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /invoices/schedule/{scheduleId}/schedule - Schedule an schedule invoice
- Description: API to schedule an schedule invoice to start sending to the customer
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/schedule.write
- Required headers: Version
- Required path params: scheduleId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/invoices/schedule/{scheduleId}/schedule
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/invoices/schedule/{scheduleId}/schedule' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /invoices/schedule/{scheduleId}/updateAndSchedule - Update scheduled recurring invoice
- Description: API to update scheduled recurring invoice
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/schedule.write
- Required headers: Version
- Required path params: scheduleId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/invoices/schedule/{scheduleId}/updateAndSchedule
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/invoices/schedule/{scheduleId}/updateAndSchedule' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PATCH /invoices/stats/last-visited-at - Update invoice last visited at
- Description: API to update invoice last visited at by invoice id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: Not explicitly listed
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PATCH
  - URL: https://services.leadconnectorhq.com/invoices/stats/last-visited-at
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PATCH 'https://services.leadconnectorhq.com/invoices/stats/last-visited-at' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /invoices/template - List templates
- Description: API to get list of templates
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/template.readonly
- Required headers: Version
- Required path params: None
- Required query params: altId, altType, limit, offset
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/invoices/template
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/invoices/template' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /invoices/template - Create template
- Description: API to create a template
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/template.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/invoices/template
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/invoices/template' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /invoices/template/{templateId} - Get an template
- Description: API to get an template by template id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/template.readonly
- Required headers: Version
- Required path params: templateId
- Required query params: altId, altType
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/invoices/template/{templateId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/invoices/template/{templateId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /invoices/template/{templateId} - Update template
- Description: API to update an template by template id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/template.write
- Required headers: Version
- Required path params: templateId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/invoices/template/{templateId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/invoices/template/{templateId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /invoices/template/{templateId} - Delete template
- Description: API to update an template by template id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices/template.write
- Required headers: Version
- Required path params: templateId
- Required query params: altId, altType
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/invoices/template/{templateId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/invoices/template/{templateId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PATCH /invoices/template/{templateId}/late-fees-configuration - Update template late fees configuration
- Description: API to update template late fees configuration by template id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: Not explicitly listed
- Required headers: Version
- Required path params: templateId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PATCH
  - URL: https://services.leadconnectorhq.com/invoices/template/{templateId}/late-fees-configuration
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PATCH 'https://services.leadconnectorhq.com/invoices/template/{templateId}/late-fees-configuration' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PATCH /invoices/template/{templateId}/payment-methods-configuration - Update template late fees configuration
- Description: API to update template late fees configuration by template id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: Not explicitly listed
- Required headers: Version
- Required path params: templateId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PATCH
  - URL: https://services.leadconnectorhq.com/invoices/template/{templateId}/payment-methods-configuration
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PATCH 'https://services.leadconnectorhq.com/invoices/template/{templateId}/payment-methods-configuration' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /invoices/text2pay - Create & Send
- Description: API to create or update a text2pay invoice
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: invoices.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/invoices/text2pay
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/invoices/text2pay' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /invoices/{invoiceId} - Get invoice
- Description: API to get invoice by invoice id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices.readonly
- Required headers: Version
- Required path params: invoiceId
- Required query params: altId, altType
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/invoices/{invoiceId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/invoices/{invoiceId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /invoices/{invoiceId} - Update invoice
- Description: API to update invoice by invoice id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices.write
- Required headers: Version
- Required path params: invoiceId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/invoices/{invoiceId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/invoices/{invoiceId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /invoices/{invoiceId} - Delete invoice
- Description: API to delete invoice by invoice id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices.write
- Required headers: Version
- Required path params: invoiceId
- Required query params: altId, altType
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/invoices/{invoiceId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/invoices/{invoiceId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PATCH /invoices/{invoiceId}/late-fees-configuration - Update invoice late fees configuration
- Description: API to update invoice late fees configuration by invoice id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: Not explicitly listed
- Required headers: Version
- Required path params: invoiceId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PATCH
  - URL: https://services.leadconnectorhq.com/invoices/{invoiceId}/late-fees-configuration
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PATCH 'https://services.leadconnectorhq.com/invoices/{invoiceId}/late-fees-configuration' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /invoices/{invoiceId}/record-payment - Record a manual payment for an invoice
- Description: API to record manual payment for an invoice by invoice id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices.write
- Required headers: Version
- Required path params: invoiceId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/invoices/{invoiceId}/record-payment
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/invoices/{invoiceId}/record-payment' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /invoices/{invoiceId}/send - Send invoice
- Description: API to send invoice by invoice id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices.write
- Required headers: Version
- Required path params: invoiceId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/invoices/{invoiceId}/send
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/invoices/{invoiceId}/send' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /invoices/{invoiceId}/void - Void invoice
- Description: API to delete invoice by invoice id
- Security: Location-Access, Agency-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: invoices.write
- Required headers: Version
- Required path params: invoiceId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/invoices/{invoiceId}/void
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/invoices/{invoiceId}/void' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security


### Module: payments

#### GET /payments/coupon - Fetch Coupon
- Description: The "Get Coupon Details" API enables you to retrieve comprehensive information about a specific coupon using either its unique identifier or promotional code. Use this endpoint to view coupon parameters, usage statistics, validity periods, and other promotional details.
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/coupons.readonly
- Required headers: Version
- Required path params: None
- Required query params: altId, altType, id, code
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/payments/coupon
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/payments/coupon' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /payments/coupon - Create Coupon
- Description: The "Create Coupon" API allows you to create a new promotional coupon with customizable parameters such as discount amount, validity period, usage limits, and applicable products. Use this endpoint to set up promotional offers and special discounts for your customers.
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/coupons.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/payments/coupon
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/payments/coupon' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /payments/coupon - Update Coupon
- Description: The "Update Coupon" API enables you to modify existing coupon details such as discount values, validity periods, usage limits, and other promotional parameters. Use this endpoint to adjust or extend promotional offers for your customers.
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/coupons.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/payments/coupon
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/payments/coupon' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /payments/coupon - Delete Coupon
- Description: The "Delete Coupon" API allows you to permanently remove a coupon from your system using its unique identifier. Use this endpoint to discontinue promotional offers or clean up unused coupons. Note that this action cannot be undone.
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/coupons.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/payments/coupon
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/payments/coupon' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /payments/coupon/list - List Coupons
- Description: The "List Coupons" API allows you to retrieve a list of all coupons available in your location. Use this endpoint to view all promotional offers and special discounts for your customers.
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/coupons.readonly
- Required headers: Version
- Required path params: None
- Required query params: altId, altType
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/payments/coupon/list
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/payments/coupon/list' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /payments/custom-provider/capabilities - Custom-provider marketplace app update capabilities
- Description: Toggle capabilities for the marketplace app tied to the OAuth client
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/custom-provider.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/payments/custom-provider/capabilities
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/payments/custom-provider/capabilities' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /payments/custom-provider/connect - Fetch given provider config
- Description: API for fetching an existing payment config for given location
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/custom-provider.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/payments/custom-provider/connect
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/payments/custom-provider/connect' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /payments/custom-provider/connect - Create new provider config
- Description: API to create a new payment config for given location
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/custom-provider.write
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/payments/custom-provider/connect
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/payments/custom-provider/connect' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /payments/custom-provider/disconnect - Disconnect existing provider config
- Description: API to disconnect an existing payment config for given location
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/custom-provider.write
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/payments/custom-provider/disconnect
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/payments/custom-provider/disconnect' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /payments/custom-provider/provider - Create new integration
- Description: API to create a new association for an app and location
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/custom-provider.write
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/payments/custom-provider/provider
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/payments/custom-provider/provider' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /payments/custom-provider/provider - Deleting an existing integration
- Description: API to delete an association for an app and location
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/custom-provider.write
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/payments/custom-provider/provider
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/payments/custom-provider/provider' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /payments/integrations/provider/whitelabel - List White-label Integration Providers
- Description: The "List White-label Integration Providers" API allows to retrieve a paginated list of integration providers. Customize your results by filtering whitelabel integration providers(which are built directly on top of Authorize.net or NMI) based on name or paginate through the list using the provided query parameters. This endpoint provides a straight
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/integration.readonly
- Required headers: Version
- Required path params: None
- Required query params: altId, altType
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/payments/integrations/provider/whitelabel
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/payments/integrations/provider/whitelabel' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /payments/integrations/provider/whitelabel - Create White-label Integration Provider
- Description: The "Create White-label Integration Provider" API allows adding a new payment provider integration to the system which is built on top of Authorize.net or NMI. Use this endpoint to create a integration provider with the specified details. Ensure that the required information is provided in the request payload. This endpoint can be only invoked usin
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/integration.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/payments/integrations/provider/whitelabel
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/payments/integrations/provider/whitelabel' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /payments/orders - List Orders
- Description: The "List Orders" API allows to retrieve a paginated list of orders. Customize your results by filtering orders based on name, alt type, order status, payment mode, date range, type of source, contact, funnel products or paginate through the list using the provided query parameters. This endpoint provides a straightforward way to explore and retrie
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/orders.readonly
- Required headers: Version
- Required path params: None
- Required query params: altId, altType
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/payments/orders
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/payments/orders' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /payments/orders/migrate-order-ps - migration Endpoint for Order Payment Status
- Description: Process to migrate all the older orders and based on the statuses introduce the payment statuses as well
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: Not explicitly listed
- Required headers: Version
- Required path params: None
- Required query params: altId
- Required body fields: None 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/payments/orders/migrate-order-ps
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/payments/orders/migrate-order-ps' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /payments/orders/{orderId} - Get Order by ID
- Description: The "Get Order by ID" API allows to retrieve information for a specific order using its unique identifier. Use this endpoint to fetch details for a single order based on the provided order ID.
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/orders.readonly
- Required headers: Version
- Required path params: orderId
- Required query params: altId
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/payments/orders/{orderId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/payments/orders/{orderId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /payments/orders/{orderId}/fulfillments - List fulfillment
- Description: List all fulfillment history of an order
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/orders.readonly
- Required headers: Version
- Required path params: orderId
- Required query params: altId, altType
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/payments/orders/{orderId}/fulfillments
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/payments/orders/{orderId}/fulfillments' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /payments/orders/{orderId}/fulfillments - Create order fulfillment
- Description: The "Order Fulfillment" API facilitates the process of fulfilling an order.
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/orders.write
- Required headers: Version
- Required path params: orderId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/payments/orders/{orderId}/fulfillments
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/payments/orders/{orderId}/fulfillments' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /payments/orders/{orderId}/notes - List Order Notes
- Description: List all notes of an order
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: Not explicitly listed
- Required headers: Version
- Required path params: orderId
- Required query params: altId, altType
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/payments/orders/{orderId}/notes
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/payments/orders/{orderId}/notes' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /payments/orders/{orderId}/record-payment - Record Order Payment
- Description: The "Record Order Payment" API allows to record a payment for an order. Use this endpoint to record payment for an order and update the order status to "Paid".
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/orders.collectPayment
- Required headers: Version
- Required path params: orderId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/payments/orders/{orderId}/record-payment
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/payments/orders/{orderId}/record-payment' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /payments/subscriptions - List Subscriptions
- Description: The "List Subscriptions" API allows to retrieve a paginated list of subscriptions. Customize your results by filtering subscriptions based on name, alt type, subscription status, payment mode, date range, type of source, contact, subscription id, entity id, contact or paginate through the list using the provided query parameters. This endpoint prov
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/subscriptions.readonly
- Required headers: Version
- Required path params: None
- Required query params: altId, altType
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/payments/subscriptions
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/payments/subscriptions' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /payments/subscriptions/{subscriptionId} - Get Subscription by ID
- Description: The "Get Subscription by ID" API allows to retrieve information for a specific subscription using its unique identifier. Use this endpoint to fetch details for a single subscription based on the provided subscription ID.
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/subscriptions.readonly
- Required headers: Version
- Required path params: subscriptionId
- Required query params: altId, altType
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/payments/subscriptions/{subscriptionId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/payments/subscriptions/{subscriptionId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /payments/transactions - List Transactions
- Description: The "List Transactions" API allows to retrieve a paginated list of transactions. Customize your results by filtering transactions based on name, alt type, transaction status, payment mode, date range, type of source, contact, subscription id, entity id or paginate through the list using the provided query parameters. This endpoint provides a straig
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/transactions.readonly
- Required headers: Version
- Required path params: None
- Required query params: altId, altType
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/payments/transactions
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/payments/transactions' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /payments/transactions/{transactionId} - Get Transaction by ID
- Description: The "Get Transaction by ID" API allows to retrieve information for a specific transaction using its unique identifier. Use this endpoint to fetch details for a single transaction based on the provided transaction ID.
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: payments/transactions.readonly
- Required headers: Version
- Required path params: transactionId
- Required query params: altId, altType
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/payments/transactions/{transactionId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/payments/transactions/{transactionId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

