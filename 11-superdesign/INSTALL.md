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
   The canonical master files path is: ~/Downloads/openclaw-master-files/
   If this folder does not exist, create it: mkdir -p ~/Downloads/openclaw-master-files/

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


# SuperDesign - Installation and Setup Guide (Agent-Executable)

This guide contains all steps required for autonomous agent execution to install and configure SuperDesign. The agent executes every step in order without skipping.


## What Is SuperDesign?

SuperDesign is an AI-powered design tool that creates website designs from plain English descriptions. It generates visual layouts and production-ready code. SuperDesign operates in three modes:
- Web App (browser-based visual canvas)
- CLI (terminal-based commands)
- IDE Extension (code editor integration)

This installation covers all three modes.


## Prerequisites - Agent Verification

The agent must verify these prerequisites before proceeding:

1. Operating system: Mac, Windows, or Linux (detect via uname)
2. Google Chrome: Verify installation via which google-chrome or equivalent
3. Node.js version 16+: Execute `node --version` and parse output
4. npm: Execute `npm --version` and verify presence

If any prerequisite fails, halt execution and report missing requirement to user.


## Part 1: Install the SuperDesign Skill for OpenClaw

Agent execution:

1. Execute: `npx clawhub install superdesign`
2. Wait for completion and capture output
3. Verify installation by executing: `ls ~/.agents/skills/superdesign/`
4. Confirm presence of SKILL.md, INIT.md, and SUPERDESIGN.md
5. If verification fails, report error and halt


## Part 2: Install the SuperDesign CLI (Command Line Tool)

Agent execution:

1. Execute: `npm install -g @superdesign/cli@latest`
2. If permission denied error occurs, execute: `sudo npm install -g @superdesign/cli@latest` (may require password input)
3. Verify installation by executing: `superdesign --version`
4. If "command not found" error occurs, attempt: `npx superdesign --version` as fallback
5. Execute: `superdesign login`
6. **STOP AND ASK THE USER:** "A browser window should be opening for you to log into SuperDesign. Please complete the login in the browser, then reply YES here when you are done." **DO NOT proceed to step 7 until the user replies YES.** If the user does not respond within 2 minutes, ask again.
7. After user confirms login success with YES, execute: `superdesign --help`
8. Verify help menu displays without authentication errors
9. If authentication errors occur, report to user and halt


## Part 3: Install the Chrome Extension (For Website Cloning)

Agent execution:

1. Agent opens browser and navigates to: https://chromewebstore.google.com
2. Agent searches for "Superdesign" in the search box
3. Agent locates the official SuperDesign extension and clicks "Add to Chrome"
4. HUMAN ACTION REQUIRED (browser security dialog): Browser displays an "Add extension?" popup. User clicks "Add extension" to confirm. **STOP AND ASK THE USER:** "Please complete this action, then reply YES here when done." **DO NOT proceed until the user replies YES.**
5. Agent verifies the SuperDesign icon appears in the browser toolbar
6. If icon not visible, agent clicks the puzzle piece icon (Extensions menu) and pins SuperDesign
7. Agent confirms extension installation is complete


## Part 4: Set Up the Web App Account

Agent execution:

1. Agent opens browser and navigates to: https://app.superdesign.dev
2. HUMAN ACTION REQUIRED (account creation/auth): User creates account using Google OAuth or email address and completes login. Agent waits until the user confirms login is complete.
3. Agent verifies successful login and workspace visibility by checking page content
4. Agent confirms Web App account setup is complete

Note: Web App provides limited free design credits per week. CLI and IDE Extension can use user's own AI API key for unlimited generation (see Part 6).


## Part 5: Install the Skill Repository (For AI Agent Integration)

Agent execution:

1. Execute: `npx skills add superdesigndev/superdesign-skill`
2. Wait for download completion
3. Verify installation includes CLI command definitions, standard operating procedures, agent rules, and /superdesign slash command
   Expected output: Output confirms skill downloaded and registered, e.g. "Skill superdesign-skill installed successfully" or "Added skill: superdesign-skill". Directory ~/.agents/skills/superdesign/ should exist with SKILL.md and command definition files.
4. If verification fails, report error and halt


## Part 6: Set Up the IDE Extension (Optional - For Code Editor Users)

### Part 6A: Install the Extension

Agent execution:

1. Agent attempts CLI installation first:
   Execute: `code --install-extension superdesigndev.superdesign`
   If "code" command not found, try: `cursor --install-extension superdesigndev.superdesign`
2. If CLI installation succeeds, proceed to Part 6B
3. If CLI installation fails (command not found or error), agent tells user: "Please open your code editor (VS Code, Cursor, or Windsurf), press Cmd+Shift+X (Mac) or Ctrl+Shift+X (Windows/Linux) to open Extensions, search for 'SuperDesign', locate the extension published by 'SuperdesignDev', and click Install." **STOP AND ASK THE USER:** "Please complete this action, then reply YES here when done." **DO NOT proceed until the user replies YES.**
4. Agent verifies installation by executing: `code --list-extensions 2>/dev/null | grep -i superdesign`
5. If verification fails, report error and continue (extension is optional)

### Part 6B: Configure Your AI API Key

Agent execution:

1. Agent checks env files for an existing API key:
   Execute: `grep -rE "ANTHROPIC_API_KEY|OPENAI_API_KEY|OPENROUTER_API_KEY" ~/clawd/secrets/.env 2>/dev/null | head -5`
2. IF a key is found in env: Agent notes the provider (anthropic, openai, or openrouter) and proceeds to step 4
3. IF no key found in env: Agent asks user: "Do you have an Anthropic, OpenAI, or OpenRouter API key to configure the SuperDesign IDE extension? This step is optional - you can skip it and use the Web App or CLI instead."
   - IF user provides key: agent captures the key and provider, proceeds to step 4
   - IF user skips: agent skips steps 4-5, documents that IDE extension API key is not configured, and notes user can configure later via Command Palette
4. HUMAN ACTION REQUIRED (IDE config - requires code editor open): User opens Command Palette (Cmd+Shift+P on Mac, Ctrl+Shift+P on Windows/Linux), types "superdesign: configureApiKey", selects it, and enters the API key. **STOP AND ASK THE USER:** "Please complete this action, then reply YES here when done." **DO NOT proceed until the user replies YES.**
5. HUMAN ACTION REQUIRED (IDE settings): User opens Command Palette again, types "superdesign: openSettings", locates "AI Model Provider" setting, and sets it to "anthropic", "openai", or "openrouter" based on the key provided. **STOP AND ASK THE USER:** "Please complete this action, then reply YES here when done." **DO NOT proceed until the user replies YES.**
6. Agent confirms API key configuration is complete

### Part 6C: Initialize Your Project

Agent execution:

1. HUMAN ACTION REQUIRED (code editor): User opens a project folder in their code editor (or creates a new empty folder). Agent waits until the user confirms the folder is open.
2. HUMAN ACTION REQUIRED (Command Palette): User opens Command Palette (Cmd+Shift+P on Mac, Ctrl+Shift+P on Windows/Linux), types "superdesign: initializeProject", and presses Enter. Agent waits until the user confirms.
3. Agent verifies creation of expected files by executing:
   `ls -la .superdesign/ CLAUDE.md .cursor/rules/design.mdc .windsurfrules 2>/dev/null`
4. If none of the expected files exist: agent tells user "SuperDesign project initialization may not have completed. Please try the Command Palette step again and confirm when done."
5. If files exist: agent confirms project initialization is complete


## Part 7: Create Your First Test Project

Agent execution:

1. Execute: `superdesign create-project --title "MY TEST Page" --json`
2. Capture response and extract Project ID and Draft ID
3. Report Project ID and Draft ID to user for future reference
4. If error occurs, report error details and halt
5. Execute: `superdesign search-prompts --keyword "landing page" --json`
6. Verify JSON results with design prompt suggestions are returned
7. If results returned, confirm CLI is fully working
8. If no results or error, report and halt


## Part 8: Save the Full Documentation

Agent execution:

1. Execute to ensure master files folder exists: `mkdir -p ~/Downloads/openclaw-master-files/superdesign/`
2. Save this complete document as: ~/Downloads/openclaw-master-files/superdesign/superdesign-instructions.md
4. Add to AGENTS.md (lean summary only, no full content):

   ## SuperDesign Web Design Skill [PRIORITY: HIGH]
   SuperDesign (superdesign.dev) is an AI-powered design agent for creating website designs.
   Three modes: Web App (browser, Chrome extension cloning), CLI (terminal commands), IDE Extension.
   Exports: React code, HTML/CSS, style.md (design system document).
   Deep file: ~/Downloads/openclaw-master-files/superdesign/superdesign-instructions.md

5. Add to TOOLS.md (lean summary only, no full content):

   ## SuperDesign [PRIORITY: HIGH]
   Design agent for websites and UI. Three modes: Web App, CLI, IDE Extension.
   CLI install: npm install -g @superdesign/cli@latest
   Skill install: npx clawhub install superdesign
   Key commands: superdesign create-project, superdesign iterate-design-draft, superdesign extract-brand-guide
   Deep file: ~/Downloads/openclaw-master-files/superdesign/superdesign-instructions.md

6. Verify both AGENTS.md and TOOLS.md were updated successfully


## Installation Complete - Execution Summary

Agent execution:

1. Verify all 8 parts completed successfully
2. Confirm all prerequisite checks passed
3. Confirm all CLI installations executed without errors
4. Confirm all user-facing steps (Chrome Extension, Web App, IDE Extension) were instructed to user
5. Confirm test project creation succeeded with Project ID and Draft ID captured
6. Confirm documentation saved to master files folder
7. Confirm AGENTS.md and TOOLS.md updated with lean summaries and file path references
8. Report completion status to user with summary of all actions taken

SuperDesign is now fully installed and configured. Agent has access to:
- OpenClaw skill (agent knowledge of SuperDesign)
- CLI tool (terminal command execution)
- Chrome Extension (website cloning capability)
- Web App account (visual canvas access)
- Skill Repository (full command library)
- IDE Extension (optional - unlimited generation in code editor)

For usage instructions, see INSTRUCTIONS.md
For examples, see EXAMPLES.md
For complete reference, see superdesign-full.md

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
