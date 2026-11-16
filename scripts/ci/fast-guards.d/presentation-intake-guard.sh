#!/usr/bin/env bash
# Folded from .github/workflows/presentation-intake-guard.yml (job "Presentation intake guard"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set +e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
fg_rc=0
if [ "$fg_rc" -eq 0 ]; then
( # step: One actual question per turn (agent, app, signature, legacy-session resume)
echo "--- step: One actual question per turn (agent, app, signature, legacy-session resume)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards presentation-intake-guard: step \"One actual question per turn (agent, app, signature, legacy-session resume)\" failed (exit $fg_rc)"' EXIT
python3 -m pip install pytest
python3 -m pytest -q 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_one_question_intake.py
)
[ $? -eq 0 ] || fg_rc=1
fi
if [ "$fg_rc" -eq 0 ]; then
( # step: Interview-app node suites (worker, PRES-006 contract, PRES-023 authority, PRES-024, branded page session flow)
echo "--- step: Interview-app node suites (worker, PRES-006 contract, PRES-023 authority, PRES-024, branded page session flow)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards presentation-intake-guard: step \"Interview-app node suites (worker, PRES-006 contract, PRES-023 authority, PRES-024, branded page session flow)\" failed (exit $fg_rc)"' EXIT
cd 23-ai-workforce-blueprint/templates/role-library/presentations/intake/interview-app
node --test test/test_worker.mjs test/test_pres006_contract.mjs test/test_pres023_worker_authority.mjs test/pres024_interview_app.test.mjs test/test_branded_page_session_flow.test.mjs
)
[ $? -eq 0 ] || fg_rc=1
fi
if [ "$fg_rc" -eq 0 ]; then
( # step: Deployed-r2 worker suites (PRES-024, PRES-005, canonical completeness)
echo "--- step: Deployed-r2 worker suites (PRES-024, PRES-005, canonical completeness)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards presentation-intake-guard: step \"Deployed-r2 worker suites (PRES-024, PRES-005, canonical completeness)\" failed (exit $fg_rc)"' EXIT
cd 23-ai-workforce-blueprint/templates/role-library/presentations/intake/interview-app/deployed-r2
node --test test/pres024_deployed_r2.test.mjs test/test_pres005_worker.mjs test/test_intake_completeness_canonical.test.mjs
)
[ $? -eq 0 ] || fg_rc=1
fi
if [ "$fg_rc" -eq 0 ]; then
( # step: Interview-app python suites (payload, writer, bridge dispatch, PRES-008, PRES-009, PRES-023)
echo "--- step: Interview-app python suites (payload, writer, bridge dispatch, PRES-008, PRES-009, PRES-023)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards presentation-intake-guard: step \"Interview-app python suites (payload, writer, bridge dispatch, PRES-008, PRES-009, PRES-023)\" failed (exit $fg_rc)"' EXIT
cd 23-ai-workforce-blueprint/templates/role-library/presentations/intake/interview-app
python3 test/test_payload.py
python3 test/test_intake_writer.py
python3 test/test_intake_bridge_dispatch.py
python3 test/test_pres008_durable_states.py
python3 test/test_pres009_bridge_and_migration.py
python3 test/test_pres023_bridge_ack.py
)
[ $? -eq 0 ] || fg_rc=1
fi
if [ "$fg_rc" -eq 0 ]; then
( # step: Interview-app payload builder selftest
echo "--- step: Interview-app payload builder selftest"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards presentation-intake-guard: step \"Interview-app payload builder selftest\" failed (exit $fg_rc)"' EXIT
cd 23-ai-workforce-blueprint/templates/role-library/presentations/intake/interview-app
python3 payload/build_questions_payload.py --selftest
)
[ $? -eq 0 ] || fg_rc=1
fi
if [ "$fg_rc" -eq 0 ]; then
( # step: UI question generation check (page + questions.json + contract stay in sync)
echo "--- step: UI question generation check (page + questions.json + contract stay in sync)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards presentation-intake-guard: step \"UI question generation check (page + questions.json + contract stay in sync)\" failed (exit $fg_rc)"' EXIT
cd 23-ai-workforce-blueprint/templates/role-library/presentations/intake/interview-app
node tools/gen_ui_questions.mjs --check
)
[ $? -eq 0 ] || fg_rc=1
fi
if [ "$fg_rc" -eq 0 ]; then
( # step: Deployed page is the source page (byte-identical landing discipline)
echo "--- step: Deployed page is the source page (byte-identical landing discipline)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards presentation-intake-guard: step \"Deployed page is the source page (byte-identical landing discipline)\" failed (exit $fg_rc)"' EXIT
cd 23-ai-workforce-blueprint/templates/role-library/presentations/intake/interview-app
cmp pages/index.html deployed-r2/public/index.html
)
[ $? -eq 0 ] || fg_rc=1
fi
if [ "$fg_rc" -eq 0 ]; then
( # step: Interview a11y gate (u054, guards the live page)
echo "--- step: Interview a11y gate (u054, guards the live page)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards presentation-intake-guard: step \"Interview a11y gate (u054, guards the live page)\" failed (exit $fg_rc)"' EXIT
bash tests/unit/u054-interview-a11y.test.sh
)
[ $? -eq 0 ] || fg_rc=1
fi
( # step: PRES-006 canonical paths (warn-first, pre-existing mirror drift)
echo "--- step: PRES-006 canonical paths (warn-first, pre-existing mirror drift)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards presentation-intake-guard: step \"PRES-006 canonical paths (warn-first, pre-existing mirror drift)\" failed (exit $fg_rc)"' EXIT
cd 23-ai-workforce-blueprint/templates/role-library/presentations/intake/interview-app
python3 test/test_pres006_canonical_paths.py
)
[ $? -eq 0 ] || echo "::warning::fast-guards presentation-intake-guard: step \"PRES-006 canonical paths (warn-first, pre-existing mirror drift)\" failed but is continue-on-error (warn-first)"
( # step: Intake writer run-mode cap (warn-first, pre-existing cap failure)
echo "--- step: Intake writer run-mode cap (warn-first, pre-existing cap failure)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards presentation-intake-guard: step \"Intake writer run-mode cap (warn-first, pre-existing cap failure)\" failed (exit $fg_rc)"' EXIT
cd 23-ai-workforce-blueprint/templates/role-library/presentations/intake/interview-app
python3 test/test_intake_writer_run_mode.py
)
[ $? -eq 0 ] || echo "::warning::fast-guards presentation-intake-guard: step \"Intake writer run-mode cap (warn-first, pre-existing cap failure)\" failed but is continue-on-error (warn-first)"
exit "$fg_rc"
