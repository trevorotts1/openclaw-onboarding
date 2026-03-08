# Google Workspace Integration - Examples

Real examples showing the Google Workspace integration in action, including command-line usage, API calls, and AI interactions.

---

## Example 1: Quick Setup (Let Your AI Do It)

Instead of following all the manual steps, copy this prompt and send it to your AI:

```
Set up Google Workspace integration for me. I need you to:
1. Use Playwright browser automation with launchPersistentContext and store session data in ~/.openclaw/playwright-data/
2. Help me create a GCP (Google Cloud Platform) project
3. Enable the required APIs for Gmail, Calendar, Drive, Docs, Sheets, Slides, Chat, Forms, Keep, Admin, Analytics, Tag Manager, Search Console, YouTube, Places, and Looker Studio
4. Create a service account with domain-wide delegation
5. Generate and download the service account JSON key
6. Set GOOGLE_SA_KEY_FILE and GOOGLE_IMPERSONATE_USER
7. Install and configure the GOG skill using the JSON key
8. Test every service in Section 12

Walk me through each step. Ask me for any information you need.
My Google Workspace email is: trevor@blackceo.com
```

Your AI will guide you through each step one at a time.

---

## Example 2: Testing Gmail

**Command line:**

```bash
node google-api.js gmail unread --limit 3 --pretty
```

**Expected output (success):**

```json
{
  "messages": [
    {
      "id": "19c7b789ef2d56f0",
      "from": "sarah@company.com",
      "subject": "Q3 Budget Review",
      "date": "2026-02-28T14:15:00Z",
      "snippet": "Hi Trevor, here are the Q3 numbers..."
    },
    {
      "id": "19c7b6a2d4e1f3b8",
      "from": "newsletter@industry.com",
      "subject": "Weekly Industry Update",
      "date": "2026-02-28T10:00:00Z",
      "snippet": "This week in AI..."
    },
    {
      "id": "19c7b5c1a3b2d4e5",
      "from": "john@vendor.com",
      "subject": "Invoice #1234",
      "date": "2026-02-27T16:30:00Z",
      "snippet": "Attached is the invoice for..."
    }
  ],
  "resultCount": 3
}
```

**If you see an error instead:**

```
Error: 401 Unauthorized
```

Check: OAuth Consent Screen configured? DWD authorized? All 5 Gmail scopes in the scope list?

---

## Example 3: Testing Calendar

**Command line:**

```bash
node google-api.js calendar today --pretty
```

**Expected output (success):**

```json
{
  "events": [
    {
      "summary": "Team Standup",
      "start": "2026-02-28T09:00:00-05:00",
      "end": "2026-02-28T09:30:00-05:00",
      "location": "Zoom"
    },
    {
      "summary": "Client Call - Pam Perry",
      "start": "2026-02-28T14:00:00-05:00",
      "end": "2026-02-28T15:00:00-05:00",
      "location": "Google Meet"
    }
  ]
}
```

---

## Example 4: Searching Google Drive

**Command line:**

```bash
node google-api.js drive search "quarterly report" --pretty
```

**Expected output:**

```json
{
  "files": [
    {
      "id": "1abc2def3ghi4jkl",
      "name": "Q3 Quarterly Report - Final",
      "mimeType": "application/vnd.google-apps.document",
      "modifiedTime": "2026-02-15T10:30:00Z"
    },
    {
      "id": "5mno6pqr7stu8vwx",
      "name": "Quarterly Report Template",
      "mimeType": "application/vnd.google-apps.spreadsheet",
      "modifiedTime": "2026-01-10T08:15:00Z"
    }
  ]
}
```

---

## Example 5: Searching Contacts

**Command line:**

```bash
node google-api.js contacts search "Pam Perry" --pretty
```

**Expected output:**

```json
{
  "connections": [
    {
      "name": "Pam Perry",
      "emails": ["pam@company.com", "pamperry@gmail.com"],
      "phones": ["+1 (404) 555-1234"]
    }
  ]
}
```

---

## Example 6: Sending an Email

**Command line:**

```bash
node google-api.js gmail send --to "sarah@company.com" --subject "Meeting Reschedule" --body "Hi Sarah, I need to move our meeting from Tuesday to Wednesday at the same time. Does that work? Thanks, Trevor"
```

**Expected output:**

```json
{
  "id": "19c7c890ab3d67e2",
  "threadId": "19c7c890ab3d67e2",
  "labelIds": ["SENT"]
}
```

---

## Example 7: Reading a Google Sheet

**Command line:**

```bash
node google-api.js sheets read 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms "Sheet1!A1:D5" --pretty
```

**Expected output:**

```json
{
  "range": "Sheet1!A1:D5",
  "values": [
    ["Name", "Email", "Status", "Revenue"],
    ["John Smith", "john@example.com", "Active", "$15,000"],
    ["Sarah Chen", "sarah@company.com", "Active", "$22,500"],
    ["Mike Johnson", "mike@vendor.com", "Pending", "$8,000"],
    ["Lisa Wang", "lisa@partner.com", "Active", "$31,200"]
  ]
}
```

---

## Example 8: Managing Tasks

**List all task lists:**

```bash
node google-api.js tasks lists --pretty
```

**Output:**

```json
{
  "items": [
    {
      "id": "MDcyNjE2NTI4MzM2MDQ3MzQ1OTk6MDow",
      "title": "My Tasks"
    },
    {
      "id": "MDcyNjE2NTI4MzM2MDQ3MzQ1OTk6MTA2MzYzMTk0NzoxMA",
      "title": "Work Projects"
    }
  ]
}
```

**Create a new task:**

```bash
node google-api.js tasks create MDcyNjE2NTI4MzM2MDQ3MzQ1OTk6MDow --title "Follow up with client by Friday" --pretty
```

**Output:**

```json
{
  "id": "abc123",
  "title": "Follow up with client by Friday",
  "status": "needsAction"
}
```

---

## Example 9: Searching for Places

**Command line:**

```bash
node google-api.js places search "coffee shops near Times Square" --pretty
```

**Expected output:**

```json
{
  "places": [
    {
      "name": "Blue Bottle Coffee",
      "address": "1 Rockefeller Plaza, New York, NY 10020",
      "rating": 4.3,
      "priceLevel": "MODERATE"
    },
    {
      "name": "Starbucks Reserve",
      "address": "1585 Broadway, New York, NY 10036",
      "rating": 4.1,
      "priceLevel": "MODERATE"
    }
  ]
}
```

---

## Example 10: JWT Token Exchange (For AI Agents Making Direct API Calls)

This is the code pattern your AI uses behind the scenes to authenticate:

```javascript
const crypto = require("crypto");
const https = require("https");
const fs = require("fs");

const sa = JSON.parse(fs.readFileSync(process.env.GOOGLE_SA_KEY_FILE, "utf8"));
const now = Math.floor(Date.now() / 1000);

const header = Buffer.from(JSON.stringify({
  alg: "RS256", typ: "JWT"
})).toString("base64url");

const payload = Buffer.from(JSON.stringify({
  iss: sa.client_email,                     // Service account email
  sub: process.env.GOOGLE_IMPERSONATE_USER, // User to impersonate
  aud: sa.token_uri,                        // Token endpoint
  iat: now,                                 // Issued now
  exp: now + 3600,                          // Expires in 1 hour
  scope: "https://mail.google.com/"         // The scope you need
})).toString("base64url");

const signature = crypto.sign(
  "sha256",
  Buffer.from(header + "." + payload),
  sa.private_key
).toString("base64url");

const jwt = header + "." + payload + "." + signature;

// Exchange JWT for access token:
// POST to https://oauth2.googleapis.com/token
// Body: grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion=<jwt>
// Response: { "access_token": "ya29.xxx", "token_type": "Bearer", "expires_in": 3600 }
```

---

## Example 11: Asking Your AI (Conversation Style)

Here is what a typical conversation looks like after setup:

**You:** Check my email for anything from Pam Perry this week

**AI:** I found 2 emails from Pam Perry this week:

1. Subject: "Event Venue Options"
   Date: Wednesday at 3:15 PM
   Preview: "Hi Trevor, I found 3 great venues for the April event..."

2. Subject: "RE: Speaker Lineup"
   Date: Monday at 10:42 AM
   Preview: "The confirmed speakers so far are..."

Would you like me to read the full text of either email?

**You:** Yes, read the first one

**AI:** Here is the full email:

From: Pam Perry (pam@company.com)
Date: Wednesday, February 26, 2026 at 3:15 PM
Subject: Event Venue Options

Hi Trevor,

I found 3 great venues for the April event:

1. The Grand Ballroom at Marriott Marquis - capacity 500, $15,000
2. Chelsea Piers Event Space - capacity 300, $8,500
3. Rooftop at 230 Fifth - capacity 200, $6,000

All three are available on April 12. Let me know which direction you want to go and I will start the deposit process.

Best,
Pam

---

## Example 12: Error Recovery (Self-Correction in Action)

**Scenario:** The AI tries to check Workspace email using GOG CLI and gets an error.

**Wrong approach (what NOT to do):**

```
AI: I tried to check your email but got a 401 Unauthorized error.
I cannot access your Gmail. You may need to reconfigure the credentials.
```

**Correct approach (self-correction):**

```
AI: I got a 401 error using GOG CLI for trevor@blackceo.com.
That is a Workspace account - I should be using google-api.js,
not GOG. Let me switch tools and try again.

[Switches to google-api.js]

Here are your 3 most recent unread emails:
1. From: sarah@company.com - "Q3 Budget Review"
2. From: newsletter@industry.com - "Weekly Update"
3. From: john@vendor.com - "Invoice #1234"
```

The AI identifies the wrong tool, corrects itself, and retries - without pushing the problem back to the user.

---

## Example 13: Verifying Setup Is Complete

Run these commands in Terminal to confirm everything is set up correctly:

```bash
# Check Node.js version (must be 18+)
node --version

# Check environment variables
echo "SA Key File: $GOOGLE_SA_KEY_FILE"
echo "Impersonate User: $GOOGLE_IMPERSONATE_USER"
echo "Places API Key: $GOOGLE_PLACES_API_KEY"

# Test each service
echo "=== Gmail ==="
node google-api.js gmail unread --limit 1 --pretty

echo "=== Calendar ==="
node google-api.js calendar today --pretty

echo "=== Drive ==="
node google-api.js drive list --limit 1 --pretty

echo "=== Contacts ==="
node google-api.js contacts list --limit 1 --pretty

echo "=== Sheets ==="
node google-api.js sheets list --pretty

echo "=== Docs ==="
node google-api.js docs list --pretty

echo "=== Slides ==="
node google-api.js slides list --pretty

echo "=== Tasks ==="
node google-api.js tasks lists --pretty

echo "=== YouTube ==="
node google-api.js youtube channels --pretty

echo "=== Chat ==="
node google-api.js chat spaces --pretty

echo "=== Places ==="
node google-api.js places search "coffee near me" --pretty

echo "=== Forms ==="
node google-api.js forms list --pretty

echo "=== Keep ==="
node google-api.js keep list --pretty

echo "=== Admin ==="
node google-api.js admin users --limit 1 --pretty
```

Each command should return JSON data. If any command returns an error, check the Troubleshooting section in INSTALL.md.
