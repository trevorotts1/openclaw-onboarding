#!/usr/bin/env bash
# Folded from .github/workflows/rescue-rangers-rr029-notifications.yml (job "rr029-notification-contract"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Receiver and worker syntax
echo "--- step: Receiver and worker syntax"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards rescue-rangers-rr029-notifications: step \"Receiver and worker syntax\" failed (exit $fg_rc)"' EXIT
bash -n 65-rescue-receiver/rescue-poll.sh
python3 -m py_compile 65-rescue-receiver/rescue-notification.py
)
( # step: Durable notification and result contracts
echo "--- step: Durable notification and result contracts"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards rescue-rangers-rr029-notifications: step \"Durable notification and result contracts\" failed (exit $fg_rc)"' EXIT
python3 tests/rescue/RR-029/test_notification_worker.py
python3 tests/rescue/RR-029/test_notification_poll.py
python3 tests/rescue/RR-029/test_notification_recovery.py
python3 tests/rescue/RR-029/test_acceptance_probe.py
bash tests/rescue/RR-029/test_structured_result.sh
)
