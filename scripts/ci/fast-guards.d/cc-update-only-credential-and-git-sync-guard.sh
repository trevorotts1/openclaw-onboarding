#!/usr/bin/env bash
# Folded from .github/workflows/cc-update-only-credential-and-git-sync-guard.yml (job "--update-only never mutates secrets/.env; detached-HEAD CC checkout still syncs"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Configure git identity (needed for local test-fixture commits)
set -e
git config --global user.email "ci@example.test"
git config --global user.name "CI"
)
( # step: Run D6+D7 regression test suite
set -e -o pipefail
set -euo pipefail
bash scripts/test-cc-update-only-credential-and-git-sync.sh
echo "cc-update-only-credential-and-git-sync-guard: PASS"
)
