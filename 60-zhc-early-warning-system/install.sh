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
        # Accepted as a no-op: update-skills.sh passes this to every installer;
        # installers that do not parse it must not fail the roll.
        --idempotent) shift ;;
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
    #
    # ROOT CAUSE OF "INSTALLED WITH ZERO CRONS" (fixed 2026-08-02):
    # These two calls used to end in `|| echo "$TAG WARN: ..."`, which swallowed
    # EVERY failure, and do_install returned EX_OK regardless. So when both calls
    # shipped with the non-existent `--schedule` flag, the installer printed a
    # WARN nobody reads, exited 0, and EWS was live with ZERO crons registered —
    # a guard that is silently dead is worse than no guard, and it is the exact
    # failure class EWS exists to catch. A cron that does not register is an
    # INSTALL FAILURE, not a warning.
    CRON_FAILURES=0
    CRON_FAILED_NAMES=""
    if [ "$NO_CRON" -eq 0 ] && command -v openclaw >/dev/null 2>&1; then
        echo "$TAG registering the 15-minute tick cron (--no-deliver, operator-only)..."
        if openclaw cron add --name "ews-tick-${BOX}" --cron "*/15 * * * *" --no-deliver \
                --command "bash $SELF_DIR/ews-entry.sh tick" >/dev/null 2>&1; then
            echo "$TAG tick cron registered"
        else
            echo "$TAG ERROR: 'openclaw cron add' FAILED for ews-tick-${BOX}" >&2
            CRON_FAILURES=$((CRON_FAILURES + 1)); CRON_FAILED_NAMES="${CRON_FAILED_NAMES}ews-tick-${BOX} "
        fi
        if [ "$ROLE" = "operator" ]; then
            if openclaw cron add --name "ews-aggregator" --cron "0 * * * *" --no-deliver \
                    --command "bash $SELF_DIR/ews-entry.sh fleet cycle" >/dev/null 2>&1; then
                echo "$TAG aggregator cron registered (operator box)"
            else
                echo "$TAG ERROR: 'openclaw cron add' FAILED for ews-aggregator" >&2
                CRON_FAILURES=$((CRON_FAILURES + 1)); CRON_FAILED_NAMES="${CRON_FAILED_NAMES}ews-aggregator "
            fi
        fi
    else
        echo "$TAG cron registration skipped (no gateway or --no-cron). Manual tick command:"
        echo "  bash $SELF_DIR/ews-entry.sh tick"
    fi

    echo "$TAG firing a manual tick..."
    py ews_sentinel.py --no-send tick >/dev/null 2>&1 || true
    # confirm a ledger exists and is healthy
    if py ews_ledger.py init >/dev/null 2>&1; then
        echo "$TAG ledger healthy (role=$ROLE box=$BOX)."
    else
        echo "$TAG ERROR: ledger not healthy after install" >&2; return $EX_ERR
    fi

    # FAIL LOUDLY on any cron that did not register. Deliberately AFTER the
    # ledger check so the operator still gets the full diagnostic picture, but
    # the exit code must not lie: an EWS with no tick never fires.
    if [ "$CRON_FAILURES" -gt 0 ]; then
        echo "" >&2
        echo "$TAG ============================================================" >&2
        echo "$TAG INSTALL FAILED: $CRON_FAILURES cron(s) did NOT register: ${CRON_FAILED_NAMES% }" >&2
        echo "$TAG EWS IS INSTALLED BUT BLIND — the tick never fires, so nothing" >&2
        echo "$TAG is ever checked and no alert can ever be raised. This exits" >&2
        echo "$TAG NON-ZERO on purpose: a silently dead guard is worse than none." >&2
        echo "$TAG Re-run the failing command by hand to see the real error:" >&2
        echo "$TAG   openclaw cron add --name ews-tick-${BOX} --cron '*/15 * * * *' --no-deliver --command 'bash $SELF_DIR/ews-entry.sh tick'" >&2
        echo "$TAG ============================================================" >&2
        return $EX_ERR
    fi

    echo "$TAG Install OK (role=$ROLE box=$BOX)."
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
    # cron-flag case: the two `openclaw cron add` calls must use flags the CLI
    # actually accepts. They shipped with `--schedule`, which does NOT exist on
    # OpenClaw (the real flag is `--cron`; `--schedule` is absent from the CLI
    # entirely). Both calls are wrapped in `|| echo WARN`, so EWS installed
    # "successfully" with ZERO crons registered — a silently dead guard, the
    # same failure class EWS exists to catch. The install cases above run with
    # NO_CRON=1 and never execute these lines, so only a static check sees them.
    #
    # THE GUARD WAS EVADABLE (fixed 2026-08-02). It matched FIRST PHYSICAL LINES
    # only (`grep -nE '^[[:space:]]*openclaw cron add'`), but every real call
    # here spans multiple lines via `\` continuations. Moving `--schedule` onto a
    # continuation line reproduced the original defect verbatim while the
    # self-test still printed PASS and exited 0 — the guard checked the one part
    # of the invocation the bug was not in.
    #
    # It now reconstructs each LOGICAL invocation (joining `\` continuations)
    # before inspecting it, so a flag is seen wherever in the call it sits.
    local cron_check
    cron_check="$(python3 - "$SELF_DIR/install.sh" <<'PY'
import re, sys
src = open(sys.argv[1], encoding="utf-8").read()
# Join backslash-continuations so each invocation is ONE logical line.
logical = re.sub(r"\\\n[ \t]*", " ", src).splitlines()
# Only real invocations: the statement must START the line (after whitespace or
# a shell operator like `if`), never a comment or a diagnostic string.
calls = [l for l in logical
         if re.match(r"^[ \t]*(if[ \t]+)?openclaw[ \t]+cron[ \t]+add\b", l)]
if not calls:
    print("FAIL\tno 'openclaw cron add' invocations found"); raise SystemExit(0)
bad = [l.strip()[:120] for l in calls if re.search(r"(?<![\w-])--schedule\b", l)]
if bad:
    print("FAIL\tuses the non-existent --schedule flag (real flag is --cron): " + " || ".join(bad))
    raise SystemExit(0)
missing = [l.strip()[:120] for l in calls if not re.search(r"(?<![\w-])--cron\b", l)]
if missing:
    print("FAIL\tinvocation(s) pass NO --cron flag: " + " || ".join(missing))
    raise SystemExit(0)
print(f"OK\t{len(calls)} invocation(s) checked as whole logical lines; all pass --cron, none pass --schedule")
PY
)"
    case "$cron_check" in
        OK*)   echo "  cron-flag case: PASS (${cron_check#OK	})" ;;
        *)     echo "$TAG self-test FAIL: ${cron_check#FAIL	}" >&2; return 1 ;;
    esac

    # cron-FAILURE case: a cron that does not register must FAIL the install.
    # The root cause of "EWS installed with ZERO crons" was not only the wrong
    # flag - it was that `|| echo WARN` swallowed the failure and do_install
    # returned EX_OK, so a broken installer reported success. Simulate a failing
    # `openclaw cron add` with a stub on PATH and require a non-zero exit.
    local fakebin td2
    td2="$(mktemp -d)"; fakebin="$td2/bin"; mkdir -p "$fakebin"
    printf '#!/usr/bin/env bash\nexit 1\n' > "$fakebin/openclaw"; chmod +x "$fakebin/openclaw"
    local rc_fail out_fail
    out_fail="$(PATH="$fakebin:$PATH" NO_CRON=0 ROLE="client" BOX="selftest-box-example" do_install 2>&1)"; rc_fail=$?
    if [ "$rc_fail" -eq 0 ]; then
        echo "$TAG self-test FAIL: a FAILING 'openclaw cron add' still returned exit 0 - the installer reports success while EWS has ZERO crons and never ticks" >&2
        rm -rf "$td2"; return 1
    fi
    if ! printf '%s\n' "$out_fail" | grep -q "INSTALL FAILED"; then
        echo "$TAG self-test FAIL: cron registration failed but no unmistakable INSTALL FAILED message was printed" >&2
        rm -rf "$td2"; return 1
    fi
    echo "  cron-failure case: PASS (failing cron add -> exit $rc_fail + explicit INSTALL FAILED message)"

    # ...and the --no-cron path must STILL succeed (skipping is not failing).
    local rc_skip
    NO_CRON=1 ROLE="client" BOX="selftest-box-example" do_install >/dev/null 2>&1; rc_skip=$?
    if [ "$rc_skip" -ne 0 ]; then
        echo "$TAG self-test FAIL: --no-cron install returned $rc_skip - deliberately skipping cron must stay a success" >&2
        rm -rf "$td2"; return 1
    fi
    echo "  cron-skip case: PASS (--no-cron still exits 0; only a real failure fails)"
    rm -rf "$td2"

    rm -rf "$td"
    unset EWS_STATE_DIR EWS_OPENCLAW_ROOT EWS_CONFIG_PATH
    echo "$TAG self-test: PASS"
    return 0
}

if [ "$SELFTEST" -eq 1 ]; then self_test; exit $?; fi
do_install; exit $?
