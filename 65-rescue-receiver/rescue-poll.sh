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
# v1.4.0 (RR-W2-CORE, RR-004 pairing): ADDITIVE claim/ack fields. The server
# (RR-07 / the Fleet Ops transactional claim service) now issues an
# attempt/owner token, a lease generation and an explicit lease expiry on every
# claim. The receiver echoes them verbatim on the ack — it does NOT interpret,
# gate on, or require them yet. Strict mode arrives only AFTER the server
# contract is confirmed additive-compatible (SPEC RR-004 shared rollout
# contract: public receiver changes pair with additive server support FIRST;
# old servers that omit the fields keep working because the fields simply echo
# as empty strings).
RECEIVER_VERSION="1.5.0"

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
# appears in argv either. On success (HTTP 2xx/3xx) prints the response body to
# stdout and returns 0. On any transport failure returns non-zero with NO stdout.
# ---------------------------------------------------------------------------
_post() {
    _req_body="$1"
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
        -o "$_tmpbody.out" \
        -w '%{http_code}' \
        "$RR_RECEIVER_URL" 2>/dev/null) || _code=""
    rm -f "$_hdr" "$_tmpbody"
    if [ -f "$_tmpbody.out" ]; then
        _out=$(cat "$_tmpbody.out" 2>/dev/null)
        rm -f "$_tmpbody.out"
    fi
    case "$_code" in
        2*|3*)
            printf '%s' "$_out"
            return 0
            ;;
        *)
            return 1
            ;;
    esac
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

    _ack_body="{\"action\":\"ack\",\"box_slug\":\"$(_json_str "$RR_BOX_SLUG")\",\"instruction_id\":\"$(_json_str "$INSTRUCTION_ID")\",\"idempotency_key\":\"$(_json_str "$IDEMPOTENCY_KEY")\",\"verdict\":\"$(_json_str "$_ack_verdict")\",\"exit_code\":$_ack_exit,\"reply_chars\":$_ack_chars,\"fail_reason\":$_fr_json,\"elapsed_s\":$_ack_elapsed${_excerpt_json}${_attempt_json},\"receiver_version\":\"$(_json_str "$RECEIVER_VERSION")\"}"

    _ack_out=$(_post "$_ack_body") || true
    _log "ack verdict=$_ack_verdict exit=$_ack_exit chars=$_ack_chars reason=$_ack_reason elapsed=${_ack_elapsed}s"
}

# ---------------------------------------------------------------------------
# _write_done <verdict> <exit> <chars> <reason> [elapsed_s]
#
# Writes the done/<idempotency_key> cache file. Written IMMEDIATELY after the
# agent turn (before the ack) so a crash between execution and ack still leaves
# the dedup in place: a re-delivered instruction (lease lapse) is re-acked from
# this file and never runs a second agent turn.
# ---------------------------------------------------------------------------
_write_done() {
    _wd_verdict="$1"
    _wd_exit="$2"
    _wd_chars="$3"
    _wd_reason="$4"
    _wd_elapsed="${5:-0}"
    case "$_wd_elapsed" in
        ''|*[!0-9]*) _wd_elapsed=0 ;;
    esac
    case "$_wd_reason" in
        "") _fr_json="null" ;;
        *)  _fr_json="\"$(_json_str "$_wd_reason")\"" ;;
    esac
    # RR-021/RR-025: collision-resistant done-file identity. The old
    # tr-normalization ALIASED distinct keys (a/b and a_b both -> key-a_b),
    # so one ticket's cached verdict could satisfy another's dedup check.
    # The exact key is hashed instead; no lossy normalization anywhere.
    _safe=$(printf '%s' "$IDEMPOTENCY_KEY" | shasum -a 256 2>/dev/null | cut -d' ' -f1) \
        || _safe=$(printf '%s' "$IDEMPOTENCY_KEY" | sha256sum 2>/dev/null | cut -d' ' -f1) \
        || _safe=$(printf '%s' "$IDEMPOTENCY_KEY" | tr -c 'A-Za-z0-9._-' '_')
    _tmp=$(mktemp "$_DONE/.tmp-XXXXXX" 2>/dev/null) || return 1
    printf '{"verdict":"%s","exit_code":%s,"reply_chars":%s,"fail_reason":%s,"elapsed_s":%s}\n' \
        "$_wd_verdict" "$_wd_exit" "$_wd_chars" "$_fr_json" "$_wd_elapsed" > "$_tmp" 2>/dev/null || { rm -f "$_tmp"; return 1; }
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
    _ack "$_rc_verdict" "$_rc_exit" "$_rc_chars" "$_rc_reason" "$_rc_elapsed"
    _log "re-acked cached verdict key=$_rc_safe verdict=$_rc_verdict"
    return 0
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

_sleep_jitter

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
    _ack "failed" 1 0 "dry_run"
    _write_done "failed" 1 0 "dry_run"
    _log "dry_run ack instruction=$INSTRUCTION_ID"
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
    _ack "failed" 1 0 "failed_empty_reply"
    _write_done "failed" 1 0 "failed_empty_reply"
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

# Persist the verdict to the done-file FIRST (crash-safe dedup), then ack.
_write_done "$VERDICT" "$AGENT_RC" "$REPLY_CHARS" "$FAIL_REASON" "$_elapsed"
_ack "$VERDICT" "$AGENT_RC" "$REPLY_CHARS" "$FAIL_REASON" "$_elapsed" "$REPLY_EXCERPT"

_log "delivery instruction=$INSTRUCTION_ID verdict=$VERDICT exit=$AGENT_RC chars=$REPLY_CHARS elapsed=${_elapsed}s reason=$FAIL_REASON"

exit 0
