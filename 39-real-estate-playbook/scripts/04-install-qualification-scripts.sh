#!/usr/bin/env bash
# 04-install-qualification-scripts.sh — Skill 39
# Installs the buyer + seller qualification templates into the client's master
# files folder (<MASTER_FILES_DIR>/real-estate/qualification/) so the agent can
# reference them at runtime. Idempotent (overwrites only if the source differs
# by content). UNIVERSAL — templates carry placeholders, no client data.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
P="[skill 39][qualification]"

OS="$(uname -s)"
case "$OS" in Darwin) DEFMFD="$HOME/Downloads" ;; *) DEFMFD="/data" ;; esac
STATE_FILE="$HOME/.openclaw/.skill-39-master-files-dir"
MFD="${MASTER_FILES_DIR:-}"
[ -z "$MFD" ] && [ -f "$STATE_FILE" ] && MFD="$(tr -d '[:space:]' < "$STATE_FILE" 2>/dev/null || true)"
[ -z "$MFD" ] && MFD="$DEFMFD"

DEST="$MFD/real-estate/qualification"
mkdir -p "$DEST" 2>/dev/null || true

copy_if_changed() {
  local src="$1" dst="$2"
  [ -f "$src" ] || { echo "$P WARN: source missing: $src"; return 0; }
  if [ -f "$dst" ] && cmp -s "$src" "$dst"; then
    echo "$P up to date: $(basename "$dst")"
  else
    cp "$src" "$dst" && echo "$P installed: $(basename "$dst")"
  fi
}

copy_if_changed "$SKILL_ROOT/templates/buyer-qualification.md"  "$DEST/buyer-qualification.md"
copy_if_changed "$SKILL_ROOT/templates/seller-qualification.md" "$DEST/seller-qualification.md"
copy_if_changed "$SKILL_ROOT/templates/agent-specialty-roster.template.json" "$DEST/agent-specialty-roster.template.json"

echo "$P qualification templates available under $DEST"
echo "$P NOTE: agent-specialty-roster.template.json is a TEMPLATE — the operator fills the real roster."
exit 0
