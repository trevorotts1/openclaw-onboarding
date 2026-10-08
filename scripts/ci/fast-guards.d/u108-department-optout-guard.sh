#!/usr/bin/env bash
# Folded from .github/workflows/u108-department-optout-guard.yml (job "U108 — department opt-out + functionality WARNING (2 hermetic suites)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: Compile department-optout-sync.py
set -e
python3 -m py_compile 23-ai-workforce-blueprint/scripts/department-optout-sync.py
)
( # step: Run the U108 suites (each exit 0 required)
set -e -o pipefail
set -uo pipefail
SCRIPTS="23-ai-workforce-blueprint/scripts"
SUITES=(
  test-department-optout-sync.sh
  test-opt-out-loss-warning.sh
)
rc=0
for s in "${SUITES[@]}"; do
  path="$SCRIPTS/$s"
  echo "======================================================================"
  echo "RUN: $s"
  echo "======================================================================"
  if [ ! -f "$path" ]; then
    echo "FATAL: $path not found" >&2
    rc=1
    continue
  fi
  if bash "$path"; then
    echo "PASS: $s"
  else
    echo "FAIL: $s exited non-zero" >&2
    rc=1
  fi
done
echo "======================================================================"
if [ "$rc" -eq 0 ]; then
  echo "ALL ${#SUITES[@]} U108 DEPARTMENT-OPTOUT SUITES PASSED"
else
  echo "ONE OR MORE U108 DEPARTMENT-OPTOUT SUITES FAILED" >&2
fi
exit "$rc"
)
