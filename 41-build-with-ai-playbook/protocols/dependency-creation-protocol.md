# Dependency Creation Protocol -- Skill 41

## Purpose

Specifies how to create tags, custom fields, and custom values via the GHL API v2 BEFORE a workflow references them. The Workflow AI Builder inserts placeholder syntax but does NOT create the underlying objects.

## Creation order

1. Custom Fields (define schema first)
2. Custom Values (global merge data)
3. Tags (segmentation labels)

## API endpoints

```
Base URL: https://services.leadconnectorhq.com
Headers for all calls:
  Authorization: Bearer ${GOHIGHLEVEL_API_KEY}
  Version: 2021-07-28
  Content-Type: application/json

# Create tag
POST /locations/{locationId}/tags
Body: {"name": "ZHC-new-lead"}
Scope: locations/tags.write

# List tags (to check existence)
GET /locations/{locationId}/tags?limit=100

# Create custom field
POST /locations/{locationId}/customFields
Body: {"name": "ZHC_lead_source", "dataType": "text", "group": "contact"}
Scope: locations/customFields.write

# List custom fields
GET /locations/{locationId}/customFields?limit=100

# Create custom value
POST /locations/{locationId}/customValues
Body: {"name": "office_phone", "value": "+1 555 123 4567", "folderId": "optional"}
Scope: locations/customValues.write

# List custom values
GET /locations/{locationId}/customValues?limit=100
```

## Data types for custom fields

| dataType | Meaning | Example values |
|---|---|---|
| text | Free-form string | "Hello world" |
| number | Numeric | 42, 3.14 |
| date | ISO-8601 date | "2026-05-30" |
| dropdown | Single select | Must match predefined options |
| checkbox | Boolean | true / false |
| textarea | Multi-line text | "Line 1\nLine 2" |
| url | URL string | "https://example.com" |
| phone | Phone number | "+1 555 123 4567" |
| email | Email address | "test@example.com" |

## ZHC prefix rules

- Agent-created tags: ZHC- prefix (e.g., ZHC-new-lead, ZHC-welcome-sent)
- Agent-created custom fields: ZHC_ prefix (e.g., ZHC_lead_source, ZHC_appointment_date)
- Agent-created custom values: no prefix required (they are global merge fields)

## Verification after creation

After each POST, verify with GET:
1. GET the list endpoint
2. Confirm the new object appears in the response
3. Confirm the name and type are correct
4. If GET fails, retry once after 2 seconds
5. If still failing, surface to operator: "Created [object] but verification failed. Please check manually."

## Idempotency

Before creating, always GET first:
- If the object exists with the correct name and type, skip creation
- If the object exists but type differs, surface to operator for decision
- If the object does not exist, create it

## Error handling

| Error | Meaning | Action |
|---|---|---|
| 400 Bad Request | Invalid body shape or missing required field | Check body against docs, retry with fix |
| 401 Unauthorized | PIT invalid or expired | Surface to operator: re-auth needed |
| 403 Forbidden | Scope missing for this location | Surface to operator: check PIT scopes |
| 409 Conflict | Object already exists (name collision) | GET to confirm, skip if identical, surface if different |
| 429 Rate Limited | Too many requests | Back off 10s, retry with exponential backoff |
| 500/502/503 | GHL server error | Retry once after 5s, then surface |

## Logging

Emit one dependency_created event per object to build-with-ai-events.jsonl:

```
{
  "ts": "2026-05-30T20:00:00Z",
  "skill": "41-build-with-ai-playbook",
  "event": "dependency_created",
  "session_ref": "sess_xxxx",
  "source": "api_response",
  "object_type": "tag",
  "object_name": "ZHC-new-lead",
  "zhc_prefixed": true
}
```
