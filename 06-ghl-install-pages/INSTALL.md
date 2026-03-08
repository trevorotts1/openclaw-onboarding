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


TYP FILE STORAGE INSTRUCTIONS (only read this if TYP confirmed)

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

# GHL Install Pages - Setup and Prerequisites

This guide covers everything the AI agent needs to have in place BEFORE deploying pages into GoHighLevel (Convert and Flow). This is about getting the tools ready. For the actual step-by-step deployment process, see INSTRUCTIONS.md.

This document assumes the HTML code is already written and ready to go. The agent is setting up the ability to insert that HTML code into GHL's page builder.


## What This Skill Does

This skill enables the AI agent to use browser automation (Playwright) to:
- Log into a GoHighLevel / Convert and Flow account
- Navigate to the page builder
- Create new funnels or website pages
- Paste HTML code into the builder's code block element
- Save, preview, and publish pages
- Update existing pages with new code


## Prerequisites Verification

The agent must verify ALL of these are in place before proceeding:

1. [ ] Playwright browser automation tool is installed and working
2. [ ] Access to the GHL/Convert and Flow account (login credentials or saved browser session)
3. [ ] Finished HTML code is ready to paste (all CSS must be inline or in style tags, no React, no external dependencies)
4. [ ] Page requirements are documented (page names, URL paths, which HTML code goes where)
5. [ ] GHL credentials are stored securely (see Credential Storage below)
6. [ ] Target SUB-ACCOUNT is identified (see Sub-Account Selection below)


## Step 1: Install Playwright

Execute the following commands to install Playwright:

```bash
pip install playwright
playwright install chromium
```

The first command installs the Playwright library. The second command downloads the Chromium browser that Playwright will control.

Verify installation:
```bash
python3 -c "from playwright.sync_api import sync_playwright; print('Playwright installed successfully')"
```

Expected output: "Playwright installed successfully" printed to stdout.


## Step 2: Store GHL Credentials Securely

GHL login credentials must NEVER be hardcoded in scripts or saved in code repositories.

Store credentials in the workspace secrets file:
```bash
nano ~/clawd/secrets/.env
```

Add these two lines (replace with actual email and password):
```
GHL_EMAIL=user@email.com
GHL_PASSWORD=the-account-password
```

Save and close the file (Ctrl+O, Enter, Ctrl+X).

Load credentials in Playwright scripts:
```python
import os
email = os.environ.get("GHL_EMAIL")
password = os.environ.get("GHL_PASSWORD")
```

If the account uses SSO (single sign-on) instead of email/password login, document this in workspace files and use the persistent session approach where the user logs in once manually and the session is reused.


## Step 3: Configure Browser Settings

GHL's page builder requires specific minimum browser window size. If the window is too small, the sidebar collapses, buttons move around, and automation fails.

Required settings:
- Width: 1280 pixels (1440 recommended)
- Height: 800 pixels (900 recommended)

Use this browser launch configuration:

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir="./ghl_session",
        headless=False,
        viewport={"width": 1440, "height": 900},
        args=[
            "--window-size=1440,900",
            "--disable-blink-features=AutomationControlled",
        ]
    )
    page = browser.pages[0] if browser.pages else browser.new_page()
```

Configuration notes:
- Always use launch_persistent_context (not regular launch). This saves login session so re-authentication is not required on every run.
- The user_data_dir ("./ghl_session") is where the browser saves cookies and session data. This folder persists between runs.
- headless=False means the browser window is visible. This is required for first login and 2FA.
- Below 1280px width: GHL's left sidebar collapses into a hamburger menu, breaking automation.
- Below 900px height: Modal dialogs may not fully render, cutting off buttons.


## Step 4: Identify and Switch to Correct Sub-Account

GHL/Convert and Flow uses a two-level structure:
- **Agency level:** The top-level dashboard where all clients are managed
- **Sub-account level:** Each client has their own sub-account with separate sites, funnels, and settings

The agent MUST be inside the correct sub-account before building pages. If pages are deployed in the wrong sub-account, the client will not see them.

To verify current sub-account:
1. Check the top-left corner of the GHL dashboard
2. The sub-account name is displayed next to the logo
3. If it shows the agency name (not the client's name), the agent is at agency level and must switch

To switch to the correct sub-account:
1. Click the sub-account name or dropdown in the top-left corner
2. Search for the client's sub-account name
3. Click to enter that sub-account
4. Verify the name in the top-left now matches the correct client

Always verify the correct sub-account is active before starting any page deployment.


## Step 5: Determine Deployment Target - Websites vs. Funnels

GHL has TWO places to build pages: Websites and Funnels. They use the exact same builder but serve different purposes.

**Use FUNNELS (default - use this 90% of the time):**
- Landing pages, opt-in pages, sales pages, checkout pages, thank you pages
- Any multi-step flow where a visitor moves through pages in order
- Most SuperDesign exports
- When target is not explicitly specified, default to Funnels

**Use WEBSITES (only when explicitly requested):**
- Standalone pages that are NOT part of a flow (like an About page or a blog)
- A full website with navigation between pages
- The user explicitly specifies "Website" not "Funnel"

If the user does not specify which one, default to Funnels.


## Step 6: Prepare for 2FA (Two-Factor Authentication)

Many business GHL accounts have 2FA enabled. After entering email and password, a second verification code is required (usually from a phone app).

The agent must handle 2FA as follows:
- When 2FA is detected, PAUSE and wait for user to complete verification in the browser window
- NEVER attempt to bypass 2FA
- Set headless=False so the user can see and interact with the browser
- Set a generous timeout (at least 5 minutes) because the user may need to find their phone and open an authenticator app
- After the user completes 2FA, the persistent session will remember the approval so it should not ask again for a while


## Step 7: Set Up Helper Functions

The agent needs several helper functions to interact with GHL reliably. These are documented in the ghl-install-pages-full.md file and include:

1. **find_element_with_fallback** - Tries multiple CSS selectors in order. GHL updates their UI frequently, so having backup selectors prevents automation from breaking when a button label changes.

2. **retry_action** - Wraps every action in retry logic. If clicking a button fails the first time, it tries again up to 3 times before giving up.

3. **safe_wait** - Waits for a specific condition to be true instead of using fixed time delays. This is more reliable because GHL pages load at different speeds.

4. **get_builder_frame** - Finds and returns the builder iframe context. GHL's page builder loads inside nested iframes, so the agent needs to switch into the iframe to interact with builder elements.

5. **click_in_builder** - Clicks elements inside the builder iframe with a fallback to the main page.

6. **handle_2fa_if_present** - Detects 2FA screens and pauses for human intervention.

7. **recovery_protocol** - Executes when everything else fails. Takes a screenshot, logs the current state, and determines if re-authentication or a restart is needed.

All functions with complete code are in the ghl-install-pages-full.md file. The agent must read that file and set up these functions before attempting any deployment.


## Step 8: Update Core .md Files

Follow TYP rules - only add summaries and file path references.

**Add to AGENTS.md:**
- GHL page deployment uses Playwright with launchPersistentContext
- Always verify correct sub-account before building
- Default to Funnels unless user specifies Websites
- NEVER publish without explicit user approval
- Always send a deployment report after completing

**Add to TOOLS.md:**
- Full guide location: ~/Downloads/[master-files-folder]/ghl-install-pages-full.md
- Viewport minimum: 1440x900
- Builder loads inside nested iframes - use get_builder_frame() to switch context
- Every selector has fallback chains - use find_element_with_fallback()
- Credential location: ~/clawd/secrets/.env

**Add to MEMORY.md:**
- GHL page deployment skill has been learned
- Reference to the full guide location
