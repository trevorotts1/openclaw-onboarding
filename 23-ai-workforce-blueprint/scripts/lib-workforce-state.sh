#!/usr/bin/env bash
# One state protocol for every shell read-modify-write. No stale lock breaking.
_WORKFORCE_STATE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKFORCE_PYTHON="${WORKFORCE_PYTHON:-$(command -v python3)}"
export WORKFORCE_PYTHON
export PYTHONPATH="$_WORKFORCE_STATE_DIR${PYTHONPATH:+:$PYTHONPATH}"
"$WORKFORCE_PYTHON" -c 'import sys; assert sys.version_info >= (3,9), "Python 3.9+ required"' || return 1
workforce_state_set() {
  local state_path="$1"; shift
  "$WORKFORCE_PYTHON" "$_WORKFORCE_STATE_DIR/workforce_state.py" jq "$state_path" "$@"
}

workforce_interview_eligible() {
  "$WORKFORCE_PYTHON" "$_WORKFORCE_STATE_DIR/interview_eligibility.py" "$1" "$2" >/dev/null
}
