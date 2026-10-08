#!/usr/bin/env bash
# Folded from .github/workflows/status-writer-resolution-defects-guard.yml (job "refresh-build-state-from-index.py measures the tree the client actually has"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check the changed Python and shell
set -e -o pipefail
set -euo pipefail
python3 -m py_compile 23-ai-workforce-blueprint/scripts/refresh-build-state-from-index.py
bash -n tests/unit/status-writer-resolution-defects.test.sh
echo "OK: syntax checks passed"
)
( # step: Materialize the pinned pre-#828 fixture (699fc0be)
set -e -o pipefail
export PRE_FIX_SHA='699fc0bef96c040f7d5d14d16238493abf029042'
set -euo pipefail
git rev-parse --verify "${PRE_FIX_SHA}^{commit}" >/dev/null
REFRESH_PRE="$(mktemp "${RUNNER_TEMP:-/tmp}/refresh-pre-fix.XXXXXX.py")"
git show "${PRE_FIX_SHA}:23-ai-workforce-blueprint/scripts/refresh-build-state-from-index.py" > "$REFRESH_PRE"
[[ -s "$REFRESH_PRE" ]]
echo "REFRESH_PRE=$REFRESH_PRE" >> "$GITHUB_ENV"
echo "OK: pinned pre-fix fixture materialized from ${PRE_FIX_SHA} -> $REFRESH_PRE"
)
( # step: Run the status-writer resolution suite (4 scenarios, 13 assertions)
set -e -o pipefail
set -uo pipefail
chmod +x tests/unit/status-writer-resolution-defects.test.sh
bash tests/unit/status-writer-resolution-defects.test.sh
)
