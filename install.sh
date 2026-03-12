#!/usr/bin/env bash
set -euo pipefail

ONBOARDING_VERSION="v2.2.2"

# ============================================================
#  OpenClaw Onboarding Installer
#  Run via: curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash
# ============================================================

echo ""
echo "============================================"
echo "   OpenClaw Onboarding Installer"
echo "   Version: ${ONBOARDING_VERSION}"
echo "============================================"
echo ""

# ----------------------------------------------------------
# Step 1: Check that OpenClaw CLI is installed
# ----------------------------------------------------------
echo "[1/7] Checking for OpenClaw CLI..."
if ! command -v openclaw &>/dev/null; then
  echo ""
  echo "ERROR: OpenClaw CLI not found in PATH."
  echo ""
  echo "Install OpenClaw first, then re-run this installer:"
  echo "  npm install -g openclaw"
  echo ""
  echo "After installing, run:"
  echo '  curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash'
  exit 1
fi
echo "  Found: $(command -v openclaw)"

# ----------------------------------------------------------
# Step 2: Download the onboarding package from GitHub
# ----------------------------------------------------------
echo ""
echo "[2/7] Downloading onboarding package from GitHub..."
TEMP_ZIP="/tmp/openclaw-onboarding-pkg.zip"
TEMP_EXTRACT="/tmp/openclaw-onboarding-extract"

curl -fsSL "https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip" -o "$TEMP_ZIP"
if [ ! -f "$TEMP_ZIP" ]; then
  echo "ERROR: Failed to download onboarding package."
  exit 1
fi
echo "  Downloaded to $TEMP_ZIP"

# ----------------------------------------------------------
# Step 3: Extract to ~/.openclaw/onboarding/
# ----------------------------------------------------------
echo ""
echo "[3/7] Extracting to ~/.openclaw/onboarding/..."
ONBOARDING_DIR="$HOME/.openclaw/onboarding"
mkdir -p "$ONBOARDING_DIR"

rm -rf "$TEMP_EXTRACT"
unzip -qo "$TEMP_ZIP" -d "$TEMP_EXTRACT"
if [ ! -d "$TEMP_EXTRACT/openclaw-onboarding-main" ]; then
  echo "ERROR: Unexpected archive structure. Expected openclaw-onboarding-main/ inside zip."
  rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
  exit 1
fi

cp -r "$TEMP_EXTRACT/openclaw-onboarding-main/." "$ONBOARDING_DIR/"
rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
echo "  Installed to $ONBOARDING_DIR"

# Record onboarding version for update checks and support
SKILLS_DIR="$HOME/.openclaw/skills"
mkdir -p "$SKILLS_DIR"
echo "$ONBOARDING_VERSION" > "$SKILLS_DIR/.onboarding-version"
echo "$ONBOARDING_VERSION" > "$ONBOARDING_DIR/.onboarding-version"
echo "  Recorded onboarding version: $ONBOARDING_VERSION"

# ----------------------------------------------------------
# Step 4: Find or create the OpenClaw Backups folder
# ----------------------------------------------------------
echo ""
echo "[4/7] Setting up backup folder..."
DOWNLOADS_DIR="$HOME/Downloads"
BACKUP_DIR=""

if [ -d "$DOWNLOADS_DIR" ]; then
  # Search case-insensitively for a folder containing both "openclaw" and "backup"
  while IFS= read -r dir; do
    dirname_lower=$(basename "$dir" | tr '[:upper:]' '[:lower:]')
    if [[ "$dirname_lower" == *openclaw* ]] && [[ "$dirname_lower" == *backup* ]]; then
      BACKUP_DIR="$dir"
      break
    fi
  done < <(find "$DOWNLOADS_DIR" -maxdepth 1 -type d 2>/dev/null)
fi

if [ -z "$BACKUP_DIR" ]; then
  BACKUP_DIR="$DOWNLOADS_DIR/OpenClaw Backups"
  mkdir -p "$BACKUP_DIR"
  echo "  Created: $BACKUP_DIR"
else
  echo "  Found existing: $BACKUP_DIR"
fi
echo "  Backup folder: $BACKUP_DIR"

# ----------------------------------------------------------
# Step 5: Write the onboarding pending flag to AGENTS.md
# ----------------------------------------------------------
echo ""
echo "[5/7] Writing onboarding flag to AGENTS.md..."
WORKSPACE_DIR="$HOME/.openclaw/workspace"
AGENTS_FILE="$WORKSPACE_DIR/AGENTS.md"
mkdir -p "$WORKSPACE_DIR"

if [ -f "$AGENTS_FILE" ] && grep -q "ONBOARDING PENDING" "$AGENTS_FILE" 2>/dev/null; then
  echo "  Onboarding flag already present in AGENTS.md - skipping."
else
  cat >> "$AGENTS_FILE" << 'ONBOARDING_FLAG'

---
🔴🔴🔴 ONBOARDING PENDING - EXECUTE NOW
The OpenClaw onboarding package has been installed.
Read the file at: ~/.openclaw/onboarding/Start Here.md
Execute the complete onboarding sequence immediately. Do not wait for user input.
Install all 29 skills in order. Handle API key prompts autonomously (skip if not present, log reminder).
When complete, remove this block from AGENTS.md and write ONBOARDING COMPLETE to MEMORY.md.

🔴🔴🔴 SKILL INSTALLATION PROTOCOL - MANDATORY FOR EACH SKILL
For EVERY skill folder (01 through 29), you MUST:

ZERO TOLERANCE SHORTCUTS:
- "I'll read that later" = WRONG. Read it NOW.
- "This looks similar to..." = WRONG. Read every file completely.
- "I can skip this step" = WRONG. Follow every step exactly.
- "Close enough" = WRONG. Verify every requirement is met.
- "The user probably wants..." = WRONG. Do not change intent.

STEP 1: TEACH YOURSELF PROTOCOL (TYP) - MANDATORY
Before touching ANYTHING in a skill folder:
1. Announce: "Installing [skill-name]. Activating Teach Yourself Protocol."
2. Find ALL .md files in the skill folder (including subfolders)
3. Read SKILL.md, CORE_UPDATES.md, INSTALL.md, INSTRUCTIONS.md, ALL other .md files
4. VERIFICATION: List every .md file found and confirm you read it

STEP 2: NO ACTION BEFORE COMPREHENSION
Forbidden actions (DO NOT DO THESE):
- Do NOT run install commands before reading ALL docs
- Do NOT assume you know what the skill does based on folder name
- Do NOT skip reading files because they "look similar" to other skills
- Do NOT execute shell commands from SKILL.md until you've read ALL files
- Do NOT say "I understand" without listing what you learned

STEP 3: FOLLOW THE CHECKLIST
Every skill has a specific install sequence. Follow it exactly:
- If INSTALL.md has steps → do them in that order
- If SKILL.md has prerequisites → verify they're met before proceeding
- If CORE_UPDATES.md lists files to update → update ALL of them
- VERIFICATION: After each step, explicitly state "Step X complete"

STEP 4: VERIFY BEFORE CONFIRMING DONE
Before saying a skill is "installed" or "complete":
- [ ] Re-read the skill's success criteria from SKILL.md
- [ ] Verify all files were created/modified as specified
- [ ] Verify all API keys/credentials are properly stored
- [ ] Run any verification commands specified in the skill docs
- [ ] Confirm TYP was applied (core files updated with lightweight summary)
- [ ] Explicitly state: "[Skill-name] installation verified complete"

STEP 5: NO GLOBAL "DONE" UNTIL ALL 29 ARE DONE
- Do NOT say "onboarding complete" after finishing one skill
- Do NOT skip skills because they "seem optional"
- Install skills 01-29 in order, confirm each one individually
- Only after skill 29 is verified complete → remove ONBOARDING PENDING flag

🔴🔴🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY
YOU ARE FORBIDDEN from triggering gateway restarts yourself.
When a gateway restart is needed:
1. STOP - Do NOT execute the restart command
2. NOTIFY the user: "This installation requires an OpenClaw gateway restart to complete."
3. ASK: "Would you like me to trigger the gateway restart for you or would you prefer to initiate it yourself?"
4. WAIT for explicit user confirmation before proceeding
FORBIDDEN: Do NOT run 'openclaw gateway restart' without permission, do NOT say 'I'll restart now' without asking, do NOT assume user wants restart.

🔴🔴🔴 COMPLETE ALL DEPENDENCIES - NO PARTIAL INSTALLS
- If INSTALL.md lists 5 steps → do ALL 5
- If SKILL.md mentions 3 dependencies → install ALL 3
- If there are sub-tasks (A, B, C) → complete ALL sub-tasks
- VERIFICATION: Scan ALL .md files before declaring complete

🔴🔴🔴 OPENROUTER RULE - NEVER CHANGE PRIMARY MODEL
- Install OpenRouter tooling only
- INFORM user: "OpenRouter is installed. Your primary model remains unchanged."
- OFFER to help switch if user asks
- FORBIDDEN: Do NOT change default model, do NOT modify model configs

🔴🔴🔴 MAIN ORCHESTRATOR ONLY - SPECIFIC SKILLS
The following MUST be installed by main orchestrator, NEVER sub-agents:
- 22-book-to-persona-coaching-leadership-system
- 23-ai-workforce-blueprint

🔴🔴🔴 GOOGLE WORKSPACE - SAVE FOR LAST
- Install AFTER skills 01-12, 15-22, 23, 24-29
- Most complex skill, requires user presence for OAuth

🔴🔴🔴 ONBOARDING FLOW PROTECTION - NOTIFY BEFORE QUESTIONS
For AI Workforce Blueprint:
1. Install skill
2. NOTIFY: "The AI Workforce Blueprint has been installed. Let me know when you're ready for me to set up your company's back office, right?"
3. WAIT for user response
4. THEN ask configuration questions

🔴🔴🔴 MASTER FILES FOLDER DISCIPLINE
- Check for existing: ~/Downloads/openclaw-master-files/ or similar
- If found: Use existing, create skill subfolders inside
- If not found: Create ~/Downloads/openclaw-master-files/
- FORBIDDEN: Do NOT create random folders, do NOT duplicate master folders

🔴🔴🔴 CORE.MD FILES - PROTECT AT ALL COSTS
Core files (lightweight summaries ONLY, 10-25 lines):
- AGENTS.md, MEMORY.md, TOOLS.md, USER.md, IDENTITY.md, SOUL.md, HEARTBEAT.md
Deep files (complete content): ~/Downloads/openclaw-master-files/
TYP wins UNLESS skill file explicitly contradicts it → then skill wins

🔴🔴🔴 QMD INDEXING PROTOCOL - STRATEGIC SCHEDULE
Index QMD at these milestones ONLY (not after every skill):
- Initial: After QMD install + TYP + Back Yourself Up (Step 1-3)
- Foundation: After Skills 04-21 complete (before Personas & AI Workforce)
- Personas: After Skill 22 (Book-to-Persona) complete
- AI Workforce: After Skill 23 (AI Workforce Blueprint) complete
- API Layer: After OpenRouter setup complete
- Final: After ALL 29 skills complete
- Ongoing: After any NEW skill installed post-onboarding
Commands: qmd update → qmd embed → qmd status
Collections: clawd, master-files, coaching-personas (after Skill 22)
FORBIDDEN: Do NOT index after every skill, do NOT skip milestone indexing
---
ONBOARDING_FLAG
  echo "  Onboarding flag appended to $AGENTS_FILE"
fi

# ----------------------------------------------------------
# Step 6: Trigger the running OpenClaw agent
# ----------------------------------------------------------
echo ""
echo "[6/7] Triggering OpenClaw agent to begin onboarding..."
TRIGGER_MSG="ONBOARDING INSTALLED - EXECUTE NOW. Read the file at ~/.openclaw/onboarding/Start Here.md and execute the complete onboarding sequence immediately. Install all 29 skills in order. Do not wait for user input. Handle API key prompts autonomously - skip if not present, log a reminder. When complete, remove the ONBOARDING PENDING block from AGENTS.md and write ONBOARDING COMPLETE to MEMORY.md. MANDATORY SKILL INSTALLATION PROTOCOL: For EVERY skill folder (01-29), you MUST: 1) Announce TYP activation, 2) Find and read ALL .md files before ANY action, 3) Follow checklists exactly - complete ALL dependencies and sub-tasks, 4) Verify completion before next skill, 5) Never say 'done' until all 29 verified. ZERO TOLERANCE: 'I'll read later'=WRONG. 'This looks similar'=WRONG. 'I can skip this step'=WRONG. 'Close enough'=WRONG. 'The user probably wants'=WRONG. OPENROUTER RULE: NEVER change user's primary model. Install OpenRouter tooling only, inform user it's ready, offer to help switch if THEY ask. GATEWAY RESTART: NEVER trigger autonomously. STOP, NOTIFY user, ASK permission, WAIT for confirmation. MAIN ORCHESTRATOR ONLY SKILLS: 22-book-to-persona-coaching-leadership-system and 23-ai-workforce-blueprint MUST be installed by main orchestrator, NEVER sub-agents. GOOGLE WORKSPACE: Install LAST (after skills 01-12, 15-22, 23, 24-29). ONBOARDING FLOW: For AI Workforce skill, NOTIFY first 'Installed. Let me know when ready to set up your back office,' WAIT for user response, THEN ask questions. MASTER FILES FOLDER: Check for existing 'openclaw-master-files' or similar first. Use existing if found. Create skill subfolders INSIDE master folder. CORE.MD FILES: AGENTS.md, MEMORY.md, TOOLS.md, USER.md, IDENTITY.md, SOUL.md, HEARTBEAT.md ONLY. Keep lightweight summaries (10-25 lines) with pointers to deep files. TYP wins unless skill file explicitly contradicts it - then skill wins. QMD INDEXING: Index at milestones ONLY - Initial (after QMD+TYP+Backup), Foundation (after Skills 04-21), Personas (after Skill 22), AI Workforce (after Skill 23), API Layer (after OpenRouter), Final (after all 29). Commands: qmd update, qmd embed, qmd status. Do NOT index after every skill."

if openclaw agent --message "$TRIGGER_MSG" --deliver 2>/dev/null; then
  echo "  Agent triggered successfully."
else
  echo "  Note: Could not trigger agent via 'openclaw agent --deliver'."
  echo "  Trying alternative method..."
  if openclaw agent --message "$TRIGGER_MSG" 2>/dev/null; then
    echo "  Agent turn completed (check your messaging channel for delivery)."
  else
    echo "  Warning: Could not trigger agent automatically."
    echo "  The onboarding flag has been written to AGENTS.md."
    echo "  Your agent will pick it up on its next session start."
    echo "  You can also manually tell your agent: 'Read ~/.openclaw/onboarding/Start Here.md and begin onboarding.'"
  fi
fi

# ----------------------------------------------------------
# Step 7: Done
# ----------------------------------------------------------
echo ""
echo "============================================"
echo "  Onboarding triggered."
echo "  Your OpenClaw agent is now installing"
echo "  29 skills autonomously."
echo "  Installer version: ${ONBOARDING_VERSION}"
echo "  Check your configured messaging channel"
echo "  for progress updates."
echo "============================================"
echo ""
