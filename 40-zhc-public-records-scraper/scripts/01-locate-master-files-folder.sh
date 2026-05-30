#!/usr/bin/env bash
# 01-locate-master-files-folder.sh — Skill 40
# Resolves + persists MASTER_FILES_DIR. Reuses Skill 38's or Skill 39's persisted
# selection if present, else falls back to the OS default. Idempotent.

set -uo pipefail
OS="$(uname -s)"
mkdir -p "$HOME/.openclaw" 2>/dev/null || true
STATE_FILE="$HOME/.openclaw/.skill-40-master-files-dir"
S38_STATE="$HOME/.openclaw/.skill-38-master-files-dir"
S39_STATE="$HOME/.openclaw/.skill-39-master-files-dir"
P="[skill 40][mfd]"

case "$OS" in Darwin) DEFAULT_MFD="$HOME/Downloads" ;; *) DEFAULT_MFD="/data" ;; esac

MFD=""; REASON=""
if [ -n "${MASTER_FILES_DIR:-}" ] && [ -d "${MASTER_FILES_DIR}" ]; then
  MFD="$MASTER_FILES_DIR"; REASON="MASTER_FILES_DIR env"
fi
for st in "$S39_STATE" "$S38_STATE" "$STATE_FILE"; do
  [ -n "$MFD" ] && break
  if [ -f "$st" ]; then
    cand="$(tr -d '[:space:]' < "$st" 2>/dev/null || true)"
    [ -n "$cand" ] && [ -d "$cand" ] && { MFD="$cand"; REASON="reused $(basename "$st")"; }
  fi
done
if [ -z "$MFD" ]; then MFD="$DEFAULT_MFD"; REASON="OS default"; mkdir -p "$MFD" 2>/dev/null || true; fi

printf '%s\n' "$MFD" > "$STATE_FILE"
echo "$P MASTER_FILES_DIR = $MFD ($REASON)"
echo "$P persisted to $STATE_FILE"
echo "$P export MASTER_FILES_DIR=\"$MFD\"   # for the rest of this install session"
exit 0
