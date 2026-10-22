#!/usr/bin/env bash
# ghl_split_variant_capture_checklist.sh — drive the live capture that unblocks
# the native split-test VARIANT capability (ghl.native_split_test.variant).
#
# This script does NOT capture anything itself and does NOT fabricate a
# selector. It (1) prints the checklist the authenticated-browser step must
# fill in, and (2) validates a filled capture against the module's own schema —
# the same schema the runtime gate uses, so the checklist can never drift.
#
# The live capture is a NAMED DEPENDENCY on the D5 login fix plus an
# authenticated browser. Until that lands, every run of this script reports
# PENDING_LIVE_SELECTOR_CAPTURE and the capability stays disabled.
#
# Usage:
#   ./ghl_split_variant_capture_checklist.sh checklist
#   ./ghl_split_variant_capture_checklist.sh state   [capture.json]
#   ./ghl_split_variant_capture_checklist.sh validate capture.json
#
# Exit: 0 ok/enabled-for-review, 3 still pending (not an error), 2 usage,
#       1 invalid capture.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOD="$HERE/ghl_split_variant.py"
PY="${PYTHON:-python3}"

if [ ! -f "$MOD" ]; then
  echo "REFUSE: $MOD missing — ghl_split_variant.py must ship with this script" >&2
  exit 2
fi

cmd="${1:-}"; shift || true

case "$cmd" in
  checklist)
    exec "$PY" -I "$MOD" --capture-checklist
    ;;
  state)
    cap="${1:-}"
    if [ -n "$cap" ]; then
      "$PY" -I "$MOD" --state --capture "$cap"
      rc=$?
    else
      "$PY" -I "$MOD" --state
      rc=$?
    fi
    [ "$rc" -eq 0 ] || exit "$rc"
    # Is the capability still gated? Report it without pretending it is an error.
    "$PY" -I - "$MOD" "$cap" <<'PYEOF'
import json, subprocess, sys
mod, cap = sys.argv[1], sys.argv[2]
args = [sys.executable, "-I", mod, "--state"]
if cap:
    args += ["--capture", cap]
out = subprocess.run(args, capture_output=True, text=True)
if out.returncode != 0:
    sys.stderr.write(out.stderr)
    raise SystemExit(out.returncode)
state = json.loads(out.stdout)
print(f"\n[gate] state={state['state']} enabled={state['enabled']} "
      f"schema_valid={state.get('schema_valid')}")
if state["state"] != "PENDING_LIVE_SELECTOR_CAPTURE":
    print("[gate] a complete capture is present — a reviewer must still approve "
          "before any write.")
raise SystemExit(0 if state["state"] != "PENDING_LIVE_SELECTOR_CAPTURE" else 3)
PYEOF
    ;;
  validate)
    cap="${1:-}"
    if [ -z "$cap" ]; then
      echo "usage: $0 validate <capture.json>" >&2
      exit 2
    fi
    if [ ! -f "$cap" ]; then
      echo "REFUSE: $cap does not exist" >&2
      exit 2
    fi
    "$PY" -I "$MOD" --state --capture "$cap" >/dev/null
    rc=$?
    if [ "$rc" -ne 0 ]; then
      echo "INVALID: $cap fails the capture schema (see message above)" >&2
      exit 1
    fi
    echo "VALID: $cap passes the capture schema."
    echo "NEXT: a reviewer approves it; enablement is a separate tested change."
    exit 0
    ;;
  *)
    sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
