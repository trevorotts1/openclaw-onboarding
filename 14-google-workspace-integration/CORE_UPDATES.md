# Google Workspace Integration - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## Google Workspace Integration [PRIORITY: CRITICAL]

Google Workspace access uses the gws CLI. One tool for both Gmail and Workspace accounts.
No more google-api.js or gog.

- Gmail accounts (@gmail.com): Use gws auth login with OAuth
- Workspace accounts (@yourdomain.com): Use gws auth setup with gcloud or service account key
- Domain-Wide Delegation required for Workspace (81 scopes)
- Token refresh: run gws auth login when tokens expire
- Full guide: ~/Downloads/openclaw-master-files/OpenClaw Onboarding/14-google-workspace-integration/google-workspace-integration-full.md
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## Google Workspace Integration [PRIORITY: CRITICAL]

Tool: Google Workspace CLI (gws)
Install: npm install -g @googleworkspace/cli

Authentication:
- Gmail: gws auth login -s gmail,calendar,drive,contacts,docs,sheets,tasks,keep,forms,youtube
- Workspace: gws auth setup (with gcloud) or GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE env var

Common commands:
- gws gmail +triage (check unread email)
- gws calendar +agenda (view today's schedule)
- gws drive files list --params '{"pageSize": 5}' (list Drive files)
- gws sheets spreadsheets create --json '{"properties": {"title": "Test"}}'
- gws docs +write (interactive document creation)

MCP server mode: gws mcp -s drive,gmail,calendar
Token refresh: gws auth login (when tokens expire)

Full guide: ~/Downloads/openclaw-master-files/OpenClaw Onboarding/14-google-workspace-integration/google-workspace-integration-full.md
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## Google Workspace Integration

Google Workspace CLI (gws) installed [DATE]. Handles all Google services including Gmail, Calendar, Drive, Docs, Sheets, Chat, Tasks, Keep, Forms, and YouTube.

Replaces: google-api.js and gog CLI
Authentication: OAuth for Gmail, service account for Workspace
Domain-Wide Delegation: 81 scopes configured for Workspace

Full guide: ~/Downloads/openclaw-master-files/OpenClaw Onboarding/14-google-workspace-integration/google-workspace-integration-full.md
```

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

---

## USER.md - NO UPDATE NEEDED

---

## SOUL.md - NO UPDATE NEEDED
