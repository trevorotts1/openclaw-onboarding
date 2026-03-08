## GOOGLE ACCOUNT ROUTING + BROWSER PERSISTENCE (SOVEREIGN)
- Ask account type first: Google Workspace (custom domain) or regular Gmail.
- Workspace path (Path A): use Domain-Wide Delegation flow.
- Gmail path (Path B): use OAuth 2.0 Desktop flow.
- Do not force Workspace-only setup for Gmail users.
- If browser automation is used, Playwright must use `launchPersistentContext(userDataDir)`.
- Never use regular `launch()` for onboarding automation.


+--------------------------------------------------------------+
|  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE        |
|  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.   |
+--------------------------------------------------------------+

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


+--------------------------------------------------------------+
|  TYP FILE STORAGE INSTRUCTIONS (only read this if TYP confirmed)
+--------------------------------------------------------------+

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

+--------------------------------------------------------------+
|  EXECUTION DISCIPLINE - MANDATORY BEFORE YOU START            |
+--------------------------------------------------------------+

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

+--------------------------------------------------------------+
|  AUTONOMOUS EXECUTION - ZERO PAUSE POLICY                     |
+--------------------------------------------------------------+

This document is designed for FULLY AUTONOMOUS agent execution.
The agent proceeds continuously from start to finish WITHOUT pausing
to ask the user for confirmation between steps.

THE ONLY ACCEPTABLE REASONS TO PAUSE AND ASK THE USER:
1. First-time browser login (persistent session means this happens once)
2. API keys or credentials the client has not entered yet
3. 2FA codes that only the user can provide

EVERYTHING ELSE: the agent handles it. No stopping. No "shall I continue?"
No "ready for the next step?" Just execute continuously until done or
until one of the three acceptable pause conditions is hit.

If an error occurs, the agent attempts to fix it. If the fix works,
continue. If the fix fails after exhausting all options, THEN pause
and report the specific blocker to the user.

======================================================================


# Google Workspace + Gmail Setup - Autonomous Installation Guide

This guide configures Google services so the AI agent can access Gmail, Calendar,
Drive, Docs, Sheets, and Contacts on behalf of the user.

Two paths are supported:
- **Path A (Workspace):** For Google Workspace accounts with a custom domain (e.g. user@company.com).
  Uses a service account with Domain-Wide Delegation.
- **Path B (Gmail):** For personal @gmail.com accounts.
  Uses OAuth 2.0 Desktop credentials with browser-based consent.


======================================================================
## BROWSER TOOL INITIALIZATION
======================================================================

Before any browser-based steps, check and initialize browser tools in this
priority order. Store the active tool in a variable for consistent use.

### Priority 1: agent-browser (Vercel) - USE THIS IF AVAILABLE

```bash
command -v agent-browser >/dev/null 2>&1 && echo "available" || echo "not found"
```

If not found, install it:
```bash
npm install -g agent-browser
agent-browser install
```

Verify installation:
```bash
agent-browser --version
```

Pattern reference for agent-browser commands used throughout this document:
```
agent-browser open <url>                              # navigate to URL
agent-browser snapshot -i --json                      # get interactive elements with refs (@e1, @e2...)
agent-browser snapshot -i                             # get interactive elements (human-readable)
agent-browser click @e1                               # click element by ref
agent-browser fill @e2 "value"                        # fill input field by ref
agent-browser find text "Submit" click                # find element by visible text, click it
agent-browser find label "Email" fill "user@email.com"  # find by label, fill value
agent-browser find role button click --name "Create"  # find by ARIA role + name, click
agent-browser wait "text"                             # wait for text to appear on page
agent-browser wait 2000                               # wait N milliseconds
agent-browser get url                                 # get current page URL
agent-browser get text @e3                            # get text content of element
```

If agent-browser is available, set:
```
BROWSER_TOOL="agent-browser"
```

### Priority 2: Playwright with launchPersistentContext - FALLBACK

Only use if agent-browser is not available or fails to install.

```bash
command -v npx >/dev/null 2>&1 && npx playwright --version 2>/dev/null && echo "available" || echo "not found"
```

If not found:
```bash
npm install -g playwright
npx playwright install chromium
```

CRITICAL: Always use `launchPersistentContext` - NEVER regular `launch()`.
Store session data at: `~/.openclaw/playwright-data/google-setup/`

```javascript
const { chromium } = require('playwright');
const browser = await chromium.launchPersistentContext(
  require('os').homedir() + '/.openclaw/playwright-data/google-setup/',
  { headless: false }
);
const page = browser.pages()[0] || await browser.newPage();
```

If Playwright is the active tool, set:
```
BROWSER_TOOL="playwright"
```

All steps in this document are written in agent-browser syntax (primary).
Playwright equivalents are shown in comments where helpful.
The agent translates as needed based on whichever tool is active.

### Priority 3: OpenClaw browser tool - LAST RESORT ONLY

Only use if both agent-browser and Playwright fail.
Not recommended for multi-step flows. Set:
```
BROWSER_TOOL="openclaw-browser"
```


======================================================================
## ACCOUNT TYPE DETECTION
======================================================================

Before starting either path, determine the account type.

Ask the user: "Is this a Google Workspace account (custom domain like user@company.com) or a personal Gmail account (@gmail.com)?"

Or detect automatically:
```bash
# If the user's email is already stored:
echo "$USER_EMAIL" | grep -q "@gmail.com" && ACCOUNT_TYPE="gmail" || ACCOUNT_TYPE="workspace"
```

- If ACCOUNT_TYPE is "workspace" - proceed to **Path A** below.
- If ACCOUNT_TYPE is "gmail" - skip to **Path B** below.


======================================================================
======================================================================
# PATH A: GOOGLE WORKSPACE (Custom Domain - Service Account + DWD)
======================================================================
======================================================================

This path applies ONLY to Google Workspace accounts (custom domain).
It uses a GCP service account with Domain-Wide Delegation (DWD) to
impersonate the Workspace user. The user must have admin access to
both Google Cloud Console and the Google Workspace Admin Console.

Store these variables as they are collected:
```
PROJECT_ID=""
SERVICE_ACCOUNT_EMAIL=""
SERVICE_ACCOUNT_CLIENT_ID=""
USER_EMAIL=""          # The Workspace user's email (e.g. user@company.com)
KEY_FILE_PATH=""       # Final location of JSON key file
```

---

## Step A1: Create a Google Cloud Project

1. Open the Google Cloud Console:
   ```
   agent-browser open https://console.cloud.google.com/
   ```
   # Playwright: await page.goto('https://console.cloud.google.com/')

2. Check login state:
   ```
   agent-browser snapshot -i --json
   agent-browser get url
   ```
   IF the current URL contains "accounts.google.com":
   - This is the ONLY acceptable pause in the flow.
   - Tell the user: "A browser window is open to Google Cloud Console. Please log in with your Google Workspace admin credentials. Press Enter when done."
   - Wait for the user to confirm.
   - After confirmation, verify redirect back to console.cloud.google.com:
     ```
     agent-browser get url
     ```
   - If still on accounts.google.com, wait and check again.
   - Once on console.cloud.google.com, continue WITHOUT pausing again.

3. Open the project dropdown:
   ```
   agent-browser snapshot -i
   agent-browser find role button click --name "Select a project"
   ```
   # Fallback: agent-browser find text "Select a project" click
   ```
   agent-browser wait 1000
   ```

4. Click New Project:
   ```
   agent-browser find text "New Project" click
   agent-browser wait 2000
   ```

5. Fill in the project name:
   ```
   agent-browser find label "Project name" fill "OpenClaw AI"
   ```

6. Click Create:
   ```
   agent-browser find role button click --name "Create"
   agent-browser wait "OpenClaw AI"
   ```
   Wait for the notification that says the project was created.

7. Select the new project:
   ```
   agent-browser find role button click --name "Select a project"
   agent-browser wait 1000
   agent-browser find text "OpenClaw AI" click
   agent-browser wait 2000
   ```

8. Capture the Project ID:
   ```
   agent-browser snapshot -i
   ```
   The Project ID appears under the project name in the dashboard or dropdown.
   It looks like "openclaw-ai-123456". Store it:
   ```
   PROJECT_ID="openclaw-ai-123456"   # Replace with actual value from snapshot
   ```

CONTINUE IMMEDIATELY. Do not pause.

---

## Step A2: Enable the Required APIs

Ensure the new project ("OpenClaw AI") is selected at the top of the page.

For each API below, navigate to the URL. If the "Enable" button is present,
click it. If "Manage" is displayed instead, the API is already enabled -
move to the next one immediately.

### API 1: Gmail API
```
agent-browser open https://console.cloud.google.com/apis/library/gmail.googleapis.com
agent-browser wait 2000
agent-browser snapshot -i
```
If "Enable" button exists:
```
agent-browser find role button click --name "Enable"
agent-browser wait 3000
```
If "Manage" is visible, skip to next API.

### API 2: Google Calendar API
```
agent-browser open https://console.cloud.google.com/apis/library/calendar-json.googleapis.com
agent-browser wait 2000
agent-browser snapshot -i
```
If "Enable" button exists:
```
agent-browser find role button click --name "Enable"
agent-browser wait 3000
```

### API 3: Google Drive API
```
agent-browser open https://console.cloud.google.com/apis/library/drive.googleapis.com
agent-browser wait 2000
agent-browser snapshot -i
```
If "Enable" button exists:
```
agent-browser find role button click --name "Enable"
agent-browser wait 3000
```

### API 4: Google Docs API
```
agent-browser open https://console.cloud.google.com/apis/library/docs.googleapis.com
agent-browser wait 2000
agent-browser snapshot -i
```
If "Enable" button exists:
```
agent-browser find role button click --name "Enable"
agent-browser wait 3000
```

### API 5: Google Sheets API
```
agent-browser open https://console.cloud.google.com/apis/library/sheets.googleapis.com
agent-browser wait 2000
agent-browser snapshot -i
```
If "Enable" button exists:
```
agent-browser find role button click --name "Enable"
agent-browser wait 3000
```

### API 6: People API (Contacts)
```
agent-browser open https://console.cloud.google.com/apis/library/people.googleapis.com
agent-browser wait 2000
agent-browser snapshot -i
```
If "Enable" button exists:
```
agent-browser find role button click --name "Enable"
agent-browser wait 3000
```

After all 6 APIs: verify by navigating to the API dashboard:
```
agent-browser open https://console.cloud.google.com/apis/dashboard
agent-browser wait 2000
agent-browser snapshot -i
```
All 6 APIs should appear in the list. If any are missing, go back and enable them.

CONTINUE IMMEDIATELY. Do not pause.

---

## Step A3: Set Up the OAuth Consent Screen

Required by Google before the agent can access sensitive services like Gmail.

1. Navigate to the consent screen:
   ```
   agent-browser open https://console.cloud.google.com/apis/credentials/consent
   agent-browser wait 2000
   agent-browser snapshot -i
   ```

2. If a "Get Started" button is present, click it:
   ```
   agent-browser find text "Get Started" click
   agent-browser wait 2000
   ```
   If no "Get Started" button, look for the consent screen configuration page directly.

3. Select User Type "Internal":
   ```
   agent-browser find text "Internal" click
   ```
   # Playwright: await page.click('text=Internal')

4. Click "Create":
   ```
   agent-browser find role button click --name "Create"
   agent-browser wait 2000
   ```

5. Fill in the app information:
   ```
   agent-browser find label "App name" fill "AI Workspace Agent"
   ```
   For "User support email" - select the admin email from the dropdown:
   ```
   agent-browser snapshot -i
   agent-browser find label "User support email" click
   agent-browser wait 500
   ```
   Select the admin email from the dropdown options.
   
   For "Developer contact email":
   ```
   agent-browser find label "Developer contact" fill "$USER_EMAIL"
   ```
   (Use the Workspace admin email address.)

6. Click "Save and Continue":
   ```
   agent-browser find role button click --name "Save and Continue"
   agent-browser wait 2000
   ```

7. On the Scopes page, click "Save and Continue" again (scopes are handled through DWD):
   ```
   agent-browser find role button click --name "Save and Continue"
   agent-browser wait 2000
   ```

8. Click "Back to Dashboard":
   ```
   agent-browser find text "Back to Dashboard" click
   agent-browser wait 2000
   ```

Without this step, Gmail returns "401 Unauthorized" errors.

CONTINUE IMMEDIATELY. Do not pause.

---

## Step A4: Create a Service Account

1. Navigate to the service accounts page:
   ```
   agent-browser open https://console.cloud.google.com/iam-admin/serviceaccounts
   agent-browser wait 2000
   agent-browser snapshot -i
   ```

2. Click "Create Service Account":
   ```
   agent-browser find text "CREATE SERVICE ACCOUNT" click
   ```
   # Fallback: agent-browser find text "Create service account" click
   ```
   agent-browser wait 2000
   ```

3. Fill in the service account details:
   ```
   agent-browser find label "Service account name" fill "OpenClaw-assistant"
   agent-browser wait 500
   ```
   The Service account ID auto-populates. Let it.
   
   Fill the description:
   ```
   agent-browser find label "Service account description" fill "Service account for AI assistant"
   ```

4. Click "Create and Continue":
   ```
   agent-browser find role button click --name "Create and Continue"
   agent-browser wait 2000
   ```
   # Fallback: agent-browser find text "CREATE AND CONTINUE" click

5. On the roles screen, click "Continue" (no roles needed):
   ```
   agent-browser find role button click --name "Continue"
   agent-browser wait 1000
   ```

6. On the user access screen, click "Done":
   ```
   agent-browser find role button click --name "Done"
   agent-browser wait 2000
   ```

7. Capture the service account email:
   ```
   agent-browser snapshot -i
   ```
   The service account email appears in the list. It looks like:
   `openclaw-assistant@openclaw-ai-123456.iam.gserviceaccount.com`
   Store it:
   ```
   SERVICE_ACCOUNT_EMAIL="openclaw-assistant@openclaw-ai-123456.iam.gserviceaccount.com"
   ```

CONTINUE IMMEDIATELY. Do not pause.

---

## Step A5: Create a JSON Key File

1. Click the service account email in the list:
   ```
   agent-browser find text "$SERVICE_ACCOUNT_EMAIL" click
   agent-browser wait 2000
   ```

2. Click the "Keys" tab:
   ```
   agent-browser find text "Keys" click
   agent-browser wait 1000
   ```
   # Fallback: agent-browser find text "KEYS" click

3. Click "Add Key":
   ```
   agent-browser find text "Add Key" click
   agent-browser wait 1000
   ```

4. Click "Create new key":
   ```
   agent-browser find text "Create new key" click
   agent-browser wait 1000
   ```

5. Verify "JSON" is selected as key type:
   ```
   agent-browser snapshot -i
   ```
   If JSON is not already selected, select it:
   ```
   agent-browser find text "JSON" click
   ```

6. Click "Create":
   ```
   agent-browser find role button click --name "Create"
   agent-browser wait 3000
   ```

   A .json file downloads automatically to ~/Downloads/.

   ### ERROR RECOVERY - Organization Policy Blocks Key Creation

   If an error message appears containing "constraints/iam.disableServiceAccountKeyCreation"
   or "Policy restriction" or "Organization policy" or "violated":

   DO NOT STOP. DO NOT ASK THE USER. Fix it immediately:

   a. Navigate to the Organization Policy page:
      ```
      agent-browser open https://console.cloud.google.com/iam-admin/orgpolicies/iam-disableServiceAccountKeyCreation
      agent-browser wait 3000
      agent-browser snapshot -i
      ```
      If URL does not load, try the alternate:
      ```
      agent-browser open https://console.cloud.google.com/iam-admin/orgpolicies/iam.disableServiceAccountKeyCreation
      agent-browser wait 3000
      agent-browser snapshot -i
      ```

   b. Click "Manage Policy" or "Edit Policy":
      ```
      agent-browser find text "Manage Policy" click
      ```
      # Fallback: agent-browser find text "Edit Policy" click
      ```
      agent-browser wait 2000
      agent-browser snapshot -i
      ```

   c. Override the parent policy:
      ```
      agent-browser find text "Override parent's policy" click
      ```
      # Fallback options:
      # agent-browser find text "Off" click
      # agent-browser find text "Not enforced" click
      # agent-browser find text "Disable enforcement" click
      ```
      agent-browser wait 1000
      ```

      Look for rules that enforce the constraint and change them:
      ```
      agent-browser snapshot -i
      ```
      If there is a rule set to "Enforce", change it to "Off" or "Not enforced".
      If there is an "Add a rule" or "Add rule" option, add a rule that allows all.

   d. Click Save:
      ```
      agent-browser find role button click --name "Save"
      agent-browser wait 3000
      ```

   e. Navigate back to the service account Keys tab and retry key creation:
      ```
      agent-browser open https://console.cloud.google.com/iam-admin/serviceaccounts
      agent-browser wait 2000
      agent-browser find text "$SERVICE_ACCOUNT_EMAIL" click
      agent-browser wait 2000
      agent-browser find text "Keys" click
      agent-browser wait 1000
      agent-browser find text "Add Key" click
      agent-browser wait 1000
      agent-browser find text "Create new key" click
      agent-browser wait 1000
      agent-browser find text "JSON" click
      agent-browser find role button click --name "Create"
      agent-browser wait 3000
      ```

   f. Verify the key downloaded. Continue without asking.

   ### END ERROR RECOVERY

7. DO NOT STOP OR PAUSE HERE. Move the key file immediately:
   ```bash
   mkdir -p ~/clawd/secrets
   mv ~/Downloads/*-*.json ~/clawd/secrets/gcp-service-account.json 2>/dev/null || \
   mv ~/Downloads/"$PROJECT_ID"-*.json ~/clawd/secrets/gcp-service-account.json
   chmod 600 ~/clawd/secrets/gcp-service-account.json
   ls -la ~/clawd/secrets/gcp-service-account.json
   ```
   Store the path:
   ```
   KEY_FILE_PATH="$HOME/clawd/secrets/gcp-service-account.json"
   ```

   Verify the file is valid JSON:
   ```bash
   python3 -c "import json; json.load(open('$HOME/clawd/secrets/gcp-service-account.json')); print('Valid JSON key file')"
   ```

CONTINUE IMMEDIATELY to Step A6. Do not pause. Do not ask the user anything.

---

## Step A6: Note the Client ID

1. Navigate to the service accounts page:
   ```
   agent-browser open https://console.cloud.google.com/iam-admin/serviceaccounts
   agent-browser wait 2000
   ```

2. Click the service account email:
   ```
   agent-browser find text "$SERVICE_ACCOUNT_EMAIL" click
   agent-browser wait 2000
   ```

3. Find the Unique ID / Client ID:
   ```
   agent-browser snapshot -i
   ```
   Look for "Unique ID" or "OAuth 2 Client ID". It is a long number like: 115886301121225599053

   Alternatively, extract it from the JSON key file:
   ```bash
   python3 -c "import json; print(json.load(open('$HOME/clawd/secrets/gcp-service-account.json'))['client_id'])"
   ```

   Store it:
   ```
   SERVICE_ACCOUNT_CLIENT_ID="115886301121225599053"   # Replace with actual value
   ```

CRITICAL: The Client ID is a NUMBER, not the email address. Using the email
address in Step A7 will fail silently. Always use the numeric ID.

CONTINUE IMMEDIATELY. Do not pause.

---

## Step A7: Enable Domain-Wide Delegation

### Part A - In Google Cloud Console

1. Navigate to the service account detail page:
   ```
   agent-browser open https://console.cloud.google.com/iam-admin/serviceaccounts
   agent-browser wait 2000
   agent-browser find text "$SERVICE_ACCOUNT_EMAIL" click
   agent-browser wait 2000
   ```

2. Find the Domain-Wide Delegation section:
   ```
   agent-browser snapshot -i
   ```
   Look for "Show Advanced Settings" or "Domain-wide delegation".

   If "Show Advanced Settings" exists:
   ```
   agent-browser find text "Show Advanced Settings" click
   agent-browser wait 1000
   agent-browser snapshot -i
   ```

3. Enable the delegation checkbox:
   ```
   agent-browser find text "Enable Google Workspace Domain-wide Delegation" click
   ```
   # Fallback: agent-browser find text "Domain-wide Delegation" click
   # Look for a checkbox element near this text and click it

4. Click Save:
   ```
   agent-browser find role button click --name "Save"
   agent-browser wait 2000
   ```

### Part B - In Google Workspace Admin Console

1. Navigate to the Admin Console:
   ```
   agent-browser open https://admin.google.com/
   agent-browser wait 3000
   agent-browser snapshot -i
   agent-browser get url
   ```
   
   IF the URL contains "accounts.google.com" or a login page appears:
   - This is the ONLY other acceptable pause.
   - Tell the user: "Please log in to the Google Workspace Admin Console. Press Enter when done."
   - Wait for user confirmation.
   - After confirmation, verify redirect to admin.google.com.

2. Navigate to API controls (direct URL to skip menu drilling):
   ```
   agent-browser open https://admin.google.com/ac/owl/domainwidedelegation
   agent-browser wait 3000
   agent-browser snapshot -i
   ```

   If the direct URL does not work, navigate manually:
   ```
   agent-browser open https://admin.google.com/
   agent-browser wait 2000
   agent-browser find text "Security" click
   agent-browser wait 2000
   agent-browser find text "Access and data control" click
   agent-browser wait 2000
   agent-browser find text "API controls" click
   agent-browser wait 2000
   agent-browser find text "Manage Domain Wide Delegation" click
   agent-browser wait 2000
   ```
   # Fallback: agent-browser find text "MANAGE DOMAIN WIDE DELEGATION" click

3. Click "Add new":
   ```
   agent-browser find text "Add new" click
   agent-browser wait 2000
   ```
   # Fallback: agent-browser find text "Add API client" click

4. Enter the Client ID:
   ```
   agent-browser find label "Client ID" fill "$SERVICE_ACCOUNT_CLIENT_ID"
   ```
   # Fallback: agent-browser find label "Client id" fill "$SERVICE_ACCOUNT_CLIENT_ID"

5. Enter the OAuth scopes (all on one line, comma-separated):
   ```
   agent-browser find label "OAuth scopes" fill "https://www.googleapis.com/auth/gmail.modify,https://www.googleapis.com/auth/calendar,https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/documents,https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/contacts.readonly"
   ```
   # Fallback: agent-browser find label "scopes" fill "..."

   The complete scope string (copy exactly):
   ```
   https://www.googleapis.com/auth/gmail.modify,https://www.googleapis.com/auth/calendar,https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/documents,https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/contacts.readonly
   ```

6. Click "Authorize":
   ```
   agent-browser find role button click --name "Authorize"
   agent-browser wait 3000
   ```

7. Verify the delegation appears in the list:
   ```
   agent-browser snapshot -i
   ```
   The Client ID and scopes should appear in the domain-wide delegation table.

The agent now has delegation access to Gmail, Calendar, Drive, Docs, Sheets, and Contacts.

CONTINUE IMMEDIATELY. Do not pause.

---

## Step A8: Configure the Environment

Run the following commands. The agent fills in actual values from previous steps:

```bash
# Create secrets directory if not present
mkdir -p ~/clawd/secrets

# Write environment variables
cat >> ~/clawd/secrets/.env << 'ENVEOF'
export GCP_PROJECT_ID=ACTUAL_PROJECT_ID
export GCP_SERVICE_ACCOUNT_EMAIL=ACTUAL_SERVICE_ACCOUNT_EMAIL
export GCP_SERVICE_ACCOUNT_CLIENT_ID=ACTUAL_CLIENT_ID
export GCP_IMPERSONATE_USER=ACTUAL_USER_EMAIL
export GCP_KEY_FILE=~/clawd/secrets/gcp-service-account.json
ENVEOF
```

Replace the ACTUAL_ placeholders with the stored variable values before running.

Also add to shell profile for persistence:
```bash
echo 'source ~/clawd/secrets/.env' >> ~/.zshrc
source ~/clawd/secrets/.env
```

CONTINUE IMMEDIATELY. Do not pause.

---

## Step A9: Test the Connection

Execute a test API call to verify everything works:

```python
python3 << 'PYTEST'
import json, time, base64, sys, os

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'cryptography'])
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'requests'])
    import requests

KEY_FILE = os.path.expanduser("~/clawd/secrets/gcp-service-account.json")
SCOPE = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar.readonly"

with open(KEY_FILE) as f:
    sa = json.load(f)

# Get impersonate user from env or key file
SUB = os.environ.get("GCP_IMPERSONATE_USER", "")
if not SUB:
    print("ERROR: GCP_IMPERSONATE_USER not set. Set it in ~/clawd/secrets/.env")
    sys.exit(1)

def b64url(d):
    if isinstance(d, str):
        d = d.encode()
    return base64.urlsafe_b64encode(d).rstrip(b'=').decode()

now = int(time.time())
header = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}))
payload = b64url(json.dumps({
    "iss": sa["client_email"],
    "sub": SUB,
    "scope": SCOPE,
    "aud": "https://oauth2.googleapis.com/token",
    "iat": now,
    "exp": now + 3600
}))

signing_input = f"{header}.{payload}"
private_key = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
signature = private_key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
jwt = f"{signing_input}.{b64url(signature)}"

# Exchange JWT for access token
token_resp = requests.post("https://oauth2.googleapis.com/token", data={
    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
    "assertion": jwt
})

if token_resp.status_code != 200:
    print(f"ERROR: Token exchange failed: {token_resp.status_code}")
    print(token_resp.text)
    sys.exit(1)

access_token = token_resp.json()["access_token"]
headers = {"Authorization": f"Bearer {access_token}"}

# Test Gmail
print("Testing Gmail API...")
gmail_resp = requests.get(
    "https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=3",
    headers=headers
)
if gmail_resp.status_code == 200:
    msgs = gmail_resp.json().get("messages", [])
    print(f"  Gmail OK - found {len(msgs)} recent messages")
else:
    print(f"  Gmail FAILED: {gmail_resp.status_code} - {gmail_resp.text[:200]}")

# Test Calendar
print("Testing Calendar API...")
cal_scope_jwt_payload = b64url(json.dumps({
    "iss": sa["client_email"],
    "sub": SUB,
    "scope": "https://www.googleapis.com/auth/calendar.readonly",
    "aud": "https://oauth2.googleapis.com/token",
    "iat": now,
    "exp": now + 3600
}))
cal_signing = f"{header}.{cal_scope_jwt_payload}"
cal_sig = private_key.sign(cal_signing.encode(), padding.PKCS1v15(), hashes.SHA256())
cal_jwt = f"{cal_signing}.{b64url(cal_sig)}"
cal_token_resp = requests.post("https://oauth2.googleapis.com/token", data={
    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
    "assertion": cal_jwt
})
if cal_token_resp.status_code == 200:
    cal_token = cal_token_resp.json()["access_token"]
    cal_resp = requests.get(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events?maxResults=3&orderBy=startTime&singleEvents=true",
        headers={"Authorization": f"Bearer {cal_token}"}
    )
    if cal_resp.status_code == 200:
        events = cal_resp.json().get("items", [])
        print(f"  Calendar OK - found {len(events)} upcoming events")
    else:
        print(f"  Calendar FAILED: {cal_resp.status_code} - {cal_resp.text[:200]}")
else:
    print(f"  Calendar token FAILED: {cal_token_resp.status_code}")

print("\n=== CONNECTION TEST COMPLETE ===")
PYTEST
```

### IF TEST PASSES:
- Report success to the user.
- IMMEDIATELY proceed to the GOG Setup phase below. Do not pause.

### IF TEST FAILS:
- Check the error message.
- Common fixes:
  - "Access denied" or 403: DWD scopes not authorized. Go back to Step A7 Part B and re-enter scopes.
  - "Service account not found": JSON key file path wrong. Verify ~/clawd/secrets/gcp-service-account.json exists.
  - 401 Unauthorized: OAuth consent screen not configured. Go back to Step A3.
  - "Cannot impersonate": DWD not enabled in BOTH Cloud Console AND Admin Console.
- Fix the issue, then re-run the test.
- Do NOT proceed to GOG if the test fails.

---

## Step A10: GOG CLI Setup (Executes Automatically After Test Passes)

GOG is a CLI tool for Google Workspace. It uses the service account + DWD
to access Gmail, Calendar, Drive, Docs, Sheets, and Contacts.

1. Check if GOG is installed:
   ```bash
   command -v gog >/dev/null 2>&1 && echo "GOG installed" || echo "GOG needs install"
   ```

2. If not installed, install it:
   ```bash
   brew install steipete/tap/gogcli
   ```
   If brew is not available:
   ```bash
   # Check for alternative install methods
   curl -sL https://github.com/steipete/gog/releases/latest/download/gog-$(uname -s)-$(uname -m) -o /usr/local/bin/gog && chmod +x /usr/local/bin/gog
   ```

3. Register the service account with GOG:
   ```bash
   gog auth sa ~/clawd/secrets/gcp-service-account.json --impersonate "$GCP_IMPERSONATE_USER"
   ```

4. Add the account with all required services:
   ```bash
   gog auth add "$GCP_IMPERSONATE_USER" --services gmail,calendar,drive,contacts,docs,sheets
   ```

5. Verify GOG is working:
   ```bash
   gog auth list
   gog gmail search 'newer_than:1d' --max 3 --account "$GCP_IMPERSONATE_USER"
   ```
   If the gmail search returns results (or an empty list with no errors), GOG is working.

6. Store the default account in environment:
   ```bash
   echo "export GOG_DEFAULT_ACCOUNT=$GCP_IMPERSONATE_USER" >> ~/clawd/secrets/.env
   source ~/clawd/secrets/.env
   ```

GOG setup is now complete. The agent can access Gmail, Calendar, Drive,
Docs, Sheets, and Contacts through GOG CLI commands.

---

## PATH A COMPLETE

Report to the user:
- Google Cloud Project created: [PROJECT_ID]
- 6 APIs enabled
- Service account created: [SERVICE_ACCOUNT_EMAIL]
- JSON key file stored at: ~/clawd/secrets/gcp-service-account.json
- Domain-Wide Delegation configured with 6 scopes
- Connection test passed
- GOG CLI installed and configured
- Default account: [USER_EMAIL]

The agent now has full access to Google Workspace services.


======================================================================
======================================================================
# PATH B: PERSONAL GMAIL (OAuth 2.0 Desktop Credentials)
======================================================================
======================================================================

This path applies ONLY to personal @gmail.com accounts.
It uses OAuth 2.0 Desktop credentials with a browser-based consent flow.
No Admin Console access needed. No Domain-Wide Delegation. No service account impersonation.

The user logs in through the browser ONCE, GOG stores the OAuth refresh token,
and subsequent access is automatic.

Store these variables as they are collected:
```
PROJECT_ID=""
CLIENT_ID=""          # OAuth 2.0 Client ID (NOT a service account Client ID)
CLIENT_SECRET=""      # OAuth 2.0 Client Secret
USER_EMAIL=""         # The user's Gmail address (e.g. user@gmail.com)
```

---

## Step B1: Create a Google Cloud Project

Same as Step A1. Follow the exact same steps:

1. Open Google Cloud Console:
   ```
   agent-browser open https://console.cloud.google.com/
   ```

2. Check login state:
   ```
   agent-browser get url
   ```
   IF on a login page:
   - Tell the user: "Please log in to Google Cloud Console with your Gmail account. Press Enter when done."
   - Wait for confirmation. This is the ONLY acceptable pause.

3. Open the project dropdown and click "New Project":
   ```
   agent-browser find role button click --name "Select a project"
   agent-browser wait 1000
   agent-browser find text "New Project" click
   agent-browser wait 2000
   ```

4. Name the project "OpenClaw AI" and create:
   ```
   agent-browser find label "Project name" fill "OpenClaw AI"
   agent-browser find role button click --name "Create"
   agent-browser wait "OpenClaw AI"
   ```

5. Select the project:
   ```
   agent-browser find role button click --name "Select a project"
   agent-browser wait 1000
   agent-browser find text "OpenClaw AI" click
   agent-browser wait 2000
   ```

6. Capture the Project ID:
   ```
   agent-browser snapshot -i
   ```
   Store: `PROJECT_ID="openclaw-ai-123456"`

CONTINUE IMMEDIATELY. Do not pause.

---

## Step B2: Enable the Required APIs

Same as Step A2. Enable all 6 APIs:

```
agent-browser open https://console.cloud.google.com/apis/library/gmail.googleapis.com
agent-browser wait 2000
agent-browser snapshot -i
```
Click "Enable" if present. Repeat for:
- https://console.cloud.google.com/apis/library/calendar-json.googleapis.com
- https://console.cloud.google.com/apis/library/drive.googleapis.com
- https://console.cloud.google.com/apis/library/docs.googleapis.com
- https://console.cloud.google.com/apis/library/sheets.googleapis.com
- https://console.cloud.google.com/apis/library/people.googleapis.com

For each: navigate, wait 2000, snapshot, click "Enable" if shown, wait 3000.

CONTINUE IMMEDIATELY. Do not pause.

---

## Step B3: Set Up the OAuth Consent Screen (External)

For Gmail accounts, the consent screen type must be "External" (not "Internal").

1. Navigate to the consent screen:
   ```
   agent-browser open https://console.cloud.google.com/apis/credentials/consent
   agent-browser wait 2000
   agent-browser snapshot -i
   ```

2. If asked to choose user type, select "External":
   ```
   agent-browser find text "External" click
   ```

3. Click "Create":
   ```
   agent-browser find role button click --name "Create"
   agent-browser wait 2000
   ```

4. Fill in the app information:
   ```
   agent-browser find label "App name" fill "OpenClaw AI Agent"
   ```
   For "User support email" - enter or select the user's Gmail:
   ```
   agent-browser find label "User support email" fill "$USER_EMAIL"
   ```
   For "Developer contact email":
   ```
   agent-browser find label "Developer contact" fill "$USER_EMAIL"
   ```

5. Click "Save and Continue":
   ```
   agent-browser find role button click --name "Save and Continue"
   agent-browser wait 2000
   ```

6. On the Scopes page, click "Add or Remove Scopes":
   ```
   agent-browser find text "Add or Remove Scopes" click
   agent-browser wait 2000
   ```

7. Add the following scopes. In the "Manually add scopes" input, paste:
   ```
   https://www.googleapis.com/auth/gmail.modify
   https://www.googleapis.com/auth/calendar
   https://www.googleapis.com/auth/drive
   https://www.googleapis.com/auth/documents
   https://www.googleapis.com/auth/spreadsheets
   https://www.googleapis.com/auth/contacts.readonly
   ```
   ```
   agent-browser find label "Manually add scopes" fill "https://www.googleapis.com/auth/gmail.modify,https://www.googleapis.com/auth/calendar,https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/documents,https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/contacts.readonly"
   ```
   Click "Add to Table" or "Update":
   ```
   agent-browser find text "Add to Table" click
   agent-browser wait 1000
   ```

8. Click "Save and Continue":
   ```
   agent-browser find role button click --name "Save and Continue"
   agent-browser wait 2000
   ```

9. On the Test Users page, click "Add Users":
   ```
   agent-browser find text "Add Users" click
   agent-browser wait 1000
   agent-browser find label "Email" fill "$USER_EMAIL"
   agent-browser find text "Add" click
   agent-browser wait 1000
   ```

10. Click "Save and Continue":
    ```
    agent-browser find role button click --name "Save and Continue"
    agent-browser wait 2000
    ```

11. Click "Back to Dashboard":
    ```
    agent-browser find text "Back to Dashboard" click
    agent-browser wait 2000
    ```

NOTE: The app stays in "Testing" mode. That is fine for personal use.
Only the test user (the Gmail account owner) can authorize.
No need to publish or verify the app.

CONTINUE IMMEDIATELY. Do not pause.

---

## Step B4: Create OAuth 2.0 Desktop Credentials

1. Navigate to Credentials:
   ```
   agent-browser open https://console.cloud.google.com/apis/credentials
   agent-browser wait 2000
   agent-browser snapshot -i
   ```

2. Click "Create Credentials":
   ```
   agent-browser find text "Create Credentials" click
   agent-browser wait 1000
   ```

3. Select "OAuth client ID":
   ```
   agent-browser find text "OAuth client ID" click
   agent-browser wait 2000
   ```

4. Set the application type to "Desktop app":
   ```
   agent-browser find label "Application type" click
   agent-browser wait 500
   agent-browser find text "Desktop app" click
   agent-browser wait 1000
   ```

5. Set the name:
   ```
   agent-browser find label "Name" fill "OpenClaw Desktop Client"
   ```

6. Click "Create":
   ```
   agent-browser find role button click --name "Create"
   agent-browser wait 3000
   ```

7. A dialog appears showing the Client ID and Client Secret. Capture both:
   ```
   agent-browser snapshot -i
   ```
   Store these values:
   ```
   CLIENT_ID="xxxxxxxxxxxx.apps.googleusercontent.com"
   CLIENT_SECRET="GOCSPX-xxxxxxxxxxxxxxxx"
   ```

8. Click "Download JSON" to download the credentials file:
   ```
   agent-browser find text "Download JSON" click
   agent-browser wait 2000
   ```

9. Move the credentials file:
   ```bash
   mkdir -p ~/clawd/secrets
   mv ~/Downloads/client_secret_*.json ~/clawd/secrets/google-oauth-credentials.json
   chmod 600 ~/clawd/secrets/google-oauth-credentials.json
   ```

10. Click "OK" to close the dialog:
    ```
    agent-browser find role button click --name "OK"
    ```

CONTINUE IMMEDIATELY. Do not pause.

---

## Step B5: GOG CLI Setup with OAuth Flow

1. Check if GOG is installed:
   ```bash
   command -v gog >/dev/null 2>&1 && echo "GOG installed" || echo "GOG needs install"
   ```

2. If not installed:
   ```bash
   brew install steipete/tap/gogcli
   ```

3. Add the Gmail account to GOG with browser OAuth flow:
   ```bash
   gog auth add "$USER_EMAIL" --services gmail,calendar,drive,contacts,docs,sheets
   ```
   
   This opens a browser window for the user to authorize the app.
   
   IF the browser opens to a consent screen:
   - Tell the user: "A browser window will open asking you to authorize the OpenClaw AI Agent app. Click 'Allow' to grant access. This only needs to happen once."
   - The user clicks through the consent flow.
   - GOG captures the refresh token automatically.
   
   IF GOG requires the client credentials file:
   ```bash
   gog auth add "$USER_EMAIL" --services gmail,calendar,drive,contacts,docs,sheets \
     --credentials ~/clawd/secrets/google-oauth-credentials.json
   ```

4. Verify GOG is working:
   ```bash
   gog auth list
   gog gmail search 'newer_than:1d' --max 3 --account "$USER_EMAIL"
   ```

5. Store the default account:
   ```bash
   echo "export GOG_DEFAULT_ACCOUNT=$USER_EMAIL" >> ~/clawd/secrets/.env
   source ~/clawd/secrets/.env
   ```

---

## Step B6: Test the Connection

```bash
# Quick verification through GOG
gog gmail search 'newer_than:7d' --max 5 --account "$USER_EMAIL"
gog calendar list --account "$USER_EMAIL" --max 5
```

If both commands return results (or empty lists without errors), the setup is complete.

If errors occur:
- "Token expired": Run `gog auth add "$USER_EMAIL" --services gmail,calendar,drive,contacts,docs,sheets` again
- "Unauthorized": Check that the test user was added in Step B3
- "API not enabled": Go back to Step B2 and verify all 6 APIs are enabled

---

## PATH B COMPLETE

Report to the user:
- Google Cloud Project created: [PROJECT_ID]
- 6 APIs enabled
- OAuth Consent Screen configured (External, Testing mode)
- OAuth 2.0 Desktop credentials created
- GOG CLI installed and configured with OAuth token
- Default account: [USER_EMAIL]

The agent now has access to Gmail, Calendar, Drive, Docs, Sheets, and Contacts
through GOG CLI commands using OAuth 2.0 authentication.


======================================================================
## TROUBLESHOOTING QUICK REFERENCE
======================================================================

| Problem | What to check | Fix |
|---------|---------------|-----|
| "Access denied" or 403 errors | DWD scopes not authorized (Workspace only) | Re-do Step A7 Part B - re-enter Client ID and scopes |
| "Service account not found" | JSON key file path wrong | Verify ~/clawd/secrets/gcp-service-account.json exists and is valid JSON |
| "Cannot impersonate user" | DWD not enabled in BOTH consoles | Enable in Cloud Console (Step A7 Part A) AND Admin Console (Step A7 Part B) |
| Gmail or Calendar not working | APIs not enabled | Re-do Step A2/B2 - verify all 6 APIs show "Manage" not "Enable" |
| "401 Unauthorized" | OAuth consent screen missing | Configure it (Step A3 or B3) |
| "Service account key creation is disabled" | Organization policy blocks key creation | See inline error recovery in Step A5 - override the org policy |
| "constraints/iam.disableServiceAccountKeyCreation" | Same as above | Navigate to org policy page, override parent policy, set to not enforced, save, retry |
| "Token expired" (Gmail path) | OAuth refresh token expired | Re-run `gog auth add` to re-authorize |
| "Unauthorized" (Gmail path) | Test user not added | Add user's email as test user in consent screen (Step B3) |
| GOG command fails | GOG not configured | Run `gog auth list` to check; re-run auth setup if empty |
| "Project not found" | Wrong project selected | Use project dropdown in Cloud Console to select "OpenClaw AI" |
| "Quota exceeded" | Too many API calls | Wait a few minutes and retry; check quotas in Cloud Console |

### Advanced Troubleshooting - Organization Policy Fix (Detailed)

If your Google Cloud organization was created after May 2024, Google blocks
service account key creation by default with the
`iam.disableServiceAccountKeyCreation` constraint.

To fix:
1. Go to: https://console.cloud.google.com/iam-admin/orgpolicies/iam-disableServiceAccountKeyCreation
2. Click "Manage Policy" or "Edit Policy"
3. Under "Applies to", select "Override parent's policy" or "Customize"
4. Set enforcement to "Off" or "Not enforced"
5. If a rule exists that enforces the constraint, delete it or change it to "Allow All"
6. Click "Save"
7. Wait 30-60 seconds for propagation
8. Retry key creation in Step A5

This override only affects your project. It does not change organization-wide settings
for other projects.


======================================================================
## SECURITY NOTES
======================================================================

- The service account (Path A) can only access what is specifically authorized through DWD scopes
- No user password is shared with the agent - it uses a cryptographic key file (Path A) or OAuth token (Path B)
- Access can be revoked at any time:
  - Path A: Remove the delegation entry in Admin Console
  - Path B: Revoke app access at https://myaccount.google.com/permissions
- The JSON key file must be kept secure - treat it like a password
- OAuth refresh tokens (Path B) are stored by GOG in its config directory
- Both paths use principle of least privilege - only the scopes listed are granted


======================================================================
## WHAT THIS SKILL COVERS VS. WHAT IT DOES NOT
======================================================================

**This skill covers:**
- Creating the Google Cloud project
- Enabling 6 core APIs (Gmail, Calendar, Drive, Docs, Sheets, People/Contacts)
- Path A: Service account creation, JSON key, Domain-Wide Delegation with 6 scopes
- Path B: OAuth 2.0 Desktop credentials, External consent screen, browser auth flow
- OAuth Consent Screen configuration (Internal for Workspace, External for Gmail)
- Organization policy error recovery for key creation
- GOG CLI installation and configuration for both paths
- Connection testing
- Environment variable setup

**The full integration guide (Skill 13) covers additionally:**
- All 26 APIs and all 70+ OAuth scopes
- The google-api.js zero-dependency script
- Playwright browser automation for advanced flows
- Comprehensive per-service testing


======================================================================
## KNOWN GAPS IN THIS DOCUMENT
======================================================================

The following items are referenced in the broader setup process but are not
fully detailed here:

1. **The full 70+ scope list** - This skill covers 6 basic scopes. Skill 13 has
   the complete list for all 26 services.
2. **google-api.js script installation** - The zero-dependency script for direct
   API access is covered in Skill 13, Section 11.
3. **Advanced GOG configuration** - Multi-account GOG setups and advanced options
   are covered in Skill 13, Section 17.
4. **Workspace-to-Gmail migration** - Switching from Path A to Path B (or vice versa)
   is not covered. Start fresh with the correct path.
