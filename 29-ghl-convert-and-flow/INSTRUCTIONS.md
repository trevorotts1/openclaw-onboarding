# GHL API Skill - Usage Instructions

> How to use this skill to answer GHL questions and execute API calls.
> This file describes the complete workflow from user question to API execution.

---

## The Core Principle: Read-First, No-Memorize

The GHL API has 413 endpoints. Memorizing them wastes context window space.
This skill's approach: **identify the domain, read the reference file, build the call, execute.**

Never guess at endpoint syntax. Never invent parameters. Always read the reference file first.

---

## The Gemini Engine-First Workflow (4 Steps)

### Step 1 - Identify the Domain

When a user asks a GHL question, classify it into a domain:

| User Says | Domain | Reference File |
|-----------|--------|---------------|
| "add a contact", "find a contact", "update contact tags" | contacts | `references/contacts.md` |
| "send an SMS", "reply to message", "get conversations" | conversations | `references/conversations.md` |
| "move deal to closed", "create opportunity", "check pipeline" | opportunities | `references/opportunities.md` |
| "book appointment", "get available slots", "cancel booking" | calendars | `references/calendars.md` |
| "add to workflow", "trigger campaign" | campaigns | `references/campaigns.md` |
| "get location info", "update sub-account", "custom fields" | locations | `references/locations.md` |
| "create invoice", "send invoice", "record payment", "subscription" | payments | `references/payments.md` |
| "buy phone number", "list phone numbers" | phone-numbers | `references/phone-numbers.md` |
| "add user", "update permissions", "team member" | users | `references/users.md` |
| "webhook event", "inbound trigger", "what fired" | webhooks | `references/webhooks.md` |

---

### Step 2 - Read the Reference File

Read ONLY the specific reference file. Do not read the 430K master.

```
read references/contacts.md
```

Scan the file for:
- The endpoint that matches the task (e.g., `POST /contacts/` to create a contact)
- Required scopes (must be enabled in your Private Integration)
- Required headers (Authorization + Version always, others per endpoint)
- Required path params (e.g., `{contactId}`)
- Required query params (e.g., `locationId`)
- Required body fields
- The cURL template provided

---

### Step 3 - Build the API Call

Take the cURL template from the reference file and substitute real values:

```bash
# Template (from reference file)
curl --request POST 'https://services.leadconnectorhq.com/contacts/' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"firstName": "John", "lastName": "Smith", "locationId": "<locationId>"}'

# Substituted (ready to run)
curl --request POST 'https://services.leadconnectorhq.com/contacts/' \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d "{\"firstName\": \"John\", \"lastName\": \"Smith\", \"locationId\": \"$GHL_LOCATION_ID\"}"
```

Substitution rules:
- `<PRIVATE_INTEGRATION_TOKEN>` becomes `$GHL_API_KEY`
- `<locationId>` or similar becomes `$GHL_LOCATION_ID`
- Path params like `{contactId}` are substituted with the actual ID from a previous lookup

---

### Step 4 - Execute and Handle Response

Execute the call and capture the response:

```bash
RESPONSE=$(curl -s \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  --request POST 'https://services.leadconnectorhq.com/contacts/' \
  -d "{\"firstName\": \"John\", \"lastName\": \"Smith\", \"locationId\": \"$GHL_LOCATION_ID\"}")

echo "$RESPONSE" | python3 -m json.tool
```

**Response handling:**
- 200/201: Success - extract the `id` field if needed for chaining calls
- 400: Bad request - check required fields in the reference file
- 401: Auth problem - verify GHL_API_KEY is set and not expired
- 403: Wrong scope - check the scope listed in the reference file, add it to your Private Integration
- 404: Record not found - verify the ID you passed is correct
- 429: Rate limited - wait and retry with backoff

---

## Multi-Step Workflows

Many GHL tasks require chaining multiple API calls. Always capture IDs from earlier steps.

### Example: Contact Lookup then Send SMS

```bash
# Step 1: Find the contact by email
CONTACT=$(curl -s \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H 'Version: 2021-04-15' \
  "https://services.leadconnectorhq.com/contacts/?locationId=$GHL_LOCATION_ID&email=jane@example.com")

CONTACT_ID=$(echo "$CONTACT" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data['contacts'][0]['id'])" 2>/dev/null)

echo "Contact ID: $CONTACT_ID"

# Step 2: Get or create a conversation for this contact
# Step 3: Send the message to the conversation
# (Read references/conversations.md for those endpoints)
```

### Example: Create Opportunity in Pipeline

```bash
# Step 1: Get pipeline ID from opportunities reference
# Step 2: Get stage IDs for the pipeline
# Step 3: Create the opportunity with contact ID + pipeline ID + stage ID
```

---

## Scope Troubleshooting

Every endpoint lists its required scope. If you get a 403, the scope is missing.

To fix:
1. Note the scope listed in the reference file (e.g., `contacts.write`)
2. Go to GHL Settings > Integrations > Private Integrations
3. Edit your integration
4. Find the scope in the list and enable it
5. Save - the same token now has the new scope (no need to regenerate)
6. Retry the API call

---

## Working with Pagination

Most GHL list endpoints return paginated results. Pattern:

```bash
# First page (skip=0, limit=20)
curl -s \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H 'Version: 2021-04-15' \
  "https://services.leadconnectorhq.com/contacts/?locationId=$GHL_LOCATION_ID&limit=20&skip=0"

# Next page (skip=20)
"https://services.leadconnectorhq.com/contacts/?locationId=$GHL_LOCATION_ID&limit=20&skip=20"
```

Use the `total` count in the response to calculate how many pages exist.

---

## Safety Checklist Before Any Destructive Call

Before running DELETE, void, or cancel endpoints:

- [ ] Confirm the ID you are passing is the correct record
- [ ] Confirm Trevor has given explicit instruction for this action
- [ ] For phone number release: Trevor-only - flag and wait
- [ ] For billing/payment changes: Trevor-only - flag and wait
- [ ] For contact delete: confirm with Trevor before executing

---

## Secrets Handling

Never hardcode the API key in scripts or documents.

Good:
```bash
curl -H "Authorization: Bearer $GHL_API_KEY" ...
```

Bad:
```bash
curl -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6..." ...
```

Store the key in `~/clawd/secrets/.env` or as a shell environment variable only.
