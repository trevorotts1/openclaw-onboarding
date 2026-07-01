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
NOTE: TYP is recommended. If not yet installed, continue and revisit TYP
later if needed. You can still safely execute this skill without TYP - just
be mindful not to dump large blocks of content into core .md files. Add only
brief summaries and file path references to AGENTS.md, TOOLS.md, and MEMORY.md.

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

RULE 2: DO NOT CHANGE THE OPERATOR'S INTENT
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
Ask the operator. Do not guess. Do not assume.

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

> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.


This guide covers everything the AI agent needs to have in place BEFORE deploying pages into GoHighLevel (Convert and Flow). This is about getting the tools ready. For the actual step-by-step deployment process, see INSTRUCTIONS.md.

This document assumes the HTML code is already written and ready to go. The agent is setting up the ability to insert that HTML code into GHL's page builder.


## What This Skill Does

This skill enables the AI agent to use browser automation to:
- Access a GoHighLevel / Convert and Flow account via a seeded Firebase refresh-token session (TOKEN-ONLY, D7) — NOT a login form
- Navigate to the page builder
- Create new funnels or website pages
- Paste HTML code into the builder's code block element
- Save, preview, and publish pages
- Update existing pages with new code

**Browser automation tier:** agent-browser (Vercel Labs, Skill 03) is PRIMARY; Playwright is the FALLBACK. Access is always established through the Firebase refresh-token seed path — the builder never renders a login form and never encounters a 2FA prompt under normal operation.


## Prerequisites Verification

The agent must verify ALL of these are in place before proceeding:

1. [ ] Browser automation is available: agent-browser (Vercel Labs, Skill 03) PRIMARY; Playwright FALLBACK — at least one must be installed and working
2. [ ] A valid `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` exists in `~/.openclaw/secrets/.env` (TOKEN-ONLY, D7) — OR a persistent Playwright browser session exists at `~/.openclaw/playwright-data/ghl-install-pages` (Playwright fallback only)
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


## Step 2: Verify Firebase Refresh Token (TOKEN-ONLY, D7)

Access is established via a seeded Firebase refresh-token session. The builder NEVER renders a login form and NEVER sees a 2FA prompt. If the token seed fails, the builder STOPS with a non-zero exit — it does NOT fall back to a login form.

**ALWAYS check for an existing token before prompting the user. Canonical location:**

```bash
# Canonical secrets file (sole authoritative path — ~/clawd/secrets/.env is retired)
grep -E "^GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=" ~/.openclaw/secrets/.env 2>/dev/null
# Live process env (token may already be exported)
printenv | grep "^GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN="
```

**Decision tree:**
- If `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` is found and non-empty: proceed to Step 3.
- If missing or empty: the operator must supply a fresh token (see token recovery below) and add it to `~/.openclaw/secrets/.env` before continuing.
- For Playwright-fallback sessions only: a persistent browser session at `~/.openclaw/playwright-data/ghl-install-pages` may substitute while a token is unavailable — note this in MEMORY.md.

**NEVER prompt for GHL_EMAIL or GHL_PASSWORD. Email/password login is not used by this skill.**

If the token needs to be added, store it in the canonical secrets file:
```bash
# Mac:
mkdir -p ~/.openclaw/secrets && nano ~/.openclaw/secrets/.env
```

Add the following line (replace with the actual token value):
```
GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=<your-token-here>
```

Save and close the file (Ctrl+O, Enter, Ctrl+X). Set permissions: `chmod 600 ~/.openclaw/secrets/.env`.

Load the token in automation scripts:
```python
import os
firebase_token = os.environ.get("GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN")
```

**Token recovery:** If the token is absent, expired, or revoked, re-grab a fresh token using the Convert and Flow Token Grabber Chrome extension (Skill 44 Action 5b), then update `~/.openclaw/secrets/.env` and re-run the seed.


## Step 3: Configure Browser Settings

GHL's page builder requires specific minimum browser window size. If the window is too small, the sidebar collapses, buttons move around, and automation fails.

Required settings:
- Width: 1280 pixels (1440 recommended)
- Height: 800 pixels (900 recommended)

Use this browser launch configuration:

# PERSISTENT SESSION - user logs in once, session saved automatically
# Session stored at: ~/.openclaw/playwright-data/ghl-install-pages/
# To reset and re-login: rm -rf ~/.openclaw/playwright-data/ghl-install-pages/

```python
import os
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir=os.path.expanduser("~/.openclaw/playwright-data/ghl-install-pages"),
        headless=True,   # D6 HEADLESS-ONLY — never open a visible window (dev OR client). NEVER set False.
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
- headless MUST stay True (D6 HEADLESS-ONLY). A visible window is forbidden, dev OR client. First login and two-factor are handled by the headless token-seed path (ghl-browser-builder-full.md §2) — no window is ever opened; a genuinely-blocked two-factor PAUSES + screenshots + surfaces to the operator instead.
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


## Step 6: TOKEN-ONLY Access — No 2FA Path

This skill uses TOKEN-ONLY access (D7). The builder seeds the session from `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` and NEVER navigates to a login form or encounters a 2FA prompt under normal operation.

**If the token seed fails:**
- The builder STOPS immediately with a non-zero exit code and reports: `[ERROR] Firebase token seed failed — exit 1`
- It does NOT open a login form, does NOT prompt for email/password, and does NOT wait for a 2FA code
- The operator must re-grab a fresh token via the Convert and Flow Token Grabber Chrome extension (Skill 44 Action 5b), update `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` in `~/.openclaw/secrets/.env`, and re-run the seed

There is no 2FA handling path to configure because the agent never reaches a 2FA screen.


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
- Credential location: ~/.openclaw/secrets/.env (Mac) | container env vars or ~/.openclaw/secrets/.env (VPS)

**Add to MEMORY.md:**
- GHL page deployment skill has been learned
- Reference to the full guide location

---

## 🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY

**During this installation, you may encounter instructions to restart the OpenClaw gateway.**

**YOU ARE FORBIDDEN from triggering gateway restarts yourself.**

### Correct Process
When a gateway restart is needed:
1. **STOP** - Do NOT execute the restart command
2. **NOTIFY** the user: "This installation requires an OpenClaw gateway restart to complete."
3. **INSTRUCT**: "Type `/restart` in Telegram to trigger it"
4. **WAIT** for user action - do NOT proceed until confirmed

### Forbidden Actions
- Do NOT run `openclaw gateway restart` without explicit user permission
- Do NOT say "I will restart the gateway now" without asking first
- Do NOT assume the user wants the restart

---
