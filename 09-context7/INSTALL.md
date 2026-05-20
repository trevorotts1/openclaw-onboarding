> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.

## 🔴 API-ONLY EXECUTION LOCK (SOVEREIGN)
- For this onboarding package, do NOT use service CLIs for GitHub, Vercel, or Context7.
- Do NOT use `gh`, `vercel`, or any Context7 CLI command for setup/auth.
- Use API-driven setup and browser-based account/token creation flows only.
- The only onboarding skill allowed to rely on CLI-specific service commands is Superdesign.

╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: VERIFY TEACH YOURSELF PROTOCOL (TYP) TRAINING

Agent must verify that TYP has been taught before proceeding.

VERIFICATION PROCESS:
- Search AGENTS.md, TOOLS.md, MEMORY.md for "Teach Yourself Protocol" or "TYP"
- Check session context for prior TYP training documentation
- Search for "Teach Yourself Protocol" tab in this document

IF TYP TRAINING CONFIRMED:
Proceed to agent execution steps below. Follow TYP file storage structure.

IF TYP TRAINING NOT FOUND:
Proceed with caution using default TYP rules:
- Save full documentation to ~/Downloads/OpenClaw Master Files/ (create if needed)
- Add only brief summaries and file path references to core .md files
- Never paste full content into AGENTS.md, TOOLS.md, or MEMORY.md

Optionally inform the user:
  "TYP documentation was not found in my core files. Proceeding with
   standard TYP rules. If you have a TYP document, sharing it will help
   me follow your specific file storage preferences."

Continue to the instructions below regardless of TYP status.

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
   Agent must locate the OpenClaw master files folder. Search for:
   - ~/Downloads/OpenClaw Master Files
   - ~/Downloads/openclaw-master-files
   - ~/Downloads/OpenClaw Master Documents
   - ~/Downloads/openclaw-documents
   - Any variation of "openclaw" + "master" or "files" or "documents"
   Search case-insensitively. If no folder exists, create:
   ~/Downloads/OpenClaw Master Files/

   Agent must save this full document content as a .md file in that folder.

2. DO NOT DUMP FULL CONTENT INTO CORE .MD FILES
   AGENTS.md, TOOLS.md, and MEMORY.md must stay lean.
   Agent must only add brief summaries and file path references to where
   the full documentation lives. Never paste thousands of lines into core files.

3. USE THE LABELED SECTIONS BELOW TO KNOW WHAT GOES WHERE
   Look for sections marked:
   [ADD TO AGENTS.md]
   [ADD TO TOOLS.md]
   [ADD TO MEMORY.md]
   Agent must only add what is labeled. Nothing else goes into core files.

EXECUTION DISCIPLINE - MANDATORY BEFORE AGENT STARTS
╚══════════════════════════════════════════════════════════════╝

These rules apply every single time agent executes instructions from this document.
No exceptions. No shortcuts. No improvising.

RULE 1: READ EVERYTHING BEFORE EXECUTING ANYTHING
Agent must read this entire document from top to bottom before executing a single step.
Agent must not start executing while still reading. Finish reading first. Then start.

RULE 2: DO NOT CHANGE INTENT
These instructions specify exactly what to do. Agent must execute them exactly as written.
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
If agent is unsure whether something should be changed, the answer is NO.
Request clarification from user. Do not guess. Do not assume.

RULE 4: BUILD CHECKLIST BEFORE EXECUTING
Before agent runs a single command or makes a single change, agent must create
a numbered checklist of every action this document requires. Write it out.
Present it to the user before starting. Get confirmation. Then execute.

RULE 5: CHECK AGAINST CHECKLIST WHEN DONE
When agent believes execution is finished, agent must go back to the checklist.
Verify every single item was completed. Check it off explicitly.
If anything was missed, complete it before reporting completion to user.
Do NOT report completion until the checklist is 100% complete.

RULE 6: REPORT WHAT WAS DONE
When finished, agent must give user a clear summary:
- What was completed
- What commands were run
- What files were changed
- Any errors encountered and how they were resolved
- Confirmation that the checklist was fully satisfied

══════════════════════════════════════════════════════════════════

══════════════════════════════════════════════════════════════════
CONTEXT7 SETUP - AGENT EXECUTION GUIDE
══════════════════════════════════════════════════════════════════

Context7 is a service that gives the AI agent access to up-to-date documentation
for software libraries and APIs. Without it, the agent might write code based on
old information that no longer works. With Context7, the agent can check the
latest documentation before writing code, so the code is accurate and current.

══════════════════════════════════════════════════════════════════
AGENT EXECUTION FLOW
══════════════════════════════════════════════════════════════════

STEP 1: CHECK FOR EXISTING CONTEXT7 ACCOUNT AND API KEY

Agent must execute:

1a. Check for existing Context7 API key in this order:
    - Check $CONTEXT7_API_KEY environment variable
    - If not set, read ~/clawd/secrets/.env and look for CONTEXT7_API_KEY
    - If not found there, read ~/.openclaw/.env and look for CONTEXT7_API_KEY
    - If key found in any location and starts with "ctx7sk-": Skip to Step 4 (Verify Key)
    - If key not found anywhere: Proceed to 1b

1b. Request Context7 API key from user:
    - Ask user: "Do you already have a Context7 account and API key?"
    - If user has key (starts with "ctx7sk-"): Proceed to Step 4 (Verify Key)
    - If user does not have account: Proceed to Step 2 (Create Account)
    - If user has account but no key: Proceed to Step 3 (Create API Key)

STEP 2: CREATE CONTEXT7 ACCOUNT (if needed)

Agent must execute:

2a. Open browser to https://context7.com
    - Use browser automation to navigate to Context7 signup page
    - Wait for page to load completely

2b. Detect signup method options:
    - Look for "Continue with GitHub" button
    - Look for "Continue with Email" option
    - Ask user which method they prefer

2c. If user chooses GitHub:
    - Click "Continue with GitHub" button
    - Wait for GitHub authorization flow
    - User must authorize Context7 app in GitHub
    - Wait for redirect back to Context7 dashboard
    - Verify dashboard loads successfully

2d. If user chooses Email:
    - Click "Continue with Email" option
    - Wait for email input field to appear
    - Request email address from user
    - Type email into field
    - STOP - do NOT request or type the password. Instruct user:
      "Please type your password and click Sign Up. I will wait."
    - Wait for user to confirm they have completed signup
    - Wait for verification email prompt
    - Request user to check inbox and click verification link
    - Wait for user to confirm verification complete
    - Instruct user to log in to Context7 (user enters credentials directly)
    - Wait for dashboard to load

2e. Verify Context7 dashboard is visible:
    - Confirm user can see dashboard
    - Proceed to Step 3

STEP 3: CREATE CONTEXT7 API KEY

Agent must execute:

3a. From Context7 dashboard, locate API Keys section:
    - Look for "API Keys" in sidebar menu
    - Look for "Settings" > "API Keys"
    - Look for "Developer" > "API Keys"
    - Click to navigate to API Keys page

3b. Create new API key:
    - Click "Create API Key" or "New Key" button
    - Wait for key creation form to appear
    - Type key name: "OpenClaw Agent"
    - Click "Create" button
    - Wait for key to be generated

3c. Copy API key:
    - Locate generated key (format: ctx7sk-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
    - Copy key to clipboard
    - Request user to save key in secure location
    - Proceed to Step 4

STEP 4: VERIFY API KEY FORMAT AND STORE

Agent must execute:

4a. Verify key format:
    - Confirm key starts with "ctx7sk-"
    - Confirm key matches UUID pattern: ctx7sk-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
      (prefix "ctx7sk-" followed by 8-4-4-4-12 hex character groups, total ~43 characters)
    - If format is incorrect: Request user to verify key and try again

4b. Store API key in environment:
    - Check if secrets.env exists at ~/.openclaw/secrets.env
    - If not: Create file at ~/.openclaw/secrets.env
    - Add line: CONTEXT7_API_KEY=<paste-key-here>
    - Replace <paste-key-here> with actual key
    - Save file
    - Verify file was written successfully

4c. Update AGENTS.md:
    - Open AGENTS.md
    - Locate appropriate section for API integrations
    - Add this section:

    ## Context7 - Real-Time Documentation
    - API Key stored in secrets.env as CONTEXT7_API_KEY
    - ALWAYS use before writing code for external APIs
    - Prevents outdated or incorrect code
    - Key libraries: n8n, GHL, React, Node.js, Python packages

    - Save AGENTS.md

4d. Update TOOLS.md:
    - Open TOOLS.md
    - Locate appropriate section for API tools
    - Add this section:

    ## Context7 - Documentation Lookup
    - API Key: $CONTEXT7_API_KEY (in secrets.env)
    - Use BEFORE coding with any external library
    - Search: GET https://api.context7.com/v1/search?q=<library>
    - Get docs: GET https://api.context7.com/v1/libraries/<id>/context

    - Save TOOLS.md

4e. Update MEMORY.md:
    - Open MEMORY.md
    - Locate appropriate section for API rules
    - Add this section:

    ## Context7 Rule
    Before writing code for ANY external library or API, use Context7
    first. Never rely on training data alone.

    - Save MEMORY.md

STEP 5: VERIFY CONTEXT7 API KEY WORKS (MANDATORY)

Agent must execute this step. Do not skip.

5a. Reload environment so newly written key is available:
    - Run: source ~/clawd/secrets/.env 2>/dev/null || source ~/.openclaw/.env 2>/dev/null || true

5b. Execute verification command:
    - Run: curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY" \
             "https://api.context7.com/v1/search?q=react" | jq '.results[0].name'
    - Wait for response

5c. Verify response:
    - Expected success: Response shows a library name in quotes, e.g. "facebook/react"
      This confirms the key is valid and the API is reachable.
    - If response shows null, empty, or an error object: TROUBLESHOOT before proceeding:
      * Confirm API key was saved correctly to ~/clawd/secrets/.env
      * Confirm key starts with "ctx7sk-"
      * Confirm internet connection is working
      * Re-run source command from 5a and retry verification
      * If still failing, ask user to verify the key is correct in their Context7 dashboard
    - Do NOT proceed to Step 6 until verification passes.

STEP 6: REPORT COMPLETION

Agent must execute:

6a. Create completion checklist:
    [ ] TYP training verified
    [ ] Context7 account created or confirmed existing
    [ ] API key generated (starts with ctx7sk-)
    [ ] API key saved to secrets.env as CONTEXT7_API_KEY
    [ ] AGENTS.md updated with Context7 section
    [ ] TOOLS.md updated with Context7 section
    [ ] MEMORY.md updated with Context7 reminder
    [ ] Verification test passed (MANDATORY - must show library name in response)

6b. Verify all checklist items complete:
    - Go through each item
    - Confirm completion
    - If any item incomplete: Complete it now

6c. Report to user:
    - Provide summary of what was completed
    - List all files that were modified
    - List all commands that were executed
    - Report any errors encountered and how they were resolved
    - Confirm checklist is 100% complete

6d. Final message to user:
    "I've saved your Context7 key. This helps me give you accurate, up-to-date
    code. Whenever you ask me to build something with an external library
    (like n8n, GoHighLevel, React, etc.), I will check the current docs first
    instead of guessing from memory."

══════════════════════════════════════════════════════════════════

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
