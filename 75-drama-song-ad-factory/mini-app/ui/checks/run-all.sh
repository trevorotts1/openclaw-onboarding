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
ran=0
# ui-contract, a11y-check, qr-roundtrip and download-bytes-check live here.
# service-client-check.mjs (W1-studio-page-U1) and questions-drift.mjs
# (W1-studio-page-U4) are wired in here as their own units' files; each runs the
# moment it exists on this branch, and a check that is not there yet is
# reported as skipped, never as passed.
for check in ui-contract a11y-check qr-roundtrip download-bytes-check \
             service-client-check questions-drift; do
  if [ ! -f "checks/${check}.mjs" ]; then
    echo "==================================================================="
    echo "== checks/${check}.mjs — not present on this branch (owned by another unit): SKIPPED"
    echo
    continue
  fi
  echo "==================================================================="
  echo "== checks/${check}.mjs"
  echo "==================================================================="
  node "checks/${check}.mjs"
  rc=$?
  ran=$((ran + 1))
  echo "-- checks/${check}.mjs exit ${rc}"
  if [ "$rc" -ne 0 ]; then status="$rc"; fi
  echo
done

echo "==================================================================="
if [ "$status" -ne 0 ]; then
  echo "UI check suite FAILED (last non-zero exit ${status})"
  exit 2
fi
echo "UI check suite OK: all ${ran} present checks passed"
exit 0
