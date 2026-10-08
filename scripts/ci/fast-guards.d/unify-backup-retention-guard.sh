#!/usr/bin/env bash
# Folded from .github/workflows/unify-backup-retention-guard.yml (job ".bak-unify backups are bounded (71,805-file / 8.4 GB fleet furnace)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check
set -e -o pipefail
set -euo pipefail
bash -n install.sh
bash -n update-skills.sh
bash -n tests/unit/unify-backup-retention.test.sh
bash -n tests/unit/unify-backup-global-reclaim.test.sh
python3 -m py_compile 23-ai-workforce-blueprint/scripts/create_role_workspaces.py
python3 -m py_compile tests/unit/unify_backup_retention_py.py
echo "syntax OK"
)
( # step: Bounded .bak-unify retention suite (per-target prune)
set -e -o pipefail
bash tests/unit/unify-backup-retention.test.sh
)
( # step: End-of-roll global .bak-unify reclaim suite (orphans + out-of-tree)
set -e -o pipefail
bash tests/unit/unify-backup-global-reclaim.test.sh
)
