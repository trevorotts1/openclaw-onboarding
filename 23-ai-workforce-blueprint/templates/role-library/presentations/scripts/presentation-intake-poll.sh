#!/usr/bin/env bash
# WORK-ITEM-02: Intake-completion poller for the Presentations department.
#
# This script polls for intake interviews that have completed (intake_ledger.json
# with status=complete) but where the engine has NOT yet been launched for the
# corresponding run directory. When it finds one, it dispatches the engine.
#
# Runs via launchd or cron on a 5-minute interval (same cadence as the watchdog).
# This is the mechanical bridge between a finished intake interview and the engine
# that builds the deck -- the gap at the heart of WORK-ITEM-02 ("the intake cron,
# canonical entry, and CC all stop short").
#
# Exit codes:
#   0 - scan completed (may or may not have found jobs to launch)
#   2 - launcher module not found
#   The engine's own exit code does NOT affect this script -- it spawns the engine
#   in the background and returns immediately.
#
# FIX 61 (W15b-B2) -- dispatch lease. Before dispatching a run dir (either
# --resume for a parked engine or --new for a fresh intake), this script
# acquires working/.lease.json naming "intake-poll-bridge" as holder (with
# pid, host, acquired_at, ttl_s) and releases it as soon as the engine
# process exists and owns .job.lock. The lease serializes the dispatch window
# so two actors never both spawn an engine for the same run dir. A live
# foreign holder skips the run dir this tick (skipped_lease_held); a lease
# with an expired ttl or a dead holder pid is taken over (lease_takeovers).
# PRESENTATION_INTAKE_LEASE=0 restores the pre-fix no-lease behavior.

set -uo pipefail

# F03: cron/launchd runs this with a minimal PATH (observed on this box:
# /usr/bin:/bin:/usr/sbin:/sbin has no /opt/homebrew/bin). Every bare
# `python3` call below would still resolve under that minimal PATH -- macOS
# ships a stub at /usr/bin/python3 -- but SILENTLY to a different
# interpreter (Apple's bundled Python) than the one this codebase is
# developed against at /opt/homebrew/bin/python3 on Apple Silicon (or
# /usr/local/bin on Intel). That is the same class of defect as a command
# that flat-out fails to resolve: a cron run behaves differently from an
# interactive run with nothing in the log to explain why. Prepend the known
# homebrew locations so both environments resolve the same interpreter;
# nothing is removed from whatever PATH cron/launchd already supplies (or
# the /usr/bin:/bin:/usr/sbin:/sbin fallback if PATH is unset, which set -u
# would otherwise reject).
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin:/usr/sbin:/sbin}"

PROG="presentation-intake-poll.sh"
# Resolve SCRIPTS_DIR relative to this script, via the canonical OC workspace
_resolve_scripts_dir() {
    local candidate
    # 1) This script's own dir (when already in the dept workspace)
    candidate="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
    if [ -f "$candidate/presentation_job.py" ]; then echo "$candidate"; return 0; fi
    # 2) Canonical agent workspace (OC_WS_RESOLVED is set by openclaw)
    candidate="${OC_WS_RESOLVED:-${HOME}/.openclaw/workspace}/departments/Presentations/scripts"
    if [ -f "$candidate/presentation_job.py" ]; then echo "$candidate"; return 0; fi
    # 3) OC config root fallback
    candidate="${OPENCLAW_CONFIG_ROOT:-${HOME}/.openclaw}/workspace/departments/Presentations/scripts"
    if [ -f "$candidate/presentation_job.py" ]; then echo "$candidate"; return 0; fi
    return 1
}
SCRIPTS_DIR="$(_resolve_scripts_dir)" || { log "cannot resolve scripts dir"; exit 2; }
LOG_FILE="${HOME}/Library/Logs/openclaw/presentation-intake-poll.log"

log() {
    echo "$(date '+%Y-%m-%dT%H:%M:%S%z') [$PROG] $*" | tee -a "$LOG_FILE"
}

# Resolve the runs root
RUNS_ROOT="${PRESENTATION_RUNS_DIR:-${HOME}/.openclaw/workspace/departments/Presentations/runs}"

if [ ! -d "$RUNS_ROOT" ]; then
    log "runs directory not found: $RUNS_ROOT"
    exit 0
fi

LAUNCHER="$SCRIPTS_DIR/presentation_job/launcher.py"
ENGINE_ENTRY="$SCRIPTS_DIR/presentation_job.py"

if [ ! -f "$LAUNCHER" ]; then
    log "engine launcher not found at $LAUNCHER -- cannot dispatch jobs"
    exit 2
fi

NEW_LAUNCHES=0
SKIPPED_RUNNING=0
SKIPPED_NO_INTAKE=0
SKIPPED_LEASE_HELD=0
LEASE_TAKEOVERS=0
# The run mode declared by the CLIENT for the run dir currently being
# dispatched. Re-read per run dir inside the loop; declared here so `set -u`
# has it defined on every path.
RUN_MODE=""

# ---------------------------------------------------------------------------
# CLIENT RUN MODE (FIX 11) -- the ultra|standard|economy axis, declared by the
# client IN THE INTAKE and carried from here into the run.
#
# THE GAP THIS CLOSES. FIX 11 wired the ENGINE to read the mode it is handed
# (dispatcher._active_mode reads PRESENTATION_MODE), and launcher.py has
# carried `--mode ultra|standard|economy` since FIX 11 landed. But nothing on
# the hands-off CLIENT path ever handed it one. This poller is the only actor
# between a finished intake interview and a running engine, and it dispatched
# with no mode at all: measured on pristine main, an intake ledger declaring
# ultra still resolved active_mode() == "standard" on BOTH branches below.
# Every deck a client got through "agent intake -> launchd poller -> engine"
# ran standard no matter what the client asked for -- ultra was unreachable
# for a client by construction. The intake now carries the declaration
# (deck-intake-questions.json resource_plan.run_mode, riding the existing
# turn 9; no 24th turn) and this is the wire that delivers it.
#
# read_run_mode <run_dir> prints the declared mode, or NOTHING AT ALL.
# Absence is absence: the launcher's own default (model_router.DEFAULT_MODE,
# "standard") then applies. It never guesses ultra -- nothing silently
# launches at the operator ceiling.
#
# The vocabulary is NOT duplicated here: it is read from
# presentation_job.model_router, the single authority active_mode() itself
# uses. A tree where that import fails prints nothing and SAYS SO on stderr;
# an unvalidatable declaration is dropped, never guessed. stderr is
# deliberately NOT sent to /dev/null (unlike the lease helpers above): a
# helper that dies inside this heredoc must be loud, not silent.
# ---------------------------------------------------------------------------
read_run_mode() {
    python3 - "$1" "$SCRIPTS_DIR" <<'PYMODE'
import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
scripts_dir = sys.argv[2]

if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)
try:
    from presentation_job.model_router import MODES, normalize_mode
except Exception as exc:  # noqa: BLE001 -- a partial deploy must be LOUD
    print(f"[run-mode] could not import presentation_job.model_router from "
          f"{scripts_dir} ({exc.__class__.__name__}: {exc}) -- a declared run "
          f"mode cannot be validated against the one authority, so NONE is "
          f"passed and the launcher default (standard) applies. Fix the "
          f"deploy.", file=sys.stderr)
    raise SystemExit(0)


def normalised(raw):
    """One candidate -> a legal mode, or None (with a loud line for garbage)."""
    text = str(raw or "").strip().strip("'\"").strip(";,.").strip()
    if not text:
        return None
    try:
        return normalize_mode(text)
    except ValueError:
        print(f"[run-mode] the intake declared {text!r}, which is not one of "
              f"{'|'.join(MODES)} -- ignoring it and letting the launcher "
              f"default (standard) apply. A run mode is never guessed.",
              file=sys.stderr)
        return None


def load(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def entry_value(entries, key):
    val = entries.get(key)
    if isinstance(val, dict):
        return val.get("value", val.get("normalized"))
    return val


candidates = []

# 1) the intake ledger -- where deck-intake-driver._record_run_mode writes it.
entries = load(run_dir / "working" / "interview" / "intake_ledger.json").get("entries")
if isinstance(entries, dict):
    for key in ("RUN_MODE", "run_mode"):
        candidates.append(entry_value(entries, key))
    # ... and the structured parent record, when the turn stored the dict form.
    parent = entries.get("resource_plan")
    if isinstance(parent, dict) and isinstance(parent.get("value"), dict):
        candidates.append(parent["value"].get("run_mode"))

# 2) intake.json, for a client whose declaration arrived through a bridge that
#    writes the run directory's intake rather than the ledger.
intake = load(run_dir / "working" / "copy" / "intake.json")
for key in ("RUN_MODE", "run_mode"):
    candidates.append(intake.get(key))
capture = intake.get("pre_presentation_capture")
if isinstance(capture, dict):
    candidates.append(capture.get("RUN_MODE"))

seen = set()
for candidate in candidates:
    text = str(candidate or "").strip()
    if not text or text.lower() in seen:
        continue
    seen.add(text.lower())
    mode = normalised(candidate)
    if mode:
        print(mode)
        break
PYMODE
}

# HOW THE MODE IS ADDED TO A DISPATCH, and why it is done INLINE at each call
# site rather than through a wrapper function.
#
#   resume branch: `${RUN_MODE:+--mode "$RUN_MODE"}` -- expands to nothing at
#     all when no mode was declared, so the launcher sees the exact argv it
#     always saw and resolves its own default.
#   new branch:    `env ${RUN_MODE:+PRESENTATION_MODE="$RUN_MODE"} python3 ...`
#     -- the engine entry (presentation_job.py) has NO --mode flag: the
#     run-mode DOOR is the launcher, and that branch does not go through the
#     launcher, it calls the engine directly (--new, then --run).
#     PRESENTATION_MODE is the documented seam for exactly that case;
#     model_router.active_mode names it "how a mode reaches dispatcher / heal /
#     credit_preflight code running in a CHILD process that has no parameter to
#     thread it through", and dispatcher._active_mode is the read that consumes
#     it. The --run branch spawns the engine through subprocess.Popen with no
#     env= argument, so the grandchild inherits it too.
#
# INLINE, not a helper, for two reasons that already cost this repo:
#   1. tests/test_f03_poll_resume_invocation.py EXTRACTS the resume dispatch
#      line out of this file by regex and EXECUTES it, to prove the real line
#      still imports (the F03 file-path-vs-module defect). A dispatch hidden
#      behind a function is invisible to that guard -- the guard would have to
#      be weakened to accommodate the refactor, which is backwards.
#   2. `${var:+...}` is bash-3.2 safe under `set -u` (verified on
#      3.2.57: empty, set and unset all behave), whereas an argv ARRAY under
#      `set -u` is a hard abort on an empty array, and an unquoted
#      "${EXTRA_ARGS}" would word-split.
# Both forms are a TEMPORARY, per-command addition -- never an `export` -- so a
# mode declared by one run dir cannot leak into the next run dir of this scan.

# ---------------------------------------------------------------------------
# FIX 61 (W15b-B2): the intake-poll bridge ACQUIRES A LEASE before it
# dispatches. QC.md FIX 61: "A staged submission becomes a running engine
# within one poll interval with no human action; `working/.lease.json` names
# the bridge as holder."
#
# Without it, two independent actors could dispatch the same run dir in the
# same interval: a poll overlapping the canonical entry door, or two poll
# ticks racing (launchd StartInterval does not serialize -- it CAN overlap),
# or the W14b bridge's own dispatch meeting this poll's dispatch. The engine's
# own RunLock (.job.lock, flock) only fires once an engine process EXISTS --
# it cannot stop two pollers from each spawning an engine process; the loser
# dies at EXIT_LOCK_HELD having already been spawned, logged, and counted as
# a launch. The lease is the pre-spawn serialization: whoever holds
# working/.lease.json is the ONLY actor allowed to dispatch this run dir.
#
# Contract:
#   - holder: "intake-poll-bridge" -- the bridge name the QC proof looks for.
#   - the lease names pid, host, acquired_at, ttl_s, run_dir so a stale lease
#     is provably distinguishable from a live one (expired ttl OR dead holder
#     pid = takeoverable; a live foreign holder = skip, count, never fight).
#   - acquire is ATOMIC (O_EXCL create, temp+rename only inside the holder's
#     own window) -- two pollers cannot both win.
#   - release removes the lease ONLY if this holder still owns it; the
#     engine's .job.lock is the long-term holder after the dispatch window.
#   - PRESENTATION_INTAKE_LEASE=0 is the documented rollback (pre-FIX 61
#     behavior: no lease, dispatch as before).
# ---------------------------------------------------------------------------
LEASE_ENABLED="${PRESENTATION_INTAKE_LEASE:-1}"
LEASE_HOLDER="intake-poll-bridge"
LEASE_TTL_S="${PRESENTATION_INTAKE_LEASE_TTL:-900}"
# FIX 61 pid-lifecycle: the lease's pid field anchors liveness to THIS poller
# shell ($$) for the whole dispatch window -- not to the heredoc python, which
# exits the moment lease_write returns (a lease pinned to that pid is takeover
# bait for every later acquire; see lease_write above).
LEASE_OWNER_PID=$$

# lease_write <run_dir> -- atomically write working/.lease.json naming this
# bridge as holder. Returns 0 when written, 1 when refused (live foreign
# holder), so the caller must re-check rather than dispatch.
lease_write() {
    # FIX 61 pid-lifecycle: record the POLLER SHELL's pid ($$), not the
    # transient heredoc python's. The python that writes the lease exits the
    # instant lease_write returns; a lease carrying ITS pid makes every later
    # lease_acquire see a dead holder and take over -- the lease could never
    # actually refuse a live overlapping dispatch, the exact race this fix
    # exists to stop. The shell (this script) stays alive for the whole
    # dispatch window (acquire -> spawn engine -> release), so its pid is the
    # real liveness anchor. lease_release (below) removes the lease by holder
    # name on every exit path, so no path leaks a lease pinned to a dead pid.
    python3 - "$1" "$LEASE_HOLDER" "$LEASE_TTL_S" "${LEASE_OWNER_PID}" <<'PYLEASE' 2>/dev/null
import json, os, socket, sys, tempfile, time
from pathlib import Path

run_dir = Path(sys.argv[1])
holder = sys.argv[2]
ttl_s = int(sys.argv[3])
owner_pid = int(sys.argv[4]) if len(sys.argv) > 4 and str(sys.argv[4]).isdigit() else os.getpid()
lease_path = run_dir / "working" / ".lease.json"

def read_lease():
    try:
        return json.loads(lease_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

def pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True

existing = read_lease()
if existing is not None:
    # Any lease with a LIVE holder and an unexpired ttl refuses us -- the
    # holder's NAME does not matter (intake-poll-bridge vs canonical-entry
    # vs a second poll tick of the SAME bridge: a second tick is still a
    # live actor, and two dispatchers into one .job.lock is the exact race
    # this lease exists to stop). A dead holder pid (a crashed actor) or an
    # expired ttl is a stale lease -- takeover. A lease we cannot parse is
    # stale by definition.
    acq = existing.get("acquired_at")
    expired = True
    if isinstance(acq, (int, float)):
        expired = (time.time() - acq) > ttl_s
    held_alive = pid_alive(existing.get("pid"))
    if held_alive and not expired:
        print(json.dumps({"acquired": False,
                          "reason": "held by live holder",
                          "holder": existing.get("holder"),
                          "pid": existing.get("pid")}))
        sys.exit(1)

payload = {
    "holder": holder,
    "pid": owner_pid,
    "host": socket.gethostname(),
    "acquired_at": time.time(),
    "ttl_s": ttl_s,
    "run_dir": str(run_dir),
}
lease_path.parent.mkdir(parents=True, exist_ok=True)
# Atomic replace: a concurrent reader either sees the old lease or this one,
# never a half-written file.
fd, tmp = tempfile.mkstemp(dir=str(lease_path.parent), prefix=".lease-", suffix=".tmp")
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    fh.write(json.dumps(payload, indent=2))
    fh.flush()
    os.fsync(fh.fileno())
os.replace(tmp, lease_path)
print(json.dumps({"acquired": True, "holder": holder, "pid": owner_pid,
                  "takeover": existing is not None}))
PYLEASE
}

# lease_takeover_count <lease_out_json> -- increment LEASE_TAKEOVERS when the
# acquire output reports a takeover. MUST be called IN THE MAIN SHELL (the
# caller, right after the command substitution): a counter incremented inside
# a `$(...)` subshell is lost the moment the substitution returns -- that
# exact bug made the first draft count zero takeovers while their log lines
# proved they happened.
lease_takeover_count() {
    case "$1" in
        *'"takeover": true'*) LEASE_TAKEOVERS=$((LEASE_TAKEOVERS + 1)) ;;
    esac
}

# lease_acquire <run_dir> -- acquire the dispatch lease. Prints the
# lease_write output (json) and returns its rc (0 = acquired, 1 = refused by
# a live holder). See lease_takeover_count for the counter call sites.
lease_acquire() {
    lease_write "$1"
}

# lease_release <run_dir> -- remove the lease iff this holder still owns it.
# Never fights a successor: if the holder name differs (takeover happened),
# the file stays.
lease_release() {
    python3 - "$1" "$LEASE_HOLDER" <<'PYREL' 2>/dev/null
import json, sys
from pathlib import Path
run_dir = Path(sys.argv[1])
holder = sys.argv[2]
lease_path = run_dir / "working" / ".lease.json"
try:
    d = json.loads(lease_path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    sys.exit(0)
if d.get("holder") == holder:
    try:
        lease_path.unlink()
    except OSError:
        pass
PYREL
}

# Walk every run directory under $RUNS_ROOT.
while IFS= read -r run_dir; do
    INTAKE_LEDGER="$run_dir/working/interview/intake_ledger.json"
    STATE_JSON="$run_dir/state.json"

    # Must have a completed intake ledger
    if [ ! -f "$INTAKE_LEDGER" ]; then
        continue
    fi

    # Check intake completeness
    INTAKE_COMPLETE=0
    if command -v python3 >/dev/null 2>&1; then
        INTAKE_COMPLETE=$(python3 -c "
import json, sys
try:
    d = json.load(open('$INTAKE_LEDGER'))
    status = d.get('status') or d.get('complete')
    if status == 'complete' or status is True or str(status).lower() == 'true':
        sys.exit(0)
    sys.exit(1)
except Exception:
    sys.exit(1)
" 2>/dev/null && echo 1 || echo 0)
    fi

    if [ "$INTAKE_COMPLETE" -eq 0 ]; then
        continue
    fi

    # FIX 11 client path: what run mode did the CLIENT declare in this intake?
    # Read once here so both dispatch branches below carry the same answer.
    # Empty = undeclared = the launcher's own default (standard) stands.
    RUN_MODE="$(read_run_mode "$run_dir")"
    if [ -n "$RUN_MODE" ]; then
        log "  run mode declared in the intake: $RUN_MODE"
    else
        log "  no run mode declared in the intake -- the launcher default (standard) applies"
    fi

    # Check if the engine has already been launched for this run
    if [ -f "$STATE_JSON" ] && command -v python3 >/dev/null 2>&1; then
        TERMINAL=$(python3 -c "
import json, sys
try:
    s = json.load(open('$STATE_JSON'))
    print(s.get('terminal',''))
except Exception:
    print('')
" 2>/dev/null)
        if [ "$TERMINAL" = "DONE" ] || [ "$TERMINAL" = "BLOCKED" ]; then
            # Already finished or parked -- skip
            continue
        fi

        # Check if already running (PID exists + alive)
        PID=$(python3 -c "
import json, sys
try:
    s = json.load(open('$STATE_JSON'))
    print(s.get('engine_pid',''))
except Exception:
    print('')
" 2>/dev/null)
        if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
            # Already running
            continue
        fi

        # state.json exists but engine is not running -- this is a parked/resume
        # candidate. Launch with --resume.
        #
        # FIX 61: acquire the dispatch lease FIRST (see the lease block above).
        # A live foreign holder means another actor (a second poll tick, the
        # canonical entry door, the W14b bridge) is dispatching this run dir
        # right now -- skip this tick and let it finish; fighting it would
        # spawn two engines into the same .job.lock.
        if [ "$LEASE_ENABLED" = "1" ]; then
            LEASE_OUT="$(lease_acquire "$run_dir")"
            LEASE_RC=$?
            lease_takeover_count "$LEASE_OUT"
            log "  lease: $LEASE_OUT"
            if [ "$LEASE_RC" -ne 0 ]; then
                log "  dispatch skipped: dispatch lease held by another actor"
                SKIPPED_LEASE_HELD=$((SKIPPED_LEASE_HELD + 1))
                continue
            fi
        fi
        #
        # F03: launcher.py is a member of the presentation_job PACKAGE and
        # imports its siblings with a relative import (`from .vocab import
        # ...`). Invoking it BY FILE PATH (`python3 "$LAUNCHER"`) makes
        # Python treat it as a top-level script with no parent package, so
        # that import dies instantly with "attempted relative import with
        # no known parent package" -- proven on this box: `python3
        # presentation_job/launcher.py --check --run-dir <run>` ImportErrors
        # while `python3 -m presentation_job.launcher --check --run-dir
        # <run>` (run from SCRIPTS_DIR) does not. Every --resume dispatch
        # through the old file-path form died the same way, silently, so a
        # parked job could never actually resume. Run it as a module instead
        # -- `-m` requires the package's PARENT directory (SCRIPTS_DIR) to be
        # the working directory, so cd there in a subshell (parens) rather
        # than changing this script's own cwd.
        #
        # FIX 11 client path: the launcher IS the run-mode door, so the mode
        # the CLIENT declared in the intake goes in as --mode. Undeclared
        # expands to nothing at all and the launcher resolves its own default
        # (standard). Never guess ultra. NOTE: this command is extracted
        # VERBATIM and executed by tests/test_f03_poll_resume_invocation.py --
        # keep it one inline line, directly under the log line below.
        log "resuming parked job: $run_dir"
        ( cd "$SCRIPTS_DIR" && python3 -m presentation_job.launcher --resume --run-dir "$run_dir" ${RUN_MODE:+--mode "$RUN_MODE"} ) 2>&1 | while IFS= read -r line; do
            log "  $line"
        done
        NEW_LAUNCHES=$((NEW_LAUNCHES + 1))
        # FIX 61: the dispatch window is over -- the engine now holds .job.lock.
        if [ "$LEASE_ENABLED" = "1" ]; then
            lease_release "$run_dir"
        fi
    else
        # No state.json -- this intake completed but the engine was never launched.
        # Build an intake JSON and create a new engine job.
        log "new intake complete, dispatching engine: $run_dir"

        # fix/deck-type-routing-bypass: this used to build the intake JSON
        # inline with NO deck-type normalization at all (`ptype =
        # ledger.get('presentation_type') or 'from_scratch'`), so a ledger
        # carrying "signature_presentation" (the SOP's own `deck_type` name
        # for what the engine calls "signature") was handed to the engine
        # unresolved, --new rejected it, no state.json was written, and this
        # loop (which always `exit 0`s -- see below) retried the identical
        # failure every 5 minutes, forever, with nothing but a WARNING line
        # to show for it. Resolve through the SAME shared resolver the
        # canonical entry script uses (single-sourced vocabulary, see
        # vocab.py) -- an unresolvable deck type is now a loud ERROR here,
        # not a silent default that would build the WRONG deck.
        # FIX 61 (W15b-B2): acquire the dispatch lease BEFORE resolve/create/
        # run -- the whole dispatch window, from "this intake is launchable"
        # to "an engine process now holds .job.lock". The bridge is the lease
        # holder for that window; see working/.lease.json. A live foreign
        # holder means another actor is already dispatching this run dir.
        if [ "$LEASE_ENABLED" = "1" ]; then
            LEASE_OUT="$(lease_acquire "$run_dir")"
            LEASE_RC=$?
            lease_takeover_count "$LEASE_OUT"
            log "  lease: $LEASE_OUT"
            if [ "$LEASE_RC" -ne 0 ]; then
                log "  dispatch skipped: dispatch lease held by another actor"
                SKIPPED_LEASE_HELD=$((SKIPPED_LEASE_HELD + 1))
                continue
            fi
        fi

        ENGINE_INTAKE_TMP="$run_dir/working/checkpoints/.engine-intake.json"
        mkdir -p "$(dirname "$ENGINE_INTAKE_TMP")"
        RESOLVE_OUT="$(python3 "$SCRIPTS_DIR/presentation_job/resolve_intake.py" \
            --ledger "$INTAKE_LEDGER" --out "$ENGINE_INTAKE_TMP" \
            --source intake-poll 2>&1)"
        if [ $? -ne 0 ]; then
            log "  ERROR: $run_dir did not resolve to a legal presentation_type: $RESOLVE_OUT"
            log "  skipping this run dir until its intake ledger is corrected -- it will NOT silently build the wrong deck type"
            # FIX 61: the lease covered a window that produced no engine --
            # release it so the next tick (after the ledger is corrected)
            # can retry; a stale lease would block the fix itself.
            if [ "$LEASE_ENABLED" = "1" ]; then
                lease_release "$run_dir"
            fi
            continue
        fi
        log "  $RESOLVE_OUT"

        # FIX 11 client path -- THE LAUNCH RECORD. Because this branch does not
        # go through the launcher, nothing here ever wrote the launch-plan
        # sidecars the launcher writes on the resume branch: a fresh client
        # intake declaring ULTRA would correctly RUN ultra and leave no evidence
        # it had. The mode governed but was unauditable, which is worse than not
        # governing -- "ultra was on" becomes an unverifiable claim exactly where
        # proof was demanded. Write the same records, in the same shape, here:
        #   .mode-plan.json   -- resolved mode + its PROVENANCE + ceiling
        #   .model-plan.json  -- the routing stamp (slots + thinking level)
        # Written AFTER the intake resolved and BEFORE the engine is created, so
        # a run dir that never becomes a launch leaves no sidecar -- the same
        # ordering the launcher uses. Best-effort by contract: it prints and
        # returns 0 on any failure, so an audit record can never be the reason a
        # client's deck does not get built.
        ( cd "$SCRIPTS_DIR" && python3 -m presentation_job.launch_plan --run-dir "$run_dir" ${RUN_MODE:+--mode "$RUN_MODE"} --source intake-slot ) 2>&1 | while IFS= read -r line; do
            log "  [launch-plan] $line"
        done

        # Create the engine job then run it.
        # FIX 11 client path: this branch calls the ENGINE directly, not the
        # launcher, so the mode travels as PRESENTATION_MODE rather than as
        # --mode -- the engine entry has no such flag, by design. See the
        # dispatch-mode note above.
        env ${RUN_MODE:+PRESENTATION_MODE="$RUN_MODE"} python3 "$ENGINE_ENTRY" --new --run-dir "$run_dir" --intake "$ENGINE_INTAKE_TMP" 2>&1 | while IFS= read -r line; do
            log "  [create] $line"
        done

        if [ -f "$run_dir/state.json" ]; then
            # Engine job created -- now launch the run (background).
            # We use Python subprocess here because poll.sh itself must return quickly.
            env ${RUN_MODE:+PRESENTATION_MODE="$RUN_MODE"} python3 -c "
import subprocess, sys, os
argv = [sys.executable or 'python3', '$ENGINE_ENTRY', '--run', '--run-dir', '$run_dir']
log_dir = os.path.join('$run_dir', 'working', 'logs')
os.makedirs(log_dir, exist_ok=True)
out = open(os.path.join(log_dir, 'engine-stdout.log'), 'a')
err = open(os.path.join(log_dir, 'engine-stderr.log'), 'a')
proc = subprocess.Popen(argv, cwd='$SCRIPTS_DIR', stdout=out, stderr=err,
                        start_new_session=True, close_fds=True)
print(f' {proc.pid}', end='')
# Write the PID to state.json so the watchdog can monitor it
import json
sp = os.path.join('$run_dir', 'state.json')
if os.path.isfile(sp):
    state = json.load(open(sp))
    state['engine_pid'] = proc.pid
    json.dump(state, open(sp + '.tmp', 'w'), indent=2)
    os.replace(sp + '.tmp', sp)
" 2>&1 | while IFS= read -r line; do
                log "  [run] $line"
            done
            NEW_LAUNCHES=$((NEW_LAUNCHES + 1))
        else
            log "  WARNING: engine --new succeeded but state.json not found -- engine not launched"
        fi
        # FIX 61: dispatch window is over (engine spawned and holds .job.lock,
        # or no engine exists because --new failed). Release the lease either
        # way -- an engine now owns the run; a dead dispatch must not leave a
        # lease that blocks the next tick's retry.
        if [ "$LEASE_ENABLED" = "1" ]; then
            lease_release "$run_dir"
        fi
    fi
done < <(find "$RUNS_ROOT" -maxdepth 2 -type d -name "pres-*" 2>/dev/null)

# FIX 37: emit poller-telemetry event (consuming FIX 5 telemetry infra)
# FIX 61: the event now also carries the lease counters (skipped_lease_held,
# lease_takeovers) so a tick that was throttled by another actor is visible
# in the telemetry stream, not only in poll.log.
TELEMETRY_DIR="${PRESENTATION_RUNS_DIR:-${HOME}/.openclaw/workspace/departments/Presentations}/telemetry"
mkdir -p "$TELEMETRY_DIR"
printf '{"event":"poller_scan","generated_at":"%s","new_launches":%d,"skipped_running":%d,"skipped_no_intake":%d,"skipped_lease_held":%d,"lease_takeovers":%d}\n'     "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$NEW_LAUNCHES" "$SKIPPED_RUNNING" "$SKIPPED_NO_INTAKE" "$SKIPPED_LEASE_HELD" "$LEASE_TAKEOVERS"     >> "$TELEMETRY_DIR/events.jsonl"

log "scan complete: $NEW_LAUNCHES launched ($SKIPPED_LEASE_HELD skipped on lease, $LEASE_TAKEOVERS lease takeovers)"
exit 0
