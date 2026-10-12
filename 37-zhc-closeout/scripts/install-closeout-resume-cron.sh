#!/usr/bin/env bash
# install-closeout-resume-cron.sh — INSTALL-TIME registrar for the DEDICATED
# closeout-resume cron (Skill 37).
#
# WHY THIS EXISTS (see ZHC-EXPERIENCE-DIAGNOSIS Part 2 BREAK #2/#3):
#   Through v12.14.x the dedicated closeout-resume cron was ONLY ever
#   self-bootstrapped at RUNTIME by run-closeout.sh. But run-closeout.sh itself
#   only runs when the workforce-build-resume cron (install.sh Step 13) execs it.
#   If Step 13 was skipped/aborted (no owner chat, operator-chat target,
#   pre-v10.14.17 box, container recreate that dropped crons), run-closeout.sh
#   never fired → the dedicated closeout cron was never created → the whole
#   closeout experience hung off ONE cron with no independent recovery path.
#
#   This script registers the dedicated closeout-resume cron AT INSTALL TIME,
#   so the closeout trigger is REDUNDANT: closeout fires if ANY of
#   {workforce-build-resume, closeout-resume, watchdog} reaches the box.
#
#   The cron is COMMAND mode (`bash resume-closeout-cron.sh`) — it needs NO
#   Telegram owner target, so it installs even on a box with no resolved owner
#   chat. This is the schema's `closeoutResumeRegisteredAt` writer
#   (build-state-schema.json) that previously had no implementing script.
#
# IDEMPOTENT: skips if a closeout-resume cron already exists. Safe to re-run.
# bash-not-zsh.
#
# EXIT CODES:
#   0  cron present (already, or registered this run), OR honest skip (no CLI /
#      script not found) — install must not abort on this
#   1  registration attempted but failed (caller warns; install continues)
#
# Onboarding repo version markers (kept in sync by scripts/bump-version.sh):
#   INSTALL_CLOSEOUT_RESUME_CRON_VERSION
INSTALL_CLOSEOUT_RESUME_CRON_VERSION="v12.33.0"

set -u

# ---- platform detection (VPS first, then Mac) ----
if [[ -d /data/.openclaw ]]; then
  OC_ROOT="/data/.openclaw"
elif [[ -d "${HOME}/.openclaw" ]]; then
  OC_ROOT="${HOME}/.openclaw"
else
  echo "[install-closeout-resume-cron] no OpenClaw root found — nothing to wire" >&2
  exit 0
fi

# FIX-XC-10a: honor ZHC_STATE_FILE (Skill-23-class state-path split-brain guard).
STATE_FILE="${ZHC_STATE_FILE:-$OC_ROOT/workspace/.workforce-build-state.json}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"

_log() { echo "[install-closeout-resume-cron] $*"; }
_now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null; }

if ! command -v openclaw >/dev/null 2>&1; then
  _log "openclaw CLI not on PATH — skipping closeout-resume cron install (re-run later)."
  exit 0
fi

# D25: closeout already complete, or resume budget already spent -> do not register.
if [[ -f "$STATE_FILE" ]] && command -v jq >/dev/null 2>&1; then
  _cs="$(jq -r '.closeoutStatus // empty' "$STATE_FILE" 2>/dev/null)"
  if [[ "$_cs" == "done" || "$_cs" == "sent" ]]; then
    _log "closeoutStatus=$_cs — closeout-resume cron not needed; skipping."
    exit 0
  fi
fi
_RC_FILE="$(dirname "$STATE_FILE")/.closeout-resume-runs.count"
_rc="$(tr -d '[:space:]' < "$_RC_FILE" 2>/dev/null || true)"
if [[ "$_rc" =~ ^[0-9]+$ ]] && (( _rc > ${ZHC_CLOSEOUT_MAX_CRON_RUNS:-48} )); then
  _log "resume budget exhausted ($_rc runs) — not registering. Reset: rm $_RC_FILE"
  exit 0
fi

# Already present? idempotent no-op. D10: a failed cron list is UNKNOWN, never "absent".
if ! _cron_list="$(openclaw cron list 2>/dev/null)"; then
  _log "openclaw cron list failed (rc!=0) — presence UNKNOWN; not registering (D10)."
  exit 0
fi
if printf '%s' "$_cron_list" | grep -qi "closeout-resume"; then
  _log "closeout-resume cron already installed — skipping (idempotent)."
  exit 0
fi

# Locate resume-closeout-cron.sh: prefer this script's own dir, then canonical
# install locations.
RESUME_CRON_SCRIPT=""
for _cand in \
  "$SCRIPT_DIR/resume-closeout-cron.sh" \
  "$OC_ROOT/skills/37-zhc-closeout/scripts/resume-closeout-cron.sh" \
  "${HOME}/.openclaw/skills/37-zhc-closeout/scripts/resume-closeout-cron.sh" \
  "/data/.openclaw/skills/37-zhc-closeout/scripts/resume-closeout-cron.sh"; do
  if [[ -f "$_cand" ]]; then
    RESUME_CRON_SCRIPT="$_cand"
    break
  fi
done

if [[ -z "$RESUME_CRON_SCRIPT" ]]; then
  _log "resume-closeout-cron.sh not found — closeout-resume cron NOT installed (Skill 37 files missing?)."
  exit 0
fi
chmod +x "$RESUME_CRON_SCRIPT" 2>/dev/null || true

# FIX-XC-08a: the flag is `--cron` (5-field expression) — `--schedule` DOES NOT
# EXIST in the OpenClaw CLI and makes registration fail outright. And on
# CLI 2026.6.8 `cron add --command` DEFAULTS delivery=announce, which would spam
# the client's chat every */15 fire (96/day) — so we pass `--no-deliver` to keep
# this operator-plumbing cron SILENT. `--no-deliver` is feature-detected against
# `cron add --help` and dropped (with a no-flag retry) on CLIs that predate it.
_cron_add_help="$(openclaw cron add --help 2>&1 || true)"
NO_DELIVER_FLAG=()
if printf '%s' "$_cron_add_help" | grep -qE '(^|[[:space:]])--no-deliver([[:space:]]|$)'; then
  NO_DELIVER_FLAG=(--no-deliver)
fi

# Register COMMAND mode (no --channel/--to/--message). No owner chat required.
OUT=$(openclaw cron add \
    --name "closeout-resume" \
    --cron "*/15 * * * *" \
    --command "bash $RESUME_CRON_SCRIPT" \
    "${NO_DELIVER_FLAG[@]}" \
    --json 2>/dev/null) || OUT=""

# If the CLI advertised --no-deliver but still rejected the combined argv,
# retry once WITHOUT it so a flag-shape mismatch never blocks registration.
if [[ -z "$OUT" && ${#NO_DELIVER_FLAG[@]} -gt 0 ]]; then
  OUT=$(openclaw cron add \
    --name "closeout-resume" \
    --cron "*/15 * * * *" \
    --command "bash $RESUME_CRON_SCRIPT" \
    --json 2>/dev/null) || OUT=""
fi

# Verify the job actually landed (assert delivery mode + payload via cron list).
if [[ -n "$OUT" ]] && openclaw cron list 2>/dev/null | grep -qi "closeout-resume"; then
  rm -f "$_RC_FILE"  # D25: fresh registration, fresh run budget
  UUID=$(printf '%s' "$OUT" | jq -r '.uuid // .id // empty' 2>/dev/null || true)
  if [[ -n "$UUID" && "$UUID" != "null" ]] && [[ -f "$STATE_FILE" ]] && command -v jq >/dev/null 2>&1; then
    _TMP=$(mktemp)
    if jq --arg uuid "$UUID" --arg ts "$(_now_iso)" \
        '.closeoutResumeUuid = $uuid | .closeoutResumeRegisteredAt = $ts' \
        "$STATE_FILE" > "$_TMP" 2>/dev/null; then
      mv "$_TMP" "$STATE_FILE"
    else
      rm -f "$_TMP"
    fi
  fi
  _log "closeout-resume cron installed (*/15, command mode, --no-deliver — dedicated REDUNDANT closeout trigger, no owner chat needed)."
  exit 0
fi

_log "closeout-resume cron creation failed (non-fatal)."
_log "  Manual: openclaw cron add --name closeout-resume --cron '*/15 * * * *' --command 'bash $RESUME_CRON_SCRIPT' --no-deliver --json"
exit 1
