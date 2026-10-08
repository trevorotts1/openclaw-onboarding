#!/usr/bin/env bash
# Folded from .github/workflows/fleet-roll-handoff-guard.yml (job "push-client-embeddings hand-off row (singular, owned, not stale)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Run the hand-off row guard
set -e
python3 tests/unit/fleet-roll-handoff-push-client-embeddings.test.py -v
)
