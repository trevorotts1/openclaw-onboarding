#!/bin/sh
#
# rescue-poll.sh — box-side PULL client for Rescue Rangers coaching delivery.
#
# One POSIX shell script, shipped identically to every fleet box by the repo roll
# (update-skills.sh -> this skill dir -> wire.sh), registered as an OpenClaw
# `kind:command` cron running every 2 minutes. It makes an OUTBOUND HTTPS call to
# the RR-07 receiver gateway, claims AT MOST ONE queued coaching instruction for
# its own box, runs the already-proven local delivery command (the client's own
# `openclaw agent` turn in an isolated per-ticket session), and acks a verdict.
#
# THE HONESTY CONTRACT (non-negotiable):
#   ack `delivered` ONLY when the delivery command returned exit_code 0 AND a
#   non-empty reply was extracted. Everything else acks `failed`. Ambiguous is
#   never fixed. A box that stays silent leaves its ticket non-terminal so the
#   SLA machinery pages a human.
#   v1.3.0: an exit-0 non-empty reply whose TEXT says the job was not done
#   (escalation/deferral language) is not a delivery — it acks `failed` with
#   fail_reason `escalation_language` and carries a reply_excerpt of the text.
#
# ROLL-SAFETY:
#   * The script lives in the repo-managed skills tree; a roll OVERWRITES it.
#   * Per-box token/slug/URL live in the box's OWN secret store
#     (<ocroot>/secrets/.env) — a roll never touches that file.
#   * The local dedup ledger lives in <ocroot>/state/rr-receiver/done/ — a roll
#     never touches <ocroot>/state/. Box-side dedup therefore survives both a
#     reboot and a fleet roll.
#
# TOKEN DISCIPLINE:
#   The bearer token is read from the secret store into a NON-EXPORTED shell
#   variable and handed to curl via a 0600 header file (curl `-H @file`). It is
#   NEVER placed in argv, NEVER exported to a child, and NEVER written to a log.
#   (An exported variable is visible to `ps eww` on the child; argv is visible to
#   `ps -o command`. Both are leaks on this fleet.)
#
# FAIL CLOSED AND QUIET:
#   No token / no config / no network => exit 0 without acting and without
#   spamming logs. It runs every 2 minutes on 38 machines forever.
#
# RECEIVER_VERSION: reported in every claim and ack (fleet version visibility).
#
# v1.5.0 (RR-W3-INSTALL, RR-027): the secret store is PARSED, not sourced.
# The old `. "$_SECRETS"` executed the file as shell and left whatever the
# CALLER's environment had already exported (a synthetic RR_BOX_TOKEN in an
# upstream env file — the CONFIRMED RCV05 leak) untouched in this process's
# env, where the child agent turn inherited it despite the comment above.
# Now: the shared dotenv parser (shared-utils/rescue-env.sh) reads ONLY the
# three required rescue values, preserves quoting/space behavior, never
# expands values, fails visibly (logged, values never printed) on malformed
# lines, and every child — agent turn, default-agent probe — runs through
# rescue_env_scrub so NO rescue credential alias can survive into any child
# env, while the box's necessary authorized model/tool credentials pass
# through untouched. Exception/trace output from the agent is reduced to a
# failure CLASS (never logged verbatim) so a stack-trace env echo cannot
# leak a credential into the poll log.
#
# v1.6.0 (RR-W3-PROTOCOL, RR-008): the delivery/ACK path is a durable state
# machine. A DURABLE ATTEMPT JOURNAL (state/rr-receiver/journal/, 0600, atomic
# + fsync) is written BEFORE every effect, and the complete outcome and proof
# (verdict, exit, chars, reason, elapsed, REPLY EXCERPT, operation id, attempt
# identity) is saved atomically as ACK_PENDING (state/rr-receiver/ack-pending/)
# before the ack is posted. The ack is resent BYTE-FOR-BYTE under the same
# operation id until a MATCHING STRUCTURED RECEIPT arrives: an expected 2xx
# carrying JSON whose receipt.operation_id matches ours and which names a
# state_revision. 302, 200-HTML, 401/403, 429, 5xx and a dropped response are
# all FAILURES with a visible class; a bare 2xx is never a confirmation. The
# old `2*|3*)` success case is GONE — a redirect (CF Access login wall, moved
# webhook) previously looked like a successful delivery. Journal failure stops
# new effects (the agent turn does not start, the ack is held); an unconfirmed
# ack is an uncertain external effect that is reconciled before anything is
# rerun. Retention is bounded: confirmed journal rows are GC'd after 14 days,
# unconfirmed ones are NEVER silently dropped (moved to reconcile/ as an owned
# obligation after 30 days). Permissions are private (0700 dirs / 0600 files).
#
# v1.4.0 (RR-W2-CORE, RR-004 pairing): ADDITIVE claim/ack fields. The server
# (RR-07 / the Fleet Ops transactional claim service) now issues an
# attempt/owner token, a lease generation and an explicit lease expiry on every
# claim. The receiver echoes them verbatim on the ack — it does NOT interpret,
# gate on, or require them yet. Strict mode arrives only AFTER the server
# contract is confirmed additive-compatible (SPEC RR-004 shared rollout
# contract: public receiver changes pair with additive server support FIRST;
# old servers that omit the fields keep working because the fields simply echo
# as empty strings).
RECEIVER_VERSION="1.6.0"

# Attempt identity echoed from the claim (empty when the server is pre-RR-004).
# Initialized empty so `set -u` never trips on the cached-re-ack path.
ATTEMPT_ID=""
ATTEMPT_GENERATION=""
LEASE_EXPIRES_AT=""

# ---------------------------------------------------------------------------
# OpenClaw root resolution. <root>/secrets/.env holds enrollment credentials.
# ---------------------------------------------------------------------------
_OCROOT=""
if [ -d /data/.openclaw ]; then
    _OCROOT="/data/.openclaw"          # VPS / container
elif [ -d "$HOME/.openclaw" ]; then
    _OCROOT="$HOME/.openclaw"          # Mac tunnel box
fi

# No root at all => nothing to act on. Silent, clean exit.
[ -n "$_OCROOT" ] || exit 0

_SECRETS="$_OCROOT/secrets/.env"
[ -f "$_SECRETS" ] || exit 0

# ---------------------------------------------------------------------------
# RR-027 credential hygiene: PARSE the documented dotenv store instead of
# sourcing it as shell. The old `. "$_SECRETS"` executed the file's lines as
# shell code (a hostile or simply malformed line gained shell semantics, an
# unescaped `$` silently expanded to empty) and left every variable in the
# file in this process's variable table — a synthetic `export RR_BOX_TOKEN`
# line in any upstream env file reached the CHILD AGENT below despite the
# comments claiming it never exports, because an export made BEFORE this
# script ran is simply inherited and nothing ever removed it.
#
# The SHARED parser (shared-utils/rescue-env.sh) reads ONLY the three
# required rescue values, keeps quoting/space behavior, never expands
# values, and reports malformed lines on stderr BY NAME AND LINE NUMBER
# (never a value). A store that carries malformed lines is a visible
# failure (exit 0 with the reason logged — the poll never silently runs a
# half-parsed config), never a guessed half-success.
# ---------------------------------------------------------------------------
_POLL_HELPERS=""
for _cand in "$_OCROOT/skills/shared-utils/rescue-env.sh" \
             "${_POLL_SELF_DIR:-}" ; do
    [ -n "$_cand" ] && [ -f "$_cand" ] && { _POLL_HELPERS="$_cand"; break; }
done
if [ -z "$_POLL_HELPERS" ]; then
    # The poll script lives at <root>/skills/65-rescue-receiver/ on a box;
    # the shared helper is at <root>/skills/shared-utils/. Derive from the
    # script's own path when it was invoked as a file (the cron does).
    _SELF="$0"
    case "$_SELF" in
        */65-rescue-receiver/rescue-poll.sh)
            _poll_dir="${_SELF%/*}"
            _cand="$_poll_dir/../shared-utils/rescue-env.sh"
            [ -f "$_cand" ] && _POLL_HELPERS="$_cand"
            ;;
    esac
fi
if [ -z "$_POLL_HELPERS" ]; then
    # Fail closed and quiet (the cron contract): the roll will repair the
    # missing helper on the next pass; without it we must not fall back to
    # sourcing the store as shell — that is exactly the defect RR-027 fixes.
    exit 0
fi
# shellcheck disable=SC1090
. "$_POLL_HELPERS"

RR_RECEIVER_URL=""
RR_BOX_TOKEN=""
RR_BOX_SLUG=""
_src_malformed=0
_rr_val=""
_rr_rc=0
_rr_val=$(rescue_env_get "$_SECRETS" RR_RECEIVER_URL 2>/dev/null); _rr_rc=$?
case "$_rr_rc" in 0|3) RR_RECEIVER_URL="$_rr_val" ;; 2) exit 0 ;; esac
[ "$_rr_rc" = 3 ] && _src_malformed=1
_rr_val=$(rescue_env_get "$_SECRETS" RR_BOX_TOKEN 2>/dev/null); _rr_rc=$?
case "$_rr_rc" in 0|3) RR_BOX_TOKEN="$_rr_val" ;; 2) exit 0 ;; esac
[ "$_rr_rc" = 3 ] && _src_malformed=1
_rr_val=$(rescue_env_get "$_SECRETS" RR_BOX_SLUG 2>/dev/null); _rr_rc=$?
case "$_rr_rc" in 0|3) RR_BOX_SLUG="$_rr_val" ;; 2) exit 0 ;; esac
[ "$_rr_rc" = 3 ] && _src_malformed=1
# The values land in NON-EXPORTED shell variables (assignment in the main
# shell only; no `export` anywhere in this file — the scrub below enforces
# it for the child even if the caller's environment exported a rescue alias
# before this script started).
#
# RR-027 child scrub list for THIS script: an agent turn seeded from a
# ticket is NOT the box's own escalation path, so the shared escalation
# secret is removed too (the box's own AGENTS.md escalation flow keeps its
# credential — it does not run through this poll). RESCUE_ENV_EXTRA_UNSET
# is the documented extension hook of rescue-env.sh.

if [ "$_src_malformed" = "1" ]; then
    # Visible malformed-config handling (RR-027 "fail visibly"): replay the
    # parser's reason lines (file+line+shape only, values never printed) to
    # stderr — the cron's stderr is the operator's surface — plus a one-line
    # log record. The poll never runs a half-parsed config.
    mkdir -p "$_OCROOT/state/rr-receiver" 2>/dev/null || true
    rescue_env_parse "$_SECRETS" RR_RECEIVER_URL RR_BOX_TOKEN RR_BOX_SLUG >/dev/null
    printf '%s rr-poll malformed-config config=%s (rescue-env reasons above; values never printed)\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$_SECRETS" \
        >> "$_OCROOT/state/rr-receiver/rescue-poll.log" 2>/dev/null || true
    exit 0
fi

# ---------------------------------------------------------------------------
# Hard-required enrollment. Missing any one => inert-until-enrolled dark state.
# ---------------------------------------------------------------------------
[ -n "${RR_RECEIVER_URL:-}" ] || exit 0
[ -n "${RR_BOX_TOKEN:-}" ]     || exit 0
[ -n "${RR_BOX_SLUG:-}" ]      || exit 0

# ---------------------------------------------------------------------------
# `openclaw` binary resolution. The command cron runs under the gateway's own
# env, which on some boxes lacks the user-local bin dir on PATH — a bare
# `openclaw` call is NOT safe to assume. Resolve to an explicit absolute path
# using this repo's own established fallback-list convention (see
# 23-ai-workforce-blueprint/scripts/migrate-existing-workforce.sh and
# qc-completeness.sh, and rescue-receiver.mjs's OPENCLAW_BIN default of
# `~/.local/bin/openclaw`): PATH lookup first, then every known install
# location across Mac (Homebrew, user-local) and VPS (npm-global, linuxbrew).
# _OC_BIN is used explicitly below; nothing downstream relies on bare PATH
# lookup finding it. PATH is not a secret; the token is never exported.
# ---------------------------------------------------------------------------
_OC_BIN=""
for _cand in "$(command -v openclaw 2>/dev/null)" \
             "$HOME/.local/bin/openclaw" \
             "/opt/homebrew/bin/openclaw" \
             "/usr/local/bin/openclaw" \
             "$HOME/.openclaw/bin/openclaw" \
             "/data/.npm-global/bin/openclaw" \
             "/data/linuxbrew/.linuxbrew/bin/openclaw"; do
    if [ -n "${_cand:-}" ] && [ -x "$_cand" ]; then
        _OC_BIN="$_cand"
        break
    fi
done
# No resolvable binary at all: fall back to the bare name so a PATH the
# checks above could not enumerate (a wrapper shim, an unusual install) still
# gets a chance. If that also fails, the agent call below exits non-zero and
# the honesty contract (verdict=failed) still holds — never a hang, never a
# guessed success.
[ -n "$_OC_BIN" ] || _OC_BIN="openclaw"

# ---------------------------------------------------------------------------
# State + ledger dirs. The `done/` ledger is the box-side dedup cache: one file
# per idempotency_key holding the cached ack verdict. Lives under
# <ocroot>/state/, which the repo roll NEVER writes — this is what makes box-side
# dedup survive a roll.
# ---------------------------------------------------------------------------
_STATE="$_OCROOT/state/rr-receiver"
_DONE="$_STATE/done"
_LOCK="$_STATE/lock"
_LOG="$_STATE/rescue-poll.log"
# Header/body temp files for curl (see _post) live HERE, not in the shared
# system tmp dir — the design's literal rule is "never write outside
# <root>/state/rr-receiver/", and a token-bearing file has no business
# transiting a world-writable-sticky directory shared with every other
# process on the box, even briefly.
_TMP="$_STATE/tmp"

mkdir -p "$_DONE" 2>/dev/null || exit 0
mkdir -p "$_TMP" 2>/dev/null || exit 0
chmod 700 "$_TMP" 2>/dev/null || true

# ---------------------------------------------------------------------------
# Locking: mkdir-based, one poll per box at a time. A lock older than 20 minutes
# is stale (a previous poll was SIGKILLed mid-turn) and is broken by removal.
# This is the onboarding-watchdog's proven stale-lock pattern.
# ---------------------------------------------------------------------------
_try_lock() {
    if mkdir "$_LOCK" 2>/dev/null; then
        return 0
    fi
    if [ -d "$_LOCK" ]; then
        if [ -n "$(find "$_LOCK" -maxdepth 0 -mmin +20 2>/dev/null)" ]; then
            rmdir "$_LOCK" 2>/dev/null || rm -rf "$_LOCK" 2>/dev/null
            if mkdir "$_LOCK" 2>/dev/null; then
                return 0
            fi
        fi
    fi
    return 1
}

_release_lock() {
    rmdir "$_LOCK" 2>/dev/null || true
}

if ! _try_lock; then
    exit 0      # another poll holds the lock; nothing to do this fire
fi
trap _release_lock EXIT HUP INT TERM

# ---------------------------------------------------------------------------
# Minimal log helper. Logs are best-effort and must NEVER contain the token or
# the payload. Lines are deliberately terse.
# ---------------------------------------------------------------------------
_log() {
    printf '%s rr-poll %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >>"$_LOG" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Jitter: 0-45s derived from the slug hash (the design's simultaneous-burst
# avoidance). Skipped entirely if no hash tool is present (jitter 0 is fine).
# ---------------------------------------------------------------------------
_sleep_jitter() {
    # Test/diagnostic hook only: RR_POLL_NO_JITTER=1 skips the sleep. The fleet
    # cron never sets it, so production behavior is unchanged.
    if [ "${RR_POLL_NO_JITTER:-0}" = "1" ]; then
        return 0
    fi
    _hex=""
    if command -v shasum >/dev/null 2>&1; then
        _hex=$(printf '%s' "$RR_BOX_SLUG" | shasum -a 256 2>/dev/null | cut -c1-4)
    elif command -v sha256sum >/dev/null 2>&1; then
        _hex=$(printf '%s' "$RR_BOX_SLUG" | sha256sum 2>/dev/null | cut -c1-4)
    fi
    if [ -n "$_hex" ]; then
        _j=$(( 0x${_hex} % 45 ))
        if [ "$_j" -gt 0 ] 2>/dev/null; then
            sleep "$_j"
        fi
    fi
}

# ---------------------------------------------------------------------------
# A safe JSON string: strip bytes that would break a JSON string literal.
# box_slug and echoed fields are enroll-time values; this is belt-and-braces so a
# hostile slug can never corrupt the request body.
# ---------------------------------------------------------------------------
_json_str() {
    printf '%s' "$1" | tr -d '"' | tr -d '\\' | tr -d '\n\r\t'
}

# ---------------------------------------------------------------------------
# v1.3.0 honesty helpers.
#
# _is_escalation <text> — returns 0 when the reply TEXT says the job was not
# done (escalation / deferral language). Case-insensitive; the apostrophe in
# "don't" is matched as a single-character wildcard so the pattern survives
# shell quoting. A well-formed turn whose text defers to a human is not a
# delivery (see the VERDICT RULE below).
# ---------------------------------------------------------------------------
_is_escalation() {
    printf '%s' "$1" | grep -iE 'could not|unable to|human intervention|i don.t have|needs human|failed to' >/dev/null 2>&1
}

# _bounded_excerpt <text> — the first 500 bytes with line breaks flattened to
# spaces, so the excerpt is a single-line JSON-safe string (the caller still
# runs it through _json_str before interpolating it into the body).
# ---------------------------------------------------------------------------
_bounded_excerpt() {
    printf '%s' "$1" | tr '\n\r\t' '   ' | cut -c1-500
}

# ---------------------------------------------------------------------------
# _post <json-body>
#
# The ONLY HTTP caller in the script. It writes the token to a 0600 temp header
# file and curls with `-H @file` so the token never appears in argv. The body is
# written to a temp file and sent with `--data-binary @file` so the payload never
# appears in argv either. On success (HTTP 2xx ONLY) prints the response body to
# stdout and returns 0. A 3xx is NOT a success: a redirect (CF Access login wall,
# moved webhook, http->https bounce) means the ack never landed. Anything that is
# not 2xx, and any transport failure, returns non-zero with NO stdout.
# ---------------------------------------------------------------------------
_post() {
    _req_body="$1"
    # Invalidate the class globals FIRST. _post_class reads them, so an early
    # return from here (mktemp failure, unwritable _TMP) must never let a
    # PREVIOUS call's 2xx be mistaken for this call's result.
    _POST_CODE=""
    _POST_CT=""
    _POST_BODY=""
    _hdr=""
    _tmpbody=""
    _hdr=$(mktemp "$_TMP/rr-poll-hdr.XXXXXX" 2>/dev/null) || return 1
    _tmpbody=$(mktemp "$_TMP/rr-poll-body.XXXXXX" 2>/dev/null) || { rm -f "$_hdr"; return 1; }
    chmod 600 "$_hdr" 2>/dev/null
    chmod 600 "$_tmpbody" 2>/dev/null
    # RR-027: the header write is a builtin redirection (the value never
    # enters any process argv), into the 0700 private state tmp dir, with a
    # 0600 mode and same-call cleanup (below) — the 0600-header-file contract
    # this script has always documented, now the ONLY path (the shared helper
    # exists for the wire/seed paths that previously lacked one).
    printf 'X-RR-Box-Token: %s\n' "$RR_BOX_TOKEN" > "$_hdr"
    printf '%s' "$_req_body" > "$_tmpbody"
    _out=""
    _code=""
    # curl retry capability. Plain `--retry` never retries POST (non-idempotent)
    # on curl >= 7.71, and `--retry-all-errors` (which re-enables POST retry) is
    # itself unknown to curl < 7.71. Detect once: best = retry-all-errors,
    # fallback = plain --retry (still retries connection-reset/timeout rc=28 path
    # failures on older boxes), none = old one-shot behavior. The fleet carries
    # both curl 7.68 (Ubuntu 20.04) and >= 7.81 (22.04+, Debian 12, macOS 12+).
    _RETRY=""
    if _ver=$(curl --version 2>/dev/null | head -1 | awk '{print $2}'); then
        _maj=${_ver%%.*}; _rest=${_ver#*.}; _min=${_rest%%.*}
        if [ -n "$_maj" ] && [ -n "$_min" ]; then
            if [ "$_maj" -gt 7 ] 2>/dev/null || { [ "$_maj" -eq 7 ] 2>/dev/null && [ "$_min" -ge 71 ] 2>/dev/null; }; then
                _RETRY="--retry 2 --retry-all-errors --retry-delay 3"
            elif [ "$_maj" -eq 7 ] 2>/dev/null && [ "$_min" -ge 68 ] 2>/dev/null; then
                _RETRY="--retry 2 --retry-delay 3"
            fi
        fi
    fi
    _code=$(curl -sS --max-time 25 --connect-timeout 10 \
        $_RETRY \
        -H @"$_hdr" \
        -H 'Content-Type: application/json' \
        --data-binary @"$_tmpbody" \
        -D "$_tmpbody.hdr" \
        -o "$_tmpbody.out" \
        -w '%{http_code}' \
        "$RR_RECEIVER_URL" 2>/dev/null) || _code=""
    rm -f "$_hdr" "$_tmpbody"
    _POST_CODE="$_code"
    _POST_CT=""
    _POST_BODY=""
    if [ -f "$_tmpbody.hdr" ]; then
        # content type of the FINAL response only (a redirect chain can carry
        # several header blocks; take the last one).
        _POST_CT=$(tr -d '\r' < "$_tmpbody.hdr" 2>/dev/null | awk 'BEGIN{IGNORECASE=1} /^content-type:/{ct=$0} END{sub(/^[^:]*:[ ]*/,"",ct); print ct}')
        rm -f "$_tmpbody.hdr"
    fi
    if [ -f "$_tmpbody.out" ]; then
        _out=$(cat "$_tmpbody.out" 2>/dev/null)
        _POST_BODY="$_out"
        rm -f "$_tmpbody.out"
    fi
    # RR-008: ONLY an expected 2xx is a success. A 3xx is a FAILURE, not a
    # delivered request: the old `2*|3*)` case treated a redirect (a CF Access
    # login wall, a moved webhook, an http->https bounce) as a successful
    # delivery, so the box recorded an ACK it never landed and the incident
    # stayed open forever with no visible error. 401/403 (unauthorized),
    # 429 (throttled), 5xx and a dropped transport are all failures too, and
    # the CALLER decides what to do with the class via _post_class.
    case "$_code" in
        2*)
            printf '%s' "$_out"
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# ---------------------------------------------------------------------------
# _post_class -> prints the response class for the LAST _post call.
#
# The classes are the RR-008 vocabulary:
#   ok_json      an expected 2xx carrying a JSON body
#   ok_nonjson   an expected 2xx whose body is NOT JSON (HTML error page,
#                gateway interstitial, empty body) -- a FAILURE for the ack
#                path, because no receipt can be read out of it
#   redirect     3xx (never followed: a login wall must not look like a send)
#   unauthorized 401/403
#   throttled    429
#   server       5xx
#   transport    curl failed (dropped response / DNS / TLS / timeout)
#   none         no code at all (never attempted)
#
# Pure: reads only the _POST_* globals. Never prints a body, a header or a
# token -- only the class name.
# ---------------------------------------------------------------------------
_post_class() {
    case "${_POST_CODE:-}" in
        "")        printf 'transport' ;;
        2*)
            # strip LEADING whitespace before sniffing the first byte, so a
            # pretty-printed JSON body is still recognised as JSON.
            _pc_body="${_POST_BODY:-}"
            _pc_body="${_pc_body#"${_pc_body%%[![:space:]]*}"}"
            case "$_pc_body" in
                \{*) printf 'ok_json' ;;
                *)   printf 'ok_nonjson' ;;
            esac
            ;;
        3*)        printf 'redirect' ;;
        401|403)   printf 'unauthorized' ;;
        429)       printf 'throttled' ;;
        5*)        printf 'server' ;;
        *)         printf 'transport' ;;
    esac
    return 0
}

# ---------------------------------------------------------------------------
# _json_get <json> <dotted-path> -> prints the value at the path, or nothing.
#
# Nested read for the RR-008 structured receipt (receipt.operation_id etc.).
# jq when present, python3 otherwise; neither => empty (a caller treats empty
# as "no receipt", which is a FAILURE, never a guessed confirmation).
# ---------------------------------------------------------------------------
_json_get() {
    _jg_json="$1"
    _jg_path="$2"
    [ -n "$_jg_json" ] || return 0
    if command -v jq >/dev/null 2>&1; then
        printf '%s' "$_jg_json" | jq -r --arg p "$_jg_path" '
          ($p | split(".")) as $k
          | getpath($k)
          | if . == null then "" elif type == "string" then . else tostring end' 2>/dev/null
        return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        printf '%s' "$_jg_json" | JG_PATH="$_jg_path" python3 -c '
import json, os, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
o = d
for k in os.environ.get("JG_PATH", "").split("."):
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
else:
    sys.exit(0)
' 2>/dev/null
        return 0
    fi
    return 0
}

# ---------------------------------------------------------------------------
# _json_field <json> <key>  -> prints the string value of <key>, or nothing.
# Pure: no token, no payload. Uses jq when present, python3 otherwise. If neither
# parser exists the field is empty (callers treat empty as "nothing", and the
# whole poll degrades to a silent no-op — never a guessed-success).
# ---------------------------------------------------------------------------
_json_field() {
    _jf_json="$1"
    _jf_key="$2"
    if [ -z "$_jf_json" ]; then
        return 0
    fi
    if command -v jq >/dev/null 2>&1; then
        printf '%s' "$_jf_json" | jq -r --arg k "$_jf_key" '.[$k] // empty' 2>/dev/null
        return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        printf '%s' "$_jf_json" | JF_KEY="$_jf_key" python3 -c '
import json, os, sys
try:
    d = json.load(sys.stdin)
    k = os.environ.get("JF_KEY", "")
    v = d.get(k)
    if v is None:
        sys.exit(0)
    if isinstance(v, bool):
        print("true" if v else "false")
    elif isinstance(v, (int, float)):
        print(v)
    else:
        print(str(v))
except Exception:
    sys.exit(0)
' 2>/dev/null
        return 0
    fi
    return 0
}

# ---------------------------------------------------------------------------
# _resolve_default_agent — prints the id of the box's default agent, or nothing.
# Pure: no token, no payload. Parses `openclaw agents list --json`, taking the
# FIRST entry whose "isDefault" is true. jq preferred, python3 fallback; neither
# => empty (caller treats empty as "resolution failed", never a guessed success).
# ---------------------------------------------------------------------------
_resolve_default_agent() {
    # RR-027: this child reads no rescue credential; still scrubbed so NO
    # child of this poll can ever inherit a rescue alias, whatever the
    # caller's environment exported.
    _rda_out=$(rescue_env_scrub "$_OC_BIN" agents list --json 2>/dev/null) || return 0
    [ -n "$_rda_out" ] || return 0
    if command -v jq >/dev/null 2>&1; then
        printf '%s' "$_rda_out" | jq -r '
          ([.[] | select(.isDefault == true)] | first | .id)
          // empty' 2>/dev/null
        return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        printf '%s' "$_rda_out" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if not isinstance(d, list):
    sys.exit(0)
for entry in d:
    if isinstance(entry, dict) and entry.get("isDefault") is True:
        aid = entry.get("id")
        if aid:
            print(aid)
        break
' 2>/dev/null
        return 0
    fi
    return 0
}

# ---------------------------------------------------------------------------
# _parse_claim <response> — extracts the instruction fields from a claim
# response into global variables. Returns 0 if it is a valid `instruction`
# response with the fields required to act, 1 otherwise.
# ---------------------------------------------------------------------------
_parse_claim() {
    _pc_resp="$1"
    _pc_status=$(_json_field "$_pc_resp" "status")
    case "$_pc_status" in
        instruction)
            INSTRUCTION_ID=$(_json_field "$_pc_resp" "instruction_id")
            IDEMPOTENCY_KEY=$(_json_field "$_pc_resp" "idempotency_key")
            TICKET_ID=$(_json_field "$_pc_resp" "ticket_id")
            AGENT_ID=$(_json_field "$_pc_resp" "agent_id")
            SESSION_KEY=$(_json_field "$_pc_resp" "session_key")
            PAYLOAD_B64=$(_json_field "$_pc_resp" "payload_b64")
            MODE=$(_json_field "$_pc_resp" "mode")
            # RR-004 additive fields (v1.4.0): echo-only; empty on old servers.
            ATTEMPT_ID=$(_json_field "$_pc_resp" "attempt_id")
            ATTEMPT_GENERATION=$(_json_field "$_pc_resp" "attempt_generation")
            LEASE_EXPIRES_AT=$(_json_field "$_pc_resp" "lease_expires_at")
            [ -n "$IDEMPOTENCY_KEY" ] || return 1
            return 0
            ;;
        empty|disabled|unauthorized|*)
            return 1
            ;;
    esac
}

# ---------------------------------------------------------------------------
# _extract_reply <agent-json-stdout>  -> prints the extracted assistant text.
#
# Mirrors rescue-receiver.mjs extractReply(): the reply is looked up at
# result.payloads[0].text, then result.meta.finalAssistantVisibleText, then
# result.run.meta.finalAssistantVisibleText, then meta.finalAssistantVisibleText.
# jq preferred, python3 fallback; neither => empty (caller acks failed_no_parser).
# The JSON is normalised to start at the first `{` first (the live receiver does
# the same), so a log line prepended to stdout does not break parsing.
# ---------------------------------------------------------------------------
_extract_reply() {
    _er_json="$1"
    if [ -z "$_er_json" ]; then
        return 0
    fi
    # Normalise: drop everything before the first '{'.
    case "$_er_json" in
        \{*) ;;
        *)
            _rest="${_er_json#*\{}"
            if [ "$_rest" != "$_er_json" ]; then
                _er_json="{$_rest"
            fi
            ;;
    esac
    if command -v jq >/dev/null 2>&1; then
        printf '%s' "$_er_json" | jq -r '
          (
            .result.payloads[0].text
            // .result.meta.finalAssistantVisibleText
            // .result.run.meta.finalAssistantVisibleText
            // .meta.finalAssistantVisibleText
            // ""
          ) | .' 2>/dev/null
        return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        printf '%s' "$_er_json" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
def dig(o, *ks):
    for k in ks:
        if not isinstance(o, dict):
            return None
        o = o.get(k)
    return o
r = dig(d, "result")
p = dig(r, "payloads")
t = p[0].get("text") if isinstance(p, list) and p and isinstance(p[0], dict) else None
if not t: t = dig(r, "meta", "finalAssistantVisibleText")
if not t: t = dig(r, "run", "meta", "finalAssistantVisibleText")
if not t: t = dig(d, "meta", "finalAssistantVisibleText")
if t is None: t = ""
print(t)
' 2>/dev/null
        return 0
    fi
    return 0
}

# ===========================================================================
# RR-008 DELIVERY / ACK STATE MACHINE  (owned section: _post/_ack/_write_done/
# _reack_cached + the journal and pending-ACK stores those four use)
#
# The defect this closes: the box POSTed an ack, IGNORED the transport result
# (`_ack_out=$(_post ...) || true`), treated a redirect as success, and kept a
# done-file that stored only the verdict -- so a re-delivered instruction was
# re-acked from a cache that had LOST the reply evidence, and nothing ever
# noticed that the server never recorded the delivery.
#
# The contract now, in order:
#   1. a DURABLE ATTEMPT JOURNAL is written (fsync'd, atomic rename) BEFORE
#      any effect. A journal write that fails STOPS NEW EFFECTS -- the agent
#      turn does not run, and the poll exits without claiming anything else.
#   2. the complete outcome AND proof (verdict, exit, chars, reason, elapsed,
#      redacted reply excerpt, structured v3 result when one exists, operation
#      identity) is saved atomically as ACK_PENDING before the ack is posted.
#   3. the ack is resent VERBATIM until a MATCHING STRUCTURED RECEIPT arrives:
#      the server must answer an expected 2xx carrying JSON whose
#      receipt.operation_id equals ours, whose receipt.attempt_id equals ours
#      (when we have one) and which names a state_revision. 302 / 200-HTML /
#      401 / 429 / 5xx / dropped response are all FAILURES; each is classified
#      and logged, the identical body is retained for the next fire, and the
#      incident stays open -- never a guessed confirmation.
#   4. the journal is the reconciliation ledger. An ack that was sent but not
#      confirmed is an UNCERTAIN EXTERNAL EFFECT: it is retained and retried
#      with a UNIQUE operation id, which the server treats as an idempotent
#      receipt, so a retry can never create a second side effect. Retention is
#      bounded: confirmed entries are GC'd after 14 days; unconfirmed entries
#      are NEVER silently dropped -- after 30 days they are moved to
#      reconcile/ and logged as an owned reconciliation obligation.
#   5. permissions are private: 0700 dirs, 0600 files. No token, no payload,
#      no reply text is ever written to the journal or the log.
# ===========================================================================
_JOURNAL="$_STATE/journal"
_PENDING="$_STATE/ack-pending"
_RECONCILE="$_STATE/reconcile"
mkdir -p "$_JOURNAL" "$_PENDING" 2>/dev/null || exit 0
chmod 700 "$_JOURNAL" "$_PENDING" 2>/dev/null || true

# _now_iso -> UTC timestamp for journal records.
_now_iso() {
    date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || printf 'unknown'
}

# _sha <string> -> hex sha256 of stdin (shasum, then sha256sum, then empty).
_sha() {
    _sh_out=$(printf '%s' "$1" | shasum -a 256 2>/dev/null | cut -d' ' -f1) \
        || _sh_out=$(printf '%s' "$1" | sha256sum 2>/dev/null | cut -d' ' -f1) \
        || _sh_out=""
    printf '%s' "$_sh_out"
}

# _op_id_for <idempotency_key> <attempt_id> <generation> -> operation id.
#
# DETERMINISTIC PER ATTEMPT, which is what makes replay safe: the same claim
# re-delivered to the same box yields the SAME operation id, so the server's
# "repeated operation id = idempotent receipt" rule applies and a retry can
# never produce a second side effect. A NEW attempt (new attempt_id or lease
# generation) yields a NEW id, so genuinely new work is never deduped onto old
# work's receipt.
_op_id_for() {
    _oi_key="$1"
    _oi_attempt="$2"
    _oi_gen="$3"
    printf 'op_%s' "$(_sha "rr-delivery|${_oi_key}|${_oi_attempt}|${_oi_gen}")"
}

# _journal_put <op_id> <phase> [extra-json-fields]
# Atomic (tmp + fsync + rename) and 0600. Prints nothing. Returns nonzero on
# ANY failure -- the caller treats that as STOP NEW EFFECTS.
_journal_put() {
    _jp_op="$1"
    _jp_phase="$2"
    _jp_extra="${3:-}"
    [ -n "$_jp_op" ] || return 1
    _jp_tmp=""
    _jp_tmp=$(mktemp "$_JOURNAL/.tmp-XXXXXX" 2>/dev/null) || return 1
    chmod 600 "$_jp_tmp" 2>/dev/null
    [ -n "$_jp_extra" ] || _jp_extra="{}"
    printf '{"operation_id":"%s","phase":"%s","instruction_id":"%s","idempotency_key":"%s","attempt_id":"%s","attempt_generation":"%s","box_slug":"%s","receiver_version":"%s","updated_at":"%s","extra":%s}\n' \
        "$(_json_str "$_jp_op")" "$(_json_str "$_jp_phase")" \
        "$(_json_str "$INSTRUCTION_ID")" "$(_json_str "$IDEMPOTENCY_KEY")" \
        "$(_json_str "${ATTEMPT_ID:-}")" "$(_json_str "${ATTEMPT_GENERATION:-}")" \
        "$(_json_str "$RR_BOX_SLUG")" "$(_json_str "$RECEIVER_VERSION")" \
        "$(_now_iso)" "$_jp_extra" > "$_jp_tmp" 2>/dev/null || { rm -f "$_jp_tmp"; return 1; }
    if command -v python3 >/dev/null 2>&1; then
        python3 -c 'import os,sys
f=open(sys.argv[1],"rb"); os.fsync(f.fileno()); f.close()' "$_jp_tmp" 2>/dev/null || { rm -f "$_jp_tmp"; return 1; }
    else
        sync 2>/dev/null
    fi
    mv "$_jp_tmp" "$_JOURNAL/$_jp_op" 2>/dev/null || { rm -f "$_jp_tmp"; return 1; }
    return 0
}

# _journal_phase <op_id> -> prints the recorded phase (empty when no journal).
_journal_phase() {
    [ -n "${1:-}" ] || return 0
    [ -f "$_JOURNAL/$1" ] || return 0
    _json_field "$(cat "$_JOURNAL/$1" 2>/dev/null)" "phase"
}

# _pending_put <op_id> <exact-ack-body>
# The body is stored BYTE-FOR-BYTE. Every resend is the same bytes -- a resend
# that rebuilt the body could drift (a different elapsed_s, a lost excerpt) and
# would no longer be a replay of the same operation.
_pending_put() {
    _pp_op="$1"
    _pp_body="$2"
    [ -n "$_pp_op" ] || return 1
    _pp_tmp=""
    _pp_tmp=$(mktemp "$_PENDING/.tmp-XXXXXX" 2>/dev/null) || return 1
    chmod 600 "$_pp_tmp" 2>/dev/null
    printf '%s' "$_pp_body" > "$_pp_tmp" 2>/dev/null || { rm -f "$_pp_tmp"; return 1; }
    if command -v python3 >/dev/null 2>&1; then
        python3 -c 'import os,sys
f=open(sys.argv[1],"rb"); os.fsync(f.fileno()); f.close()' "$_pp_tmp" 2>/dev/null || { rm -f "$_pp_tmp"; return 1; }
    else
        sync 2>/dev/null
    fi
    mv "$_pp_tmp" "$_PENDING/$_pp_op" 2>/dev/null || { rm -f "$_pp_tmp"; return 1; }
    return 0
}

# _receipt_match <response-body> <op_id> <attempt_id>
# Prints "match" when the body carries an ACCEPTABLE structured receipt for
# THIS operation and attempt; otherwise prints the reason it did not.
# An expected 2xx alone is NEVER a confirmation (RR-008).
_receipt_match() {
    _rm_body="$1"
    _rm_op="$2"
    _rm_attempt="$3"
    [ -n "$_rm_body" ] || { printf 'empty_body'; return 0; }
    _rm_op_seen=$(_json_get "$_rm_body" "receipt.operation_id")
    _rm_attempt_seen=$(_json_get "$_rm_body" "receipt.attempt_id")
    _rm_rev=$(_json_get "$_rm_body" "receipt.state_revision")
    [ -n "$_rm_op_seen" ]    || { printf 'no_receipt_operation_id'; return 0; }
    [ -n "$_rm_rev" ]        || { printf 'no_receipt_state_revision'; return 0; }
    if [ -n "$_rm_op" ] && [ "$_rm_op_seen" != "$_rm_op" ]; then
        printf 'receipt_operation_mismatch'; return 0
    fi
    if [ -n "$_rm_attempt" ] && [ -n "$_rm_attempt_seen" ] && [ "$_rm_attempt_seen" != "$_rm_attempt" ]; then
        printf 'receipt_attempt_mismatch'; return 0
    fi
    printf 'match'
    return 0
}

# _ack_send <exact-body> <op_id> <attempt_id> <label>
# ONE delivery attempt of an ack body. Prints the verdict token:
#   confirmed:<state_revision>  the server receipt matched -> settle
#   <class>:<reason>            a failure -> retain and resend later
# Never prints a body, a header or a token.
_ack_send() {
    _as_body="$1"
    _as_op="$2"
    _as_attempt="$3"
    _as_label="$4"
    # RR-008 FIX (subshell class loss): _post publishes the response class in
    # the _POST_* SHELL GLOBALS, so it has to run in THIS shell. The earlier
    # `_as_out=$(_post ...)` ran it in a $( ) SUBSHELL: the assignments died
    # with the subshell, the parent's _post_class then read globals nobody had
    # set, and EVERY ack came back class=transport -- so _receipt_match was
    # never reached and no ack could ever confirm. Capture the body in a file
    # instead of a subshell; the globals then survive for _post_class.
    _POST_CODE=""; _POST_CT=""; _POST_BODY=""
    _as_out=""
    if [ -n "${_TMP:-}" ] && [ -w "$_TMP" ]; then
        _post "$_as_body" > "$_TMP/rr-poll-ack.out" 2>/dev/null || true
        if [ -f "$_TMP/rr-poll-ack.out" ]; then
            _as_out=$(cat "$_TMP/rr-poll-ack.out" 2>/dev/null)
            rm -f "$_TMP/rr-poll-ack.out" 2>/dev/null
        fi
    fi
    # no writable tmp => _post cannot run at all => the invalidation above
    # leaves _POST_CODE empty, which _post_class reports as 'transport'.
    _as_class=$( _post_class 2>/dev/null || true )
    [ -n "$_as_class" ] || _as_class="transport"
    [ -n "$_as_class" ] || _as_class="transport"
    if [ "$_as_class" != "ok_json" ]; then
        printf '%s:%s' "$_as_class" "non_json_or_http"
        return 0
    fi
    _as_reason=$(_receipt_match "$_as_out" "$_as_op" "$_as_attempt")
    if [ "$_as_reason" = "match" ]; then
        printf 'confirmed:%s' "$(_json_get "$_as_out" "receipt.state_revision")"
    else
        printf 'ok_json:%s' "$_as_reason"
    fi
    return 0
}

# _resend_pending — retry every unconfirmed ack with its ORIGINAL bytes.
# Bounded per fire (a box must not stall the poll on a dead endpoint): the
# oldest entries are retried first, at most RR_MAX_RESENDS (default 5).
# A confirmed entry is settled and removed from the pending store; an
# unconfirmed one stays for the next fire. This is the reconciliation that
# makes an uncertain external effect safe to retry.
_resend_pending() {
    [ -d "$_PENDING" ] || return 0
    _rp_max="${RR_MAX_RESENDS:-5}"
    case "$_rp_max" in ''|*[!0-9]*) _rp_max=5 ;; esac
    [ "$_rp_max" -gt 0 ] 2>/dev/null || return 0
    _rp_n=0
    for _rp_f in $(ls -1 "$_PENDING" 2>/dev/null | grep -v '^\.tmp-' | head -20); do
        [ "$_rp_n" -lt "$_rp_max" ] 2>/dev/null || break
        _rp_path="$_PENDING/$_rp_f"
        [ -f "$_rp_path" ] || continue
        _rp_body=$(cat "$_rp_path" 2>/dev/null) || continue
        [ -n "$_rp_body" ] || continue
        _rp_op=$(_json_field "$_rp_body" "operation_id")
        _rp_attempt=$(_json_field "$_rp_body" "attempt_id")
        _rp_verdict=$(_ack_send "$_rp_body" "$_rp_op" "$_rp_attempt" "resend")
        _rp_n=$(( _rp_n + 1 ))
        case "$_rp_verdict" in
            confirmed:*)
                _journal_put "$_rp_op" "ack_confirmed" "{\"resend\":true,\"state_revision\":\"$(_json_str "${_rp_verdict#confirmed:}")\"}" 2>/dev/null || true
                rm -f "$_rp_path" 2>/dev/null || true
                _log "ack-resend CONFIRMED op=$_rp_op rev=${_rp_verdict#confirmed:}"
                ;;
            *)
                _journal_put "$_rp_op" "ack_pending" "{\"resend\":true,\"last_class\":\"$(_json_str "$_rp_verdict")\"}" 2>/dev/null || true
                _log "ack-resend UNCONFIRMED op=$_rp_op class=$_rp_verdict (retained, identical body)"
                ;;
        esac
    done
    return 0
}

# _gc_journal — bounded post-reconciliation retention.
#   * confirmed entries older than 14 days: removed (work is done, both stores
#     converged, nothing left to reconcile).
#   * PENDING (unconfirmed) entries are NEVER silently deleted. Older than 30
#     days they are moved to reconcile/ with a log line, where they stay as an
#     owned obligation until a receipt arrives or an operator clears them.
_gc_journal() {
    if [ -d "$_JOURNAL" ]; then
        find "$_JOURNAL" -type f -name 'op_*' -mtime +14 2>/dev/null | while IFS= read -r _gj_f; do
            _gj_phase=$(_json_field "$(cat "$_gj_f" 2>/dev/null)" "phase")
            case "$_gj_phase" in
                ack_confirmed) rm -f "$_gj_f" 2>/dev/null || true ;;
            esac
        done
    fi
    if [ -d "$_PENDING" ]; then
        _gj_old=$(find "$_PENDING" -type f -name 'op_*' -mtime +30 2>/dev/null | head -20)
        if [ -n "$_gj_old" ]; then
            mkdir -p "$_RECONCILE" 2>/dev/null || true
            chmod 700 "$_RECONCILE" 2>/dev/null || true
            printf '%s\n' "$_gj_old" | while IFS= read -r _gj_p; do
                [ -f "$_gj_p" ] || continue
                if mv "$_gj_p" "$_RECONCILE/" 2>/dev/null; then
                    _log "ack-reconcile OBLIGATION is now owned by operator: unconfirmed ack older than 30d moved to reconcile/ ($(basename "$_gj_p"))"
                fi
            done
        fi
    fi
    return 0
}

# ---------------------------------------------------------------------------
# _ack <verdict> <exit_code> <reply_chars> <fail_reason> [elapsed_s] [excerpt]
#
# Builds the ack body and posts it. Always uses _post (token via header file).
# The ack carries the box slug, the opaque echo of instruction/idempotency keys,
# and the verdict per §6.2/§6.3 (elapsed_s is only meaningful for live agent
# turns; it defaults to 0 for the no-agent-turn paths — dry_run, empty payload).
# A delivered ack has fail_reason null. A failed ack whose reason is not one of
# the canonical enum values is NOT sent (a failed ack without an honest reason
# is itself a lie). A failed ack that cannot be POSTed (network) is simply
# silent — the lease lapses and the instruction is re-handed, which the
# done-file dedups against.
#
# v1.3.0: an optional 6th argument carries a bounded excerpt of the reply text.
# It rides in the `reply_excerpt` field on every ack that has text to show
# (delivered or failed), so the RR-07 operator ledger can read what the agent
# actually said instead of only its length.
# ---------------------------------------------------------------------------
_ack() {
    _ack_verdict="$1"
    _ack_exit="$2"
    _ack_chars="$3"
    _ack_reason="$4"
    _ack_elapsed="${5:-0}"
    _ack_excerpt="${6:-}"
    case "$_ack_elapsed" in
        ''|*[!0-9]*) _ack_elapsed=0 ;;
    esac

    # fail-closed reason validation.
    case "$_ack_reason" in
        failed_nonzero_exit|failed_empty_reply|failed_timeout|failed_no_parser|dry_run|escalation_language)
            _fr_json="\"$(_json_str "$_ack_reason")\""
            ;;
        "")
            if [ "$_ack_verdict" = "delivered" ]; then
                _fr_json="null"
            else
                return 0   # failed ack with no honest reason: stay silent
            fi
            ;;
        *)
            return 0       # unknown reason: stay silent (fail closed)
            ;;
    esac

    _excerpt_json=""
    if [ -n "$_ack_excerpt" ]; then
        _excerpt_json=",\"reply_excerpt\":\"$(_json_str "$_ack_excerpt")\""
    fi

    # RR-004 additive fields (v1.4.0): the attempt identity is echoed back so
    # the server can fence the ack against the CURRENT owner (generation +
    # token) and reject stale/expired/replaced acknowledgments. Fields are
    # omitted-not-nulled when empty so pre-RR-004 servers see no change.
    # ${VAR:-} everywhere: with `set -u` an unset variable (pre-claim cached
    # re-ack, or a failed parse) must yield EMPTY, never abort the script.
    _attempt_json=""
    if [ -n "${ATTEMPT_ID:-}" ]; then
        _attempt_json=",\"attempt_id\":\"$(_json_str "${ATTEMPT_ID:-}")\""
    fi
    if [ -n "${ATTEMPT_GENERATION:-}" ]; then
        _attempt_json="${_attempt_json},\"attempt_generation\":${ATTEMPT_GENERATION:-}"
    fi
    if [ -n "${LEASE_EXPIRES_AT:-}" ]; then
        _attempt_json="${_attempt_json},\"lease_expires_at\":\"$(_json_str "${LEASE_EXPIRES_AT:-}")\""
    fi

    # RR-008: unique per-attempt operation id. Deterministic on
    # (idempotency_key, attempt_id, generation), so a re-delivery of the SAME
    # attempt produces the SAME id and the server records an idempotent
    # receipt instead of a second effect; a NEW attempt produces a new id.
    _op_id=$(_op_id_for "$IDEMPOTENCY_KEY" "${ATTEMPT_ID:-}" "${ATTEMPT_GENERATION:-}")

    # The v3 structured result, when the caller supplied one. It is carried
    # VERBATIM as a JSON object (never stringified into a quoted blob) so the
    # server's validator sees the real shape. Absent => the field is omitted
    # entirely and the ack is a transport receipt only.
    _result_json=""
    if [ -n "${RR_RESULT_JSON:-}" ] && [ -f "${RR_RESULT_JSON:-}" ]; then
        _rj=$(cat "$RR_RESULT_JSON" 2>/dev/null)
        case "$_rj" in
            \{*) _result_json=",\"result\":$_rj" ;;
        esac
    fi

    _ack_body="{\"action\":\"ack\",\"box_slug\":\"$(_json_str "$RR_BOX_SLUG")\",\"instruction_id\":\"$(_json_str "$INSTRUCTION_ID")\",\"idempotency_key\":\"$(_json_str "$IDEMPOTENCY_KEY")\",\"operation_id\":\"$(_json_str "$_op_id")\",\"verdict\":\"$(_json_str "$_ack_verdict")\",\"exit_code\":$_ack_exit,\"reply_chars\":$_ack_chars,\"fail_reason\":$_fr_json,\"elapsed_s\":$_ack_elapsed${_excerpt_json}${_attempt_json},\"runtime_id\":\"$(_json_str "$RR_BOX_SLUG")\",\"receiver_version\":\"$(_json_str "$RECEIVER_VERSION")\"${_result_json}}"

    # DURABLE JOURNAL BEFORE THE EFFECT (RR-008 step 1). If this write fails
    # there is no record that the ack was ever attempted, so we do NOT send --
    # journal failure stops new effects. The work item itself is already
    # durably in done/ (written before this call), so nothing is lost: the
    # ticket stays open and the next fire retries the whole ack.
    if ! _journal_put "$_op_id" "ack_attempt" "{\"verdict\":\"$(_json_str "$_ack_verdict")\",\"reply_chars\":$_ack_chars}"; then
        _log "ACK HELD: journal write failed op=$_op_id (no effect taken; work preserved in done/)"
        return 1
    fi

    # ACK_PENDING BEFORE THE EFFECT (RR-008 step 2): the COMPLETE outcome and
    # proof are stored atomically, byte-for-byte as sent, so a crash at any
    # point after this leaves an identical body to resend -- never a
    # reconstructed one that could drift.
    if ! _pending_put "$_op_id" "$_ack_body"; then
        _log "ACK HELD: ack-pending write failed op=$_op_id (no effect taken; work preserved in done/)"
        return 1
    fi

    _ack_verdict_token=$(_ack_send "$_ack_body" "$_op_id" "${ATTEMPT_ID:-}" "ack")
    case "$_ack_verdict_token" in
        confirmed:*)
            _journal_put "$_op_id" "ack_confirmed" "{\"state_revision\":\"$(_json_str "${_ack_verdict_token#confirmed:}")\"}" 2>/dev/null || true
            rm -f "$_PENDING/$_op_id" 2>/dev/null || true
            _log "ack verdict=$_ack_verdict exit=$_ack_exit chars=$_ack_chars reason=$_ack_reason elapsed=${_ack_elapsed}s receipt=CONFIRMED rev=${_ack_verdict_token#confirmed:} op=$_op_id"
            ;;
        *)
            # NOT confirmed. The identical body is retained for the next fire;
            # the incident stays open and the failure class is visible.
            _journal_put "$_op_id" "ack_pending" "{\"last_class\":\"$(_json_str "$_ack_verdict_token")\"}" 2>/dev/null || true
            _log "ack verdict=$_ack_verdict exit=$_ack_exit chars=$_ack_chars reason=$_ack_reason elapsed=${_ack_elapsed}s receipt=UNCONFIRMED class=$_ack_verdict_token op=$_op_id (identical body retained for resend)"
            ;;
    esac
    return 0
}

# ---------------------------------------------------------------------------
# _write_done <verdict> <exit> <chars> <reason> [elapsed_s] [excerpt]
#
# Writes the done/<idempotency_key> cache file. Written IMMEDIATELY after the
# agent turn (before the ack) so a crash between execution and ack still leaves
# the dedup in place: a re-delivered instruction (lease lapse) is re-acked from
# this file and never runs a second agent turn.
#
# RR-008: the record now carries the COMPLETE outcome and proof, not just the
# verdict. The old file stored {verdict, exit_code, reply_chars, fail_reason,
# elapsed_s} and nothing else, so re-acking from cache LOST the reply excerpt
# and the operation identity — the cached re-ack went out with no evidence and
# with no operation id the server could dedup on. The excerpt, the attempt
# identity and the operation id are all persisted here now, so a cached re-ack
# is byte-for-byte the same evidence a live ack would have carried.
# ---------------------------------------------------------------------------
_write_done() {
    _wd_verdict="$1"
    _wd_exit="$2"
    _wd_chars="$3"
    _wd_reason="$4"
    _wd_elapsed="${5:-0}"
    _wd_excerpt="${6:-}"
    case "$_wd_elapsed" in
        ''|*[!0-9]*) _wd_elapsed=0 ;;
    esac
    case "$_wd_reason" in
        "") _fr_json="null" ;;
        *)  _fr_json="\"$(_json_str "$_wd_reason")\"" ;;
    esac
    _wd_excerpt_json=""
    if [ -n "$_wd_excerpt" ]; then
        _wd_excerpt_json=",\"reply_excerpt\":\"$(_json_str "$_wd_excerpt")\""
    fi
    _wd_op_json=""
    _wd_op=$(_op_id_for "$IDEMPOTENCY_KEY" "${ATTEMPT_ID:-}" "${ATTEMPT_GENERATION:-}")
    [ -n "$_wd_op" ] && _wd_op_json=",\"operation_id\":\"$(_json_str "$_wd_op")\""
    _wd_attempt_json=""
    [ -n "${ATTEMPT_ID:-}" ] && _wd_attempt_json=",\"attempt_id\":\"$(_json_str "${ATTEMPT_ID:-}")\""
    [ -n "${ATTEMPT_GENERATION:-}" ] && _wd_attempt_json="${_wd_attempt_json},\"attempt_generation\":${ATTEMPT_GENERATION:-}"
    _wd_ids_json=""
    [ -n "${INSTRUCTION_ID:-}" ] && _wd_ids_json=",\"instruction_id\":\"$(_json_str "${INSTRUCTION_ID:-}")\""
    [ -n "${TICKET_ID:-}" ] && _wd_ids_json="${_wd_ids_json},\"ticket_id\":\"$(_json_str "${TICKET_ID:-}")\""
    # RR-021/RR-025: collision-resistant done-file identity. The old
    # tr-normalization ALIASED distinct keys (a/b and a_b both -> key-a_b),
    # so one ticket's cached verdict could satisfy another's dedup check.
    # The exact key is hashed instead; no lossy normalization anywhere.
    _safe=$(printf '%s' "$IDEMPOTENCY_KEY" | shasum -a 256 2>/dev/null | cut -d' ' -f1) \
        || _safe=$(printf '%s' "$IDEMPOTENCY_KEY" | sha256sum 2>/dev/null | cut -d' ' -f1) \
        || _safe=$(printf '%s' "$IDEMPOTENCY_KEY" | tr -c 'A-Za-z0-9._-' '_')
    _tmp=$(mktemp "$_DONE/.tmp-XXXXXX" 2>/dev/null) || return 1
    chmod 600 "$_tmp" 2>/dev/null
    printf '{"verdict":"%s","exit_code":%s,"reply_chars":%s,"fail_reason":%s,"elapsed_s":%s%s%s%s%s,"written_at":"%s"}\n' \
        "$_wd_verdict" "$_wd_exit" "$_wd_chars" "$_fr_json" "$_wd_elapsed" \
        "$_wd_excerpt_json" "$_wd_op_json" "$_wd_attempt_json" "$_wd_ids_json" "$(_now_iso)" > "$_tmp" 2>/dev/null || { rm -f "$_tmp"; return 1; }
    # RR-021: the claimed instruction's record must be DURABLY on disk before
    # the poll proceeds — a crash or a lost ACK must never lose the work item.
    # fsync the record (python3 is present on every supported box; `sync` is
    # the coarse fallback; failure to sync is treated as a write failure).
    if command -v python3 >/dev/null 2>&1; then
        python3 -c 'import os,sys
f=open(sys.argv[1],"rb"); os.fsync(f.fileno()); f.close()' "$_tmp" 2>/dev/null || { rm -f "$_tmp"; return 1; }
    else
        sync 2>/dev/null
    fi
    mv "$_tmp" "$_DONE/$_safe" 2>/dev/null || { rm -f "$_tmp"; return 1; }
    return 0
}

# ---------------------------------------------------------------------------
# _reack_cached <key> — a done-file exists for this idempotency_key: the
# instruction was already acted on. Re-ack the cached verdict without running
# the agent turn (one agent turn, ever).
#
# RR-008: the re-ack carries the SAME EVIDENCE as the original. Before this,
# the done-file held only the verdict, so a cached re-ack went out with NO
# reply excerpt and NO operation id — the server could neither show what the
# agent said nor dedup the replay, and the replay looked like a brand new
# delivery. The excerpt, the attempt identity and the operation id are all
# read back here and re-posted verbatim. When the cached record predates this
# change (no operation_id in the file) one is derived deterministically from
# the same inputs, so an old box's replay is still idempotent on the server.
# Returns 0 when the cached ack was CONFIRMED, 1 when it was not (the poll
# then exits without running the agent turn either way — one agent turn, ever).
# ---------------------------------------------------------------------------
_reack_cached() {
    # same collision-resistant identity as _write_done (must agree exactly)
    _rc_safe=$(printf '%s' "$1" | shasum -a 256 2>/dev/null | cut -d' ' -f1) \
        || _rc_safe=$(printf '%s' "$1" | sha256sum 2>/dev/null | cut -d' ' -f1) \
        || _rc_safe=$(printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_')
    [ -f "$_DONE/$_rc_safe" ] || return 1
    _rc_body=$(cat "$_DONE/$_rc_safe" 2>/dev/null)
    [ -n "$_rc_body" ] || return 1
    _rc_verdict=$(_json_field "$_rc_body" "verdict")
    _rc_exit=$(_json_field "$_rc_body" "exit_code")
    _rc_chars=$(_json_field "$_rc_body" "reply_chars")
    _rc_reason=$(_json_field "$_rc_body" "fail_reason")
    _rc_elapsed=$(_json_field "$_rc_body" "elapsed_s")
    # RR-008: the proof the old cache dropped.
    _rc_excerpt=$(_json_field "$_rc_body" "reply_excerpt")
    _rc_op=$(_json_field "$_rc_body" "operation_id")
    _rc_attempt=$(_json_field "$_rc_body" "attempt_id")
    _rc_gen=$(_json_field "$_rc_body" "attempt_generation")
    [ -n "$_rc_verdict" ] || return 1
    case "$_rc_exit" in
        ''|null) _rc_exit=1 ;;
    esac
    case "$_rc_chars" in
        ''|null) _rc_chars=0 ;;
    esac
    case "$_rc_elapsed" in
        ''|null|*[!0-9]*) _rc_elapsed=0 ;;
    esac
    case "$_rc_reason" in
        ''|null) _rc_reason="" ;;
    esac
    # Re-establish the attempt identity the ack echo reads, preferring the
    # CACHED values (the attempt that actually did the work) over whatever the
    # server re-sent on this claim. Falling back to the current claim keeps a
    # pre-RR-008 cache record ackable.
    [ -n "$_rc_attempt" ] || _rc_attempt="${ATTEMPT_ID:-}"
    [ -n "$_rc_gen" ]     || _rc_gen="${ATTEMPT_GENERATION:-}"
    ATTEMPT_ID="$_rc_attempt"
    ATTEMPT_GENERATION="$_rc_gen"
    if [ -z "$_rc_op" ]; then
        _rc_op=$(_op_id_for "$1" "$_rc_attempt" "$_rc_gen")
        _log "re-ack cache predates operation ids; derived op=$_rc_op key=$_rc_safe"
    fi
    _ack "$_rc_verdict" "$_rc_exit" "$_rc_chars" "$_rc_reason" "$_rc_elapsed" "$_rc_excerpt"
    _rc_rc=$?
    _log "re-acked cached verdict key=$_rc_safe verdict=$_rc_verdict excerpt_chars=${#_rc_excerpt} op=$_rc_op rc=$_rc_rc"
    return "$_rc_rc"
}

# ---------------------------------------------------------------------------
# _gc_done — self-GC the done/ ledger: files older than 14 days are removed.
# A file's mtime is its write time; a long-idle box accumulates nothing.
# ---------------------------------------------------------------------------
_gc_done() {
    if [ -d "$_DONE" ]; then
        find "$_DONE" -type f -mtime +14 -exec rm -f {} \; 2>/dev/null || true
    fi
}

# ---------------------------------------------------------------------------
# _gc_tmp — self-GC stray _post() temp files (header/body/response). The
# normal path removes each one within the same call; this only catches
# leftovers from a poll that was SIGKILLed mid-transport (the same class of
# event T8 covers). A curl round-trip never legitimately takes hours, so
# anything older than 1 hour here is dead. Cheap insurance against a slow
# leak of token-bearing files across 38 boxes x every-2-minutes x forever.
# ---------------------------------------------------------------------------
_gc_tmp() {
    if [ -d "$_TMP" ]; then
        find "$_TMP" -type f -mmin +60 -exec rm -f {} \; 2>/dev/null || true
    fi
}

# ---------------------------------------------------------------------------
# MAIN FLOW
# ---------------------------------------------------------------------------
# GC first, unconditionally: every fire reaches this line regardless of which
# branch it takes below (dry-run / empty-payload / re-ack-cached / live), so
# this is the one place both ledgers are guaranteed to get swept on a cadence
# — not just after a completed live delivery.
_gc_done
_gc_tmp
# RR-008: bounded post-reconciliation retention runs on the same cadence as
# the other sweepers, from the one place every fire reaches.
_gc_journal

_sleep_jitter

# ---------------------------------------------------------------------------
# RR-008 STEP 0: RESEND ANY UNCONFIRMED ACK FIRST, BEFORE ANY NEW EFFECT.
#
# An ack that was POSTed but never confirmed is an UNCERTAIN EXTERNAL EFFECT:
# the server may or may not have recorded it. The identical bytes are retained
# in ack-pending/ and re-sent here, each time under the SAME operation id, so
# the server's repeated-operation-id rule makes the retry an idempotent receipt
# rather than a second delivery. Claiming NEW work happens only after this,
# so a box with an unsettled ack cannot race ahead and accumulate more.
# ---------------------------------------------------------------------------
_resend_pending

# Build the claim body once. No token appears here — the token rides in a header
# file (see _post).
_claim_body="{\"action\":\"claim\",\"box_slug\":\"$(_json_str "$RR_BOX_SLUG")\",\"receiver_version\":\"$(_json_str "$RECEIVER_VERSION")\",\"capacity\":1}"

# Claim at most one instruction. Transport failure / empty / disabled / 401 => a
# clean silent no-op (next fire retries).
CLAIM_RESP=$(_post "$_claim_body") || exit 0
[ -n "$CLAIM_RESP" ] || exit 0

_parse_claim "$CLAIM_RESP" || exit 0

# If mode is dry_run: ack failed/dry_run (transport proof must never look like
# delivery), write the done-file, and exit. No agent turn ever runs.
if [ "$MODE" = "dry_run" ]; then
    # RR-008 ORDER: durable journal + done record BEFORE the ack (the effect).
    # A dry run must never look like a delivery -- it acks failed/dry_run and
    # the record is written whether or not the ack lands.
    _write_done "failed" 1 0 "dry_run" "" ""
    _ack "failed" 1 0 "dry_run"
    _log "dry_run ack instruction=$INSTRUCTION_ID rc=$? (journal+done durable before effect)"
    exit 0
fi

# Live: if a done-file already exists for this key, re-ack the cached verdict and
# stop — the same instruction seen twice must not act twice.
if _reack_cached "$IDEMPOTENCY_KEY"; then
    exit 0
fi

# Decode the payload and run the local delivery command. The message is
# base64-transported (never shell-quoted, never executed as shell).
MSG=$(printf '%s' "$PAYLOAD_B64" | base64 -d 2>/dev/null || true)
if [ -z "$MSG" ]; then
    _write_done "failed" 1 0 "failed_empty_reply" "" ""
    _ack "failed" 1 0 "failed_empty_reply"
    _log "empty payload (decode produced nothing) instruction=$INSTRUCTION_ID"
    exit 0
fi

# Default agent id and session key when the gateway did not supply them.
[ -n "$AGENT_ID" ] || AGENT_ID="main"
[ -n "$SESSION_KEY" ] || SESSION_KEY="agent:main:rescue-reply:${INSTRUCTION_ID}"

_start_ts=$(date +%s 2>/dev/null || echo 0)

# RR-027 child-env scrub (spec: "explicitly remove rescue credential aliases
# from child env while allowing necessary authorized model/tool credentials").
# Whatever the caller's environment exported (a synthetic RR_BOX_TOKEN in an
# upstream env file is the CONFIRMED leak path), the child agent turn cannot
# see a rescue alias. The necessary authorized inference/tool credentials the
# box itself carries (GEMINI_API_KEY, KIE_API_KEY, ...) are untouched — only
# rescue credential NAMES are removed. The poll's own token is additionally
# protected at the source: this script now PARSES the store (no sourcing, no
# export), so an exported RR_BOX_TOKEN here is only possible if an UPSTREAM
# env exported it before this script even started — and the scrub removes
# that too.
# The message payload rides as an argument (unchanged from the proven
# delivery command); the bearer token never appears in this argv at all.
# RESCUE_ENV_EXTRA_UNSET adds the box's own escalation secret to the scrub
# list for THIS child (an agent turn seeded from a ticket is not the box's
# escalation path; the box's own AGENTS.md escalation flow keeps its
# credential because it does not run through this poll).
# ---------------------------------------------------------------------------
# RR-008: DURABLE ATTEMPT JOURNAL BEFORE THE EFFECT.
#
# Written BEFORE the agent turn — the effect this box can never take back. If
# the journal cannot be written the turn is NOT started: an effect with no
# durable record is exactly the class RR-008 exists to remove (the box would
# have delivered coaching with no local trace that it ever happened, and a
# crash would leave the server and the box disagreeing with no way to
# reconcile). Journal failure therefore STOPS NEW EFFECTS and the claimed
# instruction is left un-acked, so the lease lapses and the work returns.
# ---------------------------------------------------------------------------
_op_id=$(_op_id_for "$IDEMPOTENCY_KEY" "${ATTEMPT_ID:-}" "${ATTEMPT_GENERATION:-}")
if ! _journal_put "$_op_id" "effect_started" "{\"instruction_id\":\"$(_json_str "$INSTRUCTION_ID")\"}"; then
    _log "JOURNAL FAILED op=$_op_id instruction=$INSTRUCTION_ID — agent turn NOT started (journal failure stops new effects)"
    exit 0
fi

RESCUE_ENV_EXTRA_UNSET="RESCUE_RANGERS_WEBHOOK_SECRET RESCUE_RANGERS_HELP_CHAT_ID"
_AGENT_ERR_PATH="$_TMP/rr-poll-agent-err.$$"
AGENT_OUT=$(rescue_env_scrub "$_OC_BIN" agent --agent "$AGENT_ID" --session-key "$SESSION_KEY" --message "$MSG" --json --timeout 600 2>"$_AGENT_ERR_PATH")
AGENT_RC=$?
_AGENT_ERR=""
if [ -f "$_AGENT_ERR_PATH" ]; then
    _AGENT_ERR=$(cat "$_AGENT_ERR_PATH" 2>/dev/null)
    rm -f "$_AGENT_ERR_PATH"
fi
# RR-027 redaction: the agent's stderr is a structured-rejection /
# exception surface that could echo an environment-shaped credential value
# under a Node stack trace (an env-var dump in an exception message). Only
# the failure CLASS is kept for the fallback gate; the bytes are never
# logged (the token discipline: no credential value in any log, ever).
case "$_AGENT_ERR" in
    *"Unknown agent id"*) : ;;
    *) _AGENT_ERR="" ;;
esac

# ---------------------------------------------------------------------------
# Agent-id fallback (v1.1.0): some boxes have no agent named "main", so the
# CLI fails instantly with 'Unknown agent id'. Resolve the box's default agent
# id once and retry the turn ONCE. The verdict still comes only from the
# retry's own exit code and reply — the honesty contract is untouched.
# ---------------------------------------------------------------------------
_rc_first=$AGENT_RC
case "$_AGENT_ERR" in
    *"Unknown agent id"*)
        # Gate on a genuinely FAILED first turn. A turn that exited 0 already
        # delivered to the client; re-running it would double-deliver and could
        # overwrite that real success with the retry's failure. "One agent turn,
        # ever" holds only if this guard is here. The retry runs through the
        # SAME rescue_env_scrub wrapper (RR-027: no rescue alias reaches any
        # child), and its stderr is discarded at the source (2>/dev/null).
        if [ "$_rc_first" -ne 0 ]; then
            _RESOLVED_AGENT=$(_resolve_default_agent)
            if [ -n "$_RESOLVED_AGENT" ] && [ "$_RESOLVED_AGENT" != "$AGENT_ID" ]; then
                _log "agent-id-fallback from=$AGENT_ID to=$_RESOLVED_AGENT rc_before=$_rc_first"
                AGENT_OUT=$(rescue_env_scrub "$_OC_BIN" agent --agent "$_RESOLVED_AGENT" --session-key "$SESSION_KEY" --message "$MSG" --json --timeout 600 2>/dev/null)
                AGENT_RC=$?
                AGENT_ID="$_RESOLVED_AGENT"
            fi
        fi
        ;;
esac

_end_ts=$(date +%s 2>/dev/null || echo 0)
_elapsed=$(( _end_ts - _start_ts ))
[ "$_elapsed" -lt 0 ] 2>/dev/null && _elapsed=0

REPLY_TEXT=$(_extract_reply "$AGENT_OUT")
# Trim leading/trailing whitespace so a whitespace-only reply is honestly empty.
REPLY_TRIM=$(printf '%s' "$REPLY_TEXT" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
REPLY_CHARS=$(printf '%s' "$REPLY_TRIM" | wc -c 2>/dev/null | tr -dc '0-9')
[ -n "$REPLY_CHARS" ] || REPLY_CHARS=0

# ---------------------------------------------------------------------------
# VERDICT RULE (§6.3) — ambiguous ⇒ NOT fixed.
#   delivered  <=>  AGENT_RC == 0 AND REPLY_CHARS > 0 AND the reply is not an
#                   escalation/deferral text (v1.3.0).
#   else failed, with the most specific honest fail_reason.
# An exit-0 turn whose text says the job was not done is NOT a delivery: it
# acks failed/escalation_language so RR-07 pages a human instead of closing
# the ticket as coached-and-done.
# ---------------------------------------------------------------------------
REPLY_EXCERPT=""
if [ "$REPLY_CHARS" -gt 0 ] 2>/dev/null; then
    REPLY_EXCERPT=$(_bounded_excerpt "$REPLY_TRIM")
fi

VERDICT="failed"
FAIL_REASON="failed_nonzero_exit"
if [ "$AGENT_RC" -eq 0 ] && [ "$REPLY_CHARS" -gt 0 ] 2>/dev/null && _is_escalation "$REPLY_TRIM"; then
    VERDICT="failed"
    FAIL_REASON="escalation_language"
elif [ "$AGENT_RC" -eq 0 ] && [ "$REPLY_CHARS" -gt 0 ] 2>/dev/null; then
    VERDICT="delivered"
    FAIL_REASON=""
elif [ "$AGENT_RC" -eq 0 ]; then
    FAIL_REASON="failed_empty_reply"
else
    FAIL_REASON="failed_nonzero_exit"
fi

# ---------------------------------------------------------------------------
# RR-008 STEP 3: DURABLE ATTEMPT JOURNAL BEFORE THE EFFECT.
#
# The journal row for this operation is written (atomic + fsync'd) BEFORE the
# done record and before the ack. A crash after the agent turn therefore still
# leaves a journal row that says the attempt happened, so the next fire can
# reconcile instead of re-running the turn blind. If the journal cannot be
# written, NO new effect is taken on this fire: the done record is skipped and
# the ack is held (a work item with no journal row would be an unowned effect).
# ---------------------------------------------------------------------------
# (_op_id was derived before the effect and is unchanged here.)
if ! _journal_put "$_op_id" "effect_executed" "{\"verdict\":\"$(_json_str "$VERDICT")\",\"exit_code\":$AGENT_RC,\"reply_chars\":$REPLY_CHARS}"; then
    _log "JOURNAL FAILED op=$_op_id instruction=$INSTRUCTION_ID — effect executed but NOT recorded; ack HELD (reconciliation required before rerunning)"
    exit 0
fi

# Persist the COMPLETE outcome and proof to the done-file (crash-safe dedup +
# the evidence a cached re-ack must replay), then send the ack. The write is
# checked: a done record that did not land means the dedup this box relies on
# does not exist, so no ack is sent that would let the server settle a
# delivery the box cannot replay.
if ! _write_done "$VERDICT" "$AGENT_RC" "$REPLY_CHARS" "$FAIL_REASON" "$_elapsed" "$REPLY_EXCERPT"; then
    _log "DONE-WRITE FAILED op=$_op_id instruction=$INSTRUCTION_ID — ack HELD (no dedup proof; journal retained)"
    exit 0
fi
_ack "$VERDICT" "$AGENT_RC" "$REPLY_CHARS" "$FAIL_REASON" "$_elapsed" "$REPLY_EXCERPT"

_log "delivery instruction=$INSTRUCTION_ID verdict=$VERDICT exit=$AGENT_RC chars=$REPLY_CHARS elapsed=${_elapsed}s reason=$FAIL_REASON op=$_op_id"

exit 0
