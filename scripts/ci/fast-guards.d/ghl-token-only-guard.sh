#!/usr/bin/env bash
# Folded from .github/workflows/ghl-token-only-guard.yml (job "GHL token-only auth guard (no login/2FA regression)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Run token-only guard
set -e -o pipefail
set -euo pipefail
bash scripts/guard-ghl-token-only.sh
echo "✓ Skill 06 token-only auth doctrine enforced (no login/2FA fallback)"
)
