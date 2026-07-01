# locations.md - Locations Module Reference (29 Endpoints)

Base URL: `https://services.leadconnectorhq.com`
Required on all calls: `Authorization: Bearer $GOHIGHLEVEL_API_KEY` and `Version: 2021-04-15`

> In GHL v2, "Location" = "Sub-Account". These terms are interchangeable.

---

## Location / Sub-Account

### Search Locations
```
GET /locations/search
Scopes: locations.readonly
Note: Returns all locations your token has access to
```

### Get Location by ID
```
GET /locations/{locationId}
Scopes: locations.readonly
```

### Create Sub-Account
```
POST /locations/
Scopes: locations.write
Token type: Agency Token required (not standard location token)
Body: { name, phone, email, address, city, state, country, ... }
```

### Update Sub-Account
```
PUT /locations/{locationId}
Scopes: locations.write
Token type: Agency Token required
Body: fields to update
```

### Delete Sub-Account
```
DELETE /locations/{locationId}
Scopes: locations.write
Token type: Agency Token required
```

---

## Custom Fields

### Get Custom Fields
```
GET /locations/{locationId}/customFields
Scopes: locations/customFields.readonly
```

### Create Custom Field
```
POST /locations/{locationId}/customFields
Scopes: locations/customFields.write
Body:
  name (required)
  fieldKey (required): e.g., "contact.my_field"
  dataType: "TEXT" | "LARGE_TEXT" | "NUMERICAL" | "PHONE" | "MONETORY" | "CHECKBOX" | "SINGLE_OPTIONS" | "MULTIPLE_OPTIONS" | "DATE" | "TEXTBOX_LIST" | "FILE_UPLOAD" | "SIGNATURE"
  options (required for SINGLE_OPTIONS and MULTIPLE_OPTIONS): [{key, label}]
```

### Get Custom Field by ID
```
GET /locations/{locationId}/customFields/{id}
Scopes: locations/customFields.readonly
```

### Update Custom Field
```
PUT /locations/{locationId}/customFields/{id}
Scopes: locations/customFields.write
```

### Delete Custom Field
```
DELETE /locations/{locationId}/customFields/{id}
Scopes: locations/customFields.write
```

### Upload File for Custom Field
```
POST /locations/{locationId}/customFields/upload
Scopes: locations/customFields.write
Content-Type: multipart/form-data
```

---

## Custom Values

### Get Custom Values
```
GET /locations/{locationId}/customValues
Scopes: locations/customValues.readonly
```

### Create Custom Value
```
POST /locations/{locationId}/customValues
Scopes: locations/customValues.write
Body: { name, value }
```

### Get Custom Value by ID
```
GET /locations/{locationId}/customValues/{id}
Scopes: locations/customValues.readonly
```

### Update Custom Value
```
PUT /locations/{locationId}/customValues/{id}
Scopes: locations/customValues.write
Body: { name, value }
```

### Delete Custom Value
```
DELETE /locations/{locationId}/customValues/{id}
Scopes: locations/customValues.write
```

---

## Tags

### Get All Tags for Location
```
GET /locations/{locationId}/tags
Scopes: locations/tags.readonly
```

### Create Tag
```
POST /locations/{locationId}/tags
Scopes: locations/tags.write
Body: { name }
```

### Get Tag by ID
```
GET /locations/{locationId}/tags/{tagId}
Scopes: locations/tags.readonly
```

### Update Tag
```
PUT /locations/{locationId}/tags/{tagId}
Scopes: locations/tags.write
Body: { name }
```

### Delete Tag
```
DELETE /locations/{locationId}/tags/{tagId}
Scopes: locations/tags.write
```

---

## Templates

### Get Templates
```
GET /locations/{locationId}/templates
Scopes: locations/templates.readonly
Query: type (optional): "email" | "sms"
```

### Delete Template
```
DELETE /locations/{locationId}/templates/{id}
Scopes: locations/templates.write
```

---

## Tasks

### Search Tasks
```
POST /locations/{locationId}/tasks/search
Scopes: locations/tasks.readonly
Body: { filters }
```

---

## Recurring Tasks

### Create Recurring Task
```
POST /locations/{locationId}/recurring-tasks
Scopes: locations/tasks.write
```

### Get Recurring Task
```
GET /locations/{locationId}/recurring-tasks/{id}
Scopes: locations/tasks.readonly
```

### Update Recurring Task
```
PUT /locations/{locationId}/recurring-tasks/{id}
Scopes: locations/tasks.write
```

### Delete Recurring Task
```
DELETE /locations/{locationId}/recurring-tasks/{id}
Scopes: locations/tasks.write
```

---

## Utilities

### Get Timezones
```
GET /locations/{locationId}/timezones
Scopes: locations.readonly
```
Returns list of valid timezone strings for the location's region.

---

## Common Setup Workflow

```bash
source ~/.openclaw/secrets/.env

# 1. Find all accessible locations (sub-accounts)
curl -s \
  "https://services.leadconnectorhq.com/locations/search" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-04-15" | jq '.locations[] | {id, name}'

# 2. Get full details of a specific location
curl -s \
  "https://services.leadconnectorhq.com/locations/$GOHIGHLEVEL_LOCATION_ID" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-04-15" | jq .

# 3. Get all custom fields for the location
curl -s \
  "https://services.leadconnectorhq.com/locations/$GOHIGHLEVEL_LOCATION_ID/customFields" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-04-15" | jq '.customFields[] | {id, name, fieldKey, dataType}'

# 4. Get all tags
curl -s \
  "https://services.leadconnectorhq.com/locations/$GOHIGHLEVEL_LOCATION_ID/tags" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-04-15" | jq .
```

---

## Notes on Agency vs Location Tokens

| Endpoint | Token Needed |
|----------|-------------|
| Create/update/delete sub-account | Agency Token |
| Read location details | Private Integration Token (location-scoped) |
| Custom fields, tags, templates | Private Integration Token |
| SaaS bulk operations | Agency Token |

If you only have a location-level Private Integration Token, you can read and manage the location but cannot create or delete sub-accounts.
