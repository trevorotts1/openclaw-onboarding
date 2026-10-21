#!/usr/bin/env bash
# uninstall.sh - remove the skill 75 run keepalive cron, durably.
#
# WHAT THIS DOES
#   1. Writes the durable tombstone marker FIRST
#      (<OC_ROOT>/workspace/.cron-tombstones/skill75-keepalive), so
#      install-keepalive-cron.sh can never resurrect the job on its next run -
#      the same oc_cron_tombstone / oc_cron_tombstoned discipline as
#      shared-utils/cron-lib.sh, kept self-contained here.
#   2. Removes the ONE job named skill75-keepalive, feature-detecting the
#      removal subcommand this CLI build accepts (rm | remove | delete).
#   3. Verifies it is gone by exact name against `cron list --json`.
#
#   Idempotent: running it twice is safe, and an already-tombstoned box just
#   repeats step 2. It never touches another cron, never edits a run folder and
#   never prints a secret.
#
# CLI
#   bash uninstall.sh [--dry-run|--apply]
#
#   --dry-run (DEFAULT) prints the plan: the tombstone path and the removal
#   command it would run. Writes nothing.
#   --apply   writes the tombstone and removes the job.
#
# EXIT
#   0  removed, already absent, or dry-run printed the plan
#   3  no removal subcommand on this CLI build, or removal failed - the
#      tombstone is still written, so the job stays removed after the next
#      gateway restart; the manual command is printed
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="skill75-keepalive"
MODE="dry-run"
OPENCLAW_BIN="${OPENCLAW_BIN:-openclaw}"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) MODE="dry-run"; shift ;;
    --apply)   MODE="apply"; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

_log() { echo "[uninstall-keepalive-cron] $*"; }

_tombstone_dir() {
  local root
  if [ -d /data/.openclaw ]; then root="/data/.openclaw"
  elif [ -d "$HOME/.openclaw" ]; then root="$HOME/.openclaw"
  else return 1; fi
  [ "${1:-}" = "create" ] && { mkdir -p "$root/workspace/.cron-tombstones" 2>/dev/null || true; }
  printf '%s' "$root/workspace/.cron-tombstones"
}

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

TDIR="$(_tombstone_dir)" || TDIR=""
MARKER="${TDIR:+$TDIR/$NAME}"

# The removal subcommand this CLI build actually has.
_SUB=""
if command -v "$OPENCLAW_BIN" >/dev/null 2>&1; then
  for sub in rm remove delete; do
    if "$OPENCLAW_BIN" cron "$sub" --help >/dev/null 2>&1; then _SUB="$sub"; break; fi
  done
fi

if [ "$MODE" = "dry-run" ]; then
  _log "DRY-RUN plan (nothing written):"
  _log "  tombstone: ${MARKER:-<OC_ROOT>/workspace/.cron-tombstones/$NAME}"
  if [ -n "$_SUB" ]; then
    _log "  remove:    $OPENCLAW_BIN cron $_SUB --name $NAME"
  else
    _log "  remove:    no 'cron rm|remove|delete' on this CLI build - print and hand off"
  fi
  _log "Re-run with --apply to tombstone and remove '$NAME'."
  exit 0
fi

# 1. Tombstone FIRST: even if removal fails, a re-install cannot resurrect it.
if [ -z "$MARKER" ]; then
  _log "WARN no OpenClaw root resolves (/data/.openclaw or \$HOME/.openclaw) - cannot write the tombstone. Say so; do not pretend."
else
  _tombstone_dir create >/dev/null 2>&1 || true
  {
    printf 'TOMBSTONED %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)"
    printf 'name: %s\n' "$NAME"
    printf 'reason: %s\n' "${SKILL75_KEEPALIVE_TOMBSTONE_REASON:-removed by uninstall.sh}"
    printf 'host: %s\n' "$(hostname 2>/dev/null || echo box)"
  } > "$MARKER" 2>/dev/null || _log "WARN could not write the tombstone at $MARKER"
fi

# 2. Already gone? Then the tombstone alone is the whole job.
_cron_present && _present=0 || _present=$?
if [ "$_present" -eq 1 ]; then
  _log "OK $NAME is not registered - tombstone written, nothing to remove"
  exit 0
fi
if [ "$_present" -eq 2 ]; then
  _log "WARN could not read 'cron list --json' - cannot verify removal. Tombstone written; re-run once the gateway answers."
  exit 3
fi

# 3. Remove it, and prove it is gone.
if [ -z "$_SUB" ]; then
  _log "FAIL no 'cron rm|remove|delete' on this CLI build. Tombstone is written (a re-install cannot resurrect it)."
  _log "  Manual: $OPENCLAW_BIN cron remove --name $NAME   # or the build's own removal command"
  exit 3
fi

"$OPENCLAW_BIN" cron "$_SUB" --name "$NAME" >/dev/null 2>&1
_cron_present && _still=1 || _still=0
if [ "$_still" -eq 1 ]; then
  _log "FAIL '$OPENCLAW_BIN cron $_SUB --name $NAME' did not remove it. Tombstone is written."
  exit 3
fi
_log "DONE $NAME removed and tombstoned - install-keepalive-cron.sh will not re-register it"
exit 0
