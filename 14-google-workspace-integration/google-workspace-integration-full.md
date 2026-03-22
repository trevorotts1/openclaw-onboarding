# Google Workspace Integration - Complete Reference

This is the comprehensive reference guide for the Google Workspace CLI (gws) integration. It includes everything from INSTALL.md plus detailed explanations of each API, what each scope does, and advanced configuration options.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Authentication](#authentication)
5. [Domain-Wide Delegation](#domain-wide-delegation)
6. [Organization Policy Fixes](#organization-policy-fixes)
7. [Google Chat Configuration](#google-chat-configuration)
8. [Verification Tests](#verification-tests)
9. [All 81 OAuth Scopes Explained](#all-81-oauth-scopes-explained)
10. [Service Reference](#service-reference)
11. [Troubleshooting](#troubleshooting)
12. [Core File Updates](#core-file-updates)

---

## Overview

The Google Workspace CLI (gws) is Google's official command-line tool for accessing Google Workspace services. It replaces multiple older tools with a single, unified interface.

### What gws Replaces

- google-api.js script (custom Node.js tool)
- GOG CLI (third-party tool)
- Multiple separate API clients

### Services Supported

| Service | Status | Notes |
|---------|--------|-------|
| Gmail | Full | Send, receive, search, labels |
| Calendar | Full | Events, agendas, scheduling |
| Drive | Full | Files, folders, sharing |
| Docs | Full | Documents, formatting |
| Sheets | Full | Spreadsheets, formulas |
| Slides | Full | Presentations |
| Chat | Full | Spaces, messages |
| Tasks | Full | Task lists, items |
| Keep | Full | Notes, lists |
| Forms | Full | Forms, responses |
| YouTube | Full | Videos, channels |
| Contacts | Full | People, groups |
| Admin SDK | Full | Users, groups, org units |
| Analytics | Full | Reports, data |
| Tag Manager | Full | Containers, tags |
| Search Console | Full | SEO data |
| BigQuery | Full | SQL queries |

---

## Prerequisites

Before starting:

1. Node.js version 18 or higher
2. npm (included with Node.js)
3. A Google account (Gmail or Workspace)
4. For Workspace: Super Admin access to your domain
5. 20-30 minutes of uninterrupted time

Check Node.js version:
```bash
node --version
```

---

## Installation

### Step 1: Install gws

```bash
npm install -g @googleworkspace/cli
```

### Step 2: Verify Installation

```bash
gws --version
```

Expected output: Version number like 1.0.0 or higher.

---

## Authentication

### Path A: Gmail Accounts (@gmail.com)

Step 1: Run setup
```bash
gws auth setup
```

Step 2: Sign in through the browser window that opens.

Step 3: Authorize services
```bash
gws auth login -s gmail,calendar,drive,contacts,docs,sheets,tasks,keep,forms,youtube
```

Step 4: Click "Allow" for each permission request.

Step 5: Verify
```bash
gws auth list
```

### Path B: Workspace Accounts (@yourdomain.com)

#### Option 1: Using gcloud (Recommended)

Step 1: Install gcloud if not present
```bash
gcloud --version
```

Step 2: Authenticate
```bash
gcloud auth application-default login
```

Step 3: Setup gws
```bash
gws auth setup
```

#### Option 2: Using Service Account JSON

Step 1: Obtain service account JSON from Google Cloud Console.

Step 2: Save to secure location
```
~/clawd/secrets/gcp-service-account.json
```

Step 3: Set environment variable
```bash
export GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=/path/to/service-account.json
```

Step 4: Make permanent
```bash
echo 'export GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=/path/to/service-account.json' >> ~/.zshrc
source ~/.zshrc
```

---

## Domain-Wide Delegation

Required for Workspace accounts. Allows a service account to act on behalf of users.

### Find Your Client ID

1. Go to https://console.cloud.google.com/iam-admin/serviceaccounts
2. Click your service account email
3. Copy the "Unique ID" (long number, NOT the email)

### Authorize in Admin Console

1. Go to https://admin.google.com/ac/owl/domainwidedelegation
2. Sign in as Super Admin
3. Click "Add new"
4. Paste the numeric Client ID
5. Paste all 81 OAuth scopes (see below)
6. Click "Authorize"

### The Complete 81-Scope List

Paste this entire block as one line, comma-separated, no spaces:

```
https://mail.google.com/,https://www.googleapis.com/auth/documents,https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/presentations,https://www.googleapis.com/auth/calendar,https://www.googleapis.com/auth/gmail.modify,https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/gmail.labels,https://www.googleapis.com/auth/gmail.settings.basic,https://www.googleapis.com/auth/tasks,https://www.googleapis.com/auth/contacts,https://www.googleapis.com/auth/directory.readonly,https://www.googleapis.com/auth/chat.messages,https://www.googleapis.com/auth/chat.spaces,https://www.googleapis.com/auth/chat.memberships,https://www.googleapis.com/auth/forms.body,https://www.googleapis.com/auth/forms.responses.readonly,https://www.googleapis.com/auth/keep,https://www.googleapis.com/auth/youtube,https://www.googleapis.com/auth/youtube.upload,https://www.googleapis.com/auth/youtube.force-ssl,https://www.googleapis.com/auth/admin.directory.user,https://www.googleapis.com/auth/admin.directory.group,https://www.googleapis.com/auth/admin.directory.orgunit,https://www.googleapis.com/auth/admin.directory.resource.calendar,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/analytics,https://www.googleapis.com/auth/analytics.edit,https://www.googleapis.com/auth/analytics.manage.users,https://www.googleapis.com/auth/analytics.provision,https://www.googleapis.com/auth/adwords,https://www.googleapis.com/auth/tagmanager.edit.containers,https://www.googleapis.com/auth/tagmanager.edit.containerversions,https://www.googleapis.com/auth/tagmanager.manage.accounts,https://www.googleapis.com/auth/tagmanager.manage.users,https://www.googleapis.com/auth/tagmanager.publish,https://www.googleapis.com/auth/tagmanager.delete.containers,https://www.googleapis.com/auth/datastudio,https://www.googleapis.com/auth/webmasters,https://www.googleapis.com/auth/webmasters.readonly,https://www.googleapis.com/auth/business.manage,https://www.googleapis.com/auth/content,https://www.googleapis.com/auth/yt-analytics.readonly,https://www.googleapis.com/auth/yt-analytics-monetary.readonly,https://www.googleapis.com/auth/youtubepartner,https://www.googleapis.com/auth/youtubepartner-channel-audit,https://www.googleapis.com/auth/display-video,https://www.googleapis.com/auth/display-video-mediaplanning,https://www.googleapis.com/auth/doubleclicksearch,https://www.googleapis.com/auth/bigquery,https://www.googleapis.com/auth/bigquery.insertdata,https://www.googleapis.com/auth/admin.reports.audit.readonly,https://www.googleapis.com/auth/admin.reports.usage.readonly,https://www.googleapis.com/auth/indexing,https://www.googleapis.com/auth/devstorage.full_control,https://www.googleapis.com/auth/pubsub,https://www.googleapis.com/auth/youtube.readonly,https://www.googleapis.com/auth/youtube.channel-memberships.creator,https://www.googleapis.com/auth/youtube.third-party-link.creator,https://www.googleapis.com/auth/analytics.readonly,https://www.googleapis.com/auth/analytics.user.deletion,https://www.googleapis.com/auth/tagmanager.readonly,https://www.googleapis.com/auth/dfatrafficking,https://www.googleapis.com/auth/dfareporting,https://www.googleapis.com/auth/ddmconversions,https://www.googleapis.com/auth/firebase,https://www.googleapis.com/auth/firebase.readonly,https://www.googleapis.com/auth/androidpublisher,https://www.googleapis.com/auth/apps.alerts,https://www.googleapis.com/auth/adwords.readonly
```

Important formatting rules:
- Single line only
- Commas between scopes, no spaces
- No line breaks
- No trailing spaces

---

## Organization Policy Fixes

For Google Cloud organizations created after May 2024, service account creation is blocked by default.

### Grant Required Roles

1. Go to https://console.cloud.google.com/iam-admin/iam
2. Switch from project to ORGANIZATION in the dropdown
3. Find your user account
4. Click Edit (pencil icon)
5. Add roles:
   - Organization Administrator
   - Organization Policy Administrator
6. Save and wait 1-2 minutes

### Disable Blocking Policies

1. Go to https://console.cloud.google.com/iam-admin/orgpolicies
2. Make sure ORGANIZATION is selected
3. Filter for: iam.disableServiceAccountCreation
4. Click "Manage Policy"
5. Select "Override parent's policy"
6. Set Enforcement to "Not enforced"
7. Click "Set Policy"
8. Repeat for: iam.disableServiceAccountKeyCreation

---

## Google Chat Configuration

After enabling the Chat API, you must configure a Chat app.

1. Go to https://console.cloud.google.com/apis/library/chat.googleapis.com
2. Enable the API if not already enabled
3. Click "Configuration" tab
4. Enter app name: "AI Workspace Agent"
5. Enter description
6. Click Save

This step is required even if you do not plan to build a Chat bot.

---

## Verification Tests

### Gmail
```bash
gws gmail +triage
```
Expected: List of unread emails or "No unread messages"

### Calendar
```bash
gws calendar +agenda
```
Expected: Today's events or "No events today"

### Drive
```bash
gws drive files list --params '{"pageSize": 5}'
```
Expected: List of Drive files

### Sheets
```bash
gws sheets spreadsheets create --json '{"properties": {"title": "Test Sheet"}}'
```
Expected: Spreadsheet ID in response

### Docs
```bash
gws docs +write --help
```
Expected: Help text for the write helper

### Tasks
```bash
gws tasks tasklists list
```
Expected: List of task lists or empty state

---

## All 81 OAuth Scopes Explained

### Gmail Scopes (10)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://mail.google.com/ | Full | Complete Gmail access |
| https://www.googleapis.com/auth/gmail.modify | Modify | Read, send, trash, label |
| https://www.googleapis.com/auth/gmail.send | Send | Send emails only |
| https://www.googleapis.com/auth/gmail.labels | Labels | Manage labels |
| https://www.googleapis.com/auth/gmail.settings.basic | Settings | Basic settings |

### Calendar Scopes (1)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/calendar | Full | Full calendar access |

### Drive Scopes (1)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/drive | Full | Full Drive access |

### Docs, Sheets, Slides Scopes (3)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/documents | Full | Google Docs |
| https://www.googleapis.com/auth/spreadsheets | Full | Google Sheets |
| https://www.googleapis.com/auth/presentations | Full | Google Slides |

### Tasks Scopes (1)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/tasks | Full | Task management |

### Contacts Scopes (2)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/contacts | Full | Contact management |
| https://www.googleapis.com/auth/directory.readonly | Read | Directory lookup |

### YouTube Scopes (7)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/youtube | Full | YouTube management |
| https://www.googleapis.com/auth/youtube.upload | Upload | Video uploads |
| https://www.googleapis.com/auth/youtube.force-ssl | SSL | SSL-enforced access |
| https://www.googleapis.com/auth/youtube.readonly | Read | Read-only access |
| https://www.googleapis.com/auth/youtube.channel-memberships.creator | Memberships | Channel memberships |
| https://www.googleapis.com/auth/youtube.third-party-link.creator | Links | Third-party links |

### Chat Scopes (3)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/chat.messages | Messages | Send/receive messages |
| https://www.googleapis.com/auth/chat.spaces | Spaces | Manage spaces |
| https://www.googleapis.com/auth/chat.memberships | Memberships | Manage members |

### Forms Scopes (2)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/forms.body | Full | Form structure |
| https://www.googleapis.com/auth/forms.responses.readonly | Read | Form responses |

### Keep Scopes (1)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/keep | Full | Notes management |

### Admin SDK Scopes (6)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/admin.directory.user | Full | User management |
| https://www.googleapis.com/auth/admin.directory.group | Full | Group management |
| https://www.googleapis.com/auth/admin.directory.orgunit | Full | Org units |
| https://www.googleapis.com/auth/admin.directory.resource.calendar | Full | Resource calendars |
| https://www.googleapis.com/auth/admin.reports.audit.readonly | Read | Audit reports |
| https://www.googleapis.com/auth/admin.reports.usage.readonly | Read | Usage reports |

### Analytics Scopes (6)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/analytics | Full | Analytics management |
| https://www.googleapis.com/auth/analytics.edit | Edit | Edit properties |
| https://www.googleapis.com/auth/analytics.manage.users | Users | User management |
| https://www.googleapis.com/auth/analytics.provision | Provision | Create accounts |
| https://www.googleapis.com/auth/analytics.readonly | Read | Read-only reports |
| https://www.googleapis.com/auth/analytics.user.deletion | Delete | User data deletion |

### Tag Manager Scopes (7)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/tagmanager.edit.containers | Edit | Edit containers |
| https://www.googleapis.com/auth/tagmanager.edit.containerversions | Versions | Container versions |
| https://www.googleapis.com/auth/tagmanager.manage.accounts | Accounts | Account management |
| https://www.googleapis.com/auth/tagmanager.manage.users | Users | User management |
| https://www.googleapis.com/auth/tagmanager.publish | Publish | Publish containers |
| https://www.googleapis.com/auth/tagmanager.delete.containers | Delete | Delete containers |
| https://www.googleapis.com/auth/tagmanager.readonly | Read | Read-only access |

### Ads and Marketing Scopes (7)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/adwords | Full | Google Ads |
| https://www.googleapis.com/auth/adwords.readonly | Read | Read-only Ads |
| https://www.googleapis.com/auth/display-video | Full | Display & Video 360 |
| https://www.googleapis.com/auth/display-video-mediaplanning | Planning | Media planning |
| https://www.googleapis.com/auth/doubleclicksearch | Full | Search Ads 360 |
| https://www.googleapis.com/auth/dfatrafficking | Trafficking | DCM trafficking |
| https://www.googleapis.com/auth/dfareporting | Reporting | DCM reporting |

### Search and Business Scopes (4)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/webmasters | Full | Search Console |
| https://www.googleapis.com/auth/webmasters.readonly | Read | Read-only Search Console |
| https://www.googleapis.com/auth/business.manage | Full | Business Profile |
| https://www.googleapis.com/auth/indexing | Full | Indexing API |

### Cloud and Storage Scopes (5)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/cloud-platform | Full | All Cloud APIs |
| https://www.googleapis.com/auth/bigquery | Full | BigQuery |
| https://www.googleapis.com/auth/bigquery.insertdata | Insert | BigQuery data insert |
| https://www.googleapis.com/auth/devstorage.full_control | Full | Cloud Storage |
| https://www.googleapis.com/auth/pubsub | Full | Pub/Sub |

### YouTube Analytics Scopes (2)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/yt-analytics.readonly | Read | YouTube Analytics |
| https://www.googleapis.com/auth/yt-analytics-monetary.readonly | Read | Monetization data |

### Partner and Content Scopes (3)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/youtubepartner | Full | YouTube Partner |
| https://www.googleapis.com/auth/youtubepartner-channel-audit | Audit | Channel audit |
| https://www.googleapis.com/auth/content | Full | Content API for Shopping |

### Other Scopes (6)

| Scope | Access | Purpose |
|-------|--------|---------|
| https://www.googleapis.com/auth/datastudio | Full | Looker Studio |
| https://www.googleapis.com/auth/ddmconversions | Full | DDM conversions |
| https://www.googleapis.com/auth/firebase | Full | Firebase |
| https://www.googleapis.com/auth/firebase.readonly | Read | Read-only Firebase |
| https://www.googleapis.com/auth/androidpublisher | Full | Google Play |
| https://www.googleapis.com/auth/apps.alerts | Full | Workspace alerts |

---

## Service Reference

### Gmail

List unread messages:
```bash
gws gmail messages list --params '{"q": "is:unread"}'
```

Send message:
```bash
gws gmail messages send --json '{
  "to": "recipient@example.com",
  "subject": "Hello",
  "body": "Message text"
}'
```

### Calendar

List events:
```bash
gws calendar events list
```

Create event:
```bash
gws calendar events create --json '{
  "summary": "Meeting",
  "start": {"dateTime": "2026-03-20T10:00:00"},
  "end": {"dateTime": "2026-03-20T11:00:00"}
}'
```

### Drive

List files:
```bash
gws drive files list --params '{"pageSize": 10}'
```

Upload file:
```bash
gws drive files upload --file /path/to/file.pdf
```

### Sheets

Create spreadsheet:
```bash
gws sheets spreadsheets create --json '{"properties": {"title": "My Sheet"}}'
```

Read values:
```bash
gws sheets spreadsheets values get --spreadsheetId ID --range "Sheet1!A1:D10"
```

### Docs

Create document:
```bash
gws docs documents create --json '{"title": "My Doc"}'
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| 401 Unauthorized | Token expired. Run gws auth login to refresh. |
| 403 Forbidden | Scope not authorized. Check Domain-Wide Delegation. |
| 404 Not Found | Resource does not exist. Check ID. |
| 429 Too Many Requests | Rate limited. Wait and retry. |
| Command not found | gws not installed or not in PATH. Reinstall. |
| Propagation delay | Wait 15 minutes to 24 hours after scope changes. |

---

## Core File Updates

After installation, update these files:

### AGENTS.md
```
## Google Workspace Integration [PRIORITY: CRITICAL]

Google Workspace access uses the gws CLI. One tool for both Gmail and Workspace accounts.
No more google-api.js or gog.

- Gmail accounts: Use gws auth login with OAuth
- Workspace accounts: Use gws auth setup with gcloud or service account
- Domain-Wide Delegation required for Workspace
- Token refresh: gws auth login
- Full guide: ~/Downloads/openclaw-master-files/OpenClaw Onboarding/14-google-workspace-integration/google-workspace-integration-full.md
```

### TOOLS.md
```
## Google Workspace Integration [PRIORITY: CRITICAL]

Tool: Google Workspace CLI (gws)
Install: npm install -g @googleworkspace/cli

Auth:
- Gmail: gws auth login -s gmail,calendar,drive,contacts,docs,sheets,tasks,keep,forms,youtube
- Workspace: gws auth setup (with gcloud) or GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE

Common commands:
- gws gmail +triage
- gws calendar +agenda
- gws drive files list --params '{"pageSize": 5}'
- gws sheets spreadsheets create
- gws docs +write

Full guide: ~/Downloads/openclaw-master-files/OpenClaw Onboarding/14-google-workspace-integration/google-workspace-integration-full.md
```

### MEMORY.md
```
## Google Workspace Integration

Google Workspace CLI (gws) installed [DATE]. Handles Gmail, Calendar, Drive, Docs, Sheets, Chat, Tasks, Keep, Forms, YouTube.

Replaces: google-api.js and gog CLI
Authentication: OAuth for Gmail, service account for Workspace
Scopes: 81 scopes configured

Full guide: ~/Downloads/openclaw-master-files/OpenClaw Onboarding/14-google-workspace-integration/google-workspace-integration-full.md
```
