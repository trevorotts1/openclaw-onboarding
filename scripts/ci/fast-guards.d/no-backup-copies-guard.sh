#!/usr/bin/env bash
# Folded from .github/workflows/no-backup-copies-guard.yml (job "No full copies of skills/onboarding in backups; rollback still works"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check
set -e -o pipefail
set -euo pipefail
bash -n scripts/skills-rollback.sh
bash -n 02-back-yourself-up-protocol/scripts/full-backup.sh
bash -n tests/unit/skills-rollback-no-copy.test.sh
bash -n tests/unit/full-backup-no-repo-skills-copy.test.sh
echo "syntax OK"
)
( # step: Updater records a no-copy rollback that restores
set -e -o pipefail
bash tests/unit/skills-rollback-no-copy.test.sh
)
( # step: Full backup copies only the box's own skills
set -e -o pipefail
bash tests/unit/full-backup-no-repo-skills-copy.test.sh
)
