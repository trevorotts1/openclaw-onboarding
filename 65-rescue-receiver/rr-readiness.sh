#!/usr/bin/env bash
# 65-rescue-receiver/rr-readiness.sh — RR-028 readiness reporter + safe probe.
# ============================================================================
# The operator/tooling surface for the RR-028 state machine. Reports EXACTLY
# one of UNENROLLED / ENROLLED_PENDING / SCHEDULED / VERIFIED with an explicit
# reason, and can (a) reconcile the cron with readback and (b) perform the
# SAFE TEST CLAIM that is the only path to VERIFIED.
#
#   rr-readiness.sh                # report (READ-ONLY)
#   rr-readiness.sh --json         # same, one JSON object
#   rr-readiness.sh --reconcile    # reconcile the cron (add/edit/dedupe) then report
#   rr-readiness.sh --probe        # safe test claim -> receipt, then report
#
# WHAT "SAFE TEST CLAIM" MEANS HERE (RR-028 required behaviour 7):
#   * It is a CLAIM-shaped request with capacity 0 and mode dry_run, carrying a
#     probe marker — the receiver is asked for a structured answer, not work.
#   * It NEVER starts an agent turn and NEVER sends an ack: if the receiver
#     hands back an instruction anyway, the probe REFUSES it, records the
#     refusal, writes NO receipt, and the box stays SCHEDULED (an unproven
#     receiver is never reported ready).
#   * The credential rides in a 0600 `curl -H @file` header inside a 0700
#     private temp dir — never in argv, never in a log, never in the body.
#   * Only a 2xx with a STRUCTURED no-work body ("empty"/"no_work") produces a
#     receipt (RR-008: a bare 2xx is never a confirmation).
#
# INSTALLER vs READY: `wire.sh` exiting 0 means FILES INSTALLED. It never means
# receiver-ready; that is this tool's VERIFIED state, which requires the receipt.
#
# EXIT CODE CONTRACT (read this before scripting against this tool):
#   0  VERIFIED        scheduled AND a matching safe-test-claim receipt exists
#   1  SCHEDULED       scheduled by readback, no verified receipt yet
#   2  ENROLLED_PENDING enrolled, scheduling not proven (reason names why)
#   3  UNENROLLED      not enrolled, or the enrollment store is unreadable
#   78 ENVIRONMENT     no openclaw root resolved (nothing downstream is valid)
# Never treat a nonzero exit as "broken" without reading the printed reason.
#
# OVERRIDES (all optional, fixtures use them): RR_ROOT / --root, OC_CONFIG_ROOT,
# OC_STATE_DB, OC_PLATFORM, OC_TARGET_MODE, OC_TARGET_ID, OC_SERVICE_LABEL,
# OC_CONTAINER, OC_ENV_DESCRIPTOR, RR_RECEIVER_PROBE_TIMEOUT.
# ============================================================================
set -u

MODE="human"
DO_PROBE=0
DO_RECONCILE=0
ROOT_OVERRIDE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --json) MODE="json" ;;
    --probe) DO_PROBE=1 ;;
    --reconcile) DO_RECONCILE=1 ;;
    --root) shift; ROOT_OVERRIDE="${1:-}" ;;
    --help|-h)
      sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "rr-readiness.sh: unknown argument: $1" >&2; exit 78 ;;
  esac
  shift
done

# ---------------------------------------------------------------------------
# Locate this script's own tree (repo-side or installed) and the openclaw root.
# ---------------------------------------------------------------------------
if [ -n "${BASH_SOURCE:-}" ]; then _SELF_SRC="${BASH_SOURCE[0]}"; else _SELF_SRC="$0"; fi
SELF_DIR="$(cd "$(dirname "$_SELF_SRC")" 2>/dev/null && pwd)"
REPO_HINT="$(cd "$SELF_DIR/.." 2>/dev/null && pwd)"

_find_up() {  # _find_up <relative-path-from-a-tree-root>
  _fu_dir="$REPO_HINT"; _fu_i=0
  while [ "$_fu_i" -lt 5 ]; do
    [ -n "$_fu_dir" ] && [ -f "$_fu_dir/$1" ] && { printf '%s' "$_fu_dir/$1"; return 0; }
    _fu_dir="$(cd "$_fu_dir/.." 2>/dev/null && pwd)"
    [ "$_fu_dir" = "/" ] && break
    _fu_i=$((_fu_i + 1))
  done
  return 1
}

RR_ROOT="${ROOT_OVERRIDE:-${RR_ROOT:-}}"
if [ -z "$RR_ROOT" ]; then
  if [ -n "${OC_CONFIG_ROOT:-}" ]; then RR_ROOT="$OC_CONFIG_ROOT"
  elif [ -d /data/.openclaw ]; then RR_ROOT="/data/.openclaw"
  elif [ -d "$HOME/.openclaw" ]; then RR_ROOT="$HOME/.openclaw"
  fi
fi
if [ -z "$RR_ROOT" ] || [ ! -d "$RR_ROOT" ]; then
  echo "rr-readiness.sh: ENVIRONMENT no openclaw root resolved (tried --root, OC_CONFIG_ROOT, /data/.openclaw, \$HOME/.openclaw)" >&2
  exit 78
fi

# ---------------------------------------------------------------------------
# The shared helpers: descriptor first (it owns host/container identity), then
# the RR-027 parser, then the RR-028 engine. Missing pieces are REPORTED, never
# papered over: an absent descriptor leaves the runtime unresolved, which the
# state machine turns into an explicit ENROLLED_PENDING reason.
# ---------------------------------------------------------------------------
OCD_LOADED=0
_OCD_CAND=""
for _cand in "${OC_ENV_DESCRIPTOR:-}" "$RR_ROOT/skills/shared-utils/oc-env-descriptor.sh" \
             "$SELF_DIR/../shared-utils/oc-env-descriptor.sh"; do
  [ -n "$_cand" ] && [ -f "$_cand" ] && { _OCD_CAND="$_cand"; break; }
done
if [ -z "$_OCD_CAND" ]; then _OCD_CAND="$(_find_up "shared-utils/oc-env-descriptor.sh" || true)"; fi
if [ -n "$_OCD_CAND" ] && [ -f "$_OCD_CAND" ]; then
  # shellcheck disable=SC1090
  . "$_OCD_CAND" && OCD_LOADED=1
fi

PARSER=""
for _cand in "$RR_ROOT/skills/shared-utils/rescue-env.sh" "$SELF_DIR/../shared-utils/rescue-env.sh"; do
  [ -n "$_cand" ] && [ -f "$_cand" ] && { PARSER="$_cand"; break; }
done
[ -n "$PARSER" ] || PARSER="$(_find_up "shared-utils/rescue-env.sh" || true)"
if [ -n "$PARSER" ] && [ -f "$PARSER" ]; then
  # shellcheck disable=SC1090
  . "$PARSER"
fi

ENGINE=""
for _cand in "$RR_ROOT/skills/shared-utils/rr-readiness.sh" "$SELF_DIR/../shared-utils/rr-readiness.sh" "$SELF_DIR/rr-readiness.sh"; do
  [ -n "$_cand" ] && [ -f "$_cand" ] && { ENGINE="$_cand"; break; }
done
[ -n "$ENGINE" ] || ENGINE="$(_find_up "shared-utils/rr-readiness.sh" || true)"
if [ -z "$ENGINE" ] || [ ! -f "$ENGINE" ]; then
  echo "rr-readiness.sh: ENVIRONMENT rr-readiness engine (shared-utils/rr-readiness.sh) not found — cannot report readiness" >&2
  exit 78
fi
# shellcheck disable=SC1090
. "$ENGINE"

# The descriptor resolves the SAME tree this tool reports on (RR-030 fixture
# contract: OC_CONFIG_ROOT addresses root/state/db). Unset unless the caller
# pinned one, so a live box keeps its own discovery.
if [ "$OCD_LOADED" = "1" ]; then
  if [ -z "${OC_CONFIG_ROOT:-}" ]; then OC_CONFIG_ROOT="$RR_ROOT"; fi
  ocd_init
fi

# ---------------------------------------------------------------------------
# rrr_report <exit-mapped> — resolve inputs, run the state machine, print.
# ---------------------------------------------------------------------------
rr_report() {
  rr_prime
  if [ "$RRR_DIGEST_STATE" = "resolved" ]; then
    rrr_receipt_read "$RRR_STATE_DIR" "$RRR_DIGEST"
  fi
  rrr_evaluate
  if [ "$MODE" = "json" ]; then rrr_report_json; else rrr_report_line; fi
  case "$RRR_STATE" in
    VERIFIED)         return 0 ;;
    SCHEDULED)        return 1 ;;
    ENROLLED_PENDING) return 2 ;;
    UNENROLLED)       return 3 ;;
    *)                return 78 ;;
  esac
}

# ---------------------------------------------------------------------------
# The safe test claim. Writes a receipt ONLY on a structured no-work 2xx from
# the intended runtime. Always re-evaluates afterwards.
# ---------------------------------------------------------------------------
rr_probe() {
  if [ "$RRR_HAS_URL" != "1" ] || [ "$RRR_HAS_TOKEN" != "1" ] || [ "$RRR_HAS_SLUG" != "1" ]; then
    echo "rr-probe: cannot probe — enrollment incomplete ($RRR_MISSING)" >&2
    return 2
  fi
  if [ "$RRR_DIGEST_STATE" != "resolved" ]; then
    echo "rr-probe: cannot probe — desired-config digest unresolved ($RRR_DIGEST_STATE)" >&2
    return 2
  fi
  if [ "$RRR_RUNTIME_STATE" != "resolved" ]; then
    echo "rr-probe: cannot probe — intended runtime unresolved (no host/container descriptor); a receipt from an unnamed runtime could never verify anything" >&2
    return 2
  fi
  if [ "$RRR_REQ_CURL" != "ok" ]; then
    echo "rr-probe: cannot probe — curl unresolved" >&2
    return 2
  fi
  _pb_dir="$RRR_STATE_DIR/readiness"
  ( umask 077; mkdir -p "$_pb_dir" 2>/dev/null ) || { echo "rr-probe: state dir not writable: $RRR_STATE_DIR" >&2; return 2; }
  chmod 700 "$_pb_dir" 2>/dev/null || true
  _pb_tmp="$(mktemp -d "${TMPDIR:-/tmp}/rr028-probe.XXXXXX" 2>/dev/null)" || return 2
  chmod 700 "$_pb_tmp" 2>/dev/null || true
  _pb_body="$_pb_tmp/body.json"
  _pb_out="$_pb_tmp/out"
  _pb_hdr=""
  # No credential in this body and no credential in argv: the token rides the
  # 0600 header file only.
  {
    printf '{"action":"claim","box_slug":"%s","capacity":0,"mode":"dry_run",' "$(rrr_json_escape "$RRR_SLUG")"
    printf '"probe":{"kind":"rr-028-safe-test-claim","digest":"%s","runtime_id":"%s"}}' "$RRR_DIGEST" "$RRR_RUNTIME_ID"
  } > "$_pb_body" 2>/dev/null || { rm -rf "$_pb_tmp"; return 2; }
  chmod 600 "$_pb_body" 2>/dev/null || true
  _pb_hdr="$(rescue_env_header_file "$_pb_dir" "X-RR-Box-Token" "$(rescue_env_get "$RRR_SECRETS" RR_BOX_TOKEN 2>/dev/null)")" || _pb_hdr=""
  if [ -z "$_pb_hdr" ] || [ ! -f "$_pb_hdr" ]; then
    rm -rf "$_pb_tmp"
    echo "rr-probe: cannot probe — credential header file could not be staged" >&2
    return 2
  fi
  _pb_timeout="${RR_RECEIVER_PROBE_TIMEOUT:-25}"
  case "$_pb_timeout" in ''|*[!0-9]*) _pb_timeout=25 ;; esac
  # argv-safe: the URL, every flag and every path is ONE argv element.
  _pb_code=""
  _pb_code="$(curl -sS --max-time "$_pb_timeout" --connect-timeout 10 \
      -H @"$_pb_hdr" \
      -H 'Content-Type: application/json' \
      --data-binary @"$_pb_body" \
      -o "$_pb_out" \
      -w '%{http_code}' \
      "$RRR_URL" 2>/dev/null)" || _pb_code=""
  rm -f "$_pb_hdr"
  _pb_class="transport_error"; _pb_transport="error"; _pb_status=0
  _pb_structured="false"
  case "$_pb_code" in
    2*)
      _pb_status="$_pb_code"; _pb_transport="ok"
      _pb_bodytext="$(cat "$_pb_out" 2>/dev/null)"
      _pb_st="$(rrr_json_get "$_pb_bodytext" "status")"
      if [ -n "$_pb_st" ]; then
        _pb_structured="true"
        case "$_pb_st" in
          empty|no_work) _pb_class="no_work" ;;
          instruction)   _pb_class="instruction_refused" ;;
          disabled)      _pb_class="disabled" ;;
          unauthorized)  _pb_class="unauthorized" ;;
          *)             _pb_class="unsupported_status" ;;
        esac
      else
        _pb_class="unstructured_response"
      fi
      ;;
    3*)  _pb_class="redirect_wall" ;;
    401|403) _pb_class="unauthorized" ;;
    429) _pb_class="throttled" ;;
    5*)  _pb_class="server_error" ;;
    "")  _pb_class="transport_error" ;;
    *)   _pb_class="http_$_pb_code" ;;
  esac
  rrr_probe_log "$_pb_class" "$_pb_status" "$_pb_transport" "$_pb_structured"
  if [ "$_pb_class" = "instruction_refused" ]; then
    # The receiver handed work to a probe. Execute NOTHING, ack NOTHING (an ack
    # would be a verdict about a turn that never ran), and write NO receipt:
    # readiness must stay SCHEDULED. The ticket stays non-terminal for the SLA
    # machinery, exactly as RR-025 requires for a refused claim.
    echo "rr-probe: RECEIVER RETURNED AN INSTRUCTION TO A CAPACITY-0 DRY-RUN PROBE — refused: no agent turn, no ack, no receipt (ticket left non-terminal)" >&2
    rm -rf "$_pb_tmp"
    return 1
  fi
  if [ "$_pb_class" != "no_work" ] || [ "$_pb_transport" != "ok" ] || [ "$_pb_structured" != "true" ]; then
    echo "rr-probe: probe NOT verified (class=$_pb_class http=${_pb_status:-none} transport=$_pb_transport structured=$_pb_structured); no receipt written" >&2
    rm -rf "$_pb_tmp"
    return 1
  fi
  if ! rrr_receipt_write "$RRR_STATE_DIR" "$RRR_DIGEST" "$RRR_RUNTIME_ID" "$_pb_status" "$_pb_transport"; then
    echo "rr-probe: probe answered no_work but the receipt could not be written; NOT reporting ready" >&2
    rm -rf "$_pb_tmp"
    return 1
  fi
  rm -rf "$_pb_tmp"
  # M-4: the probe can only prove what the ANSWER was — a transport-OK,
  # structured, no-work, zero-turn/zero-ack claim returned by the intended
  # runtime — and that the matching receipt was written. Whether the box is
  # actually READY also depends on the schedule readback, which this line does
  # NOT establish: on a box with no cron the verdict below is correctly
  # ENROLLED_PENDING/cron_state_*, so claiming "verified" here misled operators
  # grepping the log. Say exactly what was verified, and name the schedule state.
  echo "rr-probe: safe test claim answer VERIFIED as a no-work result from the intended runtime (digest=$RRR_DIGEST runtime=$RRR_RUNTIME_ID http=$_pb_status class=no_work turns=0 acks=0); receipt written — this proves the RECEIVER answered, not that the cron is scheduled (readback cron.state=$RRR_CRON_STATE)"
  return 0
}

# Append-only probe log: class/status/digest only — never a value.
rrr_probe_log() {
  _pl_class="$1"; _pl_status="$2"; _pl_transport="$3"; _pl_structured="$4"
  printf '%s rr-probe class=%s http=%s transport=%s structured=%s digest=%s runtime=%s\n' \
    "$(rrr_now_iso)" "$_pl_class" "${_pl_status:-none}" "$_pl_transport" "$_pl_structured" \
    "${RRR_DIGEST:-none}" "${RRR_RUNTIME_ID:-none}" \
    >> "$RRR_STATE_DIR/readiness/probe.log" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Reconcile-then-report. The reconciler's own verdicts map onto the state
# machine: a mutation that fails hard is reported, never smoothed over.
# ---------------------------------------------------------------------------
rr_reconcile() {
  rrr_cron_reconcile
  _rc="$RRR_RECONCILE_RC"
  case "$_rc" in
    0) echo "rr-reconcile: cron reconciled and READ BACK (action=$RRR_RECONCILE_ACTION state=$RRR_RECONCILE_STATE)" ;;
    3) echo "rr-reconcile: cron could not be read back (state=$RRR_RECONCILE_STATE) — nothing claimed" >&2 ;;
    4) echo "rr-reconcile: desired cron NOT proven after reconciliation (state=$RRR_RECONCILE_STATE)" >&2 ;;
    5) echo "rr-reconcile: openclaw CLI unresolved" >&2 ;;
    6) echo "rr-reconcile: not mutated — $RRR_RECONCILE_STATE (operator intent respected)" >&2 ;;
    7) echo "rr-reconcile: mutation command FAILED (state=$RRR_RECONCILE_STATE)" >&2 ;;
    8) echo "rr-reconcile: REFUSED to mutate — $RRR_RECONCILE_STATE: no view that can show a DISABLED job was available, so the name is not proven free and nothing was changed (fail-closed)" >&2 ;;
  esac
  return 0
}

# Probe and reconcile need the resolved inputs first, so prime the state once
# without printing, then act, then report for real. RRR_DB is set BEFORE the
# engine's readback so the DB view (the only one that sees a DISABLED job) is
# available to the reconciler — a CLI-only readback must never be able to
# resurrect an operator-disabled cron.
rr_prime() {
  RRR_DB="${OCD_DB:-${OC_STATE_DB:-}}"
  rrr_init "$RR_ROOT" "$RR_ROOT/secrets/.env" "$RR_ROOT/skills/65-rescue-receiver/rescue-poll.sh" \
           "$RR_ROOT/state/$RRR_STATE_NAME"
}

rr_prime

if [ "$DO_RECONCILE" = "1" ]; then
  rr_reconcile
fi
if [ "$DO_PROBE" = "1" ]; then
  rr_probe || true
fi

rr_report
exit $?
