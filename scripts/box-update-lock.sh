#!/usr/bin/env bash
# One box, one update owner.
# Shared atomic installation lease for every writer that can stop, rewrite or
# migrate the same OpenClaw installation: update-skills.sh, self-update.sh, the
# atomic upgrade wrapper (oc-atomic-upgrade.sh), fleet-refresh and any
# agent-pull lane.
#
# This file is SOURCED, never executed. It defines no exit paths of its own.
#
# Contract (skill: big-fleet-roll SKILL.md §7 "Installation lease"):
#   - the lease is ONE regular file at a fixed literal path holding ONE owner
#     record: pid, process start identity, run id, role, install path, UTC;
#   - liveness is decided by THE RECORD ONLY — pid alive AND the process start
#     identity still matches.  Never by the file's age, never by the file's
#     mere existence (mac.MAC-13, consistency.C12, modeB.B12);
#   - a live foreign owner means REFUSE (rc 3).  Waiting, retrying and
#     displacing are the caller's business, never this helper's;
#   - a CHILD of the owning process proceeds WITHOUT re-acquiring, so a
#     launcher that spawns a detached child cannot deadlock against itself
#     (modeB.B7, mac.MAC-3, neverBroken.NB6).  Inheritance is proven by the
#     exported run id / owner pid PLUS a live ancestor, never by trust;
#   - release removes the lease only when this process is the recorded owner;
#   - flock, where present, is a second guard on a FIXED fd number (exec 9>...
#     + flock -n 9).  `exec {VAR}>` needs bash 4.1 and aborts with rc 127 on
#     the macOS /bin/bash 3.2 the fleet actually runs (mac.MAC-8).
#
# Usage:
#   . scripts/box-update-lock.sh
#   box_update_lock_acquire /tmp/openclaw-update.lock "$RUN_ID" "self-update" "$OC_ROOT_DIR"
#   case $? in 0) ;; 3) echo "another writer owns the box"; exit 3 ;; *) exit 1 ;; esac
#   trap 'box_update_lock_release' EXIT
#
# Returns: 0 held (by us or by an ancestor of ours), 3 a live writer owns the
# box, 1 an unrecoverable filesystem error.
#
# Environment read by acquire:
#   BFX_LOCK_RUN_ID / BFX_LOCK_OWNER_PID  exported by the acquirer, read by
#                                         children to prove inheritance
#   BUL_AGENT_PULL_LOCKS                  space-separated; live-pid locks to
#                                         honour (neverBroken.NB9)
#   BUL_MAINTENANCE_LOCKS                 space-separated; age-fresh maintenance
#                                         locks to honour (neverBroken.NB9)
#   BUL_MAINTENANCE_FRESH_MINUTES         default 60
#   BUL_SKIP_FOREIGN_GATE=1               skip the foreign-lock gate (tests only)

BUL_LOCK_PATH=""
BUL_LOCK_FD=""
BUL_LOCK_RUN_ID=""
BUL_LOCK_OWNER_PID=""

# --- record primitives -------------------------------------------------------

_bul_start_identity() {
  # Process start identity.  Distinguishes this pid from a later pid-reuse of
  # the same number.  Empty when the platform's ps cannot report it.
  ps -o lstart= -p "$1" 2>/dev/null | tr -s ' ' | sed 's/^ *//;s/ *$//' || true
}

_bul_record_get() {
  # Read one key out of the lease record.  $1 is a literal key name.
  [ -f "$BUL_LOCK_PATH" ] || return 0
  # awk, not `sed | head`: under `set -o pipefail` a closing head can turn the
  # pipeline into a failure inside a command substitution, which `set -e` then
  # turns into an abort in the caller.
  awk -F= -v k="$1" '$1==k{sub(/^[^=]*=/,""); print; exit}' "$BUL_LOCK_PATH" 2>/dev/null || true
}

_bul_write_owner() {
  # $1 run_id  $2 role  $3 install_path
  # Written by the holder only, after acquisition.  pid goes first so that a
  # truncated record is read as "alive owner, unknown run" rather than silently
  # as a free lease.
  local sid
  sid="$(_bul_start_identity $$)"
  # ponytail: ps without lstart (busybox) degrades to pid-only liveness. Ceiling:
  # a reused pid would look like the owner. Upgrade path: read /proc/<pid>/stat
  # field 22 on Linux when ps cannot report lstart.
  [ -n "$sid" ] || sid="none"
  {
    printf 'pid=%s\n' "$$"
    printf 'start=%s\n' "$sid"
    printf 'run_id=%s\n' "${1-}"
    printf 'role=%s\n' "${2-}"
    printf 'install_path=%s\n' "${3-}"
    printf 'utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >"$BUL_LOCK_PATH" 2>/dev/null || return 1
  return 0
}

_bul_owner_live() {
  # 0 when the recorded owner is still the same process: pid alive AND start
  # identity matches.  A pid-reused record is NOT a live owner.  A record with
  # no start line at all is a partial write, not proof of life.
  local pid start cur
  [ -f "$BUL_LOCK_PATH" ] || return 1
  pid="$(_bul_record_get pid)"
  case "$pid" in ''|*[!0-9]*) return 1 ;; esac
  kill -0 "$pid" 2>/dev/null || return 1
  start="$(_bul_record_get start)"
  [ -n "$start" ] || return 1
  [ "$start" = "none" ] && return 0
  cur="$(_bul_start_identity "$pid")"
  [ -n "$cur" ] || return 1
  [ "$cur" = "$start" ]
}

_bul_describe_owner() {
  if [ -f "$BUL_LOCK_PATH" ] && [ -s "$BUL_LOCK_PATH" ]; then
    tr '\n' ' ' <"$BUL_LOCK_PATH" 2>/dev/null
  else
    printf 'owner unknown (no identity record)'
  fi
}

_bul_is_ancestor_or_self() {
  # 0 when $1 is this process or one of its ancestors.
  local want="$1" cur=$$ n=0
  [ -n "$want" ] || return 1
  while [ -n "$cur" ] && [ "$cur" != "0" ] && [ "$n" -lt 64 ]; do
    [ "$cur" = "$want" ] && return 0
    cur="$(ps -o ppid= -p "$cur" 2>/dev/null | tr -cd '0-9' || true)"
    n=$((n + 1))
  done
  return 1
}

_bul_dir_holder_pid() {
  # Legacy shape: a DIRECTORY at the lease path holding a pid file.  Printed
  # only when that pid is alive.
  local p
  p="$(tr -cd '0-9' <"$1/pid" 2>/dev/null)"
  [ -n "$p" ] || return 1
  kill -0 "$p" 2>/dev/null || return 1
  printf '%s' "$p"
}

_bul_foreign_holder() {
  # neverBroken.NB9: while this helper is the installation lease, a live
  # agent-pull job or a fresh oc-atomic maintenance lock must also refuse.
  # Prints the path (and reason) of the first live foreign writer.
  local p pid
  for p in ${BUL_AGENT_PULL_LOCKS-}; do
    [ -n "$p" ] || continue
    if [ -d "$p" ]; then
      pid="$(_bul_dir_holder_pid "$p")" && { printf '%s (live pid %s)' "$p" "$pid"; return 0; }
    elif [ -f "$p" ]; then
      pid="$(awk -F= '$1=="pid"{print $2; exit}' "$p" 2>/dev/null | tr -cd '0-9' || true)"
      if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        printf '%s (live pid %s)' "$p" "$pid"
        return 0
      fi
    fi
  done
  for p in ${BUL_MAINTENANCE_LOCKS-}; do
    [ -f "$p" ] || continue
    pid="$(awk -F= '$1=="pid"{print $2; exit}' "$p" 2>/dev/null | tr -cd '0-9' || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      printf '%s (live pid %s)' "$p" "$pid"
      return 0
    fi
    if [ -n "$(find "$p" -mmin -"${BUL_MAINTENANCE_FRESH_MINUTES:-60}" -print 2>/dev/null)" ]; then
      printf '%s (modified within %s min)' "$p" "${BUL_MAINTENANCE_FRESH_MINUTES:-60}"
      return 0
    fi
  done
  return 1
}

# --- inheritance -------------------------------------------------------------

_bul_try_inherit() {
  # A child of the owning process proceeds WITHOUT re-acquiring.  This is the
  # whole fix for modeB.B7 / mac.MAC-3 / neverBroken.NB6: the Mac atomic
  # upgrade runs self-update.sh -> detached child -> oc-atomic-upgrade.sh, all
  # inside one run, and the old helper refused its own descendants.
  local run_env pid_env rec_pid rec_run
  run_env="${BFX_LOCK_RUN_ID-}"
  pid_env="${BFX_LOCK_OWNER_PID-}"
  [ -f "$BUL_LOCK_PATH" ] || return 1
  rec_pid="$(_bul_record_get pid)"
  rec_run="$(_bul_record_get run_id)"
  case "$rec_pid" in ''|*[!0-9]*) return 1 ;; esac

  # Same run, proven by the exported identity — never by a guess.
  if [ -n "$run_env" ] && [ "$run_env" = "$rec_run" ]; then
    :
  elif [ -n "$pid_env" ] && [ "$pid_env" = "$rec_pid" ]; then
    :
  else
    return 1
  fi

  if _bul_owner_live; then
    # The owner is still running: only a descendant may ride its lease.
    _bul_is_ancestor_or_self "$rec_pid" || return 1
    BUL_LOCK_RUN_ID="$rec_run"
    BUL_LOCK_OWNER_PID="$rec_pid"
    BFX_LOCK_RUN_ID="$rec_run"
    BFX_LOCK_OWNER_PID="$rec_pid"
    export BFX_LOCK_RUN_ID BFX_LOCK_OWNER_PID
    printf '  [lock] inherited %s from live ancestor pid %s (run %s) — no re-acquire\n' \
      "$BUL_LOCK_PATH" "$rec_pid" "${rec_run:-unknown}" >&2
    return 0
  fi

  # The owner is gone but this is still the same run: adopt the record so the
  # lease does not go dead while we work, and so our own release still works.
  # Adopting a DEAD lease is exactly reclaim, reached without the flock dance.
  if _bul_write_owner "$rec_run" "$(_bul_record_get role)" "$(_bul_record_get install_path)"; then
    BUL_LOCK_RUN_ID="$rec_run"
    BUL_LOCK_OWNER_PID="$$"
    BFX_LOCK_RUN_ID="$rec_run"
    BFX_LOCK_OWNER_PID="$$"
    export BFX_LOCK_RUN_ID BFX_LOCK_OWNER_PID
    printf '  [lock] adopted %s from dead ancestor pid %s (run %s)\n' \
      "$BUL_LOCK_PATH" "$rec_pid" "${rec_run:-unknown}" >&2
    return 0
  fi
  return 1
}

# --- public API --------------------------------------------------------------

box_update_lock_acquire() {
  # $1 lease path  $2 run id  $3 role  $4 install path (optional)
  BUL_LOCK_PATH="${1:-/tmp/openclaw-update.lock}"
  local run_id="${2-}" role="${3-}" install_path="${4-}" holder pid start
  BUL_LOCK_FD=""

  # 0. A descendant of the current owner rides the lease (never re-acquires).
  if _bul_try_inherit; then
    return 0
  fi

  # 1. Already ours (re-entry from our own child that lost the env, or a retry).
  if [ "$(_bul_record_get pid)" = "$$" ] && _bul_owner_live; then
    BUL_LOCK_RUN_ID="${run_id:-$(_bul_record_get run_id)}"
    BUL_LOCK_OWNER_PID="$$"
    BFX_LOCK_RUN_ID="$BUL_LOCK_RUN_ID"
    BFX_LOCK_OWNER_PID="$$"
    export BFX_LOCK_RUN_ID BFX_LOCK_OWNER_PID
    return 0
  fi

  # 2. A non-regular object at the path.  Legacy main uses a DIRECTORY with a
  #    pid file; anything else non-regular is a crashed run.  Either way the
  #    decision is the recorded pid, never the object's age.
  if [ -e "$BUL_LOCK_PATH" ] && [ ! -f "$BUL_LOCK_PATH" ]; then
    if [ -d "$BUL_LOCK_PATH" ]; then
      holder="$(_bul_dir_holder_pid "$BUL_LOCK_PATH")"
      if [ -n "$holder" ]; then
        printf 'LOCK HELD: %s is a directory lease with a LIVE owner pid %s\n' "$BUL_LOCK_PATH" "$holder" >&2
        return 3
      fi
    else
      printf '  [lock] clearing non-regular lease object at %s (no live owner)\n' "$BUL_LOCK_PATH" >&2
    fi
    rm -rf "$BUL_LOCK_PATH" 2>/dev/null || {
      printf 'FATAL: cannot remove non-regular lease object %s\n' "$BUL_LOCK_PATH" >&2
      return 1
    }
  fi

  # 3. Foreign writers outside this helper's record: agent-pull jobs and the
  #    oc-atomic maintenance lock (neverBroken.NB9).
  if [ "${BUL_SKIP_FOREIGN_GATE-}" != "1" ]; then
    if holder="$(_bul_foreign_holder)"; then
      printf 'LOCK HELD: another writer owns this installation — %s\n' "$holder" >&2
      return 3
    fi
  fi

  if command -v flock >/dev/null 2>&1; then
    # Fixed fd 9: `exec {VAR}>` is bash 4.1+ and rc 127 on macOS /bin/bash 3.2.
    # Open read-write WITHOUT truncation, so a foreign record survives to be read.
    exec 9<>"$BUL_LOCK_PATH" || {
      printf 'FATAL: cannot open lease file %s\n' "$BUL_LOCK_PATH" >&2
      return 1
    }
    BUL_LOCK_FD=9
    if ! flock -n 9; then
      holder="$(_bul_describe_owner)"
      _bul_close_fd
      printf 'LOCK HELD: another updater owns %s — %s\n' "$BUL_LOCK_PATH" "$holder" >&2
      return 3
    fi
    # An inline (box-only copy) writer does not hold flock, so the record is
    # the authority too: a live foreign record beats a free flock.
    if _bul_owner_live; then
      holder="$(_bul_describe_owner)"
      _bul_close_fd
      printf 'LOCK HELD: another updater owns %s — %s\n' "$BUL_LOCK_PATH" "$holder" >&2
      return 3
    fi
    _bul_write_owner "$run_id" "$role" "$install_path" || {
      _bul_close_fd
      printf 'FATAL: cannot write lease record %s\n' "$BUL_LOCK_PATH" >&2
      return 1
    }
    # Lost the path under us (a no-flock writer rm -f'd it): our flock guards an
    # unlinked inode and proves nothing.
    if [ ! -f "$BUL_LOCK_PATH" ] || [ "$(_bul_record_get pid)" != "$$" ]; then
      _bul_close_fd
      printf 'LOCK HELD: another updater displaced %s during acquisition — %s\n' \
        "$BUL_LOCK_PATH" "$(_bul_describe_owner)" >&2
      return 3
    fi
    BUL_LOCK_RUN_ID="$run_id"
    BUL_LOCK_OWNER_PID="$$"
    BFX_LOCK_RUN_ID="$BUL_LOCK_RUN_ID"
    BFX_LOCK_OWNER_PID="$$"
    export BFX_LOCK_RUN_ID BFX_LOCK_OWNER_PID
    printf '  [lock] acquired %s (flock fd 9 + record, run %s, role %s, pid %s)\n' \
      "$BUL_LOCK_PATH" "${run_id:-unknown}" "${role:-unknown}" "$$" >&2
    return 0
  fi

  # Portable path (no flock: every Mac): exclusive create via noclobber, then
  # the record.  The record, not the file, is the authority.
  if _bul_owner_live; then
    printf 'LOCK HELD: another updater owns %s — %s\n' "$BUL_LOCK_PATH" "$(_bul_describe_owner)" >&2
    return 3
  fi
  if [ -f "$BUL_LOCK_PATH" ]; then
    holder="$(_bul_describe_owner)"
    rm -f "$BUL_LOCK_PATH" 2>/dev/null || {
      printf 'FATAL: cannot clear dead lease %s (holder: %s)\n' "$BUL_LOCK_PATH" "$holder" >&2
      return 1
    }
  fi
  if (set -o noclobber; : >"$BUL_LOCK_PATH") 2>/dev/null; then
    _bul_write_owner "$run_id" "$role" "$install_path" || {
      printf 'FATAL: cannot write lease record %s\n' "$BUL_LOCK_PATH" >&2
      return 1
    }
    # ponytail: between O_EXCL create and the record write another writer can
    # read an empty file and reclaim. Ceiling: needs a third writer landing in
    # that microsecond. Upgrade path: write a temp record and link() it into place.
    if [ "$(_bul_record_get pid)" != "$$" ]; then
      printf 'LOCK HELD: another updater displaced %s during acquisition — %s\n' \
        "$BUL_LOCK_PATH" "$(_bul_describe_owner)" >&2
      return 3
    fi
    BUL_LOCK_RUN_ID="$run_id"
    BUL_LOCK_OWNER_PID="$$"
    BFX_LOCK_RUN_ID="$BUL_LOCK_RUN_ID"
    BFX_LOCK_OWNER_PID="$$"
    export BFX_LOCK_RUN_ID BFX_LOCK_OWNER_PID
    printf '  [lock] acquired %s (exclusive create + record, run %s, role %s, pid %s)\n' \
      "$BUL_LOCK_PATH" "${run_id:-unknown}" "${role:-unknown}" "$$" >&2
    return 0
  fi
  printf 'LOCK HELD: another updater won the race for %s — %s\n' "$BUL_LOCK_PATH" "$(_bul_describe_owner)" >&2
  return 3
}

_bul_close_fd() {
  [ -n "${BUL_LOCK_FD:-}" ] || return 0
  flock -u "$BUL_LOCK_FD" 2>/dev/null || true
  eval "exec ${BUL_LOCK_FD}>&-" 2>/dev/null || true
  BUL_LOCK_FD=""
  return 0
}

box_update_lock_release() {
  # Delete ONLY when this process is the recorded owner.  A child that
  # inherited an ancestor's lease leaves it alone; the ancestor releases it.
  local pid start cur
  [ -n "${BUL_LOCK_PATH-}" ] || return 0
  if [ -f "$BUL_LOCK_PATH" ]; then
    pid="$(_bul_record_get pid)"
    start="$(_bul_record_get start)"
    if [ "$pid" = "$$" ]; then
      if [ "$start" = "none" ]; then
        rm -f "$BUL_LOCK_PATH" 2>/dev/null || true
      else
        cur="$(_bul_start_identity $$)"
        if [ -n "$cur" ] && [ "$cur" = "$start" ]; then
          rm -f "$BUL_LOCK_PATH" 2>/dev/null || true
        fi
      fi
    fi
  fi
  _bul_close_fd
  return 0
}

box_update_lock_owner_is_live() {
  # Read-only probe for callers that must WAIT rather than acquire (the
  # agent-pull host steps and the watch need this instead of `[ -e lock ]`).
  BUL_LOCK_PATH="${1:-${BUL_LOCK_PATH:-/tmp/openclaw-update.lock}}"
  if [ -d "$BUL_LOCK_PATH" ]; then
    [ -n "$(_bul_dir_holder_pid "$BUL_LOCK_PATH")" ]
    return $?
  fi
  _bul_owner_live
}
