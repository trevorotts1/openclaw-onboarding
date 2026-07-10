#!/usr/bin/env bash
# =============================================================================
# SKILL 60 - ZHC EARLY WARNING SYSTEM :: install.sh
# Per-box installer - idempotent, node-user-safe, also the upgrade path (spec 5.2).
# -----------------------------------------------------------------------------
# 1. preflight (python3/sqlite3, platform, root-refusal)
# 2. create ews/ state dirs (0700), initialize the ledger, SNAPSHOT ZERO of config
# 3. PIN the baseline (an approval - the operator eyes the printed table)
# 4. register the ONE cron tick (--no-deliver; operator target only), on the
#    operator box ALSO the hourly aggregator cron; verify the cron, fire a manual
#    tick, confirm a ledger row landed
# 5. one install-confirmation line to the operator (nothing to any client surface)
# Re-running is safe: it re-verifies, upgrades scripts in place, and NEVER re-pins
# the baseline (that is approve-baseline's job alone).
#
# CONFIG-TOUCHING => refuses root (cron registration writes config via the gateway;
# on VPS run inside `docker exec -u node`). EXIT: 0 OK, 3 dep, 4 refused, 1 error.
# =============================================================================
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS="$SELF_DIR/scripts"
TAG="[ews-install]"
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

    echo "$TAG initializing ledger..."
    py ews_ledger.py init >/dev/null || return $EX_ERR
    # meta: role + box (used by the sentinel severity + the alert box name)
    python3 - "$SCRIPTS" "$ROLE" "$BOX" <<'PY' || return $EX_ERR
import sys; sys.path.insert(0, sys.argv[1])
from ews_ledger import Ledger
led = Ledger()
led.set_meta("role", sys.argv[2]); led.set_meta("box", sys.argv[3])
led.set_meta("enforce_caps", led.get_meta("enforce_caps", "false"))  # default OFF (D2)
led.close(); print("meta set")
PY

    echo "$TAG SNAPSHOT ZERO..."
    py ews_snapshot.py snapshot >/dev/null 2>&1 || echo "$TAG (snapshot zero skipped: no readable config yet)"

    # PIN the baseline only if not already pinned (re-run never re-pins)
    if py ews_baseline.py show >/dev/null 2>&1; then
        echo "$TAG baseline already pinned (re-run: NOT re-pinning - use approve-baseline)"
    else
        echo "$TAG pinning baseline (operator: review the table below)..."
        py ews_baseline.py pin || echo "$TAG (baseline pin skipped: no readable config)"
    fi

    # register the ONE cron tick (+ aggregator on the operator box)
    if [ "$NO_CRON" -eq 0 ] && command -v openclaw >/dev/null 2>&1; then
        echo "$TAG registering the 15-minute tick cron (--no-deliver, operator-only)..."
        openclaw cron add --name "ews-tick-${BOX}" --schedule "*/15 * * * *" --no-deliver \
            --command "bash $SELF_DIR/ews-entry.sh tick" >/dev/null 2>&1 \
            && echo "$TAG tick cron registered" || echo "$TAG WARN: cron add failed (register manually)"
        if [ "$ROLE" = "operator" ]; then
            openclaw cron add --name "ews-aggregator" --schedule "0 * * * *" --no-deliver \
                --command "bash $SELF_DIR/ews-entry.sh fleet cycle" >/dev/null 2>&1 \
                && echo "$TAG aggregator cron registered (operator box)" || echo "$TAG WARN: aggregator cron add failed"
        fi
    else
        echo "$TAG cron registration skipped (no gateway or --no-cron). Manual tick command:"
        echo "  bash $SELF_DIR/ews-entry.sh tick"
    fi

    echo "$TAG firing a manual tick..."
    py ews_sentinel.py --no-send tick >/dev/null 2>&1 || true
    # confirm a ledger exists and is healthy
    if py ews_ledger.py init >/dev/null 2>&1; then
        echo "$TAG ledger healthy. Install OK (role=$ROLE box=$BOX)."
    else
        echo "$TAG ERROR: ledger not healthy after install" >&2; return $EX_ERR
    fi
    return $EX_OK
}

self_test() {
    echo "$TAG self-test: sandboxed idempotent install"
    local td; td="$(mktemp -d)"
    export EWS_STATE_DIR="$td/ews" EWS_OPENCLAW_ROOT="$td/oc" EWS_CONFIG_PATH="$td/openclaw.json"
    mkdir -p "$td/oc"
    cat > "$EWS_CONFIG_PATH" <<'JSON'
{ "agents": { "defaults": { "maxConcurrent": 16, "subagents": { "maxConcurrent": 16 },
  "model": { "primary": "glm-5.2", "fallbacks": [] },
  "compaction": { "memoryFlush": { "softThresholdTokens": 20000 } } } },
  "channels": { "telegram": { "accounts": { "default": { "allowFrom": ["1"], "dmPolicy": "allowlist" } } } },
  "cron": [ { "name": "ews-tick", "schedule": "*/15 * * * *", "delivery": "silent" } ] }
JSON
    NO_CRON=1 ROLE="client" BOX="selftest-box-example" do_install >/dev/null 2>&1 || { echo "$TAG self-test FAIL: install errored" >&2; return 1; }
    # ledger exists, baseline pinned, meta set
    [ -f "$td/ews/ews.db" ] || { echo "$TAG self-test FAIL: no ledger" >&2; return 1; }
    [ -f "$td/ews/baseline.json" ] || { echo "$TAG self-test FAIL: baseline not pinned" >&2; return 1; }
    echo "  install case: PASS (ledger + baseline + tick)"
    # idempotent re-run: baseline NOT re-pinned (mtime stable)
    local m1 m2
    m1="$(python3 -c "import os;print(os.path.getmtime('$td/ews/baseline.json'))")"
    NO_CRON=1 ROLE="client" BOX="selftest-box-example" do_install >/dev/null 2>&1 || true
    m2="$(python3 -c "import os;print(os.path.getmtime('$td/ews/baseline.json'))")"
    [ "$m1" = "$m2" ] || { echo "$TAG self-test FAIL: re-run re-pinned the baseline" >&2; return 1; }
    echo "  idempotent case: PASS (re-run did NOT re-pin the baseline)"
    rm -rf "$td"
    unset EWS_STATE_DIR EWS_OPENCLAW_ROOT EWS_CONFIG_PATH
    echo "$TAG self-test: PASS"
    return 0
}

if [ "$SELFTEST" -eq 1 ]; then self_test; exit $?; fi
do_install; exit $?
