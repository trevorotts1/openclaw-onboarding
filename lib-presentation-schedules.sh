#!/usr/bin/env bash
# ============================================================
# lib-presentation-schedules.sh — shared Presentations SCHEDULER installers
# ------------------------------------------------------------
# F12 (a + b). SINGLE canonical definition of the two schedulers the
# Presentations department needs to run without a human:
#
#   install_intake_poll_schedule()  — FIX 61's intake-completion poll (5 min).
#                                     MOVED here VERBATIM from install.sh; it
#                                     was previously defined inline there and
#                                     was therefore unreachable from
#                                     update-skills.sh.
#   install_watchdog_schedule()     — NEW. presentation-watchdog.sh (10 min),
#                                     which carries the stall watchdog, the
#                                     board reconcile, the SUPERVISOR
#                                     (worker-liveness restart) and
#                                     run-discovery passes.
#   install_presentation_schedules()— calls both; the one entry point a roll
#                                     needs.
#
# WHY THIS FILE EXISTS (measured on this repo at v25.0.11 / ea331f82a, with
# python3 str.count over the full file text — not grep):
#   install.sh        'presentation-watchdog' 0   'supervisor' 0
#                     CONTROL 'presentation-intake-poll' 25 (same instrument,
#                     same file, non-empty — the check is not broken)
#   update-skills.sh  'presentation-watchdog' 0   'presentation-intake-poll' 0
#                     CONTROL 'watchdog' 2, 'supervise' 1 (non-empty)
# So: no client box has ever had the watchdog or the supervisor SCHEDULED by
# an install, and a fleet roll could repair NEITHER scheduler. Every stalled
# deck needed a human. That is the whole defect.
#
# NOT DONE HERE — F12c. The supervisor's --apply (restart) mode is NOT armed
# by this installer. presentation-watchdog.sh gates it on
# PRESENTATION_SUPERVISE_APPLY, and arming it before F2 (auto-repin on
# manifest change) is DEPLOYED makes the supervisor's restart a `--resume`
# that dies on the manifest pin, burning its 3-restart budget in ~30 minutes
# and alarming. So:
#   * the renderer arms apply ONLY when the operator sets
#     PRESENTATION_SUPERVISE_APPLY in the INSTALLER's environment, and
#   * an already-armed value in an installed plist is PRESERVED across
#     re-runs (a roll must never disarm what an operator armed, and must
#     never arm what they did not).
# Report-only is the default, exactly as presentation-watchdog.sh ships it.
#
# SOURCED BY: install.sh (fresh install, Step 6.6b) and update-skills.sh
# (every roll, after the department scripts/intake mirrors). Same shape and
# the same reason as lib-onboarding-resume-cron.sh: one definition, no
# copy-paste drift between the install path and the roll path.
#
# DEPENDENCIES, all resolved defensively so the lib works from either caller:
#   step/success/note/warn      — the caller's own richer versions win.
#   oc_cron_present / oc_cron_tombstoned / _oc_cron_silent_main — the caller's
#     win; otherwise shared-utils/cron-lib.sh beside this file is sourced and
#     a minimal fallback fills any remaining gap. update-skills.sh defines its
#     own oc_cron_present only LATER in its run than it calls us, which is
#     precisely why these fallbacks are not optional.
#   $OPENCLAW_PLATFORM ("vps" selects cron, anything else selects launchd),
#   $_SCRIPT_DIR, $OPENCLAW_ROOT/$OC_ROOT/$OC_CONFIG, the OPENCLAW_WORKSPACE_*
#   pins, $TELEGRAM_DEFAULT_AGENT_CACHED and $TELEGRAM_TARGET_CACHED — all
#   optional and all read with `${...:-}` so `set -u` in either caller is safe.
#
# GUARDED BY tests/unit/presentation-schedules-installed.test.sh.
#
# PRES-019 (W2 WF06) — HEALTH-GATED RECOVERY ACTIVATION, explicitly parsed.
#
# THE DEFECT THIS CLOSES. F12c armed the supervisor's --apply (restart) mode
# ONLY when the operator exported PRESENTATION_SUPERVISE_APPLY in the
# installer's own environment, and report-only was the default forever. That
# meant a brand-new box — install.sh run fresh, or any box where the operator
# never set the variable — installed the watchdog with the supervisor pinned
# in report-only: deaths detected, restarts announced, NOTHING restarted.
# A live flock proves process ownership, not useful work; detection without
# recovery is not recovery. At the same time the ONLY consumer of the value
# (presentation-watchdog.sh's ${PRESENTATION_SUPERVISE_APPLY:+--apply})
# treats ANY nonempty string as "armed" — including "0" and "false". So an
# operator who read the docs, set PRESENTATION_SUPERVISE_APPLY=0 to spell out
# what they wanted, got the OPPOSITE of what they asked for, silently.
#
# THE FIX, two halves, both here (the single place every install/roll passes
# through):
#
#   1. EXPLICIT TRUTHINESS. _pres_parse_bool answers exactly one of three
#      things about a value: true (1/true/yes/on, case-insensitive), false
#      (0/false/no/off), or UNPARSEABLE (anything else). The watchdog
#      installer then:
#        - true   -> renders PRESENTATION_SUPERVISE_APPLY=1 into the plist;
#        - false  -> renders NOTHING (and STRIPS a previously rendered
#                    value, so "0" never rides into the launchd environment
#                    to be misread as armed);
#        - absent -> PRES-019's health gate decides (see 2);
#        - garbage-> preserved verbatim and passed through UNCHANGED, with a
#                    warning — an operator's hand-tuned value is never
#                    silently rewritten, and the existing render-time
#                    preservation already carries it across re-runs. The
#                    consumer-side +:- expansion still misreads garbage as
#                    armed; that legacy wart is documented, never worsened:
#                    the installer WARNS that the value is not one it
#                    understands.
#
#   2. HEALTH-GATED DEFAULT. When the operator said nothing, the installer
#      asks the box one question: is RECOVERY READY? The gate is
#      presentation_job/recovery_gate.py beside the materialized scripts —
#      the same module the renderer's shell-branch checks. It proves, in
#      order, the things a restart actually needs:
#        - the entry script exists (presentation_job.py) and is readable;
#        - python3 exists (the restart spawns sys.executable via the entry
#          script's shebang; without python3 every restart is a corpse);
#        - supervisor.py + auto_resume.py + lease.py exist in the package
#          (the recovery machinery itself);
#        - a notify transport resolves (PRESENTATION_NOTIFY_CMD in this
#          process env, or renderable beside the scripts, or the box env
#          store names one) — fail-closed by default exactly as the
#          watchdog's own FIX 22 gate is: a restart nobody can be told
#          about must not fire;
#        - launchd/launchctl on Mac (the schedule is being installed right
#          here — a plist without a working loader arms nothing); cron on
#          VPS is implied by the openclaw CLI the same branch requires.
#      ALL gates pass -> arm PRESENTATION_SUPERVISE_APPLY=1 (recovery is
#      READY, and install is the moment it becomes armed); ANY gate fails ->
#      stay report-only and NAME THE EXACT FAILED GATE in the installer's
#      output, so a box that cannot recover says why instead of failing
#      silently. This is the spec's "proves recovery ready or exposes the
#      exact failed gate".
#
#      The gate is ADVICE to the installer, never a bypass of the operator:
#      an explicit true wins over a failed gate, an explicit false wins over
#      a ready one, and a value already rendered into an installed plist is
#      still preserved across re-runs exactly as F12c built it. Kill
#      switches (PRESENTATION_AUTO_RESUME=0, PRESENTATION_NOTIFY_FAIL_CLOSED,
#      PRESENTATION_SUPERVISE_APPLY=0/false) are env-parsed downstream and
#      untouched here; budget/approval constraints live in supervisor.py's
#      ledger and auto_resume.py's bounds and are never installer business.
#
# PRES-019 ALSO RULES the old comment below wrong in one sentence: with the
# health gate, "report-only is the default" holds only while the box is NOT
# proven recovery-ready — the default on a healthy install is ARMED.
# ============================================================

# Re-source guard.
[ -n "${__PRESENTATION_SCHEDULES_LIB_SOURCED:-}" ] && return 0
__PRESENTATION_SCHEDULES_LIB_SOURCED=1

# ── PRES-019: explicit boolean parsing. No defaults inside the parser: the
#    caller owns "absent" (it is a distinct state — the health gate's call).
#    Only these exact spellings, case-insensitive, are legal: 1 true yes on;
#    0 false no off. Anything else returns rc=2 and echoes the value back —
#    never silently normalized, never silently dropped.
_pres_parse_bool() {
    # $1 = raw value; echoes "1" (true), "0" (false); rc 2 = unparseable
    # (value echoed for the warning), rc 3 = absent (caller decides).
    local _v="${1-}"
    if [ -z "$_v" ]; then
        return 3
    fi
    local _lower
    _lower="$(printf '%s' "$_v" | tr '[:upper:]' '[:lower:]')"
    case "$_lower" in
        1|true|yes|on)  echo "1"; return 0 ;;
        0|false|no|off) echo "0"; return 0 ;;
        *)              echo "$_v"; return 2 ;;
    esac
}

# ── PRES-019: the recovery-readiness health gate. Shell half.
#    Decides whether a FRESH arm (no operator decision, no carried plist
#    value) is safe. Prints one line per failed gate (the exact failed gate,
#    never a bare "not ready") and echoes "1" when every gate passes, "0"
#    otherwise. Read-only: runs no python beyond the gate module itself, and
#    the module is a pure checker (see its docstring) that never spawns,
#    never writes, never loads a credential value.
_pres_recovery_health_gate() {
    # $1 = scripts dir (must hold presentation_job/); $2 = platform
    # ("vps" selects the cron prerequisites, anything else launchd's).
    local _scripts="$1" _platform="${2:-mac}"
    local _ok=1
    local _gate _gate_err _gate_rc _tmperr
    _tmperr="$(mktemp "${TMPDIR:-/tmp}/pres019-gate-err.XXXXXX")" || return 1
    # The module's verdict comes back as JSON on stdout ("ready": true/false)
    # and its failed-gate NAMES go to stderr. The shell needs exactly one
    # word -- "1" or "0" -- so: run the module once with --json, pipe stdout
    # through python3 -c to collapse ready->1/not-ready->0, capture stderr in
    # the temp file for re-emission, and take the PIPELINE's rc via
    # `|| _gate_rc=$?` (a bash pipe's rc is the LAST command's, so the
    # normalizer's failure -- a verdict that is not JSON -- is what surfaces;
    # the module's own NOT-READY rc=1 is harmless because its VERDICT is the
    # "0" it printed, not its exit code). The `|| rc=$?` is the same set -e
    # discipline as the _pres_parse_bool call in install_watchdog_schedule: a
    # bare capture would abort this installer on any non-zero rc, killing
    # install_watchdog_schedule before it renders any plist.
    _gate_rc=0
    _gate="$( { python3 "$_scripts/presentation_job/recovery_gate.py" \
        --scripts-dir "$_scripts" --platform "$_platform" --json \
        2>"$_tmperr" | python3 -c 'import json,sys
try:
    print("1" if json.load(sys.stdin).get("ready") else "0")
except Exception:
    sys.exit(3)'; } 2>/dev/null )" || { _gate_rc=$?; _gate=""; }
    _gate_err="$(cat "$_tmperr" 2>/dev/null)"
    rm -f "$_tmperr"
    if [ -n "$_gate_err" ]; then
        printf '%s\n' "$_gate_err"
    fi
    if [ "$_gate" = "1" ]; then
        # The module RAN and answered READY (rc 0 through the normalizer).
        echo "1"
        return 0
    fi
    if [ "$_gate" = "0" ]; then
        # The module RAN and answered NOT-READY; its failed-gate lines were
        # re-emitted above. Verdict: not ready. (The module's own exit code
        # is 1 here -- its VERDICT is the printed "0", not its rc.)
        echo "0"
        return 0
    fi
    if [ "$_gate_rc" -ne 0 ] || [ -z "$_gate" ]; then
        # The gate module or its normalizer could not produce a verdict --
        # that IS the failed gate. Degrade to the shell checks below rather
        # than fail the whole installer, and say that is what happened.
        # (Anything the module printed before failing was already re-emitted
        # above.)
        echo "PRES-019: recovery_gate.py unavailable or failed (rc=$_gate_rc) -- falling back to shell checks"
        _gate=""
    fi
    # ---- shell fallback (gate module missing): the minimal, order-stable
    #      version of the same question. Each failure NAMES its gate. ----
    if [ ! -f "$_scripts/presentation_job.py" ]; then
        echo "PRES-019 GATE entry-script: $_scripts/presentation_job.py not found"; _ok=0
    fi
    if ! command -v python3 >/dev/null 2>&1; then
        echo "PRES-019 GATE python3: not on PATH"; _ok=0
    fi
    for _req in supervisor auto_resume lease; do
        if [ ! -f "$_scripts/presentation_job/$_req.py" ]; then
            echo "PRES-019 GATE recovery-module: presentation_job/$_req.py not found"; _ok=0
        fi
    done
    unset _req
    if [ ! -f "$_scripts/presentation-notify.py" ] \
       && [ -z "${PRESENTATION_NOTIFY_CMD:-}" ]; then
        echo "PRES-019 GATE notify-transport: no PRESENTATION_NOTIFY_CMD in this environment and no presentation-notify.py beside the scripts -- a restart nobody can be told about must not fire (fail-closed, same rule as the watchdog's own FIX 22 gate)"
        _ok=0
    fi
    if [ "$_platform" = "vps" ]; then
        if ! command -v openclaw >/dev/null 2>&1; then
            echo "PRES-019 GATE openclaw: not on PATH -- the VPS cron branch needs it"; _ok=0
        fi
    else
        if ! command -v launchctl >/dev/null 2>&1; then
            echo "PRES-019 GATE launchctl: not on PATH -- a rendered plist arms nothing without it"; _ok=0
        fi
    fi
    echo "$_ok"
    [ "$_ok" = "1" ]
}

# ── Minimal UI-helper fallbacks (install.sh already defines richer ones; these
#    only fill in for update-skills.sh, which logs with plain echo). Guarded so
#    a caller's own helpers always win. ─────────────────────────────────────────
command -v step    >/dev/null 2>&1 || step()    { echo ""; echo "  $1"; }
command -v success >/dev/null 2>&1 || success() { echo "  ✓ $1"; }
command -v note    >/dev/null 2>&1 || note()    { echo "  ℹ️  $1"; }
command -v warn    >/dev/null 2>&1 || warn()    { echo "  ⚠️  $1"; }

# ── Cron helpers. The VPS branch of BOTH installers below calls
#    oc_cron_tombstoned / oc_cron_present / _oc_cron_silent_main. install.sh
#    defines all three near its top; update-skills.sh defines oc_cron_present
#    only at ~line 8146, which is AFTER the point at which it calls us, and
#    never defines the other two at all. An undefined name there is rc 127 — a
#    shell abort, not a fact about the box — and the VPS branch would report a
#    failed cron install that was really a missing function. So: source the
#    canonical cron lib beside this file, then fill any remaining gap. ────────
if ! command -v oc_cron_present >/dev/null 2>&1 || ! command -v oc_cron_tombstoned >/dev/null 2>&1; then
    _pres_sched_cron_lib="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/shared-utils/cron-lib.sh"
    if [ -f "$_pres_sched_cron_lib" ]; then
        # shellcheck source=/dev/null
        source "$_pres_sched_cron_lib"
    fi
    unset _pres_sched_cron_lib
fi
# Fail-SAFE fallbacks. oc_cron_present returning false makes the installer try
# to register (the registrar itself is the last line of defence against a
# duplicate); oc_cron_tombstoned returning false means "no tombstone found",
# which is the correct reading of "this box has no tombstone directory".
command -v oc_cron_present    >/dev/null 2>&1 || oc_cron_present()    { return 1; }
command -v oc_cron_tombstoned >/dev/null 2>&1 || oc_cron_tombstoned() { return 1; }
# Runtime-compatible SILENT main-session cron helper — identical body to
# install.sh's own guarded copy (fix/cron-flag-skew). Whichever is defined
# first wins; they do the same thing.
#   $1 name  $2 agent  $3 cron-expr  $4 tz  $5 prompt ; $6.. = extra flags
command -v _oc_cron_silent_main >/dev/null 2>&1 || _oc_cron_silent_main() {
    local _name="$1" _agent="$2" _expr="$3" _tz="$4" _prompt="$5"; shift 5
    local _extra=( "$@" ); local _n=${#_extra[@]}
    local _base=( --name "$_name" --agent "$_agent" --cron "$_expr" --tz "$_tz" )
    local _help _modern=0
    _help="$(openclaw cron add --help 2>&1 || true)"
    printf '%s' "$_help" | grep -qE '^[[:space:]]*--session[[:space:]<]' && _modern=1
    local _order _k
    if [ "$_modern" = "1" ]; then _order="modern old"; else _order="old modern"; fi
    for _k in $_order; do
        if [ "$_k" = "modern" ]; then
            [ "$_n" -gt 0 ] && openclaw cron create "${_base[@]}" "${_extra[@]}" --session main --system-event "$_prompt" >/dev/null 2>&1 && return 0
            openclaw cron create "${_base[@]}" --session main --system-event "$_prompt" >/dev/null 2>&1 && return 0
        else
            [ "$_n" -gt 0 ] && openclaw cron create "${_base[@]}" "${_extra[@]}" --session-target main --message "$_prompt" >/dev/null 2>&1 && return 0
            openclaw cron create "${_base[@]}" --session-target main --message "$_prompt" >/dev/null 2>&1 && return 0
        fi
    done
    openclaw cron create "$_expr" "$_prompt" --name "$_name" --agent "$_agent" --tz "$_tz" --session main >/dev/null 2>&1 && return 0
    openclaw cron create "${_base[@]}" --message "$_prompt" --no-deliver >/dev/null 2>&1 && return 0
    return 1
}

# ════════════════════════════════════════════════════════════════════════════
# FIX 61 — the intake-completion poll. MOVED HERE VERBATIM from install.sh
# (it was defined inline at install.sh:4560-4816 and could never be reached
# from update-skills.sh). Nothing below this banner was retyped or edited;
# the only change is its address.
# ════════════════════════════════════════════════════════════════════════════
install_intake_poll_schedule() {
    local _rc=0
    # An EMPTY $PRESENTATIONS_SCRIPTS_SRC is never a usable prefix: it collapses
    # "$PRESENTATIONS_SCRIPTS_SRC/presentation-intake-poll.sh" to the
    # root-anchored literal "/presentation-intake-poll.sh", and the -f test below
    # then reports a MISSING FILE when the real fault is an UNRESOLVED DIRECTORY.
    # That misdirection is exactly what was seen in the field, so the empty
    # prefix is rejected on its own terms, before it is ever concatenated.
    if [ -z "${PRESENTATIONS_SCRIPTS_SRC:-}" ]; then
        warn "FIX 61: PRESENTATIONS_SCRIPTS_SRC is EMPTY — the presentations scripts directory was never resolved (neither the repo checkout nor the materialized department). Intake poll NOT scheduled."
        return 1
    fi
    local POLL_SRC="$PRESENTATIONS_SCRIPTS_SRC/presentation-intake-poll.sh"
    local TPL_SRC="$PRESENTATIONS_SCRIPTS_SRC/presentation-intake-poll.plist.template"

    if [ ! -f "$POLL_SRC" ]; then
        warn "FIX 61: presentation-intake-poll.sh not found at $POLL_SRC — intake poll NOT scheduled. Manual: see the script header."
        return 1
    fi

    local _poll_workspace
    _poll_workspace="$(_fix61_selected_workspace)" || return 1
    local _poll_runs_dir="$_poll_workspace/departments/Presentations/runs"
    local _poll_root="${OPENCLAW_ROOT:-${OC_ROOT:-${OC_CONFIG:-$HOME/.openclaw}}}"
    case "$_poll_root" in /*) ;; *) warn "FIX 61: client root must be absolute." >&2; return 1 ;; esac
    _poll_root="${_poll_root%/}"
    [ -n "$_poll_root" ] || return 1

    if [ "$OPENCLAW_PLATFORM" = "vps" ]; then
        # ── VPS: SILENT main-session openclaw cron, 5-minute cadence ──────────
        if ! command -v openclaw >/dev/null 2>&1; then
            warn "FIX 61: openclaw CLI not on PATH — intake-poll cron NOT registered. Re-run update-skills.sh later."
            return 1
        fi
        if oc_cron_tombstoned "presentation-intake-poll"; then
            warn "presentation-intake-poll is TOMBSTONED (deliberately removed) — NOT re-registering."
            return 0
        fi
        if oc_cron_present "presentation-intake-poll"; then
            success "FIX 61: intake-poll cron already installed — skipping"
            return 0
        fi
        local CHANNEL_AGENT="main"
        if [ -n "${TELEGRAM_DEFAULT_AGENT_CACHED:-}" ]; then
            CHANNEL_AGENT="$TELEGRAM_DEFAULT_AGENT_CACHED"
        fi
        local _poll_command
        printf -v _poll_command 'env OPENCLAW_ROOT=%q OPENCLAW_WORKSPACE_PATH=%q OPENCLAW_WORKSPACE_ROOT=%q PRESENTATION_RUNS_DIR=%q bash %q' "$_poll_root" "$_poll_workspace" "$_poll_workspace" "$_poll_runs_dir" "$POLL_SRC"
        local POLL_PROMPT="[PRESENTATION-INTAKE-POLL] Run the intake-completion poll: $_poll_command . This is an idempotent maintenance scan; it dispatches the deck engine for any intake whose interview completed but whose engine never launched (FIX 61 dispatch lease held during dispatch)."
        if _oc_cron_silent_main "presentation-intake-poll" "$CHANNEL_AGENT" "*/5 * * * *" "America/New_York" "$POLL_PROMPT" --light-context; then
            success "FIX 61: intake-poll cron installed (SILENT main-session, 5-min, no client auto-announce)"
        else
            warn "FIX 61: intake-poll cron creation FAILED — staged intake submissions will sit undispatched. Manual: openclaw cron create --name presentation-intake-poll --agent $CHANNEL_AGENT --cron '*/5 * * * *' --session main --system-event '[PRESENTATION-INTAKE-POLL] bash $POLL_SRC'"
            _rc=1
        fi
    else
        # ── Mac: launchd LaunchAgent from the rendered plist template ─────────
        local PLIST_DIR="$HOME/Library/LaunchAgents"
        local PLIST_DST="$PLIST_DIR/com.blackceo.presentation-intake-poll.plist"
        local LOG_PATH="$HOME/Library/Logs/openclaw/presentation-intake-poll.log"
        if [ ! -f "$TPL_SRC" ]; then
            warn "FIX 61: plist template not found at $TPL_SRC — intake poll NOT scheduled. Manual: copy the template, replace <POLL_SCRIPT_PATH>/<LOG_PATH>, launchctl load."
            return 1
        fi
        mkdir -p "$PLIST_DIR" "$(dirname "$LOG_PATH")"
        # ── ENV-LOADING FIX (2026-09-06) ──────────────────────────────────
        # launchd gives a job essentially NO environment. This render used to
        # substitute two placeholders into a template that declared no
        # EnvironmentVariables at all, so the poller ran with nothing — and
        # launcher.py's fail-closed notify gate refused EVERY dispatch with
        # AF-NOTIFY-UNCONFIGURED (5,948 consecutive refusals measured on the
        # operator Mac) while PRESENTATION_NOTIFY_CMD was present and
        # non-blank in all three of that box's env stores. The template now
        # carries PATH / PRESENTATION_RUNS_DIR / PRESENTATION_NOTIFY_CMD, and
        # this renderer must supply all three or the fix does not survive the
        # next install.
        #
        # Values, resolved the same way the FIX 49 watchdog render resolved
        # its own (never guessed, never fabricated):
        #   PATH   — launchd supplies none. /opt/homebrew/bin carries the
        #            interpreter this codebase is developed against;
        #            $HOME/.npm-global/bin carries the openclaw CLI the notify
        #            transport execs; the system prefix rides behind them.
        #   RUNS   — the department's runs root, sibling of the scripts dir.
        #   NOTIFY — the co-located transport, and ONLY if the file actually
        #            exists. A PRESENTATION_NOTIFY_CMD pointing at a missing
        #            file would trade "unconfigured" for a per-tick transport
        #            failure, so it renders EMPTY instead and says so. Empty
        #            is SAFE here: the poller loads the box's env store itself
        #            and its precedence only lets a NON-BLANK process value
        #            win, so an empty string cannot shadow the store.
        local _dept_scripts_dir; _dept_scripts_dir="$(dirname "$POLL_SRC")"
        local _poll_path="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$HOME/.npm-global/bin"
        local _poll_notify_cmd=""
        if [ -f "$_dept_scripts_dir/presentation-notify.py" ]; then
            _poll_notify_cmd="$_dept_scripts_dir/presentation-notify.py"
        else
            warn "FIX 61: notify transport not found at $_dept_scripts_dir/presentation-notify.py — PRESENTATION_NOTIFY_CMD rendered EMPTY in the LaunchAgent. The poller will fall back to the box env store; if that has no transport either, dispatch stays refused (AF-NOTIFY-UNCONFIGURED)."
        fi
        # Parse the actual template, substitute values as plist strings (never
        # sed/XML/shell fragments), validate, then atomically promote beside the
        # destination. Failed rendering leaves the old plist and job untouched.
        if ! python3 - "$TPL_SRC" "$PLIST_DST" "$POLL_SRC" "$LOG_PATH" "$_poll_path" "$_poll_runs_dir" "$_poll_notify_cmd" "$_poll_root" "$_poll_workspace" <<'PY_RENDER_INTAKE_PLIST'
import os
from pathlib import Path
import plistlib
import re
import shlex
import sys
import tempfile

template, destination, poll, log, runtime_path, runs, notify, client_root, workspace = sys.argv[1:]
text = Path(template).read_text()
# The repository template has a documentation comment before its XML declaration.
start = text.find('<?xml')
if start < 0:
    raise ValueError('Intake poll template has no XML declaration')
data = plistlib.loads(text[start:].encode())
values = {
    '<POLL_SCRIPT_PATH>': poll, '<LOG_PATH>': log, '<POLL_PATH>': runtime_path,
    '<PRESENTATION_RUNS_DIR>': runs,
    # This value is parsed by shlex.split in the notification transport.
    '<PRESENTATION_NOTIFY_CMD>': shlex.quote(notify) if notify else '',
}
seen = set()
def render(value):
    if isinstance(value, dict):
        return {key: render(item) for key, item in value.items()}
    if isinstance(value, list):
        return [render(item) for item in value]
    if isinstance(value, str):
        if value in values:
            seen.add(value)
            return values[value]
        if re.search(r'<[A-Z_]+>', value):
            raise ValueError('Unknown or embedded intake poll placeholder')
    return value
result = render(data)
if seen != set(values):
    raise ValueError('Intake poll template is missing required placeholders')
if (result.get('Label') != 'com.blackceo.presentation-intake-poll'
        or result.get('ProgramArguments') != ['/bin/bash', poll]
        or result.get('StartInterval') != 300
        or result.get('StandardOutPath') != log
        or result.get('StandardErrorPath') != log
        or any(result.get('EnvironmentVariables', {}).get(key) != expected for key, expected in {
            'PATH': runtime_path, 'PRESENTATION_RUNS_DIR': runs,
            'PRESENTATION_NOTIFY_CMD': values['<PRESENTATION_NOTIFY_CMD>'],
        }.items())):
    raise ValueError('Intake poll template does not satisfy the scheduler contract')
# Carry client context into launchd's otherwise empty environment, even when
# scripts themselves were sourced from a shared installer checkout.
result['EnvironmentVariables'].update({
    'OPENCLAW_ROOT': client_root,
    'OPENCLAW_WORKSPACE_PATH': workspace,
    'OPENCLAW_WORKSPACE_ROOT': workspace,
})
encoded = plistlib.dumps(result)
if plistlib.loads(encoded) != result:
    raise ValueError('Intake poll plist failed round-trip validation')
fd, candidate = tempfile.mkstemp(prefix='.presentation-intake-poll-', suffix='.plist', dir=Path(destination).parent)
try:
    with os.fdopen(fd, 'wb') as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(candidate, 0o644)
    os.replace(candidate, destination)
finally:
    if os.path.exists(candidate):
        os.unlink(candidate)
PY_RENDER_INTAKE_PLIST
        then
            warn "FIX 61: intake poll render/validation failed — prior plist and running job preserved; no launchctl changes made."
            return 1
        fi
        success "FIX 61: validated $PLIST_DST (poll script: $POLL_SRC, log: $LOG_PATH, runs: $_poll_runs_dir, notify transport: ${_poll_notify_cmd:-<EMPTY — env store must supply it>})"
        # Reload semantics: if already loaded, unload first so a re-run picks up
        # a re-rendered copy. 'launchctl load' on an already-loaded job is the
        # documented "Load failed: 5: Input/output error" — treat it as loaded.
        launchctl unload "$PLIST_DST" >/dev/null 2>&1 || true
        if launchctl load "$PLIST_DST" >/dev/null 2>&1; then
            success "FIX 61: launchctl load OK — com.blackceo.presentation-intake-poll scheduled every 300s"
        elif launchctl list 2>/dev/null | grep -q 'com.blackceo.presentation-intake-poll'; then
            success "FIX 61: com.blackceo.presentation-intake-poll already loaded (launchctl list confirms)"
        else
            warn "FIX 61: launchctl load FAILED and the agent is NOT loaded — intake poll NOT scheduled. Manual: launchctl load $PLIST_DST"
            _rc=1
        fi
    fi

    return "$_rc"
}

# Reuse the selected platform workspace; never infer client ownership from an
# unrelated /data directory. A configured resolver failure is not a default.
_fix61_selected_workspace() {
    local _ws="" _root="${OPENCLAW_ROOT:-${OC_ROOT:-${OC_CONFIG:-}}}"
    if [ -n "${OPENCLAW_WORKSPACE_PATH:-}" ] && [ -n "${OPENCLAW_WORKSPACE_ROOT:-}" ] && [ "${OPENCLAW_WORKSPACE_PATH%/}" != "${OPENCLAW_WORKSPACE_ROOT%/}" ]; then
        warn "FIX 61: selected workspace pins conflict; refusing another client root." >&2
        return 1
    fi
    _ws="${OPENCLAW_WORKSPACE_PATH:-${OPENCLAW_WORKSPACE_ROOT:-${OC_WORKSPACE_DEFAULT:-${OC_WORKSPACE:-}}}}"
    if [ -z "$_ws" ]; then
        if [ -n "$_root" ]; then
            _ws="${_root%/}/workspace"
        elif command -v obs_resolve_workspace >/dev/null 2>&1; then
            _ws="$(obs_resolve_workspace)" || {
                warn "FIX 61: configured workspace resolver failed; no alternate client root selected." >&2
                return 1
            }
            [ -n "$_ws" ] || { warn "FIX 61: configured workspace resolver returned no client workspace." >&2; return 1; }
        else
            _ws="$HOME/.openclaw/workspace"
        fi
    fi
    case "$_ws" in /*) ;; *) warn "FIX 61: client workspace must be absolute." >&2; return 1 ;; esac
    [ "${_ws%/}" != "" ] || return 1
    printf '%s\n' "${_ws%/}"
}

# Resolve PRESENTATIONS_SCRIPTS_SRC ONCE, here, before the scheduler runs.
# The poller and its plist template have TWO legitimate homes, and resolving
# from a single candidate is what failed in the field:
#   1. the repo checkout this installer is running from, and
#   2. the MATERIALIZED department — the poller's runtime home, and the only
#      home that exists when install.sh runs from anything that is not a full
#      checkout (curl|bash, a trimmed payload, a re-run out of /tmp).
# When the sole repo candidate missed, the variable stayed EMPTY and every
# path built from it collapsed to "/presentation-intake-poll.sh".
# Workspace resolution uses the selected platform client context. warn() writes to
# stdout, so its calls here are redirected to stderr: this function's stdout IS
# the resolved path and must carry nothing else.
_fix61_resolve_scripts_src() {
    local _c _ws=""
    # A caller-supplied value is honoured but VALIDATED — never trusted blind.
    if [ -n "${PRESENTATIONS_SCRIPTS_SRC:-}" ]; then
        if [ -f "$PRESENTATIONS_SCRIPTS_SRC/presentation-intake-poll.sh" ]; then
            printf '%s\n' "$PRESENTATIONS_SCRIPTS_SRC"
            return 0
        fi
        warn "FIX 61: PRESENTATIONS_SCRIPTS_SRC was preset to '$PRESENTATIONS_SCRIPTS_SRC', which holds no presentation-intake-poll.sh — refusing to replace the explicit pin." >&2
        return 1
    fi
    _c="$_SCRIPT_DIR/23-ai-workforce-blueprint/templates/role-library/presentations/scripts"
    if [ -f "$_c/presentation-intake-poll.sh" ]; then
        printf '%s\n' "$_c"
        return 0
    fi
    _ws="$(_fix61_selected_workspace)" || return 1
    _c="$_ws/departments/Presentations/scripts"
    if [ -f "$_c/presentation-intake-poll.sh" ]; then
        printf '%s\n' "$_c"
        return 0
    fi
    return 1
}

# ════════════════════════════════════════════════════════════════════════════
# F12a — the watchdog + supervisor schedule. NEW.
# ════════════════════════════════════════════════════════════════════════════
# presentation-watchdog.sh runs four passes: --watchdog (stall detection),
# --reconcile-board, --supervise (worker liveness: detects an engine PROCESS
# that died behind an active run and, with --apply, restarts it under a
# bounded backed-off budget) and run_discovery.py. Its plist template ships
# in the department beside it and has never been rendered by any installer,
# so on every client box all four passes are dead code.
#
# This mirrors install_intake_poll_schedule() above deliberately — same
# resolver, same workspace, same platform split, same atomic plist render,
# same reload semantics — because the two schedules are the same kind of
# object and drift between them is how one of them silently stops working.
#
# SCHEDULE: 600s (the template's own StartInterval) on Mac; */10 on VPS.
# ────────────────────────────────────────────────────────────────────────────
install_watchdog_schedule() {
    local _rc=0
    # Same empty-prefix refusal as FIX 61's, for the same reason: an empty
    # $PRESENTATIONS_SCRIPTS_SRC collapses the path below to the root-anchored
    # literal "/presentation-watchdog.sh" and the -f test then reports a
    # MISSING FILE when the real fault is an UNRESOLVED DIRECTORY.
    if [ -z "${PRESENTATIONS_SCRIPTS_SRC:-}" ]; then
        warn "F12: PRESENTATIONS_SCRIPTS_SRC is EMPTY — the presentations scripts directory was never resolved. Watchdog/supervisor NOT scheduled."
        return 1
    fi
    local WD_SRC="$PRESENTATIONS_SCRIPTS_SRC/presentation-watchdog.sh"
    local WD_TPL="$PRESENTATIONS_SCRIPTS_SRC/presentation-watchdog.plist.template"

    if [ ! -f "$WD_SRC" ]; then
        warn "F12: presentation-watchdog.sh not found at $WD_SRC — the stall watchdog, the board reconcile, the SUPERVISOR and run-discovery are NOT scheduled on this box. Manual: see the script header."
        return 1
    fi

    local _wd_workspace
    _wd_workspace="$(_fix61_selected_workspace)" || return 1
    local _wd_runs_dir="$_wd_workspace/departments/Presentations/runs"
    local _wd_root="${OPENCLAW_ROOT:-${OC_ROOT:-${OC_CONFIG:-$HOME/.openclaw}}}"
    case "$_wd_root" in /*) ;; *) warn "F12: client root must be absolute." >&2; return 1 ;; esac
    _wd_root="${_wd_root%/}"
    [ -n "$_wd_root" ] || return 1

    # ── OWNER_CHAT_ID — RESOLVED, NEVER FABRICATED. ───────────────────────
    # report.py's resolve_subsystem_chat() swaps a subsystem NAME (watchdog /
    # supervisor / capacity) for this id; without it a stall alert carries a
    # non-numeric "chat id" and can never land anywhere. Sources, in order,
    # all of them things the operator or install.sh already established:
    #   1. $OWNER_CHAT_ID           — already exported for this run
    #   2. $OPENCLAW_OWNER_CHAT_ID  — install.sh's documented S0 override
    #   3. $TELEGRAM_TARGET_CACHED  — the owner target install.sh RESOLVED
    # Anything non-numeric is discarded rather than shipped. When none answer
    # the value renders EMPTY and says so: presentation-watchdog.sh loads the
    # box's env store itself (presentation_job/env_store.py, which exports
    # EVERY name a store defines, not a whitelist), and its precedence lets a
    # NON-BLANK process value win — so an empty here cannot shadow the store,
    # while a real value here does win. Never a guessed id.
    local _wd_owner_chat="${OWNER_CHAT_ID:-${OPENCLAW_OWNER_CHAT_ID:-${TELEGRAM_TARGET_CACHED:-}}}"
    case "$_wd_owner_chat" in
        '') ;;
        -*) case "${_wd_owner_chat#-}" in *[!0-9]*|'') _wd_owner_chat="" ;; esac ;;
        *[!0-9]*) _wd_owner_chat="" ;;
    esac

    # ── PRESENTATION_SUPERVISE_APPLY — F12c + PRES-019. ───────────────────
    # Three sources, resolved in order, each with its own rule:
    #   1. the operator's environment (explicit true/false/1/0, parsed —
    #      "0"/"false" are now genuinely OFF instead of being misread as
    #      armed by the consumer's nonempty-means-on expansion);
    #   2. a value already rendered into an installed plist (PRESERVED across
    #      re-runs — a roll must neither arm what an operator did not nor
    #      disarm what they did; unchanged F12c behaviour, enforced in the
    #      renderer's carry-forward block below);
    #   3. NOBODY said anything -> the PRES-019 health gate decides: a box
    #      that proves recovery-ready is armed (=1) at install time; a box
    #      with any failed gate stays report-only AND NAMES THE FAILED GATE.
    local _wd_supervise_apply=""
    local _wd_supervise_note=""
    local _wd_bool _wd_bool_rc
    # `|| _wd_bool_rc=$?` and NOT a bare capture: under `set -e` (both callers
    # run with it) a command substitution whose exit status is non-zero inside
    # a plain local assignment ABORTS THE FUNCTION -- the unparseable (2) and
    # absent (3) verdicts would kill install_watchdog_schedule with the
    # PARSER's rc as the installer's rc, before any plist is rendered. This
    # shape keeps set -e disarmed for the substitution's rc while still
    # capturing it.
    _wd_bool_rc=0
    _wd_bool="$( _pres_parse_bool "${PRESENTATION_SUPERVISE_APPLY:-}" )" || _wd_bool_rc=$?
    case "$_wd_bool_rc" in
        0)
            # Explicit true or false from the environment WINS over everything.
            _wd_supervise_apply="$_wd_bool"
            ;;
        2)
            # Unparseable: never silently rewritten, never silently dropped.
            # Keep the value verbatim (the consumer's expansion treats any
            # nonempty as armed — legacy wart, warned about, not worsened)
            # and say so.
            _wd_supervise_apply="${PRESENTATION_SUPERVISE_APPLY:-}"
            warn "PRES-019: PRESENTATION_SUPERVISE_APPLY='$_wd_supervise_apply' is not one of 1/true/yes/on or 0/false/no/off — passed through VERBATIM. Note: presentation-watchdog.sh treats any nonempty value as APPLY, so this value arms the supervisor."
            ;;
        3)
            # Absent. Carried plist value first (F12c preservation), then the
            # health gate. The carry-forward is enforced again in the render
            # block below; checking it HERE too means the log line states the
            # real source instead of "gate decided".
            local _wd_carried=""
            if [ "${OPENCLAW_PLATFORM:-mac}" != "vps" ]; then
                local _wd_prior_plist="$HOME/Library/LaunchAgents/com.blackceo.presentation-watchdog.plist"
                if [ -f "$_wd_prior_plist" ]; then
                    _wd_carried="$(/usr/libexec/PlistBuddy -c 'Print :EnvironmentVariables:PRESENTATION_SUPERVISE_APPLY' "$_wd_prior_plist" 2>/dev/null)" || _wd_carried=""
                fi
            fi
            if [ -n "$_wd_carried" ]; then
                _wd_supervise_apply="$_wd_carried"
                _wd_supervise_note="carried from the installed plist (PRES-019: $_wd_supervise_apply)"
            else
                # THE HEALTH GATE. Armed only when every recovery prerequisite
                # proves out; otherwise report-only with the failed gate named.
                local _gate_scripts="$PRESENTATIONS_SCRIPTS_SRC"
                local _gate_platform="${OPENCLAW_PLATFORM:-mac}"
                local _gate_out _gate_rc
                # Same set -e discipline as the _pres_parse_bool call above:
                # _pres_recovery_health_gate returns non-zero when the gate
                # says NOT-READY (that is its verdict, not a crash) -- the
                # `|| _gate_rc=$?` keeps that verdict from aborting the
                # installer before it can say WHICH gate failed.
                _gate_rc=0
                _gate_out="$( _pres_recovery_health_gate "$_gate_scripts" "$_gate_platform" )" || _gate_rc=$?
                if [ "$_gate_out" = "1" ]; then
                    _wd_supervise_apply="1"
                    _wd_supervise_note="ARMED by the PRES-019 recovery health gate (all gates passed)"
                else
                    _wd_supervise_apply=""
                    _wd_supervise_note="report-only -- PRES-019 recovery health gate FAILED; the exact failed gate(s) are named above"
                    warn "PRES-019: supervisor stays REPORT-ONLY on this box -- the recovery health gate failed. The failed gate(s) are named above. Fix them and re-run install/update-skills.sh, or set PRESENTATION_SUPERVISE_APPLY=1 explicitly to override."
                fi
            fi
            ;;
    esac
    # Normalize the log note for the explicit-true/false paths.
    if [ -z "$_wd_supervise_note" ]; then
        case "$_wd_supervise_apply" in
            1) _wd_supervise_note="APPLY (operator-armed: PRESENTATION_SUPERVISE_APPLY=1)" ;;
            0) _wd_supervise_note="OFF (operator-set: PRESENTATION_SUPERVISE_APPLY=0/false -- supervisor stays report-only)" ;;
            *) _wd_supervise_note="APPLY (operator-armed, verbatim: PRESENTATION_SUPERVISE_APPLY=$_wd_supervise_apply)" ;;
        esac
    fi
    # A false verdict renders NOTHING: "0" must never ride into launchd's
    # environment, where the watchdog's ${...:+--apply} would misread it as
    # armed. The renderer below also strips an armed key when the verdict is
    # empty, so a box the operator explicitly turned OFF stays off.
    local _wd_apply_off=0
    [ "$_wd_supervise_apply" = "0" ] && { _wd_apply_off=1; _wd_supervise_apply=""; }

    # ── The notify transport, co-located with the watchdog. Same rule as the
    #    poller's: rendered ONLY if the file actually exists; otherwise EMPTY
    #    plus a warning, because a transport pointing at a missing file trades
    #    "unconfigured" for a per-tick failure. presentation-watchdog.sh is
    #    FAIL-CLOSED on this (exit 4, AF-NOTIFY-UNCONFIGURED) — it refuses the
    #    whole pass — so an empty here is only safe because the script loads
    #    the box env store before that gate runs.
    local _wd_scripts_dir; _wd_scripts_dir="$(dirname "$WD_SRC")"
    local _wd_notify_cmd=""
    if [ -f "$_wd_scripts_dir/presentation-notify.py" ]; then
        _wd_notify_cmd="$_wd_scripts_dir/presentation-notify.py"
    else
        warn "F12: notify transport not found at $_wd_scripts_dir/presentation-notify.py — PRESENTATION_NOTIFY_CMD rendered EMPTY. presentation-watchdog.sh is FAIL-CLOSED on an unusable transport (exit 4, AF-NOTIFY-UNCONFIGURED): unless the box env store supplies one, every tick will refuse before any pass runs."
    fi

    if [ "${OPENCLAW_PLATFORM:-}" = "vps" ]; then
        # ── VPS: SILENT main-session openclaw cron, 10-minute cadence ──────
        if ! command -v openclaw >/dev/null 2>&1; then
            warn "F12: openclaw CLI not on PATH — presentation-watchdog cron NOT registered. Re-run update-skills.sh later."
            return 1
        fi
        if oc_cron_tombstoned "presentation-watchdog"; then
            warn "presentation-watchdog is TOMBSTONED (deliberately removed) — NOT re-registering."
            return 0
        fi
        if oc_cron_present "presentation-watchdog"; then
            success "F12: presentation-watchdog cron already installed — skipping"
            return 0
        fi
        local _wd_log="$_wd_root/logs/presentation-watchdog.log"
        mkdir -p "$(dirname "$_wd_log")" 2>/dev/null || true
        local WD_CHANNEL_AGENT="main"
        if [ -n "${TELEGRAM_DEFAULT_AGENT_CACHED:-}" ]; then
            WD_CHANNEL_AGENT="$TELEGRAM_DEFAULT_AGENT_CACHED"
        fi
        # Every value is %q-quoted into an `env` prefix — never interpolated
        # into the prompt as a bare word. An EMPTY notify/owner/apply renders
        # as an empty assignment, which env_store.py treats as absence (a
        # blank never wins over a store value).
        local _wd_command
        printf -v _wd_command 'env OPENCLAW_ROOT=%q OPENCLAW_WORKSPACE_PATH=%q OPENCLAW_WORKSPACE_ROOT=%q SCAN_ROOT=%q GRACE=1.5 SCAN_DEPTH=3 PRESENTATION_NOTIFY_CMD=%q OWNER_CHAT_ID=%q PRESENTATION_SUPERVISE_APPLY=%q sh %q %q' \
            "$_wd_root" "$_wd_workspace" "$_wd_workspace" "$_wd_runs_dir" \
            "$_wd_notify_cmd" "$_wd_owner_chat" "$_wd_supervise_apply" "$WD_SRC" "$_wd_log"
        local WD_PROMPT="[PRESENTATION-WATCHDOG] Run the presentation watchdog pass: $_wd_command . This is an idempotent maintenance scan; it detects stalled deck runs, reconciles the board, supervises engine liveness (report-only unless PRESENTATION_SUPERVISE_APPLY is set) and discovers run dirs."
        if _oc_cron_silent_main "presentation-watchdog" "$WD_CHANNEL_AGENT" "*/10 * * * *" "America/New_York" "$WD_PROMPT" --light-context; then
            success "F12: presentation-watchdog cron installed (SILENT main-session, 10-min, no client auto-announce; supervisor ${_wd_supervise_note})"
        else
            warn "F12: presentation-watchdog cron creation FAILED — stalled deck runs will not be detected or restarted on this box. Manual: openclaw cron create --name presentation-watchdog --agent $WD_CHANNEL_AGENT --cron '*/10 * * * *' --session main --system-event '[PRESENTATION-WATCHDOG] sh $WD_SRC $_wd_log'"
            _rc=1
        fi
    else
        # ── Mac: launchd LaunchAgent from the rendered plist template ──────
        # DESTINATION FILENAME. The template's Label is com.presentations.watchdog
        # but the file this fleet already carries is
        # com.blackceo.presentation-watchdog.plist (verified on the operator Mac
        # 2026-09-06: that filename on disk, that Label inside, and
        # `launchctl list` shows com.presentations.watchdog loaded with status 0).
        # launchd keys on the LABEL, so writing a second file with the same label
        # would collide with the one already loaded. Rendering ONTO the existing
        # filename HEALS that box instead of duplicating it.
        local WD_PLIST_DIR="$HOME/Library/LaunchAgents"
        local WD_PLIST_DST="$WD_PLIST_DIR/com.blackceo.presentation-watchdog.plist"
        local WD_LOG_PATH="$HOME/Library/Logs/openclaw/presentation-watchdog.log"
        if [ ! -f "$WD_TPL" ]; then
            warn "F12: watchdog plist template not found at $WD_TPL — watchdog/supervisor NOT scheduled. Manual: copy the template, replace <WATCHDOG_SCRIPT_PATH>/<SCAN_ROOT>/<LOG_PATH>, launchctl load."
            return 1
        fi
        mkdir -p "$WD_PLIST_DIR" "$(dirname "$WD_LOG_PATH")"
        # PATH: launchd supplies none, and this script needs python3, and
        # `timeout`/`gtimeout` (it explicitly warns and runs unbounded without
        # one), and the openclaw CLI the notify transport execs. Same prefix
        # list, and same reasoning, as the intake-poll render.
        local _wd_path="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$HOME/.npm-global/bin"
        if ! python3 - "$WD_TPL" "$WD_PLIST_DST" "$WD_SRC" "$WD_LOG_PATH" "$_wd_path" "$_wd_runs_dir" "$_wd_notify_cmd" "$_wd_owner_chat" "$_wd_supervise_apply" "$_wd_apply_off" "$_wd_root" "$_wd_workspace" <<'PY_RENDER_WATCHDOG_PLIST'
import os
from pathlib import Path
import plistlib
import re
import shlex
import sys
import tempfile

(template, destination, script, log, runtime_path, scan_root, notify,
 owner_chat, supervise_apply, apply_off, client_root, workspace) = sys.argv[1:]
apply_off = (apply_off == '1')
text = Path(template).read_text()
# The repository template has a documentation comment before its XML declaration.
start = text.find('<?xml')
if start < 0:
    raise ValueError('Watchdog template has no XML declaration')
data = plistlib.loads(text[start:].encode())
values = {
    '<WATCHDOG_SCRIPT_PATH>': script,
    '<SCAN_ROOT>': scan_root,
    '<LOG_PATH>': log,
}
seen = set()


def render(value):
    if isinstance(value, dict):
        return {key: render(item) for key, item in value.items()}
    if isinstance(value, list):
        return [render(item) for item in value]
    if isinstance(value, str):
        if value in values:
            seen.add(value)
            return values[value]
        if re.search(r'<[A-Z_]+>', value):
            raise ValueError('Unknown or embedded watchdog placeholder')
    return value


result = render(data)
if seen != set(values):
    raise ValueError('Watchdog template is missing required placeholders')
# The scheduler contract. StartInterval 600 is the 10-minute cadence the
# watchdog is designed for; the log path is BOTH launchd's stdout/stderr and
# argv[1], because the script tees its own diagnostics into the file it is
# handed and the two must be one file.
if (result.get('Label') != 'com.presentations.watchdog'
        or result.get('ProgramArguments') != ['/bin/sh', script, log]
        or result.get('StartInterval') != 600
        or result.get('StandardOutPath') != log
        or result.get('StandardErrorPath') != log
        or result.get('EnvironmentVariables', {}).get('SCAN_ROOT') != scan_root):
    raise ValueError('Watchdog template does not satisfy the scheduler contract')

env = result.setdefault('EnvironmentVariables', {})
env.update({
    'PATH': runtime_path,
    'OPENCLAW_ROOT': client_root,
    'OPENCLAW_WORKSPACE_PATH': workspace,
    'OPENCLAW_WORKSPACE_ROOT': workspace,
})
# This value is parsed by shlex.split in the notification transport.
env['PRESENTATION_NOTIFY_CMD'] = shlex.quote(notify) if notify else ''

# PRESERVE, NEVER STRIP — with one PRES-019 exception. An operator arming the
# supervisor (F12c) or pinning an owner chat id edits the INSTALLED plist. A
# roll that re-rendered from the template alone would silently drop both on
# the next update -- the installer would be undoing the operator's live
# configuration. So a value this run did not resolve is carried forward from
# the plist already on disk, and only an explicit value in THIS process's
# environment overrides it.
# PRES-019 exception: the shell passed an EXPLICIT FALSE as an empty string
# marker (apply_off=True). A value the operator explicitly turned OFF —
# "0"/"false" parsed by _pres_parse_bool — must STRIP an armed key, not
# preserve it: preserving would resurrect exactly the value the operator
# killed, and the consumer's nonempty-means-on expansion would then misread
# any surviving "0" as armed. An explicit off beats a carried on.
previous = {}
try:
    with open(destination, 'rb') as stream:
        previous = plistlib.load(stream).get('EnvironmentVariables', {}) or {}
except (FileNotFoundError, ValueError, OSError):
    previous = {}

if apply_off:
    env.pop('PRESENTATION_SUPERVISE_APPLY', None)
else:
    carried = str(previous.get('PRESENTATION_SUPERVISE_APPLY', '') or '')
    if supervise_apply:
        env['PRESENTATION_SUPERVISE_APPLY'] = supervise_apply
    elif carried:
        env['PRESENTATION_SUPERVISE_APPLY'] = carried
    else:
        env.pop('PRESENTATION_SUPERVISE_APPLY', None)

carried_owner = str(previous.get('OWNER_CHAT_ID', '') or '')
if owner_chat:
    env['OWNER_CHAT_ID'] = owner_chat
elif carried_owner:
    env['OWNER_CHAT_ID'] = carried_owner
else:
    env.pop('OWNER_CHAT_ID', None)

encoded = plistlib.dumps(result)
if plistlib.loads(encoded) != result:
    raise ValueError('Watchdog plist failed round-trip validation')
fd, candidate = tempfile.mkstemp(prefix='.presentation-watchdog-', suffix='.plist',
                                 dir=Path(destination).parent)
try:
    with os.fdopen(fd, 'wb') as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(candidate, 0o644)
    os.replace(candidate, destination)
finally:
    if os.path.exists(candidate):
        os.unlink(candidate)
PY_RENDER_WATCHDOG_PLIST
        then
            warn "F12: watchdog plist render/validation failed — prior plist and running job preserved; no launchctl changes made."
            return 1
        fi
        success "F12: validated $WD_PLIST_DST (watchdog: $WD_SRC, log: $WD_LOG_PATH, scan root: $_wd_runs_dir, notify transport: ${_wd_notify_cmd:-<EMPTY — env store must supply it>}, owner chat: ${_wd_owner_chat:-<EMPTY — env store or a prior plist must supply it>}, supervisor: ${_wd_supervise_note})"
        # Reload semantics, identical to the intake poll's: 'launchctl load' on
        # an already-loaded job is the documented "Load failed: 5: Input/output
        # error", so unload first and treat an already-listed label as loaded.
        launchctl unload "$WD_PLIST_DST" >/dev/null 2>&1 || true
        if launchctl load "$WD_PLIST_DST" >/dev/null 2>&1; then
            success "F12: launchctl load OK — com.presentations.watchdog scheduled every 600s"
        elif launchctl list 2>/dev/null | grep -q 'com.presentations.watchdog'; then
            success "F12: com.presentations.watchdog already loaded (launchctl list confirms)"
        else
            warn "F12: launchctl load FAILED and the agent is NOT loaded — watchdog/supervisor NOT scheduled. Manual: launchctl load $WD_PLIST_DST"
            _rc=1
        fi
    fi

    return "$_rc"
}

# ════════════════════════════════════════════════════════════════════════════
# F12b — the one entry point a ROLL calls.
# ════════════════════════════════════════════════════════════════════════════
# Both installers are idempotent (the cron branch skips a present or
# tombstoned job; the launchd branch re-renders and reloads the SAME label),
# so a roll may call this every time. It resolves PRESENTATIONS_SCRIPTS_SRC
# only when the caller did not pin one — update-skills.sh pins the
# MATERIALIZED department deliberately, because its own checkout may be a temp
# clone that is deleted later in the run, and scheduling launchd against a
# path that is about to vanish is worse than not scheduling at all.
#
# Returns the WORST rc of the two so a caller can latch it, and never aborts
# on the first failure: a broken poller must not cost the box its watchdog.
install_presentation_schedules() {
    local _poll_rc=0 _wd_rc=0

    if [ -z "${PRESENTATIONS_SCRIPTS_SRC:-}" ]; then
        PRESENTATIONS_SCRIPTS_SRC="$(_fix61_resolve_scripts_src || true)"
    fi
    if [ -z "${PRESENTATIONS_SCRIPTS_SRC:-}" ]; then
        warn "F12: presentations scripts directory UNRESOLVED (looked in \${_SCRIPT_DIR}/23-ai-workforce-blueprint/templates/role-library/presentations/scripts and <workspace>/departments/Presentations/scripts) — NEITHER the intake poll NOR the watchdog/supervisor was scheduled."
        return 1
    fi

    set +e
    install_intake_poll_schedule
    _poll_rc=$?
    install_watchdog_schedule
    _wd_rc=$?
    set -e

    if [ "$_poll_rc" -ne 0 ]; then
        warn "F12: intake-poll schedule install returned rc=$_poll_rc — staged deck submissions may sit undispatched on this box."
    fi
    if [ "$_wd_rc" -ne 0 ]; then
        warn "F12: watchdog/supervisor schedule install returned rc=$_wd_rc — stalled deck runs will not be detected or restarted on this box."
    fi
    if [ "$_poll_rc" -ne 0 ]; then return "$_poll_rc"; fi
    return "$_wd_rc"
}
