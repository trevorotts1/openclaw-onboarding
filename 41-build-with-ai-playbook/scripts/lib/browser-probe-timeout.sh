#!/usr/bin/env bash
# browser-probe-timeout.sh -- Skill 41 shared hard-timeout + child-tree-kill helper.
#
# WHY (AUD-19 / FLEET-FIX Area 2 / B.1): 06-verify-agent-browser.sh's CDP probe
# spawned `createBrowser({ headless: true })` via a plain command substitution
# with NO timeout and a trap that deleted only the temp probe script -- a hung
# CDP session (or a Chromium child that never exits) hung the CALLING script
# forever and, if the script itself was killed, left the node process (and any
# Chromium it launched) running as an ORPHAN. This lib is the fix: every
# Skill-41 probe that spawns a browser process DIRECTLY (i.e. is NOT already
# routed through 06-ghl-install-pages/tools/browser_manager.sh's own
# lock+teardown gateway) must launch it through `ab_run_bg` + wait via
# `ab_wait_with_timeout`, and must register `ab_kill_tree "$pid"` on
# INT/TERM/EXIT so a kill of the CALLING script also reaps the whole tree.
#
# Guarantees:
#   1. HARD TIMEOUT -- never waits longer than AB_PROBE_MAX_TIMEOUT_SECS (120s).
#      A caller-supplied timeout greater than the ceiling (or <= 0) is clamped
#      to the ceiling, never silently ignored.
#   2. NODE-PID TRAP -- the caller records the background job's real PID and
#      traps INT/TERM/EXIT to kill it, so a `kill` sent to the wrapping script
#      mid-run still reaps every descendant.
#   3. CHILD-TREE KILL -- `ab_kill_tree` recurses via `pgrep -P` (portable:
#      works against both BSD pgrep [macOS] and GNU pgrep [Linux/VPS]) so a
#      Chromium renderer/GPU sub-tree spawned BY the node CDP host is killed
#      too, not just the immediate node PID.
#
# Sourced by: 41-build-with-ai-playbook/scripts/06-verify-agent-browser.sh
# Unit-tested by: 41-build-with-ai-playbook/scripts/lib/browser-probe-timeout.test.sh
set -uo pipefail

# Hard ceiling -- no caller may wait longer than this, no matter what timeout
# value it passes in. This is the "<=120s" requirement, enforced in code (not
# just documented), so a future caller cannot silently regress past it.
AB_PROBE_MAX_TIMEOUT_SECS="${AB_PROBE_MAX_TIMEOUT_SECS:-120}"

# Set by ab_wait_with_timeout on every call (1 = hit the hard timeout, 0 = the
# process exited on its own before the deadline).
AB_PROBE_TIMED_OUT=0

# ab_kill_tree PID [SIGNAL]
# Recursively signals PID and every descendant process, deepest-first, so a
# Chromium renderer/GPU sub-tree spawned by a Node CDP host never survives a
# kill of just the top PID. Safe to call on an already-dead PID (no-op).
ab_kill_tree() {
  local pid="${1:-}" sig="${2:-TERM}"
  [[ -z "$pid" ]] && return 0
  # pgrep -P <pid> lists direct children; recurse before killing the parent
  # so we never lose track of a child once its parent is gone.
  local children
  children="$(pgrep -P "$pid" 2>/dev/null || true)"
  local c
  for c in $children; do
    ab_kill_tree "$c" "$sig"
  done
  kill -"$sig" "$pid" 2>/dev/null || true
}

# ab_wait_with_timeout PID TIMEOUT_SECS
# Polls PID (already running in the background) up to TIMEOUT_SECS, clamped
# to AB_PROBE_MAX_TIMEOUT_SECS. On timeout: TERMs the whole descendant tree,
# gives it 1s grace, then KILLs any survivor -- so a hung probe can never
# leave an orphan running. Sets AB_PROBE_TIMED_OUT=1 on timeout.
#
# Returns: the process's real exit status if it finished in time, or 124
# (the conventional `timeout(1)` code) if the hard timeout fired.
ab_wait_with_timeout() {
  local pid="$1" timeout_secs="${2:-$AB_PROBE_MAX_TIMEOUT_SECS}" waited=0
  AB_PROBE_TIMED_OUT=0
  if ! [[ "$timeout_secs" =~ ^[0-9]+$ ]] || [[ "$timeout_secs" -le 0 ]] || \
     [[ "$timeout_secs" -gt "$AB_PROBE_MAX_TIMEOUT_SECS" ]]; then
    timeout_secs="$AB_PROBE_MAX_TIMEOUT_SECS"
  fi

  while kill -0 "$pid" 2>/dev/null; do
    if [[ "$waited" -ge "$timeout_secs" ]]; then
      AB_PROBE_TIMED_OUT=1
      ab_kill_tree "$pid" TERM
      sleep 1
      kill -0 "$pid" 2>/dev/null && ab_kill_tree "$pid" KILL
      break
    fi
    sleep 1
    waited=$((waited + 1))
  done

  if [[ "$AB_PROBE_TIMED_OUT" -eq 1 ]]; then
    wait "$pid" 2>/dev/null
    return 124
  fi
  wait "$pid"
}
