#!/usr/bin/env bash
# PRD Addendum A.2 — Session Load Gate
# Verifies edit→reset→loaded-check ordering after wire.sh migrations are applied.
# NEVER calls openclaw gateway restart — only gateway call sessions.reset.
#
# Usage:
#   a2-session-load-gate.sh --box <name> [--workspace <path>]
#
# Env overrides:
#   A2_WAIT_SECONDS          — seconds to wait after sessions.reset (default: 15)
#   OPENCLAW_WORKSPACE       — override workspace path (for testing)
#   OPERATOR_TELEGRAM_CHAT_ID — Telegram chat ID for alerts (default: 5252140759)

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
BOX=""
WORKSPACE_OVERRIDE=""
WAIT_SECONDS="${A2_WAIT_SECONDS:-15}"
OPERATOR_CHAT="${OPERATOR_TELEGRAM_CHAT_ID:-5252140759}"

# ── Parse args ─────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --box)      BOX="$2";              shift 2 ;;
    --workspace) WORKSPACE_OVERRIDE="$2"; shift 2 ;;
    *)          echo "Unknown arg: $1"; exit 1 ;;
  esac
done

[[ -z "$BOX" ]] && { echo "ERROR: --box is required"; exit 1; }

# ── Platform detection & paths ────────────────────────────────────────────────
if [[ -n "$WORKSPACE_OVERRIDE" ]]; then
  WORKSPACE="$WORKSPACE_OVERRIDE"
elif [[ -d "/data/.openclaw/workspace" ]]; then
  WORKSPACE="/data/.openclaw/workspace"
  SESSIONS_JSON="/data/.openclaw/agents/main/sessions/sessions.json"
  LOG_DIR="/data/.openclaw/skills"
else
  WORKSPACE="$HOME/.openclaw/workspace"
  SESSIONS_JSON="$HOME/.openclaw/agents/main/sessions/sessions.json"
  LOG_DIR="$HOME/.openclaw/skills"
fi

# Allow sessions.json override for testing
SESSIONS_JSON="${SESSIONS_JSON_OVERRIDE:-${SESSIONS_JSON:-$WORKSPACE/../agents/main/sessions/sessions.json}}"

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/.a2-load-gate.log"
AGENTS_MD="$WORKSPACE/AGENTS.md"

# ── Logging ───────────────────────────────────────────────────────────────────
log() {
  local msg="[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] [a2-session-load-gate] [$BOX] $*"
  echo "$msg" | tee -a "$LOG_FILE"
}

# ── Lockfile (idempotent, matches update-skills.sh pattern) ──────────────────
LOCK_FILE="/tmp/.a2-load-gate-${BOX}.lock"
if [[ -f "$LOCK_FILE" ]]; then
  LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
  if [[ -n "$LOCK_PID" ]] && kill -0 "$LOCK_PID" 2>/dev/null; then
    log "Another instance is running (pid $LOCK_PID). Exiting."
    exit 0
  fi
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

# ── Resolve session key ────────────────────────────────────────────────────────
log "Resolving session key from $SESSIONS_JSON"
if [[ ! -f "$SESSIONS_JSON" ]]; then
  log "ERROR: sessions.json not found at $SESSIONS_JSON"
  exit 1
fi

SESSION_KEY=$(python3 -c "
import json, sys
data = json.load(open('$SESSIONS_JSON'))
keys = [k for k in data.keys() if k.startswith('agent:main:telegram:direct:')]
if not keys:
    sys.exit(1)
print(keys[0])
" 2>/dev/null) || {
  log "ERROR: No agent:main:telegram:direct:<id> key found in sessions.json"
  exit 1
}
log "Found session key: $SESSION_KEY"

# ── Check AGENTS.md marker ────────────────────────────────────────────────────
check_marker() {
  if [[ ! -f "$AGENTS_MD" ]]; then
    log "AGENTS.md not found at $AGENTS_MD"
    echo "NO"
    return
  fi
  if grep -q '<!-- convertandflow-migration:' "$AGENTS_MD" 2>/dev/null; then
    echo "YES"
  else
    echo "NO"
  fi
}

# ── Check edit→reset ordering ─────────────────────────────────────────────────
# Returns 0 if AGENTS.md mtime is BEFORE reset_epoch (edit happened before reset)
check_ordering() {
  local reset_epoch="$1"
  if [[ ! -f "$AGENTS_MD" ]]; then
    return 1
  fi
  local agents_mtime
  agents_mtime=$(stat -f '%m' "$AGENTS_MD" 2>/dev/null || stat -c '%Y' "$AGENTS_MD" 2>/dev/null)
  if [[ -z "$agents_mtime" ]]; then
    log "WARNING: Could not stat AGENTS.md mtime"
    return 1
  fi
  if [[ "$agents_mtime" -lt "$reset_epoch" ]]; then
    log "Ordering OK: AGENTS.md last edited at epoch $agents_mtime, reset issued at epoch $reset_epoch (edit->reset confirmed)"
    return 0
  else
    log "Ordering FAIL: AGENTS.md mtime $agents_mtime >= reset epoch $reset_epoch (edit happened after reset)"
    return 1
  fi
}

# ── Issue sessions.reset ──────────────────────────────────────────────────────
do_reset() {
  local attempt="$1"
  log "Issuing sessions.reset (attempt $attempt) for key: $SESSION_KEY"
  local reset_epoch
  reset_epoch=$(date +%s)

  if openclaw gateway call sessions.reset \
    --params "{\"key\":\"${SESSION_KEY}\",\"reason\":\"a2-session-load-gate\"}" ; then
    log "sessions.reset succeeded (epoch $reset_epoch)"
    echo "$reset_epoch"
    return 0
  else
    log "ERROR: sessions.reset command failed (attempt $attempt)"
    echo ""
    return 1
  fi
}

# ── Wait (bounded) ────────────────────────────────────────────────────────────
do_wait() {
  log "Waiting ${WAIT_SECONDS}s for session to initialize..."
  sleep "$WAIT_SECONDS"
}

# ── Main logic ────────────────────────────────────────────────────────────────
log "=== A.2 Session Load Gate starting. Box: $BOX ==="
log "Workspace: $WORKSPACE"
log "AGENTS.md: $AGENTS_MD"

# Attempt 1
RESET_EPOCH=$(do_reset 1) || {
  log "FATAL: sessions.reset failed on attempt 1"
  exit 1
}
do_wait

MARKER=$(check_marker)
log "Marker check: $MARKER"

if [[ "$MARKER" == "YES" ]] && check_ordering "$RESET_EPOCH"; then
  log "loaded=YES — migration marker present and edit->reset ordering confirmed"
  echo "loaded=YES"
  exit 0
fi

log "loaded=NO after attempt 1. Retrying..."

# Attempt 2 (retry once)
RESET_EPOCH=$(do_reset 2) || {
  log "FATAL: sessions.reset failed on attempt 2"
  RESET_EPOCH=0
}
do_wait

MARKER=$(check_marker)
log "Marker check (attempt 2): $MARKER"

if [[ "$MARKER" == "YES" ]] && check_ordering "$RESET_EPOCH"; then
  log "loaded=YES (after retry) — migration marker present and ordering confirmed"
  echo "loaded=YES"
  exit 0
fi

# Persistent loaded=NO — send operator alert
ALERT_MSG="[A.2 ALERT] loaded=NO on box ${BOX} after 2 attempts. Migration marker absent or ordering mismatch. Check $AGENTS_MD and sessions.json. Action required: verify wire.sh ran and re-run update-skills.sh."
log "ALERT: $ALERT_MSG"
log "Sending operator alert to Telegram chat $OPERATOR_CHAT"

openclaw message send \
  --channel telegram \
  --target "$OPERATOR_CHAT" \
  --message "$ALERT_MSG" 2>/dev/null || log "WARNING: operator alert send failed (non-fatal)"

echo "loaded=NO"
log "=== A.2 Session Load Gate FAILED. Exiting 1. ==="
exit 1
