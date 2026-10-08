#!/usr/bin/env bash
# Folded from .github/workflows/core-updates-wiring-guard.yml (job "CORE_UPDATES format-robust merger guard (v12.3.11)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Run core-updates-all-skills-wired tests
set -e
chmod +x tests/unit/core-updates-all-skills-wired.test.sh
bash tests/unit/core-updates-all-skills-wired.test.sh
)
