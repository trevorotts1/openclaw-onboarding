╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.

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
anything in this document. Stop and report to the user:

  "Teach Yourself Protocol (TYP) is not installed yet. This skill cannot
   be safely installed without TYP. Navigate to 01-teach-yourself-protocol/
   in the onboarding package and complete that installation first.
   Without TYP, core .md files will be bloated and tokens wasted."

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

CONFLICT RULE (applies to all skill installs):
If THIS skill file says one thing, and TYP says another, TYP wins.
Skill docs override generic instructions. TYP overrides skill docs.
User's explicit override is highest priority. Chain:
  User Override > TYP > Skill Docs > Generic Instructions
╚══════════════════════════════════════════════════════════════╝

---

# Google Workspace Integration - Installation Guide

This guide sets up the Google Workspace CLI (gws) for accessing all Google services. It covers both personal Gmail accounts and Google Workspace business accounts.

---

## Prerequisites

Before starting, make sure you have:

1. Node.js version 18 or higher installed
2. npm (comes with Node.js)
3. A Google account (Gmail or Workspace)
4. For Workspace accounts: Google Workspace Super Admin access
5. 20-30 minutes of uninterrupted time

Check your Node.js version:
```bash
node --version
```

If you see v18.x.x or higher, you are ready. If not, download Node.js from nodejs.org first.

---

## Section 1: Install the Google Workspace CLI

The Google Workspace CLI (gws) is a single tool that replaces both the old google-api.js script and the GOG CLI.

Step 1. Open your terminal application (Terminal on Mac, PowerShell on Windows).

Step 2. Run this command to install gws globally:
```bash
npm install -g @googleworkspace/cli
```

Step 3. Wait for the installation to complete. You will see progress messages.

Step 4. Verify the installation worked:
```bash
gws --version
```

You should see a version number like 1.0.0 or higher. If you see "command not found", close your terminal and open a new one, then try again.

---

## Section 2: Authentication for Gmail Users

If you have a personal Gmail account (ending in @gmail.com), follow these steps.

Step 1. Set up gws authentication:
```bash
gws auth setup
```

This opens a browser window asking you to sign in to your Google account.

Step 2. Sign in with your Gmail address.

Step 3. When asked for permissions, click "Allow" to grant access.

Step 4. Run the login command with all the services you want to use:
```bash
gws auth login -s gmail,calendar,drive,contacts,docs,sheets,tasks,keep,forms,youtube
```

Step 5. The browser opens again. Click "Allow" for each service requested.

Step 6. Return to your terminal. You should see a success message.

Step 7. Verify authentication worked:
```bash
gws auth list
```

You should see your Gmail address listed with the scopes you authorized.

---

## Section 3: Authentication for Workspace Users

If you have a Google Workspace account (like you@yourcompany.com), you have two options.

### Option A: Using gcloud (Recommended for Most Users)

Step 1. Make sure you have gcloud installed:
```bash
gcloud --version
```

If not installed, download it from cloud.google.com/sdk.

Step 2. Authenticate gcloud with your Workspace account:
```bash
gcloud auth application-default login
```

Step 3. Set up gws:
```bash
gws auth setup
```

Step 4. Follow the prompts to complete authentication.

### Option B: Using a Service Account JSON Key

Step 1. Obtain your service account JSON key file from your Google Cloud Console.

Step 2. Save the JSON file to a secure location like:
```
~/clawd/secrets/gcp-service-account.json
```

Step 3. Set the environment variable to point to your key file:
```bash
export GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=/path/to/your-service-account.json
```

Step 4. To make this permanent, add it to your shell profile:
```bash
echo 'export GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=/path/to/your-service-account.json' >> ~/.zshrc
```

Step 5. Reload your shell:
```bash
source ~/.zshrc
```

---

## Section 4: Domain-Wide Delegation (Workspace Only)

Domain-Wide Delegation allows a service account to act on behalf of users in your Workspace domain. This step is required for Workspace accounts.

### Part A: Find Your Service Account Client ID

Step 1. Go to Google Cloud Console: https://console.cloud.google.com/

Step 2. Navigate to IAM & Admin, then Service Accounts.

Step 3. Click on your service account email address.

Step 4. Look for the "Unique ID" or "Client ID". It is a long number like 115886301121225599053.

Step 5. Copy this number. You will need it in Part B.

Important: The Client ID is a NUMBER, not the email address. Using the email will fail silently.

### Part B: Authorize in Google Admin Console

Step 1. Go to Google Admin Console: https://admin.google.com/ac/owl/domainwidedelegation

Step 2. Sign in as a Super Admin.

Step 3. Click "Add new".

Step 4. In the Client ID field, paste the numeric ID from Part A.

Step 5. In the OAuth Scopes field, paste this entire scope list (all on one line, comma-separated, no spaces):

```
https://mail.google.com/,https://www.googleapis.com/auth/documents,https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/presentations,https://www.googleapis.com/auth/calendar,https://www.googleapis.com/auth/gmail.modify,https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/gmail.labels,https://www.googleapis.com/auth/gmail.settings.basic,https://www.googleapis.com/auth/tasks,https://www.googleapis.com/auth/contacts,https://www.googleapis.com/auth/directory.readonly,https://www.googleapis.com/auth/chat.messages,https://www.googleapis.com/auth/chat.spaces,https://www.googleapis.com/auth/chat.memberships,https://www.googleapis.com/auth/forms.body,https://www.googleapis.com/auth/forms.responses.readonly,https://www.googleapis.com/auth/keep,https://www.googleapis.com/auth/youtube,https://www.googleapis.com/auth/youtube.upload,https://www.googleapis.com/auth/youtube.force-ssl,https://www.googleapis.com/auth/admin.directory.user,https://www.googleapis.com/auth/admin.directory.group,https://www.googleapis.com/auth/admin.directory.orgunit,https://www.googleapis.com/auth/admin.directory.resource.calendar,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/analytics,https://www.googleapis.com/auth/analytics.edit,https://www.googleapis.com/auth/analytics.manage.users,https://www.googleapis.com/auth/analytics.provision,https://www.googleapis.com/auth/adwords,https://www.googleapis.com/auth/tagmanager.edit.containers,https://www.googleapis.com/auth/tagmanager.edit.containerversions,https://www.googleapis.com/auth/tagmanager.manage.accounts,https://www.googleapis.com/auth/tagmanager.manage.users,https://www.googleapis.com/auth/tagmanager.publish,https://www.googleapis.com/auth/tagmanager.delete.containers,https://www.googleapis.com/auth/datastudio,https://www.googleapis.com/auth/webmasters,https://www.googleapis.com/auth/webmasters.readonly,https://www.googleapis.com/auth/business.manage,https://www.googleapis.com/auth/content,https://www.googleapis.com/auth/yt-analytics.readonly,https://www.googleapis.com/auth/yt-analytics-monetary.readonly,https://www.googleapis.com/auth/youtubepartner,https://www.googleapis.com/auth/youtubepartner-channel-audit,https://www.googleapis.com/auth/display-video,https://www.googleapis.com/auth/display-video-mediaplanning,https://www.googleapis.com/auth/doubleclicksearch,https://www.googleapis.com/auth/bigquery,https://www.googleapis.com/auth/bigquery.insertdata,https://www.googleapis.com/auth/admin.reports.audit.readonly,https://www.googleapis.com/auth/admin.reports.usage.readonly,https://www.googleapis.com/auth/indexing,https://www.googleapis.com/auth/devstorage.full_control,https://www.googleapis.com/auth/pubsub,https://www.googleapis.com/auth/youtube.readonly,https://www.googleapis.com/auth/youtube.channel-memberships.creator,https://www.googleapis.com/auth/youtube.third-party-link.creator,https://www.googleapis.com/auth/analytics.readonly,https://www.googleapis.com/auth/analytics.user.deletion,https://www.googleapis.com/auth/tagmanager.readonly,https://www.googleapis.com/auth/dfatrafficking,https://www.googleapis.com/auth/dfareporting,https://www.googleapis.com/auth/ddmconversions,https://www.googleapis.com/auth/firebase,https://www.googleapis.com/auth/firebase.readonly,https://www.googleapis.com/auth/androidpublisher,https://www.googleapis.com/auth/apps.alerts,https://www.googleapis.com/auth/adwords.readonly
```

Step 6. Click "Authorize".

Important notes:
- The scopes must be pasted as a single line with commas between them
- No spaces after commas
- No line breaks
- If you add new scopes later, you must re-paste the ENTIRE list and click Authorize again
- Changes can take 5 minutes to 24 hours to fully propagate

---

## Section 5: Fix Organization Policy Blocks

If your Google Cloud organization was created after May 2024, Google blocks service account creation by default. This is not your fault. It is a Google security default.

If you did not encounter any errors in previous sections, skip this section.

### Grant Yourself Required Roles

Step 1. Go to https://console.cloud.google.com/iam-admin/iam

Step 2. In the dropdown at the top left, switch from your project to your ORGANIZATION.

Step 3. Find your user account in the list.

Step 4. Click the pencil (Edit) icon.

Step 5. Click "+ ADD ANOTHER ROLE".

Step 6. Search for and add: Organization Administrator

Step 7. Click "+ ADD ANOTHER ROLE" again.

Step 8. Search for and add: Organization Policy Administrator

Step 9. Click Save.

Step 10. Wait 1-2 minutes for the roles to take effect.

### Disable Blocking Policies

Step 1. Go to https://console.cloud.google.com/iam-admin/orgpolicies

Step 2. Make sure your ORGANIZATION is selected.

Step 3. In the Filter field, type: iam.disableServiceAccountCreation

Step 4. Click on "Disable service account creation".

Step 5. Click "Manage Policy".

Step 6. Select "Override parent's policy".

Step 7. Set Enforcement to "Not enforced".

Step 8. Click "Set Policy".

Step 9. For key creation, filter for: iam.disableServiceAccountKeyCreation

Step 10. Repeat steps 4-8 for this policy.

Now return to Section 3 and create your service account. It will work now.

---

## Section 6: Google Chat App Configuration

Google Chat requires an additional manual step after enabling the API.

Step 1. Go to https://console.cloud.google.com/apis/library/chat.googleapis.com

Step 2. Make sure the Chat API is enabled.

Step 3. Go to the Chat API Configuration page.

Step 4. Click the Configuration tab.

Step 5. Fill in an app name (like "AI Workspace Agent").

Step 6. Fill in a description.

Step 7. Click Save.

This step is required even if you do not plan to build a Chat bot. The API will not work without it.

---

## Section 7: Verify All Services Work

Run these test commands to confirm everything is set up correctly.

### Test Gmail
```bash
gws gmail +triage
```

You should see a list of unread emails or a message saying no emails found.

### Test Calendar
```bash
gws calendar +agenda
```

You should see today's calendar events or a message saying no events today.

### Test Drive
```bash
gws drive files list --params '{"pageSize": 5}'
```

You should see a list of your Drive files.

### Test Sheets
```bash
gws sheets spreadsheets create --json '{"properties": {"title": "Test Sheet"}}'
```

You should see a response with a spreadsheet ID, confirming a new sheet was created.

### Test Docs
```bash
gws docs +write
```

This is an interactive helper. Follow the prompts to create a test document.

### Test Tasks
```bash
gws tasks tasklists list
```

You should see your task lists or a message saying no task lists found.

If any test fails with a 401 or 403 error, check:
1. Did you complete Domain-Wide Delegation (for Workspace)?
2. Did you authorize all scopes in the Admin Console?
3. Have you waited at least 15 minutes for changes to propagate?

---

## Section 8: Install OpenClaw Agent Skills

The gws CLI includes OpenClaw skill files that make it easier to use.

Step 1. Find where gws is installed:
```bash
which gws
```

Step 2. Navigate to the gws installation directory and find the skills folder.

Step 3. Copy or link the skills to your OpenClaw skills directory:
```bash
# Option A: Create symbolic links
ln -s /path/to/gws/skills/* ~/.openclaw/skills/

# Option B: Copy the files
cp -r /path/to/gws/skills/* ~/.openclaw/skills/
```

Step 4. Restart OpenClaw to load the new skills:
```bash
openclaw gateway restart
```

Wait 10 seconds, then check status:
```bash
openclaw gateway status
```

---

## Section 9: Core File Updates

After completing setup, you MUST update your workspace files so the AI remembers how to use Google services.

Add the blocks from CORE_UPDATES.md to each of these files:
- AGENTS.md
- TOOLS.md
- MEMORY.md

This prevents the AI from forgetting the correct commands in future sessions.

---

## Completion Checklist

Use this checklist to confirm installation is complete:

- [ ] Node.js 18+ installed and verified
- [ ] gws CLI installed (gws --version shows a number)
- [ ] For Gmail: gws auth login completed successfully
- [ ] For Workspace: service account configured or gcloud auth completed
- [ ] Domain-Wide Delegation authorized (Workspace only)
- [ ] All 81 OAuth scopes pasted into Admin Console (Workspace only)
- [ ] Google Chat app configured
- [ ] Gmail test passed (gws gmail +triage)
- [ ] Calendar test passed (gws calendar +agenda)
- [ ] Drive test passed (gws drive files list)
- [ ] Sheets test passed (gws sheets spreadsheets create)
- [ ] Docs test passed (gws docs +write)
- [ ] Tasks test passed (gws tasks tasklists list)
- [ ] OpenClaw skills installed
- [ ] Core files updated (AGENTS.md, TOOLS.md, MEMORY.md)

All items checked? Your Google Workspace integration is ready to use.

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| "401 Unauthorized" or "Invalid grant" | Auth rejected | Check credentials. For Workspace, verify Domain-Wide Delegation is authorized. |
| "403 Forbidden" | Scope not granted | Re-paste all 81 scopes in Admin Console. Delete and re-add the entry. |
| "API not enabled" | API switch not flipped | Go to APIs & Services dashboard, find the missing API, enable it. |
| "Service account key creation is disabled" | Organization policy | See Section 5 above. |
| "command not found: gws" | Not installed or not in PATH | Reinstall with npm install -g @googleworkspace/cli. Close and reopen terminal. |
| Gmail fails but other services work | OAuth Consent Screen missing | Configure OAuth Consent Screen. Wait 15-30 minutes. |
| Changes not taking effect | Propagation delay | Wait 15 minutes to 24 hours. Gmail scopes are especially slow. |

---

## 🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY

During this installation, you may encounter instructions to restart the OpenClaw gateway.

YOU ARE FORBIDDEN from triggering gateway restarts yourself.

### Correct Process
When a gateway restart is needed:
1. STOP - Do NOT execute the restart command
2. NOTIFY the user: "This installation requires an OpenClaw gateway restart to complete."
3. INSTRUCT: "Type /restart in Telegram to trigger it"
4. WAIT for user action - do NOT proceed until confirmed

### Forbidden Actions
- Do NOT run openclaw gateway restart without explicit user permission
- Do NOT say "I will restart the gateway now" without asking first
- Do NOT assume the user wants the restart
