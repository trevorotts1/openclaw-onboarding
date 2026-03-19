# Skill 14: Google Workspace Integration

## What This Skill Is About

This skill connects your AI agent to Google Workspace using the official Google Workspace CLI (gws). One tool handles everything: Gmail, Calendar, Drive, Docs, Sheets, Chat, Tasks, Keep, Forms, and YouTube.

The Google Workspace CLI replaces older tools like the custom google-api.js script and the GOG CLI. It supports both personal Gmail accounts (via OAuth) and Google Workspace business accounts (via service account with Domain-Wide Delegation).

## When to Use This Skill

1. You are connecting OpenClaw to Google services for the first time
2. You need to access Gmail, Calendar, Drive, Docs, Sheets, or other Google services
3. You are setting up a new Google Cloud project
4. You need to configure Domain-Wide Delegation for a Workspace account
5. You are troubleshooting 401 or 403 errors with Google APIs
6. You are migrating from the old google-api.js or GOG tools

## What This Skill Covers

- Installing the Google Workspace CLI (gws)
- Authenticating with OAuth for personal Gmail accounts
- Authenticating with service accounts for Workspace business accounts
- Configuring Domain-Wide Delegation with all 81 OAuth scopes
- Fixing Organization Policy blocks for newer Google Cloud accounts
- Setting up Google Chat app configuration
- Verifying all services work with test commands
- Installing OpenClaw agent skills for gws
- Daily usage instructions and common commands
- Troubleshooting guide for common errors

## Files in This Folder and Reading Order

1. **SKILL.md** - You are here. Overview and what this skill covers.
2. **INSTALL.md** - Complete step-by-step installation guide.
3. **INSTRUCTIONS.md** - Day-to-day usage instructions.
4. **EXAMPLES.md** - Real command examples and workflows.
5. **CORE_UPDATES.md** - What to add to your core .md files.
6. **QC.md** - Quality control checklist to verify installation.
7. **google-workspace-integration-full.md** - Comprehensive reference with all details.
8. **CHANGELOG.md** - Version history and changes.
9. **google-workspace-integration.skill** - Skill metadata file.

## Prerequisites

Before starting, make sure you have:

- Teach Yourself Protocol (TYP) already learned
- Node.js version 18 or higher installed
- npm (comes with Node.js)
- A Google account (Gmail or Workspace)

## Key Things the AI Agent Must Know

1. **One tool for all accounts.** The gws CLI handles both Gmail and Workspace accounts. No more switching between google-api.js and GOG.

2. **Two authentication paths.** Gmail users use `gws auth login` with OAuth. Workspace users use either `gws auth setup` with gcloud or set `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` for service accounts.

3. **Domain-Wide Delegation is required for Workspace.** Your Google Admin must authorize the service account with all scopes in the Admin Console.

4. **The OAuth Consent Screen is required for Gmail.** Without it, Google blocks access to sensitive scopes.

5. **Organization Policies may block new setups.** Google Cloud accounts created after May 2024 block service account key creation by default. INSTALL.md Section 5 explains how to fix this.

6. **Scopes must include both read and write versions.** The 81-scope list in INSTALL.md covers all services and tool compatibility.

7. **After setup, update all workspace files.** CORE_UPDATES.md includes exact text to add to AGENTS.md, TOOLS.md, and MEMORY.md.

8. **Token refresh is automatic but can be manual.** If tokens expire, run `gws auth login` again to refresh.
