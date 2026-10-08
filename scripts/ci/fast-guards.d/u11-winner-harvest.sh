#!/usr/bin/env bash
# Folded from .github/workflows/u11-winner-harvest.yml (job "Winner-harvest flywheel — idempotent card, card-gated write, client-local, zero cross-client"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: winner_harvest.py compiles
set -e
python3 -m py_compile shared-utils/winner_harvest.py shared-utils/exemplar_injection.py
)
( # step: winner_harvest.py self-test (offline, no network/key, no live board)
set -e
python3 shared-utils/winner_harvest.py
)
( # step: U11 — idempotent card (a), card-gated write (b), client-local not repo tree (c), zero cross-client (d)
set -e
python3 -m unittest shared-utils/test_winner_harvest.py -v
)
