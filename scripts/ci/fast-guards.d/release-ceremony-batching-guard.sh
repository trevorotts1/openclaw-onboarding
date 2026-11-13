#!/usr/bin/env bash
# Folded from .github/workflows/release-ceremony-batching-guard.yml (job "No standalone CHANGELOG/version-only PR"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Fetch base branch
echo "--- step: Fetch base branch"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards release-ceremony-batching-guard: step \"Fetch base branch\" failed (exit $fg_rc)"' EXIT
export BASE_REF="${GITHUB_BASE_REF:-}"
git fetch --quiet origin "$BASE_REF"
)
( # step: Verify this PR is not release-ceremony-only
echo "--- step: Verify this PR is not release-ceremony-only"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards release-ceremony-batching-guard: step \"Verify this PR is not release-ceremony-only\" failed (exit $fg_rc)"' EXIT
export BASE_REF="${GITHUB_BASE_REF:-}"
python3 scripts/check-no-standalone-release-pr.py --base "origin/$BASE_REF" --head HEAD
)
