#!/bin/bash
# OpenClaw Onboarding — Surgical Update Script
# Version: 3.0 | March 19, 2026
# Works on ANY Mac Mini client machine
#
# Run via:
#   curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/scripts/update-skills.sh | bash
#
# SAFETY PROTOCOLS:
# 1. Backs up core .md files and config BEFORE touching anything
# 2. Smart folder detection (searches multiple locations)
# 3. Version comparison against GitHub
# 4. Gap report with risk ratings
# 5. Displays plan and waits for user approval
# 6. Downloads only changed files
# 7. Verification checklist after completion
# 8. NEVER triggers a gateway restart — asks user to do it
#
# PROTECTED — NEVER OVERWRITTEN:
# - Company department folders
# - secrets/, .env files, credentials
# - Custom SOPs or client work

set -euo pipefail

REPO_URL="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main"
REPO_ZIP="https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip"
LOCAL_ONBOARDING_DIR=""
LOG_FILE="$HOME/.openclaw/skills/.update-log"
CHANGELOG_CACHE="/tmp/openclaw-onboarding-changelog.md"
BACKUP_DIR=""
LATEST_VERSION=""
LOCAL_VERSION=""
QMD_DETECTED=false
TEMP_DIR="/tmp/openclaw-update-$$"
SELF_SCRIPT_RAW_URL="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/scripts/update-skills.sh"
INTERACTIVE=false
if [ -t 0 ] && [ -t 1 ]; then
    INTERACTIVE=true
fi

mkdir -p "$HOME/.openclaw/skills" 2>/dev/null

echo ""
echo "============================================"
echo "  OpenClaw Onboarding Update Script v3.0"
echo "============================================"
echo ""
if [ "$INTERACTIVE" = false ]; then
    echo "⚠️  IMPORTANT: This updater may need your approval before it can make changes."
    echo "   Because you ran it in non-interactive mode (for example: curl ... | bash),"
    echo "   it cannot ask you the yes/no question directly."
    echo "   It will still analyze safely, then stop with exact rerun instructions if approval is needed."
    echo ""
fi

# ----------------------------------------------------------
# STEP 1: BACKUP PROTOCOL — runs before anything else
# ----------------------------------------------------------
step_backup() {
    echo "[STEP 1/7] Running backup protocol..."
    
    # Find or create backup folder
    BACKUP_DIR=""
    FOUND=$(find "$HOME/Downloads" -maxdepth 1 -type d -iname "*openclaw*backup*" 2>/dev/null | head -1)
    if [ -n "$FOUND" ]; then
        BACKUP_DIR="$FOUND"
    elif [ -d "$HOME/Downloads/backups" ]; then
        BACKUP_DIR="$HOME/Downloads/backups"
    elif [ -d "$HOME/Downloads/backup" ]; then
        BACKUP_DIR="$HOME/Downloads/backup"
    else
        BACKUP_DIR="$HOME/Downloads/openclaw-backups"
        mkdir -p "$BACKUP_DIR"
    fi
    
    # Create timestamped backup subfolder
    TIMESTAMP=$(date +%Y-%m-%d-%H%M)
    UPDATE_BACKUP="$BACKUP_DIR/pre-update-backup-$TIMESTAMP"
    mkdir -p "$UPDATE_BACKUP"
    
    # Backup config
    if [ -f "$HOME/.openclaw/openclaw.json" ]; then
        cp "$HOME/.openclaw/openclaw.json" "$UPDATE_BACKUP/openclaw.json" 2>/dev/null
        echo "  ✅ Config backed up"
    fi
    
    # Backup core .md files from workspace
    WORKSPACE=$(grep -o '"workspace"[[:space:]]*:[[:space:]]*"[^"]*"' "$HOME/.openclaw/openclaw.json" 2>/dev/null | head -1 | sed 's/.*"workspace"[[:space:]]*:[[:space:]]*"//' | sed 's/"//')
    if [ -z "$WORKSPACE" ]; then
        # Try common locations
        if [ -d "$HOME/clawd" ]; then
            WORKSPACE="$HOME/clawd"
        elif [ -d "$HOME/.openclaw/workspace" ]; then
            WORKSPACE="$HOME/.openclaw/workspace"
        fi
    fi
    
    if [ -n "$WORKSPACE" ] && [ -d "$WORKSPACE" ]; then
        for f in AGENTS.md MEMORY.md TOOLS.md USER.md IDENTITY.md SOUL.md HEARTBEAT.md; do
            if [ -f "$WORKSPACE/$f" ]; then
                cp "$WORKSPACE/$f" "$UPDATE_BACKUP/$f" 2>/dev/null
            fi
        done
        echo "  ✅ Core .md files backed up"
    fi
    
    # Verify backup is not empty
    FILE_COUNT=$(find "$UPDATE_BACKUP" -type f | wc -l | tr -d ' ')
    if [ "$FILE_COUNT" -eq 0 ]; then
        echo "  ⚠️  WARNING: Backup folder is empty. Proceeding with caution."
    else
        echo "  ✅ Backup complete: $FILE_COUNT files in $UPDATE_BACKUP"
    fi
    echo ""
}

# ----------------------------------------------------------
# STEP 2: SMART FOLDER DETECTION
# ----------------------------------------------------------
step_detect_folder() {
    echo "[STEP 2/7] Looking for onboarding folder..."
    
    # Search in order of likelihood
    SEARCH_PATHS=(
        "$HOME/.openclaw/onboarding"
        "$HOME/Downloads/openclaw-master-files/OpenClaw Onboarding"
        "$HOME/Downloads/OpenClaw Onboarding"
        "$HOME/Downloads/openclaw-onboarding"
    )
    
    for path in "${SEARCH_PATHS[@]}"; do
        if [ -d "$path" ] && [ -f "$path/Start Here.md" -o -f "$path/CHANGELOG.md" ]; then
            LOCAL_ONBOARDING_DIR="$path"
            echo "  ✅ Found: $LOCAL_ONBOARDING_DIR"
            echo ""
            return
        fi
    done
    
    # Deep search as fallback
    echo "  Searching ~/Downloads/ recursively..."
    FOUND_PATH=$(find "$HOME/Downloads" -maxdepth 3 -name "Start Here.md" -type f 2>/dev/null | head -1)
    if [ -n "$FOUND_PATH" ]; then
        LOCAL_ONBOARDING_DIR=$(dirname "$FOUND_PATH")
        echo "  ✅ Found: $LOCAL_ONBOARDING_DIR"
        echo ""
        return
    fi
    
    # Check ~/.openclaw/onboarding even without Start Here.md
    if [ -d "$HOME/.openclaw/onboarding" ]; then
        LOCAL_ONBOARDING_DIR="$HOME/.openclaw/onboarding"
        echo "  ✅ Found: $LOCAL_ONBOARDING_DIR"
        echo ""
        return
    fi
    
    echo ""
    echo "  ❌ ERROR: Cannot find onboarding folder."
    echo ""
    echo "  Looked in:"
    for path in "${SEARCH_PATHS[@]}"; do
        echo "    - $path"
    done
    echo "    - ~/Downloads/ (recursive search)"
    echo ""
    echo "  If this is a first-time install, run:"
    echo "    curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash"
    echo ""
    exit 1
}

# ----------------------------------------------------------
# STEP 3: VERSION DETECTION
# ----------------------------------------------------------
step_detect_version() {
    echo "[STEP 3/7] Detecting versions..."
    
    # Get local version
    if [ -f "$HOME/.openclaw/skills/.onboarding-version" ]; then
        LOCAL_VERSION=$(cat "$HOME/.openclaw/skills/.onboarding-version" 2>/dev/null | tr -d '[:space:]')
    elif [ -f "$LOCAL_ONBOARDING_DIR/.onboarding-version" ]; then
        LOCAL_VERSION=$(cat "$LOCAL_ONBOARDING_DIR/.onboarding-version" 2>/dev/null | tr -d '[:space:]')
    elif [ -f "$LOCAL_ONBOARDING_DIR/CHANGELOG.md" ]; then
        LOCAL_VERSION=$(grep -m1 '^\#\# \[v' "$LOCAL_ONBOARDING_DIR/CHANGELOG.md" 2>/dev/null | sed 's/## \[//' | sed 's/\].*//' | tr -d '[:space:]')
    fi
    
    if [ -z "$LOCAL_VERSION" ]; then
        LOCAL_VERSION="unknown (pre-v1.0.0)"
    fi
    
    # Get remote version from GitHub
    curl -fsSL -H "Cache-Control: no-cache" "$REPO_URL/CHANGELOG.md?cb=$(date +%s)" -o "$CHANGELOG_CACHE" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "  ❌ ERROR: Could not fetch changelog from GitHub."
        echo "  Check your internet connection."
        exit 1
    fi
    
    LATEST_VERSION=$(grep -m1 '^\#\# \[v' "$CHANGELOG_CACHE" | sed 's/## \[//' | sed 's/\].*//' | tr -d '[:space:]')
    
    echo "  Your version:   $LOCAL_VERSION"
    echo "  Latest version:  $LATEST_VERSION"
    echo ""
    
    if [ "$LOCAL_VERSION" = "$LATEST_VERSION" ]; then
        echo "  ✅ You're already up to date!"
        echo ""
        echo "$(date '+%Y-%m-%d %H:%M') — Update check: already up to date ($LATEST_VERSION)" >> "$LOG_FILE"
        exit 0
    fi
}

# ----------------------------------------------------------
# STEP 4: GAP REPORT
# ----------------------------------------------------------
step_gap_report() {
    echo "[STEP 4/7] Building gap report..."
    echo ""
    
    # Count local skills
    LOCAL_SKILL_COUNT=$(find "$LOCAL_ONBOARDING_DIR" -maxdepth 1 -type d -name "[0-9]*-*" 2>/dev/null | wc -l | tr -d ' ')
    
    # Download latest to temp for comparison
    mkdir -p "$TEMP_DIR"
    curl -fsSL -H "Cache-Control: no-cache" "$REPO_ZIP?cb=$(date +%s)" -o "$TEMP_DIR/latest.zip" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "  ❌ ERROR: Could not download latest version."
        exit 1
    fi
    unzip -qo "$TEMP_DIR/latest.zip" -d "$TEMP_DIR" 2>/dev/null
    REMOTE_DIR="$TEMP_DIR/openclaw-onboarding-main"
    
    REMOTE_SKILL_COUNT=$(find "$REMOTE_DIR" -maxdepth 1 -type d -name "[0-9]*-*" 2>/dev/null | wc -l | tr -d ' ')
    
    echo "  Local skills:  $LOCAL_SKILL_COUNT"
    echo "  Remote skills: $REMOTE_SKILL_COUNT"
    echo ""
    
    # Find new skills
    NEW_SKILLS=""
    CHANGED_SKILLS=""
    
    for remote_skill in $(find "$REMOTE_DIR" -maxdepth 1 -type d -name "[0-9]*-*" -exec basename {} \; 2>/dev/null | sort); do
        skill_num=$(echo "$remote_skill" | grep -o '^[0-9]*')
        local_match=$(find "$LOCAL_ONBOARDING_DIR" -maxdepth 1 -type d -name "${skill_num}-*" 2>/dev/null | head -1)
        
        if [ -z "$local_match" ]; then
            echo "  📦 NEW:     $remote_skill"
            NEW_SKILLS="$NEW_SKILLS $remote_skill"
        else
            # Compare file counts and sizes to detect changes
            local_size=$(du -s "$local_match" 2>/dev/null | cut -f1)
            remote_size=$(du -s "$REMOTE_DIR/$remote_skill" 2>/dev/null | cut -f1)
            if [ "$local_size" != "$remote_size" ]; then
                echo "  🔄 CHANGED: $remote_skill (local: ${local_size}KB, remote: ${remote_size}KB)"
                CHANGED_SKILLS="$CHANGED_SKILLS $remote_skill"
            fi
        fi
    done
    
    # Check for changed infrastructure files
    CHANGED_INFRA=""
    for infra_file in CHANGELOG.md CONTRIBUTING.md MIGRATION.md "Start Here.md" README.md; do
        if [ -f "$REMOTE_DIR/$infra_file" ]; then
            if [ -f "$LOCAL_ONBOARDING_DIR/$infra_file" ]; then
                local_hash=$(md5 -q "$LOCAL_ONBOARDING_DIR/$infra_file" 2>/dev/null || md5sum "$LOCAL_ONBOARDING_DIR/$infra_file" 2>/dev/null | cut -d' ' -f1)
                remote_hash=$(md5 -q "$REMOTE_DIR/$infra_file" 2>/dev/null || md5sum "$REMOTE_DIR/$infra_file" 2>/dev/null | cut -d' ' -f1)
                if [ "$local_hash" != "$remote_hash" ]; then
                    echo "  📄 UPDATED: $infra_file"
                    CHANGED_INFRA="$CHANGED_INFRA $infra_file"
                fi
            else
                echo "  📄 NEW:     $infra_file"
                CHANGED_INFRA="$CHANGED_INFRA $infra_file"
            fi
        fi
    done
    
    # Check scripts folder
    if [ -d "$REMOTE_DIR/scripts" ]; then
        for script_file in $(find "$REMOTE_DIR/scripts" -type f -exec basename {} \; 2>/dev/null); do
            if [ ! -f "$LOCAL_ONBOARDING_DIR/scripts/$script_file" ]; then
                echo "  📄 NEW:     scripts/$script_file"
                CHANGED_INFRA="$CHANGED_INFRA scripts/$script_file"
            fi
        done
    fi
    
    if [ -z "$NEW_SKILLS" ] && [ -z "$CHANGED_SKILLS" ] && [ -z "$CHANGED_INFRA" ]; then
        echo "  ✅ No file-level changes detected (version marker may just need updating)."
    fi
    
    echo ""
}

# ----------------------------------------------------------
# STEP 5: IMPACT ANALYSIS AND APPROVAL
# ----------------------------------------------------------
step_approval() {
    echo "[STEP 5/7] Impact analysis..."
    echo ""
    echo "=========================================="
    echo "  UPDATE PLAN: $LOCAL_VERSION → $LATEST_VERSION"
    echo "=========================================="
    echo ""
    
    TOTAL_CHANGES=0
    
    if [ -n "$NEW_SKILLS" ]; then
        echo "  LOW RISK — New skills to install:"
        for s in $NEW_SKILLS; do
            echo "    ✅ $s (new files only, nothing overwritten)"
            TOTAL_CHANGES=$((TOTAL_CHANGES + 1))
        done
        echo ""
    fi
    
    if [ -n "$CHANGED_SKILLS" ]; then
        echo "  MEDIUM RISK — Skills with changes:"
        for s in $CHANGED_SKILLS; do
            echo "    🔄 $s (skill files updated, core .md NOT touched)"
            TOTAL_CHANGES=$((TOTAL_CHANGES + 1))
        done
        echo ""
    fi
    
    if [ -n "$CHANGED_INFRA" ]; then
        echo "  LOW RISK — Infrastructure updates:"
        for f in $CHANGED_INFRA; do
            echo "    📄 $f"
            TOTAL_CHANGES=$((TOTAL_CHANGES + 1))
        done
        echo ""
    fi
    
    # Check for QMD legacy
    if [ -f "$HOME/.openclaw/openclaw.json" ]; then
        if grep -q '"backend".*"qmd"' "$HOME/.openclaw/openclaw.json" 2>/dev/null; then
            echo "  ⚠️  HIGH RISK — Legacy QMD system detected in config"
            echo "     The update includes migration from QMD to Gemini Embedding 2."
            echo "     Review MIGRATION.md after update completes."
            echo ""
        fi
    fi
    
    echo "  PROTECTED (will NOT be touched):"
    echo "    🔒 Core .md files (AGENTS.md, MEMORY.md, etc.)"
    echo "    🔒 Company department folders"
    echo "    🔒 secrets/, .env, credentials"
    echo "    🔒 Gateway will NOT be restarted"
    echo ""
    echo "  Total changes: $TOTAL_CHANGES"
    echo "  Backup saved to: $UPDATE_BACKUP"
    echo ""
    echo "=========================================="
    echo ""
    
    if [ "$INTERACTIVE" = false ]; then
        echo "  Approval is required before this updater can make changes."
        echo ""
        echo "  You ran the updater in non-interactive mode, so it cannot safely ask you"
        echo "  the yes/no approval question here."
        echo ""
        echo "  Result: no changes were made."
        echo "  Your backup is saved at: $UPDATE_BACKUP"
        echo ""
        echo "  Run these exact 2 commands instead:"
        echo ""
        echo "    curl -fsSL $SELF_SCRIPT_RAW_URL -o /tmp/update-skills.sh"
        echo "    bash /tmp/update-skills.sh"
        echo ""
        echo "  Then when you see the approval question, type: y"
        echo ""
        echo "$(date '+%Y-%m-%d %H:%M') — Update paused for interactive approval ($LOCAL_VERSION → $LATEST_VERSION)" >> "$LOG_FILE"
        rm -rf "$TEMP_DIR"
        exit 0
    fi
    if [ "$TOTAL_CHANGES" -eq 0 ]; then
        echo "  No file changes need to be applied. This will only update the version marker."
        echo ""
        read -r -p "  Update version marker to $LATEST_VERSION? (y/n): " CONFIRM
    else
        read -r -p "  Apply these changes now? (y/n): " CONFIRM
    fi
    if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ] && [ "$CONFIRM" != "yes" ]; then
        echo ""
        echo "  Update cancelled by user. No changes were made."
        echo "  Your backup is at: $UPDATE_BACKUP"
        echo ""
        echo "$(date '+%Y-%m-%d %H:%M') — Update cancelled by user ($LOCAL_VERSION → $LATEST_VERSION)" >> "$LOG_FILE"
        rm -rf "$TEMP_DIR"
        exit 0
    fi
    echo ""
}

# ----------------------------------------------------------
# STEP 6: APPLY CHANGES
# ----------------------------------------------------------
step_apply() {
    echo "[STEP 6/7] Applying approved changes..."
    echo ""
    
    APPLIED=0
    ERRORS=0
    
    # Apply new skills
    for s in $NEW_SKILLS; do
        if [ -d "$REMOTE_DIR/$s" ]; then
            cp -r "$REMOTE_DIR/$s" "$LOCAL_ONBOARDING_DIR/$s" 2>/dev/null
            if [ $? -eq 0 ]; then
                echo "  ✅ Installed: $s"
                APPLIED=$((APPLIED + 1))
            else
                echo "  ❌ FAILED: $s"
                ERRORS=$((ERRORS + 1))
            fi
        fi
    done
    
    # Apply changed skills (overwrite skill files only)
    for s in $CHANGED_SKILLS; do
        if [ -d "$REMOTE_DIR/$s" ]; then
            # Remove old skill folder and replace
            local_match=$(find "$LOCAL_ONBOARDING_DIR" -maxdepth 1 -type d -name "$(echo $s | grep -o '^[0-9]*')-*" 2>/dev/null | head -1)
            if [ -n "$local_match" ]; then
                rm -rf "$local_match"
            fi
            cp -r "$REMOTE_DIR/$s" "$LOCAL_ONBOARDING_DIR/$s" 2>/dev/null
            if [ $? -eq 0 ]; then
                echo "  ✅ Updated: $s"
                APPLIED=$((APPLIED + 1))
            else
                echo "  ❌ FAILED: $s"
                ERRORS=$((ERRORS + 1))
            fi
        fi
    done
    
    # Apply infrastructure files
    for f in $CHANGED_INFRA; do
        if [[ "$f" == scripts/* ]]; then
            mkdir -p "$LOCAL_ONBOARDING_DIR/scripts" 2>/dev/null
            cp "$REMOTE_DIR/$f" "$LOCAL_ONBOARDING_DIR/$f" 2>/dev/null
        elif [ -f "$REMOTE_DIR/$f" ]; then
            cp "$REMOTE_DIR/$f" "$LOCAL_ONBOARDING_DIR/$f" 2>/dev/null
        fi
        if [ $? -eq 0 ]; then
            echo "  ✅ Updated: $f"
            APPLIED=$((APPLIED + 1))
        else
            echo "  ❌ FAILED: $f"
            ERRORS=$((ERRORS + 1))
        fi
    done
    

    # Validate config if it was touched
    if [ -f "$HOME/.openclaw/openclaw.json" ]; then
        if command -v openclaw &>/dev/null; then
            VALIDATE_RESULT=$(openclaw config validate 2>&1)
            if echo "$VALIDATE_RESULT" | grep -qi "invalid"; then
                echo "  ⚠️  WARNING: Config validation failed after update!"
                echo "  $VALIDATE_RESULT"
                echo "  DO NOT RESTART until this is resolved."
                echo ""
            else
                echo "  ✅ Config validation passed"
            fi
        fi
    fi

    # Update version marker
    echo "$LATEST_VERSION" > "$HOME/.openclaw/skills/.onboarding-version" 2>/dev/null
    echo "$LATEST_VERSION" > "$LOCAL_ONBOARDING_DIR/.onboarding-version" 2>/dev/null
    
    echo ""
    echo "  Applied: $APPLIED changes"
    if [ "$ERRORS" -gt 0 ]; then
        echo "  ❌ Errors: $ERRORS (check above for details)"
    fi
    echo ""
}

# ----------------------------------------------------------
# STEP 7: VERIFICATION
# ----------------------------------------------------------
step_verify() {
    echo "[STEP 7/7] Verifying update..."
    echo ""
    
    PASS=true
    
    # Check version marker
    INSTALLED_VER=$(cat "$HOME/.openclaw/skills/.onboarding-version" 2>/dev/null | tr -d '[:space:]')
    if [ "$INSTALLED_VER" = "$LATEST_VERSION" ]; then
        echo "  ✅ Version marker: $INSTALLED_VER"
    else
        echo "  ❌ Version marker mismatch: expected $LATEST_VERSION, got ${INSTALLED_VER:-none}"
        PASS=false
    fi
    
    # Count skills
    FINAL_SKILL_COUNT=$(find "$LOCAL_ONBOARDING_DIR" -maxdepth 1 -type d -name "[0-9]*-*" 2>/dev/null | wc -l | tr -d ' ')
    echo "  ✅ Skills installed: $FINAL_SKILL_COUNT"
    
    # Verify core .md files were not touched
    if [ -n "$WORKSPACE" ] && [ -d "$WORKSPACE" ]; then
        CORE_OK=true
        for f in AGENTS.md MEMORY.md TOOLS.md USER.md IDENTITY.md SOUL.md HEARTBEAT.md; do
            if [ -f "$UPDATE_BACKUP/$f" ] && [ -f "$WORKSPACE/$f" ]; then
                backup_hash=$(md5 -q "$UPDATE_BACKUP/$f" 2>/dev/null || md5sum "$UPDATE_BACKUP/$f" 2>/dev/null | cut -d' ' -f1)
                current_hash=$(md5 -q "$WORKSPACE/$f" 2>/dev/null || md5sum "$WORKSPACE/$f" 2>/dev/null | cut -d' ' -f1)
                if [ "$backup_hash" != "$current_hash" ]; then
                    echo "  ⚠️  WARNING: $f was modified during update!"
                    CORE_OK=false
                fi
            fi
        done
        if [ "$CORE_OK" = true ]; then
            echo "  ✅ Core .md files: untouched"
        fi
    fi
    
    # Check if restart is needed
    RESTART_NEEDED=false
    if [ -n "$NEW_SKILLS" ] || [ -n "$CHANGED_SKILLS" ]; then
        # Check if any skill has config changes
        for s in $NEW_SKILLS $CHANGED_SKILLS; do
            if [ -f "$LOCAL_ONBOARDING_DIR/$s/INSTALL.md" ]; then
                if grep -qi 'openclaw.json\|gateway restart\|config change\|env var' "$LOCAL_ONBOARDING_DIR/$s/INSTALL.md" 2>/dev/null; then
                    RESTART_NEEDED=true
                    break
                fi
            fi
        done
    fi
    
    echo ""
    echo "=========================================="
    echo "  UPDATE COMPLETE"
    echo "=========================================="
    echo ""
    echo "  Version: $LOCAL_VERSION → $LATEST_VERSION"
    echo "  Backup:  $UPDATE_BACKUP"
    echo ""
    
    if [ "$RESTART_NEEDED" = true ]; then
        echo "  ⚠️  RESTART RECOMMENDED"
        echo "  Some updated skills may require config changes."
        echo "  Tell your AI agent to review the updated skills,"
        echo "  then type /restart in Telegram when ready."
        echo ""
    fi
    
    echo "  To tell your AI agent about the update, send:"
    echo "    'The onboarding package was updated from $LOCAL_VERSION"
    echo "     to $LATEST_VERSION. Review the CHANGELOG.md in"
    echo "     $LOCAL_ONBOARDING_DIR and apply any config"
    echo "     changes that new or updated skills require.'"
    echo ""
    echo "=========================================="
    echo ""
    
    # Log
    echo "$(date '+%Y-%m-%d %H:%M') — Updated $LOCAL_VERSION → $LATEST_VERSION ($APPLIED changes applied, $ERRORS errors)" >> "$LOG_FILE"
    
    # Cleanup
    rm -rf "$TEMP_DIR"
}

# ----------------------------------------------------------
# MAIN
# ----------------------------------------------------------
step_backup
step_detect_folder
step_detect_version
step_gap_report
step_approval
step_apply
step_verify
