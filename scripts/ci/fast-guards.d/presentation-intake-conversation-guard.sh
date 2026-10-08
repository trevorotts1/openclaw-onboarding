#!/usr/bin/env bash
# Folded from .github/workflows/presentation-intake-conversation-guard.yml (job "Choice-first / one-at-a-time intake contract (Skill 51)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Intake conversation contract guard
set -e -o pipefail
chmod +x tests/unit/presentation-intake-conversation.test.sh
bash tests/unit/presentation-intake-conversation.test.sh
)
