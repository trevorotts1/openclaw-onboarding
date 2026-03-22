# Google Workspace Integration - Examples

Real examples showing the Google Workspace CLI (gws) in action.

---

## Gmail Examples

### Send an Email
```bash
gws gmail messages send --json '{
  "to": "sarah@company.com",
  "subject": "Q3 Budget Review",
  "body": "Hi Sarah, I have reviewed the Q3 budget. Can we schedule a call to discuss? Thanks!"
}'
```

Using the helper:
```bash
gws gmail +send
```

### Reply to an Email
First get the message ID from a list or search, then:
```bash
gws gmail messages send --json '{
  "to": "sarah@company.com",
  "subject": "Re: Q3 Budget Review",
  "body": "Thanks for the quick response. Wednesday works for me.",
  "threadId": "THREAD_ID_HERE"
}'
```

### Triage Unread Emails
```bash
gws gmail +triage
```

This shows unread emails organized by priority.

### Search Emails
```bash
gws gmail messages list --params '{"q": "from:client@email.com newer_than:7d"}'
```

Using the helper:
```bash
gws gmail +search
```

Search for emails with attachments:
```bash
gws gmail messages list --params '{"q": "has:attachment filename:pdf"}'
```

---

## Calendar Examples

### Show Today's Agenda
```bash
gws calendar +agenda
```

### List Events for a Date Range
```bash
gws calendar events list --params '{
  "timeMin": "2026-03-20T00:00:00Z",
  "timeMax": "2026-03-27T23:59:59Z"
}'
```

### Create an Event
```bash
gws calendar events create --json '{
  "summary": "Team Standup",
  "start": {"dateTime": "2026-03-20T09:00:00", "timeZone": "America/New_York"},
  "end": {"dateTime": "2026-03-20T09:30:00", "timeZone": "America/New_York"},
  "attendees": [{"email": "teammate@company.com"}]
}'
```

Using the helper:
```bash
gws calendar +create
```

---

## Drive Examples

### List Files
```bash
gws drive files list --params '{"pageSize": 10}'
```

### Search Files
```bash
gws drive files list --params '{"q": "name contains \"Quarterly Report\""}'
```

Using the helper:
```bash
gws drive +search
```

### Upload a File
```bash
gws drive files upload --file /path/to/document.pdf
```

Using the helper:
```bash
gws drive +upload
```

### Download a File
```bash
gws drive files get --fileId YOUR_FILE_ID --download --destination /path/to/save/
```

---

## Sheets Examples

### Create a New Spreadsheet
```bash
gws sheets spreadsheets create --json '{
  "properties": {"title": "Sales Tracker 2026"}
}'
```

### Read Cell Values
```bash
gws sheets spreadsheets values get \
  --spreadsheetId YOUR_SPREADSHEET_ID \
  --range "Sheet1!A1:D10"
```

Using the helper:
```bash
gws sheets +read
```

### Append Rows to a Sheet
```bash
gws sheets spreadsheets values append \
  --spreadsheetId YOUR_SPREADSHEET_ID \
  --range "Sheet1!A1" \
  --json '{
    "values": [["John Smith", "john@example.com", "Active", "$15000"]]
  }'
```

Using the helper:
```bash
gws sheets +append
```

---

## Docs Examples

### Create a Document
```bash
gws docs documents create --json '{
  "title": "Meeting Notes - March 20"
}'
```

Using the helper:
```bash
gws docs +write
```

### Read a Document
```bash
gws docs documents get --documentId YOUR_DOCUMENT_ID
```

---

## Workflow Helpers

### Generate a Standup Report
```bash
gws +standup-report
```

This helper gathers your recent emails, calendar events, and tasks to generate a standup summary.

### Meeting Preparation
```bash
gws +meeting-prep
```

This helper collects information about upcoming meetings, including attendee details from contacts and relevant emails.

### Weekly Digest
```bash
gws +weekly-digest
```

This helper creates a summary of your week: emails sent, meetings attended, tasks completed, and upcoming priorities.

---

## Example Conversation with Your AI

Here is what a typical interaction looks like after setup:

**You:** Check my email for anything from Pam Perry this week

**AI:** I will search your Gmail for emails from Pam Perry in the last 7 days.
```bash
gws gmail messages list --params '{"q": "from:pam@company.com newer_than:7d"}'
```

I found 2 emails from Pam Perry this week:

1. Subject: "Event Venue Options"
   Date: Wednesday at 3:15 PM
   Preview: "Hi, I found 3 great venues for the April event..."

2. Subject: "RE: Speaker Lineup"
   Date: Monday at 10:42 AM
   Preview: "The confirmed speakers so far are..."

Would you like me to read the full text of either email?

**You:** Yes, read the first one

**AI:** Here is the full email:

From: Pam Perry (pam@company.com)
Date: Wednesday, March 18, 2026 at 3:15 PM
Subject: Event Venue Options

Hi,

I found 3 great venues for the April event:

1. The Grand Ballroom at Marriott Marquis - capacity 500, $15,000
2. Chelsea Piers Event Space - capacity 300, $8,500
3. Rooftop at 230 Fifth - capacity 200, $6,000

All three are available on April 12. Let me know which direction you want to go and I will start the deposit process.

Best,
Pam

**You:** Create a calendar event for us to discuss this on Friday at 2 PM

**AI:** I will create that meeting now.
```bash
gws calendar events create --json '{
  "summary": "Discuss Event Venues with Pam",
  "start": {"dateTime": "2026-03-20T14:00:00", "timeZone": "America/New_York"},
  "end": {"dateTime": "2026-03-20T15:00:00", "timeZone": "America/New_York"},
  "attendees": [{"email": "pam@company.com"}]
}'
```

Done! I have scheduled the meeting for Friday, March 20 at 2:00 PM and invited Pam.
