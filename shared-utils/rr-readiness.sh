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
# shared-utils/cron-lib.sh documents). That case is REPORTED as `cli-only` and,
# when the CLI advertised no full-status listing flag, as
# `visibility=enabled_only` in the JSON report — it is never presented as a
# proven absence.
#
# FAIL-CLOSED MUTATION RULE (RR-028 review M-1, corrected by re-review Z-1/Z-2).
# "Nothing visible" is proof of ABSENCE only when the view that returned it can
# actually SHOW a DISABLED job — i.e. when the CLI's own listing was asked for a
# full-status flag (`--all` / `--include-disabled` / `--show-disabled`, which the
# CLI must ADVERTISE in its own `--help` before it is asked). Otherwise the
# visible set is AMBIGUOUS — "absent" OR "present but DISABLED and hidden" —
# and the reconciler REFUSES TO MUTATE (rc 8), reporting
# `ENROLLED_PENDING / cron_state_unverifiable` instead of a write that risks
# destroying operator intent.
#
# THE RULE'S REAL DEPENDENCY, STATED PLAINLY (Z-2): the refusal is NOT
# independent of what the CLI's help advertises. A CLI that advertises the flag
# IS asked for it and its listing IS trusted; a build that advertises the flag
# and then hides a disabled job anyway is indistinguishable from an honest build
# IN-BAND — by the CLI's own answers alone — and is a documented residual (see
# the CHANGELOG). It is NOT indistinguishable by every input this engine has:
# when a resolved gateway store carries the hidden row, the contradiction is
# detected (`store_diverged`, `cli_all_omits_disabled_row(id=…)`, rc 4, nothing
# mutated, nothing claimed), which is what the `store_diverged` check below is
# for. What the rule no longer does is take a resolved gateway STORE as a
# substitute for a full-status CLI listing.
#
# THE STORE MAY VETO, NEVER LICENSE (Z-1). RRR_DB comes from
# shared-utils/oc-env-descriptor.sh `ocd_state_db`, which accepts ANY readable
# candidate sqlite with at least one table — an alternate or older file that
# ocd_state_db happens to resolve is NOT proof that it reflects the gateway's
# live cron state. So a resolved store:
#   * may VETO a write (a DISABLED row it carries => leave the job alone, rc 6);
#   * may CORROBORATE (its rows for the managed name must agree with the CLI's
#     own listing — a contradiction makes the whole readback `store_diverged`,
#     which licenses nothing and claims nothing; and a row the CLI's listing
#     does not show leaves the store merely `unconfirmed`, never
#     `corroborated` — AD-1);
#   * may never LICENSE an add, an edit or a removal. Absence is licensed by the
#     CLI's own full-status listing only, and a removal additionally requires the
#     gateway's own listing to show the row, to have OBSERVED its enabled bit,
#     and never to have seen it DISABLED.
# The cost is deliberate and one-sided — a box whose CLI cannot list disabled
# jobs stays unregistered (and says so, with the remedy) rather than risking the
# operator's job, and the remedy is a CLI that advertises the flag, never "make
# the state DB readable".
#
# UNOBSERVABLE IS NOT ABSENT (RR-028 review AD-2/AD-7). When a row is present
# and NO view reports its `enabled` bit, the engine cannot tell an
# operator-DISABLED job from an ENABLED one. Deletion is destructive and
# irreversible, so the ladder REFUSES to edit, replace or remove such a row
# (`enabled_unobservable`, rc 8, nothing mutated, nothing claimed) instead of
# guessing the switch state. This is the CLI-blind-spot rule of the paragraph
# above applied to the bit itself, not a special case: the same reasoning covers
# a `disabled` value that is not a boolean (e.g. the string "true"), because an
# unparseable bit is an unobserved bit.
#
# THE MIRROR COST (RR-028 review AD-5). Because the CLI's own listing is the
# only view that may corroborate the store, a STALE or EMPTY resolved store now
# reds a box that is genuinely scheduled: the CLI shows the one correct job, the
# store carries no row for it, `store_missing_row` makes the readback
# `store_diverged` and the box reports ENROLLED_PENDING/cron_source_disagreement
# with rc 4 and nothing mutated. That is deliberate (a store that does not
# reflect the gateway licenses nothing) and the detail names the remedy; it is
# documented here and in the CHANGELOG so a red roll is not mistaken for a
# broken box.
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
_RRR_CK_TAB="$(printf '\t')"       # literal tab for rrr_cron_cmd_key (never a
                                   # literal tab in the pattern: an editor that
                                   # eats it must not silently change behaviour)

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
# Can this readback PROVE a disabled job's absence? A CLI fact ONLY:
# "full" = the CLI advertised a full-status listing flag and was ASKED for one,
# so its listing carries disabled rows and an absence in it is proof;
# "enabled_only" = a readable CLI listing that cannot show a disabled job;
# "unknown" = no readable CLI listing. A resolved gateway store does NOT upgrade
# this value (re-review Z-1: a store that resolves is not a store that reflects
# the gateway) — the store is reported separately as RRR_DB_AUTHORITY.
RRR_CRON_VISIBILITY="unknown"
# What the resolved store is worth (re-review Z-1, widened by review AD-1):
# "none" = no store resolved; "corroborated" = EVERY row it carries for the
# managed name is matched by the CLI's own listing and vice versa;
# "diverged" = it contradicts that listing, so nothing it says is proof and no
# write is licensed by it; "unconfirmed" = no readable CLI listing to check it
# against, OR a row for the managed name the CLI's listing does not show — so it
# may still veto but can never establish readiness on its own, and it is never
# reported as corroborated.
RRR_DB_AUTHORITY="none"
RRR_CRON_STATE=""; RRR_CRON_COUNT=0; RRR_CRON_ID=""
RRR_CRON_SCHEDULE=""; RRR_CRON_COMMAND=""; RRR_CRON_ENABLED=""; RRR_CRON_DELIVERY=""
RRR_CRON_MISMATCH=""; RRR_CRON_UNOBS=""; RRR_CRON_DISAGREE=""
RRR_CRON_IDS=""; RRR_CRON_MATCH_IDS=""; RRR_CRON_DISABLED_DIRECT=0; RRR_CRON_SOURCES=""
# Which view showed each id of the managed name, which were seen DISABLED, and
# which were seen with an OBSERVABLE enabled bit at all.
RRR_CRON_CLI_IDS=""; RRR_CRON_DB_IDS=""; RRR_CRON_DB_ENABLED_IDS=""; RRR_CRON_DISABLED_IDS=""
RRR_CRON_ENABLED_IDS=""
# 1 when SOME view reported a boolean `enabled` for the managed name. At 0 the
# readback cannot tell an operator-DISABLED job from an ENABLED one, so the
# ladder must not edit, replace or remove the row (see the header rule).
RRR_CRON_ENABLED_OBSERVED=0
# Why a store that DID resolve was still not corroborated (a row the CLI's own
# listing does not show). Reported as `cron.store_note`; never a disagreement.
RRR_CRON_STORE_NOTE=""
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

# Shells whose argv[0] means "the rest of argv is a command for me to run".
SHELLS = ("sh", "bash", "zsh", "dash", "ksh", "ksh93", "ash", "mksh")
# The flag a shell uses to read its program from the NEXT word. Exactly the two
# forms this platform documents/emits: `--command <shell>` is defined as
# "Command payload run as sh -lc <shell> on the Gateway".
WRAP_FLAGS = ("-lc", "-c")

def _base(w):
    return w.rsplit("/", 1)[-1]

def argv_command(v):
    """The command a payload.argv vector expresses, or None if uninterpretable.

    RR-028 argv readback. Measured on a live box across all 117 jobs:
    `payload.command` is populated for 0 of them and `payload.argv` for 16, so
    the canonical command job is

        {"kind":"command","argv":["sh","-lc","sh <poll>"]}

    with payload.command and top-level command BOTH absent. The engine used to
    fall through to the literal "kind=command", which can never equal the
    desired "sh <poll>" -- so SCHEDULED/VERIFIED were unreachable, and a
    healthy, actively-running job was reported as a field mismatch.

    EXACTLY ONE shape is accepted, because it is the documented encoding the
    CLI itself defines for `--command <shell>` and the only one observed:

        [<shell>, "-lc" | "-c", <command>]     (3 elements, all non-empty str)

    -> returns <command>.

    EVERY other shape returns None -- which the caller reports as an
    UNOBSERVABLE command. That is deliberate. `--command-argv <json>` lets a
    job carry an arbitrary argv vector, so an unrecognised vector must not be
    flattened, joined or otherwise guessed into text that might coincidentally
    equal the desired command: a different arity (including an EXTRA element),
    a non-string or empty member, a non-shell argv[0], or any other flag is a
    shape this readback cannot vouch for, and an unreadable field must never
    be able to look like a match.
    """
    if not isinstance(v, list) or len(v) != 3:
        return None
    for x in v:
        if not isinstance(x, str) or not x:
            return None
    if _base(v[0]) not in SHELLS:
        return None
    if v[1] not in WRAP_FLAGS:
        return None
    return v[2]

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
        # RR-028: the measured CLI shape exposes the command ONLY as
        # payload.argv. Reconstruct it here; a vector this readback cannot
        # interpret yields None and falls through to the top-level fallbacks.
        cmd = argv_command(g(j, "payload", "argv"))
    if not (isinstance(cmd, str) and cmd):
        alt = j.get("command")
        if isinstance(alt, str) and alt:
            cmd = alt
        else:
            # NOTHING readable. This is deliberately EMPTY, not a "kind=..."
            # marker: the payload KIND being `command` says what sort of job
            # this is, it does not reveal WHAT it runs. An empty field is the
            # honest report -- it lands in `miss` as "command" and the
            # evaluator records `command_unobservable` -- whereas the old
            # "kind=command" string dressed an unreadable field up as an
            # observed value. Either way it can never equal "sh <poll>"; empty
            # additionally keeps it out of every "we read this" path.
            cmd = ""
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
    RRR_CRON_VISIBILITY="unknown"
    _rrr_rb_tmp="$(mktemp "${TMPDIR:-/tmp}/rr028-readback.XXXXXX" 2>/dev/null)" || {
        RRR_RB_STATE="unreadable"; return 1; }
    # ---- CLI view ----
    _rrr_rb_cli_ok=0
    _rrr_rb_flags=""
    if [ "$RRR_REQ_OPENCLAW" != "ok" ]; then
        RRR_RB_STATE="cli_unresolved"
    else
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
            # Only a CLI that ADVERTISES a full-status listing flag can show a
            # disabled job. Without one the CLI view is enabled-jobs-only and an
            # absence in it proves nothing (see the FAIL-CLOSED MUTATION RULE).
            if [ -n "$_rrr_rb_flags" ]; then
                RRR_CRON_VISIBILITY="full"
            else
                RRR_CRON_VISIBILITY="enabled_only"
            fi
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
    # RR-028 re-review Z-1: a resolved store does NOT upgrade visibility. The
    # store is a FILE that ocd_state_db resolved (any candidate with >=1 table);
    # it may be an alternate or older file that does not reflect the gateway's
    # live cron state, so "a DB resolved" is NOT "this DB is authoritative for
    # the gateway". Visibility therefore stays a CLI fact (set above), and the
    # store's role is to VETO or CORROBORATE in rrr_cron_eval — never to license
    # a write. Before this, an empty-but-readable store made the ladder treat a
    # hidden disabled job as absent, add an ENABLED poller beside it, and then
    # delete the operator's disabled job in the dedupe pass.
    if [ -n "$RRR_JOBS" ] || [ "$_rrr_rb_cli_ok" = "1" ] || [ "$_rrr_rb_db_ok" = "1" ]; then
        return 0
    fi
    [ -n "$RRR_RB_STATE" ] || RRR_RB_STATE="unreadable"
    return 1
}

# ---------------------------------------------------------------------------
# rrr_cron_cmd_key <raw-command> [root] — THE command comparison.
#
# WHY THIS EXISTS (RR-028): the match used to be a byte comparison of the
# observed command against the literal "sh $RRR_POLL". That is brittle in both
# directions that matter on a live box:
#   * it reported a MISMATCH for a job that runs the right script through a
#     shell wrapper (`sh -lc "sh <poll>"`, which is exactly how some CLIs store
#     a command job), and
#   * it reported a MISMATCH for the right script named relatively
#     (`sh ../../skills/.../rescue-poll.sh`).
# Both are the same job. So BOTH sides are normalised here, and the comparison
# is between what each side RESOLVES TO.
#
# THE NORMALISATION RULE (one rule, applied identically to both sides):
#   1. Trim leading/trailing blanks (the readback already folds tabs, CRs and
#      newlines to spaces).
#   2. Strip AT MOST ONE shell-wrapper prefix `<shell> <flag>` where <shell>'s
#      basename is one of sh/bash/zsh/dash/ksh/ksh93/ash/mksh and <flag> is
#      EXACTLY "-lc" or "-c" -- the two forms this platform documents ("Command
#      payload run as sh -lc <shell> on the Gateway") and emits. A wrapper is
#      stripped because `sh -lc "sh <poll>"` runs `sh <poll>`. Any OTHER flag is
#      a shape this engine has not observed and cannot vouch for: it is left in
#      place, so the row keys as its own text and cannot match.
#   3. Strip AT MOST ONE bare shell prefix `<shell> `, because `sh <script>`
#      runs <script>. (So "sh <poll>", "<poll>" and "sh -lc \"sh <poll>\"" all
#      reach the same leaf. No recursion: at most one wrapper, one shell.)
#   4. The remainder -- VERBATIM, spaces and all, never re-split or evaluated --
#      is the leaf command text.
#   5. Resolve the leaf to an ABSOLUTE path: an absolute leaf is taken as-is;
#      a relative leaf is resolved against <root> (the openclaw root, the only
#      directory a relative cron command could sanely be relative to).
#   6. Canonicalise that absolute path: "" and "." segments dropped, ".."
#      segments applied, duplicate "/" collapsed.
# The printed KEY is that canonical absolute path.
#
# WHY IT IS FAIL-CLOSED. rc is 1 -- the caller must then treat the command as
# UNOBSERVABLE and match NOTHING -- when the input is empty, when the leaf is
# empty, when the leaf is just a bare shell name ("sh" resolves to no script at
# all), or when the two sides cannot both be resolved (an empty <root> cannot
# resolve a relative leaf). Every accepted difference is a difference that
# provably runs the SAME file:
#   * an extra/unexpected argument is NOT dropped -- it stays in the preserved
#     remainder, so `sh -lc "sh <poll> extra"` keys as "<poll> extra" != key.
#   * a different script, or the same basename in a different directory, keys
#     as a different path.
#   * a non-shell program (`python <poll>`, `kind=command`) has no prefix
#     stripped, so it keys as its own text and cannot collide with <poll>.
#   * a metacharacter-bearing leaf (a box root may legitimately contain spaces,
#     `;` and `$( )`) is compared as a STRING and is never executed, eval'd or
#     word-split, so it is neither an injection nor a false match.
# ---------------------------------------------------------------------------
_rrr_ck_trim() {   # sets _RRR_CK_T
    _RRR_CK_T="$1"
    while [ -n "$_RRR_CK_T" ]; do
        case "$_RRR_CK_T" in
            " "*)  _RRR_CK_T="${_RRR_CK_T# }" ;;
            "$_RRR_CK_TAB"*) _RRR_CK_T="${_RRR_CK_T#"$_RRR_CK_TAB"}" ;;
            *) break ;;
        esac
    done
    while [ -n "$_RRR_CK_T" ]; do
        case "$_RRR_CK_T" in
            *" ")  _RRR_CK_T="${_RRR_CK_T% }" ;;
            *"$_RRR_CK_TAB") _RRR_CK_T="${_RRR_CK_T%"$_RRR_CK_TAB"}" ;;
            *) break ;;
        esac
    done
    return 0
}

_rrr_ck_is_shell() {
    case "${1##*/}" in
        sh|bash|zsh|dash|ksh|ksh93|ash|mksh) return 0 ;;
        *) return 1 ;;
    esac
}

_rrr_ck_is_wrapflag() {
    [ "$1" = "-lc" ] || [ "$1" = "-c" ]
}

# _rrr_ck_canon <absolute-path> — sets _RRR_CK_C. Never globs (set -f), never
# touches the filesystem (this must not depend on the path existing -- a
# mismatched job may name a script that is not installed).
_rrr_ck_canon() {
    _rrr_ck_p="$1"
    _rrr_ck_out=""
    case $- in *f*) _rrr_ck_hadf=1 ;; *) _rrr_ck_hadf=0; set -f ;; esac
    _rrr_ck_oifs="$IFS"; IFS=/
    for _rrr_ck_seg in $_rrr_ck_p; do
        case "$_rrr_ck_seg" in
            ""|.) : ;;
            ..) [ -n "$_rrr_ck_out" ] && _rrr_ck_out="${_rrr_ck_out%/*}" ;;
            *) _rrr_ck_out="$_rrr_ck_out/$_rrr_ck_seg" ;;
        esac
    done
    IFS="$_rrr_ck_oifs"
    [ "$_rrr_ck_hadf" = "0" ] && set +f
    _RRR_CK_C="${_rrr_ck_out:-/}"
    return 0
}

rrr_cron_cmd_key() {
    _rrr_ck_raw="$1"; _rrr_ck_root="${2:-$RRR_ROOT}"
    _RRR_CK_KEY=""
    [ -n "$_rrr_ck_raw" ] || return 1
    _rrr_ck_trim "$_rrr_ck_raw"
    _rrr_ck_t="$_RRR_CK_T"
    [ -n "$_rrr_ck_t" ] || return 1
    # first word / remainder
    case "$_rrr_ck_t" in
        *" "*) _rrr_ck_w="${_rrr_ck_t%% *}"; _rrr_ck_r="${_rrr_ck_t#* }" ;;
        *)     _rrr_ck_w="$_rrr_ck_t";        _rrr_ck_r="" ;;
    esac
    _rrr_ck_trim "$_rrr_ck_r"; _rrr_ck_r="$_RRR_CK_T"
    # (2) one shell-wrapper prefix
    if [ -n "$_rrr_ck_r" ] && _rrr_ck_is_shell "$_rrr_ck_w"; then
        case "$_rrr_ck_r" in
            *" "*) _rrr_ck_w2="${_rrr_ck_r%% *}"; _rrr_ck_r2="${_rrr_ck_r#* }" ;;
            *)     _rrr_ck_w2="$_rrr_ck_r";        _rrr_ck_r2="" ;;
        esac
        _rrr_ck_trim "$_rrr_ck_r2"; _rrr_ck_r2="$_RRR_CK_T"
        if [ -n "$_rrr_ck_r2" ] && _rrr_ck_is_wrapflag "$_rrr_ck_w2"; then
            _rrr_ck_t="$_rrr_ck_r2"
        else
            _rrr_ck_t="$_rrr_ck_r"
        fi
    fi
    # (3) one bare shell prefix
    case "$_rrr_ck_t" in
        *" "*) _rrr_ck_w="${_rrr_ck_t%% *}"; _rrr_ck_r="${_rrr_ck_t#* }" ;;
        *)     _rrr_ck_w="$_rrr_ck_t";        _rrr_ck_r="" ;;
    esac
    _rrr_ck_trim "$_rrr_ck_r"; _rrr_ck_r="$_RRR_CK_T"
    if [ -n "$_rrr_ck_r" ] && _rrr_ck_is_shell "$_rrr_ck_w"; then
        _rrr_ck_leaf="$_rrr_ck_r"
    else
        _rrr_ck_leaf="$_rrr_ck_t"
    fi
    # (4)/(5) leaf -> absolute
    _rrr_ck_trim "$_rrr_ck_leaf"; _rrr_ck_leaf="$_RRR_CK_T"
    [ -n "$_rrr_ck_leaf" ] || return 1
    case "$_rrr_ck_leaf" in
        /*) _rrr_ck_abs="$_rrr_ck_leaf" ;;
        *)  if _rrr_ck_is_shell "$_rrr_ck_leaf"; then return 1; fi
            [ -n "$_rrr_ck_root" ] || return 1
            _rrr_ck_abs="$_rrr_ck_root/$_rrr_ck_leaf" ;;
    esac
    # (6) canonicalise
    _rrr_ck_canon "$_rrr_ck_abs" || return 1
    _RRR_CK_KEY="$_RRR_CK_C"
    [ -n "$_RRR_CK_KEY" ] && [ "$_RRR_CK_KEY" != "/" ] || return 1
    return 0
}

# rrr_cron_cmd_key_of <raw> — the KEY, or "" when uninterpretable. A convenience
# for the two comparison sites so neither can forget the fail-closed default.
rrr_cron_cmd_key_of() {
    if rrr_cron_cmd_key "$1"; then printf '%s' "$_RRR_CK_KEY"; else printf ''; fi
    return 0
}

# rrr_cron_eval — compare the observed rows against the desired config.
# RRR_CRON_STATE: absent_proven_by_cli | cli_visibility_insufficient |
#                 duplicate | mismatch | single | unreadable | unresolved |
#                 store_unconfirmed | store_diverged
#
# `absent_proven_by_cli`  — nothing visible, and the CLI's OWN listing was asked
#                           for a full-status flag (visibility=full), so it could
#                           have shown a DISABLED job and returned none. That —
#                           and only that — is a proven absence. (Before the
#                           re-review this was `cli_only_absent`, and a resolved
#                           gateway store could also produce a bare `absent`;
#                           neither is emitted any more, because a store file is
#                           not proof that it reflects the gateway.)
# `cli_visibility_insufficient` — nothing visible and NO view that can show a
#                           DISABLED job was available (the CLI advertised no
#                           full-status flag, or its listing was unreadable).
#                           A hidden disabled job cannot be distinguished from
#                           an absent one, so the reconciler refuses to mutate.
# `store_unconfirmed`     — only the gateway STORE shows the managed name: the
#                           CLI's own listing could not be read, so the store's
#                           rows cannot be corroborated and never establish
#                           readiness (they may still veto a write).
# `store_diverged`        — the CLI's own listing and the store contradict each
#                           other about the managed name. Two views that do not
#                           describe the same gateway prove nothing, so no state
#                           is claimed and no write is licensed.
rrr_cron_eval() {
    RRR_CRON_STATE=""; RRR_CRON_MISMATCH=""; RRR_CRON_UNOBS=""; RRR_CRON_DISAGREE=""
    RRR_CRON_COUNT=0; RRR_CRON_ID=""; RRR_CRON_IDS=""; RRR_CRON_MATCH_IDS=""
    RRR_CRON_SCHEDULE=""; RRR_CRON_COMMAND=""; RRR_CRON_ENABLED=""; RRR_CRON_DELIVERY=""
    RRR_CRON_DISABLED_DIRECT=0
    RRR_CRON_CLI_IDS=""; RRR_CRON_DB_IDS=""; RRR_CRON_DB_ENABLED_IDS=""; RRR_CRON_DISABLED_IDS=""
    RRR_CRON_ENABLED_IDS=""; RRR_CRON_ENABLED_OBSERVED=0; RRR_CRON_STORE_NOTE=""
    RRR_DB_AUTHORITY="none"
    _rrr_ce_wantcmd="sh $RRR_POLL"
    # Normalised ONCE, for both comparison sites. An unresolvable desired
    # command yields "" and then matches NOTHING (fail-closed): readiness can
    # never be claimed against a desired config this engine cannot name.
    _rrr_ce_wantkey="$(rrr_cron_cmd_key_of "$_rrr_ce_wantcmd")"
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
        # Which VIEW showed this id, and was the row observed DISABLED? The
        # reconciler uses this to corroborate the store against the CLI's own
        # listing and to refuse removing a row this readback cannot trust.
        case "$_rrr_ce_src" in
            cli) RRR_CRON_CLI_IDS="$RRR_CRON_CLI_IDS $_rrr_ce_id" ;;
            db)  RRR_CRON_DB_IDS="$RRR_CRON_DB_IDS $_rrr_ce_id"
                 [ "$_rrr_ce_en" = "true" ] && RRR_CRON_DB_ENABLED_IDS="$RRR_CRON_DB_ENABLED_IDS $_rrr_ce_id" ;;
        esac
        [ "$_rrr_ce_en" = "false" ] && RRR_CRON_DISABLED_IDS="$RRR_CRON_DISABLED_IDS $_rrr_ce_id"
        # Did ANY view report a boolean `enabled` for this name? A row whose
        # enabled bit no view reports cannot be told apart from an
        # operator-disabled one, and it is protected on every mutating path.
        case "$_rrr_ce_en" in
            true)  RRR_CRON_ENABLED_OBSERVED=1
                   RRR_CRON_ENABLED_IDS="$RRR_CRON_ENABLED_IDS $_rrr_ce_id" ;;
            false) RRR_CRON_ENABLED_OBSERVED=1 ;;
        esac
        # unobservable fields (per view)
        if [ -n "$_rrr_ce_miss" ] && [ "$_rrr_ce_miss" != "$RRR_RS" ]; then
            RRR_CRON_UNOBS="${RRR_CRON_UNOBS}${RRR_CRON_UNOBS:+,}$_rrr_ce_miss"
        fi
        # Does THIS row already satisfy the desired config? Used by the dedupe
        # step to keep a good job and remove the strays. The command is
        # compared by NORMALISED KEY (rrr_cron_cmd_key), never as raw bytes:
        # see the normalisation rule above. A command this readback cannot
        # interpret keys as "" and therefore matches nothing.
        _rrr_ce_cmdkey="$(rrr_cron_cmd_key_of "$_rrr_ce_cmd")"
        if [ "$_rrr_ce_sch" = "$RRR_SCHEDULE" ] \
           && [ -n "$_rrr_ce_wantkey" ] && [ "$_rrr_ce_cmdkey" = "$_rrr_ce_wantkey" ] \
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
    rrr_cron_store_authority
    if [ "$RRR_CRON_COUNT" -eq 0 ]; then
        case "$RRR_COVERAGE" in
            none|db-only)
                # The gateway's OWN answer is missing (the CLI's listing could
                # not be read). A store alone can never prove the managed name
                # free (Z-1), so nothing is claimed: this is the existing,
                # retryable `unreadable` readback.
                RRR_CRON_STATE="unreadable" ;;
            *)
                # The CLI answered. Only a CLI that ADVERTISED a full-status
                # listing flag — and was therefore ASKED for one — can show a
                # DISABLED job, and only then does an empty result prove
                # absence. Without that the emptiness is ambiguous and the
                # reconciler refuses (fail-closed).
                case "$RRR_CRON_VISIBILITY" in
                    full) RRR_CRON_STATE="absent_proven_by_cli" ;;
                    *)    RRR_CRON_STATE="cli_visibility_insufficient" ;;
                esac ;;
        esac
        return 0
    fi
    if [ "$RRR_CRON_COUNT" -gt 1 ]; then
        RRR_CRON_STATE="duplicate"
        rrr_cron_authority_gate
        return 0
    fi
    # --- the single job, field by field ---
    _rrr_ce_mism=""
    if [ "$RRR_CRON_SCHEDULE" = "$RRR_SCHEDULE" ]; then :; else
        [ -n "$RRR_CRON_SCHEDULE" ] && _rrr_ce_mism="$_rrr_ce_mism schedule" || _rrr_ce_mism="$_rrr_ce_mism schedule_unobservable"
    fi
    # The command is compared by NORMALISED KEY on BOTH sides (the rule is
    # documented at rrr_cron_cmd_key). An unreadable command is already empty,
    # which reports `command_unobservable`; a readable-but-different one -- or
    # any shape the normaliser refuses -- keys differently from the desired
    # job and reports `command`. Neither can ever match the desired config.
    if [ -n "$_rrr_ce_wantkey" ] \
       && [ "$(rrr_cron_cmd_key_of "$RRR_CRON_COMMAND")" = "$_rrr_ce_wantkey" ]; then :; else
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
        rrr_cron_authority_gate
        return 0
    fi
    RRR_CRON_STATE="single"
    rrr_cron_authority_gate
    return 0
}

# ---------------------------------------------------------------------------
# rrr_cron_store_authority — corroborate the resolved gateway store against the
# CLI's OWN listing (RR-028 re-review Z-1).
#
# The store is a file ocd_state_db resolved; it may be an alternate or older
# candidate. For the MANAGED NAME only (an unrelated agent's job can never look
# like a contradiction), the two views must describe the same gateway:
#   * a row the CLI listing shows that the store does NOT carry, or
#   * a row the store carries that the CLI listing OMITS while the CLI's own
#     view should have shown it — an ENABLED job is listed by every build, and a
#     DISABLED one is listed by a build that was ASKED for a full-status flag
#     (an unobservable enabled bit is a coverage gap, not a contradiction),
# is a contradiction: RRR_DB_AUTHORITY="diverged". A row the store carries that
# the CLI's listing does not show, and that is NOT provably contradictory, is
# still NOT a corroborated row: the store is then "unconfirmed" — it may veto a
# write, but it never establishes readiness and is never reported as
# corroborated (RR-028 review AD-1). With every store row matched by the CLI's
# own listing and vice versa the store is "corroborated"; with no readable CLI
# listing it is "unconfirmed" (it may veto, never establish).
# Contradictions are appended to RRR_CRON_DISAGREE, the existing report field;
# a merely-uncorroborated row is reported as RRR_CRON_STORE_NOTE (a coverage
# gap, NOT a disagreement).
# ---------------------------------------------------------------------------
rrr_cron_store_authority() {
    RRR_DB_AUTHORITY="none"
    [ "$RRR_DB_STATE" = "ok" ] || return 0
    case "$RRR_COVERAGE" in
        cli-only|cli+db) : ;;
        *) RRR_DB_AUTHORITY="unconfirmed"; return 0 ;;
    esac
    _rrr_csa_div=""
    _rrr_csa_unconf=""
    for _rrr_csa_id in $RRR_CRON_CLI_IDS; do
        case " $RRR_CRON_DB_IDS " in
            *" $_rrr_csa_id "*) : ;;
            *) _rrr_csa_div="$_rrr_csa_div${_rrr_csa_div:+,}store_missing_row(id=$_rrr_csa_id)" ;;
        esac
    done
    for _rrr_csa_id in $RRR_CRON_DB_IDS; do
        case " $RRR_CRON_CLI_IDS " in
            *" $_rrr_csa_id "*) continue ;;
        esac
        case " $RRR_CRON_DB_ENABLED_IDS " in
            *" $_rrr_csa_id "*) _rrr_csa_div="$_rrr_csa_div${_rrr_csa_div:+,}cli_hides_enabled_row(id=$_rrr_csa_id)"; continue ;;
        esac
        if [ "$RRR_CRON_VISIBILITY" = "full" ]; then
            case " $RRR_CRON_DISABLED_IDS " in
                *" $_rrr_csa_id "*) _rrr_csa_div="$_rrr_csa_div${_rrr_csa_div:+,}cli_all_omits_disabled_row(id=$_rrr_csa_id)"; continue ;;
            esac
        fi
        # Neither proven-contradictory case applies: the CLI's own listing does
        # not show this row and nothing proves it SHOULD have (an ENABLED job is
        # listed by every build; a DISABLED one by a build that was asked for a
        # full-status flag). The row may belong to an alternate/stale candidate,
        # or be a genuinely hidden disabled job — either way the CLI never
        # corroborated it, so this store is AT MOST `unconfirmed` for this name.
        # (RR-028 review AD-1: "corroborated" used to be reported here for a
        # store the CLI's own listing never confirmed — a false report.)
        _rrr_csa_unconf="$_rrr_csa_unconf${_rrr_csa_unconf:+,}store_row_omitted_by_cli(id=$_rrr_csa_id)"
    done
    if [ -n "$_rrr_csa_div" ]; then
        RRR_DB_AUTHORITY="diverged"
        RRR_CRON_DISAGREE="${RRR_CRON_DISAGREE}${RRR_CRON_DISAGREE:+,}${_rrr_csa_div}"
    elif [ -n "$_rrr_csa_unconf" ]; then
        # A coverage gap, not a contradiction: it is NOT appended to
        # RRR_CRON_DISAGREE (that field means "the two views contradict each
        # other"), but it does stop the store being called corroborated.
        RRR_DB_AUTHORITY="unconfirmed"
        RRR_CRON_STORE_NOTE="$_rrr_csa_unconf"
    else
        RRR_DB_AUTHORITY="corroborated"
    fi
    return 0
}

# rrr_cron_authority_gate — a store that cannot be corroborated licenses no
# success claim. Called on every state that observed at least one row.
#
# A `diverged` store always overrides the state (two views that contradict each
# other prove nothing). An `unconfirmed` store can never ESTABLISH readiness, so
# a state that would claim the job scheduled is refused outright; but a state
# that already REFUSES (mismatch / duplicate) keeps its more specific name — the
# report's `cron.store` field still says the store was not corroborated, and the
# ladder's own guards decide what (if anything) may be mutated.
rrr_cron_authority_gate() {
    case "$RRR_DB_AUTHORITY" in
        diverged)    RRR_CRON_STATE="store_diverged" ;;
        unconfirmed)
            case "$RRR_COVERAGE" in
                # The CLI's own listing could not be read at all.
                db-only) RRR_CRON_STATE="store_unconfirmed" ;;
                *) case "$RRR_CRON_STATE" in
                       single) RRR_CRON_STATE="store_unconfirmed" ;;
                   esac ;;
            esac ;;
    esac
    return 0
}

# ---------------------------------------------------------------------------
# Readiness receipt read/write. A receipt is a small JSON record under
# <state>/readiness/receipt-<digest>.json. It is the ONLY thing that can lift a
# box from SCHEDULED to VERIFIED, and it must match the CURRENT digest AND the
# CURRENT runtime id.
#
# WHAT VERIFIED DOES AND DOES NOT MEAN (RR-028 re-review M-3): the receipt is a
# plain local FILE recording that a safe test claim was answered in this
# runtime. Nothing authenticates it — there is no signature, no HMAC and no
# signing key on the box — so a hand-written file carrying the printed digest,
# runtime id and claim fields is indistinguishable from one this engine wrote.
# VERIFIED is therefore a local liveness attestation, not a tamper-proof one.
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
        #
        # M-6: with SEVERAL superseded receipts on the box, naming the first one
        # in glob order reports an unrelated receipt's digest/at. Report the one
        # that actually matters — the NEWEST receipt from THIS runtime, since that
        # is the probe the operator most likely ran before the config changed —
        # and name its file so any remaining ambiguity is visible rather than
        # implied.
        _rrr_rr_other=""; _rrr_rr_other_at=""; _rrr_rr_other_rt=""; _rrr_rr_other_same=0
        if [ -d "$_rrr_rr_dir/readiness" ]; then
            for _rrr_rr_c in "$_rrr_rr_dir"/readiness/receipt-*.json; do
                [ -f "$_rrr_rr_c" ] || continue
                _rrr_rr_cjson="$(cat "$_rrr_rr_c" 2>/dev/null)"
                _rrr_rr_cat="$(rrr_json_get "$_rrr_rr_cjson" "at")"
                _rrr_rr_crt="$(rrr_json_get "$_rrr_rr_cjson" "runtime_id")"
                _rrr_rr_csame=0
                if [ -n "$_rrr_rr_crt" ] && [ "$_rrr_rr_crt" = "$_rrr_rr_runtime" ]; then _rrr_rr_csame=1; fi
                if [ -z "$_rrr_rr_other" ]; then
                    _rrr_rr_other="$_rrr_rr_c"; _rrr_rr_other_at="$_rrr_rr_cat"
                    _rrr_rr_other_rt="$_rrr_rr_crt"; _rrr_rr_other_same="$_rrr_rr_csame"
                    continue
                fi
                # A receipt from the INTENDED runtime beats a foreign one; within
                # the same class the newest `at` wins (ISO-8601 UTC sorts
                # lexically). An empty `at` never displaces a dated receipt.
                _rrr_rr_better=0
                if [ "$_rrr_rr_csame" = "1" ] && [ "$_rrr_rr_other_same" != "1" ]; then
                    _rrr_rr_better=1
                elif [ "$_rrr_rr_csame" = "$_rrr_rr_other_same" ]; then
                    if [ -n "$_rrr_rr_cat" ] \
                       && { [ -z "$_rrr_rr_other_at" ] \
                            || [ "$_rrr_rr_cat" \> "$_rrr_rr_other_at" ]; }; then
                        _rrr_rr_better=1
                    fi
                fi
                if [ "$_rrr_rr_better" = "1" ]; then
                    _rrr_rr_other="$_rrr_rr_c"; _rrr_rr_other_at="$_rrr_rr_cat"
                    _rrr_rr_other_rt="$_rrr_rr_crt"; _rrr_rr_other_same="$_rrr_rr_csame"
                fi
            done
        fi
        if [ -n "$_rrr_rr_other" ] && [ "$RRR_REQ_JSON" = "ok" ]; then
            _rrr_rr_ojson="$(cat "$_rrr_rr_other" 2>/dev/null)"
            _rrr_rr_odigest="$(rrr_json_get "$_rrr_rr_ojson" "digest")"
            _rrr_rr_oat="$(rrr_json_get "$_rrr_rr_ojson" "at")"
            RRR_RECEIPT_AT="$_rrr_rr_oat"
            RRR_RECEIPT_RUNTIME="$_rrr_rr_other_rt"
            RRR_RECEIPT_STATE="stale"
            RRR_RECEIPT_DETAIL="a receipt exists for a DIFFERENT desired-config digest (${_rrr_rr_odigest:-unknown}); the desired config changed since that probe, so the old verdict is void. Named here is the NEWEST superseded receipt from this runtime ($(basename "$_rrr_rr_other") at ${_rrr_rr_oat:-unknown}); other superseded receipts may also exist."
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
            RRR_DETAIL="the CLI's own cron listing could not be read back (coverage=$RRR_COVERAGE, store=$RRR_DB_STATE); absence is never inferred from the gateway store alone, so nothing is claimed" ;;
        unresolved)
            RRR_STATE="ENROLLED_PENDING"; RRR_REASON="cron_capability_unresolved"
            RRR_DETAIL="openclaw CLI unresolved, so no cron can be listed" ;;
        absent_proven_by_cli)
            RRR_STATE="ENROLLED_PENDING"; RRR_REASON="cron_absent"
            RRR_DETAIL="no cron named $RRR_NAME in the readback; the CLI's OWN listing was asked for a full-status listing and reported none, which is what proves the absence (coverage=$RRR_COVERAGE)" ;;
        store_unconfirmed)
            # FAIL CLOSED (re-review Z-1, widened by review AD-1): the resolved
            # store is not corroborated by the CLI's own listing — either that
            # listing could not be read, or it does not show a row the store
            # carries. The store is a file ocd_state_db resolved, so it is never
            # treated as proof of readiness.
            RRR_STATE="ENROLLED_PENDING"; RRR_REASON="cron_store_unconfirmed"
            RRR_DETAIL="the gateway STORE is not corroborated by the CLI's own cron listing for $RRR_NAME (store=$RRR_DB_STATE, coverage=$RRR_COVERAGE${RRR_CRON_STORE_NOTE:+; $RRR_CRON_STORE_NOTE}), so it cannot establish readiness. Nothing is mutated; fix the CLI readback (or point the descriptor at the gateway's live state DB) and reconcile again." ;;
        store_diverged)
            # FAIL CLOSED (re-review Z-1/Z-2): two views that contradict each
            # other about this name do not describe the same gateway, so neither
            # can license a write and no readiness is claimed.
            RRR_STATE="ENROLLED_PENDING"; RRR_REASON="cron_source_disagreement"
            RRR_DETAIL="the CLI's own listing and the gateway store DISAGREE about $RRR_NAME ($RRR_CRON_DISAGREE): a store that does not reflect the gateway licenses nothing and proves nothing. Nothing was mutated. Point the descriptor at the gateway's live state DB (or remove the stale candidate) and reconcile again." ;;
        cli_visibility_insufficient)
            # FAIL CLOSED (RR-028 review M-1, widened by re-review Z-1). The CLI
            # listed nothing, but no view that can show a DISABLED job was
            # available, so the engine cannot tell "no such cron" from "the
            # operator's cron is disabled and hidden". Reporting
            # ENROLLED_PENDING here — and never SCHEDULED — is the honest
            # verdict; the reconciler refuses to ADD in this state, because an add
            # would create a second, ENABLED poller beside the operator's
            # disabled one. A resolved gateway store is NOT a substitute: a file
            # that resolves is not a file that reflects the gateway.
            RRR_STATE="ENROLLED_PENDING"; RRR_REASON="cron_state_unverifiable"
            RRR_DETAIL="no cron named $RRR_NAME is VISIBLE, but this readback cannot prove it is absent: no view that can SHOW a disabled job was available (coverage=$RRR_COVERAGE, visibility=$RRR_CRON_VISIBILITY), so 'absent' and 'present-but-DISABLED' are indistinguishable. Refusing to add (fail-closed): register nothing rather than risk a second ENABLED poller beside an operator-disabled job. Remedy: run a CLI that ADVERTISES a full-status listing flag (--all / --include-disabled / --show-disabled) so the CLI itself can list disabled jobs — a readable state DB alone is not accepted as proof." ;;
        duplicate)
            RRR_STATE="ENROLLED_PENDING"; RRR_REASON="cron_duplicate"
            RRR_DETAIL="readback shows $RRR_CRON_COUNT jobs named $RRR_NAME (ids:$RRR_CRON_IDS)" ;;
        mismatch)
            if [ "$RRR_CRON_DISABLED_DIRECT" = "1" ]; then
                RRR_STATE="ENROLLED_PENDING"; RRR_REASON="cron_disabled_by_owner"
                RRR_DETAIL="cron $RRR_NAME exists but is DISABLED; readiness never re-enables an operator-disabled job it can SEE — and when the readback cannot see one (CLI-only coverage, no full-status flag) it refuses to add at all, so a hidden disable is never guessed away either (mismatches:$RRR_CRON_MISMATCH)"
            elif [ "$RRR_CRON_ENABLED_OBSERVED" != "1" ]; then
                # AD-2/AD-7 (RR-028 review): the row exists but NO view reports
                # its `enabled` bit, so an operator-disabled job is
                # indistinguishable from an enabled one. The reconciler refuses
                # to edit, replace or remove it; the state says exactly that.
                RRR_STATE="ENROLLED_PENDING"; RRR_REASON="cron_enabled_unobservable"
                RRR_DETAIL="cron ${RRR_CRON_ID:-$RRR_NAME} does not match the desired config (mismatches:$RRR_CRON_MISMATCH) AND no view reported its enabled bit, so it cannot be told apart from a job the operator switched OFF. Refusing to edit/replace/remove it (fail-closed, nothing mutated): a job this readback cannot see the switch state of is never touched. Remedy: a CLI/gateway store that reports the job's enabled state so the mismatch can be repaired safely."
            else
                RRR_STATE="ENROLLED_PENDING"; RRR_REASON="cron_field_mismatch"
                RRR_DETAIL="readback of ${RRR_CRON_ID:-$RRR_NAME} does not match the desired config: $RRR_CRON_MISMATCH${RRR_CRON_STORE_NOTE:+ (gateway store: $RRR_CRON_STORE_NOTE — not corroborated, so it licenses nothing)}"
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
            RRR_DETAIL="cron $RRR_CRON_ID read back matching the desired digest and a safe test claim receipt ($RRR_RECEIPT_AT) recorded a no-work answer from the intended runtime (a local file record: unauthenticated, see the receipt contract)"
            ;;
        absent)
            RRR_STATE="SCHEDULED"
            RRR_REASON="ready_receipt_absent"
            RRR_DETAIL="cron $RRR_CRON_ID read back matching; NO verified safe-test-claim receipt for digest $RRR_DIGEST (run rr-readiness.sh --probe)"
            ;;
        stale)
            RRR_STATE="SCHEDULED"
            RRR_REASON="ready_receipt_stale"
            # Z-6 (re-review): the M-6 detail was computed and then DISCARDED
            # here, so "names the file / NEWEST superseded receipt" could never
            # be observed. It is appended now, which is what makes the claim
            # checkable in the printed detail.
            RRR_DETAIL="the desired config changed since the last probe (digest mismatch); the old receipt is void${RRR_RECEIPT_DETAIL:+ — $RRR_RECEIPT_DETAIL}"
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
    printf '"cron":{"state":"%s","count":%s,"id":"%s","sources":"%s","coverage":"%s","visibility":"%s","store":"%s","schedule":"%s","command":"%s","enabled":"%s","delivery":"%s","unobservable":"%s","disagreement":"%s","store_note":"%s"},' \
        "$RRR_CRON_STATE" "$RRR_CRON_COUNT" "$(rrr_json_escape "$RRR_CRON_ID")" "$(rrr_json_escape "$RRR_CRON_SOURCES")" \
        "$RRR_COVERAGE" "$RRR_CRON_VISIBILITY" "$RRR_DB_AUTHORITY" "$(rrr_json_escape "$RRR_CRON_SCHEDULE")" "$(rrr_json_escape "$RRR_CRON_COMMAND")" \
        "$RRR_CRON_ENABLED" "$RRR_CRON_DELIVERY" "$(rrr_json_escape "$RRR_CRON_UNOBS")" "$(rrr_json_escape "$RRR_CRON_DISAGREE")" \
        "$(rrr_json_escape "$RRR_CRON_STORE_NOTE")"
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
# rrr_cron_removable <id> — MAY readiness remove this observed job id?
#
# Removal is the one irreversible act in the ladder, so it needs corroboration
# (RR-028 re-review Z-1/Z-2, widened by review AD-1/AD-2/AD-7). A job may be
# removed only when
#   * the gateway's OWN listing shows it — a row ONLY the store shows is not
#     corroborated (the store may be an alternate or stale candidate), and
#   * the enabled bit was OBSERVED and TRUE — a row whose `enabled` state no
#     view reports cannot be told apart from an operator-disabled one, and
#     "we could not see it" must never authorise destroying it, and
#   * it was never observed DISABLED — deleting a job the operator switched off
#     destroys operator intent exactly as re-enabling it would.
# ---------------------------------------------------------------------------
rrr_cron_removable() {
    _rrr_rem_id="$1"
    [ -n "$_rrr_rem_id" ] || return 1
    case " $RRR_CRON_DISABLED_IDS " in *" $_rrr_rem_id "*) return 1 ;; esac
    case " $RRR_CRON_CLI_IDS " in *" $_rrr_rem_id "*) : ;; *) return 1 ;; esac
    case " $RRR_CRON_ENABLED_IDS " in *" $_rrr_rem_id "*) return 0 ;; esac
    return 1
}

# ---------------------------------------------------------------------------
# rrr_cron_reconcile — make the desired job true, then READ IT BACK.
#   0 single matching job proven by readback
#   3 readback unavailable (nothing claimed) — includes `store_unconfirmed`,
#     where only the store shows the job and the CLI's own listing is unreadable
#   4 the readback does not prove the desired job after the ladder, OR the
#     readback/licence itself is refused as untrustworthy: `store_diverged`
#     (the store contradicts the CLI's own listing) and `duplicate_protected` /
#     `replace_protected` (a stray readiness may not delete: operator-disabled,
#     or visible only in the store)
#   5 openclaw CLI unresolved
#   6 tombstoned / disabled by owner (never mutated)
#   7 a mutation command itself failed (retryable wiring failure)
#   8 REFUSED — this readback cannot prove the name free, or cannot see the
#     switch state of the row it would touch. Either (a) no view that can SHOW a
#     DISABLED job was available, so an add would risk a second ENABLED poller
#     beside an operator-disabled job, or (b) NO view reported the row's
#     `enabled` bit, so it cannot be told apart from an operator-disabled one
#     and is neither edited, replaced nor removed. Nothing was mutated and
#     nothing is claimed; this is the fail-closed choice, not a failure. (A
#     resolved gateway store does NOT lift either refusal — see the header
#     rule.)
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
            store_unconfirmed)
                # Only the store shows the job and the CLI's own listing is
                # unreadable: the store cannot be corroborated, so it may veto
                # but never establish. Nothing is claimed, nothing is mutated.
                RRR_RECONCILE_STATE="store_unconfirmed"
                rm -f "$_rrr_cr_tmp"* 2>/dev/null
                RRR_RECONCILE_RC=3; return 3 ;;
            unreadable|unresolved)
                RRR_RECONCILE_STATE="readback_unavailable"
                rm -f "$_rrr_cr_tmp"* 2>/dev/null
                RRR_RECONCILE_RC=3; return 3 ;;
            store_diverged)
                # The two views contradict each other: nothing they say is
                # licensed by the other, so mutate nothing and claim nothing.
                RRR_RECONCILE_STATE="store_diverged"
                rm -f "$_rrr_cr_tmp"* 2>/dev/null
                RRR_RECONCILE_RC=4; return 4 ;;
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
                        if [ "$RRR_CRON_ENABLED_OBSERVED" != "1" ]; then
                            # AD-2/AD-7 (RR-028 review): NO view reported the
                            # `enabled` bit for this name, so the engine cannot
                            # tell an operator-DISABLED job from an ENABLED one.
                            # Editing it rewrites a job whose switch state is
                            # unknown, and the ladder's next rung would REMOVE
                            # it. Refuse instead: "we could not see it" must
                            # never authorise touching it. Fail-closed, in the
                            # same family as the CLI-blind-spot refusal.
                            RRR_RECONCILE_STATE="enabled_unobservable"
                            rm -f "$_rrr_cr_tmp"* 2>/dev/null
                            RRR_RECONCILE_RC=8; return 8
                        fi
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
                    if ! rrr_cron_removable "$RRR_CRON_ID"; then
                        # Never replace a job this readback cannot corroborate
                        # (store-only row) — the rm half of replace is still a rm.
                        RRR_RECONCILE_STATE="replace_protected"
                        rm -f "$_rrr_cr_tmp"* 2>/dev/null
                        RRR_RECONCILE_RC=4; return 4
                    fi
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
                    _rrr_cr_blocked=0; _rrr_cr_removed=0
                    for _rrr_cr_id in $RRR_CRON_IDS; do
                        [ "$_rrr_cr_id" = "$_rrr_cr_keep" ] && continue
                        if rrr_cron_removable "$_rrr_cr_id"; then
                            rrr_argv_run "$_rrr_cr_tmp.mut" "$_rrr_cr_tmp.err" "$RRR_OPENCLAW_BIN" cron rm "$_rrr_cr_id" || true
                            [ "$RRR_ARGV_RC" -ne 0 ] && _rrr_cr_mut_rc="$RRR_ARGV_RC"
                            _rrr_cr_removed=1
                        else
                            # Operator-disabled, or visible only in the store.
                            # Deleting either destroys intent or a job this
                            # readback cannot corroborate: refuse instead.
                            _rrr_cr_blocked=1
                        fi
                    done
                    [ "$_rrr_cr_removed" = "1" ] && RRR_RECONCILE_ACTION="dedupe"
                    if [ "$_rrr_cr_blocked" = "1" ]; then
                        RRR_RECONCILE_STATE="duplicate_protected"
                        rm -f "$_rrr_cr_tmp"* 2>/dev/null
                        RRR_RECONCILE_RC=4; return 4
                    fi
                    continue
                fi
                RRR_RECONCILE_STATE="duplicate_unreconciled"
                rm -f "$_rrr_cr_tmp"* 2>/dev/null
                RRR_RECONCILE_RC=4; return 4 ;;
            cli_visibility_insufficient)
                # FAIL CLOSED (RR-028 review M-1, widened by re-review Z-1): no
                # view that can SHOW a disabled job was available, so "nothing
                # visible" is NOT proof that the name is free. Adding here would
                # register a SECOND, ENABLED poller beside a disabled job of the
                # same name (double delivery), and a later readback that does see
                # the disabled job turns that into `cron_duplicate` whose dedupe
                # could only ever delete the operator's job. A resolved gateway
                # store does not lift this refusal: a file that resolves is not a
                # file that reflects the gateway (Z-1). Refuse to mutate and say
                # exactly why.
                RRR_RECONCILE_STATE="visibility_insufficient"
                rm -f "$_rrr_cr_tmp"* 2>/dev/null
                RRR_RECONCILE_RC=8; return 8 ;;
            absent_proven_by_cli)
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
