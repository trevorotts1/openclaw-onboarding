#!/usr/bin/env bash
# 06-scaffold-showing-scheduler.sh — Skill 39
# Scaffolds the showing-scheduler config (lockbox + MLS showing rules) into the
# client's master files. Copies the TEMPLATE if no config exists yet; never
# overwrites a config the operator has already filled. Idempotent.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
P="[skill 39][showing-scheduler]"

OS="$(uname -s)"
case "$OS" in Darwin) DEFMFD="$HOME/Downloads" ;; *) DEFMFD="/data" ;; esac
STATE_FILE="$HOME/.openclaw/.skill-39-master-files-dir"
MFD="${MASTER_FILES_DIR:-}"
[ -z "$MFD" ] && [ -f "$STATE_FILE" ] && MFD="$(tr -d '[:space:]' < "$STATE_FILE" 2>/dev/null || true)"
[ -z "$MFD" ] && MFD="$DEFMFD"

DEST="$MFD/real-estate/showing-scheduler"
mkdir -p "$DEST" 2>/dev/null || true

SRC="$SKILL_ROOT/templates/showing-scheduler-config.template.json"
CFG="$DEST/showing-scheduler-config.json"
TMPL="$DEST/showing-scheduler-config.template.json"

[ -f "$SRC" ] || { echo "$P WARN: template missing: $SRC"; exit 0; }

# Always refresh the template copy (reference), but only seed the live config if absent.
cp "$SRC" "$TMPL" && echo "$P template → $TMPL"
if [ -f "$CFG" ]; then
  echo "$P live config already present at $CFG — leaving operator's values intact"
else
  cp "$SRC" "$CFG" && echo "$P seeded live config → $CFG (operator fills lockbox + MLS rules)"
fi

echo "$P showing scheduler scaffolded under $DEST"
echo "$P NOTE: the protocol runtime is protocols/showing-scheduler-protocol.md"
exit 0
