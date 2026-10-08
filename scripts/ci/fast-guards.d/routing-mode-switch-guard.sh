#!/usr/bin/env bash
# Folded from .github/workflows/routing-mode-switch-guard.yml (job "switch + tripwire + model mode (real modules, fixture boxes)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Install pytest (runner python lacks it)
set -e
python3 -m pip install --quiet pytest || python3 -m pip install --user --quiet pytest
)
( # step: Syntax gates (both shells)
set -e
set -euo pipefail
bash -n scripts/routing-mode.sh
bash -n scripts/health/routing-check.sh
python3 -m py_compile shared-utils/routing_switch.py shared-utils/model_route.py shared-utils/jev_live.py shared-utils/decision-engine.py
node --check extensions/ceo-routing-doctrine/dist/index.js
)
( # step: Mode-store round trip, tripwire, model pick (shell suite)
set -e
bash tests/unit/routing-mode-switch.test.sh
)
( # step: Bridge seams in-process (pytest companion)
set -e
python3 -m pytest tests/unit/test_rf014_model_mode.py -q
)
( # step: Existing mode/decision suites still green (regression floor)
set -e
python3 -m pytest tests/unit/test_d34_modes_cohort.py \
  tests/unit/test_nojev_fallback.py \
  tests/unit/test_a62_mode_survives_install_update.py \
  tests/unit/test_d34_wiring.py tests/unit/test_direct_first_ladder.py \
  tests/unit/test_rep054_bridge_wire.py \
  tests/unit/test_jev_live_decision.py tests/unit/test_jev_live_chain.py -q
)
( # step: Anti-vacuity — a planted corrupt store must turn status red
set -e
set -euo pipefail
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
printf 'garbage\n' > "$T/decision-engine-mode.conf"
if OC_CONFIG="$T" bash scripts/routing-mode.sh status >/dev/null 2>&1; then
  echo "a corrupt mode store did NOT fail status — the check cannot fire"; exit 1
fi
echo "planted corrupt store correctly rejected (non-zero)"
)
