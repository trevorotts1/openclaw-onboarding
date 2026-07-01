# GHL Calendars + Appointments API Reference

> **Scope of this file:** All endpoints under the `calendars` module (calendars, appointments, slots, groups, resources).
> Base URL: `https://services.leadconnectorhq.com`
> Auth: `Authorization: Bearer $GOHIGHLEVEL_API_KEY` — the LOCATION PIT from `~/.openclaw/secrets/.env`. In the cURL templates below, substitute `$GOHIGHLEVEL_API_KEY` for `<PRIVATE_INTEGRATION_TOKEN>` and use double quotes so it expands. See SKILL.md "Credentials" for the fail-loud resolver.
> Version header: `Version: 2021-04-15` (required on all calls)

---

### Module: calendars

#### GET /calendars/ - Get Calendars
- Description: Get all calendars in a location.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/calendars/
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/calendars/' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /calendars/ - Create Calendar
- Description: Create calendar in a location.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/calendars/
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/calendars/' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /calendars/appointments/{appointmentId}/notes - Get Notes
- Description: Get Appointment Notes
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/events.readonly
- Required headers: Version
- Required path params: appointmentId
- Required query params: limit, offset
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/calendars/appointments/{appointmentId}/notes
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/calendars/appointments/{appointmentId}/notes' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /calendars/appointments/{appointmentId}/notes - Create Note
- Description: Create Note
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/events.write
- Required headers: Version
- Required path params: appointmentId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/calendars/appointments/{appointmentId}/notes
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/calendars/appointments/{appointmentId}/notes' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /calendars/appointments/{appointmentId}/notes/{noteId} - Update Note
- Description: Update Note
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/events.write
- Required headers: Version
- Required path params: appointmentId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/calendars/appointments/{appointmentId}/notes/{noteId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/calendars/appointments/{appointmentId}/notes/{noteId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /calendars/appointments/{appointmentId}/notes/{noteId} - Delete Note
- Description: Delete Note
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/events.write
- Required headers: Version
- Required path params: appointmentId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/calendars/appointments/{appointmentId}/notes/{noteId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/calendars/appointments/{appointmentId}/notes/{noteId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /calendars/blocked-slots - Get Blocked Slots
- Description: Get Blocked Slots
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/events.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId, startTime, endTime
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/calendars/blocked-slots
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/calendars/blocked-slots' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /calendars/events - Get Calendar Events
- Description: Get Calendar Events
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/events.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId, startTime, endTime
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/calendars/events
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/calendars/events' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /calendars/events/appointments - Create appointment
- Description: Create appointment
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/events.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/calendars/events/appointments
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/calendars/events/appointments' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /calendars/events/appointments/{eventId} - Get Appointment
- Description: Get appointment by ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/events.readonly
- Required headers: Version
- Required path params: eventId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/calendars/events/appointments/{eventId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/calendars/events/appointments/{eventId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /calendars/events/appointments/{eventId} - Update Appointment
- Description: Update appointment
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/events.write
- Required headers: Version
- Required path params: eventId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/calendars/events/appointments/{eventId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/calendars/events/appointments/{eventId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /calendars/events/block-slots - Create Block Slot
- Description: Create block slot
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/events.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/calendars/events/block-slots
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/calendars/events/block-slots' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /calendars/events/block-slots/{eventId} - Update Block Slot
- Description: Update block slot by ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/events.write
- Required headers: Version
- Required path params: eventId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/calendars/events/block-slots/{eventId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/calendars/events/block-slots/{eventId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /calendars/events/{eventId} - Delete Event
- Description: Delete event by ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/events.write
- Required headers: Version
- Required path params: eventId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/calendars/events/{eventId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/calendars/events/{eventId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /calendars/groups - Get Groups
- Description: Get all calendar groups in a location.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/groups.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/calendars/groups
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/calendars/groups' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /calendars/groups - Create Calendar Group
- Description: Create Calendar Group
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/groups.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/calendars/groups
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/calendars/groups' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /calendars/groups/validate-slug - Validate group slug
- Description: Validate if group slug is available or not.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/groups.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/calendars/groups/validate-slug
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/calendars/groups/validate-slug' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /calendars/groups/{groupId} - Update Group
- Description: Update Group by group ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/groups.write
- Required headers: Version
- Required path params: groupId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/calendars/groups/{groupId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/calendars/groups/{groupId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /calendars/groups/{groupId} - Delete Group
- Description: Delete Group
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/groups.write
- Required headers: Version
- Required path params: groupId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/calendars/groups/{groupId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/calendars/groups/{groupId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /calendars/groups/{groupId}/status - Disable Group
- Description: Disable Group
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/groups.write
- Required headers: Version
- Required path params: groupId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/calendars/groups/{groupId}/status
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/calendars/groups/{groupId}/status' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /calendars/resources/{resourceType} - List Calendar Resources
- Description: List calendar resources by resource type and location ID
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: calendars/resources.readonly
- Required headers: Version
- Required path params: resourceType
- Required query params: locationId, limit, skip
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/calendars/resources/{resourceType}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/calendars/resources/{resourceType}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /calendars/resources/{resourceType} - Create Calendar Resource
- Description: Create calendar resource by resource type
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: calendars/resources.write
- Required headers: Version
- Required path params: resourceType
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/calendars/resources/{resourceType}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/calendars/resources/{resourceType}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /calendars/resources/{resourceType}/{id} - Get Calendar Resource
- Description: Get calendar resource by ID
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: calendars/resources.readonly
- Required headers: Version
- Required path params: resourceType, id
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/calendars/resources/{resourceType}/{id}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/calendars/resources/{resourceType}/{id}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /calendars/resources/{resourceType}/{id} - Update Calendar Resource
- Description: Update calendar resource by ID
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: calendars/resources.write
- Required headers: Version
- Required path params: resourceType, id
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/calendars/resources/{resourceType}/{id}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/calendars/resources/{resourceType}/{id}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /calendars/resources/{resourceType}/{id} - Delete Calendar Resource
- Description: Delete calendar resource by ID
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: calendars/resources.write
- Required headers: Version
- Required path params: resourceType, id
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/calendars/resources/{resourceType}/{id}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/calendars/resources/{resourceType}/{id}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /calendars/{calendarId} - Get Calendar
- Description: Get calendar by ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars.readonly
- Required headers: Version
- Required path params: calendarId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/calendars/{calendarId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/calendars/{calendarId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /calendars/{calendarId} - Update Calendar
- Description: Update calendar by ID.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars.write
- Required headers: Version
- Required path params: calendarId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/calendars/{calendarId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/calendars/{calendarId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /calendars/{calendarId} - Delete Calendar
- Description: Delete calendar by ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars.write
- Required headers: Version
- Required path params: calendarId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/calendars/{calendarId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/calendars/{calendarId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /calendars/{calendarId}/free-slots - Get Free Slots
- Description: Get free slots for a calendar between a date range. Optionally a consumer can also request free slots in a particular timezone and also for a particular user.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars.readonly
- Required headers: Version
- Required path params: calendarId
- Required query params: startDate, endDate
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/calendars/{calendarId}/free-slots
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/calendars/{calendarId}/free-slots' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /calendars/{calendarId}/notifications - Get notifications
- Description: Get calendar notifications based on query
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/events.readonly
- Required headers: Version
- Required path params: calendarId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/calendars/{calendarId}/notifications
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/calendars/{calendarId}/notifications' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /calendars/{calendarId}/notifications - Create notification
- Description: Create Calendar notifications, either one or multiple. All notification settings must be for single calendar only
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/events.write
- Required headers: Version
- Required path params: calendarId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/calendars/{calendarId}/notifications
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/calendars/{calendarId}/notifications' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /calendars/{calendarId}/notifications/{notificationId} - Get notification
- Description: Find Event notification by notificationId
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/events.readonly
- Required headers: Version
- Required path params: calendarId, notificationId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/calendars/{calendarId}/notifications/{notificationId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/calendars/{calendarId}/notifications/{notificationId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /calendars/{calendarId}/notifications/{notificationId} - Update notification
- Description: Update Event notification by id
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/events.write
- Required headers: Version
- Required path params: calendarId, notificationId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/calendars/{calendarId}/notifications/{notificationId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/calendars/{calendarId}/notifications/{notificationId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /calendars/{calendarId}/notifications/{notificationId} - Delete Notification
- Description: Delete notification
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: calendars/events.write
- Required headers: Version
- Required path params: calendarId, notificationId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/calendars/{calendarId}/notifications/{notificationId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/calendars/{calendarId}/notifications/{notificationId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

