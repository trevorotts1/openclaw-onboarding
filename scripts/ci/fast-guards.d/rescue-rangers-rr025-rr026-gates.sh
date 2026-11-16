#!/usr/bin/env bash
# Folded from .github/workflows/rescue-rangers-rr025-rr026-gates.yml (job "RR-025/RR-026 gates (envelope identity + supervision)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Shell syntax gates
echo "--- step: Shell syntax gates"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards rescue-rangers-rr025-rr026-gates: step \"Shell syntax gates\" failed (exit $fg_rc)"' EXIT
sh -n 65-rescue-receiver/rescue-poll.sh
bash -n 65-rescue-receiver/rescue-poll.sh
bash -n tests/rescue/RR-025/test_claim_envelope.sh
bash -n tests/rescue/RR-025/lib-envelope-harness.sh
bash -n tests/rescue/RR-026/test_process_supervision.sh
)
( # step: Python syntax gate (stdlib-only supervisor)
echo "--- step: Python syntax gate (stdlib-only supervisor)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards rescue-rangers-rr025-rr026-gates: step \"Python syntax gate (stdlib-only supervisor)\" failed (exit $fg_rc)"' EXIT
python3 -m py_compile shared-utils/rescue-supervise.py
python3 -c "import ast,sys; ast.parse(open('shared-utils/rescue-supervise.py').read())"
)
( # step: RR-025 claim envelope identity (typed members, canonical tuple, ZERO calls on invalid input)
echo "--- step: RR-025 claim envelope identity (typed members, canonical tuple, ZERO calls on invalid input)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards rescue-rangers-rr025-rr026-gates: step \"RR-025 claim envelope identity (typed members, canonical tuple, ZERO calls on invalid input)\" failed (exit $fg_rc)"' EXIT
bash tests/rescue/RR-025/test_claim_envelope.sh
)
( # step: RR-026 process-group supervision, lock fencing, lease budget
echo "--- step: RR-026 process-group supervision, lock fencing, lease budget"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards rescue-rangers-rr025-rr026-gates: step \"RR-026 process-group supervision, lock fencing, lease budget\" failed (exit $fg_rc)"' EXIT
bash tests/rescue/RR-026/test_process_supervision.sh
)
( # step: RR-025/RR-026 must not regress the delivery path they sit inside
echo "--- step: RR-025/RR-026 must not regress the delivery path they sit inside"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards rescue-rangers-rr025-rr026-gates: step \"RR-025/RR-026 must not regress the delivery path they sit inside\" failed (exit $fg_rc)"' EXIT
bash tests/rescue/RR-004/test_receiver_additive_fields.sh
bash tests/unit/rr027-no-credential-in-child-env.test.sh
)
