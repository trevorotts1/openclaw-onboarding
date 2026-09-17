#!/usr/bin/env bash
# 65-rescue-receiver/rr-intake-auth-check.sh — RR escalation INTAKE auth self-check.
# ============================================================================
# THE DEFECT THIS EXISTS FOR
#
# A box whose RESCUE_RANGERS_WEBHOOK_SECRET went stale after an operator-side
# rotation 401s or 403s on every escalation, SILENTLY, for as long as nobody
# happens to escalate and check. Nothing on the box probed the escalation INTAKE:
#
#   * rr-readiness.sh probes only the RETURN leg (RR_RECEIVER_URL with
#     RR_BOX_TOKEN). A perfect VERIFIED readiness report says nothing about
#     whether this box can still GET INTO the queue.
#   * scripts/lib/rescue_admission.py classifies a 403 as an auth refusal
#     (is_auth_refusal), but that only happens DURING a real escalation, and
#     nothing schedules a probe or writes a durable flag afterwards.
#
# So the only signal was a human noticing an escalation never landed.
#
# WHAT THIS DOES
#
# Once a day it sends the escalation template's own documented self-check: an
# `__AUTHTEST__` escalate body that the intake answers with
# {"accepted":true,"ticketId":null,"status":"test_suppressed"}. That proves the
# channel end to end with ZERO ticket residue
# (scripts/rescue-escalation-section.md.tpl, SELF-VERIFY block).
#
# CLASSES
#   OK                 2xx carrying test_suppressed. The channel works.
#   RR_SECRET_STALE    401/403, or a body saying unauthorized. THIS BOX's
#                      credential is not accepted. Operator-owned repair.
#   RR_OLD_RELAY_URL   2xx carrying missing_message. The URL points at the OLD
#                      relay, so the secret may be fine and the endpoint is not.
#   RR_SECRET_MISSING  no credential resolvable from env OR the secrets store.
#                      Nothing was sent: there is nothing to test.
#   UNDETERMINED       transport error, timeout, 429, 5xx, a redirect, or a 2xx
#                      whose body this script does not recognise.
#
# UNDETERMINED IS NEVER REPORTED AS STALE. A network blip is not evidence about
# a credential, and an UNDETERMINED result never overwrites a flag that records
# a PROVEN class. Only an OK clears the flag, because only an OK is proof.
#
# THE CREDENTIAL
#   * Rides in a 0600 `curl -H @file` header file inside a 0700 private dir,
#     exactly as rr-readiness.sh's probe does. Never in argv, never in the body,
#     never in a log, never in the flag file.
#   * The flag file records a CLASS and an HTTP code. It never records a value.
#
# EXIT CODES
#   0   OK
#   3   RR_SECRET_STALE
#   4   RR_OLD_RELAY_URL
#   5   RR_SECRET_MISSING
#   75  UNDETERMINED (EX_TEMPFAIL): nothing was established, nothing is claimed
#   78  ENVIRONMENT: no openclaw root, no curl, or the shared parser is missing
#
# OVERRIDES (fixtures use these): RR_ROOT / --root, OC_CONFIG_ROOT,
# RESCUE_RANGERS_WEBHOOK_URL, RESCUE_RANGERS_WEBHOOK_SECRET,
# RR_INTAKE_AUTH_TIMEOUT.
# ============================================================================
set -uo pipefail

MODE="human"
ROOT_OVERRIDE=""
FLAG_NAME="rr-intake-auth.flag"
REMEDY="operator must re-provision RESCUE_RANGERS_WEBHOOK_SECRET"
DEFAULT_URL="https://main.blackceoautomations.com/webhook/rr-v2-intake"

while [ $# -gt 0 ]; do
  case "$1" in
    --json) MODE="json" ;;
    --root) shift; ROOT_OVERRIDE="${1:-}" ;;
    --help|-h) sed -n '2,60p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "rr-intake-auth-check.sh: unknown argument: $1" >&2; exit 78 ;;
  esac
  shift
done

say() { [ "$MODE" = "human" ] && printf '%s\n' "$*"; return 0; }
now_iso() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

# ---- Resolve the openclaw root ----------------------------------------------
if [ -n "${BASH_SOURCE:-}" ]; then _SELF_SRC="${BASH_SOURCE[0]}"; else _SELF_SRC="$0"; fi
SELF_DIR="$(cd "$(dirname "$_SELF_SRC")" 2>/dev/null && pwd)"

RR_ROOT="${ROOT_OVERRIDE:-${RR_ROOT:-}}"
if [ -z "$RR_ROOT" ]; then
  if   [ -n "${OC_CONFIG_ROOT:-}" ]; then RR_ROOT="$OC_CONFIG_ROOT"
  elif [ -d /data/.openclaw ];       then RR_ROOT="/data/.openclaw"
  elif [ -d "$HOME/.openclaw" ];     then RR_ROOT="$HOME/.openclaw"
  fi
fi
if [ -z "$RR_ROOT" ] || [ ! -d "$RR_ROOT" ]; then
  echo "rr-intake-auth-check: ENVIRONMENT no openclaw root resolved (tried --root, OC_CONFIG_ROOT, /data/.openclaw, \$HOME/.openclaw)" >&2
  exit 78
fi
SECRETS="$RR_ROOT/secrets/.env"
STATE_DIR="$RR_ROOT/state"
FLAG="$STATE_DIR/$FLAG_NAME"

# ---- The shared parser (never sources the secrets store) ---------------------
PARSER=""
for _cand in "$RR_ROOT/skills/shared-utils/rescue-env.sh" \
             "$SELF_DIR/../shared-utils/rescue-env.sh"; do
  [ -n "$_cand" ] && [ -f "$_cand" ] && { PARSER="$_cand"; break; }
done
if [ -z "$PARSER" ]; then
  echo "rr-intake-auth-check: ENVIRONMENT shared-utils/rescue-env.sh not found (looked beside the skills tree and beside this script); cannot read the store without sourcing it, so nothing is claimed" >&2
  exit 78
fi
# shellcheck disable=SC1090
. "$PARSER"

CURL_BIN=""
command -v curl >/dev/null 2>&1 && CURL_BIN="curl"
if [ -z "$CURL_BIN" ]; then
  echo "rr-intake-auth-check: ENVIRONMENT curl not on PATH; no request was attempted and no verdict is claimed" >&2
  exit 78
fi

# ---- Flag helpers ------------------------------------------------------------
# flag_class: prints the class currently on file, or nothing.
flag_class() {
  [ -r "$FLAG" ] || return 1
  sed -n 's/.*"class"[[:space:]]*:[[:space:]]*"\([A-Z_]*\)".*/\1/p' "$FLAG" 2>/dev/null | head -1
}

# write_flag <class> <http>. Records a CLASS and an HTTP code. NEVER a value.
write_flag() {
  _wf_class="$1"; _wf_http="$2"
  ( umask 077; mkdir -p "$STATE_DIR" 2>/dev/null ) || {
    echo "rr-intake-auth-check: state dir not writable ($STATE_DIR); the flag was NOT persisted" >&2
    return 1
  }
  _wf_tmp="$FLAG.tmp.$$"
  {
    printf '{"class":"%s","http":%s,"ts":"%s","remedy":"%s"}\n' \
      "$_wf_class" "${_wf_http:-0}" "$(now_iso)" "$REMEDY"
  } > "$_wf_tmp" 2>/dev/null || { rm -f "$_wf_tmp"; return 1; }
  chmod 600 "$_wf_tmp" 2>/dev/null || true
  mv -f "$_wf_tmp" "$FLAG" 2>/dev/null || { rm -f "$_wf_tmp"; return 1; }
  return 0
}

clear_flag() { [ -e "$FLAG" ] && rm -f "$FLAG" 2>/dev/null; return 0; }

# settle <class> <http> <detail> <exit-code>
# OK clears the flag. A PROVEN non-OK class writes it. UNDETERMINED writes only
# when there is no proven class already on file: an unproven result must never
# erase a proven one.
settle() {
  _st_class="$1"; _st_http="$2"; _st_detail="$3"; _st_rc="$4"
  case "$_st_class" in
    OK)
      clear_flag
      say "rr-intake-auth-check: OK http=${_st_http:-none} $_st_detail"
      ;;
    UNDETERMINED)
      _st_prev="$(flag_class || true)"
      case "${_st_prev:-}" in
        RR_SECRET_STALE|RR_OLD_RELAY_URL|RR_SECRET_MISSING)
          say "rr-intake-auth-check: UNDETERMINED http=${_st_http:-none} $_st_detail"
          say "rr-intake-auth-check: the existing $_st_prev flag is LEFT IN PLACE; an unproven result never overwrites a proven one"
          ;;
        *)
          write_flag "UNDETERMINED" "${_st_http:-0}" || true
          say "rr-intake-auth-check: UNDETERMINED http=${_st_http:-none} $_st_detail"
          ;;
      esac
      ;;
    *)
      write_flag "$_st_class" "${_st_http:-0}" || true
      say "rr-intake-auth-check: $_st_class http=${_st_http:-none} $_st_detail"
      say "rr-intake-auth-check: remedy: $REMEDY"
      ;;
  esac
  if [ "$MODE" = "json" ]; then
    printf '{"class":"%s","http":%s,"ts":"%s","flag":"%s","remedy":"%s"}\n' \
      "$_st_class" "${_st_http:-0}" "$(now_iso)" "$FLAG" "$REMEDY"
  fi
  exit "$_st_rc"
}

# ---- Resolve the intake URL and the credential -------------------------------
# Both can live in the runtime env OR ONLY in the secrets store. The escalation
# section is explicit that a box must read BOTH before claiming either is absent.
URL="${RESCUE_RANGERS_WEBHOOK_URL:-}"
URL_SRC="env"
if [ -z "$URL" ]; then
  URL="$(rescue_env_get "$SECRETS" RESCUE_RANGERS_WEBHOOK_URL 2>/dev/null)" || URL=""
  URL_SRC="secrets-store"
fi
if [ -z "$URL" ]; then
  URL="$DEFAULT_URL"
  URL_SRC="shipped-default"
fi

SECRET="${RESCUE_RANGERS_WEBHOOK_SECRET:-}"
SECRET_SRC="env"
if [ -z "$SECRET" ]; then
  SECRET="$(rescue_env_get "$SECRETS" RESCUE_RANGERS_WEBHOOK_SECRET 2>/dev/null)" || SECRET=""
  SECRET_SRC="secrets-store"
fi

say "rr-intake-auth-check: url_source=$URL_SRC root=$RR_ROOT"

if [ -z "$SECRET" ]; then
  # Absence proven the same way presence is: both sources named, neither had it.
  settle "RR_SECRET_MISSING" 0 \
    "no RESCUE_RANGERS_WEBHOOK_SECRET in the runtime env AND none in $SECRETS; nothing was sent because there is nothing to test" 5
fi

# ---- Stage the 0600 header file and POST the __AUTHTEST__ body ----------------
_pt="$(rescue_env_private_tmp "$STATE_DIR" 2>/dev/null)" || _pt=""
if [ -z "$_pt" ] || [ ! -d "$_pt" ]; then
  ( umask 077; mkdir -p "$STATE_DIR/tmp" 2>/dev/null ) || true
  _pt="$STATE_DIR/tmp"
fi
if [ ! -d "$_pt" ]; then
  settle "UNDETERMINED" 0 "no private temp dir under $STATE_DIR, so the credential could not be staged off the command line; NOTHING was sent" 75
fi
chmod 700 "$_pt" 2>/dev/null || true

_hdr="$(rescue_env_header_file "$_pt" "X-Rescue-Secret" "$SECRET" 2>/dev/null)" || _hdr=""
if [ -z "$_hdr" ] || [ ! -f "$_hdr" ]; then
  settle "UNDETERMINED" 0 "the 0600 credential header file could not be staged; NOTHING was sent (the secret is never put in argv)" 75
fi
# From here on the secret only exists inside $_hdr. Drop it from this shell.
SECRET=""
unset SECRET

_work="$(mktemp -d "${TMPDIR:-/tmp}/rr-intake-auth.XXXXXX" 2>/dev/null)" || _work=""
if [ -z "$_work" ]; then
  rm -f "$_hdr"
  settle "UNDETERMINED" 0 "no writable temp dir for the request body; NOTHING was sent" 75
fi
chmod 700 "$_work" 2>/dev/null || true
_body="$_work/body.json"
_out="$_work/out"
# The template's own self-check body, verbatim. clientName __AUTHTEST__ is what
# makes the intake answer test_suppressed instead of minting a ticket.
printf '%s\n' '{"action":"escalate","clientName":"__AUTHTEST__","problem":"channel self-check"}' > "$_body"
chmod 600 "$_body" 2>/dev/null || true

_timeout="${RR_INTAKE_AUTH_TIMEOUT:-60}"
case "$_timeout" in
  ''|*[!0-9]*) _timeout=60 ;;
  *) [ "$_timeout" -ge 5 ] && [ "$_timeout" -le 900 ] || _timeout=60 ;;
esac

# argv-safe: the URL, every flag and every path is ONE argv element, and the
# credential is not among them.
_code="$("$CURL_BIN" -sS --max-time "$_timeout" --connect-timeout 10 \
    -H @"$_hdr" \
    -H 'Content-Type: application/json' \
    --data-binary @"$_body" \
    -o "$_out" \
    -w '%{http_code}' \
    "$URL" 2>/dev/null)" || _code=""
rm -f "$_hdr"
_bodytext="$(cat "$_out" 2>/dev/null)"
rm -rf "$_work"

# ---- Classify ----------------------------------------------------------------
case "$_code" in
  ""|000)
    settle "UNDETERMINED" 0 \
      "the request did not complete (transport error or timeout after ${_timeout}s). A failed connection says nothing about the credential." 75
    ;;
  401|403)
    settle "RR_SECRET_STALE" "$_code" \
      "the intake refused this box's credential (HTTP $_code). Per the escalation self-check contract, that is a wrong secret, not a rejected incident." 3
    ;;
  429)
    settle "UNDETERMINED" "$_code" "the intake throttled this probe (HTTP 429); nothing about the credential was established" 75
    ;;
  2*)
    case "$_bodytext" in
      *test_suppressed*)
        settle "OK" "$_code" "the intake answered test_suppressed: the escalation channel works end to end with zero ticket residue" 0
        ;;
      *missing_message*)
        settle "RR_OLD_RELAY_URL" "$_code" \
          "the intake answered missing_message, which is the OLD relay's shape. The URL is wrong, so the credential was never the thing under test (url_source=$URL_SRC)." 4
        ;;
      *unauthorized*|*forbidden*|*invalid_credential*|*not_enrolled*)
        settle "RR_SECRET_STALE" "$_code" \
          "a 2xx whose body reports an auth refusal; this box's credential is not accepted" 3
        ;;
      *)
        settle "UNDETERMINED" "$_code" \
          "a 2xx this check does not recognise. It is NOT reported as stale: an unrecognised answer is not a verdict about the credential." 75
        ;;
    esac
    ;;
  3*)
    settle "UNDETERMINED" "$_code" \
      "the intake answered with a redirect (HTTP $_code). A redirect wall is not proof of a wrong credential or a wrong URL." 75
    ;;
  5*)
    settle "UNDETERMINED" "$_code" \
      "the intake returned a server error (HTTP $_code). That is the RECEIVER's problem, and it says nothing about this box's credential." 75
    ;;
  *)
    settle "UNDETERMINED" "$_code" \
      "unexpected HTTP $_code; no verdict about the credential is claimed" 75
    ;;
esac
