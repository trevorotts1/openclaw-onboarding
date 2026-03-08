
╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TYP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TYP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TYP"
- Look in your session context for prior TYP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TYP:
Proceed to the instructions below. Follow the TYP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TYP:
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TYP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TYP, I will bloat your core .md files and waste your tokens."

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

CONFLICT RULE (applies to all skill installs):
If this skill's SKILL.md, CORE_UPDATES.md, or any other file in this skill
folder conflicts with TYP regarding WHICH core .md files to update or WHAT
content to add, always follow this skill's files. The skill takes precedence
over TYP on core file update decisions. TYP governs the storage method (lean
summaries + file paths). The skill governs the content and which files it
touches. When in doubt: skill docs win.


══════════════════════════════════════════════════════════════════
  TYP FILE STORAGE INSTRUCTIONS (only read this if TYP confirmed)
══════════════════════════════════════════════════════════════════

WHEN LEARNING THIS DOCUMENT, FOLLOW THIS STRUCTURE:

1. SAVE FULL DOCUMENTATION TO MASTER FILES FOLDER
   Find the OpenClaw master files folder in ~/Downloads/. It may be named:
   - OpenClaw Master Files
   - OpenClaw Master Documents
   - OpenClaw Documents
   - openclaw-master-files
   - openclaw master files
   - OpenClaw Files
   - openclaw-documents
   - Any variation of "openclaw" + "master" or "files" or "documents"
   Search case-insensitively. One word or two words. Plural or singular.
   If no folder is found, create: ~/Downloads/OpenClaw Master Files/

   Save this full document content as a .md file in that folder.

2. DO NOT DUMP FULL CONTENT INTO CORE .MD FILES
   AGENTS.md, TOOLS.md, and MEMORY.md must stay lean.
   Only add a brief summary and a file path reference to where the full
   documentation lives. Never paste thousands of lines into core files.

3. USE THE LABELED SECTIONS BELOW TO KNOW WHAT GOES WHERE
   Look for sections marked:
   [ADD TO AGENTS.md]
   [ADD TO TOOLS.md]
   [ADD TO MEMORY.md]
   Only add what is labeled. Nothing else goes into core files.

EXECUTION DISCIPLINE - MANDATORY BEFORE YOU START
╚══════════════════════════════════════════════════════════════╝

These rules apply every single time you execute instructions from this document.
No exceptions. No shortcuts. No improvising.

RULE 1: READ EVERYTHING BEFORE YOU TOUCH ANYTHING
Read this entire document from top to bottom before executing a single step.
Do not start executing while still reading. Finish reading first. Then start.

RULE 2: DO NOT CHANGE TREVOR'S INTENT
These instructions say exactly what to do. Execute them exactly as written.
- Do NOT reinterpret steps
- Do NOT "improve" the instructions
- Do NOT skip steps because they seem unnecessary
- Do NOT add steps that are not in the document
- Do NOT change the order of steps
If a step says do X, do X. Not Y. Not a better version of X. X.

RULE 3: NEVER MODIFY THESE WITHOUT PERMISSION
- API keys - copy them exactly, character for character
- Terminal commands - run them exactly as written, no edits
- Config values - use the exact values specified
- Model names - use the exact names specified, spelling matters
- File paths - use the exact paths specified
If you are unsure whether something should be changed, the answer is NO.
Ask Trevor first. Do not guess. Do not assume.

RULE 4: BUILD YOUR CHECKLIST BEFORE EXECUTING
Before you run a single command or make a single change, create a numbered
checklist of every action this document requires you to take. Write it out.
Show it to the user before starting. Get confirmation. Then execute.

RULE 5: CHECK YOURSELF AGAINST THE CHECKLIST WHEN DONE
When you believe you are finished, go back to your checklist.
Verify every single item was completed. Check it off explicitly.
If anything was missed, complete it before telling the user you are done.
Do NOT tell the user you are done until the checklist is 100% complete.

RULE 6: REPORT WHAT YOU DID
When finished, give the user a clear summary:
- What was completed
- What commands were run
- What files were changed
- Any errors encountered and how they were resolved
- Confirmation that the checklist was fully satisfied

══════════════════════════════════════════════════════════════════

# Google Workspace Integration - Installation Guide

This is the COMPLETE setup guide for connecting your AI agent to ALL Google Workspace services. If you completed the basic setup in Skill 12, this guide extends it to cover all 26 APIs, all 70+ scopes, Organization Policy fixes, the google-api.js script, and the GOG skill.

**Important:** This guide is for Google Workspace accounts ONLY (@yourdomain.com). If you have a personal @gmail.com account, use the GOG CLI with OAuth instead.

---

## Prerequisites

Before starting, make sure you have:

- Google Workspace account (a business email like you@yourdomain.com - NOT a personal @gmail.com)
- Google Workspace Super Admin access (needed for Domain-Wide Delegation)
- Node.js version 18 or higher installed on your computer (check with: node --version)
- A computer with terminal access (Mac Terminal, Windows PowerShell, or Linux shell)
- Skill 12 (Google Workspace Setup) completed, OR 30 minutes of uninterrupted time to do both
- 15-30 minutes for this guide

---

## The Big Picture: Two Places You Must Visit

Setting up Google Workspace access requires visiting two different websites. Understanding this up front prevents confusion.

### Place 1: Google Cloud Console (console.cloud.google.com)

This is the "construction site" where you build the robot (Service Account) and give it tools (APIs).

What you do here:
1. Create a Google Cloud Project
2. Enable all 26 APIs
3. Configure the OAuth Consent Screen
4. Create the Service Account
5. Download the JSON key file
6. Copy the Client ID number

### Place 2: Google Workspace Admin Console (admin.google.com)

This is the "security desk" where you authorize the robot to act on your behalf.

What you do here:
1. Navigate to Security, then Access and data control, then API controls, then Manage Domain Wide Delegation
2. Add the Client ID from Place 1
3. Paste all the OAuth scopes
4. Click Authorize

Both places MUST be completed. If you only do Place 1, the robot exists but has no permission. If you only do Place 2, there is no robot to authorize.

---

## Section 1: Google Cloud Project Setup

If you already completed Skill 12, you have a project. Skip to Section 2.

1. Open your browser and go to: https://console.cloud.google.com/
2. Sign in with your Google Workspace Super Admin account
3. Click the project dropdown at the top left
4. Click "New Project" in the top right of the popup
5. Name it something like "OpenClaw AI Agent"
6. Click Create
7. Wait a few seconds, then select your new project from the dropdown
8. Write down the Project ID (it shows under the project name in the dropdown)

---

## Section 2: Enable All 26 APIs

Each Google service has its own API that must be turned on. For each link below, Click blue "Enable" button. If it says "Manage" instead, it is already enabled.

**Make sure your project is selected at the top of every page.**

### Core APIs (Required)

1. **Gmail API** - https://console.cloud.google.com/apis/library/gmail.googleapis.com
   - Lets your AI read, send, search, and manage email

2. **Google Calendar API** - https://console.cloud.google.com/apis/library/calendar-json.googleapis.com
   - Lets your AI read and create calendar events

3. **Google Drive API** - https://console.cloud.google.com/apis/library/drive.googleapis.com
   - Lets your AI find, upload, download, and organize files

4. **People API (Contacts)** - https://console.cloud.google.com/apis/library/people.googleapis.com
   - Lets your AI look up contacts by name, email, or phone

5. **Google Sheets API** - https://console.cloud.google.com/apis/library/sheets.googleapis.com
   - Lets your AI read and write spreadsheet data

6. **Google Docs API** - https://console.cloud.google.com/apis/library/docs.googleapis.com
   - Lets your AI read and edit documents

7. **Google Slides API** - https://console.cloud.google.com/apis/library/slides.googleapis.com
   - Lets your AI read and create presentations

8. **Google Tasks API** - https://console.cloud.google.com/apis/library/tasks.googleapis.com
   - Lets your AI manage to-do lists

9. **YouTube Data API v3** - https://console.cloud.google.com/apis/library/youtube.googleapis.com
   - Lets your AI access channel data and manage videos

10. **Google Chat API** - https://console.cloud.google.com/apis/library/chat.googleapis.com
    - Lets your AI read and send messages in Chat spaces

11. **Places API (New)** - https://console.cloud.google.com/apis/library/places-backend.googleapis.com
    - Lets your AI search for businesses and venues (uses API Key, not Service Account)

### Extended APIs (Recommended)

12. **Google Forms API** - https://console.cloud.google.com/apis/library/forms.googleapis.com
    - Create and manage forms, read responses

13. **Google Meet REST API** - https://console.cloud.google.com/apis/library/meet.googleapis.com
    - Access meeting info and recordings

14. **Google Keep API** - https://console.cloud.google.com/apis/library/keep.googleapis.com
    - Create and manage notes

15. **Admin SDK API** - https://console.cloud.google.com/apis/library/admin.googleapis.com
    - Manage users, groups, and org settings

16. **Contacts API (Legacy)** - https://console.cloud.google.com/apis/library/contacts.googleapis.com
    - Legacy contacts access for tool compatibility

17. **Blogger API** - https://console.cloud.google.com/apis/library/blogger.googleapis.com
    - Publish and manage blog content

18. **Google Vault API** - https://console.cloud.google.com/apis/library/vault.googleapis.com
    - Legal compliance, holds, and data exports

19. **Groups Settings API** - https://console.cloud.google.com/apis/library/groupssettings.googleapis.com
    - Manage Google Groups settings and permissions

20. **Google Analytics Admin API** - https://console.cloud.google.com/apis/library/analyticsadmin.googleapis.com
    - Manage GA4 properties and configuration

21. **Google Analytics Data API** - https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com
    - Pull GA4 reports and traffic data

22. **Google Tag Manager API** - https://console.cloud.google.com/apis/library/tagmanager.googleapis.com
    - Manage tags, triggers, and container publishing

23. **BigQuery API** - https://console.cloud.google.com/apis/library/bigquery.googleapis.com
    - Run SQL queries on large datasets

24. **Looker Studio API** - https://console.cloud.google.com/apis/library/datastudio.googleapis.com
    - Manage dashboards and data sources

25. **Google Ads API** - https://console.cloud.google.com/apis/library/googleads.googleapis.com
    - Manage ad campaigns and budgets (requires separate Developer Token from ads.google.com/aw/apicenter)

26. **Search Console API** - https://console.cloud.google.com/apis/library/searchconsole.googleapis.com
    - Track SEO performance and indexing status

**Note about Google Chat:** After enabling the Chat API, you also need to configure a Chat App. Go to the Chat API Configuration page, click the Configuration tab, fill in an app name and description, and save.

**Note about YouTube Analytics:** The YouTube Analytics API does NOT support service accounts. If you need YouTube analytics data, use the GOG CLI with OAuth.

---

## Section 3: Configure the OAuth Consent Screen

This step is CRITICAL. Without it, Google blocks sensitive scopes like Gmail. This is the number one reason people get stuck with "401 Unauthorized" errors.

1. Go to: https://console.cloud.google.com/apis/credentials/consent
2. If you see "Get Started", click it
3. Choose "Internal" as the User Type (this limits access to your organization only and does NOT require Google verification)
4. Click "Create"
5. Fill in:
   - App name: "AI Workspace Agent"
   - User support email: Select your email
   - Developer contact email: Enter your email
6. Click "Save and Continue"
7. On the Scopes page:
   - Click "Add or Remove Scopes"
   - Search for and check Gmail, Calendar, Drive scopes
   - For scopes that do not appear in the search, scroll to the bottom and paste them in the "Manually add scopes" box
   - Click "Update"
8. Click "Save and Continue" through remaining steps
9. Click "Back to Dashboard"

---

## Section 4: Create a Service Account

If you already created one in Skill 12, skip to Section 5.

1. Go to: https://console.cloud.google.com/iam-admin/serviceaccounts
2. Make sure your project is selected at the top
3. Click "+ CREATE SERVICE ACCOUNT"
4. Name: "ai-workspace-agent"
5. Description: "Service account for AI agent Google Workspace access"
6. Click "Create and Continue"
7. Skip optional roles - click "Continue"
8. Skip "Grant users access" - click "Done"

**If you get an error about service account creation being blocked,** see Section 5 (Fix Organization Policy Blocks) below.

### Create the JSON Key

1. Click on your service account's email address in the list
2. Click the "Keys" tab
3. Click "Add Key" then "Create new key"
4. Select "JSON"
5. Click "Create"
6. A .json file downloads to your computer

**If you get an error about key creation being disabled,** see Section 5 below.

### Note the Client ID

1. On your service account's detail page, find the "Unique ID" or "Client ID"
2. It is a long number like 115886301121225599053
3. Copy this number - you need it for Domain-Wide Delegation

**Important:** The Client ID is a NUMBER, not the email address. Using the email in Domain-Wide Delegation will silently fail.

---

## Section 5: Fix Organization Policy Blocks

If your Google Cloud organization was created after May 2024, Google may block service account creation and key downloads by default. This is not something you did wrong - it is a Google default.

If you did NOT encounter any errors in Section 4, skip this section.

### Grant Yourself the Required Roles

1. Go to: https://console.cloud.google.com/iam-admin/iam
2. In the resource selector dropdown at the top left, switch from your project to your ORGANIZATION (it matches your domain name)
3. Find your user account in the list
4. Click the pencil (Edit) icon
5. Click "+ ADD ANOTHER ROLE"
6. Search for and add: Organization Administrator
7. Click "+ ADD ANOTHER ROLE" again
8. Search for and add: Organization Policy Administrator
9. Click Save
10. Wait 1-2 minutes for the roles to take effect

### Disable the Blocking Policies

For service account creation being blocked:

1. Go to: https://console.cloud.google.com/iam-admin/orgpolicies
2. Make sure your ORGANIZATION is selected (not a project)
3. In the Filter field, type: iam.disableServiceAccountCreation
4. Click on "Disable service account creation"
5. Click "Manage Policy"
6. Select "Override parent's policy"
7. Set Enforcement to "Not enforced"
8. Click "Set Policy"

For key creation being blocked:

1. Same page, Filter for: iam.disableServiceAccountKeyCreation
2. Click on "Disable service account key creation"
3. Click "Manage Policy"
4. Select "Override parent's policy"
5. Set Enforcement to "Not enforced"
6. Click "Set Policy"

Now go back to Section 4 and create the service account and key. It will work now.

**Security tip:** After creating your key, you can optionally re-enable these policies to prevent anyone else from creating keys.

---

## Section 6: Domain-Wide Delegation

This is where you give the Service Account permission to act as you.

### Part A: Enable Delegation on the Service Account

1. Go to: https://console.cloud.google.com/iam-admin/serviceaccounts
2. Click on your service account email
3. Look for "Show Advanced Settings" or "Domain-Wide Delegation"
4. Check "Enable Google Workspace Domain-Wide Delegation"
5. Click Save

### Part B: Authorize in Admin Console

1. Go to: https://admin.google.com/ac/owl/domainwidedelegation
2. Sign in as Super Admin
3. Click "Add new"
4. Client ID: Paste the numeric ID from Section 4 (NOT the email address)
5. OAuth Scopes: Paste this entire block (all one line, comma-separated, no spaces):

```
https://mail.google.com/,https://www.googleapis.com/auth/documents,https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/presentations,https://www.googleapis.com/auth/calendar,https://www.googleapis.com/auth/gmail.modify,https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/gmail.labels,https://www.googleapis.com/auth/gmail.settings.basic,https://www.googleapis.com/auth/tasks,https://www.googleapis.com/auth/contacts,https://www.googleapis.com/auth/directory.readonly,https://www.googleapis.com/auth/chat.messages,https://www.googleapis.com/auth/chat.spaces,https://www.googleapis.com/auth/chat.memberships,https://www.googleapis.com/auth/forms.body,https://www.googleapis.com/auth/forms.responses.readonly,https://www.googleapis.com/auth/keep,https://www.googleapis.com/auth/youtube,https://www.googleapis.com/auth/youtube.upload,https://www.googleapis.com/auth/youtube.force-ssl,https://www.googleapis.com/auth/admin.directory.user,https://www.googleapis.com/auth/admin.directory.group,https://www.googleapis.com/auth/admin.directory.orgunit,https://www.googleapis.com/auth/admin.directory.resource.calendar,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/analytics,https://www.googleapis.com/auth/analytics.edit,https://www.googleapis.com/auth/analytics.manage.users,https://www.googleapis.com/auth/analytics.provision,https://www.googleapis.com/auth/adwords,https://www.googleapis.com/auth/tagmanager.edit.containers,https://www.googleapis.com/auth/tagmanager.edit.containerversions,https://www.googleapis.com/auth/tagmanager.manage.accounts,https://www.googleapis.com/auth/tagmanager.manage.users,https://www.googleapis.com/auth/tagmanager.publish,https://www.googleapis.com/auth/tagmanager.delete.containers,https://www.googleapis.com/auth/datastudio,https://www.googleapis.com/auth/webmasters,https://www.googleapis.com/auth/webmasters.readonly,https://www.googleapis.com/auth/business.manage,https://www.googleapis.com/auth/content,https://www.googleapis.com/auth/yt-analytics.readonly,https://www.googleapis.com/auth/yt-analytics-monetary.readonly,https://www.googleapis.com/auth/youtubepartner,https://www.googleapis.com/auth/youtubepartner-channel-audit,https://www.googleapis.com/auth/display-video,https://www.googleapis.com/auth/display-video-mediaplanning,https://www.googleapis.com/auth/doubleclicksearch,https://www.googleapis.com/auth/bigquery,https://www.googleapis.com/auth/bigquery.insertdata,https://www.googleapis.com/auth/admin.reports.audit.readonly,https://www.googleapis.com/auth/admin.reports.usage.readonly,https://www.googleapis.com/auth/indexing,https://www.googleapis.com/auth/devstorage.full_control,https://www.googleapis.com/auth/pubsub,https://www.googleapis.com/auth/youtube.readonly,https://www.googleapis.com/auth/youtube.channel-memberships.creator,https://www.googleapis.com/auth/youtube.third-party-link.creator,https://www.googleapis.com/auth/analytics.readonly,https://www.googleapis.com/auth/analytics.user.deletion,https://www.googleapis.com/auth/tagmanager.readonly,https://www.googleapis.com/auth/dfatrafficking,https://www.googleapis.com/auth/dfareporting,https://www.googleapis.com/auth/ddmconversions,https://www.googleapis.com/auth/firebase,https://www.googleapis.com/auth/firebase.readonly,https://www.googleapis.com/auth/androidpublisher,https://www.googleapis.com/auth/apps.alerts,https://www.googleapis.com/auth/adwords.readonly
```

6. Click "Authorize"

**Important notes:**
- The scopes must be pasted as a single line with commas between them. No spaces after commas. No line breaks.
- If you EVER add new scopes later, you must re-paste the ENTIRE list and click Authorize again. Google does not let you add one at a time.
- Propagation can take 5 minutes to 24 hours. Gmail scopes are especially slow. If something does not work right away, wait 15 minutes and try again.

---

## Section 7: Script Installation

### Place the google-api.js Script

Save the google-api.js file to your OpenClaw workspace directory. The script has zero external dependencies - it uses only Node.js built-in modules. No npm install needed.

### Set Environment Variables

Add these to your shell profile (~/.zshrc on Mac, ~/.bashrc on Linux):

```bash
# Required: Path to your Service Account JSON key file
export GOOGLE_SA_KEY_FILE="/path/to/your-service-account-key.json"

# Required: The email address to impersonate (must be in your Workspace domain)
export GOOGLE_IMPERSONATE_USER="you@yourdomain.com"

# Optional: Only needed for Places API
export GOOGLE_PLACES_API_KEY="your-places-api-key-here"
```

Reload your shell:

```bash
source ~/.zshrc
```

### Create a Places API Key (Optional)

Only needed if you want the Places API (searching for businesses and venues):

1. Go to: https://console.cloud.google.com/apis/credentials
2. Click "Create Credentials" then "API Key"
3. Click "Restrict Key"
4. Under "API restrictions", select "Restrict key" and check "Places API (New)"
5. Click Save
6. Copy the key and set it as GOOGLE_PLACES_API_KEY

### Verify Setup

```bash
node --version          # Must be 18+
node google-api.js help # Should show available commands
echo $GOOGLE_SA_KEY_FILE     # Should show your key file path
echo $GOOGLE_IMPERSONATE_USER # Should show your Workspace email
```

---

## Section 8: Install and Configure the GOG Skill

GOG is the bridge between your Service Account and OpenClaw actually using Google services. Without GOG, your agent has keys but cannot open doors.

### Step 1: Verify Environment Variables

```bash
echo $GOOGLE_SA_KEY_FILE
echo $GOOGLE_IMPERSONATE_USER
```

Both should show values. If either is blank, go back to Section 7.

### Step 2: Install GOG

```bash
openclaw skills install gog
```

Or through the OpenClaw dashboard: navigate to Skills and install "gog".

### Step 3: Restart OpenClaw

```bash
openclaw gateway restart
```

Wait 10 seconds:

```bash
openclaw gateway status
```

Should show "running".

### Step 4: Quick Verification

Ask your AI: "Can you check my Gmail inbox for the 3 most recent emails?"

If it returns email subjects and senders, GOG is working.

---

## Section 9: Update Workspace Files (Critical)

After completing setup, you MUST update your workspace files so the AI remembers how to use the correct tool for each account type. If you skip this, the AI will use the wrong method and get 401 errors.

Add the blocks from Section 14 of the full documentation (google-workspace-integration-full.md) to each of these files:
- MEMORY.md (what to do)
- TOOLS.md (how to do it)
- AGENTS.md (rules and self-correction)
- USER.md (which accounts use which method)
- IDENTITY.md (why - so it remembers the lesson)
- HEARTBEAT.md (daily routing for each account)

The key rule to add everywhere: Workspace accounts (@yourdomain.com) use google-api.js. Personal accounts (@gmail.com) use GOG CLI. These are incompatible methods. Mixing them always fails.

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| "401 Unauthorized" or "Invalid grant" | Auth rejected | Check: key file valid? GOOGLE_IMPERSONATE_USER set? DWD authorized? OAuth Consent Screen configured? Used Client ID (not email) in DWD? |
| "403 Forbidden" | Scope not granted | Re-paste all scopes in Admin Console DWD. Delete and re-add the entry with clean copy. |
| "API not enabled" | API switch not flipped | Go to APIs & Services dashboard, find the missing API, enable it |
| "Service account key creation is disabled" | Organization policy | See Section 5 above |
| Gmail fails but other services work | OAuth Consent Screen missing or Gmail scopes not propagated | Configure OAuth Consent Screen (Section 3). Wait 15-30 min for propagation. |
| "GOOGLE_SA_KEY_FILE not set" | Environment variable missing | Add to ~/.zshrc, run source ~/.zshrc |
| Places returns "API key not valid" | Wrong key type | Places uses API Key (Section 7), not Service Account |
| Chat returns "404 - Chat app not found" | Chat App not configured | See the Google Chat note in Section 2 |
| Browser session expired (Playwright) | Google session expires every 7-14 days | Agent pauses, asks you to re-login. Normal behavior. |
