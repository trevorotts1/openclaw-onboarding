#!/usr/bin/env bash
# Folded from .github/workflows/cron-template-delivery-guard.yml (job "Cron template delivery-path guard"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Run the gate directly against the tree
set -e
python3 scripts/check-cron-template-delivery.py --root .
)
( # step: Run cron-template-delivery tests (incl. mutation proofs)
set -e
chmod +x tests/unit/cron-template-delivery.test.sh
bash tests/unit/cron-template-delivery.test.sh
)
