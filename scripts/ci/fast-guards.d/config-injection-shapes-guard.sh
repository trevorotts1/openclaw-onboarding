#!/usr/bin/env bash
# Folded from .github/workflows/config-injection-shapes-guard.yml (job "flat active-memory / helpChatId / channels.bindings cannot ship"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Run config-injection shapes self-test (heal + write-sites + static)
echo "--- step: Run config-injection shapes self-test (heal + write-sites + static)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards config-injection-shapes-guard: step \"Run config-injection shapes self-test (heal + write-sites + static)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash scripts/test-config-injection-shapes.sh
bash scripts/test-operator-telegram-same-as-client-bot.sh
bash scripts/test-diagnose-telegram-operator-optional.sh
bash scripts/test-telegram-token-readers-default-account.sh
echo "config-injection-shapes-guard: PASS"
)
