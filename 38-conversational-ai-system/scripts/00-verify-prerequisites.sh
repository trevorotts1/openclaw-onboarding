#!/usr/bin/env bash
# 00-verify-prerequisites.sh — Skill 38 (Conversational AI System)
# Verifies that skills 05, 10, 19, 29 are installed BEFORE any v5.14 setup step runs.
# Idempotent: only reads state, never writes. Safe to re-run.
# OS-aware: Darwin + Linux. Uses semantic discovery of the skills dir.

set -euo pipefail

OS="$(uname -s)"
case "$OS" in
  Darwin) DEFAULT_SKILLS_DIR="$HOME/.openclaw/skills" ;;
  Linux)  DEFAULT_SKILLS_DIR="/data/.openclaw/skills" ;;
  *) echo "Unsupported OS: $OS"; exit 2 ;;
esac
SKILLS_DIR="${OPENCLAW_SKILLS_DIR:-$DEFAULT_SKILLS_DIR}"

REQUIRED=(05-ghl-setup 10-github-setup 19-humanizer 29-ghl-convert-and-flow)

MISSING=()
for s in "${REQUIRED[@]}"; do
  if [ ! -d "$SKILLS_DIR/$s" ]; then
    MISSING+=("$s")
  fi
done

if [ "${#MISSING[@]}" -gt 0 ]; then
  echo "[skill 38] BLOCKED: missing prerequisites in $SKILLS_DIR:"
  printf '  - %s\n' "${MISSING[@]}"
  echo
  echo "Install the missing skill(s) first, then re-run this skill's installer."
  exit 1
fi

# Skill 29 connectivity check (Convert and Flow connected to operator's GHL location)
if command -v openclaw >/dev/null 2>&1; then
  if ! openclaw config show 2>/dev/null | grep -qiE "convert.?and.?flow|GHL_LOCATION_ID|ghl_location"; then
    echo "[skill 38] WARN: openclaw config has no Convert and Flow / GHL location binding."
    echo "         Re-run skill 29 (GHL Convert and Flow) to connect your location, then re-run this skill."
    # do not exit — warn-only, since some operators set env vars differently
  fi
fi

echo "[skill 38] prerequisites OK (05, 10, 19, 29 all present at $SKILLS_DIR)"
