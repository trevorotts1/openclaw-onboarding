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
| "add a contact", "save a contact", "find a contact", "update contact tags" | contacts | `references/contacts.md` |

### Contact write decision table — read BEFORE building any contact call

Generic "add/save this person" is NOT a create. Route first:

| Intent | Meaning | Call |
|---|---|---|
| Generic add/save ("add this person", "save this contact") | Record may or may not exist | POST /contacts/upsert with match keys (email and/or phone). Omit createNewIfDuplicateAllowed unless the owner explicitly asked for a new record. |
| Explicit new record ("create a NEW contact", "add them as a new contact even if duplicate") | New row even if a match exists | POST /contacts/ (or upsert with createNewIfDuplicateAllowed=true on explicit request only) |
| Known contactId ("update contact <id>") | Exact record targeted | GET /contacts/{contactId} first, then PUT only the supplied fields |

Upsert matching is resolved by HighLevel's Upsert endpoint according to the
Location-level Allow Duplicate Contact configuration and its configured matching
priority — never claim it "matches on email/phone" as a fixed rule.
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

Safe non-destructive payload rule: send ONLY supplied fields plus locationId
(and match keys for upsert). Never send empty/null/blank values — they can wipe
data. Never put a `tags` array in an upsert or update body (use the dedicated tag
endpoint). Verify after every write: capture the returned contact ID, GET the
record, confirm intended fields. A succeeded write with a failed read-back is
reported "WRITE SUCCEEDED — VERIFICATION INCOMPLETE" — never re-fire the write
to "check" (it can duplicate).

Scan the file for:
- The endpoint that matches the task (e.g., `POST /contacts/upsert` for a generic add/save; `POST /contacts/` ONLY for an explicitly requested new record)
- Required scopes (must be enabled in your Private Integration)
- Required headers (Authorization + Version always, others per endpoint)
- Required path params (e.g., `{contactId}`)
- Required query params (e.g., `locationId`)
- Required body fields
- The cURL template provided

---

### Step 3 - Build the API Call

Take the cURL template from the reference file and substitute real values:

Generic add/save — upsert (DEFAULT for "add/save this person"):

```bash
# Template (from reference file) — match keys + only the fields the owner gave
curl --request POST 'https://services.leadconnectorhq.com/contacts/upsert' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json' \
  -d '{"email": "john@example.com", "firstName": "John", "lastName": "Smith", "locationId": "<locationId>"}'

# Substituted (ready to run)
curl --request POST 'https://services.leadconnectorhq.com/contacts/upsert' \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json' \
  -d "{\"email\": \"john@example.com\", \"firstName\": \"John\", \"lastName\": \"Smith\", \"locationId\": \"$GOHIGHLEVEL_LOCATION_ID\"}"
```

Explicit new record — create (ONLY when the owner explicitly asked for a NEW
record even if a match exists):

```bash
curl --request POST 'https://services.leadconnectorhq.com/contacts/' \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json' \
  -d "{\"firstName\": \"John\", \"lastName\": \"Smith\", \"locationId\": \"$GOHIGHLEVEL_LOCATION_ID\"}"
```

Every write ends with a read-back: capture the returned contact ID, GET
`/contacts/{contactId}`, confirm intended fields.

Substitution rules:
- `<PRIVATE_INTEGRATION_TOKEN>` becomes `$GOHIGHLEVEL_API_KEY`
- `<locationId>` or similar becomes `$GOHIGHLEVEL_LOCATION_ID`
- Path params like `{contactId}` are substituted with the actual ID from a previous lookup

Before running any call, load credentials with the resolver in SKILL.md "Credentials"
(it sources `~/.openclaw/secrets/.env`, maps legacy aliases to the canonical names, and
fails loud if a credential is unresolved — so you never send an empty Bearer token).

---

### Step 4 - Execute and Handle Response

Execute the call and capture the response:

```bash
RESPONSE=$(curl -s \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-07-28' \
  -H 'Content-Type: application/json' \
  --request POST 'https://services.leadconnectorhq.com/contacts/upsert' \
  -d "{\"email\": \"john@example.com\", \"firstName\": \"John\", \"lastName\": \"Smith\", \"locationId\": \"$GOHIGHLEVEL_LOCATION_ID\"}")

echo "$RESPONSE" | python3 -m json.tool
```

**Response handling:**
- 200/201: Success - extract the `id` field if needed for chaining calls
- 400: Bad request - check required fields in the reference file
- 401: Auth problem - run the credential resolver (SKILL.md "Credentials"); confirm `$GOHIGHLEVEL_API_KEY` resolved to a valid, non-expired LOCATION PIT. Never fire an empty `Authorization: Bearer `
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
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-07-28' \
  "https://services.leadconnectorhq.com/contacts/?locationId=$GOHIGHLEVEL_LOCATION_ID&email=jane@example.com")

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
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-07-28' \
  "https://services.leadconnectorhq.com/contacts/?locationId=$GOHIGHLEVEL_LOCATION_ID&limit=20&skip=0"

# Next page (skip=20)
"https://services.leadconnectorhq.com/contacts/?locationId=$GOHIGHLEVEL_LOCATION_ID&limit=20&skip=20"
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
curl -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" ...
```

Bad:
```bash
curl -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6..." ...
```

Store the key in `~/.openclaw/secrets/.env` (chmod 600) as `GOHIGHLEVEL_API_KEY`, or as a shell environment variable only.
