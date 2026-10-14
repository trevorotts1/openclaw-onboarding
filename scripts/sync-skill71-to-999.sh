#!/usr/bin/env bash
# Sync Skill 71 from the onboarding repo to the 999 repo (fix plan
# Item 27). Direction is onboarding to 999, always; there is no reverse
# mode. The work lives in sync_skill71_to_999.py beside this wrapper;
# see its docstring for the rules (major-version refusal, onb_only
# refusal, neutral byte copies, generated policy data, adapter files
# reported but never overwritten).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$HERE/sync_skill71_to_999.py" "$@"
