#!/usr/bin/env bash
# =============================================================================
# scripts/loop-protection-canary.sh — DEPRECATED compatibility shim
# -----------------------------------------------------------------------------
# This file has moved. As of the D20 rename (operator-box-proof vocabulary,
# 2026-07-16), the live script is scripts/loop-protection-first-proof.sh in
# this same directory. This shim execs the new script directly (same argv,
# same process via `exec`) so any existing cron registration, doc example, or
# muscle-memory invocation of this old path keeps working, unchanged, for ONE
# release.
#
# Update your invocation to loop-protection-first-proof.sh; this shim is
# scheduled for removal in the release after next.
# =============================================================================
set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
_NEW_SCRIPT="$SELF_DIR/loop-protection-first-proof.sh"

if [ ! -f "$_NEW_SCRIPT" ]; then
    echo "loop-protection-canary.sh (shim): target $_NEW_SCRIPT not found — the shim and the live script have drifted apart." >&2
    exit 1
fi

exec bash "$_NEW_SCRIPT" "$@"
