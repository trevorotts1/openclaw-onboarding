#!/usr/bin/env bash
# Folded from .github/workflows/updater-skill-box-state-guard.yml (job "update-skills.sh keeps allow-listed skill box state (owner pins)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: The updater still parses
set -e
bash -n update-skills.sh
)
( # step: Owner pins survive an update and are honored
set -e
bash tests/unit/updater-preserves-skill-box-state.test.sh
)
