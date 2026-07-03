#!/usr/bin/env bash
# 54-anthology-writer/verify-deps.sh — minimal dependency check.
# The engine is stdlib-only Python: the only hard dep is python3. Optional tools
# (a PDF renderer) degrade gracefully. Exit 0 = ok, nonzero = a hard dep missing.
set -uo pipefail
missing=0
if command -v python3 >/dev/null 2>&1; then
    echo "  OK: python3 ($(python3 --version 2>&1))"
else
    echo "  MISSING: python3 (required)"; missing=1
fi
if command -v sha256sum >/dev/null 2>&1 || command -v shasum >/dev/null 2>&1; then
    echo "  OK: a sha256 tool is present (hash-pin gate active)"
else
    echo "  NOTE: no sha256 tool — the entry hash-pin gate is skipped (non-fatal)"
fi
if [ "$missing" -eq 0 ]; then
    echo "verify-deps: PASS"; exit 0
fi
echo "verify-deps: FAIL — install python3"; exit 1
