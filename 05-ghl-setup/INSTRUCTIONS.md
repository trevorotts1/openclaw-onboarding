# GHL (GoHighLevel) Setup - How to Use It Day to Day

This document explains how to actually USE the GHL API integration after it has been set up. If you have not completed setup yet, go read INSTALL.md first.

After setup is complete, your AI agent can search contacts, send SMS and email messages, manage calendars, work with opportunities (deals), and access the media library. This guide covers all the common operations.

> **Tiering — prefer MCP / caf over raw curl:** For routine GHL work, prefer the Official GHL MCP and Community GHL MCP (install **skill 36**, `36-ghl-mcp-setup`) and build workflows with caf (**skill 44**). Drop to the raw curl shown below only when no MCP/caf tool covers the operation. This skill's direct REST is the foundation/fallback tier — required to bootstrap credentials and prove connectivity, not the preferred path for day-to-day bulk operations.

> **Credential variable names:** All commands read the canonical `$GOHIGHLEVEL_API_KEY` (a Private Integration Token) and `$GOHIGHLEVEL_LOCATION_ID`. The installer also writes legacy aliases `GHL_API_KEY` / `GHL_LOCATION_ID`, so either name resolves.


## The Base URL

Every GHL API request starts with this base URL:

```
https://services.leadconnectorhq.com
```

All the endpoint paths below get added to the end of this base URL.


## Required Headers for Every Request

Every single API call to GHL must include these two headers. No exceptions.

```
Authorization: Bearer $GOHIGHLEVEL_API_KEY
Version: 2021-07-28
```

The Authorization value is your Private Integration Token (PIT), not an API key. If you forget the Version header, you will get confusing 400 errors. This is the most common mistake.


## Priority Scopes (Test These First)

When you first start using GHL, focus on these three areas. They are the ones you will use most often:

1. **Contacts** - searching, creating, and updating contact records
2. **Media Library** - uploading and listing media files (images, documents, etc.)
3. **Conversations** - sending SMS text messages and emails to contacts


## Common Operations

### Working with Contacts

**Search for a contact by email or name:**
```
GET /contacts/search?query=john@email.com
```

**Get a specific contact by their ID:**
```
GET /contacts/{contactId}
```
Replace {contactId} with the actual contact ID.

**Create a new contact:**
```
POST /contacts/
```
Send the contact details in the request body as JSON (name, email, phone, etc.).

**Update an existing contact:**
```
PUT /contacts/{contactId}
```
Send only the fields you want to change in the request body.


### Sending Messages

**Send an SMS text message to a contact:**
```
POST /conversations/messages
```
Request body:
```json
{
  "type": "SMS",
  "contactId": "the-contact-id-here",
  "message": "Your text message goes here"
}
```

**Send an email to a contact:**
```
POST /conversations/messages
```
Request body:
```json
{
  "type": "Email",
  "contactId": "the-contact-id-here",
  "subject": "Your email subject",
  "html": "<p>Your email body in HTML format.</p>"
}
```

Note: Both SMS and email use the same endpoint. The "type" field tells GHL which one to send.


### Working with Calendars

**Get available time slots for a calendar:**
```
GET /calendars/{calendarId}/free-slots
```

**Book an appointment:**
```
POST /calendars/events/appointments
```


### Working with Opportunities (Deals)

**List opportunities (with search):**
```
GET /opportunities/search
```

**Create a new opportunity:**
```
POST /opportunities/
```

**Update an existing opportunity:**
```
PUT /opportunities/{id}
```


### Working with Media

**List files in the media library:**
```
GET /medias/?locationId=$GOHIGHLEVEL_LOCATION_ID&limit=10
```

**Upload a file to the media library:**
Uploads go to a different endpoint (`/medias/upload-file`) and use a multipart/form-data POST. They require the **Location** PIT, not an Agency PIT.
```bash
curl -X POST "https://services.leadconnectorhq.com/medias/upload-file" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28" \
  -F "file=@/path/to/local/image.png" \
  -F "name=image.png"
```
Let `curl -F` set the `multipart/form-data` Content-Type and boundary automatically; do not set it by hand. Limits: 25 MB regular files, 500 MB video. To register an already-hosted file instead of uploading bytes, send `-F "hosted=true" -F "fileUrl=https://..."` instead of `file`. See EXAMPLES.md (Example 8) for the full response and failure modes.


## Important Rules

1. **Never use the native GHL node in n8n.** It is limited and often broken. Always use HTTP Request nodes for GHL API calls instead.

2. **Always include the Version header.** This cannot be stressed enough. Without it, requests will fail.

3. **Rate limits exist.** GHL allows approximately 100 requests per minute for most endpoints. If your AI is making rapid-fire requests (like importing hundreds of contacts), it needs to pace itself and not exceed this limit.

4. **Webhooks are available.** Instead of constantly checking for updates (polling), you can set up webhooks in GHL so it automatically notifies your system when something happens (new contact created, appointment booked, etc.). This is more efficient and faster.

5. **Always check both credential locations.** Your AI should check ~/.openclaw/secrets/.env AND ~/.openclaw/openclaw.json (under env.vars) for GHL credentials, because different setups store them in different places. secrets/.env is authoritative; openclaw.json is a secondary mirror.


## Runtime Preflight and Fallback Chain

Before any GHL call at runtime, resolve credentials and fail loudly if they are missing. Never let a missing token become a silent 401. This bash preflight implements the fallback chain (resolve -> block-with-exact-fix -> auto-discover location -> rate-limit/5xx backoff). Source it once, then route requests through `ghl_request`.

```bash
# ---- ghl_preflight: resolve creds + fail loud (never a silent 401) ----
ghl_preflight() {
  # Resolve token (canonical first, then legacy aliases) and location
  GHL_TOKEN="${GOHIGHLEVEL_API_KEY:-${GHL_API_KEY:-${GHL_PIT:-}}}"
  GHL_LOC="${GOHIGHLEVEL_LOCATION_ID:-${GHL_LOCATION_ID:-}}"

  # Token missing -> BLOCK with the exact fix; do not proceed to a 401
  if [ -z "$GHL_TOKEN" ]; then
    echo "BLOCKED: GoHighLevel Private Integration Token not found." >&2
    echo "  Set GOHIGHLEVEL_API_KEY in ~/.openclaw/secrets/.env (chmod 600)." >&2
    echo "  Get the PIT from GHL: Settings > Integrations > Private Integrations." >&2
    return 1
  fi

  # Location missing only -> auto-discover via /locations/search, then persist
  if [ -z "$GHL_LOC" ]; then
    GHL_LOC="$(curl -sS -m 10 \
      -H "Authorization: Bearer $GHL_TOKEN" -H "Version: 2021-07-28" \
      "https://services.leadconnectorhq.com/locations/search?limit=1" \
      | grep -oE '"id"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 \
      | sed -E 's/.*"id"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/')"
    if [ -z "$GHL_LOC" ]; then
      echo "BLOCKED: GOHIGHLEVEL_LOCATION_ID not set and auto-discovery failed." >&2
      echo "  Add GOHIGHLEVEL_LOCATION_ID to ~/.openclaw/secrets/.env." >&2
      return 1
    fi
    printf 'GOHIGHLEVEL_LOCATION_ID=%s\n' "$GHL_LOC" >> ~/.openclaw/secrets/.env
  fi
  export GHL_TOKEN GHL_LOC
}

# ---- ghl_request: curl wrapper with 429 backoff + one 5xx/timeout retry ----
# usage: ghl_request <extra curl args...>   (Authorization + Version added for you)
ghl_request() {
  local attempt=0 max=3 out code
  while :; do
    out="$(curl -sS -m 30 -w $'\n%{http_code}' \
      -H "Authorization: Bearer $GHL_TOKEN" -H "Version: 2021-07-28" "$@")"
    code="${out##*$'\n'}"; out="${out%$'\n'*}"
    case "$code" in
      429)  attempt=$((attempt+1)); [ "$attempt" -gt "$max" ] && { echo "$out"; return 22; }
            sleep $(( 2 ** attempt )) ;;             # exponential backoff; if GHL sends Retry-After, prefer it
      5*|000) attempt=$((attempt+1)); [ "$attempt" -gt 1 ] && { echo "$out"; return 22; }
            sleep 2 ;;                               # one retry on 5xx / timeout
      *)    echo "$out"; [ "$code" -ge 400 ] 2>/dev/null && return 22; return 0 ;;
    esac
  done
}
```

**Operation tiering (R3):** prefer an MCP tool (skill 36) or a caf workflow (skill 44) for the operation; only fall back to `ghl_request` raw REST when no MCP/caf tool exists. On a persistent failure, report the exact HTTP status and body to the operator (verbose) and nothing to the client.


## Troubleshooting Common Issues

### Getting 400 errors
The most likely cause is a missing Version header. Make sure every request includes:
```
Version: 2021-07-28
```

### Getting 401 (Unauthorized) errors
Your Private Integration Token (PIT) may be expired, revoked, or incorrect. Rotate it in GHL Settings > Integrations > Private Integrations and update GOHIGHLEVEL_API_KEY in ~/.openclaw/secrets/.env. A PIT is a static token; it cannot be "refreshed" like an OAuth session.

### Getting 404 (Not Found) errors
Double-check the endpoint path. Make sure you are using the correct URL format. Also verify that the contact ID, calendar ID, or other resource ID you are referencing actually exists.

### Getting 429 (Too Many Requests) errors
You exceeded the rate limit (about 100 requests/minute). Back off exponentially and retry (the `ghl_request` wrapper above does this). If the response includes a `Retry-After` header, wait that many seconds before retrying. Cap retries at 3, then report the failure to the operator.

### Requests timing out
GHL's servers can sometimes be slow. Set your timeout to at least 30 seconds. If the problem persists, check GHL's status page for any outages.

### SMS not sending
Make sure the contact has a valid phone number. Also verify that your GHL account has SMS sending enabled and that you have sufficient credits/balance for sending.

### Email not sending
Make sure the contact has a valid email address. Check that your GHL account has email configured (SMTP settings, sending domain, etc.).


## What to Add to Your Core .md Files

After learning this, update your files following TYP rules:

**TOOLS.md** - Add the GHL API base URL, the Version header requirement, and the list of common endpoints.

**MEMORY.md** - Note that GHL credentials are configured and where they are stored.

**AGENTS.md** - Add the rule to always include the Version header in every GHL request.
