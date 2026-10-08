#!/usr/bin/env bash
# Folded from .github/workflows/backup-prune-after-verify-guard.yml (job "Backups prune only after the replacement verifies (T2-08, T0-24)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check
set -e -o pipefail
set -euo pipefail
bash -n 02-back-yourself-up-protocol/scripts/full-backup.sh
bash -n tests/unit/full-backup-prune-after-verify.test.sh
echo "syntax OK"
)
( # step: Prune-after-verify + captured-copy-status suite
set -e -o pipefail
bash tests/unit/full-backup-prune-after-verify.test.sh
)
