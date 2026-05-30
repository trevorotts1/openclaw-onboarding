#!/usr/bin/env bash
# 00-verify-prerequisites.sh — Skill 40 (ZHC Public Records Scraper)
# Verifies install prerequisites BEFORE any tier runs. Read-only. Idempotent.
# OS-aware Darwin + Linux. Governed by ../../QC-PROTOCOL.md (Category 10).

set -uo pipefail
OS="$(uname -s)"
case "$OS" in
  Darwin) DEFAULT_SKILLS_DIR="$HOME/.openclaw/skills"; DEFAULT_MFD="$HOME/Downloads" ;;
  Linux)  DEFAULT_SKILLS_DIR="/data/.openclaw/skills"; DEFAULT_MFD="/data" ;;
  *) echo "Unsupported OS: $OS"; exit 2 ;;
esac
SKILLS_DIR="${OPENCLAW_SKILLS_DIR:-$DEFAULT_SKILLS_DIR}"
MFD="${MASTER_FILES_DIR:-$DEFAULT_MFD}"
P="[skill 40][prereq]"
FAIL=0

# ---- A. MASTER_FILES_DIR (cache + event log live there) ----
if [ -d "$MFD" ]; then
  echo "$P OK — MASTER_FILES_DIR resolvable ($MFD)"
else
  echo "$P WARN: MASTER_FILES_DIR ($MFD) not present yet — 01-locate-master-files-folder.sh resolves/creates it."
fi

# ---- B. jq + curl (mandatory) ----
for bin in jq curl; do
  if command -v "$bin" >/dev/null 2>&1; then
    echo "$P OK — $bin present"
  else
    echo "$P BLOCKED: $bin not found on PATH (required for config JSON + robots/HTTP)"
    FAIL=1
  fi
done

# ---- C. Skill 39 (recommended — consumes Skill 40 output) ----
if [ -f "$SKILLS_DIR/39-real-estate-playbook/SKILL.md" ]; then
  echo "$P OK — Skill 39 (Real Estate Playbook) present (it consumes Skill 40 output for pre-foreclosure outreach)"
else
  echo "$P NOTE: Skill 39 not found — Skill 40 still works standalone, but pre-foreclosure pairing needs Skill 39."
fi

# ---- D. Headless browser (optional — for JS-rendered portals) ----
if command -v playwright >/dev/null 2>&1 || command -v chromium >/dev/null 2>&1 || command -v google-chrome >/dev/null 2>&1; then
  echo "$P OK — a headless browser is available (some Tier-1/2 portals are JS-rendered)"
else
  echo "$P NOTE: no headless browser detected — static fetch handles non-JS portals; install Playwright/Chromium for JS-rendered ones."
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "$P ALL MANDATORY PREREQUISITES PASS — proceed to 01-locate-master-files-folder.sh"
  exit 0
else
  echo "$P PREREQUISITES FAILED — fix the BLOCKED item(s), then re-run."
  exit 1
fi
