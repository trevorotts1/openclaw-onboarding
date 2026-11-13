#!/usr/bin/env bash
# Folded from .github/workflows/ghl-auth-fallback-guard.yml (job "GHL Tier-2 email-2FA auth-fallback guard (contained, gated, bounded, self-healing)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Run Tier-2 auth-fallback guard
echo "--- step: Run Tier-2 auth-fallback guard"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards ghl-auth-fallback-guard: step \"Run Tier-2 auth-fallback guard\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash scripts/guard-ghl-auth-fallback.sh
echo "✓ Skill 06/44 Tier-2 email-2FA fallback enforced (contained, gated-before-login, bounded, self-heals to token-only, leak-free, client-store-only)"
)
( # step: Re-assert Tier-1 token-only guard still green (no regression)
echo "--- step: Re-assert Tier-1 token-only guard still green (no regression)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards ghl-auth-fallback-guard: step \"Re-assert Tier-1 token-only guard still green (no regression)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash scripts/guard-ghl-token-only.sh
echo "✓ Tier-1 token-only doctrine intact (a Tier-2 change did not disturb the two Tier-1 files)"
)
( # step: Re-assert Tier-1 activation-resilience guard still green (no regression)
echo "--- step: Re-assert Tier-1 activation-resilience guard still green (no regression)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards ghl-auth-fallback-guard: step \"Re-assert Tier-1 activation-resilience guard still green (no regression)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash scripts/guard-ghl-activation-resilience.sh
echo "✓ Tier-1 activation resilience intact"
)
( # step: Run Tier-2 auth-fallback tests (MOCK GHL + MOCK Gmail only — never a real account)
echo "--- step: Run Tier-2 auth-fallback tests (MOCK GHL + MOCK Gmail only — never a real account)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards ghl-auth-fallback-guard: step \"Run Tier-2 auth-fallback tests (MOCK GHL + MOCK Gmail only — never a real account)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 -m pip install --quiet --disable-pip-version-check pytest
python3 -m pytest -q \
  06-ghl-install-pages/tests/test_ghl_auth_orchestrator.py \
  06-ghl-install-pages/tests/test_ghl_auth_fallback_gates.py \
  06-ghl-install-pages/tests/test_ghl_auth_fallback_happy_and_selfheal.py \
  06-ghl-install-pages/tests/test_guard_ghl_auth_fallback.py \
  06-ghl-install-pages/tests/test_ghl_secret_hygiene.py
)
