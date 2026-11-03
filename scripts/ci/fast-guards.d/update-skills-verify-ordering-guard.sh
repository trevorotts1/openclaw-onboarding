#!/usr/bin/env bash
# Post-copy verify.sh runs AFTER the whole skill copy loop, never inside it
# (skilldrift ordering fix 2026-11-03). Added after the CIO002 fold, so there
# is no old workflow behind it; the filter lives in scripts/ci/fast-guards.json.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Both files still parse
set -e
bash -n update-skills.sh
bash -n tests/unit/update-skills-verify-ordering.test.sh
)
( # step: Verify is deferred until every skill folder is on disk (fails on inline verify)
set -e
bash tests/unit/update-skills-verify-ordering.test.sh
)
