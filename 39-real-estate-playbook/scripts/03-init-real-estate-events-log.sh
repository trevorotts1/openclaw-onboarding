#!/usr/bin/env bash
# 03-init-real-estate-events-log.sh — Skill 39
# Creates the F52 event log <MASTER_FILES_DIR>/real-estate-events.jsonl (if it
# does not already exist) and a machine-readable .schema.json sidecar next to
# it. Appends a single "log_initialized" event. Idempotent (never truncates an
# existing log).

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
P="[skill 39][events-log]"

OS="$(uname -s)"
case "$OS" in Darwin) DEFMFD="$HOME/Downloads" ;; *) DEFMFD="/data" ;; esac
STATE_FILE="$HOME/.openclaw/.skill-39-master-files-dir"
MFD="${MASTER_FILES_DIR:-}"
[ -z "$MFD" ] && [ -f "$STATE_FILE" ] && MFD="$(tr -d '[:space:]' < "$STATE_FILE" 2>/dev/null || true)"
[ -z "$MFD" ] && MFD="$DEFMFD"
mkdir -p "$MFD" 2>/dev/null || true

LOG="$MFD/real-estate-events.jsonl"
SCHEMA_DST="$MFD/real-estate-events.schema.json"
SCHEMA_SRC="$SKILL_ROOT/templates/real-estate-events.schema.json"

if [ -f "$LOG" ]; then
  echo "$P log already exists at $LOG — leaving it intact (append-only)"
else
  : > "$LOG"
  echo "$P created $LOG"
fi

if [ -f "$SCHEMA_SRC" ]; then
  cp "$SCHEMA_SRC" "$SCHEMA_DST" 2>/dev/null && echo "$P schema sidecar → $SCHEMA_DST" || echo "$P WARN: could not copy schema sidecar"
else
  echo "$P WARN: schema source not found at $SCHEMA_SRC"
fi

# Append a log_initialized event using the lib (keeps the contract centralized).
MASTER_FILES_DIR="$MFD" bash "$SCRIPT_DIR/lib-re-events.sh" re_event log_initialized '{"lead_ref":"n/a","source":"none"}' \
  && echo "$P appended log_initialized event" \
  || echo "$P WARN: could not append log_initialized event (jq present?)"
exit 0
