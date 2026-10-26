#!/usr/bin/env bash
# One box, one update owner.
# Shared atomic installation lease for every writer that can stop, rewrite or
# migrate the same OpenClaw installation: update-skills.sh, self-update.sh, the
# atomic upgrade wrapper and any agent-pull lane.
#
# Contract (skill: big-fleet-roll SKILL.md §7 "Installation lease"):
#   - the lease is one FILE at a fixed literal path, created atomically;
#   - the holder records roll/run id, pid, process start identity, install path
#     and UTC, so a stale lease can be attributed instead of guessed;
#   - a live holder means WAITING, never a retry loop and never a second writer;
#   - a directory (or any non-regular object) at the lease path is a crashed
#     run: it is removed only after proving no matching owner exists;
#   - release removes the lease only when this process is the recorded owner.
#
# Usage:
#   . box-update-lock.sh
#   box_update_lock_acquire /tmp/openclaw-update.lock "$RUN_ID" "update-skills"
#   trap 'box_update_lock_release' EXIT
#
# Returns 0 when the lease is held by this process, 3 when a live owner holds
# it (caller prints the holder detail and exits), 1 on an unrecoverable error.

BUL_LOCK_PATH=""
BUL_LOCK_FD=""
BUL_OWNER_FILE=""

_bul_start_identity() {
  # Process start identity: distinguishes this pid from a later pid-reused one.
  ps -o lstart= -p "$1" 2>/dev/null | tr -s ' ' | sed 's/^ *//;s/ *$//'
}

_bul_write_owner() {
  # Record who holds the lease. Written by the holder only, after acquisition.
  {
    printf 'pid=%s\n' "$$"
    printf 'start=%s\n' "$(_bul_start_identity $$)"
    printf 'run_id=%s\n' "${1:-}"
    printf 'role=%s\n' "${2:-}"
    printf 'install_path=%s\n' "${3:-}"
    printf 'utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$BUL_OWNER_FILE" 2>/dev/null || true
}

_bul_owner_is_live() {
  # 0 when the recorded owner is still the same process (pid alive AND the
  # start identity matches). A pid-reused lease is not a live owner.
  local pid start now_start
  pid="$(sed -n 's/^pid=//p' "$BUL_OWNER_FILE" 2>/dev/null | head -1)"
  start="$(sed -n 's/^start=//p' "$BUL_OWNER_FILE" 2>/dev/null | head -1)"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  if [ -n "$start" ]; then
    now_start="$(_bul_start_identity "$pid")"
    [ "$now_start" = "$start" ] || return 1
  fi
  return 0
}

_bul_describe_owner() {
  if [ -f "$BUL_OWNER_FILE" ]; then
    tr '\n' ' ' < "$BUL_OWNER_FILE" 2>/dev/null
  else
    echo "owner unknown (legacy lease, no identity record)"
  fi
}

box_update_lock_acquire() {
  BUL_LOCK_PATH="${1:-/tmp/openclaw-update.lock}"
  local run_id="${2:-}" role="${3:-}" install_path="${4:-}" holder
  BUL_OWNER_FILE="${BUL_LOCK_PATH}.owner"

  # A directory (or any non-regular object) at the lease path is a crashed run,
  # not a valid lease. Remove it only after proving no live owner remains.
  if [ -e "$BUL_LOCK_PATH" ] && [ ! -f "$BUL_LOCK_PATH" ]; then
    if _bul_owner_is_live; then
      echo "LOCK HELD: $BUL_LOCK_PATH is a non-file object and its recorded owner is live: $(_bul_describe_owner)" >&2
      return 3
    fi
    echo "  [lock] clearing crashed lease object at $BUL_LOCK_PATH (no live owner: $(_bul_describe_owner))" >&2
    rm -rf "$BUL_LOCK_PATH" 2>/dev/null || {
      echo "FATAL: cannot remove crashed lease object $BUL_LOCK_PATH" >&2
      return 1
    }
  fi

  if command -v flock >/dev/null 2>&1; then
    exec {BUL_LOCK_FD}>"$BUL_LOCK_PATH" || {
      echo "FATAL: cannot open lease file $BUL_LOCK_PATH" >&2
      return 1
    }
    if ! flock -n "$BUL_LOCK_FD"; then
      holder="$(_bul_describe_owner)"
      echo "LOCK HELD: another updater owns $BUL_LOCK_PATH — $holder" >&2
      return 3
    fi
    _bul_write_owner "$run_id" "$role" "$install_path"
    echo "  [lock] acquired $BUL_LOCK_PATH (flock, run ${run_id:-unknown}, role ${role:-unknown})"
    return 0
  fi

  # Portable fallback: atomic O_CREAT|O_EXCL via noclobber.
  if ( set -o noclobber; printf 'lease\n' > "$BUL_LOCK_PATH" ) 2>/dev/null; then
    _bul_write_owner "$run_id" "$role" "$install_path"
    echo "  [lock] acquired $BUL_LOCK_PATH (exclusive create, run ${run_id:-unknown}, role ${role:-unknown})"
    return 0
  fi
  if _bul_owner_is_live; then
    echo "LOCK HELD: another updater owns $BUL_LOCK_PATH — $(_bul_describe_owner)" >&2
    return 3
  fi
  holder="$(_bul_describe_owner)"
  rm -f "$BUL_LOCK_PATH" 2>/dev/null || {
    echo "FATAL: cannot clear stale lease $BUL_LOCK_PATH (holder: $holder)" >&2
    return 1
  }
  if ( set -o noclobber; printf 'lease\n' > "$BUL_LOCK_PATH" ) 2>/dev/null; then
    _bul_write_owner "$run_id" "$role" "$install_path"
    echo "  [lock] cleared stale lease ($holder); acquired $BUL_LOCK_PATH (run ${run_id:-unknown})"
    return 0
  fi
  echo "FATAL: cannot create lease $BUL_LOCK_PATH" >&2
  return 1
}

box_update_lock_release() {
  [ -n "$BUL_LOCK_PATH" ] || return 0
  if [ -n "$BUL_LOCK_FD" ]; then
    flock -u "$BUL_LOCK_FD" 2>/dev/null || true
    exec {BUL_LOCK_FD}>&- 2>/dev/null || true
  fi
  # Remove the lease and its identity record only when this process owns it.
  if [ -f "$BUL_OWNER_FILE" ]; then
    local pid
    pid="$(sed -n 's/^pid=//p' "$BUL_OWNER_FILE" 2>/dev/null | head -1)"
    if [ "$pid" = "$$" ]; then
      rm -f "$BUL_OWNER_FILE" 2>/dev/null || true
      [ -n "$BUL_LOCK_FD" ] || rm -f "$BUL_LOCK_PATH" 2>/dev/null || true
    fi
  elif [ -z "$BUL_LOCK_FD" ]; then
    rm -f "$BUL_LOCK_PATH" 2>/dev/null || true
  fi
  return 0
}
