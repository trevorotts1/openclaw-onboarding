#!/usr/bin/env bash
# Folded from .github/workflows/ghl-activation-resilience-guard.yml (job "GHL Layer-2 activation resilience guard (no single-shot regression)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Run activation-resilience guard
echo "--- step: Run activation-resilience guard"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards ghl-activation-resilience-guard: step \"Run activation-resilience guard\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash scripts/guard-ghl-activation-resilience.sh
echo "✓ Skill 06 Layer-2 activation resilience enforced (no single-shot/reload/hasPwd-only/deep-route regression)"
)
( # step: Guard matcher cannot SIGPIPE its producer (code_has here-string lock)
echo "--- step: Guard matcher cannot SIGPIPE its producer (code_has here-string lock)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards ghl-activation-resilience-guard: step \"Guard matcher cannot SIGPIPE its producer (code_has here-string lock)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash -n tests/unit/code-has-no-sigpipe.test.sh
bash tests/unit/code-has-no-sigpipe.test.sh
echo "✓ code_has/code_has_i feed grep from a here-string; no grep -q can SIGPIPE a producer under pipefail"
)
( # step: Run activation-resilience regression tests
echo "--- step: Run activation-resilience regression tests"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards ghl-activation-resilience-guard: step \"Run activation-resilience regression tests\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 -m pip install --quiet --disable-pip-version-check pytest
python3 -m pytest -q 06-ghl-install-pages/tests/test_ghl_activation_resilience.py
)
