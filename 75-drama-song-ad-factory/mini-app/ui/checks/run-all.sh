#!/usr/bin/env bash
# =============================================================================
# Drama Song Ad Factory mini-app — U3 version-0 UI check suite
# -----------------------------------------------------------------------------
# mini-app/ui/checks/run-all.sh
#
# One entry point for every check this unit owns. Each check prints its own
# PASS/FAIL lines and its own exit code, which is echoed here so a green run is
# never reported on a check that did not actually run.
#
#   bash checks/run-all.sh
#
# Exit codes: 0 = every check passed, 2 = at least one check failed.
# =============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE/.."

status=0
for check in ui-contract a11y-check qr-roundtrip download-bytes-check; do
  echo "==================================================================="
  echo "== checks/${check}.mjs"
  echo "==================================================================="
  node "checks/${check}.mjs"
  rc=$?
  echo "-- checks/${check}.mjs exit ${rc}"
  if [ "$rc" -ne 0 ]; then status="$rc"; fi
  echo
done

echo "==================================================================="
if [ "$status" -ne 0 ]; then
  echo "U3 UI check suite FAILED (last non-zero exit ${status})"
  exit 2
fi
echo "U3 UI check suite OK: all four checks passed"
exit 0
