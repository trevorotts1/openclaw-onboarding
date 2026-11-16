#!/usr/bin/env bash
# Folded from .github/workflows/gate-added-paths-guard.yml (job "Prove the guard discriminates before trusting it" + "Judge this PR's added lines"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Control suite (asserts an exact exit code per case)
echo "--- step: Control suite (asserts an exact exit code per case)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards gate-added-paths-guard: step \"Control suite (asserts an exact exit code per case)\" failed (exit $fg_rc)"' EXIT
set -uo pipefail
bash tests/unit/gate-added-paths-guard.test.sh
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "::error::control suite failed (rc=$rc) — the guard is not trustworthy yet"
  exit 1
fi
echo "control suite PASSED (rc=0)"
)
( # step: Run the guard against the PR base...head diff
echo "--- step: Run the guard against the PR base...head diff"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards gate-added-paths-guard: step \"Run the guard against the PR base...head diff\" failed (exit $fg_rc)"' EXIT
export BASE_REF="${GITHUB_BASE_REF:-}"
export PR_HEAD="${FG_HEAD_SHA:-${GITHUB_SHA:-}}"
set -uo pipefail
case "$BASE_REF" in
  *[!A-Za-z0-9._/-]*|'')
    echo "::error::base ref is not a safe branch name — refusing to build a ref from it"
    exit 1
    ;;
esac
BASE="origin/${BASE_REF}"
echo "base=$BASE head=$PR_HEAD"
bash tools/gate-added-paths.sh . "$BASE" "$PR_HEAD"
rc=$?
echo "guard rc=$rc"
case "$rc" in
  0)
    echo "PASS: no banned absolute path added by this PR"
    exit 0
    ;;
  1)
    echo "::error::this PR ADDS a banned host-specific absolute path — see hits above"
    exit 1
    ;;
  2)
    echo "::error::guard could not run (exit 2, INSTRUMENT_ERROR) — failing closed rather than reporting clean"
    exit 1
    ;;
  *)
    echo "::error::guard exited unexpectedly ($rc) — failing closed"
    exit 1
    ;;
esac
)
