#!/usr/bin/env bash
# PRD Addendum A.2 v2 — Session Load Gate
#
# REWRITE of the broken grep-on-disk + mtime-tautology approach in #160.
# "Loaded" is NOW defined as: the running agent's freshly-rebuilt post-reset
# context actually contains the NEW core-file content (a unique canary).
#
# TWO LEGS (delegates to shared-utils/a2_load_assert.py):
#   LEG A: sessions.reset mints a new sessionId (deterministic re-init signal).
#          Does NOT need a live model.
#   LEG B: (GOLD) unique canary token written into SOUL.md, second reset,
#          probe sent via `openclaw message send`, chat.history polled for
#          the echo.  Needs a live model + CEO chat target.
#
# loaded_confidence → {HIGH, MEDIUM, UNKNOWN, LOW}
#   HIGH    : both legs passed.    EXIT 0, green-light.
#   MEDIUM  : LEG A passed, LEG B inconclusive (non-model reason).
#             EXIT 0, but NOT a full green-light.
#   UNKNOWN : no live model.  EXIT 0, no operator alert.
#   LOW     : LEG A failed.   EXIT 1, OPERATOR ALERT FIRED.
#
# NEVER calls `openclaw gateway restart` — only `gateway call sessions.reset`.
# NEVER sends operator alert via direct telegram curl — only `openclaw message send`.
# NEVER borrows another box's API key or gateway endpoint.
#
# Usage:
#   scripts/a2-session-load-gate.sh --box <name> \
#       [--workspace <path>] [--ceo-chat-id <id>] [--probe-timeout <seconds>]
#
# Env overrides (for testing):
#   SESSIONS_JSON_OVERRIDE    — override sessions.json path
#   A2_PROBE_TIMEOUT          — max seconds to poll for canary echo (default 90)
#   A2_POLL_INTERVAL          — poll interval (default 5)
#   OPERATOR_TELEGRAM_CHAT_ID — operator alert chat (default 5252140759)
#   FLEET_REFRESH_ROOT        — openclaw root dir override

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
BOX=""
WORKSPACE_OVERRIDE=""
CEO_CHAT_ID=""
PROBE_TIMEOUT="${A2_PROBE_TIMEOUT:-90}"
POLL_INTERVAL="${A2_POLL_INTERVAL:-5}"
OPERATOR_CHAT="${OPERATOR_TELEGRAM_CHAT_ID:-5252140759}"

# ── Parse args ─────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --box)           BOX="$2";                shift 2 ;;
    --workspace)     WORKSPACE_OVERRIDE="$2"; shift 2 ;;
    --ceo-chat-id)   CEO_CHAT_ID="$2";        shift 2 ;;
    --probe-timeout) PROBE_TIMEOUT="$2";      shift 2 ;;
    --poll-interval) POLL_INTERVAL="$2";      shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$BOX" ]] && { echo "ERROR: --box is required" >&2; exit 1; }

# ── Locate shared-utils ────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SHARED_UTILS="$REPO_ROOT/shared-utils"
LOAD_ASSERT_PY="$SHARED_UTILS/a2_load_assert.py"

if [[ ! -f "$LOAD_ASSERT_PY" ]]; then
  echo "ERROR: shared-utils/a2_load_assert.py not found at $LOAD_ASSERT_PY" >&2
  exit 1
fi

# ── Platform detection & paths ─────────────────────────────────────────────────
if [[ -n "${FLEET_REFRESH_ROOT:-}" ]]; then
  OC_ROOT="$FLEET_REFRESH_ROOT"
elif [[ -d "/data/.openclaw" ]]; then
  OC_ROOT="/data/.openclaw"
else
  OC_ROOT="$HOME/.openclaw"
fi

if [[ -n "$WORKSPACE_OVERRIDE" ]]; then
  WORKSPACE="$WORKSPACE_OVERRIDE"
else
  WORKSPACE="$OC_ROOT/workspace"
fi

SESSIONS_JSON="${SESSIONS_JSON_OVERRIDE:-$OC_ROOT/agents/main/sessions/sessions.json}"

# ── Log setup ──────────────────────────────────────────────────────────────────
LOG_DIR="$OC_ROOT/skills"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/.a2-load-gate.log"

log() {
  local msg="[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] [a2-session-load-gate] [$BOX] $*"
  echo "$msg" >&2
  echo "$msg" >> "$LOG_FILE"
}

# ── Lockfile ───────────────────────────────────────────────────────────────────
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

log "=== A.2 v2 Session Load Gate starting. Box: $BOX ==="
log "OC_ROOT: $OC_ROOT  WORKSPACE: $WORKSPACE"
log "SESSIONS_JSON: $SESSIONS_JSON"

# ── Resolve session key from sessions.json ─────────────────────────────────────
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

log "Session key: $SESSION_KEY"

# ── Auto-detect CEO chat ID if not provided ────────────────────────────────────
# The chat ID is the numeric suffix of the session key
if [[ -z "$CEO_CHAT_ID" ]]; then
  CEO_CHAT_ID="${SESSION_KEY##*:}"
  if [[ "$CEO_CHAT_ID" == "$SESSION_KEY" ]]; then
    CEO_CHAT_ID=""
  else
    log "Auto-detected CEO chat ID: $CEO_CHAT_ID"
  fi
fi

# ── Build python3 args ─────────────────────────────────────────────────────────
PY_ARGS=(
  "$LOAD_ASSERT_PY"
  --box "$BOX"
  --session-key "$SESSION_KEY"
  --probe-timeout "$PROBE_TIMEOUT"
  --poll-interval "$POLL_INTERVAL"
  --workspace "$WORKSPACE"
  --sessions-json "$SESSIONS_JSON"
)
[[ -n "$CEO_CHAT_ID" ]] && PY_ARGS+=(--ceo-chat-id "$CEO_CHAT_ID")

# ── Run the assertion ──────────────────────────────────────────────────────────
log "Delegating to a2_load_assert.py ..."

PY_EXIT=0
PY_OUT=$(python3 "${PY_ARGS[@]}" 2>/dev/null) || PY_EXIT=$?

log "a2_load_assert.py exit: $PY_EXIT"
log "Result JSON: $PY_OUT"

# ── Parse confidence from result JSON ──────────────────────────────────────────
CONFIDENCE=$(python3 -c "
import json, sys
try:
    d = json.loads(sys.stdin.read())
    print(d.get('loaded_confidence', 'LOW'))
except Exception:
    print('LOW')
" <<< "$PY_OUT" 2>/dev/null || echo "LOW")

PRESENT=$(python3 -c "
import json, sys
try:
    d = json.loads(sys.stdin.read())
    print('true' if d.get('present') else 'false')
except Exception:
    print('false')
" <<< "$PY_OUT" 2>/dev/null || echo "false")

log "loaded_confidence=$CONFIDENCE  present=$PRESENT"
echo "loaded_confidence=$CONFIDENCE"
echo "loaded_present=$PRESENT"

# ── Operator alert (only on LOW/FAIL) ──────────────────────────────────────────
if [[ "$CONFIDENCE" == "LOW" ]]; then
  ERRORS=$(python3 -c "
import json, sys
try:
    d = json.loads(sys.stdin.read())
    errs = d.get('errors', [])
    print('; '.join(errs[:3]) if errs else 'session did not re-initialize')
except Exception:
    print('session did not re-initialize')
" <<< "$PY_OUT" 2>/dev/null || echo "session did not re-initialize")

  ALERT_MSG="[A.2 v2 ALERT] loaded_confidence=LOW on box ${BOX}. LEG A (session re-init) failed: ${ERRORS}. Action required: verify openclaw gateway is healthy, re-run update-skills.sh."
  log "Sending LOW/FAIL operator alert to chat $OPERATOR_CHAT"

  openclaw message send \
    --channel telegram \
    --target "$OPERATOR_CHAT" \
    --message "$ALERT_MSG" 2>/dev/null \
  || log "WARNING: operator alert send failed (non-fatal)"

  log "=== A.2 v2 Session Load Gate FAILED (LOW). Exiting 1. ==="
  exit 1
fi

if [[ "$CONFIDENCE" == "UNKNOWN" ]]; then
  log "loaded_confidence=UNKNOWN (no live model; deterministic re-init signal only). No operator alert."
  echo "loaded=UNKNOWN"
  exit 0
fi

if [[ "$CONFIDENCE" == "MEDIUM" ]]; then
  log "loaded_confidence=MEDIUM (LEG A passed; LEG B inconclusive — non-model reason). Not a full green-light."
  echo "loaded=MEDIUM"
  exit 0
fi

# HIGH
log "loaded_confidence=HIGH — both legs passed. GREEN-LIGHT."
echo "loaded=HIGH"
exit 0
