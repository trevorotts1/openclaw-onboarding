#!/usr/bin/env bash
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: install.sh
# Per-box installer - idempotent, box-user-safe, also the upgrade path (spec 9.2).
# -----------------------------------------------------------------------------
# 1. preflight (python3/sqlite3, platform, root-refusal)
# 2. create loop-protection/ state dirs (0700), initialize the ledger
# 3. leave the box's ARMED STATE EXACTLY AS IT WAS. On a fresh ledger that is
#    armed=false (DRY_RUN observe-only, the 7-day burn-in); Tier 1 arms only after
#    the operator runs `loop-companion.sh arm`. THE PRECISE CLAIM MATTERS: install
#    never CHANGES armed, but it cannot promise the box IS in DRY_RUN - a re-install
#    over an already-armed ledger finds armed=true and leaves it true. The header
#    used to claim install "leaves the box in DRY_RUN observe-only", which was only
#    ever true of a FRESH ledger, and the post-install tick honored the ledger - so
#    on an armed box that sentence authorized a live armed tick over that box's real
#    sessions. The tick below is therefore pinned with --dry-run.
# 4. register the ONE host-level watchdog cron (--no-deliver; operator target only)
#    OUTSIDE any OpenClaw session (the Box B law); fire a FORCED-DRY_RUN manual tick;
#    confirm a ledger row landed
# Re-running is safe: it re-verifies + upgrades scripts in place and NEVER arms or
# disarms the box (arming is `arm`'s job alone), and never applies a fix.
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

# The ledger's armed flag as the literal Python bool text ("True"/"False"), or "" on
# any read failure. One reader, so the installer and its self-test cannot disagree.
_armed_state() {
    python3 "$SCRIPTS/loop_ledger.py" init 2>/dev/null \
        | python3 -c 'import json,sys
try: print(json.load(sys.stdin)["armed"])
except Exception: pass'
}

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
        # The schedule flag is --cron, NOT --schedule. `openclaw cron add --help` on
        # 2026.7.1-2 offers --cron/--every/--at (plus a positional schedule) and has NO
        # --schedule at all, so the old invocation could only ever exit non-zero: cron
        # registration was structurally impossible, and the operator saw a bare WARN
        # because stderr went to /dev/null. Never again: on the FAILURE path the real
        # stderr is printed, so a rejected flag names itself.
        # --command-cwd pins the job's working directory to THIS engine copy.
        local cron_err cron_rc
        cron_err="$(openclaw cron add \
            --name "loop-tick-${BOX}" \
            --cron "*/15 * * * *" \
            --no-deliver \
            --command-cwd "$SELF_DIR" \
            --command "bash $SELF_DIR/loop-companion.sh tick" 2>&1 >/dev/null)"
        cron_rc=$?
        if [ "$cron_rc" -eq 0 ]; then
            echo "$TAG tick cron registered (loop-tick-${BOX}, */15, --no-deliver)"
        else
            echo "$TAG WARN: cron add failed (exit $cron_rc); register manually with:" >&2
            echo "  openclaw cron add --name loop-tick-${BOX} --cron '*/15 * * * *' --no-deliver --command-cwd '$SELF_DIR' --command 'bash $SELF_DIR/loop-companion.sh tick'" >&2
            [ -n "$cron_err" ] && printf '%s\n' "$cron_err" >&2
        fi
    else
        echo "$TAG cron registration skipped (no gateway or --no-cron). Manual tick command:"
        echo "  bash $SELF_DIR/loop-companion.sh tick"
    fi

    # A FORCED DRY_RUN TICK, never an armed one. `--no-send` only suppresses delivery:
    # on a box that is ALREADY armed (the ledger's armed flag survives a re-install)
    # this line used to run a fully armed tick over that box's real sessions while
    # printing the word DRY_RUN. --dry-run pins armed=false whatever the ledger says,
    # so the installer's own claim is now true on a fresh AND on an armed box.
    if py loop_ledger.py init 2>/dev/null | /usr/bin/grep -q '"armed": true'; then
        echo "$TAG NOTE: this box is ALREADY ARMED. Install does not change that, and the"
        echo "$TAG       post-install tick below is FORCED observe-only (--dry-run)."
    fi
    echo "$TAG firing a manual tick, FORCED observe-only (--dry-run: applies nothing)..."
    py loop_watchdog.py tick --no-send --dry-run >/dev/null 2>&1 || true
    if py loop_ledger.py init >/dev/null 2>&1; then
        echo "$TAG ledger healthy. Install OK (role=$ROLE box=$BOX; armed state UNCHANGED)."
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
    # A FRESH ledger must come up observe-only: install never arms.
    local armed
    armed="$(_armed_state)"
    [ "$armed" = "False" ] || { echo "$TAG self-test FAIL: install armed a fresh box" >&2; rm -rf "$td"; return 1; }
    echo "  install case: PASS (ledger created, fresh box comes up DRY_RUN observe-only)"
    NO_CRON=1 ROLE="client" BOX="selftest-box-example" do_install >/dev/null 2>&1 || true
    echo "  idempotent case: PASS (re-run safe)"

    # THE CASE THE OLD SELF-TEST NEVER COVERED, and the reason it passed while the
    # header's guarantee was false: an install over an ALREADY-ARMED ledger. The old
    # assertion only ever ran against a fresh sandbox, so armed=False was trivially
    # true and nobody noticed that the post-install tick honored the ledger.
    #
    # A BAITED SANDBOX, because an empty one cannot fail. An armed tick over a sandbox
    # with nothing to fix applies nothing no matter how it is invoked, so asserting
    # "zero fixes" there proves nothing at all. A synthetic poisoned transcript is
    # planted and aged past the auto-roll idle floor, so an armed tick WOULD archive it
    # and a forced-DRY_RUN tick must not. Verified failable: dropping --dry-run from the
    # post-install tick makes this case FAIL.
    local sdir="$td/oc/agents/main/sessions"
    mkdir -p "$sdir"
    cp "$SELF_DIR/tests/fixtures/loop-blocked-session.jsonl" "$sdir/bait-session.jsonl" \
        || { echo "$TAG self-test FAIL: could not plant the bait transcript" >&2; rm -rf "$td"; return 1; }
    python3 -c 'import os,sys,time; p=sys.argv[1]; os.utime(p,(time.time()-3600,)*2)' \
        "$sdir/bait-session.jsonl"
    python3 "$SCRIPTS/loop_ledger.py" arm >/dev/null 2>&1 \
        || { echo "$TAG self-test FAIL: could not arm the sandbox ledger" >&2; rm -rf "$td"; return 1; }
    # LOOP_NO_PROBES keeps the sandboxed install hermetic: no pm2/pgrep/lsof probe
    # against the box actually running the self-test.
    LOOP_NO_PROBES=1 NO_CRON=1 ROLE="client" BOX="selftest-box-example" do_install >/dev/null 2>&1 || true
    armed="$(_armed_state)"
    [ "$armed" = "True" ] || { echo "$TAG self-test FAIL: install DISARMED an armed box (armed=$armed)" >&2; rm -rf "$td"; return 1; }
    [ -f "$sdir/bait-session.jsonl" ] || { echo "$TAG self-test FAIL: install ARCHIVED a real transcript on an armed box; the post-install tick must be forced DRY_RUN" >&2; rm -rf "$td"; return 1; }
    local fixes
    fixes="$(python3 - "$SCRIPTS" <<'PY'
import sys; sys.path.insert(0, sys.argv[1])
from loop_ledger import Ledger
led = Ledger(); print(len(led.list_fixes())); led.close()
PY
)"
    [ "$fixes" = "0" ] || { echo "$TAG self-test FAIL: install applied $fixes fix(es) on an armed box; the post-install tick must be forced DRY_RUN" >&2; rm -rf "$td"; return 1; }
    echo "  armed-box case: PASS (armed left TRUE; a poisoned bait transcript that an"
    echo "                  armed tick WOULD roll is untouched and ZERO fixes applied)"
    rm -rf "$td"; unset LOOP_STATE_DIR LOOP_OPENCLAW_ROOT
    echo "$TAG self-test: PASS"; return 0
}

if [ "$SELFTEST" -eq 1 ]; then self_test; exit $?; fi
do_install; exit $?
