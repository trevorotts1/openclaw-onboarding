#!/usr/bin/env bash
# Folded from .github/workflows/binding-pair-guard.yml (job "Prove the guard bites (fail / pass / no-fire) on a scratch repo" + "Check this PR's diff against scripts/binding-pairs.json"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: check-binding-pairs.py --selftest (must exit 0 -- proves FAIL/PASS/no-fire all work)
echo "--- step: check-binding-pairs.py --selftest (must exit 0 -- proves FAIL/PASS/no-fire all work)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards binding-pair-guard: step \"check-binding-pairs.py --selftest (must exit 0 -- proves FAIL/PASS/no-fire all work)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 scripts/check-binding-pairs.py --selftest
)
( # step: Same-commit pairs -- check this PRs base...head diff
echo "--- step: Same-commit pairs -- check this PRs base...head diff"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards binding-pair-guard: step \"Same-commit pairs -- check this PRs base...head diff\" failed (exit $fg_rc)"' EXIT
export BASE_SHA="${FG_BASE_SHA:-}"
export HEAD_SHA="${FG_HEAD_SHA:-}"
set -euo pipefail
python3 scripts/check-binding-pairs.py check --base "$BASE_SHA" --head "$HEAD_SHA"
)
( # step: Landing-order constraints -- check this PRs base...head diff
echo "--- step: Landing-order constraints -- check this PRs base...head diff"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards binding-pair-guard: step \"Landing-order constraints -- check this PRs base...head diff\" failed (exit $fg_rc)"' EXIT
export BASE_SHA="${FG_BASE_SHA:-}"
export HEAD_SHA="${FG_HEAD_SHA:-}"
set -euo pipefail
python3 scripts/check-binding-pairs.py order --base "$BASE_SHA" --head "$HEAD_SHA"
)
