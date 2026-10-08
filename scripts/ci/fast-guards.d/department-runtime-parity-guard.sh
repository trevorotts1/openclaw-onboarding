#!/usr/bin/env bash
# Folded from .github/workflows/department-runtime-parity-guard.yml (job "guard-department-runtime-parity.py regression suite (25 hermetic cases)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Run the department-runtime-parity regression suite
set -e -o pipefail
set -euo pipefail
cd 32-command-center-setup/scripts
python3 test_guard_department_runtime_parity.py
echo "department-runtime-parity-guard: PASS — no_specialist_runtime regressions caught fail-closed."
)
( # step: Assert the guard is actually wired into run-full-install.sh (BUILD-08)
set -e -o pipefail
set -euo pipefail
# A regression suite passing for the standalone script is necessary but
# not sufficient — BUILD-08 was the guard shipping UNWIRED from converge.
# Fail loud if a future edit ever detaches the Phase 6e2 hard gate.
if ! grep -q 'guard-department-runtime-parity.py' 32-command-center-setup/scripts/run-full-install.sh; then
  echo "FAIL: guard-department-runtime-parity.py is no longer referenced by run-full-install.sh — the install-blocking gate was removed." >&2
  exit 1
fi
if ! grep -q 'fail_install "phase=6e2' 32-command-center-setup/scripts/run-full-install.sh; then
  echo "FAIL: the department-runtime-parity gate in run-full-install.sh Phase 6e2 no longer fail_install()s on mismatch — regressed to warn-only." >&2
  exit 1
fi
echo "PASS: guard-department-runtime-parity.py remains a hard, install-blocking gate in run-full-install.sh Phase 6e2."
)
