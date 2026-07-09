#!/usr/bin/env bash
# ============================================================
# lib-closeout-state.sh — shared, concurrency-safe state writer for Skill 37.
# ------------------------------------------------------------
# SK1-13 FIX (closeout state write-lock race).
#
# WHY THIS EXISTS
#   ~10 Skill-37 closeout scripts each defined their OWN unlocked state_set
#   (jq → tmp → mv). The final mv is atomic, so no single write ever CORRUPTS
#   the state file — but a read-modify-write is NOT atomic across processes:
#
#     1. resume-closeout-cron.sh reads .workforce-build-state.json
#     2. a still-running (nohup'd) run-closeout.sh writes a field
#     3. the cron finishes its jq and mv's — clobbering step 2  ← LOST UPDATE
#
#   macOS ships no flock(1), so we serialize the read-modify-write with a
#   PORTABLE mkdir-based mutex. mkdir is atomic on both macOS (HFS+/APFS) and
#   Linux: exactly one racer creates the dir, everyone else's mkdir fails. That
#   makes it a correct cross-process lock with zero extra dependencies.
#
#   A botched lock is worse than the race it fixes, so the acquire loop can
#   NEVER hang:
#     • STALE-LOCK BREAKER — a lock dir older than ZHC_STATE_LOCK_STALE_SECS
#       (default 120s) is assumed abandoned by a crashed writer and reclaimed.
#     • BOUNDED WAIT — after ZHC_STATE_LOCK_WAIT_SECS (default 30s) of a live
#       but stuck lock, we break it and proceed rather than block forever.
#   The lock is held ONLY for the sub-second jq+mv critical section (not across
#   the whole script), so real contention windows are milliseconds and the
#   breakers effectively never fire in normal operation.
#
# CONTRACT (identical to the unlocked copies this replaces)
#   state_set '<jq filter>'   — apply the filter to $STATE_FILE in place.
#   Returns 0 on success, 1 if jq fails (on-disk file left untouched on failure).
#
# REQUIRED by the sourcing script BEFORE calling state_set:
#   $STATE_FILE   — path to the JSON state file.
# OPTIONAL:
#   $LOG_FILE     — diagnostics are appended here if set (also echoed to stderr).
#
# DESIGN RULES
#   • Pure bash + coreutils (jq/mktemp/mkdir/stat/date) — already mandatory.
#   • Sets NO EXIT trap: callers keep their own traps (run-closeout.sh relies on
#     one). Crash-safety comes from the stale-lock breaker, not a trap.
#   • Never writes to stdout (safe inside $(command substitution) captures);
#     diagnostics go to stderr + $LOG_FILE only, and only on the error paths.
# ============================================================

# _zhc_state_epoch — current unix time in whole seconds (portable).
_zhc_state_epoch() { date -u +%s; }

# _zhc_state_mtime <path> — mtime in epoch seconds. BSD stat, then GNU stat,
# then "now" (a vanished lock reads as age 0 → not stale → retried harmlessly).
_zhc_state_mtime() {
  stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null || _zhc_state_epoch
}

# _zhc_state_note <level> <msg> — best-effort diagnostic; never fails the caller
# and never touches stdout. Fires only on the stale/timeout/jq-failure paths.
_zhc_state_note() {
  local line
  line="$(date -u +%Y-%m-%dT%H:%M:%SZ) [$1] state_set: $2"
  if [ -n "${LOG_FILE:-}" ]; then
    printf '%s\n' "$line" >> "$LOG_FILE" 2>/dev/null || true
  fi
  printf '%s\n' "$line" >&2
}

# state_set '<jq filter>' — concurrency-safe in-place mutation of $STATE_FILE.
state_set() {
  local expr="$1"
  local lockdir="${STATE_FILE}.lock"
  local wait_max="${ZHC_STATE_LOCK_WAIT_SECS:-30}"
  local stale="${ZHC_STATE_LOCK_STALE_SECS:-120}"
  local start now age
  start="$(_zhc_state_epoch)"

  # ---- acquire (bounded + self-healing; guaranteed to terminate) ----
  while ! mkdir "$lockdir" 2>/dev/null; do
    now="$(_zhc_state_epoch)"
    age=$(( now - $(_zhc_state_mtime "$lockdir") ))
    if (( age >= stale )); then
      # Abandoned by a crashed writer — reclaim it, then retry mkdir.
      _zhc_state_note WARN "reclaiming stale lock (${age}s >= ${stale}s): $lockdir"
      rm -rf "$lockdir" 2>/dev/null || true
      continue
    fi
    if (( now - start >= wait_max )); then
      # Live but stuck longer than the budget — break it rather than hang.
      _zhc_state_note WARN "lock wait exceeded ${wait_max}s; breaking lock: $lockdir"
      rm -rf "$lockdir" 2>/dev/null || true
      continue
    fi
    sleep 0.2 2>/dev/null || sleep 1
  done

  # ---- critical section (the only window the lock is held) ----
  local tmp rc=0
  tmp="$(mktemp)"
  if jq "$expr" "$STATE_FILE" > "$tmp" 2>/dev/null; then
    mv "$tmp" "$STATE_FILE"
  else
    rm -f "$tmp"
    rc=1
    _zhc_state_note ERROR "jq failed for expr: $expr"
  fi

  # ---- release ----
  rmdir "$lockdir" 2>/dev/null || rm -rf "$lockdir" 2>/dev/null || true
  return "$rc"
}
