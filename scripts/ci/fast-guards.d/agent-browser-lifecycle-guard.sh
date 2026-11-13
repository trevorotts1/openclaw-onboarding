#!/usr/bin/env bash
# Folded from .github/workflows/agent-browser-lifecycle-guard.yml (job "agent-browser lifecycle guard (singleton gateway + teardown + reaper)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Install pytest
echo "--- step: Install pytest"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards agent-browser-lifecycle-guard: step \"Install pytest\" failed (exit $fg_rc)"' EXIT
pip install --quiet pytest
)
( # step: Run singleton gateway guard
echo "--- step: Run singleton gateway guard"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards agent-browser-lifecycle-guard: step \"Run singleton gateway guard\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash scripts/guard-agent-browser-managed.sh
echo "✓ every skill directory's agent-browser calls route through the singleton pooled-browser gateway (managed-only, teardown+lock+breaker, no per-run names, sentinel present)"
)
( # step: Guard scan-roots negative fixture (AUD-20 -- guard also scans 41-*/03-*)
echo "--- step: Guard scan-roots negative fixture (AUD-20 -- guard also scans 41-*/03-*)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards agent-browser-lifecycle-guard: step \"Guard scan-roots negative fixture (AUD-20 -- guard also scans 41-*/03-*)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash tests/unit/guard-agent-browser-managed-scan-roots.test.sh
echo "✓ guard-agent-browser-managed.sh bites an unmanaged agent-browser spawn planted in 41-build-with-ai-playbook/ or 03-agent-browser/"
)
( # step: Guard auto-discovery negative fixture (P3-04 c1 -- EVERY skill dir, incl. 44-* and future dirs)
echo "--- step: Guard auto-discovery negative fixture (P3-04 c1 -- EVERY skill dir, incl. 44-* and future dirs)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards agent-browser-lifecycle-guard: step \"Guard auto-discovery negative fixture (P3-04 c1 -- EVERY skill dir, incl. 44-* and future dirs)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash tests/unit/guard-agent-browser-managed-all-skill-dirs.test.sh
echo "✓ guard-agent-browser-managed.sh now AUTO-DISCOVERS every NN-*/ skill directory (44-convert-and-flow-operator/ and any future skill), not a fixed 3-entry list"
)
( # step: Guard backstop-conformance exemption negative fixture (ci-guard-red fix -- exact-path only, never directory-wide)
echo "--- step: Guard backstop-conformance exemption negative fixture (ci-guard-red fix -- exact-path only, never directory-wide)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards agent-browser-lifecycle-guard: step \"Guard backstop-conformance exemption negative fixture (ci-guard-red fix -- exact-path only, never directory-wide)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash tests/unit/guard-agent-browser-managed-backstop-conformance-exempt.test.sh
echo "✓ guard-agent-browser-managed.sh exempts ONLY 03-agent-browser/scripts/lib-backstop-conformance.sh (Skill 3's own raw-CLI conformance battery) by exact path, and still bites any other unmanaged spawn under 03-agent-browser/"
)
( # step: Run static singleton + iframe-taxonomy tests
echo "--- step: Run static singleton + iframe-taxonomy tests"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards agent-browser-lifecycle-guard: step \"Run static singleton + iframe-taxonomy tests\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
pytest 06-ghl-install-pages/tests/test_browser_manager_singleton.py \
       06-ghl-install-pages/tests/test_iframe_failure_taxonomy.py -q
)
( # step: Reaper behaviour against a faked ps (profile scope, macOS ages, orphaned daemons, kill order)
echo "--- step: Reaper behaviour against a faked ps (profile scope, macOS ages, orphaned daemons, kill order)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards agent-browser-lifecycle-guard: step \"Reaper behaviour against a faked ps (profile scope, macOS ages, orphaned daemons, kill order)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 tests/unit/agent-browser-reaper.test.py
)
