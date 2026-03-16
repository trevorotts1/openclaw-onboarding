#!/bin/bash
# OpenClaw Onboarding — Impact Check Helper
# Version: 1.0 | March 16, 2026
#
# Checks a specific skill or file for update impact.
# Used by the AI agent to determine risk level before applying changes.
#
# Usage: bash check-update-impact.sh <skill-number-or-path>
#
# Risk Levels:
# LOW    — New file, nothing existing touched. Safe to auto-apply.
# MEDIUM — Existing file updated, client has NOT customized it. Recommend + confirm.
# HIGH   — Existing file updated AND client has customized it. Recommend SKIP.

TARGET="$1"

if [ -z "$TARGET" ]; then
    echo "Usage: bash check-update-impact.sh <skill-number-or-path>"
    echo ""
    echo "Examples:"
    echo "  bash check-update-impact.sh 23"
    echo "  bash check-update-impact.sh /path/to/file.md"
    exit 1
fi

# Protected files — always HIGH risk
PROTECTED="AGENTS.md MEMORY.md SOUL.md USER.md IDENTITY.md HEARTBEAT.md TOOLS.md"

for p in $PROTECTED; do
    if echo "$TARGET" | grep -q "$p"; then
        echo "RISK: HIGH"
        echo "REASON: $p is a protected core file. NEVER overwrite."
        echo "RECOMMENDATION: SKIP — do not update this file."
        exit 0
    fi
done

# Check if target is inside company departments folder
if echo "$TARGET" | grep -qi "my AI company departments"; then
    echo "RISK: HIGH"
    echo "REASON: This file is inside the client's company departments folder."
    echo "RECOMMENDATION: SKIP — this is client-created content. Never overwrite."
    exit 0
fi

# Check if file exists locally
if [ -f "$TARGET" ]; then
    # File exists — check if it's been modified from original
    LOCAL_HASH=$(md5 -q "$TARGET" 2>/dev/null || md5sum "$TARGET" 2>/dev/null | cut -d' ' -f1)
    
    # Check .version file in parent directory
    PARENT_DIR=$(dirname "$TARGET")
    if [ -f "$PARENT_DIR/.version" ]; then
        echo "RISK: MEDIUM"
        echo "REASON: File exists locally with version marker."
        echo "LOCAL_HASH: $LOCAL_HASH"
        echo "RECOMMENDATION: Compare hashes. If unchanged from original, safe to update. If modified, show diff first."
    else
        echo "RISK: MEDIUM"
        echo "REASON: File exists locally but no version marker found."
        echo "LOCAL_HASH: $LOCAL_HASH"
        echo "RECOMMENDATION: Ask user before updating. File may have been customized."
    fi
else
    echo "RISK: LOW"
    echo "REASON: File does not exist locally. This is a new addition."
    echo "RECOMMENDATION: Safe to add. No existing content will be affected."
fi
