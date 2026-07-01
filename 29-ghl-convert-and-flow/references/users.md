# GHL Users + Permissions API Reference

> **Scope of this file:** All endpoints under the `users` module.
> Covers: user CRUD, roles, permissions, team management.
> Base URL: `https://services.leadconnectorhq.com`
> Auth: `Authorization: Bearer $GOHIGHLEVEL_API_KEY` — the LOCATION PIT from `~/.openclaw/secrets/.env`. In the cURL templates below, substitute `$GOHIGHLEVEL_API_KEY` for `<PRIVATE_INTEGRATION_TOKEN>` and use double quotes so it expands. See SKILL.md "Credentials" for the fail-loud resolver.
> Version header: `Version: 2021-04-15` (required on all calls)

---

### Module: users

#### GET /users/ - Get User by Location
- Description: Get User by Location
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: users.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/users/
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/users/' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /users/ - Create User
- Description: Create User
- Security: Agency-Access, Location-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: users.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/users/
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/users/' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /users/search - Search Users
- Description: Search Users
- Security: Agency-Access, Location-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: users.readonly
- Required headers: Version
- Required path params: None
- Required query params: companyId
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/users/search
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/users/search' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /users/search/filter-by-email - Filter Users by Email
- Description: Filter users by company ID, deleted status, and email array
- Security: Agency-Access, Location-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: users.readonly
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/users/search/filter-by-email
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/users/search/filter-by-email' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /users/{userId} - Get User
- Description: Get User
- Security: Agency-Access, Location-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: users.readonly
- Required headers: Version
- Required path params: userId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/users/{userId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/users/{userId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /users/{userId} - Update User
- Description: Update User
- Security: Agency-Access, Location-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: users.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/users/{userId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/users/{userId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /users/{userId} - Delete User
- Description: Delete User
- Security: Agency-Access, Location-Access
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: users.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/users/{userId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/users/{userId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

