#!/usr/bin/env bash
# 00-verify-prerequisites.sh -- Skill 41 Build With AI Playbook Generator
# Read-only. Exit 0 = all mandatory pass, 1 = a mandatory failed, 2 = unsupported OS.
set -uo pipefail

ERRORS=0
WARNINGS=0
AUTHORED_AGAINST="10.0.0"

echo "[skill 41] Verifying prerequisites..."

# OS support (exit 2 if unsupported)
OS="$(uname -s)"
case "$OS" in
  Darwin) echo "[skill 41] OS: macOS (Darwin) supported" ;;
  Linux)  echo "[skill 41] OS: Linux supported" ;;
  *)      echo "[skill 41] OS: $OS UNSUPPORTED"; exit 2 ;;
esac

# Mandatory binaries
for bin in jq curl; do
  if command -v "$bin" >/dev/null 2>&1; then
    echo "[skill 41] $bin: OK"
  else
    echo "[skill 41] $bin: MISSING (mandatory)"
    ERRORS=$((ERRORS + 1))
  fi
done

# OpenClaw version check (always check the version, as a guard)
OC_VER=""
if command -v openclaw >/dev/null 2>&1; then
  OC_VER="$(openclaw --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
  [[ -z "$OC_VER" ]] && OC_VER="$(openclaw -v 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
fi
if [[ -z "$OC_VER" && -f "$HOME/.openclaw/version" ]]; then
  OC_VER="$(grep -oE '[0-9]+\.[0-9]+\.[0-9]+' "$HOME/.openclaw/version" | head -1)"
fi
if [[ -n "$OC_VER" ]]; then
  echo "[skill 41] OpenClaw version: $OC_VER (authored against >= $AUTHORED_AGAINST)"
  LOWEST="$(printf '%s\n%s\n' "$OC_VER" "$AUTHORED_AGAINST" | sort -V | head -1)"
  if [[ "$LOWEST" == "$OC_VER" && "$OC_VER" != "$AUTHORED_AGAINST" ]]; then
    echo "[skill 41] WARNING: OpenClaw $OC_VER is older than $AUTHORED_AGAINST -- proceed with caution"
    WARNINGS=$((WARNINGS + 1))
  fi
else
  echo "[skill 41] OpenClaw version: could not detect -- verify manually before relying on version-specific behavior"
  WARNINGS=$((WARNINGS + 1))
fi

# GHL credentials (needed at RUNTIME for dependency creation -- warnings, not install blockers)
if [[ -n "${GOHIGHLEVEL_API_KEY:-}" ]]; then
  echo "[skill 41] GOHIGHLEVEL_API_KEY: present (${GOHIGHLEVEL_API_KEY:0:6}...)"
else
  echo "[skill 41] GOHIGHLEVEL_API_KEY: not set (needed at runtime for dependency creation)"
  WARNINGS=$((WARNINGS + 1))
fi
if [[ -n "${GOHIGHLEVEL_LOCATION_ID:-}" ]]; then
  echo "[skill 41] GOHIGHLEVEL_LOCATION_ID: present"
else
  echo "[skill 41] GOHIGHLEVEL_LOCATION_ID: not set (needed at runtime for GHL API calls)"
  WARNINGS=$((WARNINGS + 1))
fi

# Skill 38 (recommended for conversation-playbook pairing)
if [[ "$OS" == "Darwin" ]]; then SKILL38_DIR="$HOME/.openclaw/skills/38-conversational-ai-system"; else SKILL38_DIR="/data/.openclaw/skills/38-conversational-ai-system"; fi
if [[ -d "$SKILL38_DIR" ]]; then
  echo "[skill 41] Skill 38: found"
else
  echo "[skill 41] Skill 38: not found (recommended for conversation-playbook pairing)"
  WARNINGS=$((WARNINGS + 1))
fi

if [[ $ERRORS -eq 0 ]]; then
  echo "[skill 41] Mandatory prerequisites PASSED ($WARNINGS warning(s))"
  exit 0
else
  echo "[skill 41] FAILED: $ERRORS mandatory error(s), $WARNINGS warning(s). Fix errors before proceeding."
  exit 1
fi
