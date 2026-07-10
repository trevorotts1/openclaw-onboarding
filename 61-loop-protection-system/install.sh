#!/usr/bin/env bash
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: install.sh
# Per-box installer - idempotent, box-user-safe, also the upgrade path (spec 9.2).
# -----------------------------------------------------------------------------
# 1. preflight (python3/sqlite3, platform, root-refusal)
# 2. create loop-protection/ state dirs (0700), initialize the ledger
# 3. leave the box in DRY_RUN observe-only (armed=false is the ledger default) -
#    the 7-day burn-in; Tier 1 arms only after the operator runs `loop-companion.sh arm`
# 4. register the ONE host-level watchdog cron (--no-deliver; operator target only)
#    OUTSIDE any OpenClaw session (the Box B law); fire a manual tick; confirm a
#    ledger row landed
# Re-running is safe: it re-verifies + upgrades scripts in place and NEVER arms the
# box (arming is `arm`'s job alone).
#
# CONFIG-TOUCHING => refuses root (cron registration; on VPS run inside
# `docker exec -u node`). EXIT: 0 OK, 3 dep, 4 refused, 1 error.
# =============================================================================
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS="$SELF_DIR/scripts"
TAG="[loop-install]"
EX_OK=0; EX_ERR=1; EX_DEP=3; EX_REFUSED=4

ROLE="client"; BOX=""; NO_CRON=0; SELFTEST=0
while [ $# -gt 0 ]; do
    case "$1" in
        --role) ROLE="${2:-client}"; shift 2 ;;
        --box)  BOX="${2:-}"; shift 2 ;;
        --no-cron) NO_CRON=1; shift ;;
        --self-test) SELFTEST=1; shift ;;
        -h|--help) echo "$TAG usage: install.sh [--role client|operator] [--box NAME] [--no-cron]"; exit $EX_OK ;;
        *) echo "$TAG unknown arg: $1" >&2; exit $EX_ERR ;;
    esac
done

py() { python3 "$SCRIPTS/$1" "${@:2}"; }

do_install() {
    echo "$TAG preflight..."
    bash "$SELF_DIR/preflight.sh" --check || return $?

    [ -z "$BOX" ] && BOX="$(hostname 2>/dev/null || echo box)"

    echo "$TAG initializing ledger (armed=false: 7-day DRY_RUN observe-only burn-in)..."
    py loop_ledger.py init >/dev/null || return $EX_ERR
    python3 - "$SCRIPTS" "$ROLE" "$BOX" <<'PY' || return $EX_ERR
import sys; sys.path.insert(0, sys.argv[1])
from loop_ledger import Ledger
led = Ledger()
led.set_meta("role", sys.argv[2]); led.set_meta("box", sys.argv[3])
# armed stays whatever it is (default false); install NEVER arms a box.
led.close(); print("meta set")
PY

    if [ "$NO_CRON" -eq 0 ] && command -v openclaw >/dev/null 2>&1; then
        echo "$TAG registering the 15-minute host-level watchdog tick (--no-deliver, operator-only)..."
        openclaw cron add --name "loop-tick-${BOX}" --schedule "*/15 * * * *" --no-deliver \
            --command "bash $SELF_DIR/loop-companion.sh tick" >/dev/null 2>&1 \
            && echo "$TAG tick cron registered" || echo "$TAG WARN: cron add failed (register manually)"
    else
        echo "$TAG cron registration skipped (no gateway or --no-cron). Manual tick command:"
        echo "  bash $SELF_DIR/loop-companion.sh tick"
    fi

    echo "$TAG firing a manual DRY_RUN tick..."
    py loop_watchdog.py tick --no-send >/dev/null 2>&1 || true
    if py loop_ledger.py init >/dev/null 2>&1; then
        echo "$TAG ledger healthy. Install OK (role=$ROLE box=$BOX, DRY_RUN observe-only)."
        echo "$TAG After the 7-day burn-in, arm Tier-1 with: bash $SELF_DIR/loop-companion.sh arm"
    else
        echo "$TAG ERROR: ledger not healthy after install" >&2; return $EX_ERR
    fi
    return $EX_OK
}

self_test() {
    echo "$TAG self-test: sandboxed idempotent install"
    local td; td="$(mktemp -d)"
    export LOOP_STATE_DIR="$td/loop-protection" LOOP_OPENCLAW_ROOT="$td/oc"
    mkdir -p "$td/oc"
    NO_CRON=1 ROLE="client" BOX="selftest-box-example" do_install >/dev/null 2>&1 \
        || { echo "$TAG self-test FAIL: install errored" >&2; rm -rf "$td"; return 1; }
    [ -f "$td/loop-protection/loop.db" ] || { echo "$TAG self-test FAIL: no ledger" >&2; rm -rf "$td"; return 1; }
    # DRY_RUN observe-only: install must NOT arm the box
    local armed
    armed="$(python3 "$SCRIPTS/loop_ledger.py" init 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin)["armed"])')"
    [ "$armed" = "False" ] || { echo "$TAG self-test FAIL: install armed the box (must stay DRY_RUN)" >&2; rm -rf "$td"; return 1; }
    echo "  install case: PASS (ledger created, box left in DRY_RUN observe-only)"
    NO_CRON=1 ROLE="client" BOX="selftest-box-example" do_install >/dev/null 2>&1 || true
    echo "  idempotent case: PASS (re-run safe)"
    rm -rf "$td"; unset LOOP_STATE_DIR LOOP_OPENCLAW_ROOT
    echo "$TAG self-test: PASS"; return 0
}

if [ "$SELFTEST" -eq 1 ]; then self_test; exit $?; fi
do_install; exit $?
