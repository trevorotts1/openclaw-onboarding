#!/bin/bash
# BlackCEO System - Safe Update Script v8.8.0
# Install Experience Overhaul - Clean UI, 5-Phase Processing, Smart Credentials
#
# Download latest, compare versions, back up config, apply updates,
# notify via Telegram, write UPDATE PENDING flag for the agent.

set -euo pipefail

# ── CONFIGURATION ──
REPO_URL="https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip"
REPO_FOLDER="openclaw-onboarding-main"
BACKUP_BASE="$HOME/Downloads/openclaw-backups"

# Redirect all technical noise to log file
LOG_FILE="/tmp/blackceo-update-$$.log"
exec 3>&1 4>&2
trap 'exec 1>&3 2>&4' EXIT
exec 1>>"$LOG_FILE" 2>&1

# ── UI HELPERS ──
# All UI output goes to the original stdout (>&3)
step_counter=0
show_step() {
    step_counter=$((step_counter + 1))
    echo "[$step_counter/6] $1" >&3
}

show_success() {
    echo "  ✓ $1" >&3
}

show_info() {
    echo "  ℹ $1" >&3
}

show_error() {
    echo "  ✗ $1" >&3
}

# ── Discover where skills are actually installed ──
discover_skills_dir() {
  CANDIDATES=(
    "$HOME/Downloads/openclaw-master-files"
    "$HOME/.openclaw/skills"
    "$HOME/.openclaw/onboarding"
    "$HOME/openclaw-onboarding"
  )
  
  for DIR in "${CANDIDATES[@]}"; do
    if [ -d "$DIR" ]; then
      SKILL_COUNT=$(ls -d "$DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
      if [ "$SKILL_COUNT" -gt "0" ]; then
        echo "$DIR"
        return
      fi
    fi
  done
  
  echo "$HOME/Downloads/openclaw-master-files"
}

SKILLS_DIR=$(discover_skills_dir)
STAGE_DIR="/tmp/blackceo-update-$$"
STAGE_ZIP="/tmp/blackceo-update-$$.zip"
OPENCLAW_CONFIG="$HOME/.openclaw/openclaw.json"
WORKSPACE_ROOT="$HOME/clawd"
[ ! -d "$WORKSPACE_ROOT" ] && WORKSPACE_ROOT="$HOME/.openclaw/workspace"
AGENTS_FILE="$WORKSPACE_ROOT/AGENTS.md"

echo "" >&3
echo "============================================" >&3
echo " BlackCEO System - Update Check" >&3
echo "============================================" >&3
echo "" >&3

# ── STEP 1: Current version ──
show_step "Checking current version..."
mkdir -p "$SKILLS_DIR"
LOCAL_VER="none"
if [ -f "$SKILLS_DIR/.onboarding-version" ]; then
 LOCAL_VER=$(cat "$SKILLS_DIR/.onboarding-version" | tr -d '[:space:]')
fi
show_info "Installed: $LOCAL_VER"

# ── STEP 2: Download latest ──
show_step "Downloading latest from GitHub..."
rm -rf "$STAGE_DIR" "$STAGE_ZIP"
curl -fsSL "$REPO_URL" -o "$STAGE_ZIP" 2>/dev/null
if [ ! -f "$STAGE_ZIP" ]; then
 show_error "Download failed. Check internet."
 exit 1
fi
unzip -qo "$STAGE_ZIP" -d "$STAGE_DIR"
REPO_DIR="$STAGE_DIR/$REPO_FOLDER"
if [ ! -d "$REPO_DIR" ]; then
 show_error "Unexpected archive structure."
 rm -rf "$STAGE_DIR" "$STAGE_ZIP"
 exit 1
fi

REMOTE_VER="unknown"
if [ -f "$REPO_DIR/version" ]; then
 REMOTE_VER=$(cat "$REPO_DIR/version" | tr -d '[:space:]')
fi
show_info "Latest: $REMOTE_VER"

# ── STEP 3: Compare versions ──
show_step "Comparing versions..."
if [ "$LOCAL_VER" = "$REMOTE_VER" ]; then
 echo "" >&3
 show_success "Already up to date ($LOCAL_VER). Nothing to do."
 rm -rf "$STAGE_DIR" "$STAGE_ZIP"
 exit 0
fi

echo "" >&3
echo "Update available: $LOCAL_VER -> $REMOTE_VER" >&3
echo ""

# ── STEP 4: Per-skill comparison ──
show_step "Analyzing skill changes..."

# Parallel arrays for skill tracking (bash 3.2 compatible)
SKILL_NAMES=()
SKILL_ACTIONS=()
SKOLD_VERSIONS=()
SKNEW_VERSIONS=()

NEW_COUNT=0
UPDATE_COUNT=0
SKIP_COUNT=0

for SKILL_PATH in "$REPO_DIR"/[0-9]*/; do
 [ -d "$SKILL_PATH" ] || continue
 SNAME=$(basename "$SKILL_PATH")
 case "$SNAME" in *ARCHIVED*) continue ;; esac

 STAGED_V="unknown"
 LOCAL_V="none"
 [ -f "$SKILL_PATH/skill-version.txt" ] && STAGED_V=$(cat "$SKILL_PATH/skill-version.txt" | tr -d '[:space:]' | cut -d'#' -f1)
 [ -f "$SKILLS_DIR/$SNAME/skill-version.txt" ] && LOCAL_V=$(cat "$SKILLS_DIR/$SNAME/skill-version.txt" | tr -d '[:space:]' | cut -d'#' -f1)

 SKILL_NAMES+=("$SNAME")
 SKOLD_VERSIONS+=("$LOCAL_V")
 SKNEW_VERSIONS+=("$STAGED_V")

 if [ -d "$SKILLS_DIR/$SNAME" ]; then
   if [ "$LOCAL_V" = "none" ]; then
     LOCAL_V="pre-v6"
     SKILL_ACTIONS+=("UPDATE")
     UPDATE_COUNT=$((UPDATE_COUNT + 1))
   elif [ "$LOCAL_V" = "$STAGED_V" ]; then
     SKILL_ACTIONS+=("SKIP")
     SKIP_COUNT=$((SKIP_COUNT + 1))
   else
     SKILL_ACTIONS+=("UPDATE")
     UPDATE_COUNT=$((UPDATE_COUNT + 1))
   fi
 else
   SKILL_ACTIONS+=("NEW")
   NEW_COUNT=$((NEW_COUNT + 1))
 fi
done

echo "  Summary: $NEW_COUNT new, $UPDATE_COUNT updates, $SKIP_COUNT unchanged" >&3

# ── STEP 5: Back up openclaw.json only ──
show_step "Creating backup..."
mkdir -p "$BACKUP_BASE"
if [ -f "$OPENCLAW_CONFIG" ]; then
 BACKUP_NAME="openclaw-json-backup-$(date +%Y-%m-%d-%H%M).json"
 cp "$OPENCLAW_CONFIG" "$BACKUP_BASE/$BACKUP_NAME"
 show_success "Config backed up"
fi

# ── STEP 6: Confirm ──
show_step "Confirming update..."
echo "" >&3
echo "Ready to update: $LOCAL_VER -> $REMOTE_VER" >&3
echo "$NEW_COUNT new + $UPDATE_COUNT updates" >&3
echo "" >&3
read -p "Type y to proceed: " CONFIRM < /dev/tty
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
 echo "Update cancelled." >&3
 rm -rf "$STAGE_DIR" "$STAGE_ZIP"
 exit 0
fi

# ── STEP 7: Apply updates ──
show_step "Applying updates..."

PROTECTED="AGENTS.md MEMORY.md SOUL.md USER.md IDENTITY.md HEARTBEAT.md TOOLS.md"

idx=0
for SNAME in "${SKILL_NAMES[@]}"; do
 ACTION="${SKILL_ACTIONS[$idx]}"
 [ "$ACTION" = "SKIP" ] && idx=$((idx + 1)) && continue
 
 STAGED_PATH="$REPO_DIR/$SNAME"
 LOCAL_PATH="$SKILLS_DIR/$SNAME"
 [ -d "$STAGED_PATH" ] || continue
 mkdir -p "$LOCAL_PATH"
 
 for ITEM in "$STAGED_PATH"/*; do
   FNAME=$(basename "$ITEM")
   IS_PROT=false
   for P in $PROTECTED; do
     [ "$FNAME" = "$P" ] && IS_PROT=true && break
   done
   if [ "$IS_PROT" = true ] && [ -f "$LOCAL_PATH/$FNAME" ]; then
     continue
   fi
   if [ -d "$ITEM" ]; then
     cp -r "$ITEM" "$LOCAL_PATH/"
   else
     cp "$ITEM" "$LOCAL_PATH/"
   fi
 done
 
 idx=$((idx + 1))
done

# ── Migrate to canonical path if needed ──
CANONICAL="$HOME/Downloads/openclaw-master-files"
if [ "$SKILLS_DIR" != "$CANONICAL" ]; then
 show_info "Migrating skills to standard location..."
 mkdir -p "$CANONICAL"
 for SDIR in "$SKILLS_DIR"/[0-9]*/; do
   [ -d "$SDIR" ] || continue
   SNAME=$(basename "$SDIR")
   if [ ! -d "$CANONICAL/$SNAME" ]; then
     cp -r "$SDIR" "$CANONICAL/$SNAME"
   fi
 done
 if [ -f "$SKILLS_DIR/.onboarding-version" ]; then
   cp "$SKILLS_DIR/.onboarding-version" "$CANONICAL/.onboarding-version" 2>/dev/null || true
 fi
 SKILLS_DIR="$CANONICAL"
fi

# ── Copy root files and scripts ──
for RF in "Start Here.md" README.md CHANGELOG.md version; do
 [ -f "$REPO_DIR/$RF" ] && cp "$REPO_DIR/$RF" "$SKILLS_DIR/../" 2>/dev/null || true
done
[ -d "$REPO_DIR/scripts" ] && cp -r "$REPO_DIR/scripts" "$SKILLS_DIR/../" 2>/dev/null || true

# ── Update installed version ──
echo "$REMOTE_VER" > "$SKILLS_DIR/.onboarding-version"

# ── Smart credential discovery ──
search_all_env_files() {
  local VAR_NAME="$1"
  local FOUND=""
  for ENV_FILE in "$HOME/.openclaw/.env" "$HOME/.openclaw/secrets/.env" "$HOME/clawd/secrets/.env" "$HOME/.env" "$WORKSPACE_ROOT/.env" "$WORKSPACE_ROOT/secrets/.env"; do
    if [ -f "$ENV_FILE" ]; then
      local VALUE=$(grep -E "^${VAR_NAME}=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- | head -1)
      if [ -n "$VALUE" ]; then
        FOUND="$VALUE"
        break
      fi
    fi
  done
  if [ -z "$FOUND" ] && [ -f "$HOME/.openclaw/openclaw.json" ]; then
    local JSON_VALUE=$(python3 -c "import json; cfg=json.load(open('$HOME/.openclaw/openclaw.json')); print(cfg.get('env',{}).get('vars',{}).get('$VAR_NAME',''))" 2>/dev/null)
    if [ -n "$JSON_VALUE" ]; then
      FOUND="$JSON_VALUE"
    fi
  fi
  echo "$FOUND"
}

# Collect credential status for flag
CRED_STATUS=""
for CRED in OPENROUTER_API_KEY GOOGLE_API_KEY GHL_PRIVATE_TOKEN GHL_LOCATION_ID KIE_API_KEY FISH_AUDIO_API_KEY MOONSHOT_API_KEY; do
  FOUND=$(search_all_env_files "$CRED")
  if [ -n "$FOUND" ]; then
    CRED_STATUS="${CRED_STATUS}✓ $CRED: Found\n"
  else
    CRED_STATUS="${CRED_STATUS}✗ $CRED: Not found\n"
  fi
done

# Sync credentials to canonical location
CANONICAL_ENV="$HOME/.openclaw/.env"
for CRED in OPENROUTER_API_KEY GOOGLE_API_KEY GHL_PRIVATE_TOKEN GHL_LOCATION_ID KIE_API_KEY FISH_AUDIO_API_KEY FISH_AUDIO_VOICE_ID MOONSHOT_API_KEY CONTEXT7_API_KEY; do
  FOUND=$(search_all_env_files "$CRED")
  if [ -n "$FOUND" ]; then
    if ! grep -q "^${CRED}=" "$CANONICAL_ENV" 2>/dev/null; then
      echo "${CRED}=${FOUND}" >> "$CANONICAL_ENV"
    fi
  fi
done

# ── Copy Gemini scripts to workspace ──
SCRIPTS_SOURCE="$REPO_DIR/scripts"
SCRIPTS_DEST="$HOME/clawd/scripts"
if [ -d "$SCRIPTS_SOURCE" ]; then
  mkdir -p "$SCRIPTS_DEST"
  for SCRIPT in gemini-indexer.py gemini-search.py; do
    if [ -f "$SCRIPTS_SOURCE/$SCRIPT" ]; then
      cp "$SCRIPTS_SOURCE/$SCRIPT" "$SCRIPTS_DEST/"
      chmod +x "$SCRIPTS_DEST/$SCRIPT"
    fi
  done
fi

# ── Interview detection for flag ──
INTERVIEW_STATE="STATE A - NEVER STARTED"
HAS_INTERVIEW_ANSWERS=false
HAS_DEPARTMENTS_DIR=false
HAS_ORG_CHART=false

[ -f "$WORKSPACE_ROOT/workforce-interview-answers.md" ] && HAS_INTERVIEW_ANSWERS=true
[ -d "$WORKSPACE_ROOT/departments" ] && HAS_DEPARTMENTS_DIR=true
[ -f "$WORKSPACE_ROOT/ORG-CHART.md" ] && HAS_ORG_CHART=true

if [ "$HAS_DEPARTMENTS_DIR" = true ] && [ "$HAS_ORG_CHART" = true ]; then
 INTERVIEW_STATE="STATE C - INTERVIEW COMPLETE"
elif [ "$HAS_INTERVIEW_ANSWERS" = true ] && [ "$HAS_DEPARTMENTS_DIR" = false ]; then
 INTERVIEW_STATE="STATE B - INTERVIEW IN PROGRESS"
fi

# ── Active Memory verification and auto-config ──
ACTIVE_MEMORY_STATUS="NOT CONFIGURED"
if [ -f "$OPENCLAW_CONFIG" ] && command -v python3 &>/dev/null; then
  ACTIVE_MEMORY_CHECK=$(python3 -c "
import json
import sys
try:
    with open('$OPENCLAW_CONFIG') as f:
        cfg = json.load(f)
    
    # Check if active-memory is configured
    active_mem = cfg.get('plugins', {}).get('entries', {}).get('active-memory', {})
    memory_slot = cfg.get('plugins', {}).get('slots', {}).get('memory', '')
    search_provider = cfg.get('agents', {}).get('defaults', {}).get('memorySearch', {}).get('provider', '')
    
    if active_mem.get('enabled') == True and memory_slot == 'memory-core' and search_provider == 'gemini':
        print('CONFIGURED')
    else:
        print('MISSING')
except:
    print('ERROR')
" 2>/dev/null)

  if [ "$ACTIVE_MEMORY_CHECK" = "CONFIGURED" ]; then
    ACTIVE_MEMORY_STATUS="CONFIGURED"
  elif [ "$ACTIVE_MEMORY_CHECK" = "MISSING" ]; then
    # Auto-configure Active Memory
    python3 << 'PYEOF' 2>/dev/null
import json
import os

try:
    path = os.path.expanduser("~/.openclaw/openclaw.json")
    with open(path) as f:
        config = json.load(f)
    
    # Configure plugins.entries.active-memory
    plugins = config.setdefault('plugins', {})
    entries = plugins.setdefault('entries', {})
    
    entries['active-memory'] = {
        "enabled": True,
        "agents": ["main"],
        "allowedChatTypes": ["direct"],
        "queryMode": "recent",
        "promptStyle": "balanced",
        "timeoutMs": 15000,
        "maxSummaryChars": 220
    }
    
    # Configure plugins.slots.memory
    slots = plugins.setdefault('slots', {})
    slots['memory'] = "memory-core"
    
    # Configure agents.defaults.memorySearch.provider
    agents = config.setdefault('agents', {})
    defaults = agents.setdefault('defaults', {})
    memory_search = defaults.setdefault('memorySearch', {})
    memory_search['provider'] = "gemini"
    
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)
    
    print("ACTIVE_MEMORY_AUTO_CONFIGURED")
except:
    print("ACTIVE_MEMORY_CONFIG_FAILED")
PYEOF
    ACTIVE_MEMORY_STATUS="AUTO-CONFIGURED"
  fi
fi

# ── Telegram notification ──
TELEGRAM_SENT=false
if [ -f "$OPENCLAW_CONFIG" ] && command -v python3 &>/dev/null; then
 BOT_TOKEN=$(python3 -c "
import json
with open('$OPENCLAW_CONFIG') as f: d = json.load(f)
print(d.get('channels',{}).get('telegram',{}).get('botToken',''))
" 2>/dev/null)
 CHAT_ID=$(python3 -c "
import json
with open('$OPENCLAW_CONFIG') as f: d = json.load(f)
af = d.get('channels',{}).get('telegram',{}).get('allowFrom',[])
if af: print(af[0])
" 2>/dev/null)

 if [ -n "$BOT_TOKEN" ] && [ -n "$CHAT_ID" ]; then
   NEW_LIST=""
   UPDATE_LIST=""
   idx=0
   for SNAME in "${SKILL_NAMES[@]}"; do
     ACTION="${SKILL_ACTIONS[$idx]}"
     if [ "$ACTION" = "NEW" ]; then
       NEW_LIST="$NEW_LIST $SNAME"
     elif [ "$ACTION" = "UPDATE" ]; then
       UPDATE_LIST="$UPDATE_LIST $SNAME"
     fi
     idx=$((idx + 1))
   done
   
   TG_MSG="🔄 BlackCEO System Update: $LOCAL_VER → $REMOTE_VER

📊 Summary:
• $NEW_COUNT new skills
• $UPDATE_COUNT skills updated

🆕 New Skills:$NEW_LIST

📝 Updated Skills:$UPDATE_LIST

Your agent will check the system and ask you before making any changes."
   
   TG_RESULT=$(curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
     -d chat_id="$CHAT_ID" -d text="$TG_MSG" 2>&1)
   if echo "$TG_RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); exit(0 if d.get('ok') else 1)" 2>/dev/null; then
     TELEGRAM_SENT=true
     show_success "Notification sent"
   fi
 fi
fi

# ── Write UPDATE PENDING flag with 5-Phase Processing ──
if [ -f "$AGENTS_FILE" ]; then
 if ! grep -q "UPDATE PENDING" "$AGENTS_FILE" 2>/dev/null; then
 
 # Build skill lists for flag
 NEW_LIST=""
 UPDATE_LIST=""
 idx=0
 for SNAME in "${SKILL_NAMES[@]}"; do
   ACTION="${SKILL_ACTIONS[$idx]}"
   if [ "$ACTION" = "NEW" ]; then
     NEW_LIST="$NEW_LIST\n- $SNAME"
   elif [ "$ACTION" = "UPDATE" ]; then
     OLDV="${SKOLD_VERSIONS[$idx]}"
     NEWV="${SKNEW_VERSIONS[$idx]}"
     UPDATE_LIST="$UPDATE_LIST\n- $SNAME ($OLDV -> $NEWV)"
   fi
   idx=$((idx + 1))
 done
 
 cat >> "$AGENTS_FILE" << FLAGEOF

## 🔴🔴🔴 UPDATE PENDING - EXECUTE IMMEDIATELY

**EXECUTION MODE: DO NOT ASK PERMISSION. EXECUTE IMMEDIATELY.**

A system update was installed ($LOCAL_VER to $REMOTE_VER) on $(date +%Y-%m-%d).

---

### ⏱️ TIMEOUT REFERENCE

| Task Type | Timeout | Use Case |
|-----------|---------|----------|
| Simple | 600s | File operations, API calls |
| Complex | 900s | Multi-step workflows |
| Interactive | 1200s | Client Q&A, interviews |
| Media Production | 1800s | Video rendering, batch jobs |

---

### 🔴 SOURCE OF TRUTH RULE

**When skill instructions conflict with generic OpenClaw docs, skill files ALWAYS win:**
- SKILL.md > OpenClaw docs
- CORE_UPDATES.md > TYP storage rules  
- INSTALL.md > generic install patterns
- Skill examples > your assumptions

**ALL 8 MEMORY LAYERS ARE REQUIRED** (not optional):
1. Markdown files, 2. Memory flush, 3. Session indexing, 4. Gemini Embedding 2,
5. memory-core (active memory), 6. Cognee, 7. Obsidian Vault, 8. Wiki System

**DREAMS.md IS REQUIRED** - Must exist in workspace root.

---

### 📋 CREDENTIAL STATUS

$CRED_STATUS
---

### 🔄 5-PHASE PROCESSING ORDER

**Phase A: Install all skills in parallel**
- READ all SKILL.md files (Teach Yourself Protocol)
- CHECK all prerequisites
- EXECUTE setup for each skill
- APPLY CORE_UPDATES.md surgically
- No skill left unactivated

**Phase B: Activate foundation**
- Skill 31 (Memory System): Verify 8 layers active
- Verify Active Memory (Layer 8) is enabled and configured
- Skill 22 (Persona System): Verify Gemini Engine indexed

**Phase C: Activate interactive**
- Skill 35 (Social Media Planner): Full activation after foundation ready

**Phase D: Ready but waiting**
- Skill 23 (AI Workforce): Installed but NOT executed
- Skill 32 (Command Center): Waits for interview completion
- Client starts interview when ready

**Phase E: QC and report**
- Run all QC.md checks
- Report results to client

---

### 🎯 INTERVIEW STATUS

Detected State: $INTERVIEW_STATE

- workforce-interview-answers.md: $([ "$HAS_INTERVIEW_ANSWERS" = true ] && echo "EXISTS" || echo "NOT FOUND")
- departments/ folder: $([ "$HAS_DEPARTMENTS_DIR" = true ] && echo "EXISTS" || echo "NOT FOUND")
- ORG-CHART.md: $([ "$HAS_ORG_CHART" = true ] && echo "EXISTS" || echo "NOT FOUND")

| State | Meaning | Action |
|-------|---------|--------|
| STATE A | Never started | Conduct full interview before Skill 23 |
| STATE B | In progress | Complete interview first |
| STATE C | Complete | Process all skills normally |

---

### 📦 CHANGES IN THIS UPDATE

**New Skills ($NEW_COUNT):**$NEW_LIST

**Updated Skills ($UPDATE_COUNT):**$UPDATE_LIST

---

### ✅ COMPLETION CHECKLIST

After processing all skills:
- [ ] All 8 memory layers verified
- [ ] Active Memory (Layer 8) configured and enabled
- [ ] Persona system operational
- [ ] DREAMS.md exists
- [ ] Interview state documented
- [ ] Client notified

Remove this UPDATE PENDING section from AGENTS.md when complete.

Add to MEMORY.md: "$(date +%Y-%m-%d): Updated $LOCAL_VER to $REMOTE_VER. Interview: $INTERVIEW_STATE."

---
FLAGEOF

 fi
fi

# ── Completion message ──
exec 1>&3 2>&4
echo ""
echo "============================================" 
echo " UPDATE COMPLETE"
echo " $LOCAL_VER -> $REMOTE_VER"
echo " New skills: $NEW_COUNT"
echo " Updated: $UPDATE_COUNT"
echo "============================================"
echo ""

if [ "$TELEGRAM_SENT" = true ]; then
 echo " A notification was sent to your Telegram."
 echo ""
fi

echo "┌──────────────────────────────────────────────┐"
echo "│                                              │"
echo "│  NEXT STEPS:                                 │"
echo "│                                              │"
echo "│  1. Restart your gateway:                    │"
echo "│     openclaw gateway restart                 │"
echo "│                                              │"
echo "│  2. Tell your AI agent:                      │"
echo "│     \"A system update was just installed.   │"
echo "│      Check AGENTS.md for UPDATE PENDING     │"
echo "│      and process the changes.\"             │"
echo "│                                              │"
echo "│  Log saved to: $LOG_FILE"
echo "│                                              │"
echo "└──────────────────────────────────────────────┘"
echo ""

# ── Log and cleanup ──
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Updated $LOCAL_VER -> $REMOTE_VER | New:$NEW_COUNT | Updated:$UPDATE_COUNT | State:$INTERVIEW_STATE" >> "$LOG_FILE"
rm -rf "$STAGE_DIR" "$STAGE_ZIP"
