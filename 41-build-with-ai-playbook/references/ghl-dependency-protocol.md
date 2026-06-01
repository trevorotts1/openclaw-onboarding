# GHL Dependency Protocol -- Skill 41 Reference

## Three Distinct Objects

### Tags
- Per-contact labels for segmentation
- API: POST /locations/:locationId/tags
- Scope: locations/tags.write
- Body: {"name": "ZHC-new-lead"}
- Used in: Contact Tag trigger, Add/Remove Contact Tag actions, If/Else conditions

### Custom Fields
- Per-contact data fields (text, number, dropdown, date)
- API: POST /locations/:locationId/customFields
- Scope: locations/customFields.write (Sub-Account Custom Field)
- Body: {"name": "ZHC_lead_source", "dataType": "text", "group": "contact"}
- Must be created BEFORE values can be set on contacts
- Used in: Update Contact Field action, If/Else conditions, merge fields

### Custom Values
- Global merge fields for the sub-account (not per-contact)
- API: POST /locations/:locationId/customValues
- Scope: locations/customValues.write (Sub-Account Custom Value)
- Body: {"name": "office_phone", "value": "+1 555 123 4567", "folderId": "optional"}
- Used in: templates, workflows via {{custom_values.<name>}} syntax
- The Workflow AI Builder inserts placeholder custom value syntax but does NOT create them

## Creation Order (Critical)

1. Create Custom Fields (define schema)
2. Create Custom Values (global merge data)
3. Create Tags (for segmentation)
4. THEN build the workflow (which references these objects)

## Why Order Matters

- Workflow AI Builder inserts {{custom_values.<name>}} placeholders
- If the custom value does not exist, the workflow will fail at runtime
- Tags referenced in Add Tag actions must exist or the action fails
- Custom fields referenced in Update Contact Field must exist
- The playbook must instruct: CREATE ALL DEPENDENCIES FIRST, THEN BUILD THE WORKFLOW

## ZHC Prefix Rules

- Agent-created tags: ZHC- prefix (e.g., ZHC-new-lead, ZHC-welcome-sent)
- Agent-created custom fields: ZHC_ prefix (e.g., ZHC_lead_source, ZHC_appointment_date)
- Agent-created custom values: no prefix required

## API Endpoints

```
Base URL: https://services.leadconnectorhq.com
Headers for all calls:
  Authorization: Bearer ${GOHIGHLEVEL_API_KEY}
  Version: 2021-07-28
  Content-Type: application/json

# Tags
POST /locations/{locationId}/tags
GET /locations/{locationId}/tags?limit=100

# Custom Fields
POST /locations/{locationId}/customFields
GET /locations/{locationId}/customFields?limit=100

# Custom Values
POST /locations/{locationId}/customValues
GET /locations/{locationId}/customValues?limit=100
```

## Data Types for Custom Fields

| dataType | Meaning | Example |
|---|---|---|
| text | Free-form string | "Hello world" |
| number | Numeric | 42 |
| date | ISO-8601 date | "2026-05-30" |
| dropdown | Single select | Must match options |
| checkbox | Boolean | true |
| textarea | Multi-line text | "Line 1\nLine 2" |
| url | URL string | "https://example.com" |
| phone | Phone number | "+1 555 123 4567" |
| email | Email address | "test@example.com" |
