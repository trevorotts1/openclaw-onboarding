#!/usr/bin/env bash
# Folded from .github/workflows/hardening-and-fleet-standards-exec-guard.yml (job "structural gates (brew bounds, streamed log, exec.mode translation)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Bounded non-interactive brew + whisper probe + streamed log
echo "--- step: Bounded non-interactive brew + whisper probe + streamed log"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards hardening-and-fleet-standards-exec-guard--structural: step \"Bounded non-interactive brew + whisper probe + streamed log\" failed (exit $fg_rc)"' EXIT
chmod +x tests/unit/hardening-bounded-brew-and-whisper-probe.test.sh
bash tests/unit/hardening-bounded-brew-and-whisper-probe.test.sh
)
( # step: Fleet standards keeps tools.exec.mode (no legacy security/ask rewrite)
echo "--- step: Fleet standards keeps tools.exec.mode (no legacy security/ask rewrite)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards hardening-and-fleet-standards-exec-guard--structural: step \"Fleet standards keeps tools.exec.mode (no legacy security/ask rewrite)\" failed (exit $fg_rc)"' EXIT
chmod +x tests/unit/fleet-standards-legacy-exec-mode.test.sh
bash tests/unit/fleet-standards-legacy-exec-mode.test.sh
)
( # step: Version detector parses line 2; unknown version never writes the poison key
echo "--- step: Version detector parses line 2; unknown version never writes the poison key"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards hardening-and-fleet-standards-exec-guard--structural: step \"Version detector parses line 2; unknown version never writes the poison key\" failed (exit $fg_rc)"' EXIT
# 2026-11-06: a CLI shim that writes a banner to stderr made the old
# line-1-only detector read the wrong schema, write agents.defaults.tools
# on 2026.10.8, and ROLL BACK the entire standards apply. This leg runs
# the real script against that exact CLI shape and asserts the standards
# actually land -- plus that a genuine validator failure still rolls back.
chmod +x tests/unit/fleet-standards-version-detector-rollback.test.sh
bash tests/unit/fleet-standards-version-detector-rollback.test.sh
)
( # step: Model-sovereignty repair never truncates fallback chains
echo "--- step: Model-sovereignty repair never truncates fallback chains"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards hardening-and-fleet-standards-exec-guard--structural: step \"Model-sovereignty repair never truncates fallback chains\" failed (exit $fg_rc)"' EXIT
bash tests/unit/repair-model-sovereignty-no-truncate.test.sh
)
( # step: No rule against Anthropic models (the whole roll keeps an Anthropic fallback/provider/plugin)
echo "--- step: No rule against Anthropic models (the whole roll keeps an Anthropic fallback/provider/plugin)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards hardening-and-fleet-standards-exec-guard--structural: step \"No rule against Anthropic models (the whole roll keeps an Anthropic fallback/provider/plugin)\" failed (exit $fg_rc)"' EXIT
bash tests/unit/no-anthropic-rule.test.sh
)
( # step: Burn guard keeps skill-collection-review crons off (unset/auto -> the value the installed build accepts)
echo "--- step: Burn guard keeps skill-collection-review crons off (unset/auto -> the value the installed build accepts)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards hardening-and-fleet-standards-exec-guard--structural: step \"Burn guard keeps skill-collection-review crons off (unset/auto -> the value the installed build accepts)\" failed (exit $fg_rc)"' EXIT
bash tests/unit/burn-guard.test.sh
)
( # step: CAN014 workshop mode follows the installed builds schema (propose -> off on 2026.10.5+)
echo "--- step: CAN014 workshop mode follows the installed builds schema (propose -> off on 2026.10.5+)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards hardening-and-fleet-standards-exec-guard--structural: step \"CAN014 workshop mode follows the installed builds schema (propose -> off on 2026.10.5+)\" failed (exit $fg_rc)"' EXIT
bash tests/unit/workshop-mode-compat.test.sh
)
( # step: Both scripts parse
echo "--- step: Both scripts parse"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards hardening-and-fleet-standards-exec-guard--structural: step \"Both scripts parse\" failed (exit $fg_rc)"' EXIT
bash -n scripts/install-hardening.sh
bash -n scripts/apply-fleet-standards.sh
bash -n update-skills.sh
)
( # step: install-hardening.sh is bash 3.2 safe (macOS /bin/bash)
echo "--- step: install-hardening.sh is bash 3.2 safe (macOS /bin/bash)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards hardening-and-fleet-standards-exec-guard--structural: step \"install-hardening.sh is bash 3.2 safe (macOS /bin/bash)\" failed (exit $fg_rc)"' EXIT
# macOS ships bash 3.2 at /bin/bash and cron/launchd resolve
# `env bash` straight back to it, so this script must parse there.
# ubuntu has no bash 3.2, so assert the portability constraint the
# only way a linux runner honestly can: no bash-4-only syntax.
bash tests/unit/bash4-syntax-guard.test.sh
)
