#!/usr/bin/env bash
# Folded from .github/workflows/full-funnel-pipeline.yml (job "funnel pipeline pytest (T-1..T-9 + T-N1..T-N6 + T-PRE-1/4 + T-N5 + graduation)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
export PYTHONUNBUFFERED=1
( # step: Install pytest
echo "--- step: Install pytest"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards full-funnel-pipeline--funnel-pipeline-pytest: step \"Install pytest\" failed (exit $fg_rc)"' EXIT
pip install pytest
)
( # step: Assert documented test count (docs cannot drift)
echo "--- step: Assert documented test count (docs cannot drift)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards full-funnel-pipeline--funnel-pipeline-pytest: step \"Assert documented test count (docs cannot drift)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
# The README + CHANGELOG document "47 tests collected". Assert it here so
# the documented number is the REAL collected number on every PR.
n=$(python3 -m pytest 23-ai-workforce-blueprint/full-funnel-pipeline/tests/ \
      --collect-only -q 2>/dev/null | grep -c '::' || true)
echo "collected ${n} tests"
test "${n}" -eq 47 || { echo "::error::expected 47 collected tests, got ${n}"; exit 1; }
)
( # step: Run full-funnel pipeline tests
echo "--- step: Run full-funnel pipeline tests"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards full-funnel-pipeline--funnel-pipeline-pytest: step \"Run full-funnel pipeline tests\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
# T-PRE-1 SKIPs honestly on a keyless CI box (no embedding provider); all
# other tests run offline. -rs surfaces the skip reason in the CI log.
python3 -m pytest 23-ai-workforce-blueprint/full-funnel-pipeline/tests/ -q -rs
echo "✓ P0→P5 integration + negatives + T-PRE-1/4 + T-N5 fail-closed + graduation green"
)
