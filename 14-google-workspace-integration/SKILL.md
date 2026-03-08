# Skill 13: Google Workspace Integration

## What This Skill Is About

This skill teaches your AI agent how to connect to your Google Workspace account so it can read your email, check your calendar, manage your Drive files, edit Google Docs and Sheets, and work with 20+ other Google services - all without sharing your password.

It uses a "Service Account" (think of it as a robot employee with its own ID badge) combined with "Domain-Wide Delegation" (security clearance you grant through your Google admin panel). Once set up, your AI agent can access Google services silently in the background, 24/7, without you ever clicking "Allow" in a browser.

This guide is for Google Workspace business accounts only (like you@yourdomain.com). If you have a personal @gmail.com account, this is the wrong guide.

## When to Use This Skill

- You are connecting OpenClaw to Google Workspace for the first time
- You need to set up Gmail, Calendar, Drive, Docs, Sheets, or Slides access for your AI
- You are creating a Google Cloud project and service account
- You need to configure Domain-Wide Delegation in your Google Admin Console
- You are installing or configuring the GOG skill for Google access
- You are troubleshooting 401 or 403 errors when your AI tries to access Google services
- You need to enable Google APIs (Gmail, Calendar, Drive, and 23 others)
- You need the complete list of OAuth scopes for Domain-Wide Delegation

## What This Skill Covers

- The difference between Google Cloud Console and Google Admin Console (and what you do in each)
- Creating a Google Cloud project from scratch
- Enabling all 26 required Google APIs with direct links to each one
- Setting up the OAuth Consent Screen (required or Gmail will not work)
- Creating a Service Account and downloading its JSON key file
- Fixing Organization Policy blocks (common for accounts created after May 2024)
- Configuring Domain-Wide Delegation with all 70+ OAuth scopes
- Installing the google-api.js script (zero dependencies, Node.js only)
- Installing and configuring the GOG skill in OpenClaw
- Testing every Google service to confirm it works
- Updating all six workspace files (AGENTS.md, TOOLS.md, MEMORY.md, USER.md, IDENTITY.md, HEARTBEAT.md) so the AI remembers which tool to use for which account type
- Complete troubleshooting guide for the most common errors
- Lessons learned from real-world debugging

## Files in This Folder and Reading Order

1. **SKILL.md** - You are here. Start here for the overview.
2. **google-workspace-integration-full.md** - The complete step-by-step guide. Read this to execute the setup.
3. **INSTRUCTIONS.md** - Execution instructions and rules for the AI agent.
4. **INSTALL.md** - Installation steps specific to this skill.
5. **EXAMPLES.md** - Example commands and usage patterns.
6. **CORE_UPDATES.md** - What to add to your core .md files (AGENTS.md, TOOLS.md, etc.).
7. **google-workspace-integration.skill** - Skill metadata file.

## Prerequisites

- Teach Yourself Protocol (TYP) must be learned first
- Backup Protocol must be in place
- Google Workspace account with Super Admin access (not a free @gmail.com)
- Node.js v18 or newer installed on your machine

## Key Things the AI Agent Must Know

1. **Two tools, two account types.** Workspace accounts (@yourdomain.com) use google-api.js with the Service Account. Personal Gmail accounts (@gmail.com) use the GOG CLI with OAuth. Never mix them. Mixing always fails.

2. **The most common error is using the wrong tool.** If you get a 401 on a Workspace account and you are using GOG, switch to google-api.js immediately. That is almost always the fix.

3. **Scopes must include both "drive" and "documents" together.** Requesting "documents.readonly" alone will cause 401 errors. Always request the full read/write scopes.

4. **The OAuth Consent Screen is required.** Without it, Gmail scopes are blocked silently. Configure it as "Internal" before testing anything.

5. **Organization Policy blocks are common.** If the Google Cloud organization was created after May 2024, service account key creation is blocked by default. Section 8 of the full guide explains how to fix this.

6. **After setup, update all six workspace files.** The full guide includes exact text blocks to add to AGENTS.md, TOOLS.md, MEMORY.md, USER.md, IDENTITY.md, and HEARTBEAT.md. This prevents the AI from forgetting the correct tool in future sessions.

7. **Scope changes require re-authorization.** If you ever add new scopes, you must go back to the Admin Console and re-paste the full scope list. Old scopes do not update automatically.
