#!/usr/bin/env bash
# Folded from .github/workflows/presentation-intelligence-engines-workspace-guard.yml (job "intelligence_engines_check.py workspace-path guard (Skill 23/51, U86)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Workspace-path resolution guard
set -e -o pipefail
chmod +x tests/unit/presentation-intelligence-engines-workspace.test.sh
bash tests/unit/presentation-intelligence-engines-workspace.test.sh
)
