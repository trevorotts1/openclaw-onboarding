#!/usr/bin/env bash
# qc-responder-policy.sh — single-responder proof for WF28 (B11, B12).
#
# Runs tools/tests/test_responder_policy.py, which pins the routing record, the
# exact native channel map, the thread lease / dedupe, human takeover, opt-out,
# quiet hours, returning contacts and the "content cannot change policy" rule.
#
# Usage: bash 38-conversational-ai-system/scripts/qc-responder-policy.sh
# Exit:  0 every clause holds, 1 any mismatch, 2 usage/environment.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$SKILL_DIR/tools/tests/test_responder_policy.py" "$@"
