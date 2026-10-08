#!/usr/bin/env bash
# Folded from .github/workflows/fleet-validation-harness-guard.yml (job "Per-box ledger + post-fan-out validation harness"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: Syntax check
set -e
python3 -m py_compile shared-utils/fleet_ledger.py shared-utils/fleet_validation_harness.py
bash -n scripts/fleet-validate.sh
bash -n tests/unit/fleet-validation-harness.test.sh
)
( # step: Ledger + harness unit tests (fail-open hunt)
set -e
python3 tests/unit/fleet-ledger-harness.test.py
)
( # step: ACCEPTANCE — 20-box fan-out, one broken box, must FAIL LOUDLY
set -e
chmod +x tests/unit/fleet-validation-harness.test.sh
bash tests/unit/fleet-validation-harness.test.sh
)
( # step: A no-argument invocation must not look green
set -e
set +e
bash scripts/fleet-validate.sh >/dev/null 2>&1
rc=$?
set -e
if [ "$rc" = "0" ]; then
  echo "::error::fleet-validate.sh exited 0 with no arguments — a no-op must never read as a green wave"
  exit 1
fi
echo "no-arg invocation exits $rc (non-zero) — correct"
)
