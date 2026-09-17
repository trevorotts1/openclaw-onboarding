#!/usr/bin/env bash
# =============================================================================
# SKILL 60 - ZHC EARLY WARNING SYSTEM :: install.sh
# Per-box installer - idempotent, node-user-safe, also the upgrade path (spec 5.2).
# -----------------------------------------------------------------------------
# 1. preflight (python3/sqlite3, platform, root-refusal)
# 2. create ews/ state dirs (0700), initialize the ledger, SNAPSHOT ZERO of config
# 3. PIN the baseline (an approval - the operator eyes the printed table)
# 4. register the ONE cron tick (--no-deliver; operator target only) as the
#    `cron-tick` subcommand, NEVER bare `tick`: `cron-tick` maps the sentinel's
#    exit 10 (findings present) to 0 so the scheduler cannot read a successful
#    detection as a job failure and auto-disable the tick. On the operator box
#    ALSO the hourly aggregator cron; verify the cron, fire a manual tick,
#    confirm a ledger row landed
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

# ---------------------------------------------------------------------------
# dedupe_legacy_cron_dupes NAME COMMAND CRON_EXPR
#
# ROOT CAUSE OF "N IDENTICAL TICK CRONS" (fixed 2026-09-03): before this fix,
# `openclaw cron add` was called with plain --name/--cron/--command and NO
# declaration key, and `openclaw cron add` has no dedupe-by-name guard of its
# own - every install/repair/fleet-roll run created ANOTHER identical
# registration. One box carried NINE live "ews-tick-<box>" jobs, each firing
# every 15 minutes. Those pre-existing duplicates predate this fix and are
# NOT self-healing - the new declaration-keyed `cron add` below only
# recognizes jobs that already carry ITS OWN declaration key, so it always
# creates a fresh job the first time it runs on a box, leaving any legacy
# duplicates in place unless something disables them.
#
# This function is that something. It runs BEFORE the declaration-keyed
# `cron add` and only ever acts on PROVEN duplication: it lists existing
# jobs, keeps only those matching this exact name + command + schedule that
# carry NO declaration key (a job this installer already converged always has
# one, so it is never a candidate here), and does nothing at all unless 2 or
# more such jobs exist - a box with a single, ordinary, never-duplicated
# legacy registration is left completely untouched.
#
# When duplication IS found, every matching legacy job is DISABLED (never
# deleted - fully reversible, fully inspectable via `openclaw cron list
# --all`) and logged by id + creation time. All of them, including the
# oldest, are disabled: the declaration-keyed `cron add` immediately
# following this call is what becomes the one enabled, going-forward survivor
# - leaving the oldest duplicate enabled alongside it would just make it a
# second, permanently-duplicated active tick, not a fix. Nothing here can
# fail the install: any error (openclaw missing, list fails, bad JSON,
# disable fails) is logged and swallowed - only the registration call itself
# can flip CRON_FAILURES.
# ---------------------------------------------------------------------------
dedupe_legacy_cron_dupes() {
    local name="$1" command="$2" cron_expr="$3"
    command -v openclaw >/dev/null 2>&1 || return 0
    local listfile
    listfile="$(mktemp 2>/dev/null)" || return 0
    if ! openclaw cron list --all --json >"$listfile" 2>/dev/null; then
        echo "$TAG (dedupe skipped: 'openclaw cron list' failed)"
        rm -f "$listfile"
        return 0
    fi
    python3 - "$listfile" "$name" "$command" "$cron_expr" "$TAG" <<'PY'
import json, subprocess, sys
listfile, name, command, cron_expr, tag = sys.argv[1:6]
try:
    with open(listfile) as fh:
        data = json.load(fh)
except Exception as e:
    print(f"{tag} (dedupe skipped: could not parse cron list JSON: {e})")
    sys.exit(0)
jobs = data.get("jobs") if isinstance(data, dict) else data
if not isinstance(jobs, list):
    sys.exit(0)

def is_legacy_dupe(job):
    if not isinstance(job, dict) or job.get("name") != name:
        return False
    if job.get("declarationKey"):
        return False  # already converged under a declaration key - not a legacy dupe
    payload = job.get("payload") or {}
    argv = payload.get("argv") or []
    if payload.get("kind") != "command" or not argv or argv[-1] != command:
        return False
    schedule = job.get("schedule") or {}
    return schedule.get("expr") == cron_expr

dupes = [j for j in jobs if is_legacy_dupe(j)]
if len(dupes) < 2:
    sys.exit(0)  # no proven duplication - leave a lone legacy registration alone

def created_rank(j):
    v = j.get("createdAtMs")
    return (v if isinstance(v, (int, float)) else float("inf"), str(j.get("id")))

dupes.sort(key=created_rank)
oldest = dupes[0]
print(f"{tag} found {len(dupes)} legacy duplicate registration(s) of '{name}' with no "
      f"declaration key (oldest id={oldest.get('id')} created={oldest.get('createdAtMs')}); "
      f"disabling all {len(dupes)} - the declaration-keyed registration below becomes the "
      f"one enabled survivor:")
for j in dupes:
    jid = j.get("id")
    if not jid:
        continue
    r = subprocess.run(["openclaw", "cron", "disable", jid], capture_output=True, text=True)
    if r.returncode == 0:
        print(f"{tag}   disabled id={jid} created={j.get('createdAtMs')}")
    else:
        err = ((r.stderr or r.stdout or "").strip().splitlines() or ["unknown error"])[0]
        print(f"{tag}   WARN: could not disable duplicate id={jid}: {err}")
PY
    rm -f "$listfile"
    return 0
}

# ---------------------------------------------------------------------------
# reenable_cron_if_disabled DECL_KEY LABEL
#
# ROOT CAUSE OF "THE TICK CRON IS REGISTERED BUT NEVER FIRES" (fixed
# 2026-09-17): the openclaw scheduler records any non-zero exit as a failed run
# and auto-disables the job after 10 consecutive failures. The tick was
# registered as bare `ews-entry.sh tick`, which passes the sentinel's exit 10
# ("findings present" - the system working) straight through, so any box
# carrying a standing finding failed every 15 minutes until the scheduler
# switched its own sentinel off. A live client box was found with
# lastRunStatus=error, exitCode=10, 61 findings, auto-disabled three times.
#
# The `cron-tick` registration below stops that happening again. It does NOT
# undo it: `openclaw cron add --declaration-key` converges an existing job's
# name, schedule and command, but it does not re-enable a job the scheduler
# disabled. So every already-dark box would stay dark through any number of
# installs and fleet rolls. This function is the repair half: after each
# converge, look the job up by its declaration key and, if the scheduler had
# switched it off, switch it back on.
#
# Fails soft by construction - openclaw missing, list failure, bad JSON, no
# matching job, or a failed enable are all logged and swallowed. Only the
# registration call itself can flip CRON_FAILURES.
# ---------------------------------------------------------------------------
reenable_cron_if_disabled() {
    local decl="$1" label="$2"
    command -v openclaw >/dev/null 2>&1 || return 0
    local listfile
    listfile="$(mktemp 2>/dev/null)" || return 0
    if ! openclaw cron list --all --json >"$listfile" 2>/dev/null; then
        echo "$TAG (re-enable check skipped for $label: 'openclaw cron list' failed)"
        rm -f "$listfile"
        return 0
    fi
    python3 - "$listfile" "$decl" "$label" "$TAG" <<'PY'
import json, subprocess, sys
listfile, decl, label, tag = sys.argv[1:5]
try:
    with open(listfile) as fh:
        data = json.load(fh)
except Exception as e:
    print(f"{tag} (re-enable check skipped for {label}: could not parse cron list JSON: {e})")
    sys.exit(0)
jobs = data.get("jobs") if isinstance(data, dict) else data
if not isinstance(jobs, list):
    print(f"{tag} (re-enable check skipped for {label}: unexpected cron list shape)")
    sys.exit(0)
match = next((j for j in jobs
              if isinstance(j, dict) and j.get("declarationKey") == decl), None)
if match is None:
    print(f"{tag} (re-enable check skipped for {label}: no job carries declarationKey={decl})")
    sys.exit(0)
if match.get("enabled") is not False:
    sys.exit(0)  # already enabled (or the CLI does not report the field) - nothing to do
jid = match.get("id")
if not jid:
    print(f"{tag} WARN: {label} is DISABLED but carries no id - cannot re-enable it")
    sys.exit(0)
r = subprocess.run(["openclaw", "cron", "enable", jid], capture_output=True, text=True)
if r.returncode == 0:
    print(f"{tag} {label} was DISABLED (the scheduler switched it off after repeated "
          f"non-zero exits); re-enabled id={jid}")
else:
    err = ((r.stderr or r.stdout or "").strip().splitlines() or ["unknown error"])[0]
    print(f"{tag} WARN: {label} is DISABLED and could NOT be re-enabled (id={jid}): {err}")
PY
    rm -f "$listfile"
    return 0
}

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
    #
    # ROOT CAUSE OF "N IDENTICAL TICK CRONS" (fixed 2026-09-03): `openclaw cron
    # add` has no dedupe-by-name guard, so every install/repair/fleet-roll run
    # created ANOTHER identical registration under the same name, schedule, and
    # command — one box was found carrying NINE live copies of the same tick.
    # FIX: pass `--declaration-key` on every `cron add` call. The CLI's own
    # add-or-converge path matches on that key first: it updates the ONE
    # existing job in place if anything differs, no-ops if nothing changed, and
    # creates exactly one job the first time — so re-running this installer any
    # number of times now always converges to ONE job per declaration key; it
    # never adds a second. `dedupe_legacy_cron_dupes` (above) separately
    # disables any PRE-EXISTING duplicates from before this fix existed — see
    # its header for why those need a distinct, conservative cleanup pass.
    CRON_FAILURES=0
    CRON_FAILED_NAMES=""
    if [ "$NO_CRON" -eq 0 ] && command -v openclaw >/dev/null 2>&1; then
        TICK_NAME="ews-tick-${BOX}"
        TICK_DECL="skill60-ews-tick-${BOX}"
        TICK_CRON_EXPR="*/15 * * * *"
        # The SCHEDULER target is `cron-tick`, never bare `tick`. `cron-tick`
        # runs the identical sentinel tick and maps its exit 10 (findings
        # present) to 0; the scheduler auto-disables a job after 10 consecutive
        # non-zero exits, so registering bare `tick` made any box with a
        # standing finding switch its own sentinel off. Keep this value a
        # single plain "path + subcommand" string with no `;` or `||`:
        # dedupe_legacy_cron_dupes compares it to a job's argv[-1] verbatim.
        TICK_COMMAND="bash $SELF_DIR/ews-entry.sh cron-tick"
        # The command string every install before this fix registered. It is
        # still out there on every box, so it needs its own cleanup pass:
        # dedupe_legacy_cron_dupes matches on the EXACT command, and a pass
        # using only the new string would never see a pre-existing duplicate
        # of the old one.
        TICK_COMMAND_PRE_CRON_TICK="bash $SELF_DIR/ews-entry.sh tick"

        dedupe_legacy_cron_dupes "$TICK_NAME" "$TICK_COMMAND_PRE_CRON_TICK" "$TICK_CRON_EXPR"
        dedupe_legacy_cron_dupes "$TICK_NAME" "$TICK_COMMAND" "$TICK_CRON_EXPR"

        echo "$TAG registering the 15-minute tick cron (--no-deliver, operator-only, declaration-keyed)..."
        if openclaw cron add --name "$TICK_NAME" --cron "$TICK_CRON_EXPR" --no-deliver \
                --declaration-key "$TICK_DECL" \
                --command "$TICK_COMMAND" >/dev/null 2>&1; then
            echo "$TAG tick cron registered (converged — no duplicate)"
            reenable_cron_if_disabled "$TICK_DECL" "$TICK_NAME"
        else
            echo "$TAG ERROR: 'openclaw cron add' FAILED for ${TICK_NAME}" >&2
            CRON_FAILURES=$((CRON_FAILURES + 1)); CRON_FAILED_NAMES="${CRON_FAILED_NAMES}${TICK_NAME} "
        fi
        if [ "$ROLE" = "operator" ]; then
            AGG_NAME="ews-aggregator"
            AGG_DECL="skill60-ews-aggregator"
            AGG_CRON_EXPR="0 * * * *"
            # NO exit remap for the aggregator, deliberately. `fleet cycle`
            # runs ews_fleet.py, whose exit contract is 0 OK / 1 error / 2
            # usage only - it has no "findings" code, so it never emits the
            # non-zero-but-successful exit that the tick did. Its command
            # string is also unchanged by this fix, so it needs no second
            # dedupe pass either. It DOES get the re-enable pass below: a run
            # of genuine errors can disable this job too, and a converge alone
            # never switches a disabled job back on.
            AGG_COMMAND="bash $SELF_DIR/ews-entry.sh fleet cycle"

            dedupe_legacy_cron_dupes "$AGG_NAME" "$AGG_COMMAND" "$AGG_CRON_EXPR"

            if openclaw cron add --name "$AGG_NAME" --cron "$AGG_CRON_EXPR" --no-deliver \
                    --declaration-key "$AGG_DECL" \
                    --command "$AGG_COMMAND" >/dev/null 2>&1; then
                echo "$TAG aggregator cron registered (operator box, converged — no duplicate)"
                reenable_cron_if_disabled "$AGG_DECL" "$AGG_NAME"
            else
                echo "$TAG ERROR: 'openclaw cron add' FAILED for ${AGG_NAME}" >&2
                CRON_FAILURES=$((CRON_FAILURES + 1)); CRON_FAILED_NAMES="${CRON_FAILED_NAMES}${AGG_NAME} "
            fi
        fi
    else
        echo "$TAG cron registration skipped (no gateway or --no-cron)."
        echo "$TAG   by hand (true exit contract, 10 = findings present):"
        echo "    bash $SELF_DIR/ews-entry.sh tick"
        echo "$TAG   to register the cron later, the command MUST be cron-tick:"
        echo "    bash $SELF_DIR/ews-entry.sh cron-tick"
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
        echo "$TAG   openclaw cron add --name ews-tick-${BOX} --cron '*/15 * * * *' --declaration-key skill60-ews-tick-${BOX} --no-deliver --command 'bash $SELF_DIR/ews-entry.sh cron-tick'" >&2
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
# ROOT CAUSE OF "N IDENTICAL TICK CRONS" (fixed 2026-09-03): `openclaw cron add`
# has no dedupe-by-name guard, so an invocation missing --declaration-key
# creates a fresh duplicate registration on every run. Every real invocation
# must declare one so the CLI's own add-or-converge path applies.
undeclared = [l.strip()[:120] for l in calls if not re.search(r"(?<![\w-])--declaration-key\b", l)]
if undeclared:
    print("FAIL\tinvocation(s) pass NO --declaration-key flag (will duplicate on every re-run): " + " || ".join(undeclared))
    raise SystemExit(0)
print(f"OK\t{len(calls)} invocation(s) checked as whole logical lines; all pass --cron and --declaration-key, none pass --schedule")
PY
)"
    case "$cron_check" in
        OK*)   echo "  cron-flag case: PASS (${cron_check#OK	})" ;;
        *)     echo "$TAG self-test FAIL: ${cron_check#FAIL	}" >&2; return 1 ;;
    esac

    # cron-COMMAND case: the registered scheduler command must be `cron-tick`,
    # never bare `tick`.
    #
    # ROOT CAUSE OF "THE TICK CRON AUTO-DISABLES ITSELF" (fixed 2026-09-17):
    # the tick was registered as `ews-entry.sh tick`, which passes the
    # sentinel's exit code through verbatim. The sentinel exits 10 when it HAS
    # findings, which is the system working. The openclaw scheduler has no
    # findings exit: it records any non-zero exit as a failed run and
    # auto-disables the job after 10 consecutive failures. A live client box
    # was found with lastRunStatus=error, exitCode=10, 61 findings, and the
    # tick auto-disabled three times. Every install and fleet roll re-registered
    # the same bare command, so the box healed and re-broke on a loop.
    #
    # The install cases above all run with NO_CRON=1 and never reach the
    # registration lines, and the fake-CLI cases assert the STORE, so only a
    # static check can prove the command SOURCE itself never regresses. It
    # reconstructs each logical line (joining `\` continuations) so a flag on a
    # continuation cannot hide, resolves a shell variable passed as the command
    # back to its assignment, and refuses to pass on a command it cannot
    # resolve - an unresolvable value is an unproven one, not a clean one.
    local tickcmd_check
    tickcmd_check="$(python3 - "$SELF_DIR/install.sh" <<'PY'
import re, sys
src = open(sys.argv[1], encoding="utf-8").read()
logical = re.sub(r"\\\n[ \t]*", " ", src).splitlines()

# Every simple NAME="..." assignment, so a --command passing $NAME resolves.
assign = {m.group(1): m.group(2)
          for m in re.finditer(r'^[ \t]*([A-Za-z_][A-Za-z0-9_]*)="([^"]*)"[ \t]*$', src, re.M)}

def command_values(line):
    out = []
    for m in re.finditer(r'--command[ \t]+(?:"([^"]*)"|\'([^\']*)\')', line):
        out.append(m.group(1) if m.group(1) is not None else m.group(2))
    return out

# Every logical line that mentions a cron-add invocation: the real calls AND
# the by-hand hints this installer prints, which get copy-pasted verbatim.
add_lines = [l for l in logical if re.search(r"openclaw[ \t]+cron[ \t]+add\b", l)]
checked, bad, unresolved = 0, [], []
for line in add_lines:
    for raw in command_values(line):
        checked += 1
        value, var = raw, re.fullmatch(r'\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?', raw.strip())
        if var:
            if var.group(1) not in assign:
                unresolved.append(raw.strip()[:80]); continue
            value = assign[var.group(1)]
        if re.search(r"ews-entry\.sh[ \t]+tick[ \t]*$", value):
            bad.append(value.strip()[:100])
if checked == 0:
    print("FAIL\tno cron-add command value found to check"); raise SystemExit(0)
if unresolved:
    print("FAIL\tcron command variable(s) could not be resolved to an assignment, "
          "so the registered command is unproven: " + " || ".join(unresolved))
    raise SystemExit(0)
if bad:
    print("FAIL\tcron is registered with the bare tick subcommand, which passes the "
          "sentinel's exit 10 (findings present) to the scheduler and gets the job "
          "auto-disabled; use the cron-tick subcommand: " + " || ".join(bad))
    raise SystemExit(0)
print(f"OK\t{checked} cron command value(s) checked; none end in the bare tick subcommand")
PY
)"
    case "$tickcmd_check" in
        OK*)   echo "  cron-command case: PASS (${tickcmd_check#OK	})" ;;
        *)     echo "$TAG self-test FAIL: ${tickcmd_check#FAIL	}" >&2; return 1 ;;
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

    # cron-DEDUPE cases: a fake `openclaw` backed by a tiny JSON cron store that
    # honors --declaration-key add-or-converge, `cron list --all --json`, and
    # `cron disable <id>` — just enough of the real CLI contract to prove the
    # regression this fix exists to close, without touching any real cron store.
    write_fake_cron_bin() {
        local dir="$1"
        mkdir -p "$dir"
        cat > "$dir/openclaw" <<'FAKECRON'
#!/usr/bin/env python3
"""Fake `openclaw` for install.sh self-test only. Backs `cron add/list/disable`
with a JSON file at $FAKE_CRON_STORE, mirroring the real CLI's declaration-key
add-or-converge contract closely enough to prove install.sh's dedupe behavior."""
import json, os, sys

store_path = os.environ["FAKE_CRON_STORE"]

def load():
    if os.path.exists(store_path):
        with open(store_path) as fh:
            return json.load(fh)
    return {"jobs": [], "_seq": 0}

def save(store):
    with open(store_path, "w") as fh:
        json.dump(store, fh)

def parse_flags(argv):
    flags, i = {}, 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            key = a[2:]
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                flags[key] = argv[i + 1]; i += 2
            else:
                flags[key] = True; i += 1
        else:
            i += 1
    return flags

def cmd_add(argv):
    flags = parse_flags(argv)
    name, cron_expr, command = flags.get("name"), flags.get("cron"), flags.get("command")
    decl = flags.get("declaration-key")
    store = load()
    jobs = store.setdefault("jobs", [])
    if decl:
        match = next((j for j in jobs if j.get("declarationKey") == decl), None)
        if match:
            match["name"] = name
            match["schedule"] = {"kind": "cron", "expr": cron_expr}
            match["payload"] = {"kind": "command", "argv": ["sh", "-lc", command]}
            save(store); return 0
    store["_seq"] = store.get("_seq", 0) + 1
    job = {
        "id": f"job-{store['_seq']}", "name": name, "enabled": True,
        "createdAtMs": store["_seq"],
        "schedule": {"kind": "cron", "expr": cron_expr},
        "payload": {"kind": "command", "argv": ["sh", "-lc", command]},
    }
    if decl:
        job["declarationKey"] = decl
    jobs.append(job); save(store); return 0

def cmd_list(argv):
    print(json.dumps({"jobs": load().get("jobs", [])})); return 0

def cmd_set_enabled(argv, value):
    if not argv:
        print("missing job id", file=sys.stderr); return 1
    jid = argv[0]; store = load()
    for j in store.get("jobs", []):
        if j.get("id") == jid:
            j["enabled"] = value; save(store); return 0
    print(f"unknown cron job id: {jid}", file=sys.stderr); return 1

def main():
    argv = sys.argv[1:]
    if len(argv) < 2 or argv[0] != "cron":
        print("fake-openclaw: unsupported invocation", file=sys.stderr); return 1
    sub, rest = argv[1], argv[2:]
    if sub in ("add", "create"): return cmd_add(rest)
    if sub == "list": return cmd_list(rest)
    if sub == "disable": return cmd_set_enabled(rest, False)
    if sub == "enable": return cmd_set_enabled(rest, True)
    print(f"fake-openclaw: unsupported cron subcommand: {sub}", file=sys.stderr); return 1

sys.exit(main())
FAKECRON
        chmod +x "$dir/openclaw"
    }

    local td3 fakebin3 store3
    td3="$(mktemp -d)"; fakebin3="$td3/bin"
    write_fake_cron_bin "$fakebin3"
    store3="$td3/store.json"

    # fresh install -> exactly one cron
    local rc_a count_a
    PATH="$fakebin3:$PATH" FAKE_CRON_STORE="$store3" NO_CRON=0 ROLE="client" BOX="dedupe-test-box" do_install >/dev/null 2>&1; rc_a=$?
    count_a="$(python3 -c "import json; d=json.load(open('$store3')); print(sum(1 for j in d.get('jobs', []) if j.get('name')=='ews-tick-dedupe-test-box'))" 2>/dev/null)"
    if [ "$rc_a" -eq 0 ] && [ "$count_a" = "1" ]; then
        echo "  declaration-key case (fresh install): PASS (exactly 1 cron registered)"
    else
        echo "$TAG self-test FAIL: fresh install left $count_a 'ews-tick-dedupe-test-box' cron(s) (rc=$rc_a)" >&2
        rm -rf "$td3"; return 1
    fi

    # run install.sh AGAIN -> still exactly one (the regression guard)
    local rc_b count_b
    PATH="$fakebin3:$PATH" FAKE_CRON_STORE="$store3" NO_CRON=0 ROLE="client" BOX="dedupe-test-box" do_install >/dev/null 2>&1; rc_b=$?
    count_b="$(python3 -c "import json; d=json.load(open('$store3')); print(sum(1 for j in d.get('jobs', []) if j.get('name')=='ews-tick-dedupe-test-box'))" 2>/dev/null)"
    if [ "$rc_b" -eq 0 ] && [ "$count_b" = "1" ]; then
        echo "  declaration-key case (run install.sh TWICE): PASS (still exactly 1 cron - no duplicate)"
    else
        echo "$TAG self-test FAIL: running install.sh TWICE left $count_b 'ews-tick-dedupe-test-box' cron(s) - the exact regression this fix exists to close" >&2
        rm -rf "$td3"; return 1
    fi

    # existing registration with DIFFERENT content -> updated in place, not duplicated
    python3 - "$store3" <<'PY'
import json, sys
store = json.load(open(sys.argv[1]))
for j in store.get("jobs", []):
    if j.get("name") == "ews-tick-dedupe-test-box":
        j["payload"]["argv"][-1] = "echo stale-command-from-a-prior-version"
        j["schedule"]["expr"] = "*/5 * * * *"
json.dump(store, open(sys.argv[1], "w"))
PY
    PATH="$fakebin3:$PATH" FAKE_CRON_STORE="$store3" NO_CRON=0 ROLE="client" BOX="dedupe-test-box" do_install >/dev/null 2>&1
    local drift_check
    drift_check="$(python3 -c "
import json
d = json.load(open('$store3'))
jobs = [j for j in d.get('jobs', []) if j.get('name') == 'ews-tick-dedupe-test-box']
ok = len(jobs) == 1 and jobs[0]['payload']['argv'][-1].endswith('ews-entry.sh cron-tick') and jobs[0]['schedule']['expr'] == '*/15 * * * *'
print('OK' if ok else 'FAIL')
")"
    if [ "$drift_check" = "OK" ]; then
        echo "  declaration-key case (drifted content): PASS (converged back to current command/schedule, still exactly 1 cron)"
    else
        echo "$TAG self-test FAIL: a drifted existing registration was not converged back to the current command/schedule" >&2
        rm -rf "$td3"; return 1
    fi
    rm -rf "$td3"

    # legacy-duplicate cleanup: 3 pre-existing unkeyed dupes -> all disabled,
    # never deleted; the new declaration-keyed job is the sole enabled survivor
    local td4 fakebin4 store4
    td4="$(mktemp -d)"; fakebin4="$td4/bin"
    write_fake_cron_bin "$fakebin4"
    store4="$td4/store.json"
    python3 - "$store4" "$SELF_DIR" <<'PY'
import json, sys
store_path, self_dir = sys.argv[1], sys.argv[2]
base_cmd = f"bash {self_dir}/ews-entry.sh tick"
store = {"jobs": [], "_seq": 0}
for i, created in enumerate([1000, 2000, 3000]):
    store["jobs"].append({
        "id": f"legacy-{i}", "name": "ews-tick-legacy-test-box", "enabled": True,
        "createdAtMs": created,
        "schedule": {"kind": "cron", "expr": "*/15 * * * *"},
        "payload": {"kind": "command", "argv": ["sh", "-lc", base_cmd]},
    })
    store["_seq"] += 1
json.dump(store, open(store_path, "w"))
PY
    PATH="$fakebin4:$PATH" FAKE_CRON_STORE="$store4" NO_CRON=0 ROLE="client" BOX="legacy-test-box" do_install >/dev/null 2>&1
    local cleanup_check
    cleanup_check="$(python3 -c "
import json
d = json.load(open('$store4'))
jobs = [j for j in d.get('jobs', []) if j.get('name') == 'ews-tick-legacy-test-box']
legacy = [j for j in jobs if not j.get('declarationKey')]
declared = [j for j in jobs if j.get('declarationKey')]
legacy_enabled = [j for j in legacy if j.get('enabled')]
ok = len(legacy) == 3 and len(legacy_enabled) == 0 and len(declared) == 1 and declared[0].get('enabled') is True
print('OK' if ok else f'FAIL legacy={len(legacy)} legacy_enabled={len(legacy_enabled)} declared={len(declared)}')
")"
    if [ "$cleanup_check" = "OK" ]; then
        echo "  legacy-duplicate cleanup case: PASS (3 pre-existing dupes disabled, none deleted; 1 declaration-keyed job is the sole enabled survivor)"
    else
        echo "$TAG self-test FAIL: legacy-duplicate cleanup did not converge to exactly one enabled survivor: $cleanup_check" >&2
        rm -rf "$td4"; return 1
    fi
    rm -rf "$td4"

    # no-false-positive case: a LONE pre-existing registration (no proven
    # duplication) must be left completely untouched by cleanup
    local td5 fakebin5 store5
    td5="$(mktemp -d)"; fakebin5="$td5/bin"
    write_fake_cron_bin "$fakebin5"
    store5="$td5/store.json"
    python3 - "$store5" "$SELF_DIR" <<'PY'
import json, sys
store_path, self_dir = sys.argv[1], sys.argv[2]
store = {"jobs": [{
    "id": "lone-1", "name": "ews-tick-lone-test-box", "enabled": True,
    "createdAtMs": 500,
    "schedule": {"kind": "cron", "expr": "*/15 * * * *"},
    "payload": {"kind": "command", "argv": ["sh", "-lc", f"bash {self_dir}/ews-entry.sh tick"]},
}], "_seq": 1}
json.dump(store, open(store_path, "w"))
PY
    PATH="$fakebin5:$PATH" FAKE_CRON_STORE="$store5" NO_CRON=0 ROLE="client" BOX="lone-test-box" do_install >/dev/null 2>&1
    local lone_check
    lone_check="$(python3 -c "
import json
d = json.load(open('$store5'))
original = next((j for j in d.get('jobs', []) if j.get('id') == 'lone-1'), None)
print('OK' if original is not None and original.get('enabled') is True else 'FAIL')
")"
    if [ "$lone_check" = "OK" ]; then
        echo "  no-false-positive case: PASS (a lone pre-existing registration - no proven duplication - is left untouched)"
    else
        echo "$TAG self-test FAIL: cleanup touched a lone (non-duplicated) pre-existing registration" >&2
        rm -rf "$td5"; return 1
    fi
    rm -rf "$td5"

    # re-enable case: a tick the SCHEDULER already auto-disabled must come back
    # ON. `cron add --declaration-key` converges an existing job's name,
    # schedule and command, but it never re-enables a disabled one - so without
    # the re-enable pass every box the exit-10 bug already switched off would
    # stay dark through any number of installs and fleet rolls, with the
    # installer cheerfully reporting "converged" each time.
    local td6 fakebin6 store6
    td6="$(mktemp -d)"; fakebin6="$td6/bin"
    write_fake_cron_bin "$fakebin6"
    store6="$td6/store.json"
    PATH="$fakebin6:$PATH" FAKE_CRON_STORE="$store6" NO_CRON=0 ROLE="client" BOX="disabled-test-box" do_install >/dev/null 2>&1
    # the scheduler switches it off after 10 consecutive exit-10 runs
    python3 - "$store6" <<'PY'
import json, sys
store = json.load(open(sys.argv[1]))
hit = 0
for j in store.get("jobs", []):
    if j.get("declarationKey") == "skill60-ews-tick-disabled-test-box":
        j["enabled"] = False; hit += 1
assert hit == 1, f"fixture setup: expected 1 declaration-keyed job, found {hit}"
json.dump(store, open(sys.argv[1], "w"))
PY
    local pre_check
    pre_check="$(python3 -c "
import json
d = json.load(open('$store6'))
j = [x for x in d.get('jobs', []) if x.get('declarationKey') == 'skill60-ews-tick-disabled-test-box']
print('OK' if len(j) == 1 and j[0].get('enabled') is False else 'FAIL')
")"
    if [ "$pre_check" != "OK" ]; then
        echo "$TAG self-test FAIL: could not stage a disabled tick job for the re-enable case" >&2
        rm -rf "$td6"; return 1
    fi
    PATH="$fakebin6:$PATH" FAKE_CRON_STORE="$store6" NO_CRON=0 ROLE="client" BOX="disabled-test-box" do_install >/dev/null 2>&1
    local reenable_check
    reenable_check="$(python3 -c "
import json
d = json.load(open('$store6'))
j = [x for x in d.get('jobs', []) if x.get('declarationKey') == 'skill60-ews-tick-disabled-test-box']
ok = len(j) == 1 and j[0].get('enabled') is True and j[0]['payload']['argv'][-1].endswith('ews-entry.sh cron-tick')
print('OK' if ok else f'FAIL jobs={len(j)} enabled={[x.get(\"enabled\") for x in j]}')
")"
    if [ "$reenable_check" = "OK" ]; then
        echo "  re-enable case: PASS (a scheduler-disabled tick is switched back ON by the next install, still exactly 1 cron-tick job)"
    else
        echo "$TAG self-test FAIL: an auto-disabled tick stayed disabled across a re-install: $reenable_check" >&2
        rm -rf "$td6"; return 1
    fi
    rm -rf "$td6"

    unset -f write_fake_cron_bin

    rm -rf "$td"
    unset EWS_STATE_DIR EWS_OPENCLAW_ROOT EWS_CONFIG_PATH
    echo "$TAG self-test: PASS"
    return 0
}

if [ "$SELFTEST" -eq 1 ]; then self_test; exit $?; fi
do_install; exit $?
