#!/usr/bin/env bash
# ============================================================
#  OpenClaw Onboarding — Check for Updates (READ-ONLY)
#  Compares local install against GitHub. NEVER installs anything.
#  Outputs structured JSON the cron agent reasons over.
#
#  Run via: curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/check-updates.sh | bash
#  Or directly: bash ~/.openclaw/skills/check-updates.sh
# ============================================================

set -u
SCRIPT_VERSION="1.0.0"

# ----------------------------------------------------------
# Detect platform (Mac vs VPS) — determines all paths
# ----------------------------------------------------------
if [ -d "/data/.openclaw" ]; then
  PLATFORM="vps"
  REPO_NAME="openclaw-onboarding-vps"
  SKILLS_DIR="/data/.openclaw/skills"
  MASTER_DIR="/data/Downloads/openclaw-master-files"
  WORKSPACE="/data/clawd"
else
  PLATFORM="mac"
  REPO_NAME="openclaw-onboarding"
  SKILLS_DIR="$HOME/.openclaw/skills"
  MASTER_DIR="$HOME/Downloads/openclaw-master-files"
  WORKSPACE="$HOME/clawd"
fi

# ----------------------------------------------------------
# Fetch helpers
# ----------------------------------------------------------
GH_RAW="https://raw.githubusercontent.com/trevorotts1/${REPO_NAME}/main"

fetch_remote() {
  # $1 = path relative to repo root. Returns content or empty on 404.
  curl -fsSL --max-time 15 "${GH_RAW}/$1" 2>/dev/null || echo ""
}

# ----------------------------------------------------------
# Read local state
# ----------------------------------------------------------
LOCAL_VERSION=""
if [ -f "$SKILLS_DIR/.onboarding-version" ]; then
  LOCAL_VERSION=$(tr -d '[:space:]' < "$SKILLS_DIR/.onboarding-version")
fi

# Build local skill version map
LOCAL_SKILLS_TMP=$(mktemp)
if [ -d "$SKILLS_DIR" ]; then
  for d in "$SKILLS_DIR"/[0-9]*; do
    [ -d "$d" ] || continue
    name=$(basename "$d")
    case "$name" in *ARCHIVED*) continue ;; esac
    ver=""
    [ -f "$d/skill-version.txt" ] && ver=$(tr -d '[:space:]' < "$d/skill-version.txt")
    echo "$name|$ver" >> "$LOCAL_SKILLS_TMP"
  done
fi

# ----------------------------------------------------------
# Fetch remote state
# ----------------------------------------------------------
LATEST_VERSION=$(fetch_remote version | tr -d '[:space:]')
LATEST_CHANGELOG=$(fetch_remote CHANGELOG.md)

# Pull just the most recent changelog entry (top section until next heading).
# Matches BOTH heading formats used historically:
#   ## v10.6.2 — ...        (older entries)
#   ## [v10.7.0] — ...      (current bracketed style, since v10.6.2 release)
LATEST_ENTRY=""
if [ -n "$LATEST_CHANGELOG" ]; then
  LATEST_ENTRY=$(echo "$LATEST_CHANGELOG" | awk '
    /^## (\[v|v)/ {
      if (count == 0) { count=1; print; next }
      else { exit }
    }
    count == 1 { print }
  ')
fi

# Pull risk hint if changelog uses "### Risk: low|medium|high" tag
RISK_HINT=""
if [ -n "$LATEST_ENTRY" ]; then
  RISK_HINT=$(echo "$LATEST_ENTRY" | grep -iE "^### Risk:" | head -1 | sed -E 's/^### Risk:[[:space:]]*//I' | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
fi

# ----------------------------------------------------------
# Fetch the remote skill manifest (list of skill folders + their versions)
# We hit the GitHub git/trees API for a one-shot listing
# ----------------------------------------------------------
REMOTE_SKILLS_TMP=$(mktemp)
TREE_JSON=$(curl -fsSL --max-time 15 "https://api.github.com/repos/trevorotts1/${REPO_NAME}/git/trees/main" 2>/dev/null)
if [ -n "$TREE_JSON" ]; then
  echo "$TREE_JSON" | python3 -c "
import json,sys,re
try:
    d=json.load(sys.stdin)
    for t in d.get('tree',[]):
        n=t.get('path','')
        if t.get('type')=='tree' and re.match(r'^[0-9]+-', n) and 'ARCHIVED' not in n:
            print(n)
except: pass
" 2>/dev/null > "${REMOTE_SKILLS_TMP}.names"

  # For each remote skill, fetch its skill-version.txt
  while IFS= read -r skill_name; do
    [ -z "$skill_name" ] && continue
    remote_ver=$(curl -fsSL --max-time 10 "${GH_RAW}/${skill_name}/skill-version.txt" 2>/dev/null | tr -d '[:space:]')
    echo "${skill_name}|${remote_ver}" >> "$REMOTE_SKILLS_TMP"
  done < "${REMOTE_SKILLS_TMP}.names"
  rm -f "${REMOTE_SKILLS_TMP}.names"
fi

# ----------------------------------------------------------
# Compose skill_changes array
# ----------------------------------------------------------
SKILL_CHANGES_JSON=""
HAS_SKILL_UPDATES="false"

if [ -s "$REMOTE_SKILLS_TMP" ]; then
  while IFS='|' read -r remote_name remote_ver; do
    [ -z "$remote_name" ] && continue
    local_ver=$(grep "^${remote_name}|" "$LOCAL_SKILLS_TMP" 2>/dev/null | cut -d'|' -f2 | head -1)
    is_new="false"
    has_upd="false"
    if [ -z "$local_ver" ]; then
      is_new="true"
      has_upd="true"
      HAS_SKILL_UPDATES="true"
    elif [ "$local_ver" != "$remote_ver" ]; then
      has_upd="true"
      HAS_SKILL_UPDATES="true"
    fi
    if [ -n "$SKILL_CHANGES_JSON" ]; then SKILL_CHANGES_JSON="$SKILL_CHANGES_JSON,"; fi
    SKILL_CHANGES_JSON="${SKILL_CHANGES_JSON}{\"name\":\"${remote_name}\",\"local\":\"${local_ver}\",\"latest\":\"${remote_ver}\",\"is_new\":${is_new},\"has_update\":${has_upd}}"
  done < "$REMOTE_SKILLS_TMP"
fi

# ----------------------------------------------------------
# Compose final JSON
# ----------------------------------------------------------
HAS_REPO_UPDATE="false"
if [ -n "$LATEST_VERSION" ] && [ "$LOCAL_VERSION" != "$LATEST_VERSION" ]; then
  HAS_REPO_UPDATE="true"
fi

# Escape changelog excerpt for JSON
LATEST_ENTRY_JSON=$(printf '%s' "$LATEST_ENTRY" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null)
[ -z "$LATEST_ENTRY_JSON" ] && LATEST_ENTRY_JSON='""'

cat <<JSON
{
  "script_version": "${SCRIPT_VERSION}",
  "repo": "${REPO_NAME}",
  "platform": "${PLATFORM}",
  "checked_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "local_version": "${LOCAL_VERSION}",
  "latest_version": "${LATEST_VERSION}",
  "has_repo_update": ${HAS_REPO_UPDATE},
  "has_skill_updates": ${HAS_SKILL_UPDATES},
  "risk_hint": "${RISK_HINT}",
  "changelog_excerpt": ${LATEST_ENTRY_JSON},
  "skill_changes": [${SKILL_CHANGES_JSON}]
}
JSON

# Cleanup
rm -f "$LOCAL_SKILLS_TMP" "$REMOTE_SKILLS_TMP"

# Mark when this check ran (for catchup detection in update-skills.sh)
mkdir -p "$(dirname "$SKILLS_DIR/.last-update-check")"
date -u +%Y-%m-%dT%H:%M:%SZ > "$SKILLS_DIR/.last-update-check" 2>/dev/null || true

# ----------------------------------------------------------
# N22 (triple-fire trigger, detection-side) — write the AGENTS.md flag
# whenever an update is detected. This fires on DETECTION, NOT only on
# force-update apply. The flag remains until the user replies (via the
# Sunday cron Telegram flow) or until next Sunday's check clears it.
# v10.12.0 P20.1: prior versions only wrote this flag from force-update.sh.
# ----------------------------------------------------------
if [ "$HAS_REPO_UPDATE" = "true" ] || [ "$HAS_SKILL_UPDATES" = "true" ]; then
  if [ "$PLATFORM" = "vps" ]; then
    AGENTS_MD="/data/.openclaw/AGENTS.md"
  else
    AGENTS_MD="$HOME/.openclaw/AGENTS.md"
  fi
  mkdir -p "$(dirname "$AGENTS_MD")" 2>/dev/null || true
  flag_marker="<!-- OPENCLAW_UPDATE_DETECTED:${LATEST_VERSION}:$(date -u +%Y-%m-%dT%H:%M:%SZ) -->"
  if [ -f "$AGENTS_MD" ] && grep -qF "OPENCLAW_UPDATE_DETECTED:${LATEST_VERSION}" "$AGENTS_MD" 2>/dev/null; then
    : # already flagged for this version
  else
    {
      echo ""
      echo "$flag_marker"
      echo "## OpenClaw update detected: ${LATEST_VERSION} (from ${LOCAL_VERSION})"
      echo "Repo: ${REPO_NAME}"
      echo "Risk hint: ${RISK_HINT:-unknown}"
      echo "Detected at $(date -u +%Y-%m-%dT%H:%M:%SZ) by check-updates.sh"
      echo "Status: PENDING_USER_REPLY — awaiting Telegram reply per Sunday cron RULE 6."
      echo "<!-- OPENCLAW_UPDATE_DETECTED_END -->"
    } >> "$AGENTS_MD" 2>/dev/null || true
  fi
fi
