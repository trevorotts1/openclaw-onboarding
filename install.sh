#!/usr/bin/env bash
set -euo pipefail

ONBOARDING_VERSION="v2.4.0"

# ============================================================
#  OpenClaw Onboarding Installer
#  Run via: curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash
# ============================================================

# ----------------------------------------------------------
# Check if onboarding already in progress
# ----------------------------------------------------------
ONBOARDING_DIR="$HOME/.openclaw/onboarding"
mkdir -p "$ONBOARDING_DIR"
INSTALL_FLAG="$ONBOARDING_DIR/.install-in-progress"

if [ -f "$INSTALL_FLAG" ]; then
  echo ""
  echo "============================================"
  echo "   Onboarding already in progress"
  echo "============================================"
  echo ""
  echo "Another installation process is already running."
  echo "If this is incorrect, you can manually remove the flag:"
  echo "  rm $INSTALL_FLAG"
  echo ""
  exit 0
fi

# Create flag file
touch "$INSTALL_FLAG"
trap 'rm -f "$INSTALL_FLAG"' EXIT

echo ""
echo "============================================"
echo "   OpenClaw Onboarding Installer"
echo "   Version: ${ONBOARDING_VERSION}"
echo "============================================"
echo ""

# ----------------------------------------------------------
# Step 1: Check that OpenClaw CLI is installed
# ----------------------------------------------------------
echo "[1/5] Checking for OpenClaw CLI..."
if ! command -v openclaw &>/dev/null; then
  echo ""
  echo "ERROR: OpenClaw CLI not found in PATH."
  echo ""
  echo "Install OpenClaw first:"
  echo "  npm install -g openclaw"
  echo ""
  exit 1
fi
echo "  Found: $(command -v openclaw)"

# ----------------------------------------------------------
# Step 2: Download the onboarding package
# ----------------------------------------------------------
echo ""
echo "[2/5] Downloading 29 skills from GitHub..."
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
echo "[3/5] Extracting to ~/.openclaw/onboarding/..."
rm -rf "$TEMP_EXTRACT"
unzip -qo "$TEMP_ZIP" -d "$TEMP_EXTRACT"
if [ ! -d "$TEMP_EXTRACT/openclaw-onboarding-main" ]; then
  echo "ERROR: Unexpected archive structure."
  rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
  exit 1
fi

# Clear existing onboarding folder and copy fresh
cp -r "$TEMP_EXTRACT/openclaw-onboarding-main/"* "$ONBOARDING_DIR/"
rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
echo "  Installed to $ONBOARDING_DIR"

# Count skills
SKILL_COUNT=$(ls -1 "$ONBOARDING_DIR" | grep -E "^[0-9]+-" | wc -l)
echo "  Skills found: $SKILL_COUNT"

# Record version
SKILLS_DIR="$HOME/.openclaw/skills"
mkdir -p "$SKILLS_DIR"
echo "$ONBOARDING_VERSION" > "$SKILLS_DIR/.onboarding-version"
echo "$ONBOARDING_VERSION" > "$ONBOARDING_DIR/.onboarding-version"
echo "  Version: $ONBOARDING_VERSION"

# ----------------------------------------------------------
# Step 4: Set up backup folder
# ----------------------------------------------------------
echo ""
echo "[4/5] Setting up backup folder..."
DOWNLOADS_DIR="$HOME/Downloads"
BACKUP_DIR=""

# Look for existing backup folder
if [ -d "$DOWNLOADS_DIR" ]; then
  while IFS= read -r dir; do
    dirname_lower=$(basename "$dir" | tr '[:upper:]' '[:lower:]')
    if [[ "$dirname_lower" == *openclaw* ]] && [[ "$dirname_lower" == *backup* ]]; then
      BACKUP_DIR="$dir"
      break
    fi
  done < <(find "$DOWNLOADS_DIR" -maxdepth 1 -type d 2>/dev/null)
fi

# Create if not found
if [ -z "$BACKUP_DIR" ]; then
  BACKUP_DIR="$DOWNLOADS_DIR/OpenClaw Backups"
  mkdir -p "$BACKUP_DIR"
  echo "  Created: $BACKUP_DIR"
else
  echo "  Found: $BACKUP_DIR"
fi

# ----------------------------------------------------------
# Step 5: Write onboarding flag to AGENTS.md
# ----------------------------------------------------------
echo ""
echo "[5/5] Writing onboarding flag..."
WORKSPACE_DIR="$HOME/.openclaw/workspace"
AGENTS_FILE="$WORKSPACE_DIR/AGENTS.md"
mkdir -p "$WORKSPACE_DIR"

# Remove any existing ONBOARDING PENDING flag to avoid duplicates
if [ -f "$AGENTS_FILE" ]; then
  grep -v "ONBOARDING PENDING\|ONBOARDING COMPLETE" "$AGENTS_FILE" > "$AGENTS_FILE.tmp" 2>/dev/null || true
  mv "$AGENTS_FILE.tmp" "$AGENTS_FILE" 2>/dev/null || true
fi

cat >> "$AGENTS_FILE" << 'ONBOARDING_FLAG'

---
🔴🔴🔴 ONBOARDING PENDING - EXECUTE IMMEDIATELY

The OpenClaw onboarding package (29 skills) has been installed to:
  ~/.openclaw/onboarding/

YOUR TASK: Install all 29 skills following the 5-Wave Parallel Orchestration.

STEP 0: CHECK SUB-AGENT CAPABILITY
First, verify you can spawn sub-agents via sessions_spawn:
- Try to spawn a test sub-agent with a simple task
- If successful: Use 5-Wave Parallel Orchestration below
- If failed: Fall back to sequential installation (01→29)

5-WAVE PARALLEL ORCHESTRATION (use if sub-agent spawn works):

WAVE 1: FOUNDATION (Sequential - Main Agent)
Install these 4 skills in order, one at a time:
- 01-teach-yourself-protocol
- 02-back-yourself-up-protocol
- QMD setup (verify qmd is installed)
- 03-agent-browser
Report: "Wave 1 complete: Foundation installed"

WAVE 2: PRE-PERSONA TOOLS (Parallel - 3 Install Agents + 1 QC Agent)
Spawn 3 sub-agents simultaneously, each handling a batch:
- Agent A: 04-superpowers, 05-ghl-setup, 06-ghl-install-pages, 07-kie-setup
- Agent B: 08-vercel-setup, 09-context7, 10-github-setup, 11-superdesign
- Agent C: 12-openrouter-setup, 14-google-workspace-integration, 15-blackceo-team-management, 16-summarize-youtube, 17-self-improving-agent, 18-proactive-agent, 19-humanizer, 20-youtube-watcher, 21-tavily-search
- Agent D (QC): Monitor all Wave 2 skills, verify completion, remediate if needed
Wait for all Wave 2 agents to complete.
Report: "Wave 2 complete: Pre-Persona tools installed"
Note: Skill 13 (Google Workspace Setup) is ARCHIVED - skip it.

WAVE 3: CORE SYSTEM (Sequential - Main Orchestrator ONLY)
These 2 skills MUST be installed by main agent, NEVER sub-agents:
- 22-book-to-persona-coaching-leadership-system
- 23-ai-workforce-blueprint (after 22 completes)
Report: "Wave 3 complete: Core system ready"

WAVE 4: POST-WORKFORCE (Parallel - 2 Install Agents)
Spawn 2 sub-agents simultaneously:
- Agent E: 24-storyboard-writer, 25-video-creator, 26-caption-creator
- Agent F: 27-video-editor, 28-cinematic-forge, 29-ghl-convert-and-flow
Wait for both agents to complete.
Report: "Wave 4 complete: All skills installed"

WAVE 5: FINAL (Sequential - Main Agent)
- Verify Skill 15 (BlackCEO Team Management) is complete
- Run final QMD indexing: qmd update && qmd embed && qmd status
- Remove ONBOARDING PENDING flag from AGENTS.md
- Write ONBOARDING COMPLETE to MEMORY.md
Report: "Wave 5 complete: Onboarding finished"

SKILL INSTALLATION PROTOCOL (for each skill):
1. Read ALL .md files in the skill folder first (SKILL.md, INSTALL.md, etc.)
2. Execute installation steps exactly as written
3. Handle API key prompts autonomously (skip if missing, log reminder)
4. Verify completion before moving to next
5. Report: "Skill XX complete"

ZERO TOLERANCE SHORTCUTS:
- "I'll read that later" = WRONG. Read it NOW.
- "This looks similar to..." = WRONG. Read every file completely.
- "I can skip this step" = WRONG. Follow every step exactly.
- "Close enough" = WRONG. Verify every requirement is met.

FORBIDDEN:
- Do NOT skip skills or say "done" until all 29 are verified complete
- Do NOT change the user's model without permission
- Do NOT trigger gateway restarts without asking
- Do NOT delegate Skills 22-23 to sub-agents (main orchestrator only)

When complete, write ONBOARDING COMPLETE to MEMORY.md and remove this block.
---
ONBOARDING_FLAG

echo "  Onboarding flag written to AGENTS.md"

# ----------------------------------------------------------
# Done
# ----------------------------------------------------------
echo ""
echo "============================================"
echo "  OpenClaw Onboarding Package Ready"
echo "  Version: ${ONBOARDING_VERSION}"
echo "============================================"
echo ""
echo "  📦 29 skills downloaded to:"
echo "     ~/.openclaw/onboarding/"
echo ""
echo "  📋 Next step: Tell your AI agent to begin."
echo ""
echo "     Send this message to your OpenClaw agent:"
echo ""
echo "       'Begin onboarding installation'"
echo ""
echo "  The agent will read AGENTS.md, find the"
echo "  ONBOARDING PENDING flag, and install all"
echo "  29 skills automatically."
echo ""
echo "============================================"
echo ""
