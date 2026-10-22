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
# A capture is BOUND, not merely shaped: the artifact bytes written at capture
# time are hashed from the file, and an independent reviewer signs that hash.
# `bind` builds such a bundle from an artifact file plus the 11 selector
# results, so the capture step cannot hand-tune its own evidence.
#
# Usage:
#   ./ghl_split_variant_capture_checklist.sh checklist
#   ./ghl_split_variant_capture_checklist.sh state   [capture.json]
#   ./ghl_split_variant_capture_checklist.sh validate capture.json
#   ./ghl_split_variant_capture_checklist.sh bind <evidence-dir> <artifact>
#            <selectors.json> --company ID --session ID --revision SHA
#            [--reviewer NAME] [--captured-at ISO]
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
  bind)
    edir="${1:-}"; artifact="${2:-}"; sels="${3:-}"; shift 3 2>/dev/null || true
    company=""; session=""; revision=""; reviewer=""; captured_at=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --company)     company="${2:-}"; shift 2 ;;
        --session)     session="${2:-}"; shift 2 ;;
        --revision)    revision="${2:-}"; shift 2 ;;
        --reviewer)    reviewer="${2:-}"; shift 2 ;;
        --captured-at) captured_at="${2:-}"; shift 2 ;;
        *) echo "unknown bind option: $1" >&2; exit 2 ;;
      esac
    done
    if [ -z "$edir" ] || [ -z "$artifact" ] || [ -z "$sels" ]; then
      echo "usage: $0 bind <evidence-dir> <artifact> <selectors.json> \
--company ID --session ID --revision SHA [--reviewer NAME] [--captured-at ISO]" >&2
      exit 2
    fi
    for missing in "$artifact" "$sels"; do
      if [ ! -f "$missing" ]; then
        echo "REFUSE: $missing does not exist" >&2
        exit 2
      fi
    done
    if [ -z "$company" ] || [ -z "$session" ] || [ -z "$revision" ]; then
      echo "REFUSE: --company, --session and --revision are required; a capture \
with no authorized target, no session or no candidate revision is not bound" >&2
      exit 2
    fi
    "$PY" -I - "$MOD" "$edir" "$artifact" "$sels" \
        "$company" "$session" "$revision" "$reviewer" "$captured_at" <<'PYEOF'
import json, os, sys
mod, edir, artifact, sels = sys.argv[1:5]
company, session, revision, reviewer, captured_at = sys.argv[5:10]
sys.path.insert(0, os.path.dirname(os.path.abspath(mod)))
import ghl_split_variant as sv   # noqa: E402
with open(sels, encoding="utf-8") as fh:
    selectors = json.load(fh)
with open(artifact, "rb") as fh:
    data = fh.read()
out = sv.write_capture_bundle(
    edir, selectors, data,
    company_id=company,
    captured_at=captured_at or sv.datetime.datetime.now(
        sv.datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    session_id=session, candidate_revision=revision,
    reviewer=reviewer, reviewed_at="")
print(json.dumps(out, indent=2))
if not reviewer:
    sys.stderr.write(
        "NO RECEIPT: no --reviewer given, so this capture is UNREVIEWED and "
        "load_capture() will refuse it until an independent reviewer signs "
        "the artifact hash.\n")
raise SystemExit(0 if reviewer else 3)
PYEOF
    exit $?
    ;;
  *)
    sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
