# Google Workspace Setup - SKILL.md

## What This Skill Is About

This skill connects your AI agent to Google's tools - Gmail, Google Calendar,
Google Drive, Google Docs, and Google Sheets. Once connected, your AI can read
your emails, check your calendar, open and edit documents, and work with
spreadsheets on your behalf.

The connection works through something called a "service account" - think of it
as a special login that your AI uses to access your Google account. You create
this login inside Google Cloud Platform (GCP), give it permission to act on your
behalf, and then your AI can do the rest.

## When to Use This Skill

- Setting up Google API access for the first time
- Creating a new Google Cloud Platform project for OpenClaw
- Creating a service account (the special login your AI uses)
- Enabling the required Google APIs (Gmail, Calendar, Drive, Docs, Sheets, People)
- Setting up Domain-Wide Delegation (required for Google Workspace business accounts)
- Configuring OAuth scopes (the specific permissions your AI gets)
- Troubleshooting "Access denied" or "401" errors when your AI tries to use Google services
- Moving from personal Gmail access to Google Workspace business account access

## What This Skill Covers

1. **Creating a Google Cloud project** - Where to go, what to click, what to name it
2. **Enabling 6 core APIs** - Gmail, Calendar, Drive, Docs, Sheets, and People (Contacts)
3. **Creating a service account** - The special login your AI will use
4. **Generating and securing the JSON key file** - The password file for the service account
5. **Domain-Wide Delegation setup** - Required for Google Workspace (business) accounts, done in both the GCP Console and the Google Admin Console
6. **OAuth scopes** - The specific permissions to grant (Gmail, Calendar, Drive, Docs, Sheets, Contacts)
7. **OpenClaw configuration** - Where to put the key file and environment variables
8. **Testing the connection** - How to verify everything works
9. **Troubleshooting** - Common errors and how to fix them
10. **Security notes** - How to keep your setup safe

## Files in This Folder and Reading Order

1. **SKILL.md** - You are here. Start here for the overview.
2. **google-workspace-setup-full.md** - The complete setup guide with every step explained. Read this to execute the setup.
3. **INSTRUCTIONS.md** - Step-by-step execution instructions.
4. **INSTALL.md** - Installation-specific notes.
5. **EXAMPLES.md** - Example configurations and usage patterns.
6. **CORE_UPDATES.md** - What to add to your core workspace files after setup.
7. **google-workspace-setup.skill** - Skill metadata file.

## Prerequisites

- The Teach Yourself Protocol (TSP) must be installed first. If TSP is not in your
  AGENTS.md or TOOLS.md, stop and install TSP before proceeding.
- You need Google Workspace admin access (for business accounts) OR a personal
  Google account (for personal Gmail).
- OpenClaw must already be installed and running.
- You need access to both the Google Cloud Console (console.cloud.google.com) and
  the Google Admin Console (admin.google.com) if using a Workspace account.

## Key Things the AI Agent Needs to Know

- **Two different setups exist.** Personal Gmail uses OAuth (through the GOG CLI tool).
  Google Workspace business accounts use a service account with Domain-Wide Delegation.
  Never mix these up - using the wrong method will always fail.

- **Domain-Wide Delegation requires two steps.** First, enable it on the service account
  in the GCP Console. Second, authorize the scopes in the Google Admin Console. Missing
  either step causes "Access denied" errors.

- **The JSON key file is like a password.** Store it securely (usually in ~/clawd/secrets/).
  Set file permissions to 600 so only the owner can read it. Never share it or commit it
  to version control.

- **Scopes must match exactly.** The scopes you authorize in the Admin Console must match
  what the agent requests in code. If the agent requests a scope that is not authorized,
  it gets a 401 error. The six core scopes are: gmail.modify, calendar, drive, documents,
  spreadsheets, and contacts.readonly.

- **Always use full scopes, not readonly variants alone.** Requesting documents.readonly
  by itself often fails. Request both drive and documents together for reliable access.

- **The service account impersonates a real user.** When accessing Workspace resources,
  the service account acts as a specific user (like trevor@yourdomain.com). This user
  email must be specified in the configuration.

- **Test after setup.** Ask the AI to check Gmail or Calendar. If it works, the setup
  is complete. If it gets errors, check the troubleshooting section in the full guide.
