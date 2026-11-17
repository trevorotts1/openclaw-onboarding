#!/usr/bin/env bash
# Folded from .github/workflows/vercel-github-archive-guard.yml (job "GitHub archival (non-blocking) + reconciliation sweep"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Python syntax — new/changed modules
echo "--- step: Python syntax — new/changed modules"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards vercel-github-archive-guard: step \"Python syntax — new/changed modules\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
for f in 06-ghl-install-pages/tools/ghl_github_archive.py \
         06-ghl-install-pages/tools/ghl_github_reconcile.py \
         06-ghl-install-pages/tools/ghl_archive_receipt_gate.py \
         06-ghl-install-pages/tools/ghl_vercel.py; do
  python3 -c "import ast; ast.parse(open('$f').read())" || { echo "✗ syntax: $f"; exit 1; }
done
echo "✓ Python syntax OK"
)
( # step: ghl_github_archive self-test (no network, no real subprocess)
echo "--- step: ghl_github_archive self-test (no network, no real subprocess)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards vercel-github-archive-guard: step \"ghl_github_archive self-test (no network, no real subprocess)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 06-ghl-install-pages/tools/ghl_github_archive.py --selftest
)
( # step: ghl_archive_receipt_gate self-test (U24/B-U10, no network)
echo "--- step: ghl_archive_receipt_gate self-test (U24/B-U10, no network)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards vercel-github-archive-guard: step \"ghl_archive_receipt_gate self-test (U24/B-U10, no network)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 06-ghl-install-pages/tools/ghl_archive_receipt_gate.py --selftest
)
( # step: ghl_receipts self-test (F6 store this feature reuses)
echo "--- step: ghl_receipts self-test (F6 store this feature reuses)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards vercel-github-archive-guard: step \"ghl_receipts self-test (F6 store this feature reuses)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 06-ghl-install-pages/tools/ghl_receipts.py --selftest
)
( # step: pytest — archive + reconcile + archive-receipt gate + run_pipeline wiring (mock-only)
echo "--- step: pytest — archive + reconcile + archive-receipt gate + run_pipeline wiring (mock-only)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards vercel-github-archive-guard: step \"pytest — archive + reconcile + archive-receipt gate + run_pipeline wiring (mock-only)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 -m pip install --quiet --disable-pip-version-check pytest
python3 -m pytest -q \
  06-ghl-install-pages/tests/test_ghl_github_archive.py \
  06-ghl-install-pages/tests/test_ghl_github_reconcile.py \
  06-ghl-install-pages/tests/test_ghl_archive_receipt_gate.py \
  06-ghl-install-pages/tests/test_ghl_vercel.py \
  06-ghl-install-pages/tests/test_cc_board_reconcile.py \
  06-ghl-install-pages/tests/test_github_archive_maintenance_schedule.py
)
( # step: run_pipeline is actually wired (evidence_root param + github_archive field)
echo "--- step: run_pipeline is actually wired (evidence_root param + github_archive field)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards vercel-github-archive-guard: step \"run_pipeline is actually wired (evidence_root param + github_archive field)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 -c "
import sys, inspect, dataclasses
sys.path.insert(0, '06-ghl-install-pages/tools')
import ghl_vercel as v
sig = inspect.signature(v.run_pipeline)
assert 'evidence_root' in sig.parameters, 'run_pipeline missing evidence_root param'
fields = [f.name for f in dataclasses.fields(v.VercelEmbedReceipt)]
assert 'github_archive' in fields, 'VercelEmbedReceipt missing github_archive field'
print('✓ run_pipeline wired to non-blocking GitHub archival')
"
)
( # step: sweep_base + archive-receipt gate are actually wired (U24/B-U10)
echo "--- step: sweep_base + archive-receipt gate are actually wired (U24/B-U10)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards vercel-github-archive-guard: step \"sweep_base + archive-receipt gate are actually wired (U24/B-U10)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 -c "
import sys, inspect
sys.path.insert(0, '06-ghl-install-pages/tools')
import ghl_github_reconcile as rec
import ghl_archive_receipt_gate as gate
assert callable(rec.sweep_base), 'ghl_github_reconcile missing sweep_base'
assert callable(rec.verify_repo_byte_match), 'ghl_github_reconcile missing verify_repo_byte_match (B-U10 amended acceptance (b))'
assert 'check' in dir(gate) and callable(gate.check), 'ghl_archive_receipt_gate missing check()'
import ghl_github_archive as gha
assert callable(gha.is_archive_verified), 'ghl_github_archive missing is_archive_verified'
assert callable(gha.token_presence), 'ghl_github_archive missing token_presence'
import os
assert os.path.isfile('06-ghl-install-pages/schedule/skill6-github-archive-reconcile-sweep.cron.json'), 'maintenance-window schedule entry file missing (B-U10 amended acceptance (c))'
assert os.access('06-ghl-install-pages/scripts/install-github-archive-reconcile-cron.sh', os.X_OK), 'schedule-entry installer missing or non-executable'
print('✓ sweep_base / verify_repo_byte_match / archive_receipt_gate.check / is_archive_verified / token_presence / schedule entry all present')
"
bash scripts/guard-fab-qc-gate.sh
)
( # step: qc-built-funnel.sh actually calls the archive-receipt gate (bash syntax + grep-wired)
echo "--- step: qc-built-funnel.sh actually calls the archive-receipt gate (bash syntax + grep-wired)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards vercel-github-archive-guard: step \"qc-built-funnel.sh actually calls the archive-receipt gate (bash syntax + grep-wired)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash -n 06-ghl-install-pages/qc-built-funnel.sh
grep -q 'ghl_archive_receipt_gate.py' 06-ghl-install-pages/qc-built-funnel.sh || { echo "✗ qc-built-funnel.sh no longer calls ghl_archive_receipt_gate.py"; exit 1; }
echo "✓ qc-built-funnel.sh wires the archive-receipt gate"
)
( # step: SKILL.md regression guard — must NOT claim VERCEL_EMBED is NOT GitHub
echo "--- step: SKILL.md regression guard — must NOT claim VERCEL_EMBED is NOT GitHub"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards vercel-github-archive-guard: step \"SKILL.md regression guard — must NOT claim VERCEL_EMBED is NOT GitHub\" failed (exit $fg_rc)"' EXIT
set -uo pipefail
if grep -qi 'IS A DIRECT API UPLOAD — NOT GitHub' 06-ghl-install-pages/SKILL.md; then
  echo "✗ SKILL.md still claims VERCEL_EMBED is NOT GitHub — the doctrine fix regressed"
  exit 1
fi
grep -q 'ghl_github_archive' 06-ghl-install-pages/SKILL.md || { echo "✗ SKILL.md does not mention ghl_github_archive"; exit 1; }
grep -q 'ghl_github_reconcile' 06-ghl-install-pages/SKILL.md || { echo "✗ SKILL.md does not mention ghl_github_reconcile"; exit 1; }
grep -q -- '--sweep-base' 06-ghl-install-pages/SKILL.md || { echo "✗ SKILL.md does not document the --sweep-base maintenance-window mode (U24/B-U10)"; exit 1; }
grep -q 'ghl_archive_receipt_gate' 06-ghl-install-pages/SKILL.md || { echo "✗ SKILL.md does not mention ghl_archive_receipt_gate (U24/B-U10)"; exit 1; }
grep -q 'D6/B-D2 — RATIFIED' 06-ghl-install-pages/SKILL.md || { echo "✗ SKILL.md does not record the D6/B-D2 ratification"; exit 1; }
echo "✓ SKILL.md documents the non-blocking GitHub archive + reconciliation sweep + U24/B-U10 scheduling/gate, and no longer bans it"
)
( # step: Negative test — a re-introduced blocking archive call must be caught by review, not silently pass
echo "--- step: Negative test — a re-introduced blocking archive call must be caught by review, not silently pass"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards vercel-github-archive-guard: step \"Negative test — a re-introduced blocking archive call must be caught by review, not silently pass\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
# Prove the "never blocks/never raises" contract is actually exercised:
# if archive_async raised, test_ghl_vercel.py's
# test_archive_async_exception_never_propagates_out_of_run_pipeline
# would fail. Re-run it in isolation as an explicit named check so a
# future refactor that removes the try/except around archive_async
# fails THIS step with an unambiguous name.
python3 -m pytest -q \
  "06-ghl-install-pages/tests/test_ghl_vercel.py::TestRunPipelineGithubArchival::test_archive_async_exception_never_propagates_out_of_run_pipeline" \
  "06-ghl-install-pages/tests/test_ghl_vercel.py::TestRunPipelineGithubArchival::test_vercel_failure_raises_before_any_archive_attempt"
echo "✓ Non-blocking contract proven: archival failures never propagate; Vercel-gate failures never attempt archival"
)
