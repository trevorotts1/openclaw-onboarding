#!/usr/bin/env bash
# openclaw_browser_adapter.sh: the OpenClaw managed-browser adapter. It maps
# Skill 06 builder calls onto the OpenClaw browser CLI (`openclaw browser`,
# extension driver). Plan ref P1-12 / 9.7-6 / Appendix A.
#
# LANE POLICY (load-bearing, read before wiring): this adapter serves the
# `openclaw_managed_browser` mechanism, the PRIMARY browser mechanism since
# the operator decision of 2026-10-13 (the OpenClaw Chrome extension is
# Skill 6's default engine). The capability probe
# (tools/capability_probe.py) is the sole decider: this adapter runs only
# when the probe has selected the `openclaw_managed_browser` lane. The
# gates THIS adapter enforces are exactly two: Gate 1, the `openclaw` CLI
# must be present on PATH (refusal exit 64, checked first); Gate 2, the
# capability gate, which reads ONLY
# `lanes.openclaw_managed_browser.cliWorks` from the capability JSON and
# refuses (exit 75) unless it is `true`. The extension installed-and-
# current condition is NOT re-checked here: the probe's lane eligibility
# already requires the extension installed and current, plus the plugin
# enabled and the CLI working, before it selects this lane. agent-browser via
# browser_manager.sh (pin 0.27.0) is the FALLBACK mechanism; do not remove
# that pin, it carries every host the extension lane cannot.
#
# COMPLETION CONTRACT (W3 connection 7 — no prerequisite rung may report done)
# ---------------------------------------------------------------------------
# A verb running successfully is NOT the requested operation being done. This
# adapter therefore separates the two in every receipt it writes:
#
#   prerequisite_ready  the verb ran (page opened, snapshot taken, element
#                       clicked). Progress. NEVER a completion.
#   operation_complete  the SAME operation named by --operation is COMPLETE.
#                       Emitted only when ALL of these hold:
#                         * --operation ID and --location ID were supplied
#                         * the capability receipt carries a per-operation
#                           browser route for this box
#                           (operationCapabilities.scope ==
#                            "per-operation+per-connected-location" with a
#                            non-empty browser route list)
#                         * --expect-token TOKEN was supplied and the CLI's own
#                           output contained that token verbatim (the local,
#                           falsifiable proof that the operation's result
#                           appeared — not a caller assertion)
#                         * the CLI exit code was 0
#                         * for a verb that uses DOM refs (click/type) the refs
#                           were refreshed for THIS invocation
#                           (--refresh-snapshot; refs are never inherited from
#                           a session the adapter merely assumes is shared)
#                       Anything less writes operation_complete=false with the
#                       reason, and status "prerequisite_ready" or "failed".
#
# CLEANUP: `stop` closes ONLY the current managed tab and records it as
# released; `close --all` (which would close the user's unrelated tabs) is
# REFUSED. Every receipt carries owned_sessions + cleanup so the caller can
# prove nothing the task created was left running.
#
# WHY AN ADAPTER: Skill 6's builder speaks a small verb vocabulary (status /
# start / open / snapshot / click / type / frame-snapshot / stop). This file is
# the ONE place those verbs are translated to `openclaw browser` subcommands,
# so a managed-browser client never hand-rolls CLI plumbing and the mapping
# is testable offline. Snapshot defaults per plan P1-12: ALWAYS
# `--interactive` (snapshotDefaults), the `--efficient` preset ON by
# default (snapshotDefaults.mode: efficient, matching the capability JSON
# optimizations.snapshotMode = "efficient"), and `--frame SELECTOR` is
# passed through VERBATIM whenever given (frame-scoped snapshots are the
# whole point of the managed-browser mechanism on iframe-heavy GHL builder
# pages, Appendix A / 9.6).
#
# SAFETY: headless-safe and browser-safe. This adapter NEVER launches a
# browser in --selftest: every selftest invocation runs either against a
# PATH stripped of the openclaw CLI or against a tiny argv-echoing STUB, so
# no real browser process can ever start from a selftest. No secrets are
# read or printed. Nothing is written outside mktemp (selftest/receipt only).
#
# PORTABILITY: bash-3.2-safe for the Mac fleet half — no `mapfile`, no
# `declare -A`, no `${var,,}`; POSIX grep. `set -u` is fine; `set -e` is
# deliberately NOT used (explicit return-code checks only, matching
# browser_manager.sh which must survive being sourced). Indexed arrays ARE
# bash-3.2-safe and are used for the pass-through argument list.
#
# EXIT CODES (pick + document, per the browser_manager convention):
#   0   success (verb ran; openclaw's own exit code passes through)
#   64  usage error (unknown verb / missing argument) OR openclaw CLI absent
#   75  capability gate refusal — capability JSON missing/unreadable, python3
#       missing, or lanes.openclaw_managed_browser.cliWorks is not true
#   (a real `timeout` kill surfaces as the timeout binary's own code)
#
# USAGE:
#   bash openclaw_browser_adapter.sh <verb> [adapter flags] [--] [args...]
#   bash openclaw_browser_adapter.sh --selftest
#   bash openclaw_browser_adapter.sh --help
#
# ADAPTER FLAGS (stripped before the openclaw args; safe on every verb):
#   --operation ID       the operation this invocation serves (receipt)
#   --location ID        the connected location for that operation (receipt)
#   --receipt PATH       write the completion receipt JSON to PATH
#   --expect-token TEXT  local completion proof: TEXT must appear in the CLI's
#                        own output; without it operation_complete is never true
#   --refresh-snapshot   take a fresh snapshot before click/type so the refs are
#                        this invocation's, never an assumed shared session
#
# VERBS (mapping per plan Appendix A + live `openclaw browser --help`; EVERY
# browser command carries `--browser-profile "$OCB_PROFILE"`, shown as the
# openclaw default here):
#   status                     -> openclaw browser --browser-profile openclaw status
#   start                      -> openclaw browser --browser-profile openclaw start (no-op if running)
#   open URL [opts...]         -> openclaw browser --browser-profile openclaw open URL
#   snapshot [opts...]         -> openclaw browser --browser-profile openclaw snapshot --interactive [opts...]
#                                 (+ `--efficient` preset by default; a caller's
#                                 `--frame SELECTOR` passes through verbatim)
#   frame-snapshot SEL [opts]  -> openclaw browser --browser-profile openclaw snapshot --interactive --frame SEL
#   click REF                  -> openclaw browser --browser-profile openclaw click REF
#   type REF TEXT              -> openclaw browser --browser-profile openclaw type REF TEXT
#   stop                       -> openclaw browser --browser-profile openclaw close
#                                 (closes the current managed tab, per the P1-12
#                                 contract; the CLI's process-level `stop` is
#                                 intentionally NOT mapped — closing the tab is
#                                 the Skill 6 teardown unit. `close --all` is
#                                 refused: it would close unrelated tabs.)
#
# ENV (all optional):
#   GHL_SKILL6_CAPABILITY_JSON  capability JSON path
#                               (default <skill>/working/skill6-capability.json)
#   OCB_PROFILE                 browser profile for EVERY `browser` command
#                               (default: openclaw — status AND actions, so a
#                               selected profile is never silently bypassed)
#   OCB_CALL_TIMEOUT            per-call timeout seconds (default: 120)
#   GHL_SKILL6_SNAPSHOT_MODE    "efficient" (default) adds `--efficient`;
#                               any other value omits the preset

set -u

OCB_ADAPTER_VERSION="v0.2.0"

# Resolve the skill dir (this file lives in <skill>/tools/).
_OCB_SELF_PATH="$0"
case "$_OCB_SELF_PATH" in
  */*) ;;
  *) _OCB_SELF_PATH="./$_OCB_SELF_PATH" ;;
esac
OCB_SKILL_DIR="$(cd "$(dirname "$_OCB_SELF_PATH")/.." && pwd)"

CAPABILITY_JSON="${GHL_SKILL6_CAPABILITY_JSON:-$OCB_SKILL_DIR/working/skill6-capability.json}"
OCB_BIN_NAME="openclaw"
OCB_PROFILE="${OCB_PROFILE:-openclaw}"
OCB_CALL_TIMEOUT="${OCB_CALL_TIMEOUT:-120}"
OCB_SNAPSHOT_MODE="${GHL_SKILL6_SNAPSHOT_MODE:-efficient}"

# Adapter-flag state, filled by _ocb_parse_flags on every real verb.
_OCB_OPERATION=""
_OCB_LOCATION=""
_OCB_RECEIPT=""
_OCB_EXPECT_TOKEN=""
_OCB_REFRESH=0
_OCB_ARGS=()

usage() {
  cat <<'USAGE'
openclaw_browser_adapter.sh — OpenClaw managed-browser adapter: Skill 6 builder verbs -> `openclaw browser`.

This is the `openclaw_managed_browser` lane, PRIMARY on an OpenClaw host since the
operator decision of 2026-10-13 when the capability probe selects it (OpenClaw >=
2026.8.1, browser plugin enabled, CLI working, Chrome extension installed + current).
agent-browser via browser_manager.sh (pin 0.27.0) is the FALLBACK engine and carries
every host this lane cannot. The probe (tools/capability_probe.py) is the sole decider;
this adapter refuses unless lanes.openclaw_managed_browser.cliWorks is true.

SYNOPSIS
  openclaw_browser_adapter.sh <verb> [adapter flags] [--] [args...]

ADAPTER FLAGS (stripped before the openclaw args)
  --operation ID       operation this invocation serves (receipt identity)
  --location ID        connected location for that operation (receipt identity)
  --receipt PATH       write the completion receipt JSON to PATH
  --expect-token TEXT  local proof the operation's result appeared; without it
                       operation_complete is never reported true
  --refresh-snapshot   fresh snapshot before click/type (refs are never inherited)

VERBS (each carries `--browser-profile "$OCB_PROFILE"`; shown as openclaw default):
  status                     openclaw browser --browser-profile openclaw status
  start                      openclaw browser --browser-profile openclaw start   (no-op if running)
  open URL [opts...]         openclaw browser --browser-profile openclaw open URL
  snapshot [opts...]         openclaw browser --browser-profile openclaw snapshot --interactive [opts...]
                             (+ --efficient preset by default; --frame SELECTOR passes through verbatim)
  frame-snapshot SEL [opts]  openclaw browser --browser-profile openclaw snapshot --interactive --frame SEL
  click REF                  openclaw browser --browser-profile openclaw click REF
  type REF TEXT              openclaw browser --browser-profile openclaw type REF TEXT
  stop                       openclaw browser --browser-profile openclaw close  (closes the managed tab; --all refused)

COMPLETION
  A verb that ran is prerequisite_ready, never operation_complete. Completion needs
  --operation + --location + a per-operation browser route in the capability receipt
  + --expect-token found in the CLI output + exit 0 (+ refreshed refs for click/type).

FLAGS:
  --selftest                 offline self-test (no openclaw CLI, no browser, no network needed)
  --help                     this text

ENV:
  GHL_SKILL6_CAPABILITY_JSON  capability JSON path (default <skill>/working/skill6-capability.json)
  OCB_PROFILE                 browser profile for EVERY browser command (default openclaw)
  OCB_CALL_TIMEOUT            per-call timeout seconds (default 120)
  GHL_SKILL6_SNAPSHOT_MODE    "efficient" (default) adds --efficient; anything else omits it

EXIT CODES:
  0 success; 64 usage error / openclaw CLI absent; 75 capability gate refusal.
USAGE
}

_ocb_usage_refuse() {
  echo "REFUSE: $1" >&2
  echo "Run with --help for the verb table." >&2
  exit 64
}

# ── GATE 1: openclaw CLI present (checked FIRST on every verb; exit 64) ───────
require_ocb_cli() {
  if ! command -v "$OCB_BIN_NAME" >/dev/null 2>&1; then
    echo "REFUSE: openclaw CLI not found on PATH (command -v $OCB_BIN_NAME failed)." >&2
    echo "The managed-browser lane needs the openclaw CLI; the agent-browser FALLBACK" >&2
    echo "(browser_manager.sh) does not. Aborting." >&2
    exit 64
  fi
}

# ── GATE 2: capability gate (exit 75) ─────────────────────────────────────────
# Parse lanes.openclaw_managed_browser.cliWorks out of the capability JSON with
# python3 -c (stdlib json only — BSD-safe, no jq dependency). Fail CLOSED: any
# parse error, missing file, or non-true value refuses with exit 75.
_ocb_cliworks_py='import json, sys
try:
    with open(sys.argv[1], "r") as f:
        d = json.load(f)
    lane = d.get("lanes", {}).get("openclaw_managed_browser", {})
    print("True" if lane.get("cliWorks") is True else "False")
except Exception:
    print("Error")'

# Per-operation route check (W3 connection 7): a box-level `cliWorks` proves a
# LANE, not an operation. A per-operation completion also needs the probe's
# per-operation+per-location browser route record. Fail CLOSED: absent record,
# wrong scope, or an empty route list answers False (prerequisite only).
_ocb_route_py='import json, sys
try:
    with open(sys.argv[1], "r") as f:
        d = json.load(f)
    caps = d.get("operationCapabilities") or {}
    browser = (caps.get("transports") or {}).get("browser") or {}
    routes = browser.get("routes") or []
    scope = caps.get("scope")
    ok = (scope == "per-operation+per-connected-location"
          and isinstance(routes, list) and len(routes) > 0)
    print("True" if ok else "False")
except Exception:
    print("Error")'

require_capability() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "REFUSE: capability gate — python3 not found, cannot parse capability" >&2
    echo "JSON at $CAPABILITY_JSON. Fail-closed: the managed-browser lane stays" >&2
    echo "disabled. Aborting." >&2
    exit 75
  fi
  _ocb_cliworks="$(python3 -c "$_ocb_cliworks_py" "$CAPABILITY_JSON" 2>/dev/null)" || _ocb_cliworks=""
  case "$_ocb_cliworks" in
    True)
      : ;;
    False)
      echo "REFUSE: capability gate — lanes.openclaw_managed_browser.cliWorks is" >&2
      echo "NOT true in $CAPABILITY_JSON. Re-run tools/capability_probe.py first." >&2
      echo "The probe did not select the managed-browser lane for this host; it is" >&2
      echo "primary only when the probe proves it. Aborting." >&2
      exit 75
      ;;
    *)
      echo "REFUSE: capability gate — capability JSON missing or unreadable at" >&2
      echo "$CAPABILITY_JSON (run tools/capability_probe.py to write it)." >&2
      echo "Fail-closed: the managed-browser lane stays disabled. Aborting." >&2
      exit 75
      ;;
  esac
}

# _ocb_route_available — True | False | Error. Never a completion by itself.
_ocb_route_available() {
  if ! command -v python3 >/dev/null 2>&1; then
    printf '%s' "Error"
    return 0
  fi
  python3 -c "$_ocb_route_py" "$CAPABILITY_JSON" 2>/dev/null || printf '%s' "Error"
}

# ── Runner: direct binary name (never `command` under `timeout` — see the
#    browser_manager.sh AB() note about macOS /usr/bin/command vs Linux 127) ──
ocb() {
  if command -v timeout >/dev/null 2>&1; then
    timeout "$OCB_CALL_TIMEOUT" "$OCB_BIN_NAME" "$@"
  else
    "$OCB_BIN_NAME" "$@"
  fi
}

# Every `openclaw browser` invocation goes through here so the SELECTED profile
# is always passed. Passing it on `status` only was finding 49: open/click/type/
# snapshot silently acted on the DEFAULT profile while the caller's chosen
# profile was never used.
ocb_browser() {
  ocb browser --browser-profile "$OCB_PROFILE" "$@"
}

# Snapshot defaults per plan P1-12 (snapshotDefaults): ALWAYS --interactive;
# `--efficient` preset on by default (GHL_SKILL6_SNAPSHOT_MODE=efficient,
# mirroring the capability JSON optimizations.snapshotMode); caller args —
# including --frame SELECTOR — pass through verbatim after the defaults.
run_snapshot() {
  if [ "$OCB_SNAPSHOT_MODE" = "efficient" ]; then
    set -- --efficient "$@"
  fi
  set -- --interactive "$@"
  ocb_browser snapshot "$@"
}

# ── Flag parsing (bash-3.2-safe indexed array; -- separates verb args) ───────
# Adapter flags are stripped wherever they appear so a caller can put them before
# or after the verb's own arguments. EVERYTHING else passes through verbatim.
_ocb_parse_flags() {
  _OCB_OPERATION=""
  _OCB_LOCATION=""
  _OCB_RECEIPT=""
  _OCB_EXPECT_TOKEN=""
  _OCB_REFRESH=0
  _OCB_ARGS=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --operation)
        [ "$#" -ge 2 ] || _ocb_usage_refuse "--operation requires an operation id."
        _OCB_OPERATION="$2"; shift 2 ;;
      --location)
        [ "$#" -ge 2 ] || _ocb_usage_refuse "--location requires a location id."
        _OCB_LOCATION="$2"; shift 2 ;;
      --receipt)
        [ "$#" -ge 2 ] || _ocb_usage_refuse "--receipt requires a path."
        _OCB_RECEIPT="$2"; shift 2 ;;
      --expect-token)
        [ "$#" -ge 2 ] || _ocb_usage_refuse "--expect-token requires a token."
        _OCB_EXPECT_TOKEN="$2"; shift 2 ;;
      --refresh-snapshot)
        _OCB_REFRESH=1; shift ;;
      --)
        shift
        while [ "$#" -gt 0 ]; do
          _OCB_ARGS[${#_OCB_ARGS[@]}]="$1"; shift
        done ;;
      *)
        _OCB_ARGS[${#_OCB_ARGS[@]}]="$1"; shift ;;
    esac
  done
  # The stripped verb args are handed back in _OCB_ARGS. main() re-binds its
  # OWN positional parameters from that array: `set --` here would only change
  # this function's parameters and let the adapter flags leak to the CLI.
}

# ── Receipt (the ONLY place a completion may be claimed) ─────────────────────
# _ocb_write_receipt VERB EXIT_CODE STATUS REASON
#   STATUS: operation_complete | prerequisite_ready | failed
_ocb_json_escape() {
  printf '%s' "$1" | tr '\t\r\n' '   ' | sed 's/\\/\\\\/g; s/"/\\"/g'
}

_ocb_write_receipt() {
  _ocb_r_verb="$1"
  _ocb_r_rc="$2"
  _ocb_r_status="$3"
  _ocb_r_reason="$4"
  [ -n "$_OCB_RECEIPT" ] || return 0
  _ocb_complete=0
  [ "$_ocb_r_status" = "operation_complete" ] && _ocb_complete=1
  _ocb_prereq=0
  [ "$_ocb_r_status" = "prerequisite_ready" ] && _ocb_prereq=1
  _ocb_ok=0
  [ "$_ocb_r_rc" = "0" ] && _ocb_ok=1
  _ocb_refs=1
  case "$_ocb_r_verb" in
    click|type) [ "$_OCB_REFRESH" = "1" ] && _ocb_refs=1 || _ocb_refs=0 ;;
  esac
  _ocb_owned="\"tab:$( _ocb_json_escape "$OCB_PROFILE" )\""
  _ocb_cleanup="{\"released\": [], \"closed_all\": false}"
  if [ "$_ocb_r_verb" = "stop" ]; then
    _ocb_cleanup="{\"released\": [$_ocb_owned], \"closed_all\": false}"
  fi
  mkdir -p "$(dirname "$_OCB_RECEIPT")" 2>/dev/null
  printf '{\n  "operation": "%s",\n  "locationId": "%s",\n  "verb": "%s",\n  "ok": %s,\n  "exitCode": %s,\n  "status": "%s",\n  "operation_complete": %s,\n  "prerequisite_ready": %s,\n  "partial": false,\n  "references_fresh": %s,\n  "owned_sessions": [%s],\n  "cleanup": %s,\n  "reason": "%s",\n  "adapterVersion": "%s"\n}\n' \
    "$( _ocb_json_escape "$_OCB_OPERATION" )" \
    "$( _ocb_json_escape "$_OCB_LOCATION" )" \
    "$( _ocb_json_escape "$_ocb_r_verb" )" \
    "$([ "$_ocb_ok" = "1" ] && printf true || printf false)" \
    "$_ocb_r_rc" \
    "$( _ocb_json_escape "$_ocb_r_status" )" \
    "$([ "$_ocb_complete" = "1" ] && printf true || printf false)" \
    "$([ "$_ocb_prereq" = "1" ] && printf true || printf false)" \
    "$([ "$_ocb_refs" = "1" ] && printf true || printf false)" \
    "$_ocb_owned" \
    "$_ocb_cleanup" \
    "$( _ocb_json_escape "$_ocb_r_reason" )" \
    "$OCB_ADAPTER_VERSION" \
    > "$_OCB_RECEIPT" 2>/dev/null || true
}

# _ocb_completion_status VERB EXIT_CODE OUT_FILE
# Prints "<status>|<reason>". Status is operation_complete ONLY on real, local
# proof of THIS operation; else prerequisite_ready or failed. The reason travels
# on stdout because this runs in a command substitution (a variable set here
# would die with the subshell).
_ocb_completion_status() {
  _ocb_c_verb="$1"
  _ocb_c_rc="$2"
  _ocb_c_out="$3"

  if [ "$_ocb_c_rc" != "0" ]; then
    printf '%s' "failed|the openclaw CLI exited $_ocb_c_rc; nothing is complete"
    return 0
  fi
  # A read-only verb can never be the operation itself.
  case "$_ocb_c_verb" in
    status|start|snapshot|frame-snapshot|stop)
      printf '%s' "prerequisite_ready|verb '$_ocb_c_verb' only prepares or observes; it does not complete an operation"
      return 0 ;;
  esac
  if [ -z "$_OCB_OPERATION" ]; then
    printf '%s' "prerequisite_ready|no --operation supplied; a verb cannot complete an unnamed operation"
    return 0
  fi
  if [ -z "$_OCB_LOCATION" ]; then
    printf '%s' "prerequisite_ready|no --location supplied; capability is per operation AND connected location"
    return 0
  fi
  _ocb_route="$(_ocb_route_available)"
  if [ "$_ocb_route" != "True" ]; then
    printf '%s' "prerequisite_ready|capability receipt carries no per-operation browser route (route=${_ocb_route}); prerequisite only"
    return 0
  fi
  if [ -z "$_OCB_EXPECT_TOKEN" ]; then
    printf '%s' "prerequisite_ready|no --expect-token supplied; the adapter has no local proof the operation's result appeared"
    return 0
  fi
  case "$_ocb_c_verb" in
    click|type)
      if [ "$_OCB_REFRESH" != "1" ]; then
        printf '%s' "prerequisite_ready|DOM refs were not refreshed for this invocation (pass --refresh-snapshot); a stale ref is not proof"
        return 0
      fi ;;
  esac
  if [ -z "$_ocb_c_out" ] || [ ! -f "$_ocb_c_out" ]; then
    printf '%s' "prerequisite_ready|no CLI output to check for the expected token"
    return 0
  fi
  if grep -F -q -- "$_OCB_EXPECT_TOKEN" "$_ocb_c_out" 2>/dev/null; then
    printf '%s' "operation_complete|expected token observed in the CLI output for operation $_OCB_OPERATION at $_OCB_LOCATION"
    return 0
  fi
  printf '%s' "prerequisite_ready|expected token did not appear in the CLI output; the operation's result is not proven"
}

# _ocb_finish VERB EXIT_CODE OUT_FILE -> writes the receipt, echoes the status
_ocb_finish() {
  _ocb_f_verb="$1"
  _ocb_f_rc="$2"
  _ocb_f_out="$3"
  _ocb_verdict="$(_ocb_completion_status "$_ocb_f_verb" "$_ocb_f_rc" "$_ocb_f_out")"
  _ocb_status="${_ocb_verdict%%|*}"
  _ocb_reason="${_ocb_verdict#*|}"
  _ocb_write_receipt "$_ocb_f_verb" "$_ocb_f_rc" "$_ocb_status" "$_ocb_reason"
  if [ -n "$_OCB_RECEIPT" ]; then
    if [ "$_ocb_status" = "operation_complete" ]; then
      echo "receipt: $_OCB_RECEIPT status=operation_complete operation_complete=true" >&2
    else
      echo "receipt: $_OCB_RECEIPT status=$_ocb_status operation_complete=false ($_ocb_reason)" >&2
    fi
  fi
  return "$_ocb_f_rc"
}

# ── Shared action-verb body for click / type (kept in ONE place) ──────────────
_ocb_act_verb() {
  _ocb_a_verb="$1"
  shift
  if [ "$_ocb_a_verb" = "click" ] && [ "$#" -lt 1 ]; then
    _ocb_usage_refuse "click requires a REF argument (from a snapshot)."
  fi
  if [ "$_ocb_a_verb" = "type" ] && [ "$#" -lt 2 ]; then
    _ocb_usage_refuse "type requires REF and TEXT arguments."
  fi
  require_ocb_cli
  require_capability
  # Refresh FIRST so the refs acted on are this invocation's, never a stale ref
  # from a session the adapter merely assumes is shared.
  if [ "$_OCB_REFRESH" = "1" ]; then
    _ocb_pre="$(mktemp "${TMPDIR:-/tmp}/ocb-refresh.XXXXXX" 2>/dev/null || printf '')"
    if [ -n "$_ocb_pre" ]; then
      run_snapshot >"$_ocb_pre" 2>&1 || true
      rm -f "$_ocb_pre"
    fi
  fi
  _ocb_out="$(mktemp "${TMPDIR:-/tmp}/ocb-out.XXXXXX" 2>/dev/null || printf '')"
  if [ -n "$_ocb_out" ]; then
    ocb_browser "$_ocb_a_verb" "$@" >"$_ocb_out" 2>&1
  else
    ocb_browser "$_ocb_a_verb" "$@"
  fi
  _ocb_rc=$?
  [ -n "$_ocb_out" ] && cat "$_ocb_out"
  _ocb_finish "$_ocb_a_verb" "$_ocb_rc" "$_ocb_out"
  _ocb_rc=$?
  [ -n "$_ocb_out" ] && rm -f "$_ocb_out"
  exit "$_ocb_rc"
}

# ── Verb dispatch ─────────────────────────────────────────────────────────────
main() {
  if [ $# -lt 1 ]; then
    usage
    exit 64
  fi
  _ocb_verb="$1"
  shift
  case "$_ocb_verb" in
    --help|-h|help)
      usage
      exit 0
      ;;
    --version)
      echo "openclaw_browser_adapter $OCB_ADAPTER_VERSION"
      exit 0
      ;;
    --selftest)
      selftest
      exit $?
      ;;
  esac

  _ocb_parse_flags "$@"
  # Strip the adapter flags before the CLI: re-bind main's positional
  # parameters to the parsed verb args (bash-3.2-safe empty-array expansion).
  if [ "${#_OCB_ARGS[@]}" -gt 0 ]; then
    set -- "${_OCB_ARGS[@]}"
  else
    set --
  fi
  _ocb_out=""
  _ocb_rc=0

  case "$_ocb_verb" in
    status)
      require_ocb_cli
      require_capability
      _ocb_out="$(mktemp "${TMPDIR:-/tmp}/ocb-out.XXXXXX" 2>/dev/null || printf '')"
      if [ -n "$_ocb_out" ]; then
        ocb_browser status "$@" >"$_ocb_out" 2>&1
      else
        ocb_browser status "$@"
      fi
      _ocb_rc=$?
      [ -n "$_ocb_out" ] && cat "$_ocb_out"
      _ocb_finish status "$_ocb_rc" "$_ocb_out"
      _ocb_rc=$?
      [ -n "$_ocb_out" ] && rm -f "$_ocb_out"
      exit "$_ocb_rc"
      ;;
    start)
      require_ocb_cli
      require_capability
      _ocb_out="$(mktemp "${TMPDIR:-/tmp}/ocb-out.XXXXXX" 2>/dev/null || printf '')"
      if [ -n "$_ocb_out" ]; then
        ocb_browser start "$@" >"$_ocb_out" 2>&1
      else
        ocb_browser start "$@"
      fi
      _ocb_rc=$?
      [ -n "$_ocb_out" ] && cat "$_ocb_out"
      _ocb_finish start "$_ocb_rc" "$_ocb_out"
      _ocb_rc=$?
      [ -n "$_ocb_out" ] && rm -f "$_ocb_out"
      exit "$_ocb_rc"
      ;;
    open)
      require_ocb_cli
      if [ "${#_OCB_ARGS[@]}" -lt 1 ]; then
        _ocb_usage_refuse "open requires a URL argument."
      fi
      require_capability
      _ocb_out="$(mktemp "${TMPDIR:-/tmp}/ocb-out.XXXXXX" 2>/dev/null || printf '')"
      if [ -n "$_ocb_out" ]; then
        ocb_browser open "$@" >"$_ocb_out" 2>&1
      else
        ocb_browser open "$@"
      fi
      _ocb_rc=$?
      [ -n "$_ocb_out" ] && cat "$_ocb_out"
      _ocb_finish open "$_ocb_rc" "$_ocb_out"
      _ocb_rc=$?
      [ -n "$_ocb_out" ] && rm -f "$_ocb_out"
      exit "$_ocb_rc"
      ;;
    snapshot)
      require_ocb_cli
      require_capability
      _ocb_out="$(mktemp "${TMPDIR:-/tmp}/ocb-out.XXXXXX" 2>/dev/null || printf '')"
      if [ -n "$_ocb_out" ]; then
        run_snapshot "$@" >"$_ocb_out" 2>&1
      else
        run_snapshot "$@"
      fi
      _ocb_rc=$?
      [ -n "$_ocb_out" ] && cat "$_ocb_out"
      _ocb_finish snapshot "$_ocb_rc" "$_ocb_out"
      _ocb_rc=$?
      [ -n "$_ocb_out" ] && rm -f "$_ocb_out"
      exit "$_ocb_rc"
      ;;
    frame-snapshot)
      require_ocb_cli
      if [ "$#" -lt 1 ] || [ -z "${1:-}" ]; then
        _ocb_usage_refuse "frame-snapshot requires an iframe selector argument."
      fi
      _ocb_sel="$1"
      shift
      require_capability
      _ocb_out="$(mktemp "${TMPDIR:-/tmp}/ocb-out.XXXXXX" 2>/dev/null || printf '')"
      if [ -n "$_ocb_out" ]; then
        run_snapshot --frame "$_ocb_sel" "$@" >"$_ocb_out" 2>&1
      else
        run_snapshot --frame "$_ocb_sel" "$@"
      fi
      _ocb_rc=$?
      [ -n "$_ocb_out" ] && cat "$_ocb_out"
      _ocb_finish frame-snapshot "$_ocb_rc" "$_ocb_out"
      _ocb_rc=$?
      [ -n "$_ocb_out" ] && rm -f "$_ocb_out"
      exit "$_ocb_rc"
      ;;
    click)
      _ocb_act_verb click "$@"
      ;;
    type)
      _ocb_act_verb type "$@"
      ;;
    stop)
      require_ocb_cli
      # `close --all` would close the user's unrelated tabs. Refuse it here, in
      # the adapter, so no caller can reach it through `stop`.
      for _ocb_a in "$@"; do
        case "$_ocb_a" in
          --all|all|-a)
            _ocb_usage_refuse "stop refuses '$_ocb_a': closing EVERY tab would close the user's unrelated session. The adapter closes only the managed tab." ;;
        esac
      done
      require_capability
      _ocb_out="$(mktemp "${TMPDIR:-/tmp}/ocb-out.XXXXXX" 2>/dev/null || printf '')"
      if [ -n "$_ocb_out" ]; then
        ocb_browser close "$@" >"$_ocb_out" 2>&1
      else
        ocb_browser close "$@"
      fi
      _ocb_rc=$?
      [ -n "$_ocb_out" ] && cat "$_ocb_out"
      _ocb_finish stop "$_ocb_rc" "$_ocb_out"
      _ocb_rc=$?
      [ -n "$_ocb_out" ] && rm -f "$_ocb_out"
      exit "$_ocb_rc"
      ;;
    *)
      echo "REFUSE: unknown verb '$_ocb_verb'." >&2
      usage
      exit 64
      ;;
  esac
}

# ── OFFLINE SELFTEST ──────────────────────────────────────────────────────────
# Proves the wiring WITHOUT openclaw installed and WITHOUT ever launching a
# browser: verb calls run either with PATH stripped to /usr/bin:/bin (where the
# openclaw CLI does not live) or against a throwaway argv-echoing stub named
# `openclaw`. All temp files live under mktemp (TMPDIR). No network, no secrets.
selftest() {
  _st_fails=0
  _st_pass() { echo "  ok:   $1"; }
  _st_fail() { echo "  FAIL: $1" >&2; _st_fails=$((_st_fails + 1)); }

  _st_self="$(cd "$(dirname "$_OCB_SELF_PATH")" && pwd)/$(basename "$_OCB_SELF_PATH")"
  _st_clean_path="/usr/bin:/bin"

  echo "openclaw_browser_adapter selftest (offline; no browser will launch):"

  # 1. bash -n self-parse
  if bash -n "$_st_self" 2>/dev/null; then
    _st_pass "bash -n parses this script"
  else
    _st_fail "bash -n failed on $_st_self"
  fi

  # 2. python3 present (capability parser dependency)
  if command -v python3 >/dev/null 2>&1; then
    _st_pass "python3 present (capability JSON parser)"
  else
    _st_fail "python3 absent — capability JSON cannot be parsed"
  fi

  # 3. verb table present (every contracted verb has a dispatch arm)
  for _st_v in status start open snapshot click type frame-snapshot stop; do
    if grep -q "$_st_v)" "$_st_self" 2>/dev/null; then
      _st_pass "verb table has arm: $_st_v"
    else
      _st_fail "verb table missing arm: $_st_v"
    fi
  done

  # 4. every verb against a PATH WITHOUT openclaw -> exit 64 + names openclaw
  for _st_v in status start open snapshot click type frame-snapshot stop; do
    _st_out="$(PATH="$_st_clean_path" "$_st_self" "$_st_v" arg1 arg2 2>&1)"
    _st_rc=$?
    if [ "$_st_rc" = "64" ]; then
      case "$_st_out" in
        *openclaw*) _st_pass "no-openclaw PATH: verb $_st_v -> exit 64 + names openclaw" ;;
        *) _st_fail "no-openclaw PATH: verb $_st_v exit 64 but message does not name openclaw" ;;
      esac
    else
      _st_fail "no-openclaw PATH: verb $_st_v expected exit 64, got $_st_rc"
    fi
  done

  # 5. capability-gate refusals (stub openclaw so Gate 1 passes; Gate 2 must refuse)
  _st_dir="$(mktemp -d "${TMPDIR:-/tmp}/ocb-adapter-selftest.XXXXXX")" || _st_dir=""
  if [ -z "$_st_dir" ]; then
    _st_fail "mktemp failed — skipping stub checks"
  else
    printf '#!/bin/sh\nfor a in "$@"; do printf "%%s\\n" "$a"; done\nexit 0\n' \
      > "$_st_dir/openclaw" 2>/dev/null && chmod 755 "$_st_dir/openclaw" 2>/dev/null
    if [ -x "$_st_dir/openclaw" ]; then
      _st_stub_path="$_st_dir:/usr/bin:/bin"

      # 5a. cliWorks:false -> exit 75, message names the gate field
      printf '{"lanes":{"openclaw_managed_browser":{"cliWorks":false}}}' \
        > "$_st_dir/cap-false.json"
      _st_out="$(PATH="$_st_stub_path" GHL_SKILL6_CAPABILITY_JSON="$_st_dir/cap-false.json" \
        GHL_SKILL6_SNAPSHOT_MODE=efficient "$_st_self" status 2>&1)"
      _st_rc=$?
      if [ "$_st_rc" = "75" ]; then
        case "$_st_out" in
          *cliWorks*) _st_pass "cliWorks=false: status -> exit 75 + names cliWorks" ;;
          *) _st_fail "cliWorks=false: exit 75 but message does not name cliWorks" ;;
        esac
      else
        _st_fail "cliWorks=false: status expected exit 75, got $_st_rc"
      fi

      # 5b. capability JSON missing -> exit 75, message names the path
      _st_out="$(PATH="$_st_stub_path" \
        GHL_SKILL6_CAPABILITY_JSON="$_st_dir/absent.json" "$_st_self" status 2>&1)"
      _st_rc=$?
      if [ "$_st_rc" = "75" ]; then
        case "$_st_out" in
          *"$_st_dir/absent.json"*) _st_pass "missing capability JSON: exit 75 + names the path" ;;
          *) _st_fail "missing capability JSON: exit 75 but message does not name the path" ;;
        esac
      else
        _st_fail "missing capability JSON: status expected exit 75, got $_st_rc"
      fi

      # 5c. mapping checks: stub echoes one argv per line; assert the translation
      printf '{"lanes":{"openclaw_managed_browser":{"cliWorks":true}}}' \
        > "$_st_dir/cap-true.json"

      # snapshot -> --interactive + --efficient preset
      _st_out="$(env PATH="$_st_stub_path" GHL_SKILL6_CAPABILITY_JSON="$_st_dir/cap-true.json" \
        GHL_SKILL6_SNAPSHOT_MODE=efficient "$_st_self" snapshot 2>&1)"
      case "$_st_out" in
        *"--interactive"*) _st_pass "snapshot passes --interactive" ;;
        *) _st_fail "snapshot missing --interactive" ;;
      esac
      case "$_st_out" in
        *"--efficient"*) _st_pass "snapshot passes --efficient preset (P1-12 snapshotDefaults)" ;;
        *) _st_fail "snapshot missing --efficient preset" ;;
      esac

      # frame-snapshot -> --interactive --frame SELECTOR verbatim
      _st_out="$(env PATH="$_st_stub_path" GHL_SKILL6_CAPABILITY_JSON="$_st_dir/cap-true.json" \
        "$_st_self" frame-snapshot 'iframe[src*="form-builder-v2"]' 2>&1)"
      case "$_st_out" in
        *'--frame'*) _st_pass "frame-snapshot passes --frame" ;;
        *) _st_fail "frame-snapshot missing --frame" ;;
      esac
      case "$_st_out" in
        *'form-builder-v2'*) _st_pass "frame-snapshot passes SELECTOR verbatim" ;;
        *) _st_fail "frame-snapshot mangled the selector" ;;
      esac
      case "$_st_out" in
        *"--interactive"*) _st_pass "frame-snapshot passes --interactive" ;;
        *) _st_fail "frame-snapshot missing --interactive" ;;
      esac

      # open / click / type / stop / start / status mappings
      _st_out="$(env PATH="$_st_stub_path" GHL_SKILL6_CAPABILITY_JSON="$_st_dir/cap-true.json" \
        "$_st_self" open 'https://example.test/ghl' 2>&1)"
      case "$_st_out" in
        *"https://example.test/ghl"*) _st_pass "open passes URL" ;;
        *) _st_fail "open did not pass URL" ;;
      esac
      _st_out="$(env PATH="$_st_stub_path" GHL_SKILL6_CAPABILITY_JSON="$_st_dir/cap-true.json" \
        "$_st_self" click f1e12 2>&1)"
      case "$_st_out" in
        *"f1e12"*) _st_pass "click passes REF" ;;
        *) _st_fail "click did not pass REF" ;;
      esac
      _st_out="$(env PATH="$_st_stub_path" GHL_SKILL6_CAPABILITY_JSON="$_st_dir/cap-true.json" \
        "$_st_self" type f1e12 'hello world' 2>&1)"
      case "$_st_out" in
        *"hello"*) _st_pass "type passes TEXT" ;;
        *) _st_fail "type did not pass TEXT" ;;
      esac
      _st_out="$(env PATH="$_st_stub_path" GHL_SKILL6_CAPABILITY_JSON="$_st_dir/cap-true.json" \
        "$_st_self" stop 2>&1)"
      case "$_st_out" in
        *close*) _st_pass "stop maps to openclaw browser close" ;;
        *) _st_fail "stop does not map to close" ;;
      esac
      _st_out="$(env PATH="$_st_stub_path" GHL_SKILL6_CAPABILITY_JSON="$_st_dir/cap-true.json" \
        "$_st_self" start 2>&1)"
      case "$_st_out" in
        *start*) _st_pass "start maps to openclaw browser start" ;;
        *) _st_fail "start does not map to start" ;;
      esac
      _st_out="$(env PATH="$_st_stub_path" GHL_SKILL6_CAPABILITY_JSON="$_st_dir/cap-true.json" \
        "$_st_self" status 2>&1)"
      case "$_st_out" in
        *"--browser-profile"*) _st_pass "status passes --browser-profile" ;;
        *) _st_fail "status missing --browser-profile" ;;
      esac

      # finding 49: the SELECTED profile must reach EVERY browser command, not
      # only `status` — otherwise a caller's OCB_PROFILE is silently bypassed
      # and actions land on the default profile. Asserted end-to-end with a
      # NON-default profile so a hard-coded "openclaw" cannot pass this. The
      # verb's real exit code is captured too (a dead command that merely echoes
      # its argv on stderr must NOT count as proof), and the flag must be
      # IMMEDIATELY followed by the selected value (the stub echoes one argv per
      # line, so substring-anywhere would accept `--browser-profile openclaw ...
      # ghl-selected`).
      _st_needle="$(printf '\n%s\n%s' '--browser-profile' 'ghl-selected')"
      for _st_v in status start open snapshot click type frame-snapshot stop; do
        case "$_st_v" in
          open)           _st_args="https://example.test/ghl" ;;
          click)          _st_args="f1e12" ;;
          type)           _st_args="f1e12 hello" ;;
          frame-snapshot) _st_args='iframe[src*="form-builder-v2"]' ;;
          *)              _st_args="" ;;
        esac
        # shellcheck disable=SC2086
        _st_out="$(env PATH="$_st_stub_path" GHL_SKILL6_CAPABILITY_JSON="$_st_dir/cap-true.json" \
          OCB_PROFILE=ghl-selected "$_st_self" "$_st_v" $_st_args 2>&1)"
        _st_rc=$?
        _st_prof_ok=1
        [ "$_st_rc" = "0" ] || _st_prof_ok=0
        case "$_st_out" in
          *"$_st_needle"*) : ;;
          *) _st_prof_ok=0 ;;
        esac
        if [ "$_st_prof_ok" = "1" ]; then
          _st_pass "verb $_st_v passes the selected OCB_PROFILE (finding 49)"
        else
          _st_fail "verb $_st_v did NOT pass the selected OCB_PROFILE (finding 49, rc=$_st_rc)"
        fi
      done

      # ── W3 connection 7: completion contract ──────────────────────────────
      # A receipt with NO per-operation capability record can never complete.
      _st_r1="$_st_dir/r1.json"
      env PATH="$_st_stub_path" GHL_SKILL6_CAPABILITY_JSON="$_st_dir/cap-true.json" \
        "$_st_self" click f1e12 --operation form.create --location loc-test \
        --expect-token 'Saved' --receipt "$_st_r1" >/dev/null 2>&1
      if grep -q '"operation_complete": false' "$_st_r1" 2>/dev/null \
         && grep -q '"prerequisite_ready": true' "$_st_r1" 2>/dev/null; then
        _st_pass "a verb with a blanket (no per-operation) receipt is prerequisite_ready, never complete"
      else
        _st_fail "blanket receipt wrongly reported the operation complete"
      fi

      # With a PER-OPERATION route but no --expect-token, still not complete.
      printf '{"lanes":{"openclaw_managed_browser":{"cliWorks":true}},"operationCapabilities":{"scope":"per-operation+per-connected-location","transports":{"browser":{"routes":["openclaw_managed_browser"],"selectedLane":"openclaw_managed_browser"}}}}' \
        > "$_st_dir/cap-op.json"
      _st_r2="$_st_dir/r2.json"
      env PATH="$_st_stub_path" GHL_SKILL6_CAPABILITY_JSON="$_st_dir/cap-op.json" \
        "$_st_self" open 'https://example.test/ghl' --operation form.create \
        --location loc-test --receipt "$_st_r2" >/dev/null 2>&1
      if grep -q '"operation_complete": false' "$_st_r2" 2>/dev/null; then
        _st_pass "no --expect-token: completion not claimed even with a route"
      else
        _st_fail "completion claimed without local proof"
      fi

      # With a route + a token the stub actually prints -> complete.
      _st_r3="$_st_dir/r3.json"
      env PATH="$_st_stub_path" GHL_SKILL6_CAPABILITY_JSON="$_st_dir/cap-op.json" \
        "$_st_self" open 'https://example.test/ghl' --operation form.create \
        --location loc-test --expect-token 'https://example.test/ghl' \
        --receipt "$_st_r3" >/dev/null 2>&1
      if grep -q '"operation_complete": true' "$_st_r3" 2>/dev/null \
         && grep -q '"operation": "form.create"' "$_st_r3" 2>/dev/null; then
        _st_pass "route + observed token + exit 0 completes the SAME operation"
      else
        _st_fail "real completion proof was not recorded"
      fi

      # click without refreshed refs cannot complete even with the token.
      _st_r4="$_st_dir/r4.json"
      env PATH="$_st_stub_path" GHL_SKILL6_CAPABILITY_JSON="$_st_dir/cap-op.json" \
        "$_st_self" click f1e12 --operation form.create --location loc-test \
        --expect-token 'f1e12' --receipt "$_st_r4" >/dev/null 2>&1
      if grep -q '"references_fresh": false' "$_st_r4" 2>/dev/null \
         && grep -q '"operation_complete": false' "$_st_r4" 2>/dev/null; then
        _st_pass "click without --refresh-snapshot cannot claim completion (stale refs)"
      else
        _st_fail "stale-ref click claimed completion"
      fi

      # stop refuses --all (never close the user's unrelated session).
      _st_out="$(env PATH="$_st_stub_path" GHL_SKILL6_CAPABILITY_JSON="$_st_dir/cap-true.json" \
        "$_st_self" stop --all 2>&1)"
      _st_rc=$?
      if [ "$_st_rc" = "64" ]; then
        _st_pass "stop --all refused (exit 64) — unrelated sessions are never closed"
      else
        _st_fail "stop --all was not refused (rc=$_st_rc)"
      fi

      # stop records the managed tab as released, with closed_all false.
      _st_r5="$_st_dir/r5.json"
      env PATH="$_st_stub_path" GHL_SKILL6_CAPABILITY_JSON="$_st_dir/cap-true.json" \
        "$_st_self" stop --receipt "$_st_r5" >/dev/null 2>&1
      if grep -q '"closed_all": false' "$_st_r5" 2>/dev/null \
         && grep -q '"released": \["tab:' "$_st_r5" 2>/dev/null; then
        _st_pass "stop records only the managed tab as released"
      else
        _st_fail "stop cleanup record wrong"
      fi
    else
      _st_fail "could not create stub openclaw — skipping stub checks"
    fi
    rm -rf "$_st_dir" 2>/dev/null || true
  fi

  if [ "$_st_fails" -eq 0 ]; then
    echo "SELFTEST PASS"
    return 0
  fi
  echo "SELFTEST FAILED: $_st_fails check(s)" >&2
  return 1
}

main "$@"
