#!/usr/bin/env bash
# Folded from .github/workflows/cc-app-dir-resolution-guard.yml (job "--app-dir/CC_APP_DIR honored; a non-checkout --update-only fails LOUD"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Configure git identity (needed for local test-fixture commits)
set -e
git config --global user.email "ci@example.test"
git config --global user.name "CI"
)
( # step: Syntax-check the installer
set -e -o pipefail
set -euo pipefail
bash -n 32-command-center-setup/scripts/run-full-install.sh
echo "bash -n: PASS"
)
( # step: Run APPDIR-01 regression suite
set -e -o pipefail
set -euo pipefail
bash scripts/test-cc-app-dir-resolution.sh
echo "cc-app-dir-resolution-guard: PASS"
)
