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
#   8. Per-slug FAILURE BACKOFF + QUARANTINE (G4 furnace fix): a source that
#      fails conversion is counted; after MAX_FAILURES (default: 3) consecutive
#      failures it is moved to INBOX_DIR/failed/ and the operator is notified
#      ONCE, then never retried. Without this, an un-convertible book writes no
#      blueprint, so the idempotency skip (step 4) never fires and the full
#      extraction/analysis/synthesis pipeline re-runs ~144x/day forever.
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
#   - Per-slug failure counter + quarantine after MAX_FAILURES (kills the
#     "un-convertible source re-runs the pipeline every 10 min forever" furnace)
#   - pipefail + set -u to catch real errors

set -uo pipefail

# ─── CONFIGURATION ───────────────────────────────────────────────────────────
# Maximum personas to process per cron invocation (TOKEN-SAFE guard)
MAX_PER_RUN="${PERSONA_INBOX_MAX_PER_RUN:-5}"
# Lock TTL in minutes: locks older than this are considered stale and reaped
LOCK_TTL_MINUTES="${PERSONA_INBOX_LOCK_TTL:-120}"
# Consecutive-failure cap per source: after this many failed conversions the
# source is quarantined to inbox/failed/ and never retried (TOKEN-SAFE furnace guard)
MAX_FAILURES="${PERSONA_INBOX_MAX_FAILURES:-3}"
# Log prefix for timestamped messages
TS() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

# ─── OPERATOR ESCALATION RESOLVER ────────────────────────────────────────────
# CO-MINGLING GUARD: destination is OPT-IN. No hardcoded personal chat.
# Empty result = escalation destination not configured; caller logs only.
resolve_operator_chat_id() {
    local v=""
    if command -v openclaw >/dev/null 2>&1; then
        v="$(openclaw config get env.vars.OPERATOR_ESCALATION_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
        case "$v" in ""|*"not found"*|*"Error"*) v="" ;; esac
        if [ -z "$v" ]; then
            v="$(openclaw config get env.vars.OPERATOR_HELP_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
            case "$v" in ""|*"not found"*|*"Error"*) v="" ;; esac
        fi
        if [ -z "$v" ]; then
            v="$(openclaw config get env.vars.OPERATOR_TELEGRAM_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
            case "$v" in ""|*"not found"*|*"Error"*) v="" ;; esac
        fi
    fi
    [ -z "$v" ] && [ -n "${OPERATOR_ESCALATION_CHAT_ID:-}" ] && v="$OPERATOR_ESCALATION_CHAT_ID"
    [ -z "$v" ] && [ -n "${OPERATOR_HELP_CHAT_ID:-}" ] && v="$OPERATOR_HELP_CHAT_ID"
    [ -z "$v" ] && [ -n "${OPERATOR_TELEGRAM_CHAT_ID:-}" ] && v="$OPERATOR_TELEGRAM_CHAT_ID"
    printf '%s' "$v"
}

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
# Quarantine dir for sources that fail conversion MAX_FAILURES times in a row,
# and a hidden sidecar dir holding per-slug consecutive-failure counters.
FAILED_DIR="$INBOX_DIR/failed"
FAILCOUNT_DIR="$INBOX_DIR/.failcounts"

mkdir -p "$INBOX_DIR" "$PERSONAS_DIR" "$PROCESSED_DIR" "$LOCK_DIR" "$FAILED_DIR" "$FAILCOUNT_DIR"

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

# Helper: read the current consecutive-failure count for a slug (0 if absent/garbage)
_read_failcount() {
    local _f="$FAILCOUNT_DIR/$1.failcount" _n=0
    [ -f "$_f" ] && _n="$(cat "$_f" 2>/dev/null || echo 0)"
    case "$_n" in ''|*[!0-9]*) _n=0 ;; esac
    printf '%s' "$_n"
}

# Helper: escalate to the operator exactly ONCE per slug (guarded by a marker
# file). Non-fatal: if no operator chat is configured or the send fails, we log
# and continue — the quarantine itself (source moved out of inbox) is what stops
# the furnace; the Telegram notice is best-effort.
_escalate_once() {
    local _slug_arg="$1" _msg="$2"
    local _marker="$FAILED_DIR/.escalated-$_slug_arg"
    [ -f "$_marker" ] && return 0   # already escalated for this slug
    : > "$_marker"
    local _chat; _chat="$(resolve_operator_chat_id)"
    if [ -n "$_chat" ] && command -v openclaw >/dev/null 2>&1; then
        if openclaw message send --channel telegram -t "$_chat" -m "$_msg" >/dev/null 2>&1; then
            echo "$(TS) [persona-inbox-watcher] Escalation Telegram sent to operator ($_chat)."
        else
            echo "$(TS) [persona-inbox-watcher] WARN: escalation Telegram send failed (non-fatal): $_msg"
        fi
    else
        echo "$(TS) [persona-inbox-watcher] WARN: no operator escalation chat configured — logging only: $_msg"
    fi
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

    # Quarantine GATE (G4 furnace fix): if this slug already hit the failure cap,
    # ensure it is out of the active inbox and never reprocessed. This enforces
    # the cap even if a prior quarantine move failed (a rule not enforced at a
    # gate doesn't exist).
    _prior_fails="$(_read_failcount "$_slug")"
    if [ "$_prior_fails" -ge "$MAX_FAILURES" ]; then
        echo "$(TS) [persona-inbox-watcher] '$_slug' previously quarantined ($_prior_fails consecutive failures) — moving to $FAILED_DIR/ and skipping."
        mv "$_source_file" "$FAILED_DIR/" 2>/dev/null || true
        [ -f "$_sidecar" ] && mv "$_sidecar" "$FAILED_DIR/" 2>/dev/null || true
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
        # Clear any prior consecutive-failure count (success resets the counter)
        rm -f "$FAILCOUNT_DIR/$_slug.failcount" 2>/dev/null || true
        processed_count=$((processed_count + 1))
    else
        _rc=$?
        # Per-slug FAILURE BACKOFF + QUARANTINE (G4 furnace fix). Increment the
        # consecutive-failure counter; once it reaches MAX_FAILURES, move the
        # source (and sidecar) out of the active inbox so it is NEVER reprocessed,
        # and escalate to the operator exactly once. This kills the ~144x/day
        # re-run loop on an un-convertible source.
        _failcount_file="$FAILCOUNT_DIR/$_slug.failcount"
        _fails="$(_read_failcount "$_slug")"
        _fails=$((_fails + 1))
        echo "$_fails" > "$_failcount_file"
        echo "$(TS) [persona-inbox-watcher] FAILED (exit $_rc): '$_slug' — consecutive failure $_fails/$MAX_FAILURES."
        if [ "$_fails" -ge "$MAX_FAILURES" ]; then
            mv "$_source_file" "$FAILED_DIR/" 2>/dev/null || true
            [ -f "$_sidecar" ] && mv "$_sidecar" "$FAILED_DIR/" 2>/dev/null || true
            echo "$(TS) [persona-inbox-watcher] QUARANTINE: '$_slug' failed $_fails consecutive times — moved to $FAILED_DIR/ (no further retries)."
            _escalate_once "$_slug" "Book-to-Persona watcher: source '$_fname' (slug '$_slug') failed $_fails consecutive conversions and was quarantined to inbox/failed/. Manual review required."
            # Counter no longer needed — quarantine (source out of inbox) is authoritative.
            rm -f "$_failcount_file" 2>/dev/null || true
        else
            echo "$(TS) [persona-inbox-watcher] '$_slug' left in inbox for retry (attempt $_fails of $MAX_FAILURES)."
        fi
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
