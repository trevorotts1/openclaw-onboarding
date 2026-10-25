#!/usr/bin/env bash
# qc-interactive-owner.sh — single-owner proof for interactive workflow steps.
#
# Runs tools/tests/test_interactive_owner.py, which pins every T-19 acceptance
# clause in both directions: the OpenClaw default, controls, callbacks, free
# text, stale taps, and the refusal of two responders (plus zero responders and
# a responder whose kind disagrees with the owner).
#
# Usage: bash 38-conversational-ai-system/scripts/qc-interactive-owner.sh [-v]
# Exit:  0 every clause holds, 1 any mismatch, 2 usage/environment.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

exec python3 "$SKILL_DIR/tools/tests/test_interactive_owner.py" "$@"
