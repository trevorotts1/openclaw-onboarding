# opportunities.md - Opportunities Module Reference (10 Endpoints)

Base URL: `https://services.leadconnectorhq.com`
Required on all calls: `Authorization: Bearer $GOHIGHLEVEL_API_KEY` and `Version: 2021-04-15`

---

## Pipelines

### Get All Pipelines
```
GET /opportunities/pipelines
Scopes: opportunities.readonly
Query: locationId (required)
```
Returns all pipelines with their stages. Each pipeline has `id`, `name`, `stages` array.

Each stage has: `id`, `name`, `position`

---

## Opportunities (Deals)

### Search Opportunities
```
GET /opportunities/search
Scopes: opportunities.readonly
Query:
  location_id (required)
  pipeline_id (optional)
  stage_id (optional)
  status (optional): "open" | "won" | "lost" | "abandoned"
  assigned_to (optional): user ID
  limit (optional)
  page (optional)
  query (optional): search string
```

### Create Opportunity
```
POST /opportunities/
Scopes: opportunities.write
Body:
  pipelineId (required)
  locationId (required)
  name (required)
  pipelineStageId (required)
  status: "open" | "won" | "lost" | "abandoned"
  contactId (optional)
  monetaryValue (optional): number
  assignedTo (optional): user ID
  customFields (optional): [{id, value}]
```

### Get Opportunity by ID
```
GET /opportunities/{id}
Scopes: opportunities.readonly
```

### Update Opportunity
```
PUT /opportunities/{id}
Scopes: opportunities.write
Body: fields to update (name, pipelineStageId, status, monetaryValue, etc.)
```

### Delete Opportunity
```
DELETE /opportunities/{id}
Scopes: opportunities.write
```

### Update Opportunity Status
```
PUT /opportunities/{id}/status
Scopes: opportunities.write
Body: { status: "won" | "lost" | "open" | "abandoned" }
```

### Upsert Opportunity
```
POST /opportunities/upsert
Scopes: opportunities.write
Body: opportunity fields - will create or update based on match
```

---

## Followers

### Add Followers to Opportunity
```
POST /opportunities/{id}/followers
Scopes: opportunities.write
Body: { followers: ["userId1", "userId2"] }
```

### Remove Followers from Opportunity
```
DELETE /opportunities/{id}/followers
Scopes: opportunities.write
Body: { followers: ["userId1"] }
```

---

## Opportunity Status Values

| Status | Meaning |
|--------|---------|
| `open` | Active deal in pipeline |
| `won` | Closed as won |
| `lost` | Closed as lost |
| `abandoned` | No longer being pursued |

---

## Common Opportunity Fields

| Field | Type | Notes |
|-------|------|-------|
| `pipelineId` | string | Required |
| `locationId` | string | Required |
| `name` | string | Deal name |
| `pipelineStageId` | string | Current stage ID |
| `status` | string | open/won/lost/abandoned |
| `contactId` | string | Associated contact |
| `monetaryValue` | number | Deal value in dollars |
| `assignedTo` | string | User ID |
| `customFields` | array | `[{id, value}]` |
| `source` | string | Lead source |
| `notes` | string | Deal notes |

---

## Common Workflow

```bash
source ~/.openclaw/secrets/.env

# 1. Get pipelines and stages
curl -s \
  "https://services.leadconnectorhq.com/opportunities/pipelines?locationId=$GOHIGHLEVEL_LOCATION_ID" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-04-15" | jq '.pipelines[] | {id, name, stages: [.stages[] | {id, name}]}'

# 2. Create an opportunity
PIPELINE_ID="your_pipeline_id"
STAGE_ID="your_stage_id"
CONTACT_ID="your_contact_id"

curl -s \
  "https://services.leadconnectorhq.com/opportunities/" \
  -X POST \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-04-15" \
  -H "Content-Type: application/json" \
  -d '{
    "pipelineId": "'"$PIPELINE_ID"'",
    "locationId": "'"$GOHIGHLEVEL_LOCATION_ID"'",
    "name": "Jane Doe - Consulting Package",
    "pipelineStageId": "'"$STAGE_ID"'",
    "status": "open",
    "contactId": "'"$CONTACT_ID"'",
    "monetaryValue": 2500
  }' | jq .

# 3. Move to next stage
OPP_ID="your_opportunity_id"
NEXT_STAGE_ID="next_stage_id"

curl -s \
  "https://services.leadconnectorhq.com/opportunities/$OPP_ID" \
  -X PUT \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-04-15" \
  -H "Content-Type: application/json" \
  -d '{"pipelineStageId": "'"$NEXT_STAGE_ID"'"}' | jq .

# 4. Mark as won
curl -s \
  "https://services.leadconnectorhq.com/opportunities/$OPP_ID/status" \
  -X PUT \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-04-15" \
  -H "Content-Type: application/json" \
  -d '{"status": "won"}' | jq .
```
