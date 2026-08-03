# opportunities.md - Opportunities Module Reference (12 Endpoints)

Base URL: `https://services.leadconnectorhq.com`
Required on all calls: `Authorization: Bearer $GOHIGHLEVEL_API_KEY` and `Version: 2021-07-28`

> **Version is per-OPERATION, and FIVE versions are supported concurrently** — `v3`
> (June 11, 2026), `2023-02-21`, `2021-07-28`, `2021-04-15` and `legacy`, every one
> "Supported until: **TBD**". An older supported version is NOT a defect; only a blanket
> "one value for everything" rule is.
> `2021-07-28` is the pre-v3 default (32 of 41 specs exclusively, 33 accept it). The ONLY
> apps on `2021-04-15` are: agent-studio, calendars, conversation-ai, conversations,
> knowledge-base, saas-api, voice-ai. `links` accepts both; `store` declares none.
> Full rule + v3 capability: `references/api-generations.md`.
> Sources: `https://marketplace.gohighlevel.com/docs/Versioning/` and the per-app specs
> (verified 2026-08-03). ⚠ The spec repo lags the live docs — check the docs site first.

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

### Pipeline CRUD — LIVE under `Version: v3`

All four operations are documented on HighLevel's live docs site. They are absent from the
OpenAPI spec files only because that repo lags (announced 2026-06-26; specs last synced
2026-05-01 and 2026-06-19).

```
POST   /opportunities/pipelines                 Version: v3
GET    /opportunities/pipelines/{pipelineId}    Version: v3   (also answers under 2021-07-28)
PUT    /opportunities/pipelines/{pipelineId}    Version: v3
DELETE /opportunities/pipelines/{pipelineId}    Version: v3
```
Scopes: `opportunities.readonly` / `opportunities.write`.

**Create** — `https://marketplace.gohighlevel.com/docs/ghl/opportunities/create-pipeline`
Requires at least one stage. Pipeline names must be unique per location (case-insensitive);
stage names unique within the pipeline. For manual win probability set
`useOpportunityProbability: true` **and** give every stage a `stageWinProbability` (0–100) —
if any stage is missing one, the system silently falls back to auto-computed probabilities
based on stage position.

**Update** — `.../docs/ghl/opportunities/update-pipeline/index.html`
⚠ The `stages` array is a **complete replacement**, not a patch:
- include a stage's `id` to keep it
- omit `id` to create a new stage
- **omit a stage entirely and it is deleted**
- you cannot remove all stages
- opportunities in a deleted stage move to the lowest-ranked remaining stage

**Delete** — `.../docs/ghl/opportunities/delete-pipeline/index.html`
🔴 **Permanently deletes the pipeline AND every opportunity in it, across every stage.
Irreversible.** Export or migrate first. Treat as a TREVOR-ONLY action.

> **PROVEN live 2026-08-03:** `GET /opportunities/pipelines/{pipelineId}` returns 200 under
> both `2021-07-28` and `v3`. The three write operations were **not** probed — this audit
> made no write calls against GoHighLevel. Make one controlled test call before automating.

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
  -H "Version: 2021-07-28" | jq '.pipelines[] | {id, name, stages: [.stages[] | {id, name}]}'

# 2. Create an opportunity
PIPELINE_ID="your_pipeline_id"
STAGE_ID="your_stage_id"
CONTACT_ID="your_contact_id"

curl -s \
  "https://services.leadconnectorhq.com/opportunities/" \
  -X POST \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28" \
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
  -H "Version: 2021-07-28" \
  -H "Content-Type: application/json" \
  -d '{"pipelineStageId": "'"$NEXT_STAGE_ID"'"}' | jq .

# 4. Mark as won
curl -s \
  "https://services.leadconnectorhq.com/opportunities/$OPP_ID/status" \
  -X PUT \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28" \
  -H "Content-Type: application/json" \
  -d '{"status": "won"}' | jq .
```
