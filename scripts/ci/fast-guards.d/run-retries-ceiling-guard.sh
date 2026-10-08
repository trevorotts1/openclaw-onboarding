#!/usr/bin/env bash
# Folded from .github/workflows/run-retries-ceiling-guard.yml (job "runRetries wired, set-if-absent, CEILING_NOT_SUPPORTED on old runtimes"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: install.sh must actually wire runRetries (regression guard: was 0 hits)
set -e -o pipefail
set -euo pipefail
hits="$(grep -c 'runRetries' install.sh || true)"
echo "grep -c runRetries install.sh = $hits"
if [ "${hits:-0}" -eq 0 ]; then
  echo "FAIL: install.sh no longer wires agents.defaults.runRetries (AUD-24 regression)."
  exit 1
fi
)
( # step: Shell syntax
set -e -o pipefail
set -euo pipefail
bash -n install.sh
bash -n scripts/wire-run-retries.sh
)
( # step: runRetries ceiling wiring self-test
set -e -o pipefail
set -euo pipefail
bash tests/unit/run-retries-ceiling-wiring.test.sh
echo "run-retries-ceiling-guard: PASS — wired, set-if-absent honoured, CEILING_NOT_SUPPORTED reported, strict/refine hazards guarded."
)
