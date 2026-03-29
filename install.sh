#!/usr/bin/env bash
set -euo pipefail

ONBOARDING_VERSION="v6.0.7"

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
echo "[2/5] Downloading 34 skills from GitHub..."
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
# Step 3b: Copy Gemini Engine scripts (indexing runs after Skill 22)
# ----------------------------------------------------------
echo ""
echo "[3b/5] Installing Gemini Engine scripts..."
# Determine the agent's workspace directory
# Standard OpenClaw workspace: ~/.openclaw/workspace
WORKSPACE_DIR="$HOME/.openclaw/workspace"
mkdir -p "$WORKSPACE_DIR"
SCRIPTS_DIR="$WORKSPACE_DIR/scripts"
mkdir -p "$SCRIPTS_DIR"

# Copy gemini-indexer.py to the expected location
if [ -f "$ONBOARDING_DIR/scripts/gemini-indexer.py" ]; then
  cp "$ONBOARDING_DIR/scripts/gemini-indexer.py" "$SCRIPTS_DIR/gemini-indexer.py"
  chmod +x "$SCRIPTS_DIR/gemini-indexer.py"
  echo "  Copied gemini-indexer.py to $SCRIPTS_DIR/"
else
  echo "  gemini-indexer.py not found in onboarding scripts (will need manual setup)"
fi

# Install google-genai Python package if not present
if ! python3 -c "import google.genai" 2>/dev/null; then
  echo "  Installing google-genai Python package..."
  pip3 install google-genai --break-system-packages 2>/dev/null || \
  pip3 install google-genai 2>/dev/null || \
  echo "  Warning: google-genai install failed. You may need to install it manually: pip3 install google-genai"
else
  echo "  google-genai already installed"
fi

# Check for GOOGLE_API_KEY
if grep -q "GOOGLE_API_KEY" ~/.openclaw/.env ~/.openclaw/secrets/.env 2>/dev/null; then
  echo "  Google API key found"
else
  echo "  Warning: No Google API key found. Add GOOGLE_API_KEY to ~/.openclaw/.env before running Gemini Engine indexing."
fi

# ----------------------------------------------------------
# Step 3b.2: Add Cloudflare Tunnel Token for Command Center
# ----------------------------------------------------------
echo ""
echo "[3b.2/5] Checking Cloudflare tunnel token..."
CF_TOKEN="cfut_k7fGeMtROSYqgbsYCKvtCxqNNZDrEEMW1ncQKUd3678b4d5d"
ENV_FILE="$HOME/.openclaw/.env"
if grep -q "CLOUDFLARE_TUNNEL_TOKEN" "$ENV_FILE" 2>/dev/null; then
  echo "  Cloudflare tunnel token already set"
else
  echo "CLOUDFLARE_TUNNEL_TOKEN=$CF_TOKEN" >> "$ENV_FILE"
  echo "  Added Cloudflare tunnel token to $ENV_FILE"
fi


echo "  Gemini Engine scripts installed (indexing runs after Skill 22 adds books)"

# ----------------------------------------------------------
# Step 3c: Set sub-agent concurrency defaults
# ----------------------------------------------------------
echo ""
echo "[3c/5] Configuring sub-agent concurrency..."
OPENCLAW_JSON="$HOME/.openclaw/openclaw.json"

if [ -f "$OPENCLAW_JSON" ]; then
  # Backup first
  cp "$OPENCLAW_JSON" "$HOME/Downloads/openclaw-backups/openclaw-json-backup-$(date '+%Y-%m-%d-%I%M%p').json" 2>/dev/null || true

  # Use Python to safely update JSON (jq may not be installed)
  python3 -c "
import json, os, sys
path = os.path.expanduser('$OPENCLAW_JSON')
try:
    with open(path) as f:
        config = json.load(f)

    # CLEANUP: Remove misplaced keys from top-level 'models'
    # The 'models' key only accepts: mode, providers, bedrockDiscovery
    # If subagents/allow/other keys ended up here by mistake, remove them
    models_root = config.get('models', {})
    if isinstance(models_root, dict):
        bad_keys = [k for k in models_root if k not in ('mode', 'providers', 'bedrockDiscovery')]
        for bk in bad_keys:
            del models_root[bk]
            print(f'  Cleaned up misplaced key from models: {bk}')
        if models_root:
            config['models'] = models_root
        elif 'models' in config and not models_root:
            pass  # leave empty models dict alone

    agents = config.get('agents', {})
    defaults = agents.get('defaults', {})

    # Sub-agent concurrency
    sub = defaults.get('subagents', {})
    sub['maxSpawnDepth'] = 4
    sub['maxConcurrent'] = 20
    sub['maxChildrenPerAgent'] = 20
    defaults['subagents'] = sub

    # Model allow list (core models for sub-agents)
    models = defaults.get('models', {})
    model_defs = {
        'moonshot/kimi-k2.5': {'alias': 'kimi'},
        'openrouter/moonshot/kimi-k2.5': {'alias': 'kimi-or', 'params': {'contextWindow': 262144, 'maxTokens': 65536}},
        'openrouter/xiaomi/mimo-v2-pro': {'alias': 'mimo', 'params': {'contextWindow': 1048576, 'maxTokens': 131072}},
        'openrouter/xiaomi/mimo-v2-omni': {'alias': 'mimo-omni', 'params': {'contextWindow': 262144, 'maxTokens': 65536}},
        'openrouter/minimax/minimax-m2.7': {'alias': 'minimax', 'params': {'contextWindow': 204800, 'maxTokens': 131072}},
        'openrouter/google/gemini-3.1-flash-lite-preview': {'alias': 'gemini-flash', 'params': {'contextWindow': 1048576, 'maxTokens': 65536}},
        'openrouter/google/gemini-3-flash-preview': {'alias': 'gemini-flash-3', 'params': {'contextWindow': 1048576, 'maxTokens': 65536}},
        'openai-codex/gpt-5.4': {'params': {'contextWindow': 1048576, 'maxTokens': 65536}},
    }
    for mid, mdef in model_defs.items():
        if mid not in models:
            models[mid] = mdef
    defaults['models'] = models

    agents['defaults'] = defaults
    config['agents'] = agents
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)
    print('  Set sub-agent concurrency and 8 model allow-list entries')
except Exception as e:
    print(f'  Warning: Could not update openclaw.json: {e}', file=sys.stderr)
" 2>&1
else
  echo "  Warning: openclaw.json not found at $OPENCLAW_JSON"
fi

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

# Create master-files folder (Skills 22/23 expect this)
MASTER_FILES_DIR="$DOWNLOADS_DIR/openclaw-master-files"
mkdir -p "$MASTER_FILES_DIR"
mkdir -p "$MASTER_FILES_DIR/coaching-personas/personas"
mkdir -p "$MASTER_FILES_DIR/project-prds"
echo "  Created: $MASTER_FILES_DIR"
echo "  Created: $MASTER_FILES_DIR/coaching-personas/personas"
echo "  Created: $MASTER_FILES_DIR/project-prds"

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

The OpenClaw onboarding package (34 skills) has been installed to:
  ~/.openclaw/onboarding/

READ THIS FILE FIRST: ~/.openclaw/onboarding/Start Here.md

It contains the complete execution checklist, wave instructions, and failure handling.

SUMMARY:
- Install 34 skills using 5-Wave Parallel Orchestration
- Use parallel sub-agents for Waves 2 and 4 (if sessions_spawn works)
- Use sequential mode for Waves 1, 3, 5
- Skip skills 13, 33, 34 (archived)
- Skills 22-23: Main orchestrator ONLY (no sub-agents)
- Track progress in ~/.openclaw/onboarding/.onboarding-status
- Remove this flag and write ONBOARDING COMPLETE to MEMORY.md when done

DO NOT:
- Skip reading Start Here.md
- Skip skills or say "done" until all 34 complete
- Delegate skills 22-23 to sub-agents
- Trigger gateway restarts without asking

ZERO TOLERANCE SHORTCUTS:
- "I'll read that later" = WRONG. Read it NOW.
- "This looks similar to..." = WRONG. Read every file completely.
- "I can skip this step" = WRONG. Follow every step exactly.
---
ONBOARDING_FLAG

echo "  Onboarding flag written to: $AGENTS_FILE"

# ----------------------------------------------------------
# Done
# ----------------------------------------------------------
echo ""
echo "============================================"
echo "  OpenClaw Onboarding Package Ready"
echo "  Version: ${ONBOARDING_VERSION}"
echo "============================================"
echo ""
echo "  📦 34 skills downloaded to:"
echo "     ~/.openclaw/onboarding/"
echo ""
echo "  📋 ONBOARDING FLAG LOCATION:"
echo "     $AGENTS_FILE"
echo ""
echo "  📋 Next step: Tell your AI agent to begin."
echo ""
echo "     Send this EXACT message to your OpenClaw agent:"
echo ""
echo "       'Read $AGENTS_FILE and begin onboarding installation'"
echo ""
echo "  The agent will read AGENTS.md, find the"
echo "  ONBOARDING PENDING flag, and install all"
echo "  34 skills automatically."
echo ""
echo "  ⚠️  If the agent says it cannot find the flag,"
echo "     tell it to run:"
echo "     grep -r 'ONBOARDING PENDING' $AGENTS_FILE"
echo ""
echo "============================================"
echo ""
