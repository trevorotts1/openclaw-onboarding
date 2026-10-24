#!/usr/bin/env bash
# qc-pb-contracts.sh — shared Purple Billboard contract fixture suite.
#
# Runs tools/tests/test_pb_contracts.py, which validates every fixture in both
# directions against schemas/ plus the semantic rules JSON Schema cannot carry
# (fresh dispatch gate, idempotent collapse, per-placement approval revision,
# stage-separated readiness, ACK-is-not-completion).
#
# Usage: bash 38-conversational-ai-system/scripts/qc-pb-contracts.sh [-v]
# Exit:  0 all fixtures behave as declared, 1 any mismatch, 2 usage/environment.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

exec python3 "$SKILL_DIR/tools/tests/test_pb_contracts.py" "$@"
