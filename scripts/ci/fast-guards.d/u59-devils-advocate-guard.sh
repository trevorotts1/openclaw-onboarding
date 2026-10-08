#!/usr/bin/env bash
# Folded from .github/workflows/u59-devils-advocate-guard.yml (job "Devil's Advocate — generator (5 triggers + fallback) + bridge (real loopback HTTP)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: Compile the generator + bridge
set -e
python3 -m py_compile shared-utils/devils-advocate.py
python3 -m py_compile shared-utils/devils-advocate-bridge.py
)
( # step: Bridge self-test (offline, no network, no board required)
set -e
python3 shared-utils/devils-advocate-bridge.py --selftest
)
( # step: U55a — generator proof (5 triggers + honest fallback, evidence byte-check)
set -e
python3 tests/unit/u59-devils-advocate-generator-proof.test.py
)
( # step: U55d — bridge proof (real loopback HTTP, dual-header auth, all FAIL-SOFT branches)
set -e
python3 tests/unit/u59-devils-advocate-bridge.test.py
)
