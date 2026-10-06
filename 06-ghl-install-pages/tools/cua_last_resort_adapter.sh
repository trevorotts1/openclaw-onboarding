#!/usr/bin/env bash
# cua_last_resort_adapter.sh — v0.1.0
#
# P1-13 (skill6-fix-plan) — CUA / computer-use LAST-RESORT lane adapter.
#
# ── WHAT THIS IS (and is NOT) ─────────────────────────────────────────────────
# This is a CONTRACT wrapper, NOT a working driver. CUA is ABSENT from Skill 6
# paths today (plan 9.1: "CUA / computer-use — Absent from Skill 6 paths today
# — do not document as an existing Skill 6 lane until an adapter is built";
# plan 9.6 lane 5: "CUA — Not in Skill 6 yet — optional future last resort
# only"). Nothing here launches a browser, drives a pointer, or invokes the
# computer tool. The adapter's whole job:
#   (1) read the P0-6 capability receipt (working/skill6-capability.json, the
#       schema tools/capability_probe.py::_probe_cua emits) and answer ONE
#       question honestly: is the CUA/computer lane even present?
#   (2) gate an EXPLICIT operator opt-in (GHL_SKILL6_ALLOW_CUA=1 — NEVER a
#       default) behind that gate and write a waiver receipt when both pass;
#   (3) print the doctrine (verb `note`) so no dispatcher can "helpfully"
#       silent-fall-back into this lane.
# The OPERATOR runs the computer tool manually, with a vision model. This
# adapter never drives the pointer itself and never launches any browser.
#
# ── SCHEMA (coordinated with tools/capability_probe.py _probe_cua) ────────────
#   lanes.cua = { "pluginEnabled": bool, "appPresent": bool,
#                 "driverPresent": bool,
#                 "providerSelected": "cua" | "peekaboo" | "unknown" | "none" }
#   The probe sets providerSelected="cua" only when pluginEnabled AND
#   driverPresent; "peekaboo" when driverPresent alone; "unknown" when the
#   plugin is enabled without a driver; anything else = lane not there. This
#   adapter trusts that schema and fails closed on any deviation.
#
# USAGE
#   bash tools/cua_last_resort_adapter.sh check
#   bash tools/cua_last_resort_adapter.sh request "REASON all CDP lanes failed"
#   bash tools/cua_last_resort_adapter.sh note
#   bash tools/cua_last_resort_adapter.sh --selftest
#
# ENV
#   CUA_CAPABILITY_PATH      — capability JSON to READ (default
#                              <skill>/working/skill6-capability.json). Test
#                              isolation only; production callers never set it.
#   CUA_WAIVER_RECEIPT_PATH  — waiver receipt to WRITE (default
#                              <skill>/working/cua-waiver-receipt.json). Same
#                              test-isolation-only rule (mirrors the
#                              BM_CAPABILITY_RECEIPT_OVERRIDE convention).
#   GHL_SKILL6_ALLOW_CUA=1   — explicit operator opt-in for `request`. The
#                              literal string "1"; anything else (including
#                              unset) is a refusal. NEVER a default.
#
# EXIT CODES
#   0   check: gate satisfied ('cua available') | request: gate + opt-in OK,
#       waiver receipt written and verified | note | --selftest pass
#   1   --selftest failed (contract regression), or `request` could not write
#       the waiver receipt (never claim REQUESTED without the receipt)
#   2   cua-unavailable — capability JSON missing/unreadable/malformed, or the
#       lanes.cua gate (pluginEnabled AND driverPresent AND providerSelected
#       in {cua,peekaboo}) is not satisfied. FAIL-CLOSED: no receipt on 2.
#   3   cua-ambiguous — pluginEnabled true but providerSelected is not
#       cua/peekaboo (unknown/absent/garbage). NEVER guessed. FAIL-CLOSED:
#       no receipt on 3.
#   64  usage error (unknown verb; `request` without exactly ONE quoted REASON)
#   75  request refused on POLICY: GHL_SKILL6_ALLOW_CUA != 1 — CUA is never
#       the default lane (plan 2.2: "Never silently jump to CUA for normal
#       GHL builds"). No receipt on 75.
#
# DOCTRINE (printed in full by `note`):
#   - CUA is NEVER the default lane. Lane 5 of the 9.6 table, reached ONLY
#     when ALL CDP/browser lanes failed (agent_browser, managed browser,
#     playwright_direct) or for an explicit hard-UI / cross-origin pixel need.
#   - The provider NEVER silent-falls-back per action: a CUA failure is NOT a
#     Peekaboo retry. One provider per operation; own the failure.
#   - `browser_prepare` launches a driver-owned Chromium with an ephemeral
#     isolated profile — it does NOT attach to the user's existing Chrome.
#   - Requires a VISION model; the operator runs the tool manually.
#
# PORTABILITY: macOS bash 3.2-safe (no associative arrays, no mapfile, no
#   ${var,,}), POSIX grep/sed/tr only, NO `set -e` (browser_manager.sh
#   doctrine: sourcing/must not clobber caller options — explicit return-code
#   checks only), reads NO secret env, does NO network, launches NO browser.

CUA_ADAPTER_VERSION="v0.1.0"

_CUA_SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
_CUA_SKILL_DIR="$(cd "${_CUA_SELF_DIR}/.." 2>/dev/null && pwd)"

# ── paths (overridable for tests; production callers never set these) ─────────
cua_capability_path() {
  printf '%s' "${CUA_CAPABILITY_PATH:-${_CUA_SKILL_DIR}/working/skill6-capability.json}"
}
cua_receipt_path() {
  printf '%s' "${CUA_WAIVER_RECEIPT_PATH:-${_CUA_SKILL_DIR}/working/cua-waiver-receipt.json}"
}

# ── _cua_block_val BLOCK FIELD — raw value token of FIELD inside a pretty-
# printed JSON object block, or empty when absent (fail-closed upstream).
# POSIX grep/sed only; handles the probe's indent-2 dumps and a trailing comma.
_cua_block_val() {
  printf '%s\n' "$1" | grep "\"$2\"[[:space:]]*:" 2>/dev/null | head -n 1 \
    | sed 's/^[^:]*:[[:space:]]*//; s/[[:space:]]*,[[:space:]]*$//; s/[[:space:]]*$//'
}

# ── _cua_gate — the ONE capability gate shared by check and request.
# Reads the capability JSON, extracts lanes.cua, decides:
#   return 0 + _CUA_GATE_PROVIDER set  → available (cua | peekaboo)
#   return 2 (cua-unavailable)         → missing/unreadable/malformed/gate-false
#   return 3 (cua-ambiguous)           → pluginEnabled but provider unknown
# Never writes anything. Never launches anything.
_cua_gate() {
  _CUA_GATE_PROVIDER=""
  local cap_path block plugin driver provider
  cap_path="$(cua_capability_path)"
  if [ ! -f "$cap_path" ]; then
    echo "cua-unavailable: capability JSON not found at ${cap_path} — run the P0-6 capability probe first" >&2
    return 2
  fi
  # Extract the lanes.cua object block from the pretty-printed probe dump.
  # The cua object holds only scalars, so the first closing line ends it.
  block="$(sed -n '/^[[:space:]]*"cua":[[:space:]]*{/,/^[[:space:]]*}[[:space:]]*,\{0,1\}[[:space:]]*$/p' "$cap_path" 2>/dev/null)"
  if [ -z "$block" ]; then
    echo "cua-unavailable: no lanes.cua object found in ${cap_path} — capability schema drift or malformed JSON; failing closed" >&2
    return 2
  fi
  plugin="$( _cua_block_val "$block" pluginEnabled )"
  driver="$( _cua_block_val "$block" driverPresent )"
  provider="$( _cua_block_val "$block" providerSelected | sed 's/^"//; s/"$//' )"
  # Ambiguous FIRST (plan contract): plugin-enabled but the probe could not
  # name a usable provider — never guess between CUA and Peekaboo.
  if [ "$plugin" = "true" ] && [ "$provider" != "cua" ] && [ "$provider" != "peekaboo" ]; then
    echo "cua-ambiguous: lanes.cua pluginEnabled=true but providerSelected='${provider:-<absent>}' — provider unknown, never guessed; fix the box or the probe schema" >&2
    return 3
  fi
  if [ "$plugin" = "true" ] && [ "$driver" = "true" ] && { [ "$provider" = "cua" ] || [ "$provider" = "peekaboo" ]; }; then
    _CUA_GATE_PROVIDER="$provider"
    return 0
  fi
  echo "cua-unavailable: lanes.cua gate not satisfied (pluginEnabled=${plugin:-<absent>} driverPresent=${driver:-<absent>} providerSelected='${provider:-<absent>}') — CUA lane not usable on this box" >&2
  return 2
}

# ── verb: check ────────────────────────────────────────────────────────────────
# Exit 0 'cua available' | 2 'cua-unavailable' | 3 'cua-ambiguous' (see header).
cmd_check() {
  _cua_gate
  _cua_check_rc=$?
  if [ "$_cua_check_rc" -eq 0 ]; then
    echo "cua available: provider=$_CUA_GATE_PROVIDER (lane-5 gate only — CUA is never the default; run 'note' for the doctrine)"
  fi
  return "$_cua_check_rc"
}

# ── verb: note — the doctrine, verbatim, so it is greppable in logs ───────────
cmd_note() {
  cat <<'CUA_DOCTRINE'
CUA LANE DOCTRINE (plan 2.2 + 9.6 lane 5; CUA is NOT wired in Skill 6 today — this adapter is a contract, not a driver):
  1. CUA is NEVER the default lane. It is reached ONLY when ALL CDP/browser lanes failed (agent_browser, openclaw_managed_browser, playwright_direct) or for an explicit hard-UI / cross-origin pixel need.
  2. The provider NEVER silent-falls-back per action: a CUA failure is NOT a Peekaboo retry. One provider per operation; own the failure.
  3. browser_prepare launches a driver-owned Chromium with an ephemeral isolated profile — it does NOT attach to the user's existing Chrome profile.
  4. A VISION model is required. The operator runs the computer tool manually; this adapter never drives the pointer itself.
  5. Opt-in is explicit: GHL_SKILL6_ALLOW_CUA=1 on `request`, plus a passing capability gate; a waiver receipt is written to working/cua-waiver-receipt.json. No receipt, no CUA.
CUA_DOCTRINE
  return 0
}

# ── verb: request REASON — gated opt-in + waiver receipt ──────────────────────
# Contract: gate must pass (exit 0) AND GHL_SKILL6_ALLOW_CUA must be exactly 1.
# Writes working/cua-waiver-receipt.json then prints the REQUESTED line. Any
# refusal (gate 2/3, policy 75, write failure 1) writes NO receipt.
cmd_request() {
  if [ "$#" -ne 1 ] || [ -z "$1" ]; then
    echo "usage: cua_last_resort_adapter.sh request \"<REASON — one quoted argument explaining why ALL CDP lanes failed>\"" >&2
    return 64
  fi
  local reason="$1"
  _cua_gate
  local gate_rc=$?
  if [ "$gate_rc" -ne 0 ]; then
    echo "CUA request REFUSED: capability gate failed (rc=${gate_rc}). No waiver receipt written." >&2
    return "$gate_rc"
  fi
  if [ "${GHL_SKILL6_ALLOW_CUA:-}" != "1" ]; then
    echo "CUA request REFUSED: GHL_SKILL6_ALLOW_CUA is not set to 1 — CUA is never the default lane; explicit operator opt-in required. No waiver receipt written." >&2
    return 75
  fi
  local provider requested_at receipt_path safe_reason
  provider="$_CUA_GATE_PROVIDER"
  requested_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null)"
  [ -z "$requested_at" ] && requested_at="unknown"
  receipt_path="$(cua_receipt_path)"
  # JSON-safe the reason: newlines/tabs/CRs become spaces, then escape
  # backslashes first and double-quotes second (sed applies in order per line).
  safe_reason="$(printf '%s' "$reason" | tr '\t\r\n' '   ' | sed 's/\\/\\\\/g; s/"/\\"/g')"
  mkdir -p "$(dirname "$receipt_path")" 2>/dev/null
  printf '{\n  "requestedAt": "%s",\n  "reason": "%s",\n  "providerSelected": "%s",\n  "lane": "cua_last_resort",\n  "requiresVisionModel": true\n}\n' \
    "$requested_at" "$safe_reason" "$provider" > "$receipt_path" 2>/dev/null
  if [ ! -s "$receipt_path" ]; then
    echo "CUA request FAILED: could not write the waiver receipt at ${receipt_path}. Nothing was requested." >&2
    return 1
  fi
  echo "CUA REQUESTED — operator must run the computer tool manually with a vision model; adapter never drives the pointer itself"
  echo "waiver receipt: $receipt_path"
  return 0
}

# ── waiver-receipt validity helper (offline; python3 when present) ────────────
_cua_receipt_valid_json() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$1" >/dev/null 2>&1
  else
    # No python3 on PATH: structural best-effort check (never a fake pass —
    # the caller still requires every literal key token below).
    head -c 1 "$1" 2>/dev/null | grep -q '{' && \
      grep -q '"requiresVisionModel": true' "$1" && \
      grep -q '"lane": "cua_last_resort"' "$1" && \
      grep -q '"requestedAt"' "$1" && \
      grep -q '"reason"' "$1" && \
      grep -q '"providerSelected"' "$1"
  fi
}

# ── --selftest — fully OFFLINE contract test (PATH-simulation via the
# CUA_CAPABILITY_PATH / CUA_WAIVER_RECEIPT_PATH overrides; no capability file
# needed, no browser, no network, no secrets). Exit 0 on pass, 1 on any fail.
_cua_selftest() {
  _cua_tmp="$(mktemp -d "${TMPDIR:-/tmp}/cua-adapter-selftest.XXXXXX")" || {
    echo "FAIL: selftest could not create a tmp dir" >&2; return 1; }
  trap 'rm -rf "$_cua_tmp"' EXIT
  _cua_errors=0
  _cua_fail() { echo "  FAIL: $1" >&2; _cua_errors=$((_cua_errors + 1)); }

  # Fake capability JSON in the REAL probe schema (capability_probe._probe_cua).
  _cua_mkcap() { # plugin driver provider
    printf '{\n  "probedAt": "2026-09-07T00:00:00Z",\n  "lanes": {\n    "cua": {\n      "pluginEnabled": %s,\n      "appPresent": %s,\n      "driverPresent": %s,\n      "providerSelected": "%s"\n    }\n  }\n}\n' \
      "$1" "$1" "$2" "$3" > "${_cua_tmp}/cap-$1-$2-$3.json"
    printf '%s' "${_cua_tmp}/cap-$1-$2-$3.json"
  }

  # 1. No capability file -> check exits 2 (cua-unavailable), token on stderr.
  CUA_CAPABILITY_PATH="${_cua_tmp}/absent.json"
  CUA_WAIVER_RECEIPT_PATH="${_cua_tmp}/r1.json"
  cmd_check 2>"${_cua_tmp}/err1" >/dev/null; rc=$?
  [ "$rc" -eq 2 ] || _cua_fail "absent capability file: expected rc 2, got ${rc}"
  grep -q 'cua-unavailable' "${_cua_tmp}/err1" || _cua_fail "absent file: no cua-unavailable token on stderr"
  [ ! -e "${_cua_tmp}/r1.json" ] || _cua_fail "absent file: a receipt was written (must never happen on check)"

  # 2. Probe-schema cua with plugin OFF -> 2.
  cap="$( _cua_mkcap false false none )"
  CUA_CAPABILITY_PATH="$cap"; CUA_WAIVER_RECEIPT_PATH="${_cua_tmp}/r2.json"
  cmd_check 2>"${_cua_tmp}/err2" >/dev/null; rc=$?
  [ "$rc" -eq 2 ] || _cua_fail "plugin-off box: expected rc 2, got ${rc}"
  grep -q 'cua-unavailable' "${_cua_tmp}/err2" || _cua_fail "plugin-off: missing cua-unavailable token"

  # 3. Schema drift: JSON with NO lanes.cua at all -> 2 (fail-closed).
  printf '{\n  "lanes": {}\n}\n' > "${_cua_tmp}/cap-nocua.json"
  CUA_CAPABILITY_PATH="${_cua_tmp}/cap-nocua.json"
  cmd_check 2>"${_cua_tmp}/err3" >/dev/null; rc=$?
  [ "$rc" -eq 2 ] || _cua_fail "schema drift (no lanes.cua): expected rc 2, got ${rc}"

  # 4. Ambiguous: plugin enabled, provider unknown -> 3, never guessed.
  cap="$( _cua_mkcap true false unknown )"
  CUA_CAPABILITY_PATH="$cap"
  cmd_check 2>"${_cua_tmp}/err4" >/dev/null; rc=$?
  [ "$rc" -eq 3 ] || _cua_fail "provider-unknown plugin-on: expected rc 3, got ${rc}"
  grep -q 'cua-ambiguous' "${_cua_tmp}/err4" || _cua_fail "ambiguous: missing cua-ambiguous token"

  # 5. Available: plugin+driver+provider=cua -> 0, 'cua available' on stdout.
  cap="$( _cua_mkcap true true cua )"
  CUA_CAPABILITY_PATH="$cap"
  cmd_check 2>/dev/null >"${_cua_tmp}/out5"; rc=$?
  [ "$rc" -eq 0 ] || _cua_fail "cua provider: expected rc 0, got ${rc}"
  grep -q 'cua available' "${_cua_tmp}/out5" || _cua_fail "cua provider: missing 'cua available' token on stdout"

  # 6. Available via Peekaboo driver (no CUA plugin provider) -> 0.
  cap="$( _cua_mkcap true true peekaboo )"
  CUA_CAPABILITY_PATH="$cap"
  cmd_check 2>/dev/null >/dev/null; rc=$?
  [ "$rc" -eq 0 ] || _cua_fail "peekaboo driver: expected rc 0, got ${rc}"

  # 7. driverPresent false with provider cua -> 2 (gate needs BOTH).
  cap="$( _cua_mkcap true false cua )"
  CUA_CAPABILITY_PATH="$cap"
  cmd_check 2>/dev/null >/dev/null; rc=$?
  [ "$rc" -eq 2 ] || _cua_fail "driver-missing: expected rc 2, got ${rc}"

  # 8. request WITHOUT the opt-in env -> refused 75, NO receipt.
  CUA_CAPABILITY_PATH="$( _cua_mkcap true true cua )"
  CUA_WAIVER_RECEIPT_PATH="${_cua_tmp}/r8.json"
  GHL_SKILL6_ALLOW_CUA="" cmd_request "test reason" 2>"${_cua_tmp}/err8" >/dev/null; rc=$?
  [ "$rc" -eq 75 ] || _cua_fail "request without opt-in: expected rc 75, got ${rc}"
  [ ! -e "${_cua_tmp}/r8.json" ] || _cua_fail "request without opt-in wrote a receipt (policy violation)"
  grep -q 'GHL_SKILL6_ALLOW_CUA' "${_cua_tmp}/err8" || _cua_fail "opt-in refusal must name GHL_SKILL6_ALLOW_CUA"

  # 9. request WITH opt-in + passing gate -> receipt written, valid JSON,
  #    every contract field present, REQUESTED line printed.
  CUA_WAIVER_RECEIPT_PATH="${_cua_tmp}/r9.json"
  GHL_SKILL6_ALLOW_CUA=1 cmd_request "selftest: all CDP lanes failed" 2>/dev/null >"${_cua_tmp}/out9"; rc=$?
  [ "$rc" -eq 0 ] || _cua_fail "gated request: expected rc 0, got ${rc}"
  [ -s "${_cua_tmp}/r9.json" ] || _cua_fail "gated request: waiver receipt missing/empty"
  _cua_receipt_valid_json "${_cua_tmp}/r9.json" || _cua_fail "waiver receipt is not valid JSON"
  grep -q '"lane": "cua_last_resort"' "${_cua_tmp}/r9.json" || _cua_fail "receipt missing lane=cua_last_resort"
  grep -q '"requiresVisionModel": true' "${_cua_tmp}/r9.json" || _cua_fail "receipt missing requiresVisionModel=true"
  grep -q '"providerSelected": "cua"' "${_cua_tmp}/r9.json" || _cua_fail "receipt missing providerSelected=cua"
  grep -q '"requestedAt"' "${_cua_tmp}/r9.json" || _cua_fail "receipt missing requestedAt"
  grep -q 'CUA REQUESTED' "${_cua_tmp}/out9" || _cua_fail "gated request did not print the CUA REQUESTED line"

  # 10. request WITH opt-in but FAILING gate -> 2, NO receipt.
  CUA_CAPABILITY_PATH="$( _cua_mkcap false false none )"
  CUA_WAIVER_RECEIPT_PATH="${_cua_tmp}/r10.json"
  GHL_SKILL6_ALLOW_CUA=1 cmd_request "test reason" 2>/dev/null >/dev/null; rc=$?
  [ "$rc" -eq 2 ] || _cua_fail "request on unavailable box: expected rc 2, got ${rc}"
  [ ! -e "${_cua_tmp}/r10.json" ] || _cua_fail "request on unavailable box wrote a receipt (fail-closed violation)"

  # 11. request without a REASON -> usage 64.
  CUA_CAPABILITY_PATH="$( _cua_mkcap true true cua )"
  GHL_SKILL6_ALLOW_CUA=1 cmd_request 2>/dev/null >/dev/null; rc=$?
  [ "$rc" -eq 64 ] || _cua_fail "request without REASON: expected rc 64, got ${rc}"

  # 12. note prints the doctrine tokens.
  cmd_note >"${_cua_tmp}/out12" 2>/dev/null; rc=$?
  [ "$rc" -eq 0 ] || _cua_fail "note: expected rc 0, got ${rc}"
  for token in "NEVER the default" "ALL CDP/browser lanes failed" "NOT a Peekaboo retry" "ephemeral" "does NOT attach" "VISION model"; do
    grep -q "$token" "${_cua_tmp}/out12" || _cua_fail "note missing doctrine token: ${token}"
  done

  # 13. NO browser launch ever: no non-comment line may invoke a browser binary.
  #     (Scan the code EXCLUDING this selftest's own token list line — the
  #     assertion strings themselves are the only legitimate occurrences.)
  _cua_code="$(grep -v '^[[:space:]]*#' "$0" 2>/dev/null | grep -v '^[[:space:]]*for token in')"
  for token in 'agent-browser' 'connect_over_cdp' 'connect-over-cdp'; do
    if printf '%s\n' "$_cua_code" | grep -q "$token"; then
      _cua_fail "script code references ${token} (adapter must never drive a browser)"
    fi
  done

  if [ "$_cua_errors" -ne 0 ]; then
    echo "[selftest] FAIL — ${_cua_errors} error(s)" >&2
    return 1
  fi
  echo "[selftest] PASS — CUA last-resort contract: gate matrix (absent/2, plugin-off/2, schema-drift/2, ambiguous/3, cua/0, peekaboo/0, driver-missing/2), opt-in refusal 75 with no receipt, waiver receipt written + valid JSON with all contract fields, doctrine printed, no browser tokens in code (offline; no capability file, no browser, no network)"
  return 0
}

# ── usage ──────────────────────────────────────────────────────────────────────
_cua_usage() {
  echo "usage: cua_last_resort_adapter.sh {check|request <REASON>|note|--selftest}" >&2
  echo "  check            — capability gate: 0 'cua available' | 2 'cua-unavailable' | 3 'cua-ambiguous'" >&2
  echo "  request <REASON> — gate pass AND GHL_SKILL6_ALLOW_CUA=1 required; writes the waiver receipt; NEVER default" >&2
  echo "  note             — print the CUA lane doctrine" >&2
  echo "  --selftest       — offline contract self-test (no capability file, no browser, no network)" >&2
  return 64
}

# ── standalone verb dispatch (only when executed, not sourced) ────────────────
if [ "${BASH_SOURCE[0]:-$0}" = "$0" ]; then
  _cua_verb="${1:-}"
  if [ "$#" -gt 0 ]; then
    shift 2>/dev/null
  fi
  case "$_cua_verb" in
    check)      cmd_check; exit $? ;;
    request)    cmd_request "$@"; exit $? ;;
    note)       cmd_note; exit $? ;;
    --selftest) _cua_selftest; exit $? ;;
    *)          _cua_usage; exit 64 ;;
  esac
fi