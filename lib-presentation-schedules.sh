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
# ============================================================

# Re-source guard.
[ -n "${__PRESENTATION_SCHEDULES_LIB_SOURCED:-}" ] && return 0
__PRESENTATION_SCHEDULES_LIB_SOURCED=1

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
# ════════════════════════════════════════════════════════════════════════════
# PRES-034 — reconcile existing schedules against a versioned contract.
# ────────────────────────────────────────────────────────────────────────────
# THE DEFECT THIS CLOSES. Both VPS branches above treated "a cron with the
# right name exists" as "the schedule is correct" (oc_cron_present → success,
# return 0). A job carrying a deleted script path, a wrong company root, or
# an old recovery setting was reported "already installed" while the old
# scheduler kept invoking a missing or wrong runtime. New code shipped; the
# old tick ran. Nothing compared anything.
#
# WHAT THIS ADDS, per TODO.md PRES-034 steps 1-4:
#   1. Read the existing job by stable scheduler ID (the cron NAME on VPS,
#      the launchd LABEL on Mac) and compare its NORMALIZED desired command,
#      selected root/workspace, environment, cadence and enabled state to a
#      versioned schedule contract (_PRESCHED_CONTRACT_VERSION, recorded in
#      every receipt so a future contract bump re-reconciles).
#   2. Update the existing ID IN PLACE (`openclaw cron edit <id>`, a
#      field-level patch — schedule/tz/session/delivery/payload flags only,
#      never the name). If the edit is rejected, atomically fence the old
#      execution (disable) BEFORE enabling the new one, then remove the old
#      ID; a rollback record (the old job JSON) is written BEFORE any
#      mutation, and a failed recreate re-enables the fenced job.
#   3. Preserve deliberate tombstones and explicit pauses. A tombstoned name
#      or a gateway-disabled job reports PAUSED_BY_OWNER — visibly distinct
#      from HEALTHY and MISSING — and is NEVER reactivated or edited.
#   4. After every install/reconcile/verify, run a no-production-work health
#      invocation under the simulated scheduler context (clean env + the box
#      env-store loader + notify_preflight, the same chain the tick itself
#      runs) and record the loaded command hash plus next-fire. A repair
#      failure latches DEGRADED in the department readiness receipt instead
#      of living only in updater stdout.
#
# CONCURRENCY. Two installers racing (roll + manual re-run) both see
# "absent" and both create → duplicate crons firing the same tick. The
# reconcile body runs under a mkdir lock (stale locks self-heal by mtime),
# and every create is followed by a same-name dedupe sweep (keep the
# reconciled ID, rm the extras). Either layer alone closes the race; both
# are kept because the lock only spans this host's installers while the
# sweep also heals duplicates left by older code.
# ════════════════════════════════════════════════════════════════════════════
_PRESCHED_CONTRACT_VERSION="1"
_PRESCHED_POLL_NAME="presentation-intake-poll"
_PRESCHED_WD_NAME="presentation-watchdog"
_PRESCHED_POLL_LABEL="com.blackceo.presentation-intake-poll"
_PRESCHED_WD_LABEL="com.presentations.watchdog"
_PRESCHED_POLL_INTERVAL_S=300
_PRESCHED_WD_INTERVAL_S=600
_PRESCHED_POLL_EXPR="*/5 * * * *"
_PRESCHED_WD_EXPR="*/10 * * * *"
_PRESCHED_TZ="America/New_York"

# Globals set by _presched_reconcile_cron for the caller's finish step:
#   _PRESCHED_STATUS  HEALTHY | PAUSED_BY_OWNER | MISSING | DEGRADED
#   _PRESCHED_JOB_ID  gateway job id (VPS), launchd label (Mac), or "-" unset
#   _PRESCHED_NEXT_FIRE human next-fire record (ISO time or cron expr)
_PRESCHED_STATUS="MISSING"
_PRESCHED_JOB_ID="-"
_PRESCHED_NEXT_FIRE=""

# _presched_lock <name> — mkdir-based mutex. Prints the lock dir on success.
# A lock older than 120s is stale (a killed installer) and is taken over.
_presched_lock() {
    local _name="$1" _root="${PRESCHED_LOCK_ROOT:-${TMPDIR:-/tmp}}"
    local _dir="$_root/.presched-$1.lock" _now _mtime _age
    if mkdir "$_dir" 2>/dev/null; then printf '%s\n' "$_dir"; return 0; fi
    _now="$(date +%s 2>/dev/null || echo 0)"
    # mtime via python (portable darwin/linux); failure means "not stale".
    _mtime="$(python3 -c 'import os,sys; print(int(os.stat(sys.argv[1]).st_mtime))' "$_dir" 2>/dev/null || echo "$_now")"
    case "$_mtime" in ''|*[!0-9]*) _mtime="$_now" ;; esac
    _age=$((_now - _mtime))
    if [ "$_age" -gt 120 ]; then
        rm -rf "$_dir" 2>/dev/null || true
        if mkdir "$_dir" 2>/dev/null; then printf '%s\n' "$_dir"; return 0; fi
    fi
    # Contended but fresh: wait up to ~30s, then proceed WITHOUT the lock and
    # say so — the post-create dedupe sweep still prevents duplicates. A
    # contended lock must delay, never fail, a schedule install.
    local _wait=0
    while [ "$_wait" -lt 30 ]; do
        sleep 1; _wait=$((_wait + 1))
        if mkdir "$_dir" 2>/dev/null; then printf '%s\n' "$_dir"; return 0; fi
    done
    warn "_presched: lock for $1 contended for 30s — proceeding without it (dedupe sweep still guards against duplicates)."
    return 0
}

_presched_unlock() {
    rmdir "$1" 2>/dev/null || true
}

# _presched_state_dir <subdir> — durable per-client state under the selected
# client root (overridable for tests via OPENCLAW_ROOT, which the harness
# already sandboxes). Creates best-effort; prints the path or nothing.
_presched_state_dir() {
    local _root="${OPENCLAW_ROOT:-${OC_ROOT:-${OC_CONFIG:-$HOME/.openclaw}}}"
    case "$_root" in /*) ;; *) return 1 ;; esac
    local _dir="${_root%/}/workspace/$1"
    mkdir -p "$_dir" 2>/dev/null || return 1
    printf '%s\n' "$_dir"
}

# _presched_cron_fetch <name> — print the job JSON for an exact-name match.
# rc 0 = found (JSON on stdout), 1 = absent, 2 = list unreadable/unparseable
# (an EXPLICIT unknown — the caller must fail loudly, never read it as
# "already installed"). Uses --all so gateway-disabled jobs are visible;
# falls back to plain --json on CLIs without the flag.
_presched_cron_fetch() {
    local _name="$1" _raw="" _rc=0
    command -v openclaw >/dev/null 2>&1 || return 2
    command -v python3 >/dev/null 2>&1 || return 2
    _raw="$(openclaw cron list --json --all 2>/dev/null)" || _rc=$?
    if [ "$_rc" -ne 0 ] || [ -z "$_raw" ]; then
        # No --all support (older CLI) or first attempt failed: retry plain.
        # rc is re-captured so a second failure is still a failure.
        _rc=0
        _raw="$(openclaw cron list --json 2>/dev/null)" || _rc=$?
    fi
    if [ -z "$_raw" ]; then
        # rc 0 + empty = a READABLE empty list (nothing registered — ABSENT);
        # rc != 0 + empty = the scheduler could not be read (UNREADABLE).
        [ "$_rc" -eq 0 ] && return 1 || return 2
    fi
    _PRESCHED_FETCH_NAME="$_name" _PRESCHED_FETCH_RAW="$_raw" python3 - <<'PYEOF' 2>/dev/null
import json, os, sys
name = os.environ.get("_PRESCHED_FETCH_NAME", "")
try:
    data = json.loads(os.environ.get("_PRESCHED_FETCH_RAW", ""))
except Exception:
    sys.exit(2)
# The CLI prints an error ENVELOPE ({ok:false,...}) on stdout with rc 0 when
# the gateway is unreachable — that is an UNREADABLE list, never "absent".
if isinstance(data, dict) and data.get("ok") is False:
    sys.exit(2)
if isinstance(data, dict) and "jobs" not in data:
    sys.exit(2)
jobs = data if isinstance(data, list) else data.get("jobs", [])
hits = [j for j in jobs if isinstance(j, dict) and j.get("name") == name]
if not hits:
    sys.exit(1)
print(json.dumps(hits[0]))
print("COUNT=%d" % len(hits), file=sys.stderr)
PYEOF
}

# _presched_modern_payload — print "systemEvent" when the installed CLI takes
# --session (modern agent payload), else "message". Matches the probe in
# _oc_cron_silent_main so desired state agrees with what create would send.
_presched_modern_payload() {
    local _help=""
    _help="$(openclaw cron add --help 2>&1 || true)"
    if printf '%s' "$_help" | grep -qE '^[[:space:]]*--session[[:space:]<]'; then
        printf 'systemEvent\n'
    else
        printf 'message\n'
    fi
}

# _presched_compare <name> <expr> <tz> <agent> — compare the LIVE job against
# the desired contract. Desired prompt arrives via _PRESCHED_DESIRED_PROMPT.
# stdout: one line per drifted field (field names only, never values), or
# "IN_SYNC" when everything matches. rc 0 always (comparison cannot fail a
# roll; the CALLER decides). A disabled job prints PAUSED_BY_OWNER.
_presched_compare() {
    local _name="$1" _expr="$2" _tz="$3" _agent="$4" _job_json="$5"
    _PRESCHED_CMP_JOB="$_job_json" _PRESCHED_CMP_EXPR="$_expr" \
    _PRESCHED_CMP_TZ="$_tz" _PRESCHED_CMP_AGENT="$_agent" \
    _PRESCHED_CMP_PROMPT="${_PRESCHED_DESIRED_PROMPT:-}" \
    _PRESCHED_CMP_KIND="$(_presched_modern_payload)" python3 - <<'PYEOF' 2>/dev/null
import json, os
job = json.loads(os.environ["_PRESCHED_CMP_JOB"])
def norm(s): return (s or "").strip()
drift = []
if job.get("enabled", True) is False:
    print("PAUSED_BY_OWNER")
    raise SystemExit(0)
sch = job.get("schedule") or {}
if norm(sch.get("expr")) != norm(os.environ["_PRESCHED_CMP_EXPR"]):
    drift.append("schedule")
if norm(sch.get("tz")) != norm(os.environ["_PRESCHED_CMP_TZ"]):
    drift.append("tz")
if norm(job.get("agentId")) != norm(os.environ["_PRESCHED_CMP_AGENT"]):
    drift.append("agent")
if norm(job.get("sessionTarget")) != "main":
    drift.append("session")
dl = job.get("delivery") or {}
if (dl.get("mode") in ("announce",)) or (dl.get("to")):
    drift.append("delivery")
pay = job.get("payload") or {}
stored = pay.get("text", pay.get("message", pay.get("systemEvent", "")))
if norm(stored) != norm(os.environ["_PRESCHED_CMP_PROMPT"]):
    drift.append("command")
want = os.environ["_PRESCHED_CMP_KIND"]
have = pay.get("kind", "")
if want == "systemEvent" and have not in ("systemEvent", ""):
    drift.append("payload-kind")
elif want == "message" and have not in ("agent", "message", ""):
    drift.append("payload-kind")
print("IN_SYNC" if not drift else "DRIFT:" + ",".join(drift))
PYEOF
}

# _presched_rollback_save <name> <job_json> — persist the pre-mutation job
# JSON. Prints the record path. Best-effort; failure is fatal to the
# mutation (no rollback record, no mutation).
_presched_rollback_save() {
    local _dir _path _ts
    _dir="$(_presched_state_dir ".cron-rollback")" || return 1
    _ts="$(date -u +%Y%m%dT%H%M%SZ 2>/dev/null || echo unknown)"
    _path="$_dir/$1-${_ts}.json"
    printf '%s' "$2" > "$_path" 2>/dev/null || return 1
    chmod 600 "$_path" 2>/dev/null || true
    printf '%s\n' "$_path"
}

# _presched_dedupe <name> <keep_id> — remove same-name extras. Keeps keep_id
# (the reconciled job); prefers removing disabled rows first. Never removes
# the last remaining row.
_presched_dedupe() {
    local _name="$1" _keep="$2" _raw _ids _id
    _raw="$(openclaw cron list --json --all 2>/dev/null)" || _raw=""
    if [ -z "$_raw" ]; then
        _raw="$(openclaw cron list --json 2>/dev/null)" || _raw=""
    fi
    [ -n "$_raw" ] || return 0
    _ids="$(_PRESCHED_DD_RAW="$_raw" _PRESCHED_DD_NAME="$_name" _PRESCHED_DD_KEEP="$_keep" python3 - <<'PYEOF' 2>/dev/null
import json, os
try:
    data = json.loads(os.environ.get("_PRESCHED_DD_RAW", ""))
except Exception:
    raise SystemExit(0)
jobs = data if isinstance(data, list) else data.get("jobs", [])
keep = os.environ.get("_PRESCHED_DD_KEEP", "")
name = os.environ.get("_PRESCHED_DD_NAME", "")
same = [j for j in jobs if isinstance(j, dict) and j.get("name") == name and j.get("id") and j.get("id") != keep]
same.sort(key=lambda j: (j.get("enabled", True), j.get("createdAtMs") or 0), reverse=True)
for j in same:
    print(j["id"])
PYEOF
)"
    [ -n "$_ids" ] || return 0
    local _count
    _count="$(printf '%s' "$_ids" | grep -c . || true)"
    [ "$_count" -gt 0 ] || return 0
    # Re-count live rows: never remove the last one.
    local _total
    _total="$(_PRESCHED_DD_RAW="$_raw" _PRESCHED_DD_NAME="$_name" python3 -c '
import json, os
try: data = json.loads(os.environ.get("_PRESCHED_DD_RAW", ""))
except Exception: raise SystemExit(0)
jobs = data if isinstance(data, list) else data.get("jobs", [])
print(sum(1 for j in jobs if isinstance(j, dict) and j.get("name") == os.environ.get("_PRESCHED_DD_NAME", "")))
' 2>/dev/null || echo 0)"
    case "$_total" in ''|*[!0-9]*) _total=0 ;; esac
    while IFS= read -r _id; do
        [ -n "$_id" ] || continue
        if [ "$_total" -le 1 ]; then break; fi
        if openclaw cron rm "$_id" >/dev/null 2>&1; then
            warn "_presched: removed duplicate $_name job $_id (kept $_keep)."
            _total=$((_total - 1))
        else
            warn "_presched: could not remove duplicate $_name job $_id — left in place, will retry next run."
        fi
    done <<< "$_ids"
    return 0
}

# _presched_reconcile_cron <name> <expr> <tz> <agent> <prompt> [extra create flags...]
# Full VPS reconcile for one scheduler. Desired prompt via $5 (also exported
# as _PRESCHED_DESIRED_PROMPT for the comparator). Sets _PRESCHED_STATUS /
# _PRESCHED_JOB_ID / _PRESCHED_NEXT_FIRE. rc 0 = HEALTHY or PAUSED_BY_OWNER
# (both non-fatal); rc 1 = explicit failure (MISSING or DEGRADED latched by
# the caller's finish step).
_presched_reconcile_cron() {
    local _name="$1" _expr="$2" _tz="$3" _agent="$4" _prompt="$5"; shift 5
    local _extra=( "$@" )
    _PRESCHED_STATUS="MISSING"; _PRESCHED_JOB_ID="-"; _PRESCHED_NEXT_FIRE="expr:$_expr"
    if ! command -v openclaw >/dev/null 2>&1; then
        warn "_presched($_name): openclaw CLI not on PATH — schedule NOT verified (explicit failure, not 'already installed')."
        return 1
    fi
    if oc_cron_tombstoned "$_name"; then
        _PRESCHED_STATUS="PAUSED_BY_OWNER"
        _PRESCHED_NEXT_FIRE="tombstoned (deliberate removal)"
        warn "$_name is TOMBSTONED (deliberately removed) — NOT re-registering."
        return 0
    fi
    local _lock
    _lock="$(_presched_lock "$_name")" || _lock=""
    local _rc=1
    _PRESCHED_DESIRED_PROMPT="$_prompt" _presched_reconcile_inner "$_name" "$_expr" "$_tz" "$_agent" "$_prompt" ${_extra[@]+"${_extra[@]}"}
    _rc=$?
    if [ -n "$_lock" ]; then _presched_unlock "$_lock"; fi
    return "$_rc"
}

_presched_reconcile_inner() {
    local _name="$1" _expr="$2" _tz="$3" _agent="$4" _prompt="$5"; shift 5
    local _extra=( "$@" )
    local _fetch _job_json _fetch_rc _probe_present=1
    oc_cron_present "$_name" && _probe_present=0 || _probe_present=$?
    # _probe_present: 0 = probe sees it. The probe can miss a
    # disabled-and-invisible job on CLIs without --all (documented in
    # cron-lib.sh) — so "probe absent" never means "safe to blindly create";
    # the fetch below is authoritative and create is followed by dedupe.
    _fetch_rc=0
    _fetch="$(_presched_cron_fetch "$_name" 2>/dev/null)" || _fetch_rc=$?
    if [ "$_fetch_rc" -eq 2 ]; then
        if [ "$_probe_present" -eq 0 ]; then
            _PRESCHED_STATUS="HEALTHY"
            success "_presched($_name): present (presence probe) — job details unreadable this run, left untouched."
            return 0
        fi
        warn "_presched($_name): scheduler list unreadable — cannot verify or install (explicit failure)."
        return 1
    fi
    if [ "$_fetch_rc" -eq 1 ]; then
        # Absent: register. (Probe-absent + fetch-absent agree; probe-present
        # + fetch-absent is the invisible-disabled case — creation is still
        # correct because a tombstone would have returned above and a live
        # duplicate is swept by dedupe after create.)
        if _oc_cron_silent_main "$_name" "$_agent" "$_expr" "$_tz" "$_prompt" ${_extra[@]+"${_extra[@]}"}; then
            _fetch="$(_presched_cron_fetch "$_name" 2>/dev/null)" || _fetch=""
            _PRESCHED_JOB_ID="$(printf '%s' "$_fetch" | head -n 1 | python3 -c 'import json,sys; print(json.loads(sys.stdin.read() or "{}").get("id","-"))' 2>/dev/null || echo "-")"
            case "$_PRESCHED_JOB_ID" in ""|-) _PRESCHED_JOB_ID="-" ;; esac
            local _nf=""
            _nf="$(_presched_next_fire "$_fetch")"
            [ -n "$_nf" ] && _PRESCHED_NEXT_FIRE="$_nf"
            if [ "$_PRESCHED_JOB_ID" != "-" ]; then _presched_dedupe "$_name" "$_PRESCHED_JOB_ID"; fi
            _PRESCHED_STATUS="HEALTHY"
            success "_presched($_name): registered (SILENT main-session, $_expr)."
            return 0
        fi
        warn "_presched($_name): cron creation FAILED — staged work may sit undispatched. Manual: openclaw cron create --name $_name --agent $_agent --cron '$_expr' --session main --system-event '<prompt>'"
        return 1
    fi
    _job_json="$(printf '%s' "$_fetch" | head -n 1)"
    local _cmp
    _cmp="$(_presched_compare "$_name" "$_expr" "$_tz" "$_agent" "$_job_json")"
    case "$_cmp" in
        PAUSED_BY_OWNER*)
            _PRESCHED_STATUS="PAUSED_BY_OWNER"
            _PRESCHED_JOB_ID="$(printf '%s' "$_job_json" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read() or "{}").get("id","-"))' 2>/dev/null || echo "-")"
            _PRESCHED_NEXT_FIRE="disabled (operator pause)"
            warn "_presched($_name): gateway-DISABLED by operator (PAUSED_BY_OWNER) — left stopped, never reactivated."
            return 0
            ;;
        IN_SYNC*)
            _PRESCHED_STATUS="HEALTHY"
            _PRESCHED_JOB_ID="$(printf '%s' "$_job_json" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read() or "{}").get("id","-"))' 2>/dev/null || echo "-")"
            local _nf=""
            _nf="$(_presched_next_fire "$_fetch")"
            [ -n "$_nf" ] && _PRESCHED_NEXT_FIRE="$_nf"
            # Even an in-sync job gets the dedupe sweep: a legacy duplicate
            # (older code) heals on the next install without touching the
            # reconciled row.
            [ "$_PRESCHED_JOB_ID" != "-" ] && _presched_dedupe "$_name" "$_PRESCHED_JOB_ID"
            success "_presched($_name): installed AND verified against contract v$_PRESCHED_CONTRACT_VERSION (command, root, env, cadence, enabled all match)."
            return 0
            ;;
    esac
    local _drift="${_cmp#DRIFT:}"
    warn "_presched($_name): drifted fields [$_drift] — reconciling the same ID in place."
    local _jid
    _jid="$(printf '%s' "$_job_json" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read() or "{}").get("id",""))' 2>/dev/null || echo "")"
    if [ -z "$_jid" ]; then
        warn "_presched($_name): present but ID unresolvable — cannot edit (explicit failure)."
        return 1
    fi
    local _rollback
    if ! _rollback="$(_presched_rollback_save "$_name" "$_job_json")"; then
        warn "_presched($_name): could not write rollback record — refusing to mutate without one."
        return 1
    fi
    if _presched_edit_job "$_jid" "$_drift" "$_expr" "$_tz" "$_agent" "$_prompt"; then
        local _verify _vcmp
        _verify="$(_presched_cron_fetch "$_name" 2>/dev/null)" || _verify=""
        _vcmp="$(_presched_compare "$_name" "$_expr" "$_tz" "$_agent" "$(printf '%s' "$_verify" | head -n 1)")"
        case "$_vcmp" in
            IN_SYNC*)
                _PRESCHED_STATUS="HEALTHY"; _PRESCHED_JOB_ID="$_jid"
                local _nf=""
                _nf="$(_presched_next_fire "$_verify")"
                [ -n "$_nf" ] && _PRESCHED_NEXT_FIRE="$_nf"
                success "_presched($_name): reconciled in place (same ID $_jid, rollback: $_rollback)."
                return 0
                ;;
        esac
        warn "_presched($_name): edit applied but verification still shows [${_vcmp#DRIFT:}] — falling through to fenced replacement."
    else
        warn "_presched($_name): in-place edit rejected — falling through to fenced replacement (rollback: $_rollback)."
    fi
    # Fenced replacement: fence (disable) old BEFORE enabling new; remove old
    # only after the new ID verifies. A failed create re-enables the old job.
    if ! openclaw cron disable "$_jid" >/dev/null 2>&1; then
        warn "_presched($_name): could not fence (disable) old job $_jid — refusing to create a second live job."
        return 1
    fi
    if _oc_cron_silent_main "$_name" "$_agent" "$_expr" "$_tz" "$_prompt" ${_extra[@]+"${_extra[@]}"}; then
        local _newfetch _newid _nvcmp
        _newfetch="$(_presched_cron_fetch "$_name" 2>/dev/null)" || _newfetch=""
        # Pick the enabled non-old ID (the job just created).
        _newid="$(printf '%s' "$_newfetch" | _PRESCHED_OLD="$_jid" python3 -c '
import json, os, sys
cands = []
for line in sys.stdin.read().splitlines():
    line = line.strip()
    if not line or line.startswith("COUNT="): continue
    try: cands.append(json.loads(line))
    except Exception: pass
old = os.environ.get("_PRESCHED_OLD", "")
live = [j for j in cands if j.get("id") != old and j.get("enabled", True) is not False]
pool = live or cands
print(pool[0].get("id", "") if pool else "")
' 2>/dev/null || echo "")"
        if [ -n "$_newid" ]; then
            _nvcmp="$(_presched_compare "$_name" "$_expr" "$_tz" "$_agent" "$(printf '%s' "$_newfetch" | head -n 1)")"
            openclaw cron rm "$_jid" >/dev/null 2>&1 \
                && warn "_presched($_name): fenced replacement complete — old ID $_jid removed, new ID $_newid live (rollback: $_rollback)." \
                || warn "_presched($_name): new ID $_newid live; old fenced ID $_jid could NOT be removed — left DISABLED, will retry next run (rollback: $_rollback)."
            _presched_dedupe "$_name" "$_newid"
            _PRESCHED_STATUS="HEALTHY"; _PRESCHED_JOB_ID="$_newid"
            local _nf=""
            _nf="$(_presched_next_fire "$_newfetch")"
            [ -n "$_nf" ] && _PRESCHED_NEXT_FIRE="$_nf"
            return 0
        fi
        warn "_presched($_name): replacement created but new ID unresolvable — re-enabling fenced job $_jid."
        openclaw cron enable "$_jid" >/dev/null 2>&1 || true
        return 1
    fi
    warn "_presched($_name): replacement create FAILED — re-enabling fenced job $_jid (rollback: $_rollback)."
    openclaw cron enable "$_jid" >/dev/null 2>&1 || true
    return 1
}

# _presched_edit_job <id> <drift_csv> <expr> <tz> <agent> <prompt> — minimal
# field-level patch: only drifted fields are passed, so schedule, tz,
# sessionTarget and delivery are never touched when they already match.
_presched_edit_job() {
    local _jid="$1" _drift="$2" _expr="$3" _tz="$4" _agent="$5" _prompt="$6"
    local -a _flags=()
    case ",$_drift," in *,schedule,*|*,tz,*) _flags+=(--cron "$_expr" --tz "$_tz") ;; esac
    case ",$_drift," in *,agent,*)           _flags+=(--agent "$_agent") ;; esac
    case ",$_drift," in *,session,*)
        local _ehelp=""
        _ehelp="$(openclaw cron edit --help 2>&1 || true)"
        if printf '%s' "$_ehelp" | grep -qE '^[[:space:]]*--session[[:space:]<]'; then
            _flags+=(--session main)
        else
            _flags+=(--session-target main)
        fi
        ;;
    esac
    case ",$_drift," in *,delivery,*)
        # --no-deliver alone leaves a vestigial `to` that a future gateway
        # could re-arm — fold in --clear-to (probed: older CLIs reject
        # unknown flags, and a rejected edit must fall through to fenced
        # replacement, not half-apply).
        _flags+=(--no-deliver)
        local _ehelp2=""
        _ehelp2="$(openclaw cron edit --help 2>&1 || true)"
        if printf '%s' "$_ehelp2" | grep -qE '^[[:space:]]*--clear-to([[:space:]=<]|$)'; then
            _flags+=(--clear-to)
        fi
        ;;
    esac
    case ",$_drift," in *,command,*|*,payload-kind,*)
        if [ "$(_presched_modern_payload)" = "systemEvent" ]; then
            _flags+=(--system-event "$_prompt")
        else
            _flags+=(--message "$_prompt")
        fi
        ;;
    esac
    [ "${#_flags[@]}" -gt 0 ] || return 0
    openclaw cron edit "$_jid" "${_flags[@]}" >/dev/null 2>&1
}

# _presched_next_fire <fetch_output> — next-fire record: the gateway's own
# nextRunAtMs when present (top-level or state), else the cron expression.
_presched_next_fire() {
    printf '%s' "$1" | head -n 1 | python3 -c '
import json, sys, datetime
try: job = json.loads(sys.stdin.read() or "{}")
except Exception: job = {}
ms = job.get("nextRunAtMs") or (job.get("state") or {}).get("nextRunAtMs")
if ms:
    try: print(datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).isoformat())
    except Exception: print(str(ms))
else: print("")
' 2>/dev/null || echo ""
}

# _presched_finish <workspace> <sched_key> <client_root> <scripts_dir> <script_path> <runs_or_scan_dir> <path_value> <reconcile_rc>
# Health invocation + readiness receipt. Runs the no-production-work health
# driver (clean scheduler-like env → env-store loader → notify_preflight)
# and upserts the department readiness receipt. A reconcile failure latches
# DEGRADED with the reason; health details are recorded either way. Never
# fatal to the caller (returns reconcile_rc).
_presched_finish() {
    local _ws="$1" _key="$2" _root="$3" _sdir="$4" _script="$5" _rundir="$6" _path="$7" _rc="$8"
    local _hash _marker _ready _note
    _hash="$(sha256sum "$_script" 2>/dev/null | awk '{print $1}')"
    [ -n "$_hash" ] || _hash="$(shasum -a 256 "$_script" 2>/dev/null | awk '{print $1}')"
    [ -n "$_hash" ] || _hash="UNAVAILABLE"
    _marker="SKIPPED"; _ready="unknown"; _note=""
    if [ -f "$_sdir/presentation_job/notify_preflight.py" ] && [ -f "$_sdir/presentation_job/env_store.py" ] && command -v python3 >/dev/null 2>&1; then
        local _hout
        _hout="$(_PRESCHED_H_SDIR="$_sdir" _PRESCHED_H_ROOT="$_root" \
            _PRESCHED_H_WS_PATH="$_ws" _PRESCHED_H_RUN="$6" _PRESCHED_H_PATH="$_path" python3 - <<'PYEOF' 2>/dev/null
import json, os, sys
sys.path.insert(0, os.environ["_PRESCHED_H_SDIR"])
sched_env = {
    "PATH": os.environ["_PRESCHED_H_PATH"],
    "HOME": os.path.expanduser("~"),
    "OPENCLAW_ROOT": os.environ["_PRESCHED_H_ROOT"],
    "OPENCLAW_WORKSPACE_PATH": os.environ["_PRESCHED_H_WS_PATH"],
    "OPENCLAW_WORKSPACE_ROOT": os.environ["_PRESCHED_H_WS_PATH"],
    "PRESENTATION_RUNS_DIR": os.environ["_PRESCHED_H_RUN"],
    "SCAN_ROOT": os.environ["_PRESCHED_H_RUN"],
}
try:
    from presentation_job import env_store, notify_preflight
    assignments, report = env_store.resolve(dict(sched_env))
    merged = dict(sched_env); merged.update(assignments)
    # Call with the merged scheduler view without touching this process env.
    real_environ = dict(os.environ)
    os.environ.clear(); os.environ.update(merged)
    try:
        verdict = notify_preflight.check_notify_config()
    finally:
        os.environ.clear(); os.environ.update(real_environ)
    print(json.dumps({"marker": verdict.get("marker"), "ready": bool(verdict.get("ready")),
                      "stores": [e.get("path") for e in report.get("files", [])]}))
except Exception as exc:
    print(json.dumps({"marker": "ERROR", "ready": False, "error": "%s: %s" % (type(exc).__name__, exc)}))
PYEOF
)"
        if [ -n "$_hout" ]; then
            _marker="$(printf '%s' "$_hout" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read() or "{}").get("marker","ERROR"))' 2>/dev/null || echo ERROR)"
            _ready="$(printf '%s' "$_hout" | python3 -c 'import json,sys; print("ready" if json.loads(sys.stdin.read() or "{}").get("ready") else "not-ready")' 2>/dev/null || echo unknown)"
        else
            _marker="ERROR"; _ready="unknown"
        fi
    else
        _note="health driver unavailable (notify_preflight/env_store absent) — scheduler installed without health proof"
    fi
    local _status="$_PRESCHED_STATUS"
    if [ "$_rc" -ne 0 ]; then _status="DEGRADED"; fi
    if [ -z "$_note" ]; then
        case "$_status" in
            HEALTHY) _note="verified against contract v$_PRESCHED_CONTRACT_VERSION" ;;
            PAUSED_BY_OWNER) _note="deliberately paused by operator — never reactivated by installer" ;;
            DEGRADED) _note="repair failed — see installer output; will retry next run" ;;
            *) _note="missing" ;;
        esac
    fi
    if [ "$_PRESCHED_NEXT_FIRE" = "" ] || [ "$_PRESCHED_NEXT_FIRE" = "expr:" ]; then
        :
    fi
    _PRESCHED_R_WS="$_ws" _PRESCHED_R_KEY="$_key" _PRESCHED_R_STATUS="$_status" \
    _PRESCHED_R_JOB="$_PRESCHED_JOB_ID" _PRESCHED_R_HASH="$_hash" \
    _PRESCHED_R_NEXT="$_PRESCHED_NEXT_FIRE" _PRESCHED_R_MARKER="$_marker" \
    _PRESCHED_R_READY="$_ready" _PRESCHED_R_NOTE="$_note" \
    _PRESCHED_R_CONTRACT="$_PRESCHED_CONTRACT_VERSION" python3 - <<'PYEOF' 2>/dev/null
import json, os, socket, tempfile
from datetime import datetime, timezone
from pathlib import Path
ws = Path(os.environ["_PRESCHED_R_WS"])
receipt = ws / "departments" / "Presentations" / ".scheduler-readiness.json"
try:
    current = json.loads(receipt.read_text(encoding="utf-8")) if receipt.exists() else {}
except Exception:
    current = {}
schedules = current.get("schedules", {})
schedules[os.environ["_PRESCHED_R_KEY"]] = {
    "status": os.environ["_PRESCHED_R_STATUS"],
    "job_id": os.environ["_PRESCHED_R_JOB"],
    "command_sha256": os.environ["_PRESCHED_R_HASH"],
    "next_fire": os.environ["_PRESCHED_R_NEXT"],
    "health_marker": os.environ["_PRESCHED_R_MARKER"],
    "health_ready": os.environ["_PRESCHED_R_READY"],
    "note": os.environ["_PRESCHED_R_NOTE"],
    "contract": os.environ["_PRESCHED_R_CONTRACT"],
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "host": socket.gethostname(),
}
current["contract"] = os.environ["_PRESCHED_R_CONTRACT"]
current["schedules"] = schedules
try:
    receipt.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".scheduler-readiness-", suffix=".json", dir=str(receipt.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(current, fh, indent=2, sort_keys=True)
        fh.flush(); os.fsync(fh.fileno())
    os.chmod(tmp, 0o644)
    os.replace(tmp, str(receipt))
except Exception as exc:
    print("RECEIPT_FAIL:%s" % exc)
PYEOF
    if [ ! -f "$_ws/departments/Presentations/.scheduler-readiness.json" ]; then
        warn "_presched($_key): readiness receipt unwritable under $_ws — repair state lives only in this log."
    elif [ "$_status" = "DEGRADED" ]; then
        warn "_presched($_key): repair FAILURE latched in $_ws/departments/Presentations/.scheduler-readiness.json (status DEGRADED) — will retry next run."
    fi
    return "$_rc"
}

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
        # ── VPS: reconcile against the versioned contract (PRES-034). A
        # present name is no longer "already installed" — the existing job
        # is compared (command, root, env, cadence, enabled) and updated in
        # place, or fenced-and-replaced with a rollback record.
        local CHANNEL_AGENT="main"
        if [ -n "${TELEGRAM_DEFAULT_AGENT_CACHED:-}" ]; then
            CHANNEL_AGENT="$TELEGRAM_DEFAULT_AGENT_CACHED"
        fi
        local _poll_command
        printf -v _poll_command 'env OPENCLAW_ROOT=%q OPENCLAW_WORKSPACE_PATH=%q OPENCLAW_WORKSPACE_ROOT=%q PRESENTATION_RUNS_DIR=%q bash %q' "$_poll_root" "$_poll_workspace" "$_poll_workspace" "$_poll_runs_dir" "$POLL_SRC"
        local POLL_PROMPT="[PRESENTATION-INTAKE-POLL] Run the intake-completion poll: $_poll_command . This is an idempotent maintenance scan; it dispatches the deck engine for any intake whose interview completed but whose engine never launched (FIX 61 dispatch lease held during dispatch)."
        local _poll_path="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin"
        if ! _presched_reconcile_cron "$_PRESCHED_POLL_NAME" "$_PRESCHED_POLL_EXPR" "$_PRESCHED_TZ" "$CHANNEL_AGENT" "$POLL_PROMPT" --light-context; then
            warn "FIX 61: intake-poll cron reconcile FAILED — staged intake submissions may sit undispatched. Manual: openclaw cron create --name presentation-intake-poll --agent $CHANNEL_AGENT --cron '*/5 * * * *' --session main --system-event '[PRESENTATION-INTAKE-POLL] bash $POLL_SRC'"
            _rc=1
        else
            case "$_PRESCHED_STATUS" in
                PAUSED_BY_OWNER) success "FIX 61: intake-poll PAUSED_BY_OWNER — deliberately stopped, left stopped (never reactivated)" ;;
                *) success "FIX 61: intake-poll cron reconciled (SILENT main-session, 5-min, no client auto-announce; contract v$_PRESCHED_CONTRACT_VERSION)" ;;
            esac
        fi
        _presched_finish "$_poll_workspace" "intake-poll" "$_poll_root" "$(dirname "$POLL_SRC")" "$POLL_SRC" "$_poll_runs_dir" "$_poll_path" "$_rc" || _rc=$?
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
        # PRES-034 Mac reconcile: the rendered plist is the contract — an
        # already-loaded job with a drifted script path / runs root / cadence
        # is re-rendered above and reloaded here, never trusted by label
        # alone. Record readiness the same way the VPS branch does: HEALTHY
        # when the load itself succeeded (rc 0) OR the label is listed.
        local _poll_plist_path="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$HOME/.npm-global/bin"
        if [ "$_rc" -eq 0 ] || launchctl list 2>/dev/null | grep -q 'com.blackceo.presentation-intake-poll'; then
            _PRESCHED_STATUS="HEALTHY"; _PRESCHED_JOB_ID="com.blackceo.presentation-intake-poll"
            _PRESCHED_NEXT_FIRE="StartInterval:300s"
        else
            _PRESCHED_STATUS="MISSING"; _PRESCHED_JOB_ID="-"
            _PRESCHED_NEXT_FIRE="StartInterval:300s"
        fi
        if command -v _presched_finish >/dev/null 2>&1; then
            _presched_finish "$_poll_workspace" "intake-poll" "$_poll_root" "$(dirname "$POLL_SRC")" "$POLL_SRC" "$_poll_runs_dir" "$_poll_plist_path" "$_rc" || _rc=$?
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

    # ── PRESENTATION_SUPERVISE_APPLY — F12c, NOT armed by this installer. ──
    # Passed through ONLY when the operator set it in this process's
    # environment. The renderer additionally PRESERVES a value already present
    # in an installed plist, so a roll can neither arm what an operator did
    # not, nor disarm what they did.
    local _wd_supervise_apply="${PRESENTATION_SUPERVISE_APPLY:-}"
    # A plain word for the log lines. `${x:+A}${x:-B}` would print "A1" when x=1
    # (the :- branch yields the VALUE, not B) — a log that misreports the very
    # setting this whole section exists to be careful about.
    local _wd_supervise_note="report-only (F12c not armed here)"
    [ -n "$_wd_supervise_apply" ] && _wd_supervise_note="APPLY (operator-armed: PRESENTATION_SUPERVISE_APPLY=$_wd_supervise_apply)"

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
        # ── VPS: reconcile against the versioned contract (PRES-034). Same
        # rule as the poller: a present name is compared, not trusted.
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
        local _wd_sched_path="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin"
        if ! _presched_reconcile_cron "$_PRESCHED_WD_NAME" "$_PRESCHED_WD_EXPR" "$_PRESCHED_TZ" "$WD_CHANNEL_AGENT" "$WD_PROMPT" --light-context; then
            warn "F12: presentation-watchdog cron reconcile FAILED — stalled deck runs will not be detected or restarted on this box. Manual: openclaw cron create --name presentation-watchdog --agent $WD_CHANNEL_AGENT --cron '*/10 * * * *' --session main --system-event '[PRESENTATION-WATCHDOG] sh $WD_SRC $_wd_log'"
            _rc=1
        else
            case "$_PRESCHED_STATUS" in
                PAUSED_BY_OWNER) success "F12: presentation-watchdog PAUSED_BY_OWNER — deliberately stopped, left stopped (never reactivated)" ;;
                *) success "F12: presentation-watchdog cron reconciled (SILENT main-session, 10-min, no client auto-announce; supervisor ${_wd_supervise_note}; contract v$_PRESCHED_CONTRACT_VERSION)" ;;
            esac
        fi
        _presched_finish "$_wd_workspace" "watchdog" "$_wd_root" "$(dirname "$WD_SRC")" "$WD_SRC" "$_wd_runs_dir" "$_wd_sched_path" "$_rc" || _rc=$?
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
        if ! python3 - "$WD_TPL" "$WD_PLIST_DST" "$WD_SRC" "$WD_LOG_PATH" "$_wd_path" "$_wd_runs_dir" "$_wd_notify_cmd" "$_wd_owner_chat" "$_wd_supervise_apply" "$_wd_root" "$_wd_workspace" <<'PY_RENDER_WATCHDOG_PLIST'
import os
from pathlib import Path
import plistlib
import re
import shlex
import sys
import tempfile

(template, destination, script, log, runtime_path, scan_root, notify,
 owner_chat, supervise_apply, client_root, workspace) = sys.argv[1:]
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

# PRESERVE, NEVER STRIP. An operator arming the supervisor (F12c) or pinning
# an owner chat id edits the INSTALLED plist. A roll that re-rendered from the
# template alone would silently drop both on the next update -- the installer
# would be undoing the operator's live configuration. So a value this run did
# not resolve is carried forward from the plist already on disk, and only an
# explicit value in THIS process's environment overrides it.
previous = {}
try:
    with open(destination, 'rb') as stream:
        previous = plistlib.load(stream).get('EnvironmentVariables', {}) or {}
except (FileNotFoundError, ValueError, OSError):
    previous = {}

for name, resolved in (('OWNER_CHAT_ID', owner_chat),
                       ('PRESENTATION_SUPERVISE_APPLY', supervise_apply)):
    carried = str(previous.get(name, '') or '')
    if resolved:
        env[name] = resolved
    elif carried:
        env[name] = carried
    else:
        env.pop(name, None)

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
        # PRES-034 Mac reconcile: same contract rule as the poller — the
        # re-rendered plist is the source of truth, never the label alone.
        if [ "$_rc" -eq 0 ] || launchctl list 2>/dev/null | grep -q 'com.presentations.watchdog'; then
            _PRESCHED_STATUS="HEALTHY"; _PRESCHED_JOB_ID="com.presentations.watchdog"
            _PRESCHED_NEXT_FIRE="StartInterval:600s"
        else
            _PRESCHED_STATUS="MISSING"; _PRESCHED_JOB_ID="-"
            _PRESCHED_NEXT_FIRE="StartInterval:600s"
        fi
        if command -v _presched_finish >/dev/null 2>&1; then
            _presched_finish "$_wd_workspace" "watchdog" "$_wd_root" "$(dirname "$WD_SRC")" "$WD_SRC" "$_wd_runs_dir" "$_wd_path" "$_rc" || _rc=$?
        fi
    fi

    return "$_rc"
}

# ════════════════════════════════════════════════════════════════════════════
# F12b — the one entry point a ROLL calls.
# ════════════════════════════════════════════════════════════════════════════
# Both installers are idempotent (the cron branch reconciles a present or
# tombstoned job against contract v1 — IN_SYNC untouched, drifted edited in
# place, operator-paused never reactivated; the launchd branch re-renders and
# reloads the SAME label),
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
