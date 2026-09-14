#!/usr/bin/env bash
# shared-utils/rr-readiness.sh — RR-028 Rescue Receiver readiness engine.
# ============================================================================
# ONE implementation of "is this box actually enrolled, scheduled and proven
# ready to receive Rescue Rangers work?" — with an EXPLICIT state and an
# EXPLICIT reason for every outcome, and a readback for every write.
#
# WHY THIS EXISTS (RR-028): enrollment and cron reconciliation reported PROSE.
#   * `UNENROLLED` existed only as a comment in wire.sh; the four-state
#     vocabulary (UNENROLLED / ENROLLED_PENDING / SCHEDULED / VERIFIED) existed
#     nowhere in this repo.
#   * Presence was decided by `cron list --json | grep '"name": "..."'` — a
#     TEXT match that proves nothing about the command, the schedule, the
#     enabled bit or the delivery flags, so a job registered with a stale poll
#     path, the wrong cadence, or delivery left ON looked identical to a
#     correct one.
#   * Nothing separated "files were installed" (the installer's claim) from
#     "the receiver is READY" (a claim about the intended runtime that only a
#     safe test claim's receipt can support).
#
# THE CONTRACT (RR-028 required behaviours, numbered as in the spec):
#   1. FOUR EXPLICIT STATES — UNENROLLED, ENROLLED_PENDING, SCHEDULED, VERIFIED
#      — each with an explicit machine-readable reason code and a human detail.
#      There is no implicit success: anything unproven is ENROLLED_PENDING
#      naming exactly what is missing.
#   2. VERSION-INDEPENDENT RECONCILIATION — no input here is a software
#      version (not ONBOARDING_VERSION, not RECEIVER_VERSION, not
#      skill-version.txt, not a `.wired-<version>` sentinel). A `.wired-*`
#      sentinel says "files were copied at version X" and is NEVER evidence
#      that a cron exists, so the verdict is the same across a version change.
#   3. KEYED BY DESIRED-CONFIG DIGEST — the desired configuration (box slug,
#      receiver URL, cron name, schedule, command, enabled bit, delivery mode
#      and a SALTED commitment to the token) hashes to ONE digest. Readiness
#      and every verified receipt are keyed by it, so a changed desired config
#      can never inherit an old verdict.
#   4. REQUIRED RESOLUTIONS — slug, token and URL from the enrollment store,
#      plus the runtime requirements: the shared dotenv PARSER, curl, base64,
#      the OpenClaw CLI and node (plus the JSON reader and hasher this engine
#      itself needs). Anything unresolved is named by NAME.
#   5. READBACK, NEVER ASSUME — after every write the job is read back from the
#      CLI's own JSON AND, when a state DB resolves, from the gateway's stored
#      `cron_jobs.job_json` — the only view that shows a DISABLED job.
#      Duplicates, command, schedule, enabled state and delivery flags are all
#      compared. A write that does not read back is NEVER reported as success.
#   6. ARGV-SAFE INVOCATION + SHARED DESCRIPTOR — every external command runs
#      as an argv vector through rrr_argv_run ("$@"); there is no eval, no
#      `sh -c`, and no re-split string anywhere in the RR-028 path. The
#      host/container identity comes from shared-utils/oc-env-descriptor.sh
#      (the ONE descriptor) and the runtime id a receipt is bound to is
#      derived from it.
#   7. INSTALLER SUCCESS != READY — SCHEDULED is reachable on readback alone;
#      VERIFIED additionally requires a receipt from a SAFE TEST CLAIM that
#      ran in the intended runtime, carried no credential in argv, started no
#      agent turn, acked nothing, and came back as a structured no-work answer
#      (RR-008: a bare 2xx is never confirmation).
#
# SECRET DISCIPLINE: this file never prints, logs, echoes or hashes-in-the-
# clear the token. Its only uses are presence and a SALTED commitment inside
# the digest; every diagnostic carries NAMES only.
#
# COVERAGE NOTE (honest limitation): when no state DB resolves, the readback is
# CLI-only and a DISABLED job is invisible to `cron list --json` (the defect
# shared-utils/cron-lib.sh documents). That case is REPORTED as `cli-only` in
# the JSON report — it is never presented as a DB-proven absence.
#
# POSIX sh, safe to source under `set -u`; bash 3.2 compatible (no arrays, no
# ${var,,}, no local). Never executes the enrollment store. Never exports a
# credential.
#
# Sourced by: 65-rescue-receiver/wire.sh, 65-rescue-receiver/rr-readiness.sh.
# Tested by:  tests/rescue/RR-028/.
# ============================================================================

# ---- defaults (overridable by the caller/fixtures) -------------------------
RRR_NAME="${RRR_NAME:-rescue-rr-box-poll}"
RRR_LEGACY_NAME="${RRR_LEGACY_NAME:-rescue-rangers-poll}"
RRR_SCHEDULE="${RRR_SCHEDULE:-*/2 * * * *}"
RRR_DELIVERY="${RRR_DELIVERY:-none}"
RRR_ENABLED="${RRR_ENABLED:-1}"
RRR_STATE_NAME="${RRR_STATE_NAME:-rr-receiver}"
RRR_RS="$(printf '\036')"          # empty-field sentinel (see rrr_json_rows)

# ---- resolved state --------------------------------------------------------
RRR_ROOT=""; RRR_SECRETS=""; RRR_POLL=""; RRR_STATE_DIR=""
RRR_OPENCLAW_BIN=""; RRR_NODE_BIN=""; RRR_DB=""
RRR_REQ_PARSER=""; RRR_REQ_CURL=""; RRR_REQ_BASE64=""
RRR_REQ_OPENCLAW=""; RRR_REQ_NODE=""; RRR_REQ_JSON=""; RRR_REQ_SHA=""
RRR_MISSING_REQS=""
RRR_STORE_STATE=""; RRR_MISSING=""; RRR_MALFORMED=0
RRR_HAS_URL=0; RRR_HAS_TOKEN=0; RRR_HAS_SLUG=0
RRR_URL=""; RRR_SLUG=""; RRR_TOKEN_COMMIT=""
RRR_SALT_STATE=""; RRR_DIGEST=""; RRR_DIGEST_STATE=""
RRR_RUNTIME_ID=""; RRR_RUNTIME_STATE=""; RRR_PLATFORM=""; RRR_TARGET_MODE=""; RRR_TARGET_ID=""
RRR_RB_STATE=""; RRR_JOBS=""; RRR_DB_STATE="none"; RRR_COVERAGE="none"
RRR_CRON_STATE=""; RRR_CRON_COUNT=0; RRR_CRON_ID=""
RRR_CRON_SCHEDULE=""; RRR_CRON_COMMAND=""; RRR_CRON_ENABLED=""; RRR_CRON_DELIVERY=""
RRR_CRON_MISMATCH=""; RRR_CRON_UNOBS=""; RRR_CRON_DISAGREE=""
RRR_CRON_IDS=""; RRR_CRON_MATCH_IDS=""; RRR_CRON_DISABLED_DIRECT=0; RRR_CRON_SOURCES=""
RRR_TOMBSTONED=0
RRR_RECEIPT_STATE=""; RRR_RECEIPT_AT=""; RRR_RECEIPT_RUNTIME=""; RRR_RECEIPT_DETAIL=""
RRR_RECONCILE_STATE=""; RRR_RECONCILE_ACTION=""; RRR_RECONCILE_RC=0
RRR_ARGV_RC=0
RRR_STATE=""; RRR_REASON=""; RRR_DETAIL=""

# ---------------------------------------------------------------------------
# rrr_sha256 <text> -> hex digest on stdout, rc 1 when no hasher exists.
# ---------------------------------------------------------------------------
rrr_sha256() {
    _rrr_sh_in="$1"
    if command -v shasum >/dev/null 2>&1; then
        printf '%s' "$_rrr_sh_in" | shasum -a 256 2>/dev/null | awk '{print $1}'
        return 0
    fi
    if command -v sha256sum >/dev/null 2>&1; then
        printf '%s' "$_rrr_sh_in" | sha256sum 2>/dev/null | awk '{print $1}'
        return 0
    fi
    if command -v openssl >/dev/null 2>&1; then
        printf '%s' "$_rrr_sh_in" | openssl dgst -sha256 2>/dev/null | awk '{print $NF}'
        return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        printf '%s' "$_rrr_sh_in" | python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())' 2>/dev/null
        return 0
    fi
    return 1
}

rrr_now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "1970-01-01T00:00:00Z"; }

# ---------------------------------------------------------------------------
# rrr_argv_run <stdout-file> <stderr-file> <cmd> [arg ...]
#
# THE argv-safe invocation primitive. Every external command in this module and
# its callers goes through here (or through an identical "$@" call), so an
# argument containing spaces, globs, `;`, `$(...)` or backticks is ONE argv
# element and can never be word-split or executed as shell. There is no eval,
# no `sh -c`, and no string re-splitting anywhere in the RR-028 path.
# Sets RRR_ARGV_RC.
# ---------------------------------------------------------------------------
rrr_argv_run() {
    _rrr_av_out="$1"; shift
    _rrr_av_err="$1"; shift
    RRR_ARGV_RC=0
    "$@" >"$_rrr_av_out" 2>"$_rrr_av_err" || RRR_ARGV_RC=$?
    return "$RRR_ARGV_RC"
}

# ---------------------------------------------------------------------------
# JSON reading. jq first, python3 second — the same ladder the receiver uses.
# With neither, RRR_REQ_JSON is unresolved and readback reports UNOBSERVABLE
# rather than guessing.
# ---------------------------------------------------------------------------
rrr_json_get() {  # rrr_json_get <json> <dotted.path>
    _rrr_jg_json="$1"; _rrr_jg_path="$2"
    [ -n "$_rrr_jg_json" ] || return 0
    if command -v jq >/dev/null 2>&1; then
        printf '%s' "$_rrr_jg_json" | jq -r --arg p "$_rrr_jg_path" '
          ($p | split(".")) as $k | getpath($k)
          | if . == null then "" elif type == "string" then . else tostring end' 2>/dev/null
        return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        printf '%s' "$_rrr_jg_json" | RRR_JG_PATH="$_rrr_jg_path" python3 -c '
import json, os, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
o = d
for k in os.environ.get("RRR_JG_PATH", "").split("."):
    if not k:
        continue
    if isinstance(o, dict) and k in o:
        o = o[k]
    else:
        sys.exit(0)
if o is None:
    sys.exit(0)
if isinstance(o, bool):
    print("true" if o else "false")
elif isinstance(o, (int, float)):
    print(o)
elif isinstance(o, str):
    print(o)
' 2>/dev/null
        return 0
    fi
    return 0
}

# ---------------------------------------------------------------------------
# rrr_json_rows <json> <exact-name> <source>
#
# Prints ONE RS-delimited row per job whose name EXACTLY equals <exact-name>
# (JSON exact match — never a text-table substring, the truncation
# false-positive class shared-utils/cron-lib.sh documents):
#   source RS id RS enabled RS schedule RS command RS delivery RS unobservable
# An RS sentinel stands for "empty" so `read`/field splitting cannot collapse
# columns. "unobservable" lists the fields this view does not expose AT ALL
# (which is a different fact from a field that is present and wrong).
# ---------------------------------------------------------------------------
rrr_json_rows() {
    _rrr_jr_json="$1"; _rrr_jr_name="$2"; _rrr_jr_src="$3"
    [ -n "$_rrr_jr_json" ] || return 0
    command -v python3 >/dev/null 2>&1 || return 0
    printf '%s' "$_rrr_jr_json" | RRR_JR_NAME="$_rrr_jr_name" RRR_JR_SRC="$_rrr_jr_src" python3 -c '
import json, os, sys

RS = "\x1e"
name = os.environ.get("RRR_JR_NAME", "")
src = os.environ.get("RRR_JR_SRC", "")

def clean(v):
    if v is None:
        return ""
    return str(v).replace("\t", " ").replace("\n", " ").replace("\r", " ").replace(RS, " ")

def g(d, *ks):
    o = d
    for k in ks:
        if isinstance(o, dict) and k in o:
            o = o[k]
        else:
            return None
    return o

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
# Three accepted shapes: a bare array of jobs (some CLI builds), a
# {"jobs":[...]} envelope (the documented CLI shape), or ONE job object — which
# is exactly what each `cron_jobs.job_json` row is in the gateway store. The DB
# view is the only one that shows a disabled job, so failing to read a bare job
# object would silently blind the enabled-state check.
if isinstance(data, list):
    jobs = data
elif isinstance(data, dict) and isinstance(data.get("jobs"), list):
    jobs = data["jobs"]
elif isinstance(data, dict) and "name" in data:
    jobs = [data]
else:
    jobs = []
if not isinstance(jobs, list):
    sys.exit(0)

for j in jobs:
    if not isinstance(j, dict) or j.get("name") != name:
        continue
    jid = j.get("id") or j.get("jobId") or j.get("job_id") or ""
    en = j.get("enabled")
    if en is None and isinstance(j.get("disabled"), bool):
        en = not j["disabled"]
    en_s = ("true" if en else "false") if isinstance(en, bool) else ""
    sch = g(j, "schedule", "expr")
    if not (isinstance(sch, str) and sch):
        kind = g(j, "schedule", "kind")
        if isinstance(kind, str) and kind:
            extra = g(j, "schedule", "everyMs")
            # A non-cron schedule is a VISIBLE value, never silently empty: an
            # unreadable field must not be able to look like a match.
            sch = "kind=" + kind + ((":" + str(extra)) if extra is not None else "")
        else:
            alt = j.get("cron") or j.get("scheduleExpr")
            sch = alt if isinstance(alt, str) else ""
    cmd = g(j, "payload", "command")
    if not (isinstance(cmd, str) and cmd):
        alt = j.get("command")
        if isinstance(alt, str) and alt:
            cmd = alt
        else:
            pk = g(j, "payload", "kind")
            cmd = ("kind=" + pk) if isinstance(pk, str) and pk else ""
    dl = g(j, "delivery", "mode")
    if not (isinstance(dl, str) and dl):
        alt = j.get("deliver")
        if isinstance(alt, bool):
            dl = "announce" if alt else "none"
        elif isinstance(alt, str) and alt:
            dl = alt
        else:
            nd = j.get("noDeliver")
            if isinstance(nd, bool):
                dl = "none" if nd else "announce"
    miss = []
    if en_s == "":
        miss.append("enabled")
    if not sch:
        miss.append("schedule")
    if not cmd:
        miss.append("command")
    if not dl:
        miss.append("delivery")
    print(RS.join([clean(src), clean(str(jid)), clean(en_s), clean(sch), clean(cmd), clean(dl), clean(",".join(miss))]))
' 2>/dev/null
    return 0
}

# ---------------------------------------------------------------------------
# Runtime resolution — the ladder wire.sh already used for the CLI, extended
# with the other requirements the spec names (parser/curl/base64/node) so
# "enrolled" can never be reported on a box that cannot run the poll.
# ---------------------------------------------------------------------------
rrr_tools_resolve() {
    RRR_MISSING_REQS=""
    if command -v rescue_env_get >/dev/null 2>&1 && command -v rescue_env_parse >/dev/null 2>&1; then
        RRR_REQ_PARSER="ok"
    else
        RRR_REQ_PARSER="missing"; RRR_MISSING_REQS="$RRR_MISSING_REQS parser"
    fi
    if command -v curl >/dev/null 2>&1; then RRR_REQ_CURL="ok"; else RRR_REQ_CURL="missing"; RRR_MISSING_REQS="$RRR_MISSING_REQS curl"; fi
    if command -v base64 >/dev/null 2>&1; then RRR_REQ_BASE64="ok"; else RRR_REQ_BASE64="missing"; RRR_MISSING_REQS="$RRR_MISSING_REQS base64"; fi
    if command -v jq >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1; then RRR_REQ_JSON="ok"; else RRR_REQ_JSON="missing"; RRR_MISSING_REQS="$RRR_MISSING_REQS json_reader"; fi
    if command -v shasum >/dev/null 2>&1 || command -v sha256sum >/dev/null 2>&1 \
       || command -v openssl >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1; then
        RRR_REQ_SHA="ok"
    else
        RRR_REQ_SHA="missing"; RRR_MISSING_REQS="$RRR_MISSING_REQS hasher"
    fi
    # OpenClaw CLI: an explicit override wins, but ONLY if it actually
    # resolves (a fixture hook that silently fell back to PATH could not be
    # used to prove the unresolved case). Then PATH, then the standard install
    # locations (the updater's stripped PATH is why this ladder exists).
    RRR_OPENCLAW_BIN=""
    if [ -n "${RRR_OPENCLAW_OVERRIDE:-}" ]; then
        if [ -x "$RRR_OPENCLAW_OVERRIDE" ]; then RRR_OPENCLAW_BIN="$RRR_OPENCLAW_OVERRIDE"
        elif command -v "$RRR_OPENCLAW_OVERRIDE" >/dev/null 2>&1; then RRR_OPENCLAW_BIN="$RRR_OPENCLAW_OVERRIDE"
        fi
    elif command -v openclaw >/dev/null 2>&1; then
        RRR_OPENCLAW_BIN="openclaw"
    elif [ -x /opt/homebrew/bin/openclaw ]; then
        RRR_OPENCLAW_BIN="/opt/homebrew/bin/openclaw"
    elif [ -x /usr/local/bin/openclaw ]; then
        RRR_OPENCLAW_BIN="/usr/local/bin/openclaw"
    elif [ -x "$HOME/.local/bin/openclaw" ]; then
        RRR_OPENCLAW_BIN="$HOME/.local/bin/openclaw"
    fi
    if [ -n "$RRR_OPENCLAW_BIN" ]; then RRR_REQ_OPENCLAW="ok"; else RRR_REQ_OPENCLAW="missing"; RRR_MISSING_REQS="$RRR_MISSING_REQS openclaw"; fi
    # node: PATH, then beside the CLI (where the toolchain's own node symlink
    # lives — the CLI is a `#!/usr/bin/env node` script), then standard paths.
    RRR_NODE_BIN=""
    if [ -n "${RRR_NODE_OVERRIDE:-}" ]; then
        if [ -x "$RRR_NODE_OVERRIDE" ]; then RRR_NODE_BIN="$RRR_NODE_OVERRIDE"
        elif command -v "$RRR_NODE_OVERRIDE" >/dev/null 2>&1; then RRR_NODE_BIN="$RRR_NODE_OVERRIDE"
        fi
    elif command -v node >/dev/null 2>&1; then
        RRR_NODE_BIN="node"
    else
        for _rrr_nc in /opt/homebrew/bin/node /usr/local/bin/node "$HOME/.local/bin/node" /usr/bin/node; do
            [ -x "$_rrr_nc" ] && { RRR_NODE_BIN="$_rrr_nc"; break; }
        done
        if [ -z "$RRR_NODE_BIN" ] && [ -n "$RRR_OPENCLAW_BIN" ]; then
            case "$RRR_OPENCLAW_BIN" in
                */*) [ -x "${RRR_OPENCLAW_BIN%/*}/node" ] && RRR_NODE_BIN="${RRR_OPENCLAW_BIN%/*}/node" ;;
            esac
        fi
    fi
    if [ -n "$RRR_NODE_BIN" ]; then RRR_REQ_NODE="ok"; else RRR_REQ_NODE="missing"; RRR_MISSING_REQS="$RRR_MISSING_REQS node"; fi
    RRR_MISSING_REQS="${RRR_MISSING_REQS# }"
}

# ---------------------------------------------------------------------------
# The intended-RUNTIME identity. A readiness receipt is bound to this string,
# so a probe run in the WRONG runtime (an operator shell on the host while the
# cron runs inside the container, a different root/CLI/node) can never verify
# the runtime the cron actually lives in. Uses the shared descriptor's
# platform/target when loaded, else explicit OC_* overrides, else "unresolved"
# — never a guess.
# ---------------------------------------------------------------------------
rrr_runtime_id() {
    RRR_PLATFORM="${OCD_PLATFORM:-${OC_PLATFORM:-unresolved}}"
    RRR_TARGET_MODE="${OCD_TARGET_MODE:-${OC_TARGET_MODE:-unresolved}}"
    RRR_TARGET_ID="${OCD_TARGET_ID:-${OC_TARGET_ID:-unresolved}}"
    if [ "$RRR_PLATFORM" = "unresolved" ] || [ "$RRR_TARGET_MODE" = "unresolved" ]; then
        RRR_RUNTIME_STATE="unresolved"; RRR_RUNTIME_ID=""
        return 1
    fi
    _rrr_ri_oc="${RRR_OPENCLAW_BIN:-none}"
    case "$_rrr_ri_oc" in
        */*) _rrr_ri_oc="$(cd "$(dirname "$_rrr_ri_oc")" 2>/dev/null && pwd)/$(basename "$_rrr_ri_oc")" ;;
        *) _rrr_ri_oc="path:$_rrr_ri_oc" ;;
    esac
    _rrr_ri_canon="rr028-runtime/1
platform=$RRR_PLATFORM
target_mode=$RRR_TARGET_MODE
target_id=$RRR_TARGET_ID
root=${RRR_ROOT:-none}
poll=${RRR_POLL:-none}
openclaw=$_rrr_ri_oc
node=${RRR_NODE_BIN:-none}"
    RRR_RUNTIME_ID="$(rrr_sha256 "$_rrr_ri_canon" 2>/dev/null)"
    if [ -z "$RRR_RUNTIME_ID" ]; then
        RRR_RUNTIME_STATE="unresolved"; return 1
    fi
    RRR_RUNTIME_ID="$(printf '%s' "$RRR_RUNTIME_ID" | cut -c1-32)"
    RRR_RUNTIME_STATE="resolved"
    return 0
}

# ---------------------------------------------------------------------------
# Enrollment resolution. Reads ONLY the three required rescue values through
# the shared parser (RR-027). Values land in NON-exported variables and are
# never printed; the token is additionally reduced to a SALTED commitment so a
# token rotation changes the digest without the token ever being echoed.
# ---------------------------------------------------------------------------
rrr_enrollment_resolve() {
    _rrr_er_store="$1"
    RRR_STORE_STATE=""; RRR_MISSING=""; RRR_MALFORMED=0
    RRR_HAS_URL=0; RRR_HAS_TOKEN=0; RRR_HAS_SLUG=0
    RRR_URL=""; RRR_SLUG=""; RRR_TOKEN_COMMIT=""
    if [ ! -e "$_rrr_er_store" ]; then RRR_STORE_STATE="missing"; return 0; fi
    if [ ! -f "$_rrr_er_store" ] || [ ! -r "$_rrr_er_store" ]; then RRR_STORE_STATE="unreadable"; return 0; fi
    if ! command -v rescue_env_get >/dev/null 2>&1; then RRR_STORE_STATE="parser_unresolved"; return 0; fi
    _rrr_er_tok=""
    _rrr_er_val=""; _rrr_er_rc=0
    _rrr_er_val="$(rescue_env_get "$_rrr_er_store" RR_RECEIVER_URL 2>/dev/null)"; _rrr_er_rc=$?
    [ "$_rrr_er_rc" = "3" ] && RRR_MALFORMED=1
    [ "$_rrr_er_rc" = "2" ] && { RRR_STORE_STATE="unreadable"; return 0; }
    RRR_URL="$_rrr_er_val"
    _rrr_er_val="$(rescue_env_get "$_rrr_er_store" RR_BOX_TOKEN 2>/dev/null)"; _rrr_er_rc=$?
    [ "$_rrr_er_rc" = "3" ] && RRR_MALFORMED=1
    _rrr_er_tok="$_rrr_er_val"
    _rrr_er_val="$(rescue_env_get "$_rrr_er_store" RR_BOX_SLUG 2>/dev/null)"; _rrr_er_rc=$?
    [ "$_rrr_er_rc" = "3" ] && RRR_MALFORMED=1
    RRR_SLUG="$_rrr_er_val"
    RRR_STORE_STATE="ok"
    [ -n "$RRR_URL" ]  && RRR_HAS_URL=1
    [ -n "$_rrr_er_tok" ] && RRR_HAS_TOKEN=1
    [ -n "$RRR_SLUG" ] && RRR_HAS_SLUG=1
    [ "$RRR_HAS_URL" = "1" ]   || RRR_MISSING="$RRR_MISSING RR_RECEIVER_URL"
    [ "$RRR_HAS_TOKEN" = "1" ] || RRR_MISSING="$RRR_MISSING RR_BOX_TOKEN"
    [ "$RRR_HAS_SLUG" = "1" ]  || RRR_MISSING="$RRR_MISSING RR_BOX_SLUG"
    RRR_MISSING="${RRR_MISSING# }"
    # Salted token commitment: a per-box 0600 salt means the digest cannot be
    # used to test token guesses offline without the box's own state dir.
    if [ "$RRR_HAS_TOKEN" = "1" ]; then
        RRR_SALT_STATE="absent"
        _rrr_er_salt=""
        if [ -n "${RRR_STATE_DIR:-}" ]; then
            _rrr_er_saltfile="$RRR_STATE_DIR/readiness/.salt"
            if [ ! -s "$_rrr_er_saltfile" ]; then
                ( umask 077; mkdir -p "$RRR_STATE_DIR/readiness" 2>/dev/null ) || true
                if [ -r /dev/urandom ]; then
                    ( umask 077; dd if=/dev/urandom bs=32 count=1 2>/dev/null | od -An -tx1 | tr -d ' \n' > "$_rrr_er_saltfile" ) 2>/dev/null || true
                fi
                [ -s "$_rrr_er_saltfile" ] || rm -f "$_rrr_er_saltfile" 2>/dev/null || true
                chmod 600 "$_rrr_er_saltfile" 2>/dev/null || true
            fi
            if [ -s "$_rrr_er_saltfile" ]; then
                _rrr_er_salt="$(cat "$_rrr_er_saltfile" 2>/dev/null)"
                [ -n "$_rrr_er_salt" ] && RRR_SALT_STATE="present"
            fi
        fi
        RRR_TOKEN_COMMIT="$(rrr_sha256 "${_rrr_er_salt}${_rrr_er_tok}" 2>/dev/null)"
        if [ -n "$RRR_TOKEN_COMMIT" ]; then
            [ "$RRR_SALT_STATE" = "present" ] || RRR_SALT_STATE="absent"
            RRR_TOKEN_COMMIT="sha256-${RRR_SALT_STATE}:$(printf '%s' "$RRR_TOKEN_COMMIT" | cut -c1-24)"
        else
            RRR_TOKEN_COMMIT="present:unhashed"
        fi
    fi
    _rrr_er_tok=""
    return 0
}

# ---------------------------------------------------------------------------
# rrr_desired_digest — the desired-config digest. NO VERSION INPUTS.
# ---------------------------------------------------------------------------
rrr_desired_digest() {
    RRR_DIGEST=""; RRR_DIGEST_STATE=""
    [ "$RRR_STORE_STATE" = "ok" ] || { RRR_DIGEST_STATE="enrollment_unresolved"; return 1; }
    [ -z "$RRR_MISSING" ] || { RRR_DIGEST_STATE="enrollment_incomplete"; return 1; }
    [ "$RRR_REQ_SHA" = "ok" ] || { RRR_DIGEST_STATE="hasher_unresolved"; return 1; }
    _rrr_dd_canon="rr028-desired/1
name=$RRR_NAME
schedule=$RRR_SCHEDULE
command=sh $RRR_POLL
enabled=$RRR_ENABLED
delivery=$RRR_DELIVERY
slug=$RRR_SLUG
url=$RRR_URL
token=$RRR_TOKEN_COMMIT"
    RRR_DIGEST="$(rrr_sha256 "$_rrr_dd_canon" 2>/dev/null)"
    if [ -z "$RRR_DIGEST" ]; then RRR_DIGEST_STATE="hasher_unresolved"; return 1; fi
    RRR_DIGEST="$(printf '%s' "$RRR_DIGEST" | cut -c1-32)"
    RRR_DIGEST_STATE="resolved"
    return 0
}

# ---------------------------------------------------------------------------
# Cron readback. TWO views, never one:
#   cli — `openclaw cron list --json` (with a feature-detected full-status flag)
#   db  — the gateway's stored `cron_jobs.job_json` (the ONLY view that shows a
#         DISABLED job; `cron list --json` is documented to hide them).
# RRR_DB is optional: with no readable DB the readback is CLI-only and the
# report SAYS so (RRR_COVERAGE) — never a silent single-view claim.
# ---------------------------------------------------------------------------
rrr_cron_readback() {
    RRR_RB_STATE=""; RRR_JOBS=""; RRR_DB_STATE="none"; RRR_CRON_SOURCES=""; RRR_COVERAGE="none"
    _rrr_rb_tmp="$(mktemp "${TMPDIR:-/tmp}/rr028-readback.XXXXXX" 2>/dev/null)" || {
        RRR_RB_STATE="unreadable"; return 1; }
    # ---- CLI view ----
    _rrr_rb_cli_ok=0
    if [ "$RRR_REQ_OPENCLAW" != "ok" ]; then
        RRR_RB_STATE="cli_unresolved"
    else
        _rrr_rb_flags=""
        rrr_argv_run "$_rrr_rb_tmp.help" "$_rrr_rb_tmp.err" "$RRR_OPENCLAW_BIN" cron list --help || true
        _rrr_rb_help="$(cat "$_rrr_rb_tmp.help" 2>/dev/null)"
        for _rrr_rb_c in --all --include-disabled --show-disabled; do
            case "$_rrr_rb_help" in
                *"$_rrr_rb_c"*) _rrr_rb_flags="$_rrr_rb_c"; break ;;
            esac
        done
        if [ -n "$_rrr_rb_flags" ]; then
            rrr_argv_run "$_rrr_rb_tmp.cli" "$_rrr_rb_tmp.err" "$RRR_OPENCLAW_BIN" cron list --json "$_rrr_rb_flags" || true
        else
            rrr_argv_run "$_rrr_rb_tmp.cli" "$_rrr_rb_tmp.err" "$RRR_OPENCLAW_BIN" cron list --json || true
        fi
        if [ -s "$_rrr_rb_tmp.cli" ]; then
            RRR_JOBS="$(rrr_json_rows "$(cat "$_rrr_rb_tmp.cli" 2>/dev/null)" "$RRR_NAME" "cli")"
            _rrr_rb_cli_ok=1
            RRR_RB_STATE="ok"
        else
            RRR_RB_STATE="cli_unreadable"
        fi
    fi
    # ---- DB view (authoritative, and the only one that shows disabled jobs) --
    _rrr_rb_db_ok=0
    if [ -n "${RRR_DB:-}" ] && [ -f "$RRR_DB" ] && [ -s "$RRR_DB" ] && command -v sqlite3 >/dev/null 2>&1 \
       && command -v python3 >/dev/null 2>&1; then
        _rrr_rb_sqlrc=0
        _rrr_rb_rows="$(sqlite3 -readonly "$RRR_DB" "select job_json from cron_jobs;" 2>"$_rrr_rb_tmp.err")" || _rrr_rb_sqlrc=$?
        if [ "$_rrr_rb_sqlrc" -eq 0 ]; then
            RRR_DB_STATE="ok"; _rrr_rb_db_ok=1
            _rrr_rb_dbrows=""
            _rrr_rb_oldifs="$IFS"
            IFS='
'
            for _rrr_rb_line in $_rrr_rb_rows; do
                [ -n "$_rrr_rb_line" ] || continue
                _rrr_rb_one="$(rrr_json_rows "$_rrr_rb_line" "$RRR_NAME" "db")"
                [ -n "$_rrr_rb_one" ] && _rrr_rb_dbrows="$_rrr_rb_dbrows$_rrr_rb_one
"
            done
            IFS="$_rrr_rb_oldifs"
            _rrr_rb_dbrows="$(printf '%s' "$_rrr_rb_dbrows" | grep -v '^$' 2>/dev/null || true)"
            if [ -n "$_rrr_rb_dbrows" ]; then
                if [ -n "$RRR_JOBS" ]; then
                    RRR_JOBS="$RRR_JOBS
$_rrr_rb_dbrows"
                else
                    RRR_JOBS="$_rrr_rb_dbrows"
                fi
            fi
        else
            RRR_DB_STATE="unreadable"
        fi
    elif [ -n "${RRR_DB:-}" ]; then
        RRR_DB_STATE="unavailable"
    fi
    RRR_JOBS="$(printf '%s\n' "$RRR_JOBS" | grep -v '^[[:space:]]*$' 2>/dev/null || true)"
    rm -f "$_rrr_rb_tmp" "$_rrr_rb_tmp.cli" "$_rrr_rb_tmp.err" "$_rrr_rb_tmp.help" 2>/dev/null || true
    [ "$_rrr_rb_cli_ok" = "1" ] && RRR_CRON_SOURCES="cli"
    [ "$_rrr_rb_db_ok" = "1" ] && RRR_CRON_SOURCES="${RRR_CRON_SOURCES:+$RRR_CRON_SOURCES,}db"
    if [ "$_rrr_rb_db_ok" = "1" ] && [ "$_rrr_rb_cli_ok" = "1" ]; then RRR_COVERAGE="cli+db"
    elif [ "$_rrr_rb_db_ok" = "1" ]; then RRR_COVERAGE="db-only"
    elif [ "$_rrr_rb_cli_ok" = "1" ]; then RRR_COVERAGE="cli-only"
    else RRR_COVERAGE="none"; fi
    if [ -n "$RRR_JOBS" ] || [ "$_rrr_rb_cli_ok" = "1" ] || [ "$_rrr_rb_db_ok" = "1" ]; then
        return 0
    fi
    [ -n "$RRR_RB_STATE" ] || RRR_RB_STATE="unreadable"
    return 1
}

# rrr_cron_eval — compare the observed rows against the desired config.
# RRR_CRON_STATE: absent | cli_only_absent | duplicate | mismatch | single |
#                 unreadable | unresolved
rrr_cron_eval() {
    RRR_CRON_STATE=""; RRR_CRON_MISMATCH=""; RRR_CRON_UNOBS=""; RRR_CRON_DISAGREE=""
    RRR_CRON_COUNT=0; RRR_CRON_ID=""; RRR_CRON_IDS=""; RRR_CRON_MATCH_IDS=""
    RRR_CRON_SCHEDULE=""; RRR_CRON_COMMAND=""; RRR_CRON_ENABLED=""; RRR_CRON_DELIVERY=""
    RRR_CRON_DISABLED_DIRECT=0
    _rrr_ce_wantcmd="sh $RRR_POLL"
    _rrr_ce_seen=""
    _rrr_ce_first_id=""; _rrr_ce_first_src=""; _rrr_ce_first_sch=""; _rrr_ce_first_cmd=""
    _rrr_ce_first_en=""; _rrr_ce_first_dl=""
    _rrr_ce_oldifs="$IFS"
    IFS='
'
    for _rrr_ce_row in $RRR_JOBS; do
        IFS="$_rrr_ce_oldifs"
        if [ -z "$_rrr_ce_row" ]; then IFS='
'; continue; fi
        _rrr_ce_rest="$_rrr_ce_row"
        _rrr_ce_src="${_rrr_ce_rest%%$RRR_RS*}"
        _rrr_ce_rest="${_rrr_ce_rest#*$RRR_RS}"
        _rrr_ce_id="${_rrr_ce_rest%%$RRR_RS*}"
        _rrr_ce_rest="${_rrr_ce_rest#*$RRR_RS}"
        _rrr_ce_en="${_rrr_ce_rest%%$RRR_RS*}"
        _rrr_ce_rest="${_rrr_ce_rest#*$RRR_RS}"
        _rrr_ce_sch="${_rrr_ce_rest%%$RRR_RS*}"
        _rrr_ce_rest="${_rrr_ce_rest#*$RRR_RS}"
        _rrr_ce_cmd="${_rrr_ce_rest%%$RRR_RS*}"
        _rrr_ce_rest="${_rrr_ce_rest#*$RRR_RS}"
        _rrr_ce_dl="${_rrr_ce_rest%%$RRR_RS*}"
        _rrr_ce_rest="${_rrr_ce_rest#*$RRR_RS}"
        _rrr_ce_miss="$_rrr_ce_rest"
        _rrr_ce_id="$(printf '%s' "$_rrr_ce_id" | tr -d "$RRR_RS")"
        [ -n "$_rrr_ce_id" ] || _rrr_ce_id="?${RRR_CRON_COUNT}"
        # unobservable fields (per view)
        if [ -n "$_rrr_ce_miss" ] && [ "$_rrr_ce_miss" != "$RRR_RS" ]; then
            RRR_CRON_UNOBS="${RRR_CRON_UNOBS}${RRR_CRON_UNOBS:+,}$_rrr_ce_miss"
        fi
        # Does THIS row already satisfy the desired config? Used by the dedupe
        # step to keep a good job and remove the strays.
        if [ "$_rrr_ce_sch" = "$RRR_SCHEDULE" ] && [ "$_rrr_ce_cmd" = "sh $RRR_POLL" ] \
           && [ "$_rrr_ce_en" = "true" ] && [ "$_rrr_ce_dl" = "$RRR_DELIVERY" ]; then
            case " $RRR_CRON_MATCH_IDS " in
                *" $_rrr_ce_id "*) : ;;
                *) RRR_CRON_MATCH_IDS="$RRR_CRON_MATCH_IDS $_rrr_ce_id" ;;
            esac
        fi
        case " $_rrr_ce_seen " in
            *" $_rrr_ce_id "*)
                # Same job seen in the other view: cross-check the two views
                # instead of counting it twice. Only two OBSERVED values can
                # disagree — an unobservable field is a coverage gap, not a
                # contradiction.
                if [ "$_rrr_ce_src" != "$_rrr_ce_first_src" ]; then
                    [ "$_rrr_ce_sch" != "$RRR_RS" ] && [ "$_rrr_ce_first_sch" != "$RRR_RS" ] && [ "$_rrr_ce_sch" != "$_rrr_ce_first_sch" ] && RRR_CRON_DISAGREE="${RRR_CRON_DISAGREE}${RRR_CRON_DISAGREE:+,}schedule"
                    [ "$_rrr_ce_cmd" != "$RRR_RS" ] && [ "$_rrr_ce_first_cmd" != "$RRR_RS" ] && [ "$_rrr_ce_cmd" != "$_rrr_ce_first_cmd" ] && RRR_CRON_DISAGREE="${RRR_CRON_DISAGREE}${RRR_CRON_DISAGREE:+,}command"
                    [ "$_rrr_ce_en"  != "$RRR_RS" ] && [ "$_rrr_ce_first_en"  != "$RRR_RS" ] && [ "$_rrr_ce_en"  != "$_rrr_ce_first_en" ]  && RRR_CRON_DISAGREE="${RRR_CRON_DISAGREE}${RRR_CRON_DISAGREE:+,}enabled"
                    [ "$_rrr_ce_dl"  != "$RRR_RS" ] && [ "$_rrr_ce_first_dl"  != "$RRR_RS" ] && [ "$_rrr_ce_dl"  != "$_rrr_ce_first_dl" ]  && RRR_CRON_DISAGREE="${RRR_CRON_DISAGREE}${RRR_CRON_DISAGREE:+,}delivery"
                fi
                ;;
            *)
                _rrr_ce_seen="$_rrr_ce_seen $_rrr_ce_id"
                RRR_CRON_IDS="$RRR_CRON_IDS $_rrr_ce_id"
                RRR_CRON_COUNT=$((RRR_CRON_COUNT + 1))
                if [ -z "$_rrr_ce_first_id" ]; then
                    _rrr_ce_first_id="$_rrr_ce_id"; _rrr_ce_first_src="$_rrr_ce_src"
                    _rrr_ce_first_sch="$_rrr_ce_sch"; _rrr_ce_first_cmd="$_rrr_ce_cmd"
                    _rrr_ce_first_en="$_rrr_ce_en";   _rrr_ce_first_dl="$_rrr_ce_dl"
                fi
                ;;
        esac
        # The DB view is authoritative, so it also wins as the REPORTED row.
        if [ -z "$RRR_CRON_ID" ] || [ "$_rrr_ce_src" = "db" ]; then
            [ -n "$RRR_CRON_ID" ] || RRR_CRON_ID="$_rrr_ce_id"
            [ "$_rrr_ce_src" = "db" ] && RRR_CRON_ID="$_rrr_ce_id"
            [ "$_rrr_ce_sch" != "$RRR_RS" ] && RRR_CRON_SCHEDULE="$_rrr_ce_sch"
            [ "$_rrr_ce_cmd" != "$RRR_RS" ] && RRR_CRON_COMMAND="$_rrr_ce_cmd"
            [ "$_rrr_ce_en"  != "$RRR_RS" ] && RRR_CRON_ENABLED="$_rrr_ce_en"
            [ "$_rrr_ce_dl"  != "$RRR_RS" ] && RRR_CRON_DELIVERY="$_rrr_ce_dl"
        fi
        IFS='
'
    done
    IFS="$_rrr_ce_oldifs"
    RRR_CRON_IDS="${RRR_CRON_IDS# }"
    RRR_CRON_MATCH_IDS="${RRR_CRON_MATCH_IDS# }"
    RRR_CRON_UNOBS="${RRR_CRON_UNOBS#,}"
    RRR_CRON_DISAGREE="${RRR_CRON_DISAGREE#,}"
    if [ "$RRR_CRON_COUNT" -eq 0 ]; then
        case "$RRR_COVERAGE" in
            db-only|cli+db) RRR_CRON_STATE="absent" ;;
            cli-only)       RRR_CRON_STATE="cli_only_absent" ;;
            *)              RRR_CRON_STATE="unreadable" ;;
        esac
        return 0
    fi
    if [ "$RRR_CRON_COUNT" -gt 1 ]; then
        RRR_CRON_STATE="duplicate"
        return 0
    fi
    # --- the single job, field by field ---
    _rrr_ce_mism=""
    if [ "$RRR_CRON_SCHEDULE" = "$RRR_SCHEDULE" ]; then :; else
        [ -n "$RRR_CRON_SCHEDULE" ] && _rrr_ce_mism="$_rrr_ce_mism schedule" || _rrr_ce_mism="$_rrr_ce_mism schedule_unobservable"
    fi
    if [ "$RRR_CRON_COMMAND" = "$_rrr_ce_wantcmd" ]; then :; else
        [ -n "$RRR_CRON_COMMAND" ] && _rrr_ce_mism="$_rrr_ce_mism command" || _rrr_ce_mism="$_rrr_ce_mism command_unobservable"
    fi
    case "$RRR_CRON_ENABLED" in
        true)  : ;;
        false) _rrr_ce_mism="$_rrr_ce_mism enabled"; RRR_CRON_DISABLED_DIRECT=1 ;;
        *)     _rrr_ce_mism="$_rrr_ce_mism enabled_unobservable" ;;
    esac
    case "$RRR_CRON_DELIVERY" in
        none) : ;;
        "")   _rrr_ce_mism="$_rrr_ce_mism delivery_unobservable" ;;
        *)    _rrr_ce_mism="$_rrr_ce_mism delivery" ;;
    esac
    RRR_CRON_MISMATCH="${_rrr_ce_mism# }"
    if [ -n "$RRR_CRON_MISMATCH" ]; then
        RRR_CRON_STATE="mismatch"
        return 0
    fi
    RRR_CRON_STATE="single"
    return 0
}

# ---------------------------------------------------------------------------
# Readiness receipt read/write. A receipt is a small JSON record under
# <state>/readiness/receipt-<digest>.json. It is the ONLY thing that can lift a
# box from SCHEDULED to VERIFIED, and it must match the CURRENT digest AND the
# CURRENT runtime id.
# ---------------------------------------------------------------------------
rrr_receipt_path() { printf '%s/readiness/receipt-%s.json' "$1" "$2"; }

rrr_receipt_read() {
    _rrr_rr_dir="$1"; _rrr_rr_digest="$2"; _rrr_rr_runtime="${3:-$RRR_RUNTIME_ID}"
    RRR_RECEIPT_STATE=""; RRR_RECEIPT_AT=""; RRR_RECEIPT_RUNTIME=""; RRR_RECEIPT_DETAIL=""
    _rrr_rr_path="$(rrr_receipt_path "$_rrr_rr_dir" "$_rrr_rr_digest")"
    if [ ! -f "$_rrr_rr_path" ]; then
        # No receipt for THIS digest. A receipt for a DIFFERENT digest is not
        # "never probed" — it is a STALE verdict for a desired config that has
        # since changed, and saying so is the difference between an operator
        # re-probing and an operator chasing a phantom.
        _rrr_rr_other=""
        if [ -d "$_rrr_rr_dir/readiness" ]; then
            for _rrr_rr_c in "$_rrr_rr_dir"/readiness/receipt-*.json; do
                [ -f "$_rrr_rr_c" ] && { _rrr_rr_other="$_rrr_rr_c"; break; }
            done
        fi
        if [ -n "$_rrr_rr_other" ] && [ "$RRR_REQ_JSON" = "ok" ]; then
            _rrr_rr_ojson="$(cat "$_rrr_rr_other" 2>/dev/null)"
            _rrr_rr_odigest="$(rrr_json_get "$_rrr_rr_ojson" "digest")"
            _rrr_rr_oat="$(rrr_json_get "$_rrr_rr_ojson" "at")"
            RRR_RECEIPT_AT="$_rrr_rr_oat"
            RRR_RECEIPT_STATE="stale"
            RRR_RECEIPT_DETAIL="a receipt exists for a DIFFERENT desired-config digest (${_rrr_rr_odigest:-unknown}); the desired config changed since that probe, so the old verdict is void"
            return 0
        fi
        RRR_RECEIPT_STATE="absent"; return 0
    fi
    if [ "$RRR_REQ_JSON" != "ok" ]; then RRR_RECEIPT_STATE="unproven"; RRR_RECEIPT_DETAIL="no json reader"; return 0; fi
    _rrr_rr_json="$(cat "$_rrr_rr_path" 2>/dev/null)"
    _rrr_rr_rec="$(rrr_json_get "$_rrr_rr_json" "digest")"
    _rrr_rr_rt="$(rrr_json_get "$_rrr_rr_json" "runtime_id")"
    _rrr_rr_at="$(rrr_json_get "$_rrr_rr_json" "at")"
    _rrr_rr_kind="$(rrr_json_get "$_rrr_rr_json" "claim.kind")"
    _rrr_rr_turns="$(rrr_json_get "$_rrr_rr_json" "claim.agent_turns")"
    _rrr_rr_acks="$(rrr_json_get "$_rrr_rr_json" "claim.acks_sent")"
    _rrr_rr_transport="$(rrr_json_get "$_rrr_rr_json" "evidence.transport")"
    _rrr_rr_struct="$(rrr_json_get "$_rrr_rr_json" "evidence.structured")"
    _rrr_rr_class="$(rrr_json_get "$_rrr_rr_json" "evidence.response_class")"
    _rrr_rr_status="$(rrr_json_get "$_rrr_rr_json" "evidence.http_status")"
    RRR_RECEIPT_AT="$_rrr_rr_at"; RRR_RECEIPT_RUNTIME="$_rrr_rr_rt"
    if [ "$_rrr_rr_rec" != "$_rrr_rr_digest" ]; then
        RRR_RECEIPT_STATE="stale"
        RRR_RECEIPT_DETAIL="receipt digest does not match the current desired-config digest"
        return 0
    fi
    if [ -z "$_rrr_rr_rt" ] || [ -z "$_rrr_rr_runtime" ] || [ "$_rrr_rr_rt" != "$_rrr_rr_runtime" ]; then
        RRR_RECEIPT_STATE="foreign"
        RRR_RECEIPT_DETAIL="receipt was produced in a different runtime than the scheduled one"
        return 0
    fi
    if [ "$_rrr_rr_kind" != "safe_test_claim" ] || [ "$_rrr_rr_transport" != "ok" ] \
       || [ "$_rrr_rr_struct" != "true" ] || [ "$_rrr_rr_status" != "200" ] \
       || [ "$_rrr_rr_turns" != "0" ] || [ "$_rrr_rr_acks" != "0" ]; then
        RRR_RECEIPT_STATE="unproven"
        RRR_RECEIPT_DETAIL="receipt does not carry a transport-ok, structured, 200, zero-turn/zero-ack safe-test-claim result"
        return 0
    fi
    case "$_rrr_rr_class" in
        no_work|empty) : ;;
        *) RRR_RECEIPT_STATE="unproven"; RRR_RECEIPT_DETAIL="receipt response_class=[$_rrr_rr_class] is not a no-work answer"; return 0 ;;
    esac
    RRR_RECEIPT_STATE="verified"
    RRR_RECEIPT_DETAIL="safe test claim verified in the intended runtime"
    return 0
}

# rrr_receipt_write <state-dir> <digest> <runtime-id> <http-status> <transport>
# Atomic, 0600 inside a 0700 dir. Never contains a credential or a request
# body — class/counters only.
rrr_receipt_write() {
    _rrr_rw_dir="$1"; _rrr_rw_digest="$2"; _rrr_rw_rt="$3"; _rrr_rw_status="$4"; _rrr_rw_transport="$5"
    _rrr_rw_path="$(rrr_receipt_path "$_rrr_rw_dir" "$_rrr_rw_digest")"
    mkdir -p "$_rrr_rw_dir/readiness" 2>/dev/null || return 1
    chmod 700 "$_rrr_rw_dir/readiness" 2>/dev/null || true
    _rrr_rw_tmp="$_rrr_rw_path.tmp.$$"
    {
        printf '{"schema":"rr-028/readiness-receipt/1","state":"VERIFIED",'
        printf '"digest":"%s","runtime_id":"%s",' "$_rrr_rw_digest" "$_rrr_rw_rt"
        printf '"runtime":{"platform":"%s","target_mode":"%s","target_id":"%s"},' \
            "$RRR_PLATFORM" "$RRR_TARGET_MODE" "$RRR_TARGET_ID"
        printf '"claim":{"kind":"safe_test_claim","mode":"dry_run","capacity":0,"agent_turns":0,"acks_sent":0},'
        printf '"evidence":{"transport":"%s","http_status":%s,"structured":true,"response_class":"no_work"},' \
            "$_rrr_rw_transport" "$_rrr_rw_status"
        printf '"at":"%s"}\n' "$(rrr_now_iso)"
    } > "$_rrr_rw_tmp" 2>/dev/null || { rm -f "$_rrr_rw_tmp"; return 1; }
    chmod 600 "$_rrr_rw_tmp" 2>/dev/null || true
    mv -f "$_rrr_rw_tmp" "$_rrr_rw_path" 2>/dev/null || { rm -f "$_rrr_rw_tmp"; return 1; }
    return 0
}

# ---------------------------------------------------------------------------
# rrr_tombstone_check <ocroot> — a durable operator tombstone means "do not
# register this name again" (the shared-utils/cron-lib.sh contract). Read-only.
# ---------------------------------------------------------------------------
rrr_tombstone_check() {
    RRR_TOMBSTONED=0
    [ -n "$1" ] || return 0
    _rrr_tc_safe="$(printf '%s' "$RRR_NAME" | tr -c 'A-Za-z0-9_.-' '_')"
    [ -f "$1/workspace/.cron-tombstones/$_rrr_tc_safe" ] && RRR_TOMBSTONED=1
    return 0
}

# ---------------------------------------------------------------------------
# rrr_init <ocroot> <secrets> <poll> <state-dir>
# Resolves every input once. Never fatal: an unresolved input is recorded and
# the state machine reports it by NAME.
# ---------------------------------------------------------------------------
rrr_init() {
    RRR_ROOT="${1:-}"; RRR_SECRETS="${2:-}"; RRR_POLL="${3:-}"; RRR_STATE_DIR="${4:-}"
    rrr_tools_resolve
    rrr_enrollment_resolve "$RRR_SECRETS"
    rrr_desired_digest || true
    rrr_runtime_id || true
    rrr_tombstone_check "$RRR_ROOT"
    rrr_cron_readback || true
    rrr_cron_eval
    return 0
}

# ---------------------------------------------------------------------------
# rrr_evaluate — THE state machine. Exactly one of UNENROLLED /
# ENROLLED_PENDING / SCHEDULED / VERIFIED, each with an explicit reason code
# and a human detail naming NAMES (never values).
# ---------------------------------------------------------------------------
rrr_evaluate() {
    RRR_STATE=""; RRR_REASON=""; RRR_DETAIL=""
    # (1) UNENROLLED — not enrolled, or not provably enrolled.
    if [ "$RRR_STORE_STATE" != "ok" ]; then
        RRR_STATE="UNENROLLED"
        case "$RRR_STORE_STATE" in
            missing)           RRR_REASON="enrollment_store_missing"; RRR_DETAIL="enrollment store not present at $RRR_SECRETS" ;;
            unreadable)        RRR_REASON="enrollment_store_unreadable"; RRR_DETAIL="enrollment store not readable at $RRR_SECRETS" ;;
            parser_unresolved) RRR_REASON="enrollment_parser_unresolved"; RRR_DETAIL="shared dotenv parser (shared-utils/rescue-env.sh) could not be sourced" ;;
            *)                 RRR_REASON="enrollment_unresolved"; RRR_DETAIL="enrollment store state=$RRR_STORE_STATE" ;;
        esac
        return 0
    fi
    if [ "$RRR_MALFORMED" = "1" ]; then
        RRR_STATE="UNENROLLED"
        RRR_REASON="enrollment_store_malformed"
        RRR_DETAIL="enrollment store carries malformed lines (parser reasons name file+line on stderr); nothing half-parsed is used"
        return 0
    fi
    if [ -n "$RRR_MISSING" ]; then
        RRR_STATE="UNENROLLED"
        RRR_REASON="enrollment_value_absent"
        RRR_DETAIL="missing enrollment value(s): $RRR_MISSING"
        return 0
    fi
    # (2) ENROLLED_PENDING — enrolled, but scheduling is not proven.
    if [ -n "$RRR_MISSING_REQS" ]; then
        RRR_STATE="ENROLLED_PENDING"
        RRR_REASON="runtime_requirement_unresolved"
        RRR_DETAIL="unresolved runtime requirement(s): $RRR_MISSING_REQS"
        return 0
    fi
    if [ "$RRR_DIGEST_STATE" != "resolved" ]; then
        RRR_STATE="ENROLLED_PENDING"
        RRR_REASON="desired_digest_unresolved"
        RRR_DETAIL="desired-config digest unresolved ($RRR_DIGEST_STATE)"
        return 0
    fi
    if [ ! -f "$RRR_POLL" ]; then
        RRR_STATE="ENROLLED_PENDING"
        RRR_REASON="poll_script_missing"
        RRR_DETAIL="poll script not installed at $RRR_POLL (files were not installed)"
        return 0
    fi
    if [ "$RRR_TOMBSTONED" = "1" ]; then
        RRR_STATE="ENROLLED_PENDING"
        RRR_REASON="cron_tombstoned"
        RRR_DETAIL="operator tombstone present for $RRR_NAME; the registrar must not resurrect it"
        return 0
    fi
    case "$RRR_CRON_STATE" in
        unreadable)
            RRR_STATE="ENROLLED_PENDING"; RRR_REASON="cron_readback_unreadable"
            RRR_DETAIL="cron store could not be read back (coverage=$RRR_COVERAGE); a write is never assumed to have succeeded" ;;
        unresolved)
            RRR_STATE="ENROLLED_PENDING"; RRR_REASON="cron_capability_unresolved"
            RRR_DETAIL="openclaw CLI unresolved, so no cron can be listed" ;;
        absent|cli_only_absent)
            RRR_STATE="ENROLLED_PENDING"; RRR_REASON="cron_absent"
            RRR_DETAIL="no cron named $RRR_NAME in the readback (coverage=$RRR_COVERAGE)" ;;
        duplicate)
            RRR_STATE="ENROLLED_PENDING"; RRR_REASON="cron_duplicate"
            RRR_DETAIL="readback shows $RRR_CRON_COUNT jobs named $RRR_NAME (ids:$RRR_CRON_IDS)" ;;
        mismatch)
            if [ "$RRR_CRON_DISABLED_DIRECT" = "1" ]; then
                RRR_STATE="ENROLLED_PENDING"; RRR_REASON="cron_disabled_by_owner"
                RRR_DETAIL="cron $RRR_NAME exists but is DISABLED; readiness never re-enables an operator-disabled job (mismatches:$RRR_CRON_MISMATCH)"
            else
                RRR_STATE="ENROLLED_PENDING"; RRR_REASON="cron_field_mismatch"
                RRR_DETAIL="readback of ${RRR_CRON_ID:-$RRR_NAME} does not match the desired config: $RRR_CRON_MISMATCH"
            fi ;;
        single) : ;;
        *)
            RRR_STATE="ENROLLED_PENDING"; RRR_REASON="cron_state_unresolved"
            RRR_DETAIL="cron readback state=$RRR_CRON_STATE" ;;
    esac
    if [ -n "$RRR_STATE" ]; then return 0; fi
    if [ -n "$RRR_CRON_DISAGREE" ]; then
        RRR_STATE="ENROLLED_PENDING"
        RRR_REASON="cron_source_disagreement"
        RRR_DETAIL="the CLI view and the gateway store disagree on: $RRR_CRON_DISAGREE"
        return 0
    fi
    # (3) SCHEDULED — readback proved the desired job, exactly once, matching.
    if [ "$RRR_RUNTIME_STATE" != "resolved" ]; then
        RRR_STATE="ENROLLED_PENDING"
        RRR_REASON="runtime_unresolved"
        RRR_DETAIL="host/container descriptor did not resolve (platform=${RRR_PLATFORM:-?} mode=${RRR_TARGET_MODE:-?}); the intended runtime cannot be named, so neither SCHEDULED nor VERIFIED can be claimed"
        return 0
    fi
    case "$RRR_RECEIPT_STATE" in
        verified)
            RRR_STATE="VERIFIED"
            RRR_REASON="ready_receipt_verified"
            RRR_DETAIL="cron $RRR_CRON_ID read back matching the desired digest and a safe test claim receipt ($RRR_RECEIPT_AT) verified the intended runtime"
            ;;
        absent)
            RRR_STATE="SCHEDULED"
            RRR_REASON="ready_receipt_absent"
            RRR_DETAIL="cron $RRR_CRON_ID read back matching; NO verified safe-test-claim receipt for digest $RRR_DIGEST (run rr-readiness.sh --probe)"
            ;;
        stale)
            RRR_STATE="SCHEDULED"
            RRR_REASON="ready_receipt_stale"
            RRR_DETAIL="the desired config changed since the last probe (digest mismatch); the old receipt is void"
            ;;
        foreign)
            RRR_STATE="SCHEDULED"
            RRR_REASON="ready_receipt_foreign_runtime"
            RRR_DETAIL="a receipt exists but was produced in a different runtime than the scheduled one"
            ;;
        *)
            RRR_STATE="SCHEDULED"
            RRR_REASON="ready_receipt_unproven"
            RRR_DETAIL="receipt present but not a proven safe claim: $RRR_RECEIPT_DETAIL"
            ;;
    esac
    return 0
}

# ---------------------------------------------------------------------------
# Reports. Machine JSON + one human line. Names, states and digests only — no
# secret value ever reaches either surface.
# ---------------------------------------------------------------------------
rrr_json_escape() {
    if command -v python3 >/dev/null 2>&1; then
        printf '%s' "$1" | python3 -c 'import json,sys; sys.stdout.write(json.dumps(sys.stdin.read())[1:-1])' 2>/dev/null
        return 0
    fi
    printf '%s' "$1" | tr -d '"\\' | tr -d '\n\r\t'
}

rrr_report_json() {
    _rrr_rj_missing=""
    for _rrr_rj_m in $RRR_MISSING; do
        _rrr_rj_missing="$_rrr_rj_missing${_rrr_rj_missing:+,}\"$(rrr_json_escape "$_rrr_rj_m")\""
    done
    printf '{"state":"%s","reason":"%s","detail":"%s","digest":"%s",' \
        "$RRR_STATE" "$(rrr_json_escape "$RRR_REASON")" "$(rrr_json_escape "$RRR_DETAIL")" "$RRR_DIGEST"
    printf '"desired":{"name":"%s","schedule":"%s","command":"%s","enabled":%s,"delivery":"%s","box_slug":"%s","receiver_url_set":%s,"token_set":%s,"token_commit":"%s"},' \
        "$(rrr_json_escape "$RRR_NAME")" "$(rrr_json_escape "$RRR_SCHEDULE")" "$(rrr_json_escape "sh $RRR_POLL")" \
        "$([ "$RRR_ENABLED" = "1" ] && echo true || echo false)" "$(rrr_json_escape "$RRR_DELIVERY")" \
        "$(rrr_json_escape "$RRR_SLUG")" "$([ "$RRR_HAS_URL" = "1" ] && echo true || echo false)" \
        "$([ "$RRR_HAS_TOKEN" = "1" ] && echo true || echo false)" "$(rrr_json_escape "$RRR_TOKEN_COMMIT")"
    printf '"enrollment":{"store_state":"%s","missing":[%s],"malformed":%s},' \
        "$RRR_STORE_STATE" "$_rrr_rj_missing" "$([ "$RRR_MALFORMED" = "1" ] && echo true || echo false)"
    printf '"requirements":{"parser":"%s","curl":"%s","base64":"%s","openclaw":"%s","node":"%s","json_reader":"%s","hasher":"%s","missing":"%s"},' \
        "$RRR_REQ_PARSER" "$RRR_REQ_CURL" "$RRR_REQ_BASE64" "$RRR_REQ_OPENCLAW" "$RRR_REQ_NODE" "$RRR_REQ_JSON" "$RRR_REQ_SHA" \
        "$(rrr_json_escape "$RRR_MISSING_REQS")"
    printf '"cron":{"state":"%s","count":%s,"id":"%s","sources":"%s","coverage":"%s","schedule":"%s","command":"%s","enabled":"%s","delivery":"%s","unobservable":"%s","disagreement":"%s"},' \
        "$RRR_CRON_STATE" "$RRR_CRON_COUNT" "$(rrr_json_escape "$RRR_CRON_ID")" "$(rrr_json_escape "$RRR_CRON_SOURCES")" \
        "$RRR_COVERAGE" "$(rrr_json_escape "$RRR_CRON_SCHEDULE")" "$(rrr_json_escape "$RRR_CRON_COMMAND")" \
        "$RRR_CRON_ENABLED" "$RRR_CRON_DELIVERY" "$(rrr_json_escape "$RRR_CRON_UNOBS")" "$(rrr_json_escape "$RRR_CRON_DISAGREE")"
    printf '"runtime":{"state":"%s","id":"%s","platform":"%s","target_mode":"%s","target_id":"%s"},"receipt":{"state":"%s","at":"%s"},"reconcile":{"state":"%s","action":"%s"}}\n' \
        "$RRR_RUNTIME_STATE" "$RRR_RUNTIME_ID" "$(rrr_json_escape "$RRR_PLATFORM")" "$(rrr_json_escape "$RRR_TARGET_MODE")" \
        "$(rrr_json_escape "$RRR_TARGET_ID")" "$RRR_RECEIPT_STATE" "$(rrr_json_escape "$RRR_RECEIPT_AT")" \
        "$RRR_RECONCILE_STATE" "$RRR_RECONCILE_ACTION"
}

rrr_report_line() {
    printf 'readiness=%s reason=%s digest=%s runtime=%s coverage=%s detail=%s\n' \
        "$RRR_STATE" "$RRR_REASON" "${RRR_DIGEST:-none}" "${RRR_RUNTIME_ID:-unresolved}" "$RRR_COVERAGE" "$RRR_DETAIL"
}

# ---------------------------------------------------------------------------
# rrr_cron_reconcile — make the desired job true, then READ IT BACK.
#   0 single matching job proven by readback
#   3 readback unavailable (nothing claimed)
#   4 readback read, desired job not proven after the ladder
#   5 openclaw CLI unresolved
#   6 tombstoned / disabled by owner (never mutated)
#   7 a mutation command itself failed (retryable wiring failure)
# Every mutation is followed by a FRESH readback + rrr_cron_eval; each step's
# success is the readback, never the command's exit code. The ladder is
# dedupe -> add -> edit-in-place -> replace, bounded to 4 attempts.
# ---------------------------------------------------------------------------
rrr_cron_reconcile() {
    RRR_RECONCILE_STATE=""; RRR_RECONCILE_ACTION=""; RRR_RECONCILE_RC=0
    if [ "$RRR_REQ_OPENCLAW" != "ok" ]; then RRR_RECONCILE_STATE="cli_unresolved"; RRR_RECONCILE_RC=5; return 5; fi
    if [ "$RRR_REQ_JSON" != "ok" ]; then RRR_RECONCILE_STATE="json_unresolved"; RRR_RECONCILE_RC=3; return 3; fi
    if [ "$RRR_TOMBSTONED" = "1" ]; then RRR_RECONCILE_STATE="tombstoned"; RRR_RECONCILE_RC=6; return 6; fi
    _rrr_cr_tmp="$(mktemp "${TMPDIR:-/tmp}/rr028-reconcile.XXXXXX" 2>/dev/null)" || { RRR_RECONCILE_RC=3; return 3; }
    _rrr_cr_tried_dedupe=0; _rrr_cr_tried_add=0; _rrr_cr_tried_edit=0; _rrr_cr_tried_replace=0
    _rrr_cr_mut_rc=0
    _rrr_cr_attempt=0
    while [ "$_rrr_cr_attempt" -lt 5 ]; do
        _rrr_cr_attempt=$((_rrr_cr_attempt + 1))
        rrr_cron_readback || true
        rrr_cron_eval
        case "$RRR_CRON_STATE" in
            single)
                [ -n "$RRR_RECONCILE_ACTION" ] || RRR_RECONCILE_ACTION="none"
                [ "$RRR_RECONCILE_ACTION" = "none" ] && RRR_RECONCILE_STATE="in_sync" || RRR_RECONCILE_STATE="readback_verified"
                rm -f "$_rrr_cr_tmp"* 2>/dev/null
                RRR_RECONCILE_RC=0; return 0 ;;
            unreadable|unresolved)
                RRR_RECONCILE_STATE="readback_unavailable"
                rm -f "$_rrr_cr_tmp"* 2>/dev/null
                RRR_RECONCILE_RC=3; return 3 ;;
            mismatch)
                if [ "$RRR_CRON_DISABLED_DIRECT" = "1" ]; then
                    RRR_RECONCILE_STATE="disabled_by_owner"
                    rm -f "$_rrr_cr_tmp"* 2>/dev/null
                    RRR_RECONCILE_RC=6; return 6
                fi
                if [ "$_rrr_cr_tried_edit" = "0" ]; then
                    _rrr_cr_tried_edit=1
                    rrr_argv_run "$_rrr_cr_tmp.ehelp" "$_rrr_cr_tmp.err" "$RRR_OPENCLAW_BIN" cron edit --help || true
                    _rrr_cr_ehelp="$(cat "$_rrr_cr_tmp.ehelp" 2>/dev/null)"
                    _rrr_cr_has_cron=0; _rrr_cr_has_cmd=0; _rrr_cr_has_nod=0
                    case "$_rrr_cr_ehelp" in *--cron*) _rrr_cr_has_cron=1 ;; esac
                    case "$_rrr_cr_ehelp" in *--command*) _rrr_cr_has_cmd=1 ;; esac
                    case "$_rrr_cr_ehelp" in *--no-deliver*) _rrr_cr_has_nod=1 ;; esac
                    if [ "$_rrr_cr_has_cron" = "1" ] || [ "$_rrr_cr_has_cmd" = "1" ] || [ "$_rrr_cr_has_nod" = "1" ]; then
                        if [ "$_rrr_cr_has_cron" = "1" ] && [ "$_rrr_cr_has_cmd" = "1" ] && [ "$_rrr_cr_has_nod" = "1" ]; then
                            rrr_argv_run "$_rrr_cr_tmp.mut" "$_rrr_cr_tmp.err" "$RRR_OPENCLAW_BIN" cron edit "$RRR_CRON_ID" \
                                --cron "$RRR_SCHEDULE" --command "sh $RRR_POLL" --no-deliver
                        elif [ "$_rrr_cr_has_cron" = "1" ] && [ "$_rrr_cr_has_cmd" = "1" ]; then
                            rrr_argv_run "$_rrr_cr_tmp.mut" "$_rrr_cr_tmp.err" "$RRR_OPENCLAW_BIN" cron edit "$RRR_CRON_ID" \
                                --cron "$RRR_SCHEDULE" --command "sh $RRR_POLL"
                        elif [ "$_rrr_cr_has_cmd" = "1" ] && [ "$_rrr_cr_has_nod" = "1" ]; then
                            rrr_argv_run "$_rrr_cr_tmp.mut" "$_rrr_cr_tmp.err" "$RRR_OPENCLAW_BIN" cron edit "$RRR_CRON_ID" \
                                --command "sh $RRR_POLL" --no-deliver
                        elif [ "$_rrr_cr_has_cmd" = "1" ]; then
                            rrr_argv_run "$_rrr_cr_tmp.mut" "$_rrr_cr_tmp.err" "$RRR_OPENCLAW_BIN" cron edit "$RRR_CRON_ID" \
                                --command "sh $RRR_POLL"
                        elif [ "$_rrr_cr_has_cron" = "1" ]; then
                            rrr_argv_run "$_rrr_cr_tmp.mut" "$_rrr_cr_tmp.err" "$RRR_OPENCLAW_BIN" cron edit "$RRR_CRON_ID" \
                                --cron "$RRR_SCHEDULE"
                        else
                            rrr_argv_run "$_rrr_cr_tmp.mut" "$_rrr_cr_tmp.err" "$RRR_OPENCLAW_BIN" cron edit "$RRR_CRON_ID" \
                                --no-deliver
                        fi
                        [ "$RRR_ARGV_RC" -ne 0 ] && _rrr_cr_mut_rc="$RRR_ARGV_RC"
                        RRR_RECONCILE_ACTION="edit"
                        continue
                    fi
                fi
                if [ "$_rrr_cr_tried_replace" = "0" ] && [ -n "$RRR_CRON_ID" ]; then
                    _rrr_cr_tried_replace=1
                    rrr_argv_run "$_rrr_cr_tmp.mut" "$_rrr_cr_tmp.err" "$RRR_OPENCLAW_BIN" cron rm "$RRR_CRON_ID" || true
                    [ "$RRR_ARGV_RC" -ne 0 ] && _rrr_cr_mut_rc="$RRR_ARGV_RC"
                    RRR_RECONCILE_ACTION="replace"
                    continue
                fi
                RRR_RECONCILE_STATE="mismatch_unreconciled"
                rm -f "$_rrr_cr_tmp"* 2>/dev/null
                RRR_RECONCILE_RC=4; return 4 ;;
            duplicate)
                if [ "$_rrr_cr_tried_dedupe" = "0" ]; then
                    _rrr_cr_tried_dedupe=1
                    _rrr_cr_keep=""
                    # Prefer a job that already matches the desired config.
                    for _rrr_cr_id in $RRR_CRON_MATCH_IDS; do _rrr_cr_keep="$_rrr_cr_id"; break; done
                    if [ -z "$_rrr_cr_keep" ]; then
                        for _rrr_cr_id in $RRR_CRON_IDS; do _rrr_cr_keep="$_rrr_cr_id"; break; done
                    fi
                    for _rrr_cr_id in $RRR_CRON_IDS; do
                        [ "$_rrr_cr_id" = "$_rrr_cr_keep" ] && continue
                        rrr_argv_run "$_rrr_cr_tmp.mut" "$_rrr_cr_tmp.err" "$RRR_OPENCLAW_BIN" cron rm "$_rrr_cr_id" || true
                        [ "$RRR_ARGV_RC" -ne 0 ] && _rrr_cr_mut_rc="$RRR_ARGV_RC"
                    done
                    RRR_RECONCILE_ACTION="dedupe"
                    continue
                fi
                RRR_RECONCILE_STATE="duplicate_unreconciled"
                rm -f "$_rrr_cr_tmp"* 2>/dev/null
                RRR_RECONCILE_RC=4; return 4 ;;
            absent|cli_only_absent)
                if [ "$_rrr_cr_tried_add" = "0" ]; then
                    _rrr_cr_tried_add=1
                    rrr_argv_run "$_rrr_cr_tmp.ahelp" "$_rrr_cr_tmp.err" "$RRR_OPENCLAW_BIN" cron add --help || true
                    _rrr_cr_ahelp="$(cat "$_rrr_cr_tmp.ahelp" 2>/dev/null)"
                    if [ -z "$_rrr_cr_ahelp" ] || [ "$RRR_ARGV_RC" -ne 0 ]; then
                        # A CLI with no readable help must still get a chance to
                        # register; try the silenced form first, then the plain
                        # form (the two forms wire.sh has always used).
                        rrr_argv_run "$_rrr_cr_tmp.mut" "$_rrr_cr_tmp.err" "$RRR_OPENCLAW_BIN" cron add \
                            --name "$RRR_NAME" --cron "$RRR_SCHEDULE" --no-deliver --command "sh $RRR_POLL" || true
                        if [ "$RRR_ARGV_RC" -ne 0 ]; then
                            rrr_argv_run "$_rrr_cr_tmp.mut" "$_rrr_cr_tmp.err" "$RRR_OPENCLAW_BIN" cron add \
                                --name "$RRR_NAME" --cron "$RRR_SCHEDULE" --command "sh $RRR_POLL" || true
                        fi
                    else
                        case "$_rrr_cr_ahelp" in
                            *--no-deliver*)
                                rrr_argv_run "$_rrr_cr_tmp.mut" "$_rrr_cr_tmp.err" "$RRR_OPENCLAW_BIN" cron add \
                                    --name "$RRR_NAME" --cron "$RRR_SCHEDULE" --no-deliver --command "sh $RRR_POLL" || true ;;
                            *)
                                rrr_argv_run "$_rrr_cr_tmp.mut" "$_rrr_cr_tmp.err" "$RRR_OPENCLAW_BIN" cron add \
                                    --name "$RRR_NAME" --cron "$RRR_SCHEDULE" --command "sh $RRR_POLL" || true ;;
                        esac
                    fi
                    [ "$RRR_ARGV_RC" -ne 0 ] && _rrr_cr_mut_rc="$RRR_ARGV_RC"
                    [ -z "$RRR_RECONCILE_ACTION" ] && RRR_RECONCILE_ACTION="add"
                    continue
                fi
                if [ "$_rrr_cr_mut_rc" -ne 0 ]; then
                    RRR_RECONCILE_STATE="mutation_failed"
                    rm -f "$_rrr_cr_tmp"* 2>/dev/null
                    RRR_RECONCILE_RC=7; return 7
                fi
                RRR_RECONCILE_STATE="add_not_read_back"
                rm -f "$_rrr_cr_tmp"* 2>/dev/null
                RRR_RECONCILE_RC=4; return 4 ;;
            *)
                RRR_RECONCILE_STATE="unexpected_$RRR_CRON_STATE"
                rm -f "$_rrr_cr_tmp"* 2>/dev/null
                RRR_RECONCILE_RC=4; return 4 ;;
        esac
    done
    rm -f "$_rrr_cr_tmp"* 2>/dev/null
    RRR_RECONCILE_STATE="attempts_exhausted"
    RRR_RECONCILE_RC=4
    return 4
}
