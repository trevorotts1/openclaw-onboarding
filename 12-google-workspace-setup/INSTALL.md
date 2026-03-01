
╔══════════════════════════════════════════════════════════════╗
  MANDATORY TSP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TSP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TSP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TSP"
- Look in your session context for prior TSP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TSP:
Proceed to the instructions below. Follow the TSP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TSP:
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TSP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TSP, I will bloat your core .md files and waste your tokens."

DO NOT PROCEED PAST THIS POINT WITHOUT TSP CONFIRMED.

══════════════════════════════════════════════════════════════════
  TSP FILE STORAGE INSTRUCTIONS (only read this if TSP confirmed)
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

# Google Workspace Setup - Installation Guide

This guide walks you through setting up Google Workspace so your AI assistant can access Gmail, Calendar, Drive, Docs, and Sheets on your behalf.

**Who this is for:** Anyone with a Google Workspace account (that means a business email like yourname@yourcompany.com - NOT a personal @gmail.com account).

**What you will need before starting:**
- A computer with a web browser (Chrome, Safari, Firefox, etc.)
- Your Google Workspace admin login (the email and password you use to manage your business Google account)
- About 30 minutes of uninterrupted time

---

## Step 1: Create a Google Cloud Project

A Google Cloud Project is like a folder that holds all the settings your AI needs. You only create it once.

1. Open your web browser and go to this address: https://console.cloud.google.com/
2. Sign in with your Google Workspace admin email (the business one, like you@yourcompany.com)
3. Look at the very top of the page. You will see a dropdown near the top left - it might say "Select a project" or show another project name
4. Click that dropdown
5. In the window that pops up, click the button that says "New Project" in the top right corner
6. In the "Project name" field, type something easy to remember, like "OpenClaw AI"
7. Leave everything else as it is
8. Click the "Create" button
9. Wait a few seconds. Google will create your project.
10. Click the project dropdown at the top again and select the project you just created. You should see its name appear at the top of the page.

**Write down your Project ID.** It shows under the project name in the dropdown. It looks something like "openclaw-ai-123456". You will need it later.

---

## Step 2: Enable the Required APIs

APIs are like "switches" that turn on different Google services for your AI. You need to flip each switch one at a time.

Go to each link below, and for each one, click the blue "Enable" button. If you see a button that says "Manage" instead, that means it is already turned on - just move to the next one.

**Before clicking each link, make sure your new project is selected at the top of the page.**

1. **Gmail API** - https://console.cloud.google.com/apis/library/gmail.googleapis.com
   - Click "Enable" (this lets your AI read and send email)

2. **Google Calendar API** - https://console.cloud.google.com/apis/library/calendar-json.googleapis.com
   - Click "Enable" (this lets your AI check and create calendar events)

3. **Google Drive API** - https://console.cloud.google.com/apis/library/drive.googleapis.com
   - Click "Enable" (this lets your AI find and manage files)

4. **Google Docs API** - https://console.cloud.google.com/apis/library/docs.googleapis.com
   - Click "Enable" (this lets your AI read and edit documents)

5. **Google Sheets API** - https://console.cloud.google.com/apis/library/sheets.googleapis.com
   - Click "Enable" (this lets your AI read and update spreadsheets)

6. **People API** - https://console.cloud.google.com/apis/library/people.googleapis.com
   - Click "Enable" (this lets your AI look up contacts)

After enabling each one, the button should change from "Enable" to "Manage". If it still says "Enable" after clicking, try clicking it one more time.

---

## Step 3: Set Up the OAuth Consent Screen

This step is required by Google before your AI can access sensitive services like Gmail. Even though you are not building a public app, Google still requires this screen to be configured.

1. Go to: https://console.cloud.google.com/apis/credentials/consent
2. If you see a "Get Started" button, click it
3. You will be asked to choose a User Type. Select "Internal" (this limits access to your organization only - which is what you want)
4. Click "Create"
5. Fill in these fields:
   - App name: Type "AI Workspace Agent" (or any name you like)
   - User support email: Select your email from the dropdown
   - Developer contact email: Type your email address
6. Click "Save and Continue"
7. On the Scopes page, you can click "Save and Continue" (scopes will be handled through Domain-Wide Delegation later)
8. Click "Back to Dashboard"

**Why this matters:** Without this step, Gmail will refuse to work and you will see "401 Unauthorized" errors. Do not skip it.

---

## Step 4: Create a Service Account

A Service Account is like a "robot employee" - it is a special account your AI uses to access Google services without needing your password.

1. Go to: https://console.cloud.google.com/iam-admin/serviceaccounts
2. Make sure your project is selected at the top of the page
3. Click the button that says "+ CREATE SERVICE ACCOUNT"
4. Fill in:
   - Service account name: Type "OpenClaw-assistant"
   - The Service account ID will fill in automatically
   - Description: Type "Service account for AI assistant"
5. Click "Create and Continue"
6. On the next screen (about roles), just click "Continue" - you do not need to add any roles here
7. On the next screen (about granting users access), just click "Done"

You should now see your new service account in the list.

---

## Step 5: Create a JSON Key File

The JSON key file is like an ID badge for your robot employee. Your AI needs this file to prove who it is.

1. In the list of service accounts, click on the email address of the one you just created
2. Click the "Keys" tab near the top of the page
3. Click the "Add Key" dropdown button
4. Select "Create new key"
5. Make sure "JSON" is selected (it usually is by default)
6. Click "Create"
7. A file will automatically download to your computer. It will have a long name ending in .json

**Important:** This file is like a master password. Keep it safe. Do not share it, email it, or post it online.

Now move the file to your secrets folder by opening your Terminal (on Mac, search for "Terminal" in Spotlight) and typing:

```
mv ~/Downloads/your-project-*.json ~/clawd/secrets/gcp-service-account.json
chmod 600 ~/clawd/secrets/gcp-service-account.json
```

(Replace "your-project-*.json" with the actual filename if the wildcard does not work.)

---

## Step 6: Note the Client ID

You need a special number called the Client ID for the next step.

1. Go back to your service account page: https://console.cloud.google.com/iam-admin/serviceaccounts
2. Click on your service account's email address
3. Look for a field called "Unique ID" or "Client ID" - it is a long number like 115886301121225599053
4. Copy this number and save it somewhere (a sticky note, a text file, wherever you can find it again)

**Important:** The Client ID is a NUMBER, not the email address. Using the email address in the next step will not work.

---

## Step 7: Enable Domain-Wide Delegation

This step gives your robot employee (the service account) permission to act on your behalf. You need to do this in two places.

### Part A - In Google Cloud Console

1. Go to: https://console.cloud.google.com/iam-admin/serviceaccounts
2. Click on your service account's email
3. Look for "Show Advanced Settings" or a section called "Domain-Wide Delegation"
4. Check the box that says "Enable Google Workspace Domain-Wide Delegation"
5. Click "Save"

### Part B - In Google Workspace Admin Console

1. Go to: https://admin.google.com/
2. Sign in with your Google Workspace admin account (if you are not already signed in)
3. In the left menu, click on "Security"
4. Click on "Access and data control"
5. Click on "API controls"
6. Click on "Manage Domain Wide Delegation"
7. Click "Add new"
8. In the "Client ID" field, paste the number you copied in Step 6
9. In the "OAuth scopes" field, paste this entire block (it is all one line):

```
https://www.googleapis.com/auth/gmail.modify,https://www.googleapis.com/auth/calendar,https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/documents,https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/contacts.readonly
```

10. Click "Authorize"

After you click Authorize, your AI now has permission to access Gmail, Calendar, Drive, Docs, Sheets, and Contacts on your behalf.

---

## Step 8: Configure Your Environment

Tell your AI where the key file is and which email to use.

1. Open Terminal on your Mac (search for "Terminal" in Spotlight)
2. Type these commands and press Enter after each one (replace the placeholder values with YOUR actual values):

```bash
echo 'export GCP_PROJECT_ID=your-project-id' >> ~/.zshrc
echo 'export GCP_SERVICE_ACCOUNT_EMAIL=OpenClaw-assistant@your-project-id.iam.gserviceaccount.com' >> ~/.zshrc
echo 'export GCP_IMPERSONATE_USER=your-email@yourdomain.com' >> ~/.zshrc
source ~/.zshrc
```

You can also add these values to your secrets file at ~/clawd/secrets/.env

3. Tell your AI: "My GCP service account is at ~/clawd/secrets/gcp-service-account.json and it impersonates your-email@yourdomain.com"

---

## Step 9: Test the Connection

Ask your AI one of these questions to make sure everything works:

- "Check my Gmail for unread messages"
- "What is on my calendar today?"

If it comes back with real results, congratulations - you are all set!

If you get an error, see the Troubleshooting section below.

---

## Troubleshooting Quick Reference

| Problem | What to check |
|---------|---------------|
| "Access denied" errors | Make sure Domain-Wide Delegation is enabled (Step 7) and scopes are authorized |
| "Service account not found" | Check the JSON key file path is correct (Step 5) |
| "Cannot impersonate user" | The service account needs Domain-Wide Delegation enabled in BOTH Cloud Console AND Admin Console |
| Gmail or Calendar not working | Make sure you enabled all the required APIs in Step 2 |
| "401 Unauthorized" | Check that the OAuth Consent Screen is configured (Step 3) |
| "Service account key creation is disabled" | Your organization may have a security policy blocking this - see the full documentation (Skill 13, Section 8) for the fix |

---

## Security Notes

- The service account can only access what you specifically authorize through the scopes in Step 7
- Your password is never shared with the AI - it uses a cryptographic key file instead
- You can revoke access at any time by going back to the Admin Console and removing the delegation entry
- Keep the JSON key file secure - treat it like a password

---

## What This Skill Covers vs. What It Does Not

**This skill covers:** Creating the Google Cloud project, enabling 6 core APIs, creating the service account, setting up Domain-Wide Delegation with basic scopes, configuring the OAuth Consent Screen, and testing the connection.

**The full integration guide (Skill 13) covers:** All 26 APIs, all 70+ OAuth scopes, Organization Policy fixes, the google-api.js zero-dependency script, GOG CLI setup, Playwright browser automation, and comprehensive testing of every service.

---

## KNOWN GAPS IN THIS DOCUMENT

The following items are referenced in the broader setup process but are not fully detailed in the source material for this skill. They may need to be addressed in a future update:

1. **Organization Policy blocks** - If your organization was created after May 2024, Google may block service account key creation by default. The fix is covered in detail in Skill 13, Section 8.
2. **The full 70+ scope list** - This skill only covers the 6 basic scopes. Skill 13 has the complete list of all scopes for all 26 services.
3. **GOG CLI installation and configuration** - Covered in Skill 13, Section 17.
4. **google-api.js script installation** - The zero-dependency script for direct API access is covered in Skill 13, Section 11.
