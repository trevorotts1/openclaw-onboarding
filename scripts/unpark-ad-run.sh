#!/usr/bin/env bash
# unpark-ad-run.sh — operator inspect/clear for PARKED Facebook & Instagram ad runs
# (Skill 48). Mirrors scripts/unpark-build.sh: a parked run is held by a DURABLE
# checkpoint (working/checkpoints/PARKED.json in the run dir + a box-level pointer
# under $OC_ROOT/workspace/.park/fbad/<run_id>.parked) that survives a reboot.
#
# A park NEVER auto-clears: the foreman only continues when the blocker's REAL checker
# passes on `ad_director.py --resume`. This tool is the operator's view + a manual
# clear of the durable pointer. Clearing the pointer does NOT bypass a gate — a resume
# still re-runs the real check, and a still-failing blocker re-parks.
#
# USAGE:
#   bash scripts/unpark-ad-run.sh                 # list every parked fbad run
#   bash scripts/unpark-ad-run.sh --status        # same (explicit)
#   bash scripts/unpark-ad-run.sh --run-id <id>   # inspect one parked run's checkpoint
#   bash scripts/unpark-ad-run.sh --run-id <id> --clear [--dry-run]
#                                                 # remove ONE park's durable markers
#                                                 # (then `ad_director.py --resume` it)
#   bash scripts/unpark-ad-run.sh --dry-run       # show what WOULD change, change nothing
#
# Runs as the BOX user (never root). Idempotent + fail-soft. Ledgers to
# $OC_ROOT/workspace/.park/fbad/unpark.log.

set -u
UNPARK_AD_VERSION="v14.3.0"

if [ -n "${FBAD_OC_ROOT:-}" ]; then
  OC_ROOT="$FBAD_OC_ROOT"
elif [ -d /data/.openclaw ]; then
  OC_ROOT=/data/.openclaw
elif [ -d "${HOME:-}/.openclaw" ]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[unpark-ad-run] no OpenClaw root found (.openclaw absent) — nothing to inspect" >&2
  exit 0
fi

PARK_DIR="$OC_ROOT/workspace/.park/fbad"
LEDGER="$PARK_DIR/unpark.log"

MODE="status"
RUN_ID=""
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --status)  MODE="status" ;;
    --run-id)  shift; RUN_ID="${1:-}"; MODE="inspect" ;;
    --clear)   MODE="clear" ;;
    --dry-run) DRY=1 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "[unpark-ad-run] unknown arg '$1'. Use --status | --run-id <id> [--clear] | --dry-run | --help" >&2; exit 64 ;;
  esac
  shift
done

_ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
ledger() {
  mkdir -p "$PARK_DIR" 2>/dev/null || true
  printf '%s %s\n' "$(_ts)" "$*" >> "$LEDGER" 2>/dev/null || true
  echo "[unpark-ad-run] $*"
}

_pointer_for() { echo "$PARK_DIR/$1.parked"; }
_rundir_of()   { python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('run_dir',''))" "$1" 2>/dev/null; }

list_parked() {
  echo "── unpark-ad-run $UNPARK_AD_VERSION — parked FB/IG ad runs on $(hostname 2>/dev/null || echo box) ──"
  echo "OC_ROOT  : $OC_ROOT"
  echo "PARK DIR : $PARK_DIR"
  if [ ! -d "$PARK_DIR" ] || [ -z "$(ls -1 "$PARK_DIR"/*.parked 2>/dev/null)" ]; then
    echo "(no parked runs)"
    return 0
  fi
  for p in "$PARK_DIR"/*.parked; do
    [ -f "$p" ] || continue
    python3 - "$p" <<'PY' 2>/dev/null || echo "  - $p (unreadable)"
import json, sys
d = json.load(open(sys.argv[1]))
print(f"  - run_id={d.get('run_id')}  by={d.get('parked_by_af')}  class={d.get('park_class')}")
print(f"      run_dir={d.get('run_dir')}")
print(f"      parked_at={d.get('parked_at')}")
PY
  done
}

inspect_one() {
  local ptr; ptr="$(_pointer_for "$RUN_ID")"
  if [ ! -f "$ptr" ]; then
    echo "[unpark-ad-run] no parked run with run_id='$RUN_ID' (pointer $ptr absent)." >&2
    return 1
  fi
  echo "── parked run $RUN_ID ──"
  sed 's/^/  /' "$ptr" 2>/dev/null || true
  local rd; rd="$(_rundir_of "$ptr")"
  local chk="$rd/working/checkpoints/PARKED.json"
  if [ -f "$chk" ]; then
    echo "  ── checkpoint $chk ──"
    sed 's/^/    /' "$chk" 2>/dev/null || true
  else
    echo "  (run-dir checkpoint PARKED.json not found at $chk — pointer is stale)"
  fi
  echo ""
  echo "  To continue once the blocker is fixed:  python3 48-facebook-ad-generator/scripts/ad_director.py --run-dir '$rd' --resume"
}

clear_one() {
  local ptr; ptr="$(_pointer_for "$RUN_ID")"
  if [ ! -f "$ptr" ]; then
    echo "[unpark-ad-run] no parked run with run_id='$RUN_ID' (pointer $ptr absent)." >&2
    return 1
  fi
  local rd; rd="$(_rundir_of "$ptr")"
  local chk="$rd/working/checkpoints/PARKED.json"
  if [ "$DRY" = "1" ]; then
    echo "── DRY RUN — would clear park markers for run_id=$RUN_ID ──"
    echo "  WOULD remove: $ptr"
    [ -f "$chk" ] && echo "  WOULD remove: $chk"
    echo "  (a resume still re-runs the REAL checker; a still-failing blocker re-parks)"
    return 0
  fi
  ledger "CLEAR run_id=$RUN_ID run_dir=$rd"
  rm -f "$ptr" 2>/dev/null && ledger "removed box pointer $ptr" || ledger "WARN could not remove $ptr"
  if [ -n "$rd" ] && [ -f "$chk" ]; then
    rm -f "$chk" 2>/dev/null && ledger "removed checkpoint $chk" || ledger "WARN could not remove $chk"
  fi
  ledger "CLEARED run_id=$RUN_ID — now run: ad_director.py --run-dir '$rd' --resume"
  echo ""
  echo "Done. Park markers for $RUN_ID cleared. Resume with the command above (the real"
  echo "check re-runs on resume — clearing the marker did NOT bypass any gate)."
}

case "$MODE" in
  status)  list_parked ;;
  inspect) [ "$DRY" = "1" ] && { echo "(--dry-run with --run-id only inspects)"; }; inspect_one ;;
  clear)   [ -z "$RUN_ID" ] && { echo "[unpark-ad-run] --clear requires --run-id <id>" >&2; exit 64; }; clear_one ;;
esac
exit 0
