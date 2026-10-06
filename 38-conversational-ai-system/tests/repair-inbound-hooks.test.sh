#!/usr/bin/env bash
# Hermetic test for scripts/repair/repair-inbound-hooks.py (fixtures only, stub openclaw CLI) and
# its registration in the shared front door.
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
python3 "$HERE/scripts/repair/repair-inbound-hooks.py" --selftest || { echo "FAIL selftest"; exit 1; }
grep -q '"38-conversational-ai-system/scripts/repair/repair-inbound-hooks.py"' "$ROOT/shared-utils/oct4_frontdoor.py" \
  || { echo "FAIL not registered in oct4_frontdoor.py"; exit 1; }
python3 "$ROOT/shared-utils/oct4_frontdoor.py" --selftest || { echo "FAIL frontdoor selftest"; exit 1; }
echo "ok   inbound-hooks repair"
