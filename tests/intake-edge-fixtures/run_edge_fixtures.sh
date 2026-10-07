#!/bin/sh
# run_edge_fixtures.sh: drive the intake/preflight edge-fixture suite (W4-02-U1).
#
# Families: other-offer, ambiguous-briefs, injection-battery,
#           three-question-cap, provenance-recording, preflight-edges
#
# Exit 0 = every check, 1 = at least one failed check, 2 = resolve/tooling failure.
#
# Overrides: BOX_SLUG (default "local") -> temp prefix <box>-W4-02-U1-
HERE="$(cd "$(dirname "$0")" && pwd)"
UNIT_ID="W4-02-U1"
BOX_SLUG="${BOX_SLUG:-local}"
LANE="${LANE:-${DTS_BUILD_ROOT}/swarm-plans/lanes/${UNIT_ID}-lane}"
mkdir -p "$LANE" || exit 2
export BOX_SLUG

PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "tooling-failure: python3 not on PATH" >&2
  exit 2
fi
if [ ! -f "$HERE/intake_edge.py" ]; then
  echo "tooling-failure: $HERE/intake_edge.py missing" >&2
  exit 2
fi

LOG="$LANE/${UNIT_ID}-run.log"
"$PY" "$HERE/intake_edge.py" >"$LOG" 2>&1
rc=$?
tail -n 60 "$LOG"

case "$rc" in
  0) echo "run_edge_fixtures.sh: PASS (log $LOG)"; exit 0 ;;
  2) echo "run_edge_fixtures.sh: TOOLING FAILURE (log $LOG)" >&2; exit 2 ;;
  *) echo "run_edge_fixtures.sh: FAILED (log $LOG)" >&2; exit 1 ;;
esac
