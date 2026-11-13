#!/usr/bin/env bash
# Folded from .github/workflows/prebuilt-index-section-tagged-guard.yml (job "Static + manifest + fixture (offline)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
export OPENCLAW_PLATFORM=mac
( # step: Run prebuilt-index-section-tagged tests (layers A/B/C)
echo "--- step: Run prebuilt-index-section-tagged tests (layers A/B/C)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards prebuilt-index-section-tagged-guard--static-manifest-fixture: step \"Run prebuilt-index-section-tagged tests (layers A/B/C)\" failed (exit $fg_rc)"' EXIT
chmod +x tests/unit/prebuilt-index-section-tagged.test.sh
bash tests/unit/prebuilt-index-section-tagged.test.sh
)
