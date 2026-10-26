#!/usr/bin/env bash
# One box, one update owner.
# Shared atomic installation lease for every writer that can stop, rewrite or
# migrate the same OpenClaw installation: update-skills.sh, self-update.sh, the
# atomic upgrade wrapper and any agent-pull lane.
#
# Contract (skill: big-fleet-roll SKILL.md §7 "Installation lease"):
#   - the lease is one FILE at a fixed literal path holding ONE owner record;
#   - the holder records pid, process start identity, run id, role, install path
#     and UTC, so a stale lease can be attributed instead of guessed;
#   - liveness is decided by the RECORD (pid alive AND start identity matches),
#     never by the file's mere existence, and never by the companion file;
#   - a live holder means WAITING, never a retry loop and never a second writer;
#   - a directory (or any non-regular object) at the lease path is a crashed
#     run: it is removed only after proving no matching owner exists;
#   - release removes the lease only when this process is the recorded owner.
#
# Every writer uses the SAME record shape, so a helper-present writer and a
# box-only-copy inline writer see each other. flock (when present) is an extra
# guard, never the authority: the record is re-read under the lock.
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

_bul_start_identity() {
  # Process start identity: distinguishes this pid from a later pid-reused one.
  ps -o lstart= -p "$1" 2>/dev/null | tr -s ' ' | sed 's/^ *//;s/ *$//'
}

_bul_write_owner() {
  # Record who holds the lease. Written by the holder only, after acquisition.
  # ponytail: truncate+write is not one syscall, so a contender reading in that
  # microsecond sees no owner and may reclaim. Real fix if it ever bites: write
  # the record to a temp file and rename under the same flock. Not worth the
  # extra inode today — the window needs a third updater landing exactly there.
  {
    printf 'pid=%s\n' "$$"
    printf 'start=%s\n' "$(_bul_start_identity $$)"
    printf 'run_id=%s\n' "${1:-}"
    printf 'role=%s\n' "${2:-}"
    printf 'install_path=%s\n' "${3:-}"
    printf 'utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$BUL_LOCK_PATH" 2>/dev/null || true
}

_bul_owner_is_live() {
  # 0 when the recorded owner is still the same process (pid alive AND the
  # start identity matches). A pid-reused record is not a live owner. Reads the
  # lease file itself so helper and inline writers agree on one representation.
  local pid start now_start
  [ -f "$BUL_LOCK_PATH" ] || return 1
  pid="$(sed -n 's/^pid=\([0-9]*\).*/\1/p' "$BUL_LOCK_PATH" 2>/dev/null | head -1)"
  start="$(sed -n 's/^start=//p' "$BUL_LOCK_PATH" 2>/dev/null | head -1)"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  if [ -n "$start" ]; then
    now_start="$(_bul_start_identity "$pid")"
    [ "$now_start" = "$start" ] || return 1
  fi
  return 0
}

_bul_describe_owner() {
  if [ -f "$BUL_LOCK_PATH" ] && [ -s "$BUL_LOCK_PATH" ]; then
    tr '\n' ' ' < "$BUL_LOCK_PATH" 2>/dev/null
  else
    echo "owner unknown (no identity record)"
  fi
}

box_update_lock_acquire() {
  BUL_LOCK_PATH="${1:-/tmp/openclaw-update.lock}"
  local run_id="${2:-}" role="${3:-}" install_path="${4:-}" holder
  BUL_LOCK_FD=""

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
    # Never truncate a foreign record before checking it: open read-write
    # without truncation, take the lock, then judge the record we actually see.
    exec {BUL_LOCK_FD}<>"$BUL_LOCK_PATH" || {
      echo "FATAL: cannot open lease file $BUL_LOCK_PATH" >&2
      BUL_LOCK_FD=""
      return 1
    }
    if ! flock -n "$BUL_LOCK_FD"; then
      holder="$(_bul_describe_owner)"
      flock -u "$BUL_LOCK_FD" 2>/dev/null || true
      exec {BUL_LOCK_FD}>&- 2>/dev/null || true
      BUL_LOCK_FD=""
      echo "LOCK HELD: another updater owns $BUL_LOCK_PATH — $holder" >&2
      return 3
    fi
    # An inline (box-only copy) writer does not hold flock, so the record is
    # the authority too: a live foreign record wins over a free flock.
    if _bul_owner_is_live; then
      holder="$(_bul_describe_owner)"
      flock -u "$BUL_LOCK_FD" 2>/dev/null || true
      exec {BUL_LOCK_FD}>&- 2>/dev/null || true
      BUL_LOCK_FD=""
      echo "LOCK HELD: another updater owns $BUL_LOCK_PATH — $holder" >&2
      return 3
    fi
    _bul_write_owner "$run_id" "$role" "$install_path"
    echo "  [lock] acquired $BUL_LOCK_PATH (flock + record, run ${run_id:-unknown}, role ${role:-unknown})"
    return 0
  fi

  # Portable fallback (no flock): atomic O_CREAT|O_EXCL via noclobber, with the
  # same record shape written by every inline writer.
  if _bul_owner_is_live; then
    echo "LOCK HELD: another updater owns $BUL_LOCK_PATH — $(_bul_describe_owner)" >&2
    return 3
  fi
  if [ -e "$BUL_LOCK_PATH" ]; then
    holder="$(_bul_describe_owner)"
    rm -f "$BUL_LOCK_PATH" 2>/dev/null || {
      echo "FATAL: cannot clear stale lease $BUL_LOCK_PATH (holder: $holder)" >&2
      return 1
    }
  fi
  if ( set -o noclobber; : > "$BUL_LOCK_PATH" ) 2>/dev/null; then
    _bul_write_owner "$run_id" "$role" "$install_path"
    echo "  [lock] acquired $BUL_LOCK_PATH (exclusive create, run ${run_id:-unknown}, role ${role:-unknown})"
    return 0
  fi
  echo "LOCK HELD: another updater won the race for $BUL_LOCK_PATH — $(_bul_describe_owner)" >&2
  return 3
}

box_update_lock_release() {
  [ -n "$BUL_LOCK_PATH" ] || return 0
  # Remove the lease only when this process is the recorded owner.
  if _bul_owner_is_live; then
    local pid
    pid="$(sed -n 's/^pid=\([0-9]*\).*/\1/p' "$BUL_LOCK_PATH" 2>/dev/null | head -1)"
    [ "$pid" = "$$" ] && rm -f "$BUL_LOCK_PATH" 2>/dev/null || true
  fi
  if [ -n "$BUL_LOCK_FD" ]; then
    flock -u "$BUL_LOCK_FD" 2>/dev/null || true
    exec {BUL_LOCK_FD}>&- 2>/dev/null || true
    BUL_LOCK_FD=""
  fi
  return 0
}
