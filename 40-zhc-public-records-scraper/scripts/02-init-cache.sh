#!/usr/bin/env bash
# 02-init-cache.sh — Skill 40
# Creates the 30-day cache dir + the F52 event log + a schema sidecar. Appends a
# cache_init event. Idempotent (never wipes an existing cache or log).

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
P="[skill 40][cache-init]"

OS="$(uname -s)"
case "$OS" in Darwin) DEFMFD="$HOME/Downloads" ;; *) DEFMFD="/data" ;; esac
STATE_FILE="$HOME/.openclaw/.skill-40-master-files-dir"
MFD="${MASTER_FILES_DIR:-}"
[ -z "$MFD" ] && [ -f "$STATE_FILE" ] && MFD="$(tr -d '[:space:]' < "$STATE_FILE" 2>/dev/null || true)"
[ -z "$MFD" ] && MFD="$DEFMFD"
mkdir -p "$MFD" 2>/dev/null || true

CACHE="$MFD/public-records-cache"
LOG="$MFD/public-records-queries.jsonl"
SCHEMA_DST="$MFD/public-records-queries.schema.json"
SCHEMA_SRC="$SKILL_ROOT/templates/public-records-queries.schema.json"

mkdir -p "$CACHE" 2>/dev/null && echo "$P cache dir ready: $CACHE"
if [ -f "$LOG" ]; then echo "$P log already exists at $LOG — leaving intact"; else : > "$LOG"; echo "$P created $LOG"; fi
if [ -f "$SCHEMA_SRC" ]; then cp "$SCHEMA_SRC" "$SCHEMA_DST" && echo "$P schema sidecar → $SCHEMA_DST"; else echo "$P WARN: schema source missing: $SCHEMA_SRC"; fi

MASTER_FILES_DIR="$MFD" bash "$SCRIPT_DIR/lib-pr-events.sh" pr_event cache_init '{"query_ref":"n/a","target_ref":"n/a"}' \
  && echo "$P appended cache_init event" || echo "$P WARN: could not append cache_init event (jq present?)"
exit 0
