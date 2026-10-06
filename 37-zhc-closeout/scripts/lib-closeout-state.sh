#!/usr/bin/env bash
# Shared OS lock + atomic read/modify/replace; missing helper fails closed.
_closeout_state_lib="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../23-ai-workforce-blueprint/scripts" && pwd)/lib-workforce-state.sh"
source "$_closeout_state_lib" || return 1
state_set() {
  workforce_state_set "$STATE_FILE" "$1"
}

# Durable owner-sends hold (shared-utils/owner_sends_hold.py). Returns 0 = HELD,
# reason in OWNER_SENDS_HOLD_REASON; 1 = clear. Anything but a clean "clear"
# from the helper (python or the helper missing, unreadable state) is HELD.
owner_sends_held() {
  local _h _rc
  _h="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../shared-utils" 2>/dev/null && pwd)/owner_sends_hold.py"
  OWNER_SENDS_HOLD_REASON="$(python3 "$_h" check "$STATE_FILE" 2>&1)"; _rc=$?
  [ "$_rc" -eq 1 ] && return 1
  [ -n "$OWNER_SENDS_HOLD_REASON" ] || OWNER_SENDS_HOLD_REASON="owner_sends_hold.py unavailable (rc $_rc)"
  return 0
}
