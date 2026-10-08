#!/usr/bin/env bash
# Folded from .github/workflows/u10-anti-copy-guard.yml (job "Anti-copy guard — ceiling locked, copy-through hard-fails, fresh passes, key-free"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: anti_copy_guard.py compiles
set -e
python3 -m py_compile shared-utils/anti_copy_guard.py shared-utils/fab_qc.py
)
( # step: anti_copy_guard.py self-test (offline, no network/key)
set -e
python3 shared-utils/anti_copy_guard.py
)
( # step: U10 — copy-through hard-fails, fresh passes, ceiling locked, key-free, wired into fab_qc
set -e
python3 tests/unit/u10-anti-copy-guard.test.py
)
( # step: fab_qc.py regression suite unaffected (byte-identical when no exemplar_packs)
set -e
python3 tests/unit/fab-qc.test.py
)
( # step: FAB-QC gate guard — anti-copy guard wiring asserted alongside every other invariant
set -e
bash scripts/guard-fab-qc-gate.sh
)
