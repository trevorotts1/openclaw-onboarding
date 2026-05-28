#!/usr/bin/env bash
# 01-locate-master-files-folder.sh — Skill 38 (Conversational AI System)
# Implements the v5.14 playbook's Step O.2 semantic master-files-folder discovery.
# Sets MASTER_FILES_DIR for the rest of the install. Idempotent. OS-aware.

set -euo pipefail
OS="$(uname -s)"

# Candidate directories to scan, in priority order
case "$OS" in
  Darwin) CANDIDATES=("$HOME/Downloads" "$HOME/Documents" "$HOME/Desktop" "$HOME") ;;
  Linux)  CANDIDATES=("/data" "/root" "/home" "$HOME") ;;
esac

# Semantic signals: a folder is the master files folder if it contains
# any of: ai-workforce-config.json, ai-workforce-blueprint, openclaw-master-files,
# master-files/, blackceo-master/, or has been explicitly set
if [ -n "${MASTER_FILES_DIR:-}" ] && [ -d "$MASTER_FILES_DIR" ]; then
  echo "[skill 38] using MASTER_FILES_DIR=$MASTER_FILES_DIR (already set)"
  exit 0
fi

found=""
for root in "${CANDIDATES[@]}"; do
  [ -d "$root" ] || continue
  # Look down 3 levels for marker files
  while IFS= read -r match; do
    parent="$(dirname "$match")"
    found="$parent"
    break 2
  done < <(find "$root" -maxdepth 3 -type f \( \
              -iname "ai-workforce-config.json" -o \
              -iname "openclaw-master-files" -o \
              -iname "master-files.md" -o \
              -iname "conversational-ai-state.json" \
           \) 2>/dev/null)
done

if [ -z "$found" ]; then
  echo "[skill 38] no master-files folder detected. Prompting operator (interactive):"
  read -r -p "Enter the absolute path to your master files folder: " input || true
  if [ -n "$input" ] && [ -d "$input" ]; then
    found="$input"
  else
    echo "[skill 38] ERR: no usable folder. See v5.14 playbook §O.2."
    exit 1
  fi
fi

echo "export MASTER_FILES_DIR=\"$found\"" > "$HOME/.openclaw/.skill-38-master-files-dir"
echo "[skill 38] MASTER_FILES_DIR=$found  (saved to ~/.openclaw/.skill-38-master-files-dir)"
