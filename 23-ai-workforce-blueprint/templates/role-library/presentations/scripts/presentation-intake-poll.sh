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

# PRES-035 native-tool fallback PATH. The launchd plist renders BOTH Homebrew
# prefixes (Apple Silicon /opt/homebrew/bin + Intel /usr/local/bin) behind
# the system prefix; this runtime prepend is the belt to those braces — a
# tick whose plist predates the PRES-035 render (or a hand invocation under
# a bare cron PATH) still discovers the same native tools. Nothing is
# removed; the rendered launchd PATH and any operator PATH survive intact.
case ":$PATH:" in
    *":/opt/homebrew/bin:"*) ;;
    *) PATH="/opt/homebrew/bin:$PATH" ;;
esac
case ":$PATH:" in
    *":/usr/local/bin:"*) ;;
    *) PATH="/usr/local/bin:$PATH" ;;
esac
export PATH

PROG="presentation-intake-poll.sh"

# ---------------------------------------------------------------------------
# PRES-035 — ONE pipeline interpreter for this whole tick.
#
# The updater validates and persists a department venv
# (PRESENTATION_PIPELINE_INTERPRETER), but this script used to invoke bare
# `python3` — which, under a launchd/cron PATH, silently resolves to a
# DIFFERENT interpreter (Apple's /usr/bin/python3 stub) than the validated
# engine. Every python below therefore runs through $PRESENTATION_PY: the
# validated pin when set+usable, else the client venv, else PATH python3 —
# with the choice logged once per tick, so a cron run can never again
# behave differently from an interactive run with nothing in the log.
#
# Order matters: defined BEFORE _resolve_scripts_dir (helpers below need
# it), but the LOG_FILE-twins note above still holds — log() is defined
# further down, so this block reports through its own tick-header lines
# once log() exists, and stays silent before that.
#
# Precedence: the SCHEDULE's explicit pin wins (rendered by
# lib-presentation-schedules.sh, validated before render); a NON-BLANK
# process value from a hand invocation wins over nothing — it IS the pin;
# the client venv is next; PATH python3 is the last resort. Rollback:
# PRESENTATION_PIPELINE_PIN=0 restores bare `python3` everywhere.
# ---------------------------------------------------------------------------
PRESENTATION_PY=""
_pres35_init_interpreter() {
    local _pin="${PRESENTATION_PIPELINE_INTERPRETER:-}"
    if [ "${PRESENTATION_PIPELINE_PIN:-1}" = "0" ]; then
        PRESENTATION_PY="python3"
        return 0
    fi
    if [ -n "$_pin" ]; then
        case "$_pin" in /*)
            if [ -x "$_pin" ]; then
                PRESENTATION_PY="$_pin"
                return 0
            fi
            ;;
        esac
    fi
    return 1
}
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

# F3 -- ONE LINE PER LINE. This used to be `| tee -a "$LOG_FILE"`, which
# writes the line to $LOG_FILE *and* to stdout. Under launchd that is a
# DOUBLE WRITE, because presentation-intake-poll.plist.template sets BOTH
#   <key>StandardOutPath</key><string><LOG_PATH></string>
#   <key>StandardErrorPath</key><string><LOG_PATH></string>
# and install.sh renders <LOG_PATH> as
#   $HOME/Library/Logs/openclaw/presentation-intake-poll.log
# -- byte-for-byte the same path as $LOG_FILE above. So every logged line
# landed in that file twice: once from tee's own append, once from launchd
# copying our stdout into the same file.
#
# WHY IT MATTERS BEYOND TIDINESS: the log is EVIDENCE, and a doubled log
# doubles every measurement taken from it. The 2026-09-06 outage was counted
# from this file as 5,948 consecutive AF-NOTIFY-UNCONFIGURED refusals; the
# true figure was ~2,978 -- the same outage, inflated 2x by this line. A
# count read off a doubled log is not a small error, it is a wrong number
# reported with full confidence.
#
# `>>` (append) is the fix: the line reaches $LOG_FILE exactly once, from
# exactly one writer, and launchd's StandardOutPath copy is empty rather
# than a duplicate. Nothing else in this script writes to stdout on the
# happy path, so the plist needs no change and no existing log is rotated
# or rewritten. An interactive run reads the log the same way launchd does:
#   tail -f ~/Library/Logs/openclaw/presentation-intake-poll.log
log() {
    echo "$(date '+%Y-%m-%dT%H:%M:%S%z') [$PROG] $*" >> "$LOG_FILE"
}

# ---------------------------------------------------------------------------
# ENV STORE -- launchd/cron hands this script essentially NO environment.
#
# THE DEFECT THIS CLOSES (measured on the operator Mac, 2026-09-06):
# 5,948 consecutive dispatch refusals in this script's own log --
#   AF-NOTIFY-UNCONFIGURED: PRESENTATION_NOTIFY_CMD is unset or blank
# -- while PRESENTATION_NOTIFY_CMD was PRESENT and non-blank (len 61) in all
# three of this box's env stores. The credential was never missing. It was
# simply absent from THIS PROCESS's environment, because nothing here ever
# loaded a store and the LaunchAgent's EnvironmentVariables dict did not
# carry it either. launcher.py's notify_gate then refused every single
# dispatch, every five minutes, for over a day.
#
# IT IS A CLASS, NOT AN INSTANCE. Every credential a CHILD of this script
# needs arrives the same way. OPENROUTER_API_KEY is the second instance:
# shared-utils/llm_score.py reads it from os.environ only (falling back to
# openclaw.json's env block, never to the secrets stores), so a persona
# pass spawned from an environment-less scheduler logs
# "all models failed: OPENROUTER_API_KE...". Loading the store HERE, at the
# entry point, fixes every such reader at once -- they are all children.
#
# PRECEDENCE: an already-set, NON-BLANK process value WINS and is never
# overwritten, so `PRESENTATION_NOTIFY_CMD=... bash presentation-intake-poll.sh`
# still overrides for one invocation and the plist's own EnvironmentVariables
# still win over a stale store. That is the OPPOSITE of the `set -a; . file`
# idiom used elsewhere in this repo, and it is deliberate -- see the module
# docstring. A BLANK value is absence, not an override.
#
# NO VALUE IS EVER LOGGED. The loader's --emit-shell output (the only surface
# carrying values) is captured in a command substitution and eval'd; it never
# reaches $LOG_FILE. What IS logged is --report: paths, name counts, and
# per-name presence plus LENGTH. Emitted AFTER the eval, so it reports what
# actually resolved in this process rather than what the loader predicted.
#
# Loaded BEFORE RUNS_ROOT below, so a store may legitimately supply
# PRESENTATION_RUNS_DIR too.
#
# Rollback: PRESENTATION_ENV_STORE=0 (documented no-op; the report says so).
# ---------------------------------------------------------------------------
load_env_store() {
    if [ ! -f "$SCRIPTS_DIR/presentation_job/env_store.py" ]; then
        log "  [env-store] presentation_job/env_store.py NOT FOUND under $SCRIPTS_DIR -- the env store was not loaded (partial deploy). Every credential this scan's children need must already be in this process env, or dispatch will be refused downstream."
        return 1
    fi
    # `-m` needs the package's PARENT dir as cwd; a subshell keeps this
    # script's own cwd untouched (same reason the dispatch lines below do it).
    # PRES-035: the env-store loader runs under the pinned interpreter when
    # already known, else PATH python3 — it must measure the same interpreter
    # the dispatch below will use, never a different host python.
    _ENV_SH="$( cd "$SCRIPTS_DIR" && python3 -m presentation_job.env_store --emit-shell 2>/dev/null )"
    _ENV_RC=$?
    if [ "$_ENV_RC" -ne 0 ]; then
        unset _ENV_SH
        log "  [env-store] loader exited rc=$_ENV_RC -- the env store was NOT loaded and nothing was exported"
        return 1
    fi
    # eval, NOT `. "$file"`: the loader emits only shlex-quoted
    # `export NAME=value` lines, so a store file cannot execute anything --
    # strictly safer than sourcing it, which runs the whole file as shell.
    eval "$_ENV_SH"
    unset _ENV_SH
    ( cd "$SCRIPTS_DIR" && python3 -m presentation_job.env_store --report 2>&1 ) | while IFS= read -r _env_line; do
        log "  [env-store] $_env_line"
    done
    return 0
}

# PRES-035 — finish the interpreter pin AFTER the env store loads (a store
# may legitimately supply PRESENTATION_PIPELINE_INTERPRETER for this box)
# and BEFORE anything else runs python. Resolution: schedule pin first
# (validated before render, _pres35_init_interpreter already took it when
# usable), else the client venv via pipeline_interp.py, else PATH python3
# last-resort. The tick header names the interpreter, its version and the
# source. A set-but-unusable pin is reported here and falls through to the
# venv rather than silently substituting a host interpreter.
#
# HOW THE PIN REACHES EVERY HELPER. The dispatch lines below keep their
# shipped `python3 ...` shape VERBATIM (tests/test_f03_poll_resume_invocation.py
# extracts the --resume line by regex and EXECUTES it; tests/test_fix37_*
# and tests/test_auto_resume.py extract the walk body and the
# POLLER-LAUNCH-VERIFY block the same way — rewording those lines breaks the
# guards). Instead this function installs a shim directory at the FRONT of
# PATH containing an executable `python3` that execs the pinned interpreter.
# PATH lookup then resolves every bare `python3` below — helpers, dispatch,
# engine spawns — to the validated pin, with zero line changes and a full
# audit trail in the log.
_pres35_finish_interpreter() {
    local _resolved="" _src="unknown"
    if [ -n "${PRESENTATION_PY:-}" ]; then
        _resolved="$PRESENTATION_PY"; _src="schedule-pin"
    elif [ -f "$SCRIPTS_DIR/presentation_job/pipeline_interp.py" ]; then
        _resolved="$(cd "$SCRIPTS_DIR" && python3 -m presentation_job.pipeline_interp --resolve 2>/dev/null || true)"
        if [ -n "$_resolved" ]; then _src="pipeline_interp(client-venv-or-path)"; fi
    fi
    if [ -z "$_resolved" ]; then
        _resolved="python3"; _src="PATH-last-resort"
    fi
    if [ -n "${PRESENTATION_PIPELINE_INTERPRETER:-}" ] && [ "$_src" != "schedule-pin" ]; then
        log "  [interp] schedule pin ${PRESENTATION_PIPELINE_INTERPRETER} unusable (missing or not executable) — fell through to $_resolved ($_src); fix the pin or re-run update-skills.sh"
    fi
    # Validate before use: the pin must actually run, not just resolve as a
    # name. A NAME resolving is never proof the program runs.
    if ! "$_resolved" -c 'import sys' >/dev/null 2>&1; then
        log "  [interp] VALIDATION FAILED: $_resolved does not execute — refusing this tick rather than running helpers under an unknown interpreter"
        return 1
    fi
    PRESENTATION_PY="$_resolved"
    export PRESENTATION_PY PRESENTATION_PIPELINE_INTERPRETER="$_resolved"
    _PRES35_VER="$("$_resolved" -c 'import sys; print(sys.version.split()[0])' 2>/dev/null || echo unknown)"
    log "  [interp] pipeline interpreter: $PRESENTATION_PY (Python $_PRES35_VER; source: $_src)"
    # The shim: every bare `python3` below resolves to the pin. Kept under
    # the run's own working dir (never /tmp-shared): one tick's shim can
    # never redirect another run's python.
    _PRES35_SHIM="$RUNS_ROOT/working/.interp-shim-$$"
    if mkdir -p "$_PRES35_SHIM" 2>/dev/null; then
        printf '#!/bin/sh\nexec "%s" "$@"\n' "$_resolved" > "$_PRES35_SHIM/python3" 2>/dev/null             && chmod +x "$_PRES35_SHIM/python3" 2>/dev/null             && PATH="$_PRES35_SHIM:$PATH" && export PATH             && log "  [interp] shim installed: python3 -> $PRESENTATION_PY"             || log "  [interp] WARNING: shim install failed — bare python3 below resolves via PATH (tick continues, pin exported)"
    else
        log "  [interp] WARNING: shim dir unwritable — bare python3 below resolves via PATH (tick continues, pin exported)"
    fi
    # Scheduler readiness receipt: actual sys.executable/version + required
    # import proof, compared against the rendered pin; mismatch degrades
    # with bounded remediation instead of reusing stale proof.
    if [ -f "$SCRIPTS_DIR/presentation_job/pipeline_interp.py" ]; then
        ( cd "$SCRIPTS_DIR" && python3 -m presentation_job.pipeline_interp --check-readiness --scheduler intake-poll --recorded "${PRESENTATION_PIPELINE_INTERPRETER:-}" --runs-root "$RUNS_ROOT" 2>&1 ) | while IFS= read -r _rline; do
            if [ -n "$_rline" ]; then log "  $_rline"; fi
        done
    fi
    return 0
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

# PRES-035: pin the interpreter now that SCRIPTS_DIR, the env store and
# RUNS_ROOT all exist. Refusing the tick here (rather than running helpers
# under an unknown python) is the fail-closed choice: a schedule that
# cannot prove its interpreter proves nothing else either.
_pres35_init_interpreter || true
_pres35_finish_interpreter || { log "scan aborted: no validated pipeline interpreter"; exit 2; }

# ---------------------------------------------------------------------------
# LAUNCH ACCOUNTING -- the counters must report what HAPPENED, not what was
# ATTEMPTED.
#
# THE DEFECT THIS CLOSES: NEW_LAUNCHES was incremented unconditionally after
# each dispatch, so a pass that logged
#   launcher: REFUSING to dispatch <run> -- AF-NOTIFY-UNCONFIGURED: ...
# twice ALSO logged "scan complete: 2 launched". A run that never started
# read as started. That is how the 5,948-refusal outage above went unnoticed
# for a day: the only summary line the operator sees was reporting success.
#
# A dispatch now increments NEW_LAUNCHES only when the dispatching command
# actually EXITED 0; anything else increments REFUSED_DISPATCH and says so.
# The launcher's exit status is read with ${PIPESTATUS[0]} because every
# dispatch is piped into the log loop, and a pipeline's own `$?` is the
# LOOP's status, not the launcher's -- reading `$?` there is what made the
# refusal invisible in the first place.
#
# SKIPPED_RUNNING and SKIPPED_NO_INTAKE were declared here and emitted in the
# telemetry event but NEVER incremented anywhere -- they reported a hard 0 on
# every scan no matter what was skipped. That is the same defect (a counter
# that cannot be right) in a quieter place, so they are wired to their real
# `continue` sites below. SKIPPED_TERMINAL and RUN_DIRS_SEEN are added so the
# accounting TALLIES: seen == launched + refused + every skip.
# ---------------------------------------------------------------------------
NEW_LAUNCHES=0
REFUSED_DISPATCH=0
SKIPPED_RUNNING=0
SKIPPED_NO_INTAKE=0
SKIPPED_TERMINAL=0
SKIPPED_LEASE_HELD=0
# F4: a run dir whose intake ledger ALREADY refused to resolve, with that
# ledger byte-for-byte unchanged since the refusal. Its own counter, because
# it is neither a refusal this tick (nothing was attempted) nor a terminal
# run (nothing ever started) -- and because folding it into REFUSED_DISPATCH
# is exactly how three dirs that have been unresolvable since 2026-08-07
# manufactured a fresh "refusal" every five minutes forever.
SKIPPED_REFUSED_STICKY=0
LEASE_TAKEOVERS=0
RUN_DIRS_SEEN=0
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

# ---------------------------------------------------------------------------
# F3 -- A LAUNCH IS A RUNNING ENGINE, NOT A SUCCESSFUL SPAWN.
#
# THE DEFECT THIS CLOSES (measured on the operator Mac, 2026-09-06, ticks at
# 13:40, 13:45 and 13:50): the resume branch counted NEW_LAUNCHES whenever
# the dispatching command EXITED 0. launcher.dispatch() returns 0 the instant
# subprocess.Popen() succeeds -- it has proven that the OS accepted a fork,
# nothing more. The two engines it forked each died about one second later on
# EXIT_MANIFEST_MISMATCH (state's pinned manifest sha vs the shipped v67), so
# the very same two run dirs were re-spawned every five minutes for days
# while the only line an operator reads said, every time:
#
#     scan complete: 2 launched, 0 refused
#
# Two one-second deaths, reported as two launches. The previous accounting
# fix made a REFUSAL countable; this one makes a LAUNCH provable. They are
# different lies: one about what the launcher said, one about what the
# machine did.
#
# WHAT COUNTS AS PROOF. After a rc-0 dispatch, an engine is counted only when
# BOTH hold, re-checked once a second until they do or the settle window
# expires:
#
#   (A) a recorded engine pid is ALIVE -- state.json engine_pid first (where
#       launcher._record_engine_pid puts it), then the run_dir/.engine.pid
#       sidecar it uses before state.json exists (launcher._engine_pid_sidecar
#       -- NOTE: at the RUN DIR ROOT, not under working/), then .job.lock's
#       own first field. This is the leg that bites: a manifest-pin death
#       leaves a dead pid within a second.
#
#   (B) the run's .job.lock shows an engine actually TOOK the run -- either
#       its mtime advanced past the baseline captured immediately before the
#       dispatch, or it names the very pid proven alive in (A).
#       state.RunLock.__enter__ truncates and rewrites "<pid> <timestamp>"
#       into that file the moment a run starts, so both readings are the same
#       claim. The "or names the pid" arm exists because the launcher itself
#       takes .job.lock (FIX 27's _merge_run_state_field) while recording the
#       engine pid, so a bare mtime comparison is not by itself decisive --
#       and because a 1-second stat granularity can otherwise lose the bump.
#       A lock naming a live engine is STRONGER evidence than a bumped mtime,
#       never weaker, so this widening cannot manufacture a false launch.
#
# Anything else is REFUSED_DISPATCH, said out loud, with the last 3 lines of
# working/logs/engine-stderr.log -- which is where the manifest-mismatch
# FATAL actually landed while the summary line claimed success.
#
# WHY BOTH, AND WHY NOT MORE. RunLock is entered BEFORE the manifest sha
# check in __main__.main, so a pin death advances the lock but kills the pid:
# (B) alone would have counted those two deaths as launches all over again.
# (A) alone is nearly enough -- (B) is what distinguishes "a process is
# alive" from "an engine owns this run".
#
# ROLLBACK: PRESENTATION_LAUNCH_VERIFY=0 restores the pre-F3 accounting
# (rc 0 == launched). PRESENTATION_LAUNCH_VERIFY_S sets the settle window in
# whole seconds (default 8); the check short-circuits the moment both legs
# hold, so a healthy launch costs no wall clock at all and only a FAILED
# dispatch pays the full window.
#
# The helpers between the two markers below are extracted VERBATIM by
# tests/test_f3f4_poller_truth.py, tests/test_poller_launch_accounting.py and
# tests/test_fix37_poller_counter.py, whose harnesses execute this script's
# real walk-loop body. Keep them self-contained -- they may read no variable
# this block does not itself declare.
# >>> POLLER-LAUNCH-VERIFY-BEGIN
LAUNCH_VERIFY_ENABLED="${PRESENTATION_LAUNCH_VERIFY:-1}"
LAUNCH_VERIFY_S="${PRESENTATION_LAUNCH_VERIFY_S:-8}"
case "$LAUNCH_VERIFY_S" in ''|*[!0-9]*) LAUNCH_VERIFY_S=8 ;; esac
# Baseline .job.lock mtime, taken immediately BEFORE each dispatch. Declared
# here so `set -u` has it on every path.
LOCK_MTIME_BEFORE=0
# verify_engine_running's finding, read by the caller on the line right
# after the call. Always a full sentence naming what was and was not checked,
# so a refusal in the log carries its own evidence instead of a bare verdict.
VERIFY_WHY=""

# file_mtime <path> -- epoch seconds, or 0 when absent/unreadable. BSD stat
# (`-f %m`, macOS) first, GNU stat (`-c %Y`, Linux/VPS) second; each result is
# validated as digits so the wrong stat's output can never be mistaken for a
# timestamp (GNU `stat -f %m file` prints a MOUNT POINT, not a number).
file_mtime() {
    local out=""
    if [ ! -e "$1" ]; then printf '0'; return 0; fi
    out="$(stat -f '%m' "$1" 2>/dev/null)" || out=""
    case "$out" in ''|*[!0-9]*) out="$(stat -c '%Y' "$1" 2>/dev/null)" || out="" ;; esac
    case "$out" in ''|*[!0-9]*) out=0 ;; esac
    printf '%s' "$out"
}

# read_engine_pid <run_dir> -- the pid an engine was recorded under, or "".
# Same three sources launcher._read_engine_pid consults, in the same order,
# plus .job.lock last (state.RunLock writes "<pid> <timestamp>" there). The
# sidecar and lock legs are pure shell on purpose: they must still work when
# the interpreter is the very thing that failed to start.
read_engine_pid() {
    local run_dir="$1" pid=""
    pid="$(python3 -c 'import json,sys
try:
    print(json.load(open(sys.argv[1] + "/state.json")).get("engine_pid", "") or "")
except Exception:
    print("")' "$run_dir" 2>/dev/null)"
    case "$pid" in ''|*[!0-9]*) pid="" ;; esac
    if [ -z "$pid" ] && [ -f "$run_dir/.engine.pid" ]; then
        pid="$(head -n 1 "$run_dir/.engine.pid" 2>/dev/null | tr -d '[:space:]')"
        case "$pid" in ''|*[!0-9]*) pid="" ;; esac
    fi
    if [ -z "$pid" ] && [ -f "$run_dir/.job.lock" ]; then
        pid="$(awk 'NR==1{print $1}' "$run_dir/.job.lock" 2>/dev/null)"
        case "$pid" in ''|*[!0-9]*) pid="" ;; esac
    fi
    printf '%s' "$pid"
}

# engine_stderr_tail <run_dir> -- the last 3 lines of the engine's own stderr,
# into this log, at the moment a dispatch is declared NOT LAUNCHED. Says so
# explicitly when there is no such file: an absent log is a fact about the
# evidence, never evidence that nothing went wrong.
engine_stderr_tail() {
    local err="$1/working/logs/engine-stderr.log"
    if [ -f "$err" ]; then
        tail -n 3 "$err" 2>/dev/null | while IFS= read -r _err_line; do
            log "    [engine-stderr] $_err_line"
        done
    else
        log "    [engine-stderr] no $err on disk -- the engine either wrote no stderr or never got far enough to open it"
    fi
}

# verify_engine_running <run_dir> <lock_mtime_before> -- 0 when an engine is
# provably RUNNING for this run dir, 1 otherwise. Sets VERIFY_WHY either way.
verify_engine_running() {
    local run_dir="$1" baseline="$2" waited=0 pid="" now="" lockpid=""
    VERIFY_WHY=""
    if [ "$LAUNCH_VERIFY_ENABLED" != "1" ]; then
        VERIFY_WHY="running-engine verification is DISABLED (PRESENTATION_LAUNCH_VERIFY=0) -- this is the pre-F3 accounting: a rc-0 dispatch is counted as a launch WITHOUT proof that anything is running"
        return 0
    fi
    while : ; do
        pid="$(read_engine_pid "$run_dir")"
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            if [ -f "$run_dir/.job.lock" ]; then
                now="$(file_mtime "$run_dir/.job.lock")"
                if [ "$now" -gt "$baseline" ]; then
                    VERIFY_WHY="engine pid $pid is alive and .job.lock advanced ($baseline -> $now)"
                    return 0
                fi
                lockpid="$(awk 'NR==1{print $1}' "$run_dir/.job.lock" 2>/dev/null)"
                if [ -n "$lockpid" ] && [ "$lockpid" = "$pid" ]; then
                    VERIFY_WHY="engine pid $pid is alive and holds .job.lock"
                    return 0
                fi
                VERIFY_WHY="pid $pid is alive but .job.lock neither advanced past $baseline nor names it (lock pid: ${lockpid:-none}) -- no engine has taken this run"
            else
                VERIFY_WHY="pid $pid is alive but $run_dir/.job.lock does not exist -- no engine has taken this run"
            fi
        elif [ -n "$pid" ]; then
            VERIFY_WHY="the recorded engine pid $pid is NOT alive"
        else
            VERIFY_WHY="no engine pid was recorded at all (state.json engine_pid, $run_dir/.engine.pid and $run_dir/.job.lock are all empty or absent)"
        fi
        if [ "$waited" -ge "$LAUNCH_VERIFY_S" ]; then
            break
        fi
        sleep 1
        waited=$((waited + 1))
    done
    return 1
}

# ledger_sha256 <path> -- the intake ledger's content hash, or "". shasum
# (macOS) then sha256sum (Linux/VPS); each answer validated as HEXADECIMAL,
# so a missing tool or an error message yields "" (UNDETERMINED) rather than a
# bogus digest -- and the caller treats "" as "cannot compare", never as a
# match, so an unhashable ledger is retried rather than silently stickied.
ledger_sha256() {
    local out=""
    out="$(shasum -a 256 "$1" 2>/dev/null | awk 'NR==1{print $1}')" || out=""
    case "$out" in ''|*[!0-9a-f]*) out="$(sha256sum "$1" 2>/dev/null | awk 'NR==1{print $1}')" || out="" ;; esac
    case "$out" in ''|*[!0-9a-f]*) out="" ;; esac
    printf '%s' "$out"
}
# auto_resume_refund <run_dir> <was_auto> <why> -- F1. Give back the attempt
# just charged, because no engine started.
#
# presentation_job.auto_resume allows at most three automatic resumes per run
# per rolling day and records the attempt BEFORE the dispatch (the engine
# clears state["blocked"] the moment it starts, so a row written afterwards
# could not name the park it was answering). That ordering is right, and it
# means an attempt can be charged for a dispatch that then produced nothing:
# the launcher refuses (AF-NOTIFY-UNCONFIGURED, a capacity autofail, the
# credit preflight), or it exits 0 and verify_engine_running above comes back
# negative. Charging those lets ONE curable environment fault burn the whole
# budget in forty minutes and leave a healthy deck parked with no retries --
# for a reason that has nothing to do with the deck.
#
# So both NOT-LAUNCHED arms of the resume branch call this. It is bookkeeping,
# not a decision: it can only ever REMOVE a charge, it marks at most one row,
# and it always returns 0 -- a failed refund must never become a second
# failure in a log that is already reporting the first.
#
# $2 is the "did WE auto-resume this tick?" flag. A human-initiated resume, or
# a run that was never BLOCKED, has no attempt to give back and this is a
# no-op for it. Reads $SCRIPTS_DIR and calls log(), both of which every
# harness that executes the walk body already declares.
auto_resume_refund() {
    local run_dir="$1" was_auto="$2" why="$3"
    if [ "$was_auto" != "1" ]; then
        return 0
    fi
    ( cd "$SCRIPTS_DIR" && python3 -m presentation_job.auto_resume --run-dir "$run_dir" --refund "$why" 2>&1 ) | while IFS= read -r refund_line; do
        if [ -n "$refund_line" ]; then log "  $refund_line"; fi
    done
    return 0
}
# <<< POLLER-LAUNCH-VERIFY-END

# ---------------------------------------------------------------------------
# F4 -- the walk must not descend into the PARK SHELF.
#
# `find "$RUNS_ROOT" -maxdepth 2 -type d -name "pres-*"` walks TWO levels, so
# it finds $RUNS_ROOT/pres-<slug> (a real run) AND $RUNS_ROOT/_parked/pres-<slug>
# (a run a human deliberately shelved). The shelf is exactly the place whose
# contents must never be dispatched again, and the poller was reading it as
# just another run dir.
#
# `-not -path "$RUNS_ROOT/_*"` prunes every entry under any underscore-prefixed
# child of the runs root -- _parked/, _archive/, _retired/ -- at both depths.
#
# NOTE, deliberate deviation from the fix spec, which proposed the pattern
# `*/_*/*`: that one is anchored to NOTHING, so it also matches a legitimate
# run whose RUNS_ROOT happens to contain an underscore component (a scratch
# root under /tmp/pytest-of-.../test_x_0/, say). Anchoring the pattern to
# $RUNS_ROOT makes it mean what it says -- "an underscore directory INSIDE the
# runs root" -- and cannot silently swallow the real runs of a box whose paths
# are shaped differently. If $RUNS_ROOT itself contains a find glob character
# ([ ? *) the pattern simply stops matching and the walk is as wide as it was
# before: this filter can lose a park, never a live deck.
# ---------------------------------------------------------------------------

# Walk every run directory under $RUNS_ROOT.
while IFS= read -r run_dir; do
    RUN_DIRS_SEEN=$((RUN_DIRS_SEEN + 1))
    INTAKE_LEDGER="$run_dir/working/interview/intake_ledger.json"
    STATE_JSON="$run_dir/state.json"

    # Must have a completed intake ledger
    if [ ! -f "$INTAKE_LEDGER" ]; then
        SKIPPED_NO_INTAKE=$((SKIPPED_NO_INTAKE + 1))
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
        SKIPPED_NO_INTAKE=$((SKIPPED_NO_INTAKE + 1))
        continue
    fi

    # -----------------------------------------------------------------------
    # F4 -- REMEMBER A REFUSAL. The --new branch below refuses a run dir whose
    # intake ledger does not resolve to a legal presentation_type
    # (AF-DECK-TYPE-UNKNOWN). Nothing remembered that, so the identical
    # resolve was re-attempted every five minutes forever: three run dirs on
    # the operator Mac have been failing that way since 2026-08-07, and every
    # tick they contribute a fresh "refused" to a summary line an operator is
    # supposed to be able to read as news.
    #
    # A refusal is now written to working/.poller-refused.json together with
    # the sha256 of the ledger that caused it. While that ledger is
    # byte-for-byte unchanged, the answer is known and this dir is skipped
    # (counted, never silent). The MOMENT the ledger changes -- a human fixed
    # the deck type -- the sha differs, the memo is deleted, and the run dir
    # is retried on that very tick. The memory is therefore self-clearing: it
    # can delay nothing except a repetition of an answer already obtained.
    #
    # Guarded on `[ ! -f "$STATE_JSON" ]` because the memo is about the --new
    # path only. If a state.json appears later (a human ran the canonical
    # entry door by hand), that run has a job and belongs on the RESUME path;
    # a stale memo must never suppress a real resume.
    # -----------------------------------------------------------------------
    POLLER_REFUSED_JSON="$run_dir/working/.poller-refused.json"
    if [ ! -f "$STATE_JSON" ] && [ -f "$POLLER_REFUSED_JSON" ]; then
        REFUSED_LEDGER_SHA="$(sed -n 's/.*"ledger_sha256"[[:space:]]*:[[:space:]]*"\([0-9a-f]*\)".*/\1/p' "$POLLER_REFUSED_JSON" 2>/dev/null | head -n 1)"
        CURRENT_LEDGER_SHA="$(ledger_sha256 "$INTAKE_LEDGER")"
        if [ -n "$REFUSED_LEDGER_SHA" ] && [ -n "$CURRENT_LEDGER_SHA" ] && \
           [ "$REFUSED_LEDGER_SHA" = "$CURRENT_LEDGER_SHA" ]; then
            log "  skipping $run_dir: its intake ledger already failed to resolve and is UNCHANGED since (sha256 $CURRENT_LEDGER_SHA). See $POLLER_REFUSED_JSON for the reason. This dir is retried the moment the ledger changes -- re-running the same failing resolve every 5 minutes proves nothing."
            SKIPPED_REFUSED_STICKY=$((SKIPPED_REFUSED_STICKY + 1))
            continue
        fi
        log "  $run_dir was refused before, but its intake ledger has CHANGED since (was ${REFUSED_LEDGER_SHA:-UNDETERMINED}, now ${CURRENT_LEDGER_SHA:-UNDETERMINED}) -- clearing the refusal memo and retrying"
        rm -f "$POLLER_REFUSED_JSON"
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
        # F4: ABANDONED is the third of the department's terminal values --
        # the sanctioned retirement marker (FAULT #11). supervisor.py has
        # skipped ("DONE", "BLOCKED", "ABANDONED") since it was written; this
        # poller and cc_board._dispatch_engine_if_idle knew only two of the
        # three, so a run a human had explicitly retired was still a resume
        # candidate here every five minutes. Retiring a run must actually
        # retire it, in every actor that can start an engine.
        #
        # F1 SPLITS THE THREE. DONE and ABANDONED are ENDINGS -- one finished,
        # one a human deliberately retired -- and neither is ever restarted by
        # anything. BLOCKED is NOT an ending: it is a PARK, and the whole point
        # of a park is that the run is resumable. It used to be skipped here
        # with the other two, which is why nothing in this system could resume
        # a parked run: not this poller, not supervisor.supervise() (skips
        # DONE|BLOCKED|ABANDONED), not cc_board._dispatch_engine_if_idle, not
        # the watchdog (report-only). One measured run cost 22 h 14 min and 21
        # HUMAN --resume commands to reach 37 of 38 phases; nine of those 21
        # passed on the very next try, transient failures nothing retried.
        #
        # So BLOCKED now falls THROUGH this test and is decided further down,
        # by presentation_job.auto_resume, after the already-running check and
        # after the dispatch lease -- see the F1 block below. It is decided
        # there and not here on purpose: a run that parked seconds ago may
        # still have a live engine winding down (`_block` sets terminal=BLOCKED
        # from inside the engine), and spending one of three daily attempts on
        # a dir this tick was going to skip anyway is exactly the kind of
        # quiet leak that makes a bound not a bound.
        if [ "$TERMINAL" = "DONE" ] || [ "$TERMINAL" = "ABANDONED" ]; then
            # Finished, or retired by a human. Neither is ever restarted.
            SKIPPED_TERMINAL=$((SKIPPED_TERMINAL + 1))
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
            SKIPPED_RUNNING=$((SKIPPED_RUNNING + 1))
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
        # -------------------------------------------------------------------
        # F1 -- BOUNDED AUTO-RESUME OF A PARKED RUN.
        #
        # This is the branch that used to read `TERMINAL = BLOCKED -> continue`
        # ("Already finished or parked -- skip"). A BLOCKED run now gets a
        # DECISION instead of a shrug, and the decision is made by
        # presentation_job.auto_resume, never here: the bounds (class, phase,
        # cap, backoff) are code with tests, not shell.
        #
        #   exit 0 -> RESUME. An attempt has been RECORDED in state.json
        #             (state["auto_resume"]) BEFORE we get here, so the count
        #             cannot be lost by the dispatch that follows. The resume
        #             then goes through the EXISTING launcher line below --
        #             this file still has exactly one engine dispatcher.
        #   exit 3 -> decided NOT to resume (owner decision, a close-time gate,
        #             the cap, or backoff). Counted as SKIPPED_TERMINAL, which
        #             is what it is: a parked run this tick left parked.
        #   exit 4 -> UNDETERMINED (state.json unreadable, or the manifest pin
        #             moved and this tree has no auto-repin to cure it, so the
        #             resume would die EXIT_MANIFEST_MISMATCH in one second and
        #             burn an attempt for nothing). Also SKIPPED_TERMINAL.
        #   any other non-zero (module missing on a box that has not taken the
        #             scripts refresh, a traceback) -> skip. FAIL-CLOSED: the
        #             pre-F1 behaviour is the failure mode, never a resume.
        #
        # Every line the decider prints goes into this log, because a bare
        # "skipped" tells an operator nothing and the reason IS the evidence.
        # -------------------------------------------------------------------
        # Declared on every iteration, BEFORE the branch that may set it, so
        # `set -u` has it on every path where no auto-resume happened.
        AUTO_RESUMED=0
        if [ "$TERMINAL" = "BLOCKED" ]; then
            AUTO_RESUME_OUT="$( cd "$SCRIPTS_DIR" && python3 -m presentation_job.auto_resume --run-dir "$run_dir" 2>&1 )"
            AUTO_RESUME_RC=$?
            printf '%s\n' "$AUTO_RESUME_OUT" | while IFS= read -r auto_resume_line; do
                if [ -n "$auto_resume_line" ]; then log "  $auto_resume_line"; fi
            done
            if [ "$AUTO_RESUME_RC" -ne 0 ]; then
                log "  parked run LEFT PARKED (auto-resume exit $AUTO_RESUME_RC) -- see the reason above. Counted as terminal, never as a refusal: nothing went wrong this tick."
                SKIPPED_TERMINAL=$((SKIPPED_TERMINAL + 1))
                if [ "$LEASE_ENABLED" = "1" ]; then
                    lease_release "$run_dir"
                fi
                continue
            fi
            AUTO_RESUMED=1
            log "  parked run AUTHORISED for automatic resume -- dispatching through the same launcher line every resume uses"
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
        #
        # F3: the baseline for leg (B) of the running-engine proof, taken
        # immediately BEFORE the dispatch so "advanced" means "advanced
        # because of THIS dispatch". A resume nearly always finds an old
        # .job.lock already on disk from the run's previous life.
        LOCK_MTIME_BEFORE="$(file_mtime "$run_dir/.job.lock")"
        log "resuming parked job: $run_dir"
        ( cd "$SCRIPTS_DIR" && python3 -m presentation_job.launcher --resume --run-dir "$run_dir" ${RUN_MODE:+--mode "$RUN_MODE"} ) 2>&1 | while IFS= read -r line; do
            log "  $line"
        done
        # LAUNCH ACCOUNTING: the launcher's OWN exit status, taken from
        # PIPESTATUS[0] -- `$?` here is the log loop's status (always 0), which
        # is precisely why a refusal used to be counted as a launch. The
        # launcher exits non-zero when it REFUSES to dispatch (notify_gate's
        # EXIT_NOTIFY_UNCONFIGURED=8 / AF-NOTIFY-UNCONFIGURED, the capacity
        # autofails, a missing state.json). No engine started; do not claim one.
        # F3: rc 0 is now the ENTRY condition, not the verdict. The launcher
        # returns 0 the moment Popen() succeeds; the engine it forked may
        # already be dead (EXIT_MANIFEST_MISMATCH takes about one second).
        # verify_engine_running is what turns "a fork was accepted" into "an
        # engine owns this run".
        DISPATCH_RC=${PIPESTATUS[0]}
        if [ "$DISPATCH_RC" -eq 0 ]; then
            if verify_engine_running "$run_dir" "$LOCK_MTIME_BEFORE"; then
                log "  LAUNCHED: $VERIFY_WHY"
                NEW_LAUNCHES=$((NEW_LAUNCHES + 1))
            else
                log "  NOT LAUNCHED: the launcher exited 0 but no engine is RUNNING for $run_dir after ${LAUNCH_VERIFY_S}s -- $VERIFY_WHY. A spawn that dies is not a launch. Counted as REFUSED, never as a launch."
                engine_stderr_tail "$run_dir"
                REFUSED_DISPATCH=$((REFUSED_DISPATCH + 1))
                auto_resume_refund "$run_dir" "$AUTO_RESUMED" "the launcher exited 0 but no engine was running: $VERIFY_WHY"
            fi
        else
            REFUSED_DISPATCH=$((REFUSED_DISPATCH + 1))
            log "  NOT LAUNCHED: the launcher refused this resume dispatch (exit $DISPATCH_RC) -- see the launcher lines above for the reason. Counted as REFUSED, never as a launch."
            auto_resume_refund "$run_dir" "$AUTO_RESUMED" "the launcher refused the dispatch (exit $DISPATCH_RC)"
        fi
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
            # LAUNCH ACCOUNTING: this was the one `continue` in the whole walk
            # that incremented NOTHING -- a dispatch that produced no engine,
            # invisible in every counter and in the telemetry event. It is
            # precisely the case the comment above describes ("retried the
            # identical failure every 5 minutes, forever"), so it is exactly
            # the case that must be countable.
            # F4: REMEMBER this refusal, keyed to the exact ledger that caused
            # it, so the next tick does not re-run an identical resolve and
            # manufacture an identical refusal. Read back at the top of the
            # walk (see the refusal-memo block there). Best-effort: if the
            # memo cannot be written the poller simply behaves as it did
            # before -- a memo is an optimisation over a known answer, never
            # a gate on a client's deck.
            #
            # Written BEFORE the counter below on purpose: the accounting
            # guard (tests/test_poller_launch_accounting.py) requires every
            # `continue` in this walk to have its counter within a few lines,
            # so that a run dir can never leave the loop unreported. Inserting
            # this block between the increment and the `continue` pushed the
            # counter out of that window -- the gate caught it, and the fix is
            # to keep the increment adjacent to the exit, not to widen the gate.
            POLLER_REFUSAL_SHA="$(ledger_sha256 "$INTAKE_LEDGER")"
            POLLER_REFUSAL_REASON="$(printf '%s' "$RESOLVE_OUT" | tr '\n\r\t' '   ' | tr -d '"\\' | cut -c1-400)"
            mkdir -p "$run_dir/working" 2>/dev/null
            if printf '{\n  "reason": "%s",\n  "ledger_sha256": "%s",\n  "ledger_path": "%s",\n  "recorded_at": "%s",\n  "recorded_by": "presentation-intake-poll.sh"\n}\n' \
                "$POLLER_REFUSAL_REASON" "$POLLER_REFUSAL_SHA" "$INTAKE_LEDGER" \
                "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
                > "$run_dir/working/.poller-refused.json" 2>/dev/null; then
                log "  recorded the refusal in $run_dir/working/.poller-refused.json (ledger sha256 ${POLLER_REFUSAL_SHA:-UNDETERMINED}) -- this dir is skipped until that ledger changes"
            else
                log "  WARNING: could not record the refusal memo at $run_dir/working/.poller-refused.json -- this dir will be retried (and refused) again next tick"
            fi
            REFUSED_DISPATCH=$((REFUSED_DISPATCH + 1))
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
        # LAUNCH ACCOUNTING (see the resume branch): the ENGINE's own exit
        # status, not the log loop's. A --new that fails leaves no job to run.
        CREATE_RC=${PIPESTATUS[0]}

        if [ "$CREATE_RC" -ne 0 ]; then
            log "  NOT LAUNCHED: engine --new exited $CREATE_RC for $run_dir -- no job was created. Counted as REFUSED, never as a launch."
            REFUSED_DISPATCH=$((REFUSED_DISPATCH + 1))
        elif [ -f "$run_dir/state.json" ]; then
            # Engine job created -- now launch the run (background).
            # We use Python subprocess here because poll.sh itself must return quickly.
            #
            # F3: baseline for leg (B) of the running-engine proof, taken
            # BEFORE the spawner. A brand-new run dir normally has no
            # .job.lock at all, so this is 0 and any lock at all is an advance.
            LOCK_MTIME_BEFORE="$(file_mtime "$run_dir/.job.lock")"
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
            # LAUNCH ACCOUNTING: the spawner's own exit status. It exits
            # non-zero when Popen could not start the engine at all -- in that
            # case nothing is running and nothing may be counted as running.
            # F3: same treatment as the resume branch. Popen() succeeding is
            # not an engine running -- the fresh run's first act is to load
            # the manifest and take .job.lock, and it can die doing either.
            RUN_RC=${PIPESTATUS[0]}
            if [ "$RUN_RC" -eq 0 ]; then
                if verify_engine_running "$run_dir" "$LOCK_MTIME_BEFORE"; then
                    log "  LAUNCHED: $VERIFY_WHY"
                    NEW_LAUNCHES=$((NEW_LAUNCHES + 1))
                else
                    log "  NOT LAUNCHED: the engine spawner exited 0 but no engine is RUNNING for $run_dir after ${LAUNCH_VERIFY_S}s -- $VERIFY_WHY. A spawn that dies is not a launch. Counted as REFUSED, never as a launch."
                    engine_stderr_tail "$run_dir"
                    REFUSED_DISPATCH=$((REFUSED_DISPATCH + 1))
                fi
            else
                log "  NOT LAUNCHED: the engine spawner exited $RUN_RC for $run_dir -- no engine process was started. Counted as REFUSED, never as a launch."
                REFUSED_DISPATCH=$((REFUSED_DISPATCH + 1))
            fi
        else
            log "  NOT LAUNCHED: engine --new exited 0 but state.json was not written for $run_dir -- engine not launched. Counted as REFUSED, never as a launch."
            REFUSED_DISPATCH=$((REFUSED_DISPATCH + 1))
        fi
        # FIX 61: dispatch window is over (engine spawned and holds .job.lock,
        # or no engine exists because --new failed). Release the lease either
        # way -- an engine now owns the run; a dead dispatch must not leave a
        # lease that blocks the next tick's retry.
        if [ "$LEASE_ENABLED" = "1" ]; then
            lease_release "$run_dir"
        fi
    fi
done < <(find "$RUNS_ROOT" -maxdepth 2 -type d -name "pres-*" -not -path "$RUNS_ROOT/_*" 2>/dev/null)

# FIX 37: emit poller-telemetry event (consuming FIX 5 telemetry infra)
# FIX 61: the event now also carries the lease counters (skipped_lease_held,
# lease_takeovers) so a tick that was throttled by another actor is visible
# in the telemetry stream, not only in poll.log.
TELEMETRY_DIR="${PRESENTATION_RUNS_DIR:-${HOME}/.openclaw/workspace/departments/Presentations}/telemetry"
mkdir -p "$TELEMETRY_DIR"
# LAUNCH ACCOUNTING: `refused` is new and is the number that makes this event
# honest -- a scan that refused every dispatch used to emit the SAME event as
# a scan that launched them. `run_dirs_seen` closes the tally: it must equal
# new_launches + refused + every skipped_* count, so a missing increment is
# arithmetically visible instead of silently under-reported. The keys that
# already existed keep their names and meanings; nothing was removed.
# F3: `new_launches` now means "an engine was proven RUNNING", not "a spawn
# was accepted", so this stream changes meaning without changing shape -- a
# consumer comparing today's numbers with last week's is comparing a proof
# with a claim. F4 adds `skipped_refused_sticky`, which keeps the tally
# closed: seen == launched + refused + every skipped_* count.
printf '{"event":"poller_scan","generated_at":"%s","new_launches":%d,"refused":%d,"skipped_running":%d,"skipped_no_intake":%d,"skipped_terminal":%d,"skipped_lease_held":%d,"skipped_refused_sticky":%d,"lease_takeovers":%d,"run_dirs_seen":%d}\n'     "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$NEW_LAUNCHES" "$REFUSED_DISPATCH" "$SKIPPED_RUNNING" "$SKIPPED_NO_INTAKE" "$SKIPPED_TERMINAL" "$SKIPPED_LEASE_HELD" "$SKIPPED_REFUSED_STICKY" "$LEASE_TAKEOVERS" "$RUN_DIRS_SEEN"     >> "$TELEMETRY_DIR/events.jsonl"

log "scan complete: $NEW_LAUNCHES launched, $REFUSED_DISPATCH refused ($SKIPPED_RUNNING skipped already-running, $SKIPPED_NO_INTAKE skipped no-completed-intake, $SKIPPED_TERMINAL skipped terminal, $SKIPPED_LEASE_HELD skipped on lease, $SKIPPED_REFUSED_STICKY skipped on an unchanged refused ledger, $LEASE_TAKEOVERS lease takeovers, $RUN_DIRS_SEEN run dirs seen)"
exit 0
