#!/usr/bin/env bash
# Shared OS lock + atomic read/modify/replace; missing helper fails closed.
_closeout_state_lib="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../23-ai-workforce-blueprint/scripts" && pwd)/lib-workforce-state.sh"
source "$_closeout_state_lib" || return 1
state_set() {
  workforce_state_set "$STATE_FILE" "$1"
}
