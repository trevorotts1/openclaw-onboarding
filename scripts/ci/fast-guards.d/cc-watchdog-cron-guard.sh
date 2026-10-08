#!/usr/bin/env bash
# Folded from .github/workflows/cc-watchdog-cron-guard.yml (job "the CC self-heal watchdog is scheduled on install AND update"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check the installer and the skill QC script
set -e -o pipefail
set -euo pipefail
bash -n 32-command-center-setup/scripts/run-full-install.sh
bash -n 32-command-center-setup/qc-command-center-setup.sh
bash -n tests/unit/cc-watchdog-cron-registration.test.sh
echo "bash -n: PASS"
)
( # step: Run the cc-watchdog registration suite
set -e -o pipefail
set -euo pipefail
bash tests/unit/cc-watchdog-cron-registration.test.sh
echo "cc-watchdog-cron-guard: PASS"
)
