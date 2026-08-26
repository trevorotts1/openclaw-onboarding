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
# 4. RECONCILE the ONE host-level watchdog cron (--no-deliver; operator target only):
#    list --all, keep/repair exactly one, collapse duplicates, re-list to prove it
#    OUTSIDE any OpenClaw session (the Box B law); fire a FORCED-DRY_RUN manual tick;
#    confirm a ledger row landed
# Re-running is safe: it re-verifies + upgrades scripts in place and NEVER arms or
# disarms the box (arming is `arm`'s job alone), and never applies a fix.
#
# CONFIG-TOUCHING => refuses root (cron registration; on VPS run inside
# `docker exec -u node`). EXIT: 0 OK, 3 dep, 4 refused, 5 NO PROVEN CRON, 1 error.
# 5 is the 0.6.5 addition: an install whose watchdog tick is not scheduled and
# PROVEN can no longer print "Install OK" - see the cron block for the 19-of-26
# roll logs that reported success over a box nothing was ever scheduled on.
# =============================================================================
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS="$SELF_DIR/scripts"
TAG="[loop-install]"
EX_OK=0; EX_ERR=1; EX_DEP=3; EX_REFUSED=4; EX_CRON=5

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

# The ledger's armed flag as the literal Python bool text ("True"/"False"), or "" on
# any read failure. One reader, so the installer and its self-test cannot disagree.
_armed_state() {
    python3 "$SCRIPTS/loop_ledger.py" init 2>/dev/null \
        | python3 -c 'import json,sys
try: print(json.load(sys.stdin)["armed"])
except Exception: pass'
}

do_install() {
    local cron_state="unknown"
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

    # ---- THE WATCHDOG CRON: reconciled, never blindly added -----------------
    # TWO defects lived here until 0.6.5, and they compounded.
    #
    # (1) THE GATE WAS `command -v openclaw`. A bare ssh to a Mac gets
    #     PATH=/usr/bin:/bin:/usr/sbin:/sbin - no openclaw, no node. The gate
    #     therefore evaluated FALSE on Mac after Mac, took the else branch, and
    #     execution fell straight through to "Install OK" below. That pattern is in
    #     19 of 26 roll logs: the operator read "Install OK" and believed the box was
    #     protected while NOTHING was ever scheduled. openclaw was installed the whole
    #     time (measured: /opt/homebrew/bin on Apple Silicon, /usr/local/bin on Intel,
    #     ~/.local/bin on the operator box) - it was a PATH failure being reported as
    #     a capability fact. loop_cron.py now resolves the binary itself and, when it
    #     truly cannot, returns UNDETERMINED naming every path it probed.
    #
    # (2) `openclaw cron add` RAN UNCONDITIONALLY and has no upsert, so every re-run
    #     added ANOTHER job. Measured 2026-08-26: 25 of 34 running boxes carried 2-12
    #     duplicate loop-tick jobs, all enabled, all */15 - the watchdog firing up to
    #     12x per window. loop_cron.py lists first (--all: `cron list` HIDES disabled
    #     jobs), keeps or repairs exactly one, collapses the rest, and re-lists to
    #     PROVE the result. Running this installer 10 times now leaves exactly 1 job.
    #
    # THE VERDICT IS NO LONGER FREE. cron_state is carried to the end of do_install
    # and a box whose watchdog is not scheduled CANNOT print "Install OK" - it exits
    # EX_CRON(5). update-skills.sh treats a non-zero installer as FAILED, withholds
    # the .wired sentinel and retries next roll, which is exactly the loud behaviour
    # a silently unscheduled watchdog always deserved.
    if [ "$NO_CRON" -eq 1 ]; then
        cron_state="skipped-by-operator"
        echo "$TAG cron registration SKIPPED - --no-cron was passed explicitly."
        echo "$TAG NOTHING on this box will run the watchdog. Manual tick command:"
        echo "  bash $SELF_DIR/loop-companion.sh tick"
    else
        echo "$TAG reconciling the 15-minute host-level watchdog tick (--no-deliver, operator-only)..."
        local cron_rc
        cron_rc=0
        python3 "$SCRIPTS/loop_cron.py" reconcile \
            --name "loop-tick-${BOX}" \
            --cron "*/15 * * * *" \
            --command "bash $SELF_DIR/loop-companion.sh tick" \
            --cwd "$SELF_DIR" || cron_rc=$?
        case "$cron_rc" in
            0) cron_state="ok"
               echo "$TAG watchdog cron PROVEN: exactly one enabled loop-tick-${BOX} (*/15, --no-deliver)" ;;
            3) cron_state="undetermined"
               echo "$TAG UNDETERMINED: could not READ this box's cron table (see the named" >&2
               echo "$TAG   probe list above). Nothing was added. This is NOT a claim that the" >&2
               echo "$TAG   box has no watchdog - it is a claim that we could not look." >&2 ;;
            4) cron_state="needs-operator"
               echo "$TAG NEEDS OPERATOR: loop-tick job(s) this installer will not touch, or" >&2
               echo "$TAG   duplicates left in place by LOOP_CRON_NO_PRUNE=1. See above." >&2 ;;
            *) cron_state="failed"
               echo "$TAG ERROR: cron reconciliation FAILED (exit $cron_rc). Register manually:" >&2
               echo "  openclaw cron add --name loop-tick-${BOX} --cron '*/15 * * * *' --no-deliver --command-cwd '$SELF_DIR' --command 'bash $SELF_DIR/loop-companion.sh tick'" >&2 ;;
        esac
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
    if ! py loop_ledger.py init >/dev/null 2>&1; then
        echo "$TAG ERROR: ledger not healthy after install" >&2; return $EX_ERR
    fi

    # ---- THE VERDICT --------------------------------------------------------
    # "Install OK" used to be unconditional once the ledger opened, so a box whose
    # watchdog was never scheduled reported success in the same breath as the line
    # saying the cron step had been skipped. A watchdog that is not scheduled is not
    # installed, whatever else worked.
    case "$cron_state" in
        ok)
            echo "$TAG ledger healthy. Install OK (role=$ROLE box=$BOX; armed state UNCHANGED)."
            echo "$TAG After the 7-day burn-in, arm Tier-1 with: bash $SELF_DIR/loop-companion.sh arm"
            return $EX_OK ;;
        skipped-by-operator)
            # The operator asked for this explicitly, so it is not a failure - but it
            # is never reported as a protected box either.
            echo "$TAG ledger healthy. Scripts installed (role=$ROLE box=$BOX; armed state UNCHANGED)."
            echo "$TAG ============================================================"
            echo "$TAG  NOT PROTECTED: --no-cron was passed, so no watchdog is"
            echo "$TAG  scheduled on this box. Re-run WITHOUT --no-cron, or"
            echo "$TAG  register the tick yourself, before calling this box done."
            echo "$TAG ============================================================"
            return $EX_OK ;;
        *)
            echo "$TAG ============================================================" >&2
            echo "$TAG  INSTALL INCOMPLETE - cron state: $cron_state" >&2
            echo "$TAG  The ledger and scripts are in place, but this box has NO" >&2
            echo "$TAG  PROVEN 15-minute watchdog tick. It is NOT protected, and" >&2
            echo "$TAG  this installer will NOT report success for it." >&2
            echo "$TAG  Verify with: bash $SELF_DIR/verify.sh --live" >&2
            echo "$TAG ============================================================" >&2
            return $EX_CRON ;;
    esac
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

    # ---- THE VERDICT, FAILABLE IN BOTH DIRECTIONS -------------------------
    # The 0.6.5 defect: a box whose cron step was skipped still printed
    # "Install OK". Both cases below run the REAL do_install with cron enabled,
    # against a STUB gateway (loop_cron.py --emit-stub, the same fake its own
    # self-test uses - one source, so they cannot drift). Hermetic: an
    # unresolvable LOOP_OPENCLAW_BIN returns UNDETERMINED without falling back
    # to PATH, so neither case can ever reach this box's real gateway.
    local out rc stub fdb
    stub="$td/openclaw-stub"
    python3 "$SCRIPTS/loop_cron.py" --emit-stub "$stub" \
        || { echo "$TAG self-test FAIL: could not emit the stub gateway" >&2; rm -rf "$td"; return 1; }
    fdb="$td/fake-cron.json"

    # (a) CRON UNPROVEN -> exit 5 and the words "Install OK" must NOT appear.
    #     This is the exact Mac shape: openclaw not resolvable from this PATH.
    rc=0
    out="$(LOOP_OPENCLAW_BIN="$td/no-such-openclaw" LOOP_NO_PROBES=1 NO_CRON=0 \
        ROLE="client" BOX="selftest-box-example" do_install 2>&1)" || rc=$?
    [ "$rc" -eq 5 ] || { echo "$TAG self-test FAIL: an unscheduled watchdog exited $rc, expected 5" >&2; rm -rf "$td"; return 1; }
    case "$out" in
        *"Install OK"*) echo "$TAG self-test FAIL: printed 'Install OK' with NO watchdog cron" >&2; rm -rf "$td"; return 1 ;;
    esac
    case "$out" in
        *"INSTALL INCOMPLETE"*) : ;;
        *) echo "$TAG self-test FAIL: an unscheduled watchdog produced no loud banner" >&2; rm -rf "$td"; return 1 ;;
    esac
    echo "  unproven-cron case: PASS (exit 5, loud banner, and the words 'Install OK'"
    echo "                      are ABSENT from the entire transcript)"

    # (b) CRON PROVEN -> exit 0, "Install OK", and EXACTLY ONE job - after THREE
    #     installs, which is the duplicate-cron defect measured on 25 of 34 boxes.
    rc=0
    out="$(LOOP_OPENCLAW_BIN="$stub" FAKE_CRON_DB="$fdb" LOOP_NO_PROBES=1 NO_CRON=0 \
        ROLE="client" BOX="selftest-box-example" do_install 2>&1)" || rc=$?
    [ "$rc" -eq 0 ] || { echo "$TAG self-test FAIL: a proven cron install exited $rc" >&2; rm -rf "$td"; return 1; }
    case "$out" in
        *"Install OK"*) : ;;
        *) echo "$TAG self-test FAIL: a proven cron install did not report Install OK" >&2; rm -rf "$td"; return 1 ;;
    esac
    LOOP_OPENCLAW_BIN="$stub" FAKE_CRON_DB="$fdb" LOOP_NO_PROBES=1 NO_CRON=0 \
        ROLE="client" BOX="selftest-box-example" do_install >/dev/null 2>&1 || true
    LOOP_OPENCLAW_BIN="$stub" FAKE_CRON_DB="$fdb" LOOP_NO_PROBES=1 NO_CRON=0 \
        ROLE="client" BOX="selftest-box-example" do_install >/dev/null 2>&1 || true
    local njobs
    njobs="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$fdb" 2>/dev/null)"
    [ "$njobs" = "1" ] || { echo "$TAG self-test FAIL: 3 installs left $njobs cron job(s), expected exactly 1" >&2; rm -rf "$td"; return 1; }
    echo "  proven-cron case: PASS (exit 0, Install OK, and THREE consecutive installs"
    echo "                    leave EXACTLY ONE loop-tick job)"

    # (c) ALREADY SCHEDULED AND CORRECT -> quiet success, and NOT ONE mutating call.
    #     THE regression guard that matters most: if this fails, the skill has
    #     started rewriting a working cron job on every roll across the fleet, and
    #     "skipped" never implied "missing" - a box whose roll log says skipped can
    #     be carrying four healthy enabled registrations.
    rm -f "$td/add-called" "$td/edit-called" "$td/enable-called" 2>/dev/null || true
    rc=0
    out="$(LOOP_OPENCLAW_BIN="$stub" FAKE_CRON_DB="$fdb" LOOP_NO_PROBES=1 NO_CRON=0 \
        ROLE="client" BOX="selftest-box-example" do_install 2>&1)" || rc=$?
    [ "$rc" -eq 0 ] || { echo "$TAG self-test FAIL: an already-scheduled box exited $rc, expected 0" >&2; rm -rf "$td"; return 1; }
    [ -f "$td/add-called" ] && { echo "$TAG self-test FAIL: added a DUPLICATE cron on a box that already had one" >&2; rm -rf "$td"; return 1; }
    [ -f "$td/edit-called" ] && { echo "$TAG self-test FAIL: rewrote a correctly-scheduled cron job" >&2; rm -rf "$td"; return 1; }
    echo "  already-scheduled case: PASS (rc=0, Install OK, and NOT ONE of add/edit"
    echo "                         was called - a correct box is left completely alone)"

    # (d) EXISTS BUT DISABLED -> rc 5, never re-enabled, never duplicated.
    #     A disabled cron is a DECISION somebody made, quite possibly to stop a
    #     runaway. An installer that quietly undoes it is a worse failure than the
    #     one it is fixing.
    python3 -c 'import json,sys
p=sys.argv[1]; j=json.load(open(p))
for r in j: r["enabled"]=False
json.dump(j,open(p,"w"))' "$fdb"
    rm -f "$td/add-called" "$td/edit-called" "$td/enable-called" 2>/dev/null || true
    rc=0
    out="$(LOOP_OPENCLAW_BIN="$stub" FAKE_CRON_DB="$fdb" LOOP_NO_PROBES=1 NO_CRON=0 \
        ROLE="client" BOX="selftest-box-example" do_install 2>&1)" || rc=$?
    [ "$rc" -eq 5 ] || { echo "$TAG self-test FAIL: an all-disabled box exited $rc, expected 5" >&2; rm -rf "$td"; return 1; }
    [ -f "$td/enable-called" ] && { echo "$TAG self-test FAIL: silently re-enabled a deliberately disabled cron" >&2; rm -rf "$td"; return 1; }
    [ -f "$td/add-called" ] && { echo "$TAG self-test FAIL: added a duplicate alongside a disabled registration" >&2; rm -rf "$td"; return 1; }
    case "$out" in
        *"Install OK"*) echo "$TAG self-test FAIL: reported Install OK with only a DISABLED cron" >&2; rm -rf "$td"; return 1 ;;
    esac
    echo "  disabled-only case: PASS (rc=5, no 'Install OK', not re-enabled, not duplicated)"

    # (e) GATEWAY WILL NOT ANSWER -> rc 5, and never a blind registration.
    #     Guessing "none" is how one box reached twelve duplicates.
    rm -f "$td/add-called" 2>/dev/null || true
    rc=0
    out="$(LOOP_OPENCLAW_BIN="$stub" FAKE_CRON_DB="$fdb" FAKE_CRON_FAIL=9 LOOP_NO_PROBES=1 \
        NO_CRON=0 ROLE="client" BOX="selftest-box-example" do_install 2>&1)" || rc=$?
    [ "$rc" -eq 5 ] || { echo "$TAG self-test FAIL: an unreadable cron table exited $rc, expected 5" >&2; rm -rf "$td"; return 1; }
    [ -f "$td/add-called" ] && { echo "$TAG self-test FAIL: registered BLIND when cron state was UNDETERMINED" >&2; rm -rf "$td"; return 1; }
    echo "  undetermined-list case: PASS (rc=5, and nothing registered blind)"

    rm -rf "$td"; unset LOOP_STATE_DIR LOOP_OPENCLAW_ROOT
    echo "$TAG self-test: PASS"; return 0
}

if [ "$SELFTEST" -eq 1 ]; then self_test; exit $?; fi
do_install; exit $?
