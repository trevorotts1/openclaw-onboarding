#!/usr/bin/env bash
# unpark-build.sh — the ONE intentional, operator-triggered un-park path.
#
# WHY THIS EXISTS (v14.1.5, fix/stuck-build-park-loop-durable):
#   A stuck/flaky build is PARKED by a DURABLE marker that survives a reboot:
#     • 06-ghl-install-pages/tools/browser_manager.sh (agent-browser circuit-
#       breaker) writes it when it trips, and
#     • 23-ai-workforce-blueprint/scripts/resume-workforce-build.sh writes it
#       after MAX_STUCK_FIRES consecutive no-progress fires and DISABLES its cron.
#   While parked, the resume cron does NOT re-fire and the cron registrar
#   (scripts/ensure-pipeline-crons.sh) does NOT resurrect it. That is deliberate:
#   AUTO-RESUME NEVER HAPPENS SILENTLY. The ONLY way back to a running build is an
#   operator running THIS script — after they have looked at why it was stuck.
#
# WHAT IT DOES (idempotent, fail-soft, runs as the BOX user — never root):
#   1. Clears the canonical box-level PARK marker.
#   2. Clears the agent-browser breaker markers (durable + legacy TMPDIR path).
#   3. Resets the stuck/run counters + progress fingerprint.
#   4. Resets the one-shot escalation flags + resumeAttempts in the build-state.
#   5. Re-registers the workforce-build-resume cron via ensure-pipeline-crons.sh
#      (now allowed, because the park marker is gone) so the build resumes.
#   6. Ledgers every change to $OC_ROOT/workspace/.park/unpark.log.
#
# It touches ONLY the park/breaker/resume state and the workforce-build-resume
# cron. It NEVER touches a legitimate client/business cron.
#
# USAGE:
#   bash scripts/unpark-build.sh            # un-park + re-register the resume cron
#   bash scripts/unpark-build.sh --status   # show current park state, change nothing
#   bash scripts/unpark-build.sh --dry-run  # show what WOULD change, change nothing
#   bash scripts/unpark-build.sh --no-cron  # un-park but do NOT re-register the cron

set -u

UNPARK_BUILD_VERSION="v14.1.5"

# ---- platform detection (VPS /data first, then Mac $HOME) — mirrors every
#      other pipeline script so paths resolve identically on both. ----
if [ -d /data/.openclaw ]; then
  OC_ROOT=/data/.openclaw
elif [ -d "${HOME:-}/.openclaw" ]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[unpark-build] no OpenClaw root found (.openclaw absent) — nothing to un-park" >&2
  exit 0
fi

PARK_DIR="$OC_ROOT/workspace/.park"
BOX_PARK_MARKER="$PARK_DIR/workforce-build.parked"
STUCK_COUNT_FILE="$OC_ROOT/workspace/.workforce-build-resume-stuck.count"
PROGRESS_FP_FILE="$OC_ROOT/workspace/.workforce-build-resume-progress.fp"
RUN_COUNT_FILE="$OC_ROOT/workspace/.workforce-build-resume-runs.count"
STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"
LEDGER="$PARK_DIR/unpark.log"
LEGACY_BREAKER_DIR="${TMPDIR:-/tmp}/agent-browser/breaker"

MODE="apply"
RE_REGISTER=1
case "${1:-}" in
  --status)  MODE="status" ;;
  --dry-run) MODE="dryrun" ;;
  --no-cron) RE_REGISTER=0 ;;
  "" )       : ;;
  -h|--help)
    grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *)
    echo "[unpark-build] unknown arg '${1}'. Use --status | --dry-run | --no-cron | --help" >&2
    exit 64 ;;
esac

_ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
ledger() {
  mkdir -p "$PARK_DIR" 2>/dev/null || true
  printf '%s %s\n' "$(_ts)" "$*" >> "$LEDGER" 2>/dev/null || true
  echo "[unpark-build] $*"
}

# ---- STATUS: report current park state, change nothing ----
print_status() {
  echo "── unpark-build $UNPARK_BUILD_VERSION — park status on $(hostname 2>/dev/null || echo box) ──"
  echo "OC_ROOT      : $OC_ROOT"
  if [ -f "$BOX_PARK_MARKER" ]; then
    echo "PARK MARKER  : PRESENT — build is PARKED"
    echo "  $BOX_PARK_MARKER:"
    sed 's/^/    /' "$BOX_PARK_MARKER" 2>/dev/null || true
  else
    echo "PARK MARKER  : absent — build is NOT parked"
  fi
  local _bk
  _bk=$(ls -1 "$PARK_DIR"/agent-browser-*.BLOCKED 2>/dev/null | wc -l | tr -d '[:space:]')
  echo "BREAKER MARKS: ${_bk:-0} (durable) + $(ls -1 "$LEGACY_BREAKER_DIR"/*.BLOCKED 2>/dev/null | wc -l | tr -d '[:space:]') (legacy TMPDIR)"
  [ -f "$STUCK_COUNT_FILE" ] && echo "STUCK COUNT  : $(cat "$STUCK_COUNT_FILE" 2>/dev/null)" || echo "STUCK COUNT  : 0"
  if command -v openclaw >/dev/null 2>&1; then
    if openclaw cron list 2>/dev/null | grep -q "workforce-build-resume"; then
      echo "RESUME CRON  : present"
    else
      echo "RESUME CRON  : absent (disabled / self-removed)"
    fi
  fi
}

if [ "$MODE" = "status" ]; then
  print_status
  exit 0
fi

# ---- count what is present (so a no-op un-park is honest about it) ----
_had_park=0; [ -f "$BOX_PARK_MARKER" ] && _had_park=1
_n_breaker=$(ls -1 "$PARK_DIR"/agent-browser-*.BLOCKED "$PARK_DIR"/agent-browser-*.count \
              "$LEGACY_BREAKER_DIR"/*.BLOCKED "$LEGACY_BREAKER_DIR"/*.count 2>/dev/null | wc -l | tr -d '[:space:]')

if [ "$MODE" = "dryrun" ]; then
  echo "── unpark-build $UNPARK_BUILD_VERSION — DRY RUN (no changes) ──"
  print_status
  echo ""
  echo "WOULD: remove park marker (present=$_had_park), clear $_n_breaker breaker file(s),"
  echo "       reset stuck/run counters + progress fingerprint, reset escalation flags,"
  echo "       and $([ "$RE_REGISTER" = "1" ] && echo 're-register' || echo 'NOT re-register') the workforce-build-resume cron."
  exit 0
fi

# ---- APPLY ----
ledger "UNPARK START ($UNPARK_BUILD_VERSION) on $(hostname 2>/dev/null || echo box); park_present=$_had_park breaker_files=$_n_breaker"

# 1. Canonical box-level park marker.
if [ -f "$BOX_PARK_MARKER" ]; then
  rm -f "$BOX_PARK_MARKER" 2>/dev/null && ledger "cleared park marker: $BOX_PARK_MARKER" \
    || ledger "WARN could not remove park marker: $BOX_PARK_MARKER"
else
  ledger "no park marker present (already un-parked) — proceeding to clear counters/breaker anyway"
fi

# 2. agent-browser breaker markers — durable dir + legacy TMPDIR dir (best-effort).
rm -f "$PARK_DIR"/agent-browser-*.BLOCKED "$PARK_DIR"/agent-browser-*.count 2>/dev/null || true
rm -f "$LEGACY_BREAKER_DIR"/*.BLOCKED "$LEGACY_BREAKER_DIR"/*.count 2>/dev/null || true
ledger "cleared agent-browser breaker markers (durable + legacy TMPDIR)"

# 3. Stuck/run counters + progress fingerprint.
rm -f "$STUCK_COUNT_FILE" "$PROGRESS_FP_FILE" "$RUN_COUNT_FILE" 2>/dev/null || true
ledger "reset stuck/run counters + progress fingerprint"

# 4. Reset one-shot escalation flags + give the build a fresh attempt budget.
if [ -f "$STATE_FILE" ] && command -v jq >/dev/null 2>&1; then
  _tmp_u=$(mktemp 2>/dev/null || echo "$STATE_FILE.unpark.tmp")
  if jq '
        .resumeAttempts = 0
        | del(.stuckParkEscalated, .resumeCapEscalated, .rescueRangersEscalated, .librariesNearCapNotified)
      ' "$STATE_FILE" > "$_tmp_u" 2>/dev/null && [ -s "$_tmp_u" ]; then
    mv "$_tmp_u" "$STATE_FILE" && ledger "reset build-state: resumeAttempts=0 + cleared one-shot escalation flags"
  else
    rm -f "$_tmp_u" 2>/dev/null || true
    ledger "WARN could not rewrite build-state escalation flags (non-fatal)"
  fi
else
  ledger "no build-state/jq — skipped state-flag reset (non-fatal)"
fi

# 5. Re-register the workforce-build-resume cron (now allowed; park marker is gone).
if [ "$RE_REGISTER" = "1" ]; then
  ENSURE=""
  for _cand in \
    "$OC_ROOT/onboarding/scripts/ensure-pipeline-crons.sh" \
    "$OC_ROOT/scripts/ensure-pipeline-crons.sh" \
    "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)/ensure-pipeline-crons.sh"; do
    [ -n "$_cand" ] && [ -f "$_cand" ] && ENSURE="$_cand" && break
  done
  if [ -n "$ENSURE" ]; then
    if bash "$ENSURE" >>"$LEDGER" 2>&1; then
      ledger "re-registered pipeline crons via $ENSURE (workforce-build-resume restored)"
    else
      ledger "WARN ensure-pipeline-crons.sh returned non-zero — re-run update-skills.sh to backfill the resume cron"
    fi
  else
    ledger "WARN ensure-pipeline-crons.sh not found — re-run update-skills.sh on this box to restore the resume cron"
  fi
else
  ledger "--no-cron: left the resume cron as-is (NOT re-registered)"
fi

ledger "UNPARK COMPLETE — build is un-parked; the resume cron may now fire again."
echo ""
echo "Done. The build on $(hostname 2>/dev/null || echo box) is un-parked. Ledger: $LEDGER"
exit 0
