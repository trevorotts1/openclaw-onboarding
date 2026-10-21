#!/usr/bin/env bash
# install-keepalive-cron.sh - register the skill 75 run keepalive (ONE cron).
#
# WHAT THIS DOES
#   Registers exactly one `openclaw` cron job named `skill75-keepalive`, every
#   10 minutes, whose prompt is timer-artifacts/keepalive-cron-prompt.txt with
#   __SKILL_ROOT__ / __RUNS_DIR__ substituted. The prompt tells the box's one
#   bound agent to run scripts/core/heartbeat/run_watch.py for its active run
#   and deliver message_for_client on the client's own Telegram lane.
#
#   Silence and cost, on purpose:
#     * --no-deliver on the cron itself, so a fire never announces on its own -
#       the ONLY text the client ever sees is run_watch's message, sent through
#       the same sender the choice card uses (intake_card.openclaw_send_argv).
#     * a cheap/local model pinned with --model (SKILL75_KEEPALIVE_MODEL, or the
#       default below). A CLI that has no --model registers without it and says
#       so loudly - it never pretends the model was pinned.
#     * --session isolated when the CLI advertises it, so the job can never
#       land on the client-facing main session (2026.6.11+ rejects a
#       main-session --message job outright).
#     * ONE agent: --agent only when SKILL75_KEEPALIVE_AGENT or DS_AGENT_ID is
#       set; a box with one bound agent needs no name and none is guessed.
#
# IDEMPOTENT AND TOMBSTONE-RESPECTING
#   * exact-name presence check against `cron list --json` (never the truncated
#     text table) - present = nothing to do, UNKNOWN = do NOT register (a
#     failed list must never become a duplicate cron), absent = register once.
#   * a durable tombstone marker under <OC_ROOT>/workspace/.cron-tombstones is
#     checked BEFORE registering; uninstall.sh writes it, so a deliberate
#     removal survives this registrar's next run. Same discipline as
#     shared-utils/cron-lib.sh (oc_cron_present / oc_cron_tombstoned), kept
#     self-contained here so the script works on a box without that file.
#
# MODES
#   --dry-run  (DEFAULT) print the exact command, register nothing, exit 0.
#   --apply    register the job (check-first, idempotent).
#
# CLI
#   bash install-keepalive-cron.sh [--dry-run|--apply]
#        [--agent NAME] [--model ID] [--runs-dir DIR]
#
# EXIT
#   0  already present, or registered this run, or dry-run printed the plan
#   2  this skill's own prompt file is missing (repo defect)
#   3  openclaw CLI absent, presence UNKNOWN, or registration failed - non-fatal
#      and re-run safe (a later run backfills)
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$HERE/.." && pwd)"
PROMPT_FILE="$HERE/keepalive-cron-prompt.txt"

NAME="skill75-keepalive"
CRON="*/10 * * * *"
MODE="dry-run"
AGENT="${SKILL75_KEEPALIVE_AGENT:-${DS_AGENT_ID:-}}"
MODEL="${SKILL75_KEEPALIVE_MODEL:-ollama/deepseek-v4.1-flash:cloud}"
OPENCLAW_BIN="${OPENCLAW_BIN:-openclaw}"

# The persistent runs dir for this platform (INSTRUCTIONS.md "Studio orders").
if [ -n "${SKILL75_KEEPALIVE_RUNS_DIR:-}" ]; then
  RUNS_DIR="$SKILL75_KEEPALIVE_RUNS_DIR"
elif [ -d /data/.openclaw ]; then
  RUNS_DIR="/data/.openclaw/drama-runs"
elif [ -d "$HOME/.openclaw" ]; then
  RUNS_DIR="$HOME/.openclaw/drama-runs"
else
  RUNS_DIR="$HOME/.openclaw/drama-runs"
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)  MODE="dry-run"; shift ;;
    --apply)    MODE="apply"; shift ;;
    --agent)    AGENT="${2:-}"; shift 2 ;;
    --model)    MODEL="${2:-}"; shift 2 ;;
    --runs-dir) RUNS_DIR="${2:-}"; shift 2 ;;
    -h|--help)  sed -n '2,44p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

_log() { echo "[install-keepalive-cron] $*"; }

if [ ! -f "$PROMPT_FILE" ]; then
  _log "FAIL prompt file not found: $PROMPT_FILE"
  exit 2
fi

# --- presence: exact name against JSON, never the truncated text table -------
_cron_present() {
  local raw
  raw="$("$OPENCLAW_BIN" cron list --json 2>/dev/null)" || return 2
  [ -n "$raw" ] || return 2
  if command -v jq >/dev/null 2>&1; then
    local verdict
    verdict=$(printf '%s' "$raw" | jq -r --arg n "$NAME" '
        ( if type == "array" then . elif (type == "object" and (.jobs | type) == "array") then .jobs else empty end )
        | map(select(.name == $n)) | length > 0' 2>/dev/null) || return 2
    case "$verdict" in
      true) return 0 ;;
      false) return 1 ;;
      *) return 2 ;;
    esac
  fi
  if command -v python3 >/dev/null 2>&1; then
    # JSON via the environment: `python3 -` already reads its script on stdin.
    OC_CRON_RAW="$raw" python3 - "$NAME" 2>/dev/null <<'PYEOF'
import json, os, sys
name = sys.argv[1]
try:
    data = json.loads(os.environ.get("OC_CRON_RAW", ""))
    jobs = data if isinstance(data, list) else data["jobs"]
    if not isinstance(jobs, list):
        raise ValueError
except Exception:
    sys.exit(2)
sys.exit(0 if any(isinstance(j, dict) and j.get("name") == name for j in jobs) else 1)
PYEOF
    return $?
  fi
  return 2
}

# --- durable tombstone (only the operator's uninstall writes one) ------------
# Resolves the path only; a --dry-run must write nothing at all, so the
# directory is never created here.
_tombstone_dir() {
  local root
  if [ -d /data/.openclaw ]; then root="/data/.openclaw"
  elif [ -d "$HOME/.openclaw" ]; then root="$HOME/.openclaw"
  else return 1; fi
  printf '%s' "$root/workspace/.cron-tombstones"
}

_tombstoned() {
  local dir
  dir="$(_tombstone_dir)" || return 1
  [ -f "$dir/$NAME" ]
}

if _tombstoned; then
  _log "SKIP $NAME is tombstoned (an operator removed it) - not registering"
  exit 0
fi

if ! command -v "$OPENCLAW_BIN" >/dev/null 2>&1; then
  _log "SKIP openclaw CLI not on PATH - cannot register '$NAME'. Re-run once it is installed."
  exit 3
fi

_cron_present && _present=0 || _present=$?
if [ "$_present" -eq 2 ]; then
  _log "FAIL could not read 'cron list --json' - presence of '$NAME' UNKNOWN, NOT registering (would risk a duplicate). Re-run to backfill."
  exit 3
fi
if [ "$_present" -eq 0 ]; then
  _log "OK $NAME already present - nothing to do"
  exit 0
fi

# --- the prompt (placeholders substituted, never a second copy) --------------
PROMPT="$(sed -e "s|__SKILL_ROOT__|$SKILL_ROOT|g" -e "s|__RUNS_DIR__|$RUNS_DIR|g" "$PROMPT_FILE")"
[ -n "$PROMPT" ] || { _log "FAIL prompt file rendered empty: $PROMPT_FILE"; exit 2; }

# --- feature-detect the flags this CLI build actually accepts ----------------
_help="$("$OPENCLAW_BIN" cron add --help 2>&1 || true)"
_has() { printf '%s' "$_help" | grep -q -- "$1"; }

_register() {
  local with_model="$1"
  set -- --name "$NAME" --cron "$CRON" --message "$PROMPT"
  [ -n "$AGENT" ] && set -- "$@" --agent "$AGENT"
  _has --no-deliver && set -- "$@" --no-deliver
  _has --session && set -- "$@" --session isolated
  if [ "$with_model" = "yes" ] && [ -n "$MODEL" ] && _has --model; then
    set -- "$@" --model "$MODEL"
  fi
  if [ "$MODE" = "dry-run" ]; then
    printf '%s cron add' "$OPENCLAW_BIN"
    for a in "$@"; do printf ' %q' "$a"; done
    printf '\n'
    return 0
  fi
  "$OPENCLAW_BIN" cron add "$@" >/dev/null 2>&1
}

if [ "$MODE" = "dry-run" ]; then
  _log "DRY-RUN plan (nothing registered). Runs dir: $RUNS_DIR"
  _register yes
  _log "Re-run with --apply to register '$NAME' ($CRON)."
  exit 0
fi

_register yes && _ok=1 || _ok=0
_cron_present && _landed=1 || _landed=0
if [ "$_landed" -ne 1 ] && [ -n "$MODEL" ] && _has --model; then
  _log "WARN registration with --model '$MODEL' did not land - retrying WITHOUT a pinned model (the job must exist; say so rather than pretend)."
  _register no && _ok=1 || _ok=0
  _cron_present && _landed=1 || _landed=0
fi

if [ "$_landed" -eq 1 ]; then
  _log "DONE $NAME registered ($CRON, silent, agent=${AGENT:-the agent this box binds}, model=$([ -n "$MODEL" ] && _has --model && printf '%s' "$MODEL" || printf 'unpinned'))"
  exit 0
fi

_log "FAIL could not register '$NAME' (cron add rc=$_ok). Non-fatal - re-run to backfill."
_log "  Manual: $OPENCLAW_BIN cron add --name $NAME --cron '$CRON' --no-deliver --message '<the rendered prompt>'"
exit 3
