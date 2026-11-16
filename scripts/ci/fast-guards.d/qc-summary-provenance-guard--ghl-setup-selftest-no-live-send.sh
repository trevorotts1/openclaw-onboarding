#!/usr/bin/env bash
# Folded from .github/workflows/qc-summary-provenance-guard.yml (job "the GHL setup self-test sends nothing from a client account"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Byte-compile the test
echo "--- step: Byte-compile the test"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards qc-summary-provenance-guard--ghl-setup-selftest-no-live-send: step \"Byte-compile the test\" failed (exit $fg_rc)"' EXIT
python3 -m py_compile tests/unit/ghl-setup-selftest-no-live-send.test.py
)
( # step: Assert the automatic self-test is read-only and the counts agree
echo "--- step: Assert the automatic self-test is read-only and the counts agree"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards qc-summary-provenance-guard--ghl-setup-selftest-no-live-send: step \"Assert the automatic self-test is read-only and the counts agree\" failed (exit $fg_rc)"' EXIT
python3 tests/unit/ghl-setup-selftest-no-live-send.test.py
)
