# Google Workspace Setup - Usage Instructions

This document covers how to USE your Google Workspace integration day to day, after you have completed the installation steps in INSTALL.md.

---

## What Your AI Can Do After Setup

Once the Google Workspace setup is complete, your AI assistant can:

- **Read and send emails** through Gmail
- **Check and create calendar events** through Google Calendar
- **Find, upload, and organize files** through Google Drive
- **Read and edit documents** through Google Docs
- **Read and update spreadsheets** through Google Sheets
- **Look up contacts** through the People API

All of this happens automatically. You just ask your AI in plain English, and it uses the service account you set up to do the work.

---

## How to Ask Your AI for Google Workspace Tasks

You do not need to use any special commands. Just talk to your AI like you would talk to a human assistant. Here are examples organized by service:

### Gmail

- "Check my Gmail for unread messages"
- "Search my email for messages from john@example.com"
- "Send an email to sarah@company.com with the subject 'Meeting Tomorrow' and tell her I will be 10 minutes late"
- "Show me my Gmail labels"
- "Find all emails about the quarterly report"

### Google Calendar

- "What is on my calendar today?"
- "Show me my schedule for this week"
- "Create a meeting called 'Team Standup' for tomorrow at 9 AM"
- "Do I have any conflicts on Friday afternoon?"

### Google Drive

- "List my 10 most recent files in Google Drive"
- "Search my Drive for anything about 'budget proposal'"
- "Upload this file to my Google Drive"

### Google Docs

- "List my recent Google Docs"
- "Read the document titled 'Marketing Plan'"
- "Create a new Google Doc called 'Meeting Notes'"

### Google Sheets

- "List my Google Sheets"
- "Read the data from Sheet1 in my 'Sales Tracker' spreadsheet"
- "Update cell A1 in my 'Inventory' spreadsheet to say 'Updated'"

### Contacts

- "Look up John Smith in my contacts"
- "Find the email address for Pam Perry"
- "Show me my most recent contacts"

---

## How Authentication Works (Behind the Scenes)

You do not need to do anything for authentication after the initial setup. Here is what happens when you ask your AI to check your email:

1. Your AI reads the JSON key file you set up during installation
2. It creates a signed "permission slip" (called a JWT) saying "I am the OpenClaw-assistant service account and I need to act as you@yourcompany.com"
3. It sends that permission slip to Google
4. Google checks the Domain-Wide Delegation settings and says "Yes, this service account is authorized"
5. Google gives your AI a temporary access pass (called a token) that lasts for 1 hour
6. Your AI uses that token to access Gmail, Calendar, or whatever you asked for
7. When the token expires after 1 hour, your AI automatically creates a new one

You never need to click "Allow" or re-enter your password. It all happens silently.

---

## Important Rules to Remember

### Workspace Email vs. Personal Gmail

Your AI uses DIFFERENT methods for different types of email accounts:

| Email Type | Example | Method Used |
|-----------|---------|-------------|
| Business email (Google Workspace) | you@yourcompany.com | Service Account (set up in INSTALL.md) |
| Personal Gmail | you@gmail.com | GOG CLI (different tool, see Skill 13) |

**Do not mix these up.** If you ask your AI to check your @gmail.com account, it needs to use a different method than the one set up here. The service account method only works for Google Workspace (business) accounts.

### When Things Stop Working

If your AI suddenly cannot access your Google services:

1. **Check if the service account key is still valid** - Keys do not expire on their own, but someone might have deleted it in the Google Cloud Console
2. **Check if Domain-Wide Delegation is still authorized** - Go to admin.google.com and verify the delegation entry is still there
3. **Check if the APIs are still enabled** - Go to console.cloud.google.com and verify each API shows "Manage" (not "Enable")
4. **Check your environment variables** - Open Terminal and run:
   ```bash
   echo $GCP_SERVICE_ACCOUNT_EMAIL
   echo $GCP_IMPERSONATE_USER
   ```
   If either is blank, the variables may have been lost. Re-add them to ~/.zshrc

### Revoking Access

If you ever want to cut off your AI's access to your Google Workspace:

1. Go to: https://admin.google.com/ac/owl/domainwidedelegation
2. Find the entry with your service account's Client ID
3. Click the delete button (trash icon) next to it
4. Your AI immediately loses all access

You can also delete the JSON key file from your computer:
```bash
rm ~/clawd/secrets/gcp-service-account.json
```

---

## Scope Management

"Scopes" are the specific permissions your AI has. The basic setup in INSTALL.md gives your AI these 6 scopes:

1. Gmail (read and modify)
2. Calendar (full access)
3. Drive (full access)
4. Docs (full access)
5. Sheets (full access)
6. Contacts (read only)

If you need more services (like YouTube, Google Chat, Google Forms, Slides, Tasks, etc.), you need to:

1. Enable the additional API in Google Cloud Console
2. Add the new scope to the Domain-Wide Delegation entry in the Admin Console
3. The full list of all available scopes (70+) is in Skill 13 (Google Workspace Integration)

**Important:** When you add new scopes, you must re-paste the ENTIRE scope list (old + new) and click Authorize again. Google does not let you add scopes one at a time - you replace the whole list each time.

---

## Security Best Practices

1. **Keep only one JSON key file per service account.** If you create a new key, delete the old one from both your computer and the Google Cloud Console.
2. **Never share the JSON key file.** Do not email it, post it in a chat, or commit it to a code repository.
3. **Review the delegation entry periodically.** Go to admin.google.com every few months and confirm only your authorized service accounts are listed.
4. **Monitor API usage.** You can see how many API calls are being made in the Google Cloud Console under APIs & Services.

---

## Getting More Help

- **Full documentation:** See the google-workspace-setup-full.md file in this same folder
- **Complete integration guide:** See Skill 13 (Google Workspace Integration) for the comprehensive setup with all 26 services
- **Troubleshooting:** See the Troubleshooting section in INSTALL.md or the full Skill 13 documentation
