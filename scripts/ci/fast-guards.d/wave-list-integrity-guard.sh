#!/usr/bin/env bash
# Folded from .github/workflows/wave-list-integrity-guard.yml (job "install wave lists reference real skills"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Byte-compile the gate script
set -e
python3 -m py_compile scripts/qc-assert-wave-list-integrity.py
)
( # step: Self-test the gate (must fail on a phantom entry, pass on a clean list)
set -e
python3 scripts/qc-assert-wave-list-integrity.py --self-test
)
( # step: Assert every wave-list entry resolves to a real skill (must pass)
set -e
python3 scripts/qc-assert-wave-list-integrity.py
)
