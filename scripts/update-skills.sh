#!/bin/bash
# OpenClaw Onboarding — Surgical Update Script
# Version: 2.0 | March 16, 2026
# Runs weekly (Sundays 2 AM) via cron, or manually triggered
#
# LOGIC:
# 1. Read CHANGELOG.md from GitHub — understand what's new
# 2. Compare against local version markers
# 3. Build gap list (new items, changed items)
# 4. Rate each item: LOW / MEDIUM / HIGH risk
# 5. Surface recommendations to user
# 6. Wait for user approval on MEDIUM/HIGH items
# 7. Apply only approved changes — surgical, additive only
#
# RULES:
# - NEVER overwrite: core .md files, company dept folders, custom SOPs
# - NEVER trigger a gateway restart
# - LOW risk items auto-apply (new files, nothing existing touched)
# - MEDIUM risk: recommend + confirm
# - HIGH risk: recommend SKIP + show diff + require explicit yes

REPO_URL="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main"
VPS_REPO_URL="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding-vps/main"
LOCAL_ONBOARDING_DIR=""
LOG_FILE="$HOME/.openclaw/skills/.update-log"
VERSION_FILE="$HOME/.openclaw/skills/.installed-versions"
CHANGELOG_CACHE="/tmp/openclaw-onboarding-changelog.md"
NEEDS_RESTART=false

# Detect environment
detect_environment() {
    if [ -d "$HOME/Downloads/openclaw-master-files/OpenClaw Onboarding" ]; then
        LOCAL_ONBOARDING_DIR="$HOME/Downloads/openclaw-master-files/OpenClaw Onboarding"
        ACTIVE_REPO_URL="$REPO_URL"
        echo "[INFO] Detected Mac environment"
    elif [ -d "$HOME/.openclaw/skills" ]; then
        LOCAL_ONBOARDING_DIR="$HOME/.openclaw/skills"
        ACTIVE_REPO_URL="$VPS_REPO_URL"
        echo "[INFO] Detected VPS environment"
    else
        echo "[ERROR] Cannot detect onboarding installation directory"
        exit 1
    fi
}

# Step 1: Read changelog from GitHub
fetch_changelog() {
    echo "[STEP 1] Fetching changelog from GitHub..."
    curl -fsSL "$ACTIVE_REPO_URL/CHANGELOG.md" -o "$CHANGELOG_CACHE" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "[ERROR] Could not fetch changelog. Network issue or repo unavailable."
        echo "$(date '+%Y-%m-%d %H:%M') — Update check failed: could not fetch changelog" >> "$LOG_FILE"
        exit 1
    fi
    echo "[OK] Changelog fetched"
}

# Step 2: Compare versions
compare_versions() {
    echo "[STEP 2] Comparing installed versions against changelog..."
    
    # Read local version markers
    if [ ! -f "$VERSION_FILE" ]; then
        echo "[INFO] No version file found. This appears to be a first-time check."
        echo "# Installed Versions — auto-generated" > "$VERSION_FILE"
    fi
    
    # Extract latest version from changelog
    LATEST_VERSION=$(grep -m1 "^## " "$CHANGELOG_CACHE" | sed 's/## //' | head -1)
    LOCAL_VERSION=$(head -2 "$VERSION_FILE" | tail -1 | sed 's/# Latest: //')
    
    echo "[INFO] Remote latest: $LATEST_VERSION"
    echo "[INFO] Local latest: ${LOCAL_VERSION:-none}"
    
    if [ "$LATEST_VERSION" = "$LOCAL_VERSION" ]; then
        echo "[OK] Already up to date. No changes needed."
        echo "$(date '+%Y-%m-%d %H:%M') — Update check: already up to date ($LATEST_VERSION)" >> "$LOG_FILE"
        exit 0
    fi
}

# Step 3: Build gap list
build_gap_list() {
    echo "[STEP 3] Building gap list..."
    
    GAP_REPORT="/tmp/openclaw-update-gap-report.md"
    echo "# Update Gap Report" > "$GAP_REPORT"
    echo "Generated: $(date '+%Y-%m-%d %H:%M')" >> "$GAP_REPORT"
    echo "Remote version: $LATEST_VERSION" >> "$GAP_REPORT"
    echo "Local version: ${LOCAL_VERSION:-none}" >> "$GAP_REPORT"
    echo "" >> "$GAP_REPORT"
    
    NEW_COUNT=0
    CHANGED_COUNT=0
    
    # Check each skill folder
    for skill_num in $(seq -w 1 31); do
        SKILL_DIR=$(find "$LOCAL_ONBOARDING_DIR" -maxdepth 1 -name "${skill_num}-*" -type d 2>/dev/null | head -1)
        
        if [ -z "$SKILL_DIR" ]; then
            # Skill not installed locally
            echo "- [NEW] Skill $skill_num: Not installed" >> "$GAP_REPORT"
            NEW_COUNT=$((NEW_COUNT + 1))
        else
            # Check for .version file
            LOCAL_VER=$(cat "$SKILL_DIR/.version" 2>/dev/null || echo "unknown")
            echo "- [INSTALLED] Skill $skill_num: v$LOCAL_VER" >> "$GAP_REPORT"
        fi
    done
    
    echo "" >> "$GAP_REPORT"
    echo "## Summary" >> "$GAP_REPORT"
    echo "- New skills to install: $NEW_COUNT" >> "$GAP_REPORT"
    echo "- Installed skills to check: $CHANGED_COUNT" >> "$GAP_REPORT"
    
    echo "[OK] Gap report built: $GAP_REPORT"
}

# Step 4: Impact analysis
run_impact_analysis() {
    echo "[STEP 4] Running impact analysis..."
    
    IMPACT_REPORT="/tmp/openclaw-update-impact.md"
    echo "# Impact Analysis" > "$IMPACT_REPORT"
    echo "" >> "$IMPACT_REPORT"
    
    # Protected files — NEVER overwrite
    PROTECTED_FILES="AGENTS.md MEMORY.md SOUL.md USER.md IDENTITY.md HEARTBEAT.md TOOLS.md"
    
    echo "## Protected Files (NEVER overwritten)" >> "$IMPACT_REPORT"
    for f in $PROTECTED_FILES; do
        echo "- $f — PROTECTED" >> "$IMPACT_REPORT"
    done
    
    echo "" >> "$IMPACT_REPORT"
    echo "## Company Department Folders — PROTECTED" >> "$IMPACT_REPORT"
    echo "Any folder inside 'my AI company departments' is client work. Never touch." >> "$IMPACT_REPORT"
    
    echo "[OK] Impact analysis complete: $IMPACT_REPORT"
}

# Step 5: Surface recommendations
surface_recommendations() {
    echo "[STEP 5] Generating recommendations..."
    echo ""
    echo "=========================================="
    echo "  OPENCLAW ONBOARDING UPDATE AVAILABLE"
    echo "=========================================="
    echo ""
    echo "Remote version: $LATEST_VERSION"
    echo "Your version: ${LOCAL_VERSION:-none}"
    echo ""
    echo "See gap report: $GAP_REPORT"
    echo "See impact report: $IMPACT_REPORT"
    echo ""
    echo "To review and apply updates, tell your AI assistant:"
    echo "  'Review the update reports and apply approved changes'"
    echo ""
    echo "=========================================="
    
    echo "$(date '+%Y-%m-%d %H:%M') — Update available: $LATEST_VERSION (current: ${LOCAL_VERSION:-none})" >> "$LOG_FILE"
}

# Main
detect_environment
fetch_changelog
compare_versions
build_gap_list
run_impact_analysis
surface_recommendations

echo ""
echo "[DONE] Update check complete. Reports generated for review."
echo "No changes have been made. Waiting for your approval."
