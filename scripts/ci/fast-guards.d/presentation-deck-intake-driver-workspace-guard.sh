#!/usr/bin/env bash
# Folded from .github/workflows/presentation-deck-intake-driver-workspace-guard.yml (job "deck-intake-turngate.py workspace-containment guard (Skill 23, U86)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Driver workspace-containment guard (filesystem diff)
set -e -o pipefail
chmod +x tests/unit/presentation-deck-intake-driver-workspace.test.sh
bash tests/unit/presentation-deck-intake-driver-workspace.test.sh
)
