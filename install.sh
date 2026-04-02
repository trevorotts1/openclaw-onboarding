#!/usr/bin/env bash
set -euo pipefail

ONBOARDING_VERSION="v6.5.17"

# ============================================================
#  OpenClaw Onboarding Installer (IMPROVED)
#  Run via: curl -fSL --progress-bar https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash
# ============================================================

# ----------------------------------------------------------
# Telegram progress notification function
# ----------------------------------------------------------
send_telegram_progress() {
    local message="$1"
    local OCJSON="$HOME/.openclaw/openclaw.json"
    local TELEGRAM_TARGET=""

    # Try to read the first allowFrom ID from openclaw.json
    if [ -f "$OCJSON" ] && command -v python3 &>/dev/null; then
        TELEGRAM_TARGET=$(python3 -c "
import json, sys
try:
    cfg = json.load(open('$OCJSON'))
    allow = cfg.get('channels', {}).get('telegram', {}).get('allowFrom', [])
    if allow:
        print(allow[0])
except:
    pass
" 2>/dev/null)
    fi

    if command -v openclaw &>/dev/null && [ -n "$TELEGRAM_TARGET" ]; then
        openclaw message send --channel telegram --target "$TELEGRAM_TARGET" --message "$message" 2>/dev/null \
            || echo "[TELEGRAM FALLBACK] $message"
    elif command -v openclaw &>/dev/null; then
        openclaw message send --message "$message" 2>/dev/null \
            || echo "[TELEGRAM FALLBACK] $message"
    else
        echo "[TELEGRAM FALLBACK] $message"
    fi
}

# ----------------------------------------------------------
# Simple spinner for long-running operations
# ----------------------------------------------------------
show_status() {
    local message="$1"
    echo ""
    echo "  >>> $message"
    echo ""
}

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

# ============================================================
# CONFIG EDIT PROTOCOL — MANDATORY (Trevor standing rule)
# Before ANY edit to openclaw.json or exec-approvals.json:
#   1. Call backup_config_file to create timestamped backup
#   2. Verify schema against docs.openclaw.ai for that section
#   3. Only then apply the change
# Official docs: https://docs.openclaw.ai
# ============================================================
backup_config_file() {
  local file="$1"
  if [ -f "$file" ]; then
    local ts
    ts=$(date +%Y%m%d-%H%M%S)
    local backup="${file}.bak-${ts}"
    cp "$file" "$backup"
    echo "  📦 Backed up: $backup"
  fi
}

echo ""
echo "============================================"
echo "   OpenClaw Onboarding Installer"
echo "   Version: ${ONBOARDING_VERSION}"
echo "============================================"
echo ""

send_telegram_progress "Starting BlackCEO Command Center install..."

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
  send_telegram_progress "ERROR: OpenClaw CLI not found. Install failed."
  exit 1
fi
echo "  Found: $(command -v openclaw)"

# ----------------------------------------------------------
# Step 2: Download the onboarding package
# ----------------------------------------------------------
show_status "Downloading 34 skills package... (this may take 1-2 minutes)"

echo "[2/5] Downloading 34 skills from GitHub..."
TEMP_ZIP="/tmp/openclaw-onboarding-pkg.zip"
TEMP_EXTRACT="/tmp/openclaw-onboarding-extract"

# NOT silent - users see the download progress bar
curl -fSL --progress-bar "https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip" -o "$TEMP_ZIP"
if [ ! -f "$TEMP_ZIP" ]; then
  echo "ERROR: Failed to download onboarding package."
  send_telegram_progress "ERROR: Download failed. Install aborted."
  exit 1
fi
echo "  Downloaded to $TEMP_ZIP"

send_telegram_progress "Downloaded 34 skills package"

# ----------------------------------------------------------
# Step 3: Extract to ~/.openclaw/onboarding/
# ----------------------------------------------------------
show_status "Extracting skills package..."

echo "[3/5] Extracting to ~/.openclaw/onboarding/..."
rm -rf "$TEMP_EXTRACT"
unzip -qo "$TEMP_ZIP" -d "$TEMP_EXTRACT"
if [ ! -d "$TEMP_EXTRACT/openclaw-onboarding-main" ]; then
  echo "ERROR: Unexpected archive structure."
  rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
  send_telegram_progress "ERROR: Extract failed. Archive structure unexpected."
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

send_telegram_progress "Extracted skills to your OpenClaw ($SKILL_COUNT skills found)"

# ----------------------------------------------------------
# Step 3b: Copy Gemini Engine scripts (indexing runs after Skill 22)
# ----------------------------------------------------------
show_status "Installing Gemini Engine scripts..."

echo "[3b/5] Installing Gemini Engine scripts..."
# Scripts go to ~/clawd/scripts/ — this is where ALL skills expect them
SCRIPTS_DIR="$HOME/clawd/scripts"
mkdir -p "$SCRIPTS_DIR"

# Copy gemini-indexer.py to the expected location
if [ -f "$ONBOARDING_DIR/scripts/gemini-indexer.py" ]; then
  cp "$ONBOARDING_DIR/scripts/gemini-indexer.py" "$SCRIPTS_DIR/gemini-indexer.py"
  chmod +x "$SCRIPTS_DIR/gemini-indexer.py"
  echo "  Copied gemini-indexer.py to $SCRIPTS_DIR/"
else
  echo "  gemini-indexer.py not found in onboarding scripts (will need manual setup)"
fi

# Copy gemini-search.py to the expected location
if [ -f "$ONBOARDING_DIR/scripts/gemini-search.py" ]; then
  cp "$ONBOARDING_DIR/scripts/gemini-search.py" "$SCRIPTS_DIR/gemini-search.py"
  chmod +x "$SCRIPTS_DIR/gemini-search.py"
  echo "  Copied gemini-search.py to $SCRIPTS_DIR/"
else
  echo "  gemini-search.py not found in onboarding scripts (will need manual setup)"
fi

# Install google-genai Python package if not present
if ! python3 -c "import google.genai" 2>/dev/null; then
  show_status "Installing google-genai Python package... (this may take 1-2 minutes)"
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
ENV_FILE="$HOME/.openclaw/.env"
if grep -q "CLOUDFLARE_TUNNEL_TOKEN" "$ENV_FILE" 2>/dev/null; then
  echo "  Cloudflare tunnel token already set"
else
  echo "  No Cloudflare tunnel token found."
  echo "  To add one: echo 'CLOUDFLARE_TUNNEL_TOKEN=your-token-here' >> $ENV_FILE"
fi


echo "  Gemini Engine scripts installed (indexing runs after Skill 22 adds books)"

send_telegram_progress "Installed Gemini Engine scripts"

# ----------------------------------------------------------
# Step 3c: Set sub-agent concurrency defaults
# ----------------------------------------------------------
show_status "Configuring sub-agent concurrency and models..."

echo "[3c/5] Configuring sub-agent concurrency..."
OPENCLAW_JSON="$HOME/.openclaw/openclaw.json"

if [ -f "$OPENCLAW_JSON" ]; then
  # BACKUP BEFORE EDIT — per Trevor standing rule
  # Verify schema at: https://docs.openclaw.ai/config
  backup_config_file "$HOME/.openclaw/openclaw.json"

  # Use Python to safely update JSON (jq may not be installed)
  python3 -c "
# ⚠️  SCHEMA VERIFICATION REQUIRED BEFORE EDITING THIS BLOCK
# Check docs.openclaw.ai for current field names and valid values
# Do NOT rely solely on this script — OpenClaw updates may change the schema
# Backup is created automatically by backup_config_file() above
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

    # NEVER overwrite client's existing primary model
    # Only set sub-agent primary if no sub-agent model config exists yet
    # Explicit sessions_spawn(model=...) always overrides this
    existing_primary = sub.get('model', {}).get('primary')
    if existing_primary:
        print(f'  Preserving existing primary model: {existing_primary}')
    else:
        sub['model'] = {'primary': 'openrouter/google/gemini-3.1-flash-lite-preview'}
        print('  Set default sub-agent primary model: openrouter/google/gemini-3.1-flash-lite-preview')

    defaults['subagents'] = sub

    # Model allow list (core models for sub-agents)
    # This is the SUB-AGENT allow list — any model NOT in this list
    # cannot be used by sub-agents. It must include ALL models the client has.
    models = defaults.get('models', {})

    # Sync ALL model references from the client's config to the allow list
    # This ensures models added manually by the client are available to sub-agents
    def find_model_refs(obj):
        refs = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == 'model' and isinstance(v, str) and ('/' in v or ':' in v):
                    # Skip embedder/search models (not chat models)
                    if not any(x in v.lower() for x in ['embedding', 'rerank']):
                        refs.add(v)
                else:
                    refs.update(find_model_refs(v))
        elif isinstance(obj, list):
            for item in obj:
                refs.update(find_model_refs(item))
        return refs

    all_config_models = find_model_refs(config)
    added_from_config = 0
    for m in all_config_models:
        if m not in models:
            models[m] = {}
            added_from_config += 1
    if added_from_config > 0:
        print(f'  Synced {added_from_config} models from client config to sub-agent allow list')

    # Ensure core models are always present
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

    # Remove Perplexity models — OpenClaw no longer supports Perplexity as a model
    perplexity_keys = [k for k in models if 'perplexity' in k.lower() or 'sonar' in k.lower()]
    for pk in perplexity_keys:
        del models[pk]
        print(f'  Removed deprecated model: {pk}')

    defaults['models'] = models

    agents['defaults'] = defaults
    config['agents'] = agents

    # Exec security — verified against docs.openclaw.ai/tools/exec-approvals
    # Re-verify this section if OpenClaw version is bumped
    # Allows agent to run shell commands without per-command approval prompts
    
    config.setdefault('tools', {})['exec'] = {
        'security': 'full',
        'ask': 'off'
    }
    print('  Set tools.exec: security=full, ask=off (no approval wall)')

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
# Write exec-approvals.json — disable approval wall for autonomous operation
# ----------------------------------------------------------
EXEC_APPROVALS="$HOME/.openclaw/exec-approvals.json"

# BACKUP BEFORE EDIT — per Trevor standing rule
# Verify schema at: https://docs.openclaw.ai/tools/exec-approvals
backup_config_file "$HOME/.openclaw/exec-approvals.json"

if [ -f "$EXEC_APPROVALS" ]; then
  python3 - "$EXEC_APPROVALS" << 'PYEOF'
# ⚠️  SCHEMA VERIFICATION REQUIRED BEFORE EDITING THIS BLOCK
# Check docs.openclaw.ai for current field names and valid values
# Do NOT rely solely on this script — OpenClaw updates may change the schema
# Backup is created automatically by backup_config_file() above
import json, sys
p = sys.argv[1]
cfg = json.load(open(p))
cfg.setdefault('defaults', {}).update({
    'security': 'full',
    'ask': 'off',
    'askFallback': 'full',
    'autoAllowSkills': True
})
json.dump(cfg, open(p, 'w'), indent=2)
print('  exec-approvals.json: security=full, ask=off, askFallback=full')
PYEOF
else
  echo "  exec-approvals.json not found yet (will apply on next run after gateway init)"
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
show_status "Writing onboarding flag to your agent workspace..."

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

CRITICAL WAVE ORDERING RULE:
- Skill 12 (openrouter-setup) MUST be installed FIRST, before any other skill
- Wave 1 must always start with Skill 12 as the very first skill
- Reason: Other skills spawn sub-agents that require OpenRouter to be configured first
- If Skill 12 is skipped or delayed, sub-agent spawning will fail across all subsequent skills

MIMO V2 PRO THINKING LEVELS:
- Main agent (you): thinkingDefault is medium -- this is correct, do not change it
- Sub-agents you spawn: ALWAYS pass thinking: "high" explicitly in sessions_spawn()
- Never rely on default thinking for sub-agents -- always set it explicitly

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
# Apply exec security config (runs on BOTH fresh install AND update)
# ----------------------------------------------------------
apply_exec_security_config() {
  echo ""
  echo "[6/5] Applying exec security configuration..."

  # Patch openclaw.json tools.exec settings
  python3 << 'PYEOF'
# Exec security — verified against docs.openclaw.ai/tools/exec-approvals
# Re-verify this section if OpenClaw version is bumped
# Runs on BOTH fresh install and update — always applied
import json, os
cfg_path = os.path.expanduser("~/.openclaw/openclaw.json")
if os.path.exists(cfg_path):
    cfg = json.load(open(cfg_path))
    cfg.setdefault('tools', {})['exec'] = {
        'security': 'full',
        'ask': 'off'
    }
    json.dump(cfg, open(cfg_path, 'w'), indent=2)
    print('  ✅ tools.exec: security=full, ask=off')
else:
    print('  ⚠️  openclaw.json not found yet — exec security will be set on next run')
PYEOF

  # Patch exec-approvals.json if it exists
  EXEC_APPROVALS="$HOME/.openclaw/exec-approvals.json"
  if [ -f "$EXEC_APPROVALS" ]; then
    python3 - "$EXEC_APPROVALS" << 'PYEOF'
import json, sys
p = sys.argv[1]
cfg = json.load(open(p))
cfg.setdefault('defaults', {}).update({
    'security': 'full',
    'ask': 'off',
    'askFallback': 'full',
    'autoAllowSkills': True
})
json.dump(cfg, open(p, 'w'), indent=2)
print('  ✅ exec-approvals.json patched')
PYEOF
  else
    echo "  ℹ️  exec-approvals.json not found yet — will apply on next run after gateway init"
  fi
}

apply_exec_security_config

# ----------------------------------------------------------
# Done
# ----------------------------------------------------------
send_telegram_progress "✅ BlackCEO AI System install complete!

IMPORTANT -- Do these 2 steps now:

1️⃣ Restart your AI: type /restart in this chat
2️⃣ After restart, send: 'Read your AGENTS.md and begin onboarding installation'

Your AI will then install all 34 skills automatically. This takes 10-20 minutes."

echo ""
echo "============================================"
echo "  OpenClaw Onboarding Package Ready"
echo "  Version: ${ONBOARDING_VERSION}"
echo "============================================"
echo ""
echo "  📦 34 skills downloaded to:"
echo "     ~/.openclaw/onboarding/"
echo ""
echo "  ============================================"
echo "  🔴 STEP 1 -- RESTART THE GATEWAY NOW"
echo "  ============================================"
echo "  Run this command:"
echo ""
echo "     openclaw gateway restart"
echo ""
echo "  Or tell your AI in Telegram: /restart"
echo ""
echo "  WHY: The agent needs to restart to read"
echo "  the new ONBOARDING PENDING flag in AGENTS.md."
echo "  Without restart, it may take 30 minutes."
echo ""
echo "  ============================================"
echo "  🔴 STEP 2 -- AFTER RESTART, SEND THIS MESSAGE"
echo "  ============================================"
echo "  Send this EXACT message to your OpenClaw agent:"
echo ""
echo "     'Read $AGENTS_FILE and begin onboarding installation'"
echo ""
echo "  ============================================"
echo ""
