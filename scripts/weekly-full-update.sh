#!/usr/bin/env bash
# =============================================================================
# weekly-full-update.sh — a box's own weekly update, identical to the operator's roll.
# =============================================================================
# Runs `scripts/fleet-refresh.sh --local --apply` from this box's onboarding
# clone, so the Sunday update does exactly what the operator's fleet roll does:
#   onboarding (update-skills.sh) + 999-setup (only if already installed)
#   + Command Center pull/build/restart (atomic-deploy.sh) + sessions.reset
#   + repair runner (OCT4 #5/#6/#7/#9, then author-missing-sops) + the
#   library-standard health gate (OCT4 #11) — all inside the root updater now
#   (OCT4 #10 one front door) — plus snapshot before / automatic rollback on
#   regression.
#
# Callers (both fetch this file from GitHub main, so every box runs the latest):
#   * the silent Sunday shell cron   (scripts/setup-weekly-update.sh)
#   * the Sunday agent cron, RULE 9 auto-apply and RULE 10 "install all" (cron-prompt.txt)
#
# It runs from the roll's own copy of the onboarding repo (the same one the
# operator's roll uses, <OpenClaw root>/fleet-refresh/onboarding), cloned if
# absent and synced to origin/main first. If no copy can be made (no git / no
# network to GitHub), it falls back to the root update-skills.sh fetched
# straight from main — which now carries the SAME full path itself (OCT4 #10),
# so the fallback is a narrower TRANSPORT (no snapshot/rollback machinery
# around it), never a narrower update.
#
# --onboarding-only: run ONLY the onboarding stage (the rare narrow case);
# passed through to both the fleet-refresh path and the fallback updater.
#
# PRE-FLIGHT (docs/FLEET-ROLL-RUNBOOK.md section 11): before any install step the updater
# checks account standing, provider standing, free storage and memory pressure. An enforced
# failure ends the run with the documented status "paused-preflight" (the updater prints
# "FLEET-PREFLIGHT-PAUSED: <reasons>"; this script's exit code is fleet-refresh.sh's, and the
# roll records outcome SKIPPED). Nothing is changed on a paused box. At most one plain note per
# issue per week goes to the client through their own Telegram agent.
#
# Never restarts the gateway, never sends a chat message. (The pre-flight note above is the one
# deliberate exception, sent by shared-utils/fleet_preflight.py, capped and recorded weekly.)
# Exit: fleet-refresh.sh's exit code (0 ok, 2 rolled back / partial, 3 unknown),
#       75 DEFERRED — another updater legitimately owns this box, nothing was
#       changed (critic.C13). 75 is never reported as success.
# =============================================================================
set -uo pipefail

REPO_URL="${FLEET_ROLL_REPO_URL:-https://github.com/trevorotts1/openclaw-onboarding.git}"
UPDATER_URL="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/update-skills.sh"

# OCT4 issue #10: --onboarding-only passes through to whichever transport runs.
WFU_FLAGS=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --onboarding-only) WFU_FLAGS="--onboarding-only" ;;
    --help|-h)
      echo "Usage: weekly-full-update.sh [--onboarding-only]"
      echo "  (no flag)          The FULL update path (default, same as the operator's roll)"
      echo "  --onboarding-only  ONLY the onboarding stage (skip the shared tail)"
      exit 0 ;;
    *) echo "weekly-full-update.sh: unknown flag: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

# cron runs with PATH=/usr/bin:/bin; openclaw, node, npm and pm2 live elsewhere.
# Without them sessions.reset and atomic-deploy.sh cannot run at all.
for d in "${OPENCLAW_ROOT:-/nonexistent}/npm-global/bin" /data/.openclaw/npm-global/bin \
         "$HOME/.openclaw/npm-global/bin" "$HOME/.npm-global/bin" "$HOME/.local/bin" \
         /usr/local/bin /opt/homebrew/bin; do
  [ -d "$d" ] && case ":$PATH:" in *":$d:"*) ;; *) PATH="$d:$PATH" ;; esac
done
export PATH

log() { echo "[weekly-full-update $(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# ── SHARED INSTALLATION LEASE (mac.MAC-1 / consistency.C1) ───────────────────
# The box's own content update is an update WRITER, so it takes the same lease
# as update-skills.sh, self-update.sh, oc-atomic-upgrade.sh and the Saturday
# cron: /tmp/openclaw-update.lock, one record (pid + process start identity +
# run id). Liveness is decided by the RECORD — never by age, never by the
# file's mere existence (mac.MAC-13). A nested run (self-update → this script)
# INHERITS the lease from its ancestor and must not be refused: refusing our
# own children is the defect that closed PR #2612.
#
# A busy box is DEFERRED: exit 75, never "exit 0, nothing changed" (critic.C13).
EX_BUSY=75
WFU_LEASE="${OPENCLAW_UPDATE_LEASE:-/tmp/openclaw-update.lock}"
WFU_STATE=""      # "" | owned | inherited
WFU_IMPL=""

_wfu_start() { ps -o lstart= -p "$1" 2>/dev/null | tr -s ' ' | sed 's/^ *//;s/ *$//' || true; }
_wfu_ppid()  { ps -o ppid= -p "$1" 2>/dev/null | tr -d ' ' || true; }
_wfu_rpid() {
  if [ -d "$WFU_LEASE" ]; then head -1 "$WFU_LEASE/pid" 2>/dev/null || true
  else sed -n 's/^pid=\([0-9][0-9]*\).*/\1/p' "$WFU_LEASE" 2>/dev/null | head -1 || true
  fi
  return 0
}
_wfu_rstart() { sed -n 's/^start=//p' "$WFU_LEASE" 2>/dev/null | head -1 || true; return 0; }

_wfu_owner_live() {
  local _p _s
  if [ -d "$WFU_LEASE" ]; then
    _p="$(_wfu_rpid)"; [ -n "$_p" ] || return 1
    kill -0 "$_p" 2>/dev/null || return 1
    return 0
  fi
  [ -f "$WFU_LEASE" ] || return 1
  _p="$(_wfu_rpid)"; [ -n "$_p" ] || return 1
  kill -0 "$_p" 2>/dev/null || return 1
  _s="$(_wfu_rstart)"
  if [ -n "$_s" ]; then [ "$(_wfu_start "$_p")" = "$_s" ] || return 1; fi
  return 0
}

_wfu_in_owner_tree() {
  [ -d "$WFU_LEASE" ] && return 1
  _wfu_owner_live || return 1
  local _p _cur _n
  _p="$(_wfu_rpid)"; _cur="$$"; _n=0
  while [ -n "$_cur" ] && [ "$_cur" -gt 1 ] 2>/dev/null && [ "$_n" -lt 64 ]; do
    [ "$_cur" = "$_p" ] && return 0
    _cur="$(_wfu_ppid "$_cur")"
    _n=$((_n + 1))
  done
  return 1
}

_wfu_write_own() {
  printf 'pid=%s\nstart=%s\nrun_id=%s\nrole=%s\ninstall_path=%s\nutc=%s\n' \
    "$$" "$(_wfu_start "$$")" "${RUN_ID:-weekly-full-update-$$}" "weekly-full-update" "${B:-}" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$WFU_LEASE" 2>/dev/null
}

_wfu_load_helper() {
  local _h _d
  _d="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
  for _h in "$_d/box-update-lock.sh" \
            "${B:-$HOME/.openclaw}/scripts/box-update-lock.sh" \
            "${B:-$HOME/.openclaw}/fleet-refresh/onboarding/scripts/box-update-lock.sh"; do
    if [ -f "$_h" ]; then
      # shellcheck source=/dev/null
      . "$_h" || continue
      command -v box_update_lock_acquire >/dev/null 2>&1 && return 0
    fi
  done
  return 1
}

# 0 held · 3 a live foreign writer owns it · 1 unrecoverable.
_wfu_lease_acquire() {
  WFU_IMPL="inline"
  if _wfu_load_helper; then WFU_IMPL="helper"; fi

  if [ "$WFU_IMPL" = "helper" ]; then
    box_update_lock_acquire "$WFU_LEASE" "${RUN_ID:-weekly-full-update-$$}" "weekly-full-update" "${B:-}"
    case "$?" in
      0) WFU_STATE="owned"; log "lock: $WFU_LEASE held (shared lease)"; return 0 ;;
      3) return 3 ;;
      *) return 1 ;;
    esac
  fi

  if _wfu_in_owner_tree; then
    WFU_STATE="inherited"
    BFX_LOCK_RUN_ID="$(sed -n 's/^run_id=//p' "$WFU_LEASE" 2>/dev/null | head -1 || true)"
    BFX_LOCK_OWNER_PID="$(_wfu_rpid)"
    export BFX_LOCK_RUN_ID BFX_LOCK_OWNER_PID
    log "lock: inherited $WFU_LEASE from pid $(_wfu_rpid) (nested writer)"
    return 0
  fi

  if [ -e "$WFU_LEASE" ] && [ ! -f "$WFU_LEASE" ]; then
    _wfu_owner_live && return 3
    rm -rf "$WFU_LEASE" 2>/dev/null || return 1
  fi

  if command -v flock >/dev/null 2>&1; then
    exec 9<>"$WFU_LEASE" 2>/dev/null || return 1
    if ! flock -n 9 2>/dev/null; then
      exec 9>&- 2>/dev/null || true
      return 3
    fi
    if _wfu_owner_live; then
      flock -u 9 2>/dev/null || true
      exec 9>&- 2>/dev/null || true
      return 3
    fi
    _wfu_write_own || return 1
    WFU_STATE="owned"
    log "lock: acquired $WFU_LEASE (flock + record, pid $$)"
    return 0
  fi

  _wfu_owner_live && return 3
  if [ -e "$WFU_LEASE" ]; then rm -f "$WFU_LEASE" 2>/dev/null || return 1; fi
  ( set -o noclobber; : > "$WFU_LEASE" ) 2>/dev/null || return 3
  _wfu_write_own || return 1
  WFU_STATE="owned"
  log "lock: acquired $WFU_LEASE (exclusive create, pid $$)"
  return 0
}

_wfu_lease_release() {
  if [ "$WFU_STATE" = "owned" ]; then
    if [ "$WFU_IMPL" = "helper" ]; then
      command -v box_update_lock_release >/dev/null 2>&1 && box_update_lock_release
    elif _wfu_owner_live && [ "$(_wfu_rpid)" = "$$" ]; then
      rm -rf "$WFU_LEASE" 2>/dev/null || true
    fi
  fi
  WFU_STATE=""
  return 0
}

# ── the lease, before anything touches the onboarding copy ───────────────────
B="${OPENCLAW_ROOT:-}"
[ -n "$B" ] || { if [ -d /data/.openclaw ]; then B=/data/.openclaw; else B="$HOME/.openclaw"; fi; }
_wfu_lease_acquire
_WFU_RC=$?
case "$_WFU_RC" in
  0) trap '_wfu_lease_release' EXIT ;;
  3) log "another updater owns this box — the shared installation lease ($WFU_LEASE) is held by pid $(_wfu_rpid). DEFERRED (exit 75): nothing changed"
     exit "$EX_BUSY" ;;
  *) log "REFUSED: could not take the shared installation lease at $WFU_LEASE — nothing changed"
     exit 1 ;;
esac

# Never move the copy under a run that is already in progress (e.g. the
# operator's roll): its lock lives in the OpenClaw root. Legacy marker, still
# honoured for a roll that predates the shared lease; judged by a LIVE pid,
# never by the lock's age. A busy box is DEFERRED (exit 75), never "exit 0".
for L in "${OPENCLAW_ROOT:-/nonexistent}" /data/.openclaw "$HOME/.openclaw"; do
  P="$(cat "$L/.fleet-refresh.lock/pid" 2>/dev/null)" && kill -0 "$P" 2>/dev/null && {
    log "another fleet-refresh (pid $P) is running on this box — DEFERRED (exit 75), nothing changed"; exit "$EX_BUSY"; }
done

# The roll's OWN copy of the onboarding repo, the same one the operator's roll
# keeps (scripts/fleet-roll-copy.sh, same steps): <OpenClaw root>/fleet-refresh/onboarding,
# refreshed to origin/main. The box's other clones are never used or changed.
# ONBOARDING_CLONE, when set, names an explicit clone to run from instead.
R="${ONBOARDING_CLONE:-$B/fleet-refresh/onboarding}"
if [ -z "${ONBOARDING_CLONE:-}" ] && [ -e "$R" ] && [ "$(git -C "$R" remote get-url origin 2>/dev/null)" != "$REPO_URL" ]; then
  rm -rf "$R"
fi
PREV="$(git -C "$R" rev-parse HEAD 2>/dev/null || true)"
if [ -d "$R/.git" ]; then
  # Tool-owned copy, but an old scrub (or anyone) can leave edits in it, and
  # `checkout -B` aborts on them ("local changes ... would be overwritten") so the
  # whole update exited 1. Save them first in a stash that is kept in the copy and
  # never dropped, then hard-sync. If the stash cannot be written, stop: nothing
  # is ever discarded unsaved. Only this copy is touched, never another checkout.
  _n="$(git -C "$R" status --porcelain --untracked-files=all 2>/dev/null | wc -l | tr -d ' ')"
  if [ "${_n:-0}" -gt 0 ]; then
    _s0="$(git -C "$R" rev-parse -q --verify refs/stash 2>/dev/null || true)"
    if ! git -C "$R" -c user.name=fleet-refresh -c user.email=fleet-refresh@localhost \
           stash push -q --include-untracked -m "fleet-refresh auto-stash $(date -u +%Y%m%dT%H%M%SZ)"; then
      log "ERROR: could not save the $_n local change(s) in $R before syncing — nothing was changed on this box"
      exit 1
    fi
    _s1="$(git -C "$R" rev-parse -q --verify refs/stash 2>/dev/null || true)"
    if [ -n "$_s1" ] && [ "$_s1" != "$_s0" ]; then
      log "onboarding copy $R had $_n locally changed file(s): saved as stash ${_s1:0:12} (stash@{0}; kept in the copy, never dropped)"
    else
      log "WARNING: onboarding copy $R reported $_n local change(s) but git stashed nothing (e.g. a nested repository); syncing anyway"
    fi
  fi
  if ! { git -C "$R" fetch -q --depth 1 origin +refs/heads/main:refs/remotes/origin/main \
         && git -C "$R" checkout -q -B main origin/main && git -C "$R" reset -q --hard origin/main; }; then
    log "ERROR: could not sync $R to origin/main — nothing was changed on this box"
    exit 1
  fi
elif ! { mkdir -p "$(dirname "$R")" && git clone -q --depth 1 --single-branch --branch main "$REPO_URL" "$R"; }; then
  # critic.C11 (code side): under self-update the content step is NEVER handed
  # to the bare updater — it has no snapshot and no rollback, so a bad release
  # would be unrecoverable on that box. Exit non-zero and say nothing changed.
  if [ "${SELF_UPDATE_RUN:-0}" = "1" ]; then
    log "REFUSED: no usable onboarding copy (could not create $R) and this run is under self-update — the bare updater has no snapshot/rollback, so it is never used here. Nothing was changed on this box."
    exit 1
  fi
  log "WARNING: no usable onboarding copy (could not create $R) — falling back to the root updater fetched from main (same FULL path per OCT4 #10; narrower transport only, no snapshot/rollback machinery around it)"
  tmp="$(mktemp "${TMPDIR:-/tmp}/openclaw-update-XXXXXX")"
  trap 'rm -f "$tmp"' EXIT
  curl -fsSL --max-time 60 "$UPDATER_URL" -o "$tmp" || { log "ERROR: could not download update-skills.sh"; exit 1; }
  bash "$tmp" $WFU_FLAGS
  exit $?
fi
log "onboarding copy $R: ${PREV:0:12} -> $(git -C "$R" rev-parse --short=12 HEAD)"

export FLEET_PREV_ONBOARDING_SHA="$PREV"   # rollback target for the snapshot
exec bash "$R/scripts/fleet-refresh.sh" --local --apply $WFU_FLAGS
