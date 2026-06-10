#!/usr/bin/env bash
# ============================================================
# scripts/onboarding-state.sh — compatibility shim (PRD 2.1 unified)
# ============================================================
# The canonical onboarding state-machine is now:
#   lib-onboarding-state.sh  (repo root, v10.16.48)
#
# This shim exists so any script that still sources
# scripts/onboarding-state.sh (the old Mac-only path) gets
# the correct implementation without code duplication.
# ============================================================

_SHIM_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_OBS_CANONICAL="${_SHIM_SCRIPT_DIR}/../lib-onboarding-state.sh"

if [ -f "$_OBS_CANONICAL" ]; then
    # shellcheck source=/dev/null
    source "$_OBS_CANONICAL"
else
    echo "[onboarding-state shim] WARNING: lib-onboarding-state.sh not found at $_OBS_CANONICAL" >&2
    echo "  Cannot provide onboarding state-machine. Install may be incomplete." >&2
fi
