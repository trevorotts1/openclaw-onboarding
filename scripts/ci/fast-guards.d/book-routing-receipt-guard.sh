#!/usr/bin/env bash
# Folded from .github/workflows/book-routing-receipt-guard.yml (job "Book routing needs a target receipt (52 -> 53), not a directory"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Compile the caller, the target and the suite
set -e
set -euo pipefail
python3 -m py_compile 52-avatar-alchemist/scripts/aa_director.py
python3 -m py_compile 53-book-writer/scripts/bw_intake_accept.py
python3 -m py_compile tests/unit/book-routing-requires-a-receipt.test.py
echo "compile OK"
)
( # step: Skill 53 — intake-accept self-test (accept, reject, wrong version, unreadable)
set -e
python3 53-book-writer/scripts/bw_intake_accept.py --self-test
)
( # step: Skill 52 — the pinned-gate hashes still match the shipped files
set -e
python3 52-avatar-alchemist/scripts/aa_gate_integrity_check.py --check
)
( # step: Routing decision requires the target's receipt (all five outcomes)
set -e
python3 tests/unit/book-routing-requires-a-receipt.test.py
)
( # step: Skill 52 — foreman self-test (dispatch loop unchanged)
set -e
python3 52-avatar-alchemist/scripts/aa_director.py --self-test
)
