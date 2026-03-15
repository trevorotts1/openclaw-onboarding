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
   The canonical master files folder is: ~/Downloads/openclaw-master-files/
   If that exact path does not exist, check for these common variations:
   - ~/Downloads/OpenClaw Master Files/
   - ~/Downloads/OpenClaw Master Documents/
   Use whichever exists. If none exist, create: ~/Downloads/openclaw-master-files/

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

---

# Install - tavily-search

1. Ensure TYP read pass is complete.
2. Create target folder:
   `mkdir -p ~/.openclaw/skills/tavily-search`
3. Copy upstream files:
   `cp -R ./upstream-original/. ~/.openclaw/skills/tavily-search/`
4. Verify `~/.openclaw/skills/tavily-search/SKILL.md` exists.
5. Apply relevant core file updates from CORE_UPDATES.md only.
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

## 🔴 ERROR RECOVERY - If Install Fails Partway Through

If the installation fails at any step (copy error, permission denied, missing folder, etc.):

1. **STOP** - Do not proceed to the next step
2. **Clean up** the partial install:
   ```bash
   rm -rf ~/.openclaw/skills/tavily-search
   ```
3. **Identify the failure** - read the error message carefully
4. **Fix the root cause** (missing folder, wrong path, permission issue)
5. **Restart from Step 1** - do not resume from a partially installed state
6. **Report to user** if the issue cannot be resolved: "Installation of tavily-search failed at [step]. Error: [message]. Please check [specific thing]."

A partial install is worse than no install — it can cause the agent to find incomplete files and behave incorrectly.
