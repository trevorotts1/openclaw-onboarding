#!/bin/bash
# BlackCEO System — Safe Skill Updater
# Version: 7.0.0 | April 13, 2026
#
# This script performs a FULL safe update with staged download,
# version checking, per-skill comparison, and user confirmation.
#
# Usage: bash ~/.openclaw/workspace/scripts/update-skills.sh

set -euo pipefail

# ───────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ───────────────────────────────────────────────────────────────────────────────

REPO_URL="https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip"
STAGED_DIR="/tmp/oc-update"
STAGED_ZIP="/tmp/oc-update.zip"
STAGED_ROOT="$STAGED_DIR/openclaw-onboarding-main"
LOCAL_SKILLS_DIR="$HOME/.openclaw/skills"
BACKUP_DIR="$HOME/Downloads/openclaw-backups/$(date +%Y%m%d-%H%M%S)-update"
LOG_FILE="$HOME/.openclaw/skills/.update-log"
FLAG_FILE="$HOME/.openclaw/skills/.update-pending"
NOTIFICATION_FILE="/tmp/oc-update-notification.md"
OPENCLAW_CONFIG="$HOME/.openclaw/openclaw.json"
AGENTS_FILE="$HOME/.openclaw/workspace/AGENTS.md"
VERSION_FILE="$HOME/.openclaw/skills/.onboarding-version"
MANIFEST_FILE="$HOME/.openclaw/skills/.skill-manifest.json"

# Protected core files that should never be overwritten
PROTECTED_FILES=(
    "AGENTS.md"
    "MEMORY.md"
    "SOUL.md"
    "USER.md"
    "IDENTITY.md"
    "HEARTBEAT.md"
    "TOOLS.md"
)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ───────────────────────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS
# ───────────────────────────────────────────────────────────────────────────────

log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE" 2>/dev/null || true
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
}

# Rollback function for failed skill updates
rollback_skill() {
    local skill_name="$1"
    local backup_path="$2"
    
    log "Rolling back $skill_name from backup..."
    if [ -d "$backup_path" ]; then
        rm -rf "${LOCAL_SKILLS_DIR:?}/${skill_name:?}"
        cp -r "$backup_path" "${LOCAL_SKILLS_DIR}/${skill_name}"
        success "Rolled back $skill_name"
        return 0
    else
        error "No backup found for $skill_name at $backup_path"
        return 1
    fi
}

# Cleanup function on exit
cleanup() {
    if [ "${KEEP_STAGED:-false}" != "true" ]; then
        rm -rf "$STAGED_DIR" "$STAGED_ZIP" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# ───────────────────────────────────────────────────────────────────────────────
# STEP 1: STAGED DOWNLOAD
# ───────────────────────────────────────────────────────────────────────────────

echo ""
echo "============================================"
echo "   BlackCEO System — Safe Skill Updater"
echo "============================================"
echo ""

log "Step 1: Staged Download — Downloading latest version..."

# Clean up any previous staged downloads
rm -rf "$STAGED_DIR" "$STAGED_ZIP"
mkdir -p "$STAGED_DIR"

# Download the latest version
curl -fsSL "$REPO_URL" -o "$STAGED_ZIP" 2>/dev/null

if [ ! -f "$STAGED_ZIP" ]; then
    error "Could not download update. Check your internet connection."
    exit 1
fi

# Extract
unzip -qo "$STAGED_ZIP" -d "$STAGED_DIR"

if [ ! -d "$STAGED_ROOT" ]; then
    error "Unexpected archive structure."
    exit 1
fi

success "Downloaded and extracted to $STAGED_ROOT"

# ───────────────────────────────────────────────────────────────────────────────
# STEP 2: VERSION CHECK
# ───────────────────────────────────────────────────────────────────────────────

log "Step 2: Version Check — Comparing local vs remote..."

LOCAL_VERSION="unknown"
if [ -f "$VERSION_FILE" ]; then
    LOCAL_VERSION=$(cat "$VERSION_FILE" | tr -d '[:space:]')
fi

REMOTE_VERSION="unknown"
if [ -f "$STAGED_ROOT/version" ]; then
    REMOTE_VERSION=$(cat "$STAGED_ROOT/version" | tr -d '[:space:]')
fi

echo "  Current version: $LOCAL_VERSION"
echo "  Latest version:  $REMOTE_VERSION"

if [ "$LOCAL_VERSION" = "$REMOTE_VERSION" ]; then
    echo ""
    success "You are already on the latest version ($LOCAL_VERSION)."
    echo "No update needed."
    exit 0
fi

echo ""
echo "Update available: $LOCAL_VERSION → $REMOTE_VERSION"
echo ""

# ───────────────────────────────────────────────────────────────────────────────
# STEP 3: PER-SKILL COMPARISON
# ───────────────────────────────────────────────────────────────────────────────

log "Step 3: Per-Skill Comparison — Analyzing skill differences..."

STAGED_SKILLS_DIR="$STAGED_ROOT"
SKILLS_NEW=0
SKILLS_UPDATED=0
SKILLS_UNCHANGED=0
SKILLS_TOTAL=0

# Arrays to store skill info
declare -a NEW_SKILLS=()
declare -a UPDATED_SKILLS=()
declare -a UNCHANGED_SKILLS=()

for staged_skill in "$STAGED_SKILLS_DIR"/[0-9]*/; do
    [ -d "$staged_skill" ] || continue
    
    skill_name=$(basename "$staged_skill")
    staged_version_file="$staged_skill/skill-version.txt"
    local_version_file="$LOCAL_SKILLS_DIR/$skill_name/skill-version.txt"
    
    SKILLS_TOTAL=$((SKILLS_TOTAL + 1))
    
    if [ -f "$staged_version_file" ]; then
        staged_skill_version=$(cat "$staged_version_file" 2>/dev/null | tr -d '[:space:]' || echo "unknown")
    else
        staged_skill_version="unknown"
    fi
    
    if [ -f "$local_version_file" ]; then
        local_skill_version=$(cat "$local_version_file" 2>/dev/null | tr -d '[:space:]' || echo "unknown")
    else
        local_skill_version="none"
    fi
    
    if [ ! -d "$LOCAL_SKILLS_DIR/$skill_name" ]; then
        SKILLS_NEW=$((SKILLS_NEW + 1))
        NEW_SKILLS+=("$skill_name|$staged_skill_version")
    elif [ "$local_skill_version" = "$staged_skill_version" ]; then
        SKILLS_UNCHANGED=$((SKILLS_UNCHANGED + 1))
        UNCHANGED_SKILLS+=("$skill_name|$local_skill_version")
    else
        SKILLS_UPDATED=$((SKILLS_UPDATED + 1))
        UPDATED_SKILLS+=("$skill_name|$local_skill_version|$staged_skill_version")
    fi
done

echo "  Total skills in repo: $SKILLS_TOTAL"
echo "  New skills:           $SKILLS_NEW"
echo "  Skills to update:     $SKILLS_UPDATED"
echo "  Skills unchanged:     $SKILLS_UNCHANGED"
echo ""

# ───────────────────────────────────────────────────────────────────────────────
# STEP 4: CHANGELOG DISPLAY
# ───────────────────────────────────────────────────────────────────────────────

log "Step 4: Changelog Display — Reading CHANGELOG.md..."

if [ -f "$STAGED_ROOT/CHANGELOG.md" ]; then
    echo ""
    echo "--- CHANGELOG (since $LOCAL_VERSION) ---"
    echo ""
    
    # Try to extract relevant changelog entries
    if command -v grep >/dev/null 2>&1; then
        # Show first 100 lines of changelog that might be relevant
        head -100 "$STAGED_ROOT/CHANGELOG.md" 2>/dev/null || cat "$STAGED_ROOT/CHANGELOG.md"
    else
        head -50 "$STAGED_ROOT/CHANGELOG.md"
    fi
    
    echo ""
    echo "--- End Changelog ---"
    echo ""
else
    warning "No CHANGELOG.md found in downloaded repo"
fi

# ───────────────────────────────────────────────────────────────────────────────
# STEP 5: RISK ASSESSMENT
# ───────────────────────────────────────────────────────────────────────────────

log "Step 5: Risk Assessment — Evaluating update risks..."

# Determine overall risk level
RISK_LEVEL="LOW"
if [ $SKILLS_UPDATED -gt 3 ]; then
    RISK_LEVEL="MEDIUM"
fi

# Check for any high-risk indicators
HIGH_RISK_COUNT=0
for skill_info in "${UPDATED_SKILLS[@]}"; do
    IFS='|' read -r skill_name old_ver new_ver <<< "$skill_info"
    # Check if skill has CORE_UPDATES.md (indicates core file changes)
    if [ -f "$STAGED_ROOT/$skill_name/CORE_UPDATES.md" ]; then
        warning "Skill $skill_name has CORE_UPDATES.md (core file modifications)"
        HIGH_RISK_COUNT=$((HIGH_RISK_COUNT + 1))
        RISK_LEVEL="HIGH"
    fi
done

echo "  Risk Level: $RISK_LEVEL"
echo "  Skills with core changes: $HIGH_RISK_COUNT"
echo ""

# ───────────────────────────────────────────────────────────────────────────────
# STEP 6: BACKUP
# ───────────────────────────────────────────────────────────────────────────────

log "Step 6: Backup — Creating backup of current installation..."

mkdir -p "$BACKUP_DIR"

# Backup current skills
cp -r "$LOCAL_SKILLS_DIR" "$BACKUP_DIR/skills" 2>/dev/null || true

# Backup core .md files
mkdir -p "$BACKUP_DIR/core-files"
for file in "${PROTECTED_FILES[@]}"; do
    if [ -f "$HOME/.openclaw/workspace/$file" ]; then
        cp "$HOME/.openclaw/workspace/$file" "$BACKUP_DIR/core-files/"
    elif [ -f "$HOME/.openclaw/$file" ]; then
        cp "$HOME/.openclaw/$file" "$BACKUP_DIR/core-files/"
    fi
done

# Backup config
if [ -f "$OPENCLAW_CONFIG" ]; then
    cp "$OPENCLAW_CONFIG" "$BACKUP_DIR/"
fi

# Backup version file
if [ -f "$VERSION_FILE" ]; then
    cp "$VERSION_FILE" "$BACKUP_DIR/"
fi

# Backup manifest if exists
if [ -f "$MANIFEST_FILE" ]; then
    cp "$MANIFEST_FILE" "$BACKUP_DIR/"
fi

success "Backup created at: $BACKUP_DIR"
echo ""

# ───────────────────────────────────────────────────────────────────────────────
# STEP 7: YES CONFIRMATION GATE
# ───────────────────────────────────────────────────────────────────────────────

log "Step 7: Confirmation Gate — Waiting for user approval..."

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    UPDATE SUMMARY                          ║"
echo "╠════════════════════════════════════════════════════════════╣"
echo "║  Version: $LOCAL_VERSION → $REMOTE_VERSION"
echo "║  New skills:       $SKILLS_NEW"
echo "║  Skills to update: $SKILLS_UPDATED"
echo "║  Risk Level:       $RISK_LEVEL"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

if [ $SKILLS_NEW -gt 0 ]; then
    echo "New skills to install:"
    for skill_info in "${NEW_SKILLS[@]}"; do
        IFS='|' read -r skill_name version <<< "$skill_info"
        echo "  - $skill_name (v$version)"
    done
    echo ""
fi

if [ $SKILLS_UPDATED -gt 0 ]; then
    echo "Skills to update:"
    for skill_info in "${UPDATED_SKILLS[@]}"; do
        IFS='|' read -r skill_name old_ver new_ver <<< "$skill_info"
        echo "  - $skill_name ($old_ver → $new_ver)"
    done
    echo ""
fi

echo "Backup location: $BACKUP_DIR"
echo ""
echo "Do you want to proceed with the update?"
echo "Type YES (in uppercase) to continue, or anything else to cancel:"
read -r CONFIRM

if [ "$CONFIRM" != "YES" ]; then
    warning "Update cancelled by user"
    exit 0
fi

success "User confirmed. Proceeding with update..."
echo ""

# ───────────────────────────────────────────────────────────────────────────────
# STEP 8: SKILL-BY-SKILL APPLY
# ───────────────────────────────────────────────────────────────────────────────

log "Step 8: Skill-by-Skill Apply — Installing/updating skills..."

SUCCESSFUL_SKILLS=()
FAILED_SKILLS=()
SKIPPED_SKILLS=()

# Process new skills
for skill_info in "${NEW_SKILLS[@]}"; do
    IFS='|' read -r skill_name version <<< "$skill_info"
    log "Installing new skill: $skill_name..."
    
    # Backup before applying (for rollback)
    SKILL_BACKUP="$BACKUP_DIR/skills/$skill_name"
    
    if cp -r "$STAGED_ROOT/$skill_name" "$LOCAL_SKILLS_DIR/" 2>/dev/null; then
        success "Installed $skill_name"
        SUCCESSFUL_SKILLS+=("$skill_name (new)")
    else
        error "Failed to install $skill_name"
        FAILED_SKILLS+=("$skill_name")
    fi
done

# Process updated skills
for skill_info in "${UPDATED_SKILLS[@]}"; do
    IFS='|' read -r skill_name old_ver new_ver <<< "$skill_info"
    log "Updating skill: $skill_name ($old_ver → $new_ver)..."
    
    # Create backup of current version for rollback
    SKILL_BACKUP="$BACKUP_DIR/skills/$skill_name"
    if [ -d "$LOCAL_SKILLS_DIR/$skill_name" ]; then
        cp -r "$LOCAL_SKILLS_DIR/$skill_name" "$SKILL_BACKUP" 2>/dev/null || true
    fi
    
    # Remove old version and copy new
    rm -rf "${LOCAL_SKILLS_DIR:?}/${skill_name:?}"
    
    if cp -r "$STAGED_ROOT/$skill_name" "$LOCAL_SKILLS_DIR/" 2>/dev/null; then
        success "Updated $skill_name"
        SUCCESSFUL_SKILLS+=("$skill_name ($old_ver → $new_ver)")
    else
        error "Failed to update $skill_name"
        # Attempt rollback
        rollback_skill "$skill_name" "$SKILL_BACKUP" || true
        FAILED_SKILLS+=("$skill_name")
    fi
done

echo ""

# ───────────────────────────────────────────────────────────────────────────────
# STEP 9: INSTALLED VERSION UPDATE
# ───────────────────────────────────────────────────────────────────────────────

log "Step 9: Installed Version Update — Updating version file..."

echo "$REMOTE_VERSION" > "$VERSION_FILE"
success "Updated version file to $REMOTE_VERSION"
echo ""

# ───────────────────────────────────────────────────────────────────────────────
# STEP 10: MANIFEST REGENERATION
# ───────────────────────────────────────────────────────────────────────────────

log "Step 10: Manifest Regeneration — Rebuilding skill manifest..."

# Create JSON manifest of installed skills
{
    echo "{"
    echo "  \"generated_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
    echo "  \"version\": \"$REMOTE_VERSION\","
    echo "  \"skills\": ["
    
    FIRST=true
    for skill_dir in "$LOCAL_SKILLS_DIR"/[0-9]*/; do
        [ -d "$skill_dir" ] || continue
        
        skill_name=$(basename "$skill_dir")
        skill_version="unknown"
        
        if [ -f "$skill_dir/skill-version.txt" ]; then
            skill_version=$(cat "$skill_dir/skill-version.txt" | tr -d '[:space:]')
        fi
        
        if [ "$FIRST" = true ]; then
            FIRST=false
        else
            echo ","
        fi
        
        echo -n "    {\"name\": \"$skill_name\", \"version\": \"$skill_version\"}"
    done
    
    echo ""
    echo "  ]"
    echo "}"
} > "$MANIFEST_FILE"

success "Manifest regenerated at $MANIFEST_FILE"
echo ""

# ───────────────────────────────────────────────────────────────────────────────
# STEP 11: UPDATE LOG
# ───────────────────────────────────────────────────────────────────────────────

log "Step 11: Update Log — Writing detailed log entry..."

{
    echo ""
    echo "========================================"
    echo "Update Completed: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Version: $LOCAL_VERSION → $REMOTE_VERSION"
    echo "Backup: $BACKUP_DIR"
    echo "Risk Level: $RISK_LEVEL"
    echo "========================================"
    echo ""
    echo "Successful Updates (${#SUCCESSFUL_SKILLS[@]}):"
    for skill in "${SUCCESSFUL_SKILLS[@]}"; do
        echo "  ✓ $skill"
    done
    echo ""
    if [ ${#FAILED_SKILLS[@]} -gt 0 ]; then
        echo "Failed Updates (${#FAILED_SKILLS[@]}):"
        for skill in "${FAILED_SKILLS[@]}"; do
            echo "  ✗ $skill"
        done
        echo ""
    fi
    echo "========================================"
} >> "$LOG_FILE"

success "Update log written"
echo ""

# ───────────────────────────────────────────────────────────────────────────────
# STEP 12: TELEGRAM NOTIFICATION
# ───────────────────────────────────────────────────────────────────────────────

log "Step 12: Telegram Notification — Sending update notification..."

TELEGRAM_SENT=false

if [ -f "$OPENCLAW_CONFIG" ]; then
    # Extract bot token
    BOT_TOKEN=$(python3 -c "
import json
with open('$OPENCLAW_CONFIG') as f:
    d = json.load(f)
tg = d.get('channels', {}).get('telegram', {})
print(tg.get('botToken', ''))
" 2>/dev/null || echo "")

    # Extract first allowFrom chat ID
    CHAT_ID=$(python3 -c "
import json
with open('$OPENCLAW_CONFIG') as f:
    d = json.load(f)
tg = d.get('channels', {}).get('telegram', {})
af = tg.get('allowFrom', [])
if af:
    print(af[0])
" 2>/dev/null || echo "")

    if [ -n "$BOT_TOKEN" ] && [ -n "$CHAT_ID" ]; then
        # Build the success message
        TG_MESSAGE="🔄 *BlackCEO System Updated*

Version: \`${LOCAL_VERSION}\` → \`${REMOTE_VERSION}\`

*Summary:*
• New skills: ${SKILLS_NEW}
• Updated: ${SKILLS_UPDATED}
• Unchanged: ${SKILLS_UNCHANGED}
• Risk Level: ${RISK_LEVEL}

*Backup:* \`${BACKUP_DIR}\`

Run \`openclaw gateway restart\` to apply changes."

        # Send via Telegram Bot API
        TG_RESULT=$(curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
            -d chat_id="$CHAT_ID" \
            -d text="$TG_MESSAGE" \
            -d parse_mode="Markdown" 2>&1 || echo "{\"ok\": false}")

        # Check if send succeeded
        if echo "$TG_RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); exit(0 if d.get('ok') else 1)" 2>/dev/null; then
            TELEGRAM_SENT=true
            success "Telegram notification sent"
        else
            warning "Could not send Telegram notification"
        fi
    else
        warning "Could not read Telegram config"
    fi
else
    warning "openclaw.json not found"
fi

# Generate notification file
cat > "$NOTIFICATION_FILE" << NOTEOF
# BlackCEO System Update Complete

**Version:** $LOCAL_VERSION → $REMOTE_VERSION
**Completed:** $(date '+%Y-%m-%d %H:%M:%S')

## Summary

- **New skills installed:** $SKILLS_NEW
- **Skills updated:** $SKILLS_UPDATED
- **Skills unchanged:** $SKILLS_UNCHANGED
- **Risk Level:** $RISK_LEVEL

## Backup Location

Your previous version was backed up to:
\`$BACKUP_DIR\`

## What Changed

See the CHANGELOG.md in the downloaded repo for full details:
https://github.com/trevorotts1/openclaw-onboarding/blob/main/CHANGELOG.md

## Next Steps

1. Review the updated skills above
2. Restart your gateway for changes to take effect:
   \`openclaw gateway restart\`

## If Something Goes Wrong

You can restore from the backup if needed:
\`cp -r "$BACKUP_DIR/skills/*" "$LOCAL_SKILLS_DIR/"\`

NOTEOF

echo "Notification written to: $NOTIFICATION_FILE"
echo ""

# ───────────────────────────────────────────────────────────────────────────────
# STEP 13: UPDATE PENDING FLAG IN AGENTS.md
# ───────────────────────────────────────────────────────────────────────────────

log "Step 13: UPDATE PENDING Flag — Writing flag to AGENTS.md..."

if [ -f "$AGENTS_FILE" ]; then
    # Check if flag already exists
    if ! grep -q "UPDATE PENDING" "$AGENTS_FILE" 2>/dev/null; then
        cat >> "$AGENTS_FILE" << 'UPDATEFLAG'

## 🔴 UPDATE PENDING — RESTART REQUIRED

An update has been applied to your BlackCEO system:
- Version: $LOCAL_VERSION → $REMOTE_VERSION
- Completed: $(date '+%Y-%m-%d %H:%M:%S')
- Backup: $BACKUP_DIR

**ACTION REQUIRED:**
Restart your gateway for changes to take effect:
\`openclaw gateway restart\`

After restart, this flag will be cleared automatically.
UPDATEFLAG
        success "UPDATE PENDING flag added to AGENTS.md"
    else
        warning "UPDATE PENDING flag already exists in AGENTS.md"
    fi
else
    warning "AGENTS.md not found, skipping flag"
fi

echo ""

# ───────────────────────────────────────────────────────────────────────────────
# STEP 14: COMPLETION SUMMARY
# ───────────────────────────────────────────────────────────────────────────────

log "Step 14: Completion Summary"

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                   UPDATE COMPLETE                              ║"
echo "╠════════════════════════════════════════════════════════════════╣"
echo "║  Version: $LOCAL_VERSION → $REMOTE_VERSION"
echo "║  Backup:  $BACKUP_DIR"
echo "╠════════════════════════════════════════════════════════════════╣"
echo "║  Results:                                                      ║"
printf "║    ✓ Successful:  %d%-30s║\n" "${#SUCCESSFUL_SKILLS[@]}" ""
printf "║    ✗ Failed:      %d%-30s║\n" "${#FAILED_SKILLS[@]}" ""
printf "║    ⊘ Unchanged:   %d%-30s║\n" "$SKILLS_UNCHANGED" ""
echo "╠════════════════════════════════════════════════════════════════╣"
echo "║  Next Steps:                                                   ║"
echo "║    1. Review changes above                                     ║"
echo "║    2. Run: openclaw gateway restart                            ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

if [ "$TELEGRAM_SENT" = true ]; then
    success "A notification was sent to your Telegram."
else
    warning "Check $NOTIFICATION_FILE for update details."
fi

echo ""
echo "Update log: $LOG_FILE"
echo ""

# Final status
if [ ${#FAILED_SKILLS[@]} -eq 0 ]; then
    success "All skills updated successfully!"
    exit 0
else
    error "Some skills failed to update. Check the log for details."
    exit 1
fi
