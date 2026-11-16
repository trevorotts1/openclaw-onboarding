#!/usr/bin/env bash
# Folded from .github/workflows/qc-summary-provenance-guard.yml (job "a QC summary carries only the version it was measured at"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Byte-compile the gate script
echo "--- step: Byte-compile the gate script"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards qc-summary-provenance-guard--qc-summary-provenance-guard: step \"Byte-compile the gate script\" failed (exit $fg_rc)"' EXIT
python3 -m py_compile scripts/qc-assert-qc-summary-provenance.py
)
( # step: Self-test the gate (must fail on a stamped version, pass on a clean artifact)
echo "--- step: Self-test the gate (must fail on a stamped version, pass on a clean artifact)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards qc-summary-provenance-guard--qc-summary-provenance-guard: step \"Self-test the gate (must fail on a stamped version, pass on a clean artifact)\" failed (exit $fg_rc)"' EXIT
python3 scripts/qc-assert-qc-summary-provenance.py --self-test
)
( # step: Assert no QC summary is stamped with an unearned version (must pass)
echo "--- step: Assert no QC summary is stamped with an unearned version (must pass)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards qc-summary-provenance-guard--qc-summary-provenance-guard: step \"Assert no QC summary is stamped with an unearned version (must pass)\" failed (exit $fg_rc)"' EXIT
python3 scripts/qc-assert-qc-summary-provenance.py
)
( # step: Assert a version bump does not rewrite the QC summary (must pass)
echo "--- step: Assert a version bump does not rewrite the QC summary (must pass)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards qc-summary-provenance-guard--qc-summary-provenance-guard: step \"Assert a version bump does not rewrite the QC summary (must pass)\" failed (exit $fg_rc)"' EXIT
bash tests/unit/qc-summary-not-rolled-by-bumper.test.sh
)
