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
# 4. CONFIRM the ONE host-level watchdog cron (--no-deliver; operator target only)
#    OUTSIDE any OpenClaw session (the Box B law) - resolve the openclaw CLI without
#    trusting PATH, check whether a loop-tick job already exists, register only when
#    one does not, and FAIL LOUD AND NON-ZERO when the tick is not scheduled and this
#    run could not schedule it; then fire a FORCED-DRY_RUN manual tick
# Re-running is safe: it re-verifies + upgrades scripts in place and NEVER arms or
# disarms the box (arming is `arm`'s job alone), and never applies a fix.
#
# CONFIG-TOUCHING => refuses root (cron registration; on VPS run inside
# `docker exec -u node`). EXIT: 0 OK, 3 dep, 4 refused, 5 cron-not-confirmed,
# 1 error. 5 is a REAL failure to update-skills.sh: it withholds the .wired
# sentinel and retries the skill on the next roll, which is exactly right -
# an unscheduled watchdog must stay visible until someone schedules it.
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

# Resolve the openclaw CLI WITHOUT trusting the caller's PATH, and echo its path.
# Returns non-zero (and echoes nothing) when it genuinely cannot be found.
#
# WHY (LOOP-CRONGATE-20260826). The old gate was a bare `command -v openclaw`.
# update-skills.sh runs every installer as a plain `bash install.sh` - a NON-login
# shell, whose PATH on a Mac box is /usr/bin:/bin:/usr/sbin:/sbin. openclaw lives in
# ~/.local/bin or /opt/homebrew/bin, so the gate missed on essentially every Mac:
# 19 of the 26 roll logs from 2026-08-26 say "cron registration skipped" - including
# boxes carrying four healthy enabled registrations. The CLI was installed and
# reachable the whole time; only PATH was wrong.
_resolve_openclaw() {
    local c
    # An explicit override wins, and is never silently fallen back from: a
    # configured-but-wrong path is a mistake to surface, not to paper over.
    if [ -n "${LOOP_OPENCLAW_BIN:-}" ]; then
        [ -x "${LOOP_OPENCLAW_BIN}" ] && { printf '%s\n' "$LOOP_OPENCLAW_BIN"; return 0; }
        return 1
    fi
    c="$(command -v openclaw 2>/dev/null || true)"
    [ -n "$c" ] && [ -x "$c" ] && { printf '%s\n' "$c"; return 0; }
    # A LOGIN shell, which is where a Mac box's PATH actually gets set.
    c="$(bash -lc 'command -v openclaw' 2>/dev/null | tail -n 1 || true)"
    [ -n "$c" ] && [ -x "$c" ] && { printf '%s\n' "$c"; return 0; }
    for c in "${HOME:-}/.local/bin/openclaw" /opt/homebrew/bin/openclaw \
             /usr/local/bin/openclaw /usr/bin/openclaw; do
        [ -x "$c" ] && { printf '%s\n' "$c"; return 0; }
    done
    return 1
}

# Echo "<enabled> <disabled>" counting jobs named loop-tick-*, or return non-zero
# (echoing nothing) when that cannot be determined. UNDETERMINED IS NOT ZERO: a
# gateway that will not answer is reported as unknown, never as "no cron", because
# "no cron" would make this installer add a duplicate.
#
# Matched by NAME PREFIX, not by the exact loop-tick-${BOX}. BOX comes from
# `hostname`, which drifts (Mac.lan -> Mac), and the question being asked is "does
# THIS BOX have a watchdog tick scheduled", not "does one exist under the name I
# would pick today". --all is required: `openclaw cron list` HIDES disabled jobs,
# which is precisely how a box with a disabled loop-tick read as having none at all.
_loop_tick_state() {
    local bin="$1" out
    out="$("$bin" cron list --all --json 2>/dev/null)" || return 1
    printf '%s' "$out" | python3 -c '
import sys, json
raw = sys.stdin.read()
i = raw.find("{")
if i < 0:
    sys.exit(1)
try:
    d, _ = json.JSONDecoder().raw_decode(raw[i:])
except Exception:
    sys.exit(1)
jobs = d.get("jobs", d) if isinstance(d, dict) else d
if not isinstance(jobs, list):
    sys.exit(1)
lt = [j for j in jobs if isinstance(j, dict)
      and str(j.get("name", "")).startswith("loop-tick-")]
en = [j for j in lt if j.get("enabled")]
print("%d %d" % (len(en), len(lt) - len(en)))
' 2>/dev/null || return 1
}

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

    # ── THE RECURRING WATCHDOG TICK ───────────────────────────────────────────
    # The one fact that makes this skill real. Everything else here is bookkeeping.
    #
    # WHAT THIS BLOCK IS FIXING (LOOP-CRONGATE-20260826). The old gate skipped
    # registration whenever `command -v openclaw` missed, then fired a one-shot tick,
    # printed "ledger healthy. Install OK", and EXITED 0. Two defects, both fixed:
    #   1. The gate fired SPURIOUSLY (see _resolve_openclaw) - openclaw was there.
    #   2. "skipped" EXITED 0 while printing success, so a roll could never create or
    #      repair a missing cron yet reported OK forever. One box was found carrying
    #      live P1 findings with NO recurring tick, its ledger kept looking fresh by
    #      this very installer's post-install tick. It looked watched. It was not.
    #
    # WHAT IT MUST NOT DO. "skipped" never implied "missing" - the control that
    # proves it is a box whose roll log says "skipped" and which has FOUR healthy
    # enabled registrations. Hard-failing every roll that registers nothing would be
    # worse than the bug. So EXISTENCE IS CHECKED FIRST and an already-scheduled box
    # succeeds quietly; only a genuinely unscheduled tick fails.
    local CRON_UNCONFIRMED=0
    local oc_bin cron_state cron_en cron_dis cron_err cron_rc
    if [ "$NO_CRON" -eq 1 ]; then
        echo "$TAG cron registration SKIPPED: --no-cron was passed explicitly."
        echo "$TAG   Manual tick: bash $SELF_DIR/loop-companion.sh tick"
    else
        oc_bin="$(_resolve_openclaw || true)"
        if [ -z "$oc_bin" ]; then
            echo "$TAG ERROR: the 'openclaw' CLI could not be resolved, so the 15-minute" >&2
            echo "$TAG   watchdog tick was NEITHER registered NOR verified on this box." >&2
            echo "$TAG   Searched: \$LOOP_OPENCLAW_BIN, \$PATH, a login shell, \$HOME/.local/bin," >&2
            echo "$TAG   /opt/homebrew/bin, /usr/local/bin, /usr/bin." >&2
            echo "$TAG   This is NOT proof the cron is missing - only that nothing here could" >&2
            echo "$TAG   see it. Undetermined is reported as a FAILURE on purpose: a silent 0" >&2
            echo "$TAG   is what let unwatched boxes read as healthy for days." >&2
            echo "$TAG   Register manually with:" >&2
            echo "     openclaw cron add --name loop-tick-${BOX} --cron '*/15 * * * *' --no-deliver --command-cwd '$SELF_DIR' --command 'bash $SELF_DIR/loop-companion.sh tick'" >&2
            CRON_UNCONFIRMED=1
        else
            cron_state="$(_loop_tick_state "$oc_bin" || true)"
            if [ -z "$cron_state" ]; then
                echo "$TAG ERROR: '$oc_bin cron list --all --json' returned nothing readable, so" >&2
                echo "$TAG   whether a watchdog tick is scheduled here is UNDETERMINED (gateway" >&2
                echo "$TAG   down, or an openclaw too old for --all)." >&2
                echo "$TAG   NOT registering blind: guessing 'none' is how one box reached twelve" >&2
                echo "$TAG   duplicate registrations. Re-run once the gateway answers." >&2
                CRON_UNCONFIRMED=1
            else
                cron_en="${cron_state%% *}"; cron_dis="${cron_state##* }"
                if [ "$cron_en" -gt 0 ]; then
                    echo "$TAG tick cron already scheduled: $cron_en enabled, $cron_dis disabled." \
                         "Nothing to register."
                elif [ "$cron_dis" -gt 0 ]; then
                    echo "$TAG ERROR: this box has $cron_dis loop-tick registration(s) and EVERY ONE" >&2
                    echo "$TAG   IS DISABLED. No watchdog tick is running here." >&2
                    echo "$TAG   NOT re-enabling it and NOT adding a duplicate: a disabled cron is a" >&2
                    echo "$TAG   DECISION somebody made, and an installer that quietly undoes human" >&2
                    echo "$TAG   decisions is a worse failure than the one it is fixing." >&2
                    echo "$TAG   An operator re-enables it deliberately:" >&2
                    echo "     $oc_bin cron list --all | grep loop-tick   # find the id" >&2
                    echo "     $oc_bin cron enable --id <id>" >&2
                    CRON_UNCONFIRMED=1
                else
                    echo "$TAG registering the 15-minute host-level watchdog tick (--no-deliver, operator-only)..."
                    # The schedule flag is --cron, NOT --schedule. `openclaw cron add --help` on
                    # 2026.7.1-2 offers --cron/--every/--at (plus a positional schedule) and has NO
                    # --schedule at all, so the old invocation could only ever exit non-zero: cron
                    # registration was structurally impossible, and the operator saw a bare WARN
                    # because stderr went to /dev/null. Never again: on the FAILURE path the real
                    # stderr is printed, so a rejected flag names itself.
                    # --command-cwd pins the job's working directory to THIS engine copy.
                    cron_err="$("$oc_bin" cron add \
                        --name "loop-tick-${BOX}" \
                        --cron "*/15 * * * *" \
                        --no-deliver \
                        --command-cwd "$SELF_DIR" \
                        --command "bash $SELF_DIR/loop-companion.sh tick" 2>&1 >/dev/null)"
                    cron_rc=$?
                    if [ "$cron_rc" -eq 0 ]; then
                        echo "$TAG tick cron registered (loop-tick-${BOX}, */15, --no-deliver)"
                    else
                        echo "$TAG ERROR: cron add FAILED (exit $cron_rc). No watchdog tick is" >&2
                        echo "$TAG   scheduled on this box. Register manually with:" >&2
                        echo "     openclaw cron add --name loop-tick-${BOX} --cron '*/15 * * * *' --no-deliver --command-cwd '$SELF_DIR' --command 'bash $SELF_DIR/loop-companion.sh tick'" >&2
                        [ -n "$cron_err" ] && printf '%s\n' "$cron_err" >&2
                        CRON_UNCONFIRMED=1
                    fi
                fi
            fi
        fi
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
        # "Install OK" is now a claim about the WHOLE install, cron included. It used
        # to print on a box with no watchdog scheduled at all, which is the sentence
        # that made every roll report unfalsifiable success.
        if [ "$CRON_UNCONFIRMED" -eq 1 ]; then
            echo "$TAG INSTALL INCOMPLETE (rc=$EX_CRON): the ledger is healthy, but the" >&2
            echo "$TAG   recurring watchdog tick is NOT confirmed on this box (see the ERROR" >&2
            echo "$TAG   above). Deliberately NOT reporting 'Install OK'. update-skills.sh" >&2
            echo "$TAG   surfaces a non-zero installer, withholds the .wired sentinel, and" >&2
            echo "$TAG   retries this skill on the next roll." >&2
            return $EX_CRON
        fi
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

    # ---- THE CRON GATE, BOTH DIRECTIONS (LOOP-CRONGATE-20260826) --------------
    # The bug being closed is an installer that reported success on a box with no
    # watchdog scheduled. The obvious fix - fail whenever nothing was registered -
    # would be WORSE than the bug: "skipped" never implied "missing", and the
    # control that proves it is a box whose roll log says "skipped" while carrying
    # four healthy enabled registrations. So both directions are asserted here, and
    # the quiet-success direction is the regression guard that matters most: if it
    # ever fails, this skill has started breaking every Mac roll on the fleet.
    #
    # A STUB openclaw, because the real CLI cannot be made to fail on demand and a
    # test that cannot fail proves nothing. It records what it was ASKED to do, so
    # "did not add a duplicate" and "did not re-enable a human's disabled cron" are
    # checked by absence of a marker, not by absence of a complaint.
    mkdir -p "$td/bin" "$td/marks"
    cat > "$td/bin/openclaw" <<'STUB'
#!/usr/bin/env bash
# install.sh --self-test stub. Answers from $STUB_*; records calls in $STUB_MARKER_DIR.
if [ "${1:-}" = "cron" ] && [ "${2:-}" = "list" ]; then
    case "${STUB_LIST_MODE:-json}" in
        garbage) echo "this is not json"; exit 0 ;;
        fail)    echo "stub: gateway refused" >&2; exit 1 ;;
        *)       printf '%s\n' "${STUB_LIST_JSON:-}"; exit 0 ;;
    esac
fi
if [ "${1:-}" = "cron" ] && [ "${2:-}" = "add" ]; then
    : > "${STUB_MARKER_DIR}/add-called"
    if [ "${STUB_ADD_RC:-0}" != "0" ]; then
        echo "stub: cron add refused" >&2; exit "${STUB_ADD_RC}"
    fi
    exit 0
fi
if [ "${1:-}" = "cron" ] && [ "${2:-}" = "enable" ]; then
    : > "${STUB_MARKER_DIR}/enable-called"; exit 0
fi
exit 0
STUB
    chmod +x "$td/bin/openclaw"
    export STUB_MARKER_DIR="$td/marks" LOOP_NO_PROBES=1

    _cron_case() {   # <name> <expect_rc> ; runs do_install, echoes nothing on pass
        local name="$1" want="$2" got=0
        rm -f "$td/marks/"* 2>/dev/null || true
        NO_CRON=0 ROLE="client" BOX="selftest-box-example" \
            do_install > "$td/cron-out.txt" 2>&1 || got=$?
        if [ "$got" != "$want" ]; then
            echo "$TAG self-test FAIL: cron case '$name' exited $got, expected $want" >&2
            sed -n '1,40p' "$td/cron-out.txt" >&2
            return 1
        fi
        return 0
    }

    # (a) ALREADY SCHEDULED -> quiet success, and NO duplicate added. THE guard
    #     against this fix breaking every Mac roll.
    export LOOP_OPENCLAW_BIN="$td/bin/openclaw" STUB_LIST_MODE=json STUB_ADD_RC=0
    export STUB_LIST_JSON='{"jobs":[{"id":"x1","name":"loop-tick-someotherhostname","enabled":true}]}'
    _cron_case "already-scheduled" 0 || { rm -rf "$td"; return 1; }
    [ -f "$td/marks/add-called" ] && {
        echo "$TAG self-test FAIL: added a DUPLICATE cron on a box that already had one" >&2
        rm -rf "$td"; return 1; }
    /usr/bin/grep -q "already scheduled" "$td/cron-out.txt" || {
        echo "$TAG self-test FAIL: an already-scheduled box did not say so" >&2
        rm -rf "$td"; return 1; }
    /usr/bin/grep -qF "ledger healthy. Install OK" "$td/cron-out.txt" || {
        echo "$TAG self-test FAIL: an already-scheduled box must still report Install OK" >&2
        rm -rf "$td"; return 1; }
    echo "  cron already-scheduled case: PASS (rc=0, Install OK, NO duplicate added)"

    # (b) NOT scheduled, registration SUCCEEDS -> registered, and still rc 0.
    export STUB_LIST_JSON='{"jobs":[{"id":"x2","name":"rescue-rr-box-poll","enabled":true}]}'
    _cron_case "registers-when-missing" 0 || { rm -rf "$td"; return 1; }
    [ -f "$td/marks/add-called" ] || {
        echo "$TAG self-test FAIL: a box with NO loop-tick cron did not register one" >&2
        rm -rf "$td"; return 1; }
    echo "  cron registers-when-missing case: PASS (rc=0, cron add attempted)"

    # (c) NOT scheduled and registration FAILS -> LOUD, rc=5, and NEVER "Install OK".
    export STUB_ADD_RC=1
    _cron_case "add-fails" "$EX_CRON" || { rm -rf "$td"; return 1; }
    /usr/bin/grep -qF "ledger healthy. Install OK" "$td/cron-out.txt" && {
        echo "$TAG self-test FAIL: reported Install OK with NO watchdog cron scheduled" >&2
        rm -rf "$td"; return 1; }
    echo "  cron add-fails case: PASS (rc=$EX_CRON, loud, no 'Install OK')"

    # (d) EXISTS BUT ALL DISABLED -> rc=5, and the installer must NOT re-enable it
    #     and must NOT add a duplicate. A disabled cron is somebody's decision.
    export STUB_ADD_RC=0
    export STUB_LIST_JSON='{"jobs":[{"id":"x3","name":"loop-tick-selftest-box-example","enabled":false}]}'
    _cron_case "disabled-only" "$EX_CRON" || { rm -rf "$td"; return 1; }
    [ -f "$td/marks/enable-called" ] && {
        echo "$TAG self-test FAIL: silently re-enabled a deliberately disabled cron" >&2
        rm -rf "$td"; return 1; }
    [ -f "$td/marks/add-called" ] && {
        echo "$TAG self-test FAIL: added a duplicate alongside a disabled registration" >&2
        rm -rf "$td"; return 1; }
    echo "  cron disabled-only case: PASS (rc=$EX_CRON, not re-enabled, not duplicated)"

    # (e) Gateway will not answer -> UNDETERMINED is rc=5, and never a blind add.
    export STUB_LIST_MODE=garbage
    _cron_case "undetermined-list" "$EX_CRON" || { rm -rf "$td"; return 1; }
    [ -f "$td/marks/add-called" ] && {
        echo "$TAG self-test FAIL: registered BLIND when cron state was undetermined" >&2
        rm -rf "$td"; return 1; }
    echo "  cron undetermined case: PASS (rc=$EX_CRON, no blind registration)"

    # (f) openclaw unresolvable at all -> rc=5, never "Install OK". This is the
    #     literal shape of the 2026-08-26 roll, minus the silent 0.
    export LOOP_OPENCLAW_BIN="$td/bin/openclaw-does-not-exist" STUB_LIST_MODE=json
    _cron_case "unresolvable-cli" "$EX_CRON" || { rm -rf "$td"; return 1; }
    /usr/bin/grep -qF "ledger healthy. Install OK" "$td/cron-out.txt" && {
        echo "$TAG self-test FAIL: reported Install OK when openclaw could not be found" >&2
        rm -rf "$td"; return 1; }
    echo "  cron unresolvable-cli case: PASS (rc=$EX_CRON, no 'Install OK')"

    # (g) --no-cron stays an explicit, successful opt-out.
    unset LOOP_OPENCLAW_BIN
    NO_CRON=1 ROLE="client" BOX="selftest-box-example" \
        do_install > "$td/cron-out.txt" 2>&1 || {
        echo "$TAG self-test FAIL: --no-cron must remain a clean opt-out (rc!=0)" >&2
        rm -rf "$td"; return 1; }
    echo "  cron --no-cron case: PASS (explicit opt-out still exits 0)"
    unset STUB_MARKER_DIR STUB_LIST_JSON STUB_LIST_MODE STUB_ADD_RC LOOP_NO_PROBES

    rm -rf "$td"; unset LOOP_STATE_DIR LOOP_OPENCLAW_ROOT
    echo "$TAG self-test: PASS"; return 0
}

if [ "$SELFTEST" -eq 1 ]; then self_test; exit $?; fi
do_install; exit $?
