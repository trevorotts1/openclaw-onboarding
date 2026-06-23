#!/bin/bash
# persona-inbox-watcher.sh — v6.6.0
#
# Cron-driven inbox watcher for Skill 22. Scans a drop-folder for new source
# files and automatically converts them into personas without operator interaction.
#
# Invoked by a cron job installed by install.sh (*/10 cron schedule):
#   */10 * * * * /data/.openclaw/skills/22-book-to-persona-coaching-leadership-system/scripts/persona-inbox-watcher.sh >> /data/.openclaw/logs/persona-inbox-watcher.log 2>&1
#
# HOW IT WORKS:
#   1. Scans INBOX_DIR for files with a .json manifest (source.json style) OR
#      raw book/video files (PDF, EPUB, MOBI, AZW3, MP4, etc.) without a matching
#      personas/<slug>/persona-blueprint.md.
#   2. For each unprocessed file: calls add-persona-from-source.sh once.
#   3. Moves processed source file to INBOX_DIR/processed/.
#   4. Uses per-slug .lock files for idempotency (skips if blueprint already
#      exists or if a lock is held by a concurrent run).
#   5. Reaps stale locks older than LOCK_TTL_MINUTES (default: 120 min).
#   6. Processes at most MAX_PER_RUN files per invocation (default: 5)
#      to bound token burn.
#   7. Self-disables if the orchestrator/add-persona-from-source.sh is missing.
#
# DROP FOLDER:
#   VPS:  /data/.openclaw/master-files/coaching-personas/inbox/
#   Mac:  ~/.openclaw/workspace/data/coaching-personas/inbox/
#
# TO ADD A FILE:
#   cp "My New Book.pdf" <INBOX_DIR>/
#   (optionally) create a sidecar: <INBOX_DIR>/my-new-book.json
#     { "title": "My New Book", "author": "Jane Doe" }
#
# GUARDRAILS (TOKEN-SAFE):
#   - MAX_PER_RUN hard cap (never burns unbounded tokens in one cron invocation)
#   - Lock files prevent double-processing
#   - Stale lock reaping (2h TTL) prevents permanent stuck state
#   - Self-disables if orchestrator not found (no runaway cron)
#   - pipefail + set -u to catch real errors

set -uo pipefail

# ─── CONFIGURATION ───────────────────────────────────────────────────────────
# Maximum personas to process per cron invocation (TOKEN-SAFE guard)
MAX_PER_RUN="${PERSONA_INBOX_MAX_PER_RUN:-5}"
# Lock TTL in minutes: locks older than this are considered stale and reaped
LOCK_TTL_MINUTES="${PERSONA_INBOX_LOCK_TTL:-120}"
# Log prefix for timestamped messages
TS() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

# ─── PATH RESOLUTION ─────────────────────────────────────────────────────────
# Resolve canonical base dir: VPS first, then Mac, then legacy
if [ -d /data/.openclaw/master-files ]; then
    PERSONA_BASE="/data/.openclaw/master-files/coaching-personas"
elif [ -d "$HOME/.openclaw/workspace/data" ]; then
    PERSONA_BASE="$HOME/.openclaw/workspace/data/coaching-personas"
else
    # Legacy path — keep for backward compat
    PERSONA_BASE="$HOME/Downloads/openclaw-master-files/coaching-personas"
fi

INBOX_DIR="$PERSONA_BASE/inbox"
PERSONAS_DIR="$PERSONA_BASE/personas"
PROCESSED_DIR="$INBOX_DIR/processed"
LOCK_DIR="$INBOX_DIR/.locks"

mkdir -p "$INBOX_DIR" "$PERSONAS_DIR" "$PROCESSED_DIR" "$LOCK_DIR"

# Resolve add-persona-from-source.sh (the script we call per new file)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADD_PERSONA_SCRIPT="$SCRIPT_DIR/add-persona-from-source.sh"

# Self-disable guard: if the script doesn't exist, exit cleanly (no runaway cron)
if [ ! -f "$ADD_PERSONA_SCRIPT" ]; then
    echo "$(TS) [persona-inbox-watcher] WARN: add-persona-from-source.sh not found at $ADD_PERSONA_SCRIPT — watcher disabled until reinstalled."
    exit 0
fi

# Resolve orchestrator (additional self-disable guard)
ORCHESTRATOR="$(dirname "$SCRIPT_DIR")/pipeline/orchestrator.py"
if [ ! -f "$ORCHESTRATOR" ]; then
    echo "$(TS) [persona-inbox-watcher] WARN: orchestrator.py not found at $ORCHESTRATOR — watcher disabled until reinstalled."
    exit 0
fi

# ─── STALE LOCK REAPING ──────────────────────────────────────────────────────
# Find lock files older than LOCK_TTL_MINUTES and remove them
stale_reaped=0
while IFS= read -r -d '' _lock; do
    if [ -f "$_lock" ]; then
        rm -f "$_lock"
        stale_reaped=$((stale_reaped + 1))
        echo "$(TS) [persona-inbox-watcher] Reaped stale lock: $_lock"
    fi
done < <(find "$LOCK_DIR" -name "*.lock" -mmin "+$LOCK_TTL_MINUTES" -print0 2>/dev/null)
[ "$stale_reaped" -gt 0 ] && echo "$(TS) [persona-inbox-watcher] Reaped $stale_reaped stale lock(s)."

# ─── SCAN INBOX ──────────────────────────────────────────────────────────────
# Supported file extensions the watcher will pick up from the inbox
SUPPORTED_EXTS=".pdf .epub .mobi .azw3 .mp4 .mov .mkv .avi .webm .txt .md"

processed_count=0

# Helper: derive slug from filename (same logic as add-persona-from-source.sh)
_slugify() {
    echo "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g; s/-\{2,\}/-/g; s/^-//; s/-$//'
}

# Iterate over files in INBOX_DIR (non-recursive, no subdirectories)
for _source_file in "$INBOX_DIR"/*; do
    # Stop if we've hit the per-run cap
    [ "$processed_count" -ge "$MAX_PER_RUN" ] && {
        echo "$(TS) [persona-inbox-watcher] MAX_PER_RUN ($MAX_PER_RUN) reached — deferring remaining files to next cron run."
        break
    }

    # Skip if not a regular file
    [ -f "$_source_file" ] || continue

    # Skip manifest/sidecar .json files (we'll read them when processing the source)
    case "$_source_file" in *.json) continue ;; esac

    # Skip hidden files and directories
    _fname="$(basename "$_source_file")"
    case "$_fname" in .*) continue ;; esac

    # Check extension is supported
    _ext="${_fname##*.}"
    _ext_lower=".$(echo "$_ext" | tr '[:upper:]' '[:lower:]')"
    _supported=false
    for _e in $SUPPORTED_EXTS; do
        [ "$_ext_lower" = "$_e" ] && { _supported=true; break; }
    done
    if [ "$_supported" = "false" ]; then
        echo "$(TS) [persona-inbox-watcher] Skipping unsupported extension: $_fname"
        continue
    fi

    # Derive slug from filename
    _basename_no_ext="${_fname%.*}"
    _slug="$(_slugify "$_basename_no_ext")"

    # Check for a sidecar .json with title/author overrides
    _sidecar="$INBOX_DIR/$_basename_no_ext.json"
    _title=""
    _author=""
    if [ -f "$_sidecar" ]; then
        _title=$(python3 -c "import json,sys; d=json.load(open('$_sidecar')); print(d.get('title',''))" 2>/dev/null || true)
        _author=$(python3 -c "import json,sys; d=json.load(open('$_sidecar')); print(d.get('author',''))" 2>/dev/null || true)
        if [ -n "$_title" ] && [ -n "$_author" ]; then
            _slug="$(_slugify "$_author-$_title")"
        fi
    fi

    # Idempotency check: skip if blueprint already exists
    _blueprint="$PERSONAS_DIR/$_slug/persona-blueprint.md"
    if [ -f "$_blueprint" ]; then
        echo "$(TS) [persona-inbox-watcher] Blueprint already exists for '$_slug' — moving to processed."
        mv "$_source_file" "$PROCESSED_DIR/" 2>/dev/null || true
        [ -f "$_sidecar" ] && mv "$_sidecar" "$PROCESSED_DIR/" 2>/dev/null || true
        continue
    fi

    # Lock check: skip if another process is working on this slug
    _lock_file="$LOCK_DIR/$_slug.lock"
    if [ -f "$_lock_file" ]; then
        echo "$(TS) [persona-inbox-watcher] Lock held for '$_slug' — skipping (will retry next run)."
        continue
    fi

    # Acquire lock
    echo "$$" > "$_lock_file"
    trap 'rm -f "$_lock_file"' EXIT INT TERM

    echo "$(TS) [persona-inbox-watcher] Processing: $_fname → slug='$_slug'"

    # Build the add-persona-from-source.sh invocation
    _add_args=("--source" "$_source_file")
    [ -n "$_title"  ] && _add_args+=("--title"  "$_title")
    [ -n "$_author" ] && _add_args+=("--author" "$_author")

    if bash "$ADD_PERSONA_SCRIPT" "${_add_args[@]}" ; then
        echo "$(TS) [persona-inbox-watcher] SUCCESS: '$_slug' processed."
        mv "$_source_file" "$PROCESSED_DIR/" 2>/dev/null || true
        [ -f "$_sidecar" ] && mv "$_sidecar" "$PROCESSED_DIR/" 2>/dev/null || true
        processed_count=$((processed_count + 1))
    else
        _rc=$?
        echo "$(TS) [persona-inbox-watcher] FAILED (exit $_rc): '$_slug'. Source file left in inbox for manual retry."
    fi

    # Release lock
    rm -f "$_lock_file"
    trap - EXIT INT TERM

done

if [ "$processed_count" -gt 0 ]; then
    echo "$(TS) [persona-inbox-watcher] Done. Processed $processed_count new persona(s) this run."
else
    echo "$(TS) [persona-inbox-watcher] No new files to process in $INBOX_DIR."
fi
