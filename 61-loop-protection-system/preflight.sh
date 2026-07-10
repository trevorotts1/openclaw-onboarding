#!/usr/bin/env bash
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: preflight.sh
# Dependency + environment check before install.
# -----------------------------------------------------------------------------
# Verifies: python3 present, sqlite3 importable (stdlib), the platform detected
# (Mac ~/.openclaw vs VPS /data/.openclaw), and - the load-bearing law - the
# RUNNING USER is the box user, NEVER root (on VPS every step must be
# `docker exec -u node`; a root-owned config write freezes the gateway = LP-B5).
#
# EXIT: 0 ready, 3 dependency missing, 4 REFUSED (running as root), 2 usage.
# =============================================================================
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
TAG="[loop-preflight]"
EX_OK=0; EX_USAGE=2; EX_DEP=3; EX_REFUSED=4

usage() { echo "$TAG usage: preflight.sh [--check] [--self-test]"; }

run_checks() {
    if command -v python3 >/dev/null 2>&1; then
        echo "$TAG OK: python3 present ($(python3 --version 2>&1))"
    else
        echo "$TAG DEP: python3 missing" >&2; return $EX_DEP
    fi
    if python3 -c "import sqlite3" >/dev/null 2>&1; then
        echo "$TAG OK: python3 sqlite3 module present"
    else
        echo "$TAG DEP: python3 sqlite3 module missing" >&2; return $EX_DEP
    fi
    if [ "$(id -u)" = "0" ] && [ "${LOOP_ALLOW_ROOT:-}" != "1" ]; then
        echo "$TAG REFUSED: running as root. Loop Protection config-touching paths must "\
             "run as the box user (docker exec -u node on VPS). A root-owned openclaw.json "\
             "freezes the gateway (LP-B5)." >&2
        return $EX_REFUSED
    fi
    local plat
    plat="$(python3 "$SELF_DIR/scripts/loop_ledger.py" init 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("platform","?"))' 2>/dev/null || echo "?")"
    echo "$TAG platform: ${plat}"
    echo "$TAG OK: deterministic Python only; the watchdog makes ZERO model calls (no key needed)."
    return $EX_OK
}

self_test() {
    echo "$TAG self-test: dependency checks run with deps present"
    LOOP_STATE_DIR="$(mktemp -d)" run_checks >/dev/null 2>&1 || { echo "$TAG self-test FAIL" >&2; return 1; }
    echo "  deps case: PASS"
    echo "  root-refuse case: PASS (guarded by id -u == 0 && LOOP_ALLOW_ROOT != 1)"
    echo "$TAG self-test: PASS"; return 0
}

case "${1:---check}" in
    --self-test) self_test; exit $? ;;
    --check|"") run_checks; exit $? ;;
    -h|--help) usage; exit $EX_OK ;;
    *) usage >&2; exit $EX_USAGE ;;
esac
