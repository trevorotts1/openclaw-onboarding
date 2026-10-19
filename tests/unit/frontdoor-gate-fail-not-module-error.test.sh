#!/usr/bin/env bash
# tests/unit/frontdoor-gate-fail-not-module-error.test.sh — CAN004 regression lock.
# oct4_frontdoor.py exits 1 for a gate-failed VERDICT. frontdoor_run_stage read
# any non-zero exit as "module errored", threw the real report away and sent the
# traceback to /dev/null, so every gate failure surfaced as an opaque
# 'module errored: <path>'. Runs the REAL lib + module against a scratch
# OPENCLAW_ROOT (never the live one). Exit: 0 green; 1 regressed.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LIB="$REPO_ROOT/shared-utils/lib-frontdoor.sh"
PY="$REPO_ROOT/shared-utils/oct4_frontdoor.py"
W="$(mktemp -d "${TMPDIR:-/tmp}/frontdoor-gatefail-XXXXXX")"
trap 'rm -rf "$W"' EXIT
fail=0; ok() { echo "  ok   $1"; }; bad() { echo "  FAIL $1"; fail=1; }

mkdir -p "$W/skills" "$W/scripts/health"
printf '#!/bin/bash\nexit 1\n' > "$W/scripts/health/library-gate-check.sh"
out="$(OPENCLAW_ROOT="$W" bash -c 'source "$1"; frontdoor_run_stage "$2" 2>/dev/null; echo "STATUS=$FRONTDOOR_STATUS"' _ "$LIB" "$PY")"
case "$out" in *STATUS=gate-failed*) ok "failing gate reports gate-failed";; *) bad "failing gate reported: $out";; esac

# a module that really crashes must surface its exception text in the reason
printf 'raise RuntimeError("boom-from-module")\n' > "$W/broken.py"
out="$(OPENCLAW_ROOT="$W" bash -c 'source "$1"; frontdoor_run_stage "$2" 2>/dev/null; echo "STATUS=$FRONTDOOR_STATUS"' _ "$LIB" "$W/broken.py")"
case "$out" in *STATUS=failed*boom-from-module*|*boom-from-module*STATUS=failed*) ok "crash reason carries the real exception";; *) bad "crash reason: $out";; esac

# an unusable interpreter (rc=127) must still leave failure JSON on stdout (plain-shell fallback)
out="$(OC_FRONTDOOR_PYTHON=/nonexistent/python3 OPENCLAW_ROOT="$W" bash -c 'source "$1"; frontdoor_run_stage "$2" 2>/dev/null; echo "STATUS=$FRONTDOOR_STATUS"' _ "$LIB" "$PY")"
case "$out" in *'"status":"failed"'*'module errored (exit 127)'*STATUS=failed*) ok "unusable interpreter still prints failure JSON";; *) bad "unusable interpreter output: $out";; esac

[ "$fail" = 0 ] && echo "PASS" || { echo "REGRESSED"; exit 1; }
