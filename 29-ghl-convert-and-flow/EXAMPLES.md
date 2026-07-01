# GHL API Skill - Real-World Examples

> All examples use environment variables `$GOHIGHLEVEL_API_KEY` and `$GOHIGHLEVEL_LOCATION_ID`.
> Carved from the Convert and Flow GoHighLevel API v2 Master Reference.
> Do NOT hardcode credentials. Load them with the resolver in SKILL.md "Credentials"
> (it sources `~/.openclaw/secrets/.env`, maps legacy aliases, and fails loud if unset —
> so you never send an empty `Authorization: Bearer `).
> After any write, point the client to the verify table in SKILL.md "Caller Contract".

```bash
# Canonical names (match ~/.openclaw/secrets/.env). For ad-hoc testing you may export directly:
export GOHIGHLEVEL_API_KEY="pit-your-location-scoped-token"
export GOHIGHLEVEL_LOCATION_ID="your_location_id"
```

---

## Contacts

### Create a New Contact

```bash
curl --request POST 'https://services.leadconnectorhq.com/contacts/' \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d "{
    \"firstName\": \"Jane\",
    \"lastName\": \"Smith\",
    \"email\": \"jane@example.com\",
    \"phone\": \"+15555551234\",
    \"locationId\": \"$GOHIGHLEVEL_LOCATION_ID\",
    \"tags\": [\"lead\", \"website\"]
  }"
```

Required scope: `contacts.write`
Returns: Contact object with `id` field - save this for follow-up calls.
Verify in CF UI: Contacts → the new record appears with the tags/notes you set.

---

### Search Contacts by Email

```bash
curl -s \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  "https://services.leadconnectorhq.com/contacts/?locationId=$GOHIGHLEVEL_LOCATION_ID&email=jane%40example.com"
```

Required scope: `contacts.readonly`
Returns: Array of matching contacts with full contact objects.

---

### Update Contact Tags

```bash
# Replace tags entirely
curl --request PUT "https://services.leadconnectorhq.com/contacts/CONTACT_ID_HERE" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"tags": ["hot-lead", "called", "interested"]}'
```

Required scope: `contacts.write`
Replace `CONTACT_ID_HERE` with the actual contact ID from a prior lookup.

---

### Add a Note to a Contact

```bash
curl --request POST "https://services.leadconnectorhq.com/contacts/CONTACT_ID_HERE/notes" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d "{
    \"body\": \"Called contact - interested in the Gold package. Follow up Friday.\",
    \"userId\": \"USER_ID_HERE\"
  }"
```

Required scope: `contacts/notes.write`

---

### Add a Task for a Contact

```bash
curl --request POST "https://services.leadconnectorhq.com/contacts/CONTACT_ID_HERE/tasks" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d "{
    \"title\": \"Follow up call\",
    \"body\": \"Check in on proposal sent\",
    \"dueDate\": \"2024-02-01T17:00:00Z\",
    \"completed\": false,
    \"assignedTo\": \"USER_ID_HERE\"
  }"
```

Required scope: `contacts/tasks.write`

---

## Conversations and Messages

### Get All Conversations for a Location

```bash
curl -s \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  "https://services.leadconnectorhq.com/conversations/?locationId=$GOHIGHLEVEL_LOCATION_ID&limit=20&skip=0"
```

Required scope: `conversations.readonly`

---

### Get Messages in a Conversation

```bash
curl -s \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  "https://services.leadconnectorhq.com/conversations/CONVERSATION_ID_HERE/messages"
```

Required scope: `conversations/message.readonly`

---

### Send an Outbound SMS Message

```bash
curl --request POST 'https://services.leadconnectorhq.com/conversations/messages' \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d "{
    \"type\": \"SMS\",
    \"contactId\": \"CONTACT_ID_HERE\",
    \"locationId\": \"$GOHIGHLEVEL_LOCATION_ID\",
    \"message\": \"Hi Jane, just following up on our call today. Let me know if you have questions!\"
  }"
```

Required scope: `conversations/message.write`
Verify in CF UI: the contact's Conversation thread shows the outbound SMS.

---

## Opportunities

### Get All Opportunities (Pipeline View)

```bash
curl -s \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  "https://services.leadconnectorhq.com/opportunities/search?location_id=$GOHIGHLEVEL_LOCATION_ID&limit=20"
```

Required scope: `opportunities.readonly`

---

### Create an Opportunity

```bash
curl --request POST 'https://services.leadconnectorhq.com/opportunities/' \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d "{
    \"pipelineId\": \"PIPELINE_ID_HERE\",
    \"locationId\": \"$GOHIGHLEVEL_LOCATION_ID\",
    \"name\": \"Jane Smith - Gold Package\",
    \"pipelineStageId\": \"STAGE_ID_HERE\",
    \"status\": \"open\",
    \"contactId\": \"CONTACT_ID_HERE\",
    \"monetaryValue\": 2500
  }"
```

Required scope: `opportunities.write`

---

### Update Opportunity Stage (Move in Pipeline)

```bash
curl --request PUT "https://services.leadconnectorhq.com/opportunities/OPPORTUNITY_ID_HERE" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d "{
    \"pipelineStageId\": \"NEW_STAGE_ID_HERE\",
    \"status\": \"open\"
  }"
```

Required scope: `opportunities.write`

---

## Calendars and Appointments

### Get All Calendars for a Location

```bash
curl -s \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  "https://services.leadconnectorhq.com/calendars/?locationId=$GOHIGHLEVEL_LOCATION_ID"
```

Required scope: `calendars.readonly`

---

### Get Available Appointment Slots

```bash
curl -s \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  "https://services.leadconnectorhq.com/calendars/CALENDAR_ID_HERE/free-slots?startDate=2024-02-01&endDate=2024-02-07&timezone=America/New_York"
```

Required scope: `calendars/events.readonly`

---

### Book an Appointment

```bash
curl --request POST 'https://services.leadconnectorhq.com/calendars/events/appointments' \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d "{
    \"calendarId\": \"CALENDAR_ID_HERE\",
    \"locationId\": \"$GOHIGHLEVEL_LOCATION_ID\",
    \"contactId\": \"CONTACT_ID_HERE\",
    \"startTime\": \"2024-02-05T14:00:00-05:00\",
    \"endTime\": \"2024-02-05T14:30:00-05:00\",
    \"title\": \"Discovery Call - Jane Smith\",
    \"appointmentStatus\": \"confirmed\"
  }"
```

Required scope: `calendars/events.write`

---

## Locations (Sub-Accounts)

### Get Location Info

```bash
curl -s \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  "https://services.leadconnectorhq.com/locations/$GOHIGHLEVEL_LOCATION_ID"
```

Required scope: `locations.readonly`

---

### Get All Tags for a Location

```bash
curl -s \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  "https://services.leadconnectorhq.com/locations/$GOHIGHLEVEL_LOCATION_ID/tags"
```

Required scope: `tags.readonly`

---

## Invoices

### Create an Invoice

```bash
curl --request POST 'https://services.leadconnectorhq.com/invoices/' \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d "{
    \"altId\": \"$GOHIGHLEVEL_LOCATION_ID\",
    \"altType\": \"location\",
    \"name\": \"Gold Package - Month 1\",
    \"contactDetails\": {
      \"id\": \"CONTACT_ID_HERE\",
      \"name\": \"Jane Smith\",
      \"email\": \"jane@example.com\"
    },
    \"items\": [
      {
        \"name\": \"Gold Package\",
        \"qty\": 1,
        \"unitPrice\": 2500
      }
    ],
    \"currency\": \"USD\",
    \"dueDate\": \"2024-02-15\"
  }"
```

Required scope: `invoices.write`

---

### Send an Invoice to a Contact

```bash
curl --request POST "https://services.leadconnectorhq.com/invoices/INVOICE_ID_HERE/send" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d "{
    \"altId\": \"$GOHIGHLEVEL_LOCATION_ID\",
    \"altType\": \"location\",
    \"action\": \"send_now\"
  }"
```

Required scope: `invoices.write`

---

## Users

### List All Users for a Location

```bash
curl -s \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  "https://services.leadconnectorhq.com/users/?locationId=$GOHIGHLEVEL_LOCATION_ID"
```

Required scope: `users.readonly`

---

### Get a Specific User

```bash
curl -s \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  "https://services.leadconnectorhq.com/users/USER_ID_HERE"
```

Required scope: `users.readonly`

---

## Workflows

### List All Workflows for a Location

```bash
curl -s \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  "https://services.leadconnectorhq.com/workflows/?locationId=$GOHIGHLEVEL_LOCATION_ID"
```

Required scope: `workflows.readonly`

---

## Handling Errors in Scripts

### Robust Pattern with Error Checking

```bash
#!/bin/bash

# Resolve creds (canonical names; legacy aliases mapped) and FAIL LOUD if unset —
# never fire an empty "Authorization: Bearer ". See SKILL.md "Credentials".
[ -f ~/.openclaw/secrets/.env ] && { set -a; . ~/.openclaw/secrets/.env; set +a; }
: "${GOHIGHLEVEL_API_KEY:=${GHL_API_KEY:-${GHL_PIT:-${GHL_TOKEN:-${GHL_PRIVATE_INTEGRATION_TOKEN:-${PRIVATE_INTEGRATION_TOKEN:-${GHL_PRIVATE_TOKEN:-${PIT_TOKEN:-${GHL_PIT_TOKEN:-${GOHIGHLEVEL_LOCATION_PIT:-${GHL_LOCATION_PIT:-}}}}}}}}}}}}"
: "${GOHIGHLEVEL_LOCATION_ID:=${GHL_LOCATION_ID:-}}"
if [ -z "${GOHIGHLEVEL_API_KEY:-}" ] || [ -z "${GOHIGHLEVEL_LOCATION_ID:-}" ]; then
  echo "BLOCKED: GOHIGHLEVEL_API_KEY and GOHIGHLEVEL_LOCATION_ID must be set." >&2
  echo "Add them to ~/.openclaw/secrets/.env (chmod 600), or export them in your shell." >&2
  echo "Media uploads require a LOCATION-scoped PIT (an agency PIT 401s on media)." >&2
  exit 1
fi

# Make the call and capture HTTP status code separately
HTTP_CODE=$(curl -s -o /tmp/ghl_response.json -w "%{http_code}" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H 'Version: 2021-04-15' \
  "https://services.leadconnectorhq.com/locations/$GOHIGHLEVEL_LOCATION_ID")

if [ "$HTTP_CODE" = "200" ]; then
  echo "Success:"
  cat /tmp/ghl_response.json | python3 -m json.tool
elif [ "$HTTP_CODE" = "401" ]; then
  echo "ERROR 401: Invalid or expired token. Check GOHIGHLEVEL_API_KEY (must be a valid LOCATION PIT)."
elif [ "$HTTP_CODE" = "403" ]; then
  echo "ERROR 403: Missing scope. Check the required scope in the reference file."
  cat /tmp/ghl_response.json
elif [ "$HTTP_CODE" = "429" ]; then
  echo "ERROR 429: Rate limited. Wait 60 seconds and retry."
else
  echo "ERROR $HTTP_CODE:"
  cat /tmp/ghl_response.json
fi
```
