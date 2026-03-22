# Google Workspace Integration - Usage Instructions

This document covers how to use the Google Workspace CLI (gws) day to day after installation is complete.

---

## Common Commands

These are the commands you will use most often. Just ask your AI agent in plain English, or run these commands directly.

### Send Email
```bash
gws gmail messages send --json '{"to": "recipient@example.com", "subject": "Hello", "body": "Your message here"}'
```

Or use the helper:
```bash
gws gmail +send
```

### Check Calendar
```bash
gws calendar +agenda
```

Shows today's events in a readable format.

### Upload to Drive
```bash
gws drive files upload --file /path/to/file.pdf
```

Or use the helper:
```bash
gws drive +upload
```

### Read a Google Sheet
```bash
gws sheets spreadsheets values get --spreadsheetId YOUR_SHEET_ID --range "Sheet1!A1:D10"
```

Or use the helper:
```bash
gws sheets +read
```

### Create a Google Doc
```bash
gws docs documents create --json '{"title": "My New Document"}'
```

Or use the helper:
```bash
gws docs +write
```

---

## Helper Commands

The gws CLI includes helper commands that make common tasks easier. These use the plus sign (+) syntax.

### Gmail Helpers
```bash
gws gmail +send      # Interactive email composition
gws gmail +triage    # Show unread emails needing attention
gws gmail +search    # Interactive search helper
```

### Calendar Helpers
```bash
gws calendar +agenda     # Show today's agenda
gws calendar +create     # Interactive event creation
gws calendar +find       # Find available meeting times
```

### Drive Helpers
```bash
gws drive +upload        # Interactive file upload
gws drive +search        # Search with filters
gws drive +share         # Share files with others
```

### Sheets Helpers
```bash
gws sheets +read         # Interactive sheet reading
gws sheets +append       # Append rows to a sheet
gws sheets +create       # Create a new spreadsheet
```

### Docs Helpers
```bash
gws docs +write          # Interactive document creation
gws docs +read           # Read document content
gws docs +edit           # Edit existing documents
```

---

## MCP Server Mode

The gws CLI can run as an MCP (Model Context Protocol) server for advanced integrations.

Start the MCP server with specific services:
```bash
gws mcp -s drive,gmail,calendar
```

This allows AI agents to call Google services through a standardized protocol.

To run with all services:
```bash
gws mcp -s gmail,calendar,drive,contacts,docs,sheets,tasks,keep,forms,youtube
```

---

## Token Refresh

Authentication tokens expire after a period of time. The gws CLI handles refresh automatically for most operations.

If you encounter authentication errors, manually refresh your tokens:

For Gmail users:
```bash
gws auth login -s gmail,calendar,drive,contacts,docs,sheets,tasks,keep,forms,youtube
```

For Workspace users using gcloud:
```bash
gcloud auth application-default login
gws auth setup
```

For Workspace users using service account keys, no refresh is needed. The service account authenticates automatically.

---

## Troubleshooting Common Errors

### "401 Unauthorized"
This means your authentication token has expired or is invalid.

Fix: Run the appropriate login command for your account type to refresh tokens.

### "403 Forbidden"
This means you do not have permission for the requested action.

Fix: Check that you authorized all required scopes. For Workspace, verify Domain-Wide Delegation includes the scope needed for the service you are accessing.

### "404 Not Found"
The requested resource does not exist.

Fix: Check the ID of the file, document, or resource you are trying to access. Use list commands to find correct IDs.

### "429 Too Many Requests"
You have hit Google's rate limit.

Fix: Wait a minute and try again. For high-volume operations, add delays between requests.

### "API not enabled"
The required Google API is not turned on in your Cloud project.

Fix: Go to Google Cloud Console, navigate to APIs & Services, and enable the required API.

### "command not found: gws"
The gws CLI is not installed or not in your PATH.

Fix: Reinstall with npm install -g @googleworkspace/cli. Close and reopen your terminal.

---

## Asking Your AI Agent

You do not need to remember these commands. Just ask your AI in plain English:

- "Check my email for unread messages"
- "What is on my calendar today?"
- "Upload this file to my Drive"
- "Read the data from my Sales spreadsheet"
- "Create a new document called Meeting Notes"

Your AI will translate these requests into the appropriate gws commands.

---

## Self-Correction for AI Agents

If a Google API call returns an error:

1. Check if authentication has expired
2. Verify the correct account type is being used (Gmail vs Workspace)
3. Confirm all required scopes were authorized
4. Check if the API is enabled in Google Cloud Console
5. Retry with the correct command

Never tell the user "I cannot do this" without trying the refresh steps first.
