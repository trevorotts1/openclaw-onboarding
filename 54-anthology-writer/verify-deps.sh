#!/usr/bin/env bash
# 54-anthology-writer/verify-deps.sh — minimal dependency check.
# The engine is stdlib-only Python: the only hard dep is python3. Optional tools
# (a PDF renderer) degrade gracefully. Exit 0 = ok, nonzero = a hard dep missing.
set -euo pipefail
missing=0
if command -v python3 >/dev/null 2>&1; then
    echo "  [PASS] python3 ($(python3 --version 2>&1))"
else
    echo "  MISSING: python3 (required)"; missing=1
fi
if command -v sha256sum >/dev/null 2>&1 || command -v shasum >/dev/null 2>&1; then
    echo "  [PASS] a sha256 tool is present (hash-pin gate active)"
else
    echo "  NOTE: no sha256 tool — the entry hash-pin gate is skipped (non-fatal)"
fi
# ---- Command Center board env check (OPTIONAL — board is fail-soft, never a gate) ----
board_vars=("COMMAND_CENTER_URL" "CC_API_TOKEN" "WEBHOOK_SECRET")
board_unset=0
for var in "${board_vars[@]}"; do
    if [ -z "${!var:-}" ]; then
        board_unset=1
    fi
done
if [ "$board_unset" -eq 1 ]; then
    echo "  NOTE: one or more CC board env vars (COMMAND_CENTER_URL, CC_API_TOKEN, WEBHOOK_SECRET) are unset."
    echo "        The board seam is OPTIONAL — runs will continue without it. Set COMMAND_CENTER_URL to enable."
fi

if [ "$missing" -eq 0 ]; then
    echo "[PASS] verify-deps"; exit 0
fi
echo "[FAIL] verify-deps — install python3"; exit 1
