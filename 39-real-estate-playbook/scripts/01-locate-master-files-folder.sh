#!/usr/bin/env bash
# 01-locate-master-files-folder.sh — Skill 39
# Resolves + persists MASTER_FILES_DIR. Reuses Skill 38's selection if present
# (Skill 38 persists it to ~/.openclaw/.skill-38-master-files-dir), otherwise
# falls back to semantic discovery / the OS default. Idempotent.

set -uo pipefail

OS="$(uname -s)"
mkdir -p "$HOME/.openclaw" 2>/dev/null || true
STATE_FILE="$HOME/.openclaw/.skill-39-master-files-dir"
S38_STATE="$HOME/.openclaw/.skill-38-master-files-dir"
P="[skill 39][mfd]"

case "$OS" in
  Darwin) DEFAULT_MFD="$HOME/Downloads" ;;
  *)      DEFAULT_MFD="/data" ;;
esac

MFD=""
REASON=""

# 1) Honor an explicit env var.
if [ -n "${MASTER_FILES_DIR:-}" ] && [ -d "${MASTER_FILES_DIR}" ]; then
  MFD="$MASTER_FILES_DIR"; REASON="MASTER_FILES_DIR env"
fi

# 2) Reuse Skill 38's persisted selection (single source of truth).
if [ -z "$MFD" ] && [ -f "$S38_STATE" ]; then
  cand="$(tr -d '[:space:]' < "$S38_STATE" 2>/dev/null || true)"
  if [ -n "$cand" ] && [ -d "$cand" ]; then
    MFD="$cand"; REASON="reused Skill 38 selection"
  fi
fi

# 3) Reuse our own prior selection.
if [ -z "$MFD" ] && [ -f "$STATE_FILE" ]; then
  cand="$(tr -d '[:space:]' < "$STATE_FILE" 2>/dev/null || true)"
  if [ -n "$cand" ] && [ -d "$cand" ]; then
    MFD="$cand"; REASON="reused prior Skill 39 selection"
  fi
fi

# 4) Fall back to the OS default (create it).
if [ -z "$MFD" ]; then
  MFD="$DEFAULT_MFD"; REASON="OS default"
  mkdir -p "$MFD" 2>/dev/null || true
fi

printf '%s\n' "$MFD" > "$STATE_FILE"
echo "$P MASTER_FILES_DIR = $MFD ($REASON)"
echo "$P persisted to $STATE_FILE"
echo "$P export MASTER_FILES_DIR=\"$MFD\"   # for the rest of this install session"
exit 0
