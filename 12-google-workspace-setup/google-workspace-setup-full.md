# Google Workspace Setup

Give your AI access to Google Docs, Gmail, Calendar, Drive, and Sheets.



✅ What This Does

Once set up, your AI can:
- Read and edit Google Docs
- Send and read Gmail
- Check and create Calendar events
- Access Google Drive files
- Read and update Google Sheets



🚀 Quick Setup (Tell Your AI)

Copy this prompt and send it to your AI assistant:


Set up Google Workspace integration for me. I need you to:

1. Help me create a GCP (Google Cloud Platform) project
2. Enable the necessary APIs (Gmail, Calendar, Drive, Docs, Sheets)
3. Create a service account with domain-wide delegation
4. Generate and download the service account JSON key
5. Configure OpenClaw to use the service account
6. Test the connection

Walk me through each step. Ask me for any information you need.
My Google Workspace email is: [YOUR_EMAIL@yourdomain.com]


Your AI will guide you through the process step-by-step.



🔧 Manual Setup Steps

If you prefer to do it yourself:

Step 1: Create a Google Cloud Project

1. Go to: https://console.cloud.google.com/
2. Click the project dropdown (top left) → New Project
3. Name it something like "OpenClaw AI"
4. Click Create
5. Wait for it to be created, then select it

Step 2: Enable APIs

Go to APIs & Services → Library and enable these:
- Gmail API
- Google Calendar API
- Google Drive API
- Google Docs API
- Google Sheets API
- People API (for Contacts)

Step 3: Create a Service Account

1. Go to APIs & Services → Credentials
2. Click Create Credentials → Service Account
3. Name: `OpenClaw-assistant`
4. Click Create and Continue
5. Skip the optional steps, click Done

Step 4: Create a Key for the Service Account

1. Click on the service account you just created
2. Go to Keys tab
3. Click Add Key → Create new key
4. Choose JSON
5. Click Create
6. A JSON file downloads - save it securely

Step 5: Move the Key to Your Secrets Folder


mv ~/Downloads/your-project-*.json ~/clawd/secrets/gcp-service-account.json
chmod 600 ~/clawd/secrets/gcp-service-account.json


Step 6: Enable Domain-Wide Delegation (Google Workspace only)

If you use Google Workspace (not personal Gmail):

1. Go to your service account in GCP Console
2. Click Edit (pencil icon)
3. Check Enable Google Workspace Domain-wide Delegation
4. Save

Then, as a Google Workspace admin:
1. Go to: https://admin.google.com/
2. Navigate to Security → Access and data control → API controls
3. Click Manage Domain Wide Delegation
4. Click Add new
5. Enter the service account's Client ID (found in GCP Console)
6. Add these scopes:

https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/drive
https://www.googleapis.com/auth/documents
https://www.googleapis.com/auth/spreadsheets
https://www.googleapis.com/auth/contacts.readonly

7. Click Authorize

Step 7: Configure OpenClaw

Add these to your secrets file (`~/clawd/secrets/.env`):

env
GCP_PROJECT_ID=your-project-id
GCP_SERVICE_ACCOUNT_EMAIL=OpenClaw-assistant@your-project-id.iam.gserviceaccount.com
GCP_IMPERSONATE_USER=your-email@yourdomain.com


Then tell your AI:
> "My GCP service account is at `~/clawd/secrets/gcp-service-account.json` and it impersonates `your-email@yourdomain.com`"



✅ Test the Connection

Ask your AI:

> "Check my Gmail for unread messages"

or

> "What's on my calendar today?"

If it works, you're all set! 🎉



🔧 Troubleshooting

| Problem | Solution |
| "Access denied" errors | Make sure domain-wide delegation is enabled and scopes are authorized |
| "Service account not found" | Check the JSON key file path is correct |
| "Cannot impersonate user" | The service account needs domain-wide delegation enabled in both GCP and Admin Console |
| Gmail/Calendar not working | Make sure you enabled all the required APIs in Step 2 |



🔒 Security Notes

- The service account can only access what you authorize
- Domain-wide delegation should only be granted to trusted service accounts
- Keep the JSON key file secure - treat it like a password
- You can revoke access at any time in the Admin Console



📚 Learn More

- Google Cloud Console: https://console.cloud.google.com/
- Google Workspace Admin: https://admin.google.com/
- API Documentation: https://developers.google.com/workspace


