#!/bin/bash
# BlackCEO System - Safe Update Script
# Downloads latest, compares versions, backs up config,
# asks for approval, applies updates, notifies via Telegram,
# writes UPDATE PENDING flag for the agent.

set -euo pipefail

# ── CONFIGURATION ──
# MAC REPO (change these two lines for VPS version):
REPO_URL="https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip"
REPO_FOLDER="openclaw-onboarding-main"
BACKUP_BASE="$HOME/Downloads/openclaw-backups"

# ── Discover where skills are actually installed ──
# Old versions installed to different paths. Check all known locations.
discover_skills_dir() {
  CANDIDATES=(
    "$HOME/.openclaw/skills"
    "$HOME/Downloads/openclaw-master-files"
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
  
  echo "$HOME/.openclaw/skills"
}

SKILLS_DIR=$(discover_skills_dir)
echo "Skills directory: $SKILLS_DIR"
STAGE_DIR="/tmp/blackceo-update-$$"
STAGE_ZIP="/tmp/blackceo-update-$$.zip"
LOG_FILE="$SKILLS_DIR/.update-log"
OPENCLAW_CONFIG="$HOME/.openclaw/openclaw.json"

echo ""
echo "============================================"
echo " BlackCEO System - Update Check"
echo "============================================"
echo ""

# ── STEP 1: Current version ──
mkdir -p "$SKILLS_DIR"
LOCAL_VER="none"
if [ -f "$SKILLS_DIR/.onboarding-version" ]; then
 LOCAL_VER=$(cat "$SKILLS_DIR/.onboarding-version" | tr -d '[:space:]')
fi
echo "Installed version: $LOCAL_VER"

# ── STEP 2: Download latest ──
echo "Downloading latest from GitHub..."
rm -rf "$STAGE_DIR" "$STAGE_ZIP"
curl -fsSL "$REPO_URL" -o "$STAGE_ZIP" 2>/dev/null
if [ ! -f "$STAGE_ZIP" ]; then
 echo "[ERROR] Download failed. Check internet."
 exit 1
fi
unzip -qo "$STAGE_ZIP" -d "$STAGE_DIR"
REPO_DIR="$STAGE_DIR/$REPO_FOLDER"
if [ ! -d "$REPO_DIR" ]; then
 echo "[ERROR] Unexpected archive structure."
 rm -rf "$STAGE_DIR" "$STAGE_ZIP"
 exit 1
fi

REMOTE_VER="unknown"
if [ -f "$REPO_DIR/version" ]; then
 REMOTE_VER=$(cat "$REPO_DIR/version" | tr -d '[:space:]')
fi
echo "Latest version: $REMOTE_VER"

# ── STEP 3: Compare versions ──
if [ "$LOCAL_VER" = "$REMOTE_VER" ]; then
 echo ""
 echo "Already up to date ($LOCAL_VER). Nothing to do."
 rm -rf "$STAGE_DIR" "$STAGE_ZIP"
 exit 0
fi

echo ""
echo "Update available: $LOCAL_VER -> $REMOTE_VER"
echo ""

# ── STEP 4: Per-skill comparison ──
UPDATE_LIST=""
NEW_LIST=""
SKIP_COUNT=0
UPDATE_COUNT=0
NEW_COUNT=0

for SKILL_PATH in "$REPO_DIR"/[0-9]*/; do
 [ -d "$SKILL_PATH" ] || continue
 SNAME=$(basename "$SKILL_PATH")
 case "$SNAME" in *ARCHIVED*) continue ;; esac

 STAGED_V="unknown"
 LOCAL_V="none"
 [ -f "$SKILL_PATH/skill-version.txt" ] && STAGED_V=$(cat "$SKILL_PATH/skill-version.txt" | tr -d '[:space:]' | cut -d'#' -f1)
 [ -f "$SKILLS_DIR/$SNAME/skill-version.txt" ] && LOCAL_V=$(cat "$SKILLS_DIR/$SNAME/skill-version.txt" | tr -d '[:space:]' | cut -d'#' -f1)

 # Handle old installs: folder exists but no version file = pre-v6
 if [ -d "$SKILLS_DIR/$SNAME" ]; then
   if [ "$LOCAL_V" = "none" ]; then
     # Skill folder exists but no version file (old install)
     LOCAL_V="pre-v6"
     echo " UPDATE: $SNAME (pre-v6 -> $STAGED_V)"
     UPDATE_LIST="$UPDATE_LIST $SNAME"
     UPDATE_COUNT=$((UPDATE_COUNT + 1))
   elif [ "$LOCAL_V" = "$STAGED_V" ]; then
     SKIP_COUNT=$((SKIP_COUNT + 1))
   else
     echo " UPDATE: $SNAME ($LOCAL_V -> $STAGED_V)"
     UPDATE_LIST="$UPDATE_LIST $SNAME"
     UPDATE_COUNT=$((UPDATE_COUNT + 1))
   fi
 else
   echo " NEW: $SNAME ($STAGED_V)"
   NEW_LIST="$NEW_LIST $SNAME"
   NEW_COUNT=$((NEW_COUNT + 1))
 fi
done

echo ""
echo " New skills: $NEW_COUNT"
echo " Updates: $UPDATE_COUNT"
echo " Already current: $SKIP_COUNT"

# ── STEP 5: Show changelog ──
echo ""
echo "── What changed ──"
if [ -f "$REPO_DIR/CHANGELOG.md" ]; then
 head -40 "$REPO_DIR/CHANGELOG.md"
fi

# ── STEP 6: Back up openclaw.json only ──
mkdir -p "$BACKUP_BASE"
if [ -f "$OPENCLAW_CONFIG" ]; then
 BACKUP_NAME="openclaw-json-backup-$(date +%Y-%m-%d-%H%M).json"
 cp "$OPENCLAW_CONFIG" "$BACKUP_BASE/$BACKUP_NAME"
 echo ""
 echo " Config backed up: $BACKUP_BASE/$BACKUP_NAME"
fi

# ── STEP 7: Confirm ──
echo ""
echo "============================================"
echo " Ready to update: $LOCAL_VER -> $REMOTE_VER"
echo " $NEW_COUNT new + $UPDATE_COUNT updates"
echo "============================================"
echo ""
read -p " Type y to proceed: " CONFIRM < /dev/tty
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
 echo " Update cancelled."
 rm -rf "$STAGE_DIR" "$STAGE_ZIP"
 exit 0
fi

# ── STEP 8: Apply skill by skill ──
echo ""
echo "Applying updates..."

PROTECTED="AGENTS.md MEMORY.md SOUL.md USER.md IDENTITY.md HEARTBEAT.md TOOLS.md"

for SNAME in $UPDATE_LIST $NEW_LIST; do
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
 # Skip protected files (agent handles these surgically)
 if [ "$IS_PROT" = true ] && [ -f "$LOCAL_PATH/$FNAME" ]; then
 continue
 fi
 if [ -d "$ITEM" ]; then
 cp -r "$ITEM" "$LOCAL_PATH/"
 else
 cp "$ITEM" "$LOCAL_PATH/"
 fi
 done
 echo " Applied: $SNAME"
done

# ── STEP 8b: Migrate to canonical path if needed ──
CANONICAL="$HOME/.openclaw/skills"
if [ "$SKILLS_DIR" != "$CANONICAL" ]; then
  echo ""
  echo " Migrating skills to standard location..."
  mkdir -p "$CANONICAL"
  for SDIR in "$SKILLS_DIR"/[0-9]*/; do
    [ -d "$SDIR" ] || continue
    SNAME=$(basename "$SDIR")
    if [ ! -d "$CANONICAL/$SNAME" ]; then
      cp -r "$SDIR" "$CANONICAL/$SNAME"
    fi
  done
  # Copy the version file too
  if [ -f "$SKILLS_DIR/.onboarding-version" ]; then
    cp "$SKILLS_DIR/.onboarding-version" "$CANONICAL/.onboarding-version" 2>/dev/null || true
  fi
  if [ -f "$SKILLS_DIR/../.onboarding-version" ]; then
    cp "$SKILLS_DIR/../.onboarding-version" "$CANONICAL/../.onboarding-version" 2>/dev/null || true
  fi
  echo " Skills migrated to $CANONICAL"
  SKILLS_DIR="$CANONICAL"
fi

# ── STEP 9: Update root files ──
for RF in "Start Here.md" README.md CHANGELOG.md version; do
 [ -f "$REPO_DIR/$RF" ] && cp "$REPO_DIR/$RF" "$SKILLS_DIR/../" 2>/dev/null || true
done
[ -d "$REPO_DIR/scripts" ] && cp -r "$REPO_DIR/scripts" "$SKILLS_DIR/../" 2>/dev/null || true

# ── STEP 10: Update installed version ──
echo "$REMOTE_VER" > "$SKILLS_DIR/.onboarding-version"

# ── STEP 11: Telegram notification ──
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
 TG_MSG="Your BlackCEO system has been updated from $LOCAL_VER to $REMOTE_VER. $NEW_COUNT new skills added, $UPDATE_COUNT skills updated. Your agent will review the changes and ask you before setting anything up."
 TG_RESULT=$(curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
 -d chat_id="$CHAT_ID" -d text="$TG_MSG" 2>&1)
 if echo "$TG_RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); exit(0 if d.get('ok') else 1)" 2>/dev/null; then
 TELEGRAM_SENT=true
 echo ""
 echo " Telegram notification sent."
 fi
 fi
fi

# ── STEP 12: Write UPDATE PENDING flag ──
WORKSPACE_ROOT="$HOME/clawd"
[ ! -d "$WORKSPACE_ROOT" ] && WORKSPACE_ROOT="$HOME/.openclaw/workspace"
AGENTS_FILE="$WORKSPACE_ROOT/AGENTS.md"

if [ -f "$AGENTS_FILE" ]; then
 if ! grep -q "UPDATE PENDING" "$AGENTS_FILE" 2>/dev/null; then
 cat >> "$AGENTS_FILE" << FLAGEOF

## UPDATE PENDING - PROCESS NOW

A system update was installed ($LOCAL_VER to $REMOTE_VER) on $(date).

New skills:$NEW_LIST
Updated skills:$UPDATE_LIST

SEND YOUR OWNER THIS MESSAGE IMMEDIATELY:
"Your BlackCEO system was just updated from $LOCAL_VER to $REMOTE_VER. Here is what changed: $NEW_COUNT new skills added, $UPDATE_COUNT skills updated. Would you like me to start setting up the new skills and applying the updates?"

WAIT for the owner to say yes before proceeding.

When they approve:
- For each UPDATED skill: read SKILL.md and QC.md, verify it works correctly
- For each NEW skill: run the full Teach Yourself Protocol (read all files in order), follow INSTALL.md setup steps, run QC.md checks
- For each skill with CORE_UPDATES.md: surgically update AGENTS.md, TOOLS.md, and MEMORY.md
 - Add new entries that do not exist yet
 - Update entries that have changed from a previous skill version
 - Remove entries from old skill versions that no longer apply
 - Do NOT duplicate entries that already exist
 - Do NOT touch the owner's personal content
 - Skill sections are identified by headers like "### [Skill Name] (Skill [Number])"

After ALL skills are processed:
1. Remove this entire UPDATE PENDING section from AGENTS.md
2. Add one line to MEMORY.md under "## System Updates":
 "[DATE]: Updated $LOCAL_VER to $REMOTE_VER. New:$NEW_LIST. Updated:$UPDATE_LIST. All QC passed."
FLAGEOF
 fi
fi

# ── STEP 13: Terminal output ──
echo ""
echo "============================================"
echo " UPDATE COMPLETE"
echo " $LOCAL_VER -> $REMOTE_VER"
echo " New skills: $NEW_COUNT"
echo " Updated: $UPDATE_COUNT"
echo " Skipped: $SKIP_COUNT"
echo "============================================"
echo ""

if [ "$TELEGRAM_SENT" = true ]; then
 echo " A notification was sent to your Telegram."
 echo ""
fi

echo "┌──────────────────────────────────────────────┐"
echo "│                                              │"
echo "│  TELL YOUR AI AGENT:                         │"
echo "│                                              │"
echo "│  \"A system update was just installed.       │"
echo "│  Check your AGENTS.md for the UPDATE        │"
echo "│  PENDING flag and process the changes.      │"
echo "│  Ask me before making any changes.\"        │"
echo "│                                              │"
echo "└──────────────────────────────────────────────┘"
echo ""

# ── STEP 14: Log and cleanup ──
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Updated $LOCAL_VER -> $REMOTE_VER | New:$NEW_LIST | Updated:$UPDATE_LIST | telegram=$TELEGRAM_SENT" >> "$LOG_FILE"
rm -rf "$STAGE_DIR" "$STAGE_ZIP"
