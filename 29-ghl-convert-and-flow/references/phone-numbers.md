# GHL Phone Number Management API Reference

> **Scope of this file:** All endpoints under the `phone-system` module.
> Covers: phone number search, purchase, release, and configuration.
> Base URL: `https://services.leadconnectorhq.com`
> Auth: `Authorization: Bearer $GOHIGHLEVEL_API_KEY` — the LOCATION PIT from `~/.openclaw/secrets/.env`. In the cURL templates below, substitute `$GOHIGHLEVEL_API_KEY` for `<PRIVATE_INTEGRATION_TOKEN>` and use double quotes so it expands. See SKILL.md "Credentials" for the fail-loud resolver.
> Version header: `Version: 2021-04-15` (required on all calls)

> **IMPORTANT:** Phone number removal and release is a TREVOR-ONLY action.
> The agent may read and search phone number data but must NEVER release or remove numbers autonomously.
> Flag to Trevor and wait for his instruction before any destructive phone number action.

---

### Module: phone-system

#### GET /phone-system/number-pools - List Number Pools
- Description: Get list of number pools
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: numberpools.read
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/phone-system/number-pools
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/phone-system/number-pools' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /phone-system/numbers/location/{locationId} - List active numbers
- Description: Retrieve a paginated list of active phone numbers for a specific location. Supports filtering, pagination, and optional exclusion of number pool assignments.
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: phonenumbers.read
- Required headers: Version
- Required path params: locationId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/phone-system/numbers/location/{locationId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/phone-system/numbers/location/{locationId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

