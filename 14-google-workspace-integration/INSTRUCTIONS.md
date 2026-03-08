# Google Workspace Integration - Usage Instructions

This document covers how to USE your Google Workspace integration day to day, after you have completed the installation steps in INSTALL.md.

---

## The Golden Rule: Check the Email Domain First

Before making ANY Google API call, check the email address:

| Email Type | Example | Tool to Use |
|-----------|---------|-------------|
| Workspace (business) | you@yourcompany.com | google-api.js with Service Account |
| Personal Gmail | you@gmail.com | GOG CLI with OAuth |

These are INCOMPATIBLE methods. Using the wrong tool for the wrong account type WILL fail. If you get a 401 or 403 error, the FIRST thing to check is whether you are using the correct tool.

---

## How Authentication Works Behind the Scenes

You do not need to do anything for authentication after initial setup. Here is what happens automatically:

1. Your AI reads the JSON key file
2. It creates a signed permission slip (called a JWT) saying "I am the service account and I need to act as you@yourcompany.com"
3. It sends that to Google
4. Google checks the Domain-Wide Delegation settings
5. Google gives back a temporary token that lasts 1 hour
6. When the token expires, the AI automatically creates a new one

No browser. No "Allow" button. No human interaction needed. Ever.

---

## Asking Your AI to Do Things (Plain English)

You do not need special commands. Just ask in plain English. Your AI will figure out which service and API to use.

### Gmail
- "Check my Gmail for unread messages"
- "Search my email for messages from sarah@company.com"
- "Send an email to john@vendor.com about the invoice"
- "Show me my Gmail labels"
- "Find all emails about the quarterly report from last week"

### Calendar
- "What is on my calendar today?"
- "Show me my schedule for this week"
- "Create a meeting called Team Standup for tomorrow at 9 AM"
- "Do I have any conflicts on Friday afternoon?"

### Drive
- "List my 10 most recent files in Google Drive"
- "Search Drive for anything about budget proposal"
- "Upload this file to my Google Drive"

### Docs
- "List my recent Google Docs"
- "Read the document titled Marketing Plan"
- "Create a new doc called Meeting Notes"

### Sheets
- "Read the data from Sheet1 in my Sales Tracker spreadsheet"
- "Update cell A1 in my Inventory sheet to say Updated"
- "List my Google Sheets"

### Slides
- "List my Google Slides presentations"
- "Create a presentation from these bullet points"

### Contacts
- "Look up John Smith in my contacts"
- "Find the email address for Pam Perry"

### Tasks
- "Show me my task lists"
- "Create a new task: Follow up with client by Friday"

### YouTube
- "Show me my YouTube channel info"
- "List my recent videos"

### Chat
- "List my Google Chat spaces"
- "Show messages in [space name]"

### Forms
- "List my Google Forms"
- "Show responses for [form name]"

### Keep
- "List my Google Keep notes"
- "Create a note with today's to-do list"

### Places
- "Find coffee shops near Times Square"
- "Search for event venues in Atlanta with good ratings"

### Admin
- "List users in my Google Workspace organization"

---

## Using the google-api.js Script Directly

For more control, you can use the google-api.js script from the command line. Add --pretty for human-readable output.

### Gmail Commands

```bash
node google-api.js gmail unread --limit 5 --pretty       # List unread emails
node google-api.js gmail search "from:client@email.com"   # Search emails
node google-api.js gmail read 19c7b789ef2d56f0 --pretty   # Read specific email by ID
node google-api.js gmail send --to "a@b.com" --subject "Hi" --body "Hello"  # Send email
node google-api.js gmail labels --pretty                   # List all labels
```

### Calendar Commands

```bash
node google-api.js calendar today --pretty         # Today's events
node google-api.js calendar list --days 7 --pretty # Next 7 days of events
```

### Drive Commands

```bash
node google-api.js drive list --limit 10 --pretty          # List recent files
node google-api.js drive search "conference 2026" --pretty  # Search files
```

### Contacts Commands

```bash
node google-api.js contacts list --limit 10 --pretty  # List contacts
node google-api.js contacts search "Pam Perry" --pretty # Search by name
```

### Sheets Commands

```bash
node google-api.js sheets list --pretty                           # List spreadsheets
node google-api.js sheets read SPREADSHEET_ID "Sheet1!A1:D10"    # Read cells
```

### Docs Commands

```bash
node google-api.js docs list --pretty             # List documents
node google-api.js docs read DOCUMENT_ID --pretty  # Read a document
```

### Slides Commands

```bash
node google-api.js slides list --pretty  # List presentations
```

### Tasks Commands

```bash
node google-api.js tasks lists --pretty                                  # List task lists
node google-api.js tasks list TASKLIST_ID --pretty                        # List tasks in a list
node google-api.js tasks create TASKLIST_ID --title "Follow up" --pretty  # Create a task
```

### YouTube Commands

```bash
node google-api.js youtube channels --pretty          # Channel info
node google-api.js youtube videos --limit 5 --pretty  # Recent videos
```

### Chat Commands

```bash
node google-api.js chat spaces --pretty                    # List spaces
node google-api.js chat messages SPACE_ID --pretty         # Messages in a space
```

### Forms Commands

```bash
node google-api.js forms list --pretty  # List forms
```

### Keep Commands

```bash
node google-api.js keep list --pretty  # List notes
```

### Admin Commands

```bash
node google-api.js admin users --limit 5 --pretty  # List users
```

### Places Commands

```bash
node google-api.js places search "coffee near Atlanta" --pretty  # Search places
```

---

## JWT Authentication Flow (For AI Agents)

When the AI needs to make a direct API call, it follows this process:

1. Load the service account JSON key file from GOOGLE_SA_KEY_FILE
2. Build the JWT header: { alg: "RS256", typ: "JWT" }
3. Build the JWT payload with: iss (service account email), sub (user to impersonate), aud (token URI), iat (now), exp (now + 3600), scope (the scope needed)
4. Sign with RSA-SHA256 using the private key from the JSON file
5. Exchange the JWT for an access token at https://oauth2.googleapis.com/token
6. Use the access token in the Authorization: Bearer header for API calls
7. Token lasts 1 hour. Request a new one when it expires.

---

## Scope-to-Service Reference

When the AI makes a direct API call, it needs to know which scope to request:

| Service | Scope to Request | API Base URL |
|---------|-----------------|--------------|
| Gmail | https://mail.google.com/ | https://gmail.googleapis.com/gmail/v1 |
| Calendar | https://www.googleapis.com/auth/calendar | https://www.googleapis.com/calendar/v3 |
| Drive | https://www.googleapis.com/auth/drive | https://www.googleapis.com/drive/v3 |
| Contacts | https://www.googleapis.com/auth/contacts | https://people.googleapis.com/v1 |
| Sheets | https://www.googleapis.com/auth/spreadsheets | https://sheets.googleapis.com/v4 |
| Docs | https://www.googleapis.com/auth/documents | https://docs.googleapis.com/v1 |
| Slides | https://www.googleapis.com/auth/presentations | https://slides.googleapis.com/v1 |
| Tasks | https://www.googleapis.com/auth/tasks | https://tasks.googleapis.com/tasks/v1 |
| YouTube | https://www.googleapis.com/auth/youtube | https://www.googleapis.com/youtube/v3 |
| Chat | https://www.googleapis.com/auth/chat.spaces | https://chat.googleapis.com/v1 |
| Forms | https://www.googleapis.com/auth/forms.body | https://forms.googleapis.com/v1 |
| Keep | https://www.googleapis.com/auth/keep | https://keep.googleapis.com/v1 |
| Admin SDK | https://www.googleapis.com/auth/admin.directory.user | https://admin.googleapis.com/admin/directory/v1 |
| Places | Uses API Key, not JWT | https://places.googleapis.com/v1 |

---

## Key API Endpoints Reference

| Service | Endpoint | Method | What It Does |
|---------|----------|--------|--------------|
| Gmail | /users/me/messages?q=is:unread | GET | List unread emails |
| Gmail | /users/me/messages/{id} | GET | Read a specific email |
| Gmail | /users/me/messages/send | POST | Send an email |
| Gmail | /users/me/labels | GET | List all labels |
| Calendar | /calendars/primary/events | GET | List events |
| Calendar | /calendars/primary/events | POST | Create an event |
| Drive | /files | GET | List files |
| Drive | /files?q=name contains 'X' | GET | Search files |
| Contacts | /people/me/connections?personFields=names,emailAddresses | GET | List contacts |
| Sheets | /spreadsheets/{id}/values/{range} | GET | Read cells |
| Sheets | /spreadsheets/{id}/values/{range} | PUT | Write cells |
| Docs | /documents/{id} | GET | Read document |
| Tasks | /users/@me/lists | GET | List task lists |
| YouTube | /channels?part=snippet&mine=true | GET | Get channel info |
| Chat | /spaces | GET | List spaces |
| Places | /places:searchText | POST | Search places (uses API Key) |

---

## Self-Correction Protocol for AI Agents

If ANY Google API call returns 401, 403, "access denied", or "permission denied":

1. FIRST: What account am I accessing? Workspace or personal?
2. THEN: Am I using the right tool? Workspace = google-api.js. Personal = GOG CLI.
3. If using GOG for a Workspace account - THAT IS THE BUG. Switch to google-api.js.
4. If using google-api.js for personal Gmail - THAT IS THE BUG. Switch to GOG.
5. Only if the correct tool is being used, THEN check scopes and delegation.
6. NEVER tell the user "I cannot access this" without first checking the tool selection.
7. NEVER push this back to the user. Fix it yourself.

---

## Important Notes

- **Token caching:** Each call generates a fresh token. For high-frequency use, cache the token (valid 1 hour).
- **One scope per request:** Only request the scope needed for the specific API call.
- **Rate limits:** Gmail allows about 250 quota units per second. Calendar allows about 500 requests per 100 seconds. If you hit 429 (Too Many Requests), back off and retry.
- **Pagination:** Most list endpoints support pageToken for getting additional pages of results.
- **Error codes:** 401 = auth issue. 403 = scope not granted or API not enabled. 404 = resource not found. 429 = rate limited.

---

## Morning Briefing Routing

When checking accounts during the daily briefing:

- Workspace emails (@yourdomain.com): Use google-api.js
  Example: node google-api.js gmail unread --limit 10 --pretty
- Personal emails (@gmail.com): Use GOG CLI
  Example: gog gmail search "in:inbox" --limit 10 --account user@gmail.com

If ANY check fails with 401/403:
1. Do NOT skip that account
2. Check if you used the wrong tool
3. Switch to the correct tool and retry
4. Never silently skip a failed check

---

## Lessons Learned (From Real Debugging)

1. **The Client ID Trap** - Use the numeric Unique ID, NOT the email address, for Domain-Wide Delegation. Using the email silently fails.

2. **Scope Formatting** - Scopes must be comma-separated, no spaces, no line breaks. Even a trailing space can break it.

3. **Third-Party CLI Bugs** - The GOG CLI has a known bug with Gmail scope negotiation (returns 401 even when everything is correct). Bypass it with google-api.js for Workspace accounts.

4. **Propagation Delays** - After changing scopes or enabling APIs, wait 5-15 minutes (up to 24 hours for Gmail). If something does not work immediately, wait and retry.

5. **Zero Dependencies** - The google-api.js script uses only Node.js built-ins. No npm install, no version conflicts.

6. **OAuth Consent Screen Is Required** - Without it, Gmail will not work even if everything else is correct. Configure it first.

7. **Keep One Key File** - Multiple key files in the same directory causes confusion. Rotate by creating new, updating config, then deleting old.

8. **Organization Policies Block New Setups** - Since May 2024, Google blocks key creation by default on new organizations. See INSTALL.md Section 5.
