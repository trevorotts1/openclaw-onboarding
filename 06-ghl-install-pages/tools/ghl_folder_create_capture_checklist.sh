#!/usr/bin/env bash
# ghl_folder_create_capture_checklist.sh — drive the live capture that unblocks
# the FOLDER-CREATE capability (ghl.folder.create).
#
# This script does NOT capture anything itself and does NOT fabricate a route or
# a body key. It (1) prints the checklist the authenticated-browser step must
# fill in, and (2) validates a filled capture against the module's own schema —
# the same schema the runtime gate uses, so the checklist can never drift.
#
# The live capture is a NAMED DEPENDENCY: an authenticated browser session plus
# one authorized staging location. Until it lands, every run of this script
# reports PENDING_LIVE_CAPTURE and the capability stays disabled.
#
# Usage:
#   ./ghl_folder_create_capture_checklist.sh checklist
#   ./ghl_folder_create_capture_checklist.sh state   [capture.json] [--reviewed]
#   ./ghl_folder_create_capture_checklist.sh validate capture.json
#
# Exit: 0 ok/enabled-for-review, 3 still pending (not an error), 2 usage,
#       1 invalid capture.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOD="$HERE/ghl_recipe_objects.py"
PY="${PYTHON:-python3}"

if [ ! -f "$MOD" ]; then
  echo "REFUSE: $MOD missing — ghl_recipe_objects.py must ship with this script" >&2
  exit 2
fi

cmd="${1:-}"; shift || true

case "$cmd" in
  checklist)
    exec "$PY" -I "$MOD" --folder-create-checklist
    ;;
  state)
    cap=""
    reviewed=""
    for arg in "$@"; do
      case "$arg" in
        --reviewed) reviewed="--reviewed" ;;
        *) cap="$arg" ;;
      esac
    done
    if [ -n "$cap" ]; then
      exec "$PY" -I "$MOD" --folder-create-state --capture "$cap" $reviewed
    fi
    exec "$PY" -I "$MOD" --folder-create-state $reviewed
    ;;
  validate)
    cap="${1:-}"
    if [ -z "$cap" ]; then
      echo "usage: $0 validate <capture.json>" >&2
      exit 2
    fi
    # Schema validation only — this does NOT approve the capture. A valid
    # capture lands at ENABLED_FOR_REVIEW and stays disabled until a reviewer
    # passes --reviewed (a separate, human step).
    "$PY" -I "$MOD" --folder-create-state --capture "$cap" >/dev/null 2>&1
    rc=$?
    if [ "$rc" -ne 0 ]; then
      echo "capture FAILED validation (see REFUSE line above)" >&2
      exit 1
    fi
    "$PY" -I - "$MOD" "$cap" <<'PYEOF'
import json, subprocess, sys
mod, cap = sys.argv[1], sys.argv[2]
out = subprocess.run([sys.executable, "-I", mod, "--folder-create-state",
                      "--capture", cap], capture_output=True, text=True)
state = json.loads(out.stdout)
if state.get("schema_valid"):
    print("capture is schema-valid: ENABLED_FOR_REVIEW (still disabled until "
          "--reviewed)", file=sys.stderr)
    raise SystemExit(0)
print("capture FAILED validation: " + "; ".join(state.get("schema_problems") or
      []), file=sys.stderr)
raise SystemExit(1)
PYEOF
    ;;
  *)
    echo "usage: $0 {checklist|state [capture.json] [--reviewed]|validate <capture.json>}" >&2
    exit 2
    ;;
esac
