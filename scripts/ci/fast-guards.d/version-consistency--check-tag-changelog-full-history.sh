#!/usr/bin/env bash
# Folded from .github/workflows/version-consistency.yml (job "G2-EXT — every annotated tag (all history) must have a CHANGELOG entry or a documented gap"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Verify every annotated tag has a CHANGELOG entry or a documented gap
echo "--- step: Verify every annotated tag has a CHANGELOG entry or a documented gap"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards version-consistency--check-tag-changelog-full-history: step \"Verify every annotated tag has a CHANGELOG entry or a documented gap\" failed (exit $fg_rc)"' EXIT
python3 scripts/check-changelog-full-history.py
)
( # step: Self-test: check-changelog-full-history.py (tests/unit/check-changelog-full-history.test.sh)
echo "--- step: Self-test: check-changelog-full-history.py (tests/unit/check-changelog-full-history.test.sh)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards version-consistency--check-tag-changelog-full-history: step \"Self-test: check-changelog-full-history.py (tests/unit/check-changelog-full-history.test.sh)\" failed (exit $fg_rc)"' EXIT
bash tests/unit/check-changelog-full-history.test.sh
)
