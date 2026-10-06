#!/usr/bin/env bash
# shared-utils/oc-env-descriptor.sh
# ============================================================================
# THE environment descriptor — ONE place that decides WHICH box this is, WHERE
# its state lives, WHICH service/container is the approved gateway target, and
# whether that gateway is APP-READY (not merely "container Up" or "process
# once exited 0").
#
# WHY THIS EXISTS (RR-029 / RCV-07):
#   Every diagnostic used to re-derive its own target. rr-triage.sh's `_oc_root`
#   missed the advertised Contabo layout; STEP 1 took the FIRST launchctl label
#   containing "openclaw" (the operator box carries 8 of them: two gateway
#   tunnels, node, watchdog, rescue-receiver, loop-watchdog, ...) and called any
#   parsed non-78 exit CLEAN without proving an active process; STEP 1's docker
#   branch took the first `--filter name=openclaw` match, which on a host that
#   also runs client containers can be a NEIGHBOUR's container. STEP 2/5 opened
#   whichever sqlite file existed first — including a 0-byte `openclaw.sqlite`
#   that `sqlite3 ... "select 1;"` happily "opens". Result: false CLEAN.
#
# CONTRACT
#   * READ-ONLY. Every probe here reads; nothing is written, restarted, or
#     chowned. No host-wide scan of /opt/clients or /var/lib/docker is ever
#     performed — the Contabo path is only entered through an EXPLICIT target
#     (OC_TARGET_BOX), so a diagnostic can never enumerate neighbours.
#   * EXACTLY ONE TARGET, never first-match. The launchd label and the docker
#     container name are exact strings; an absent or ambiguous target is
#     reported as such (and callers must turn that into UNDETERMINED, never
#     CLEAN).
#   * UNKNOWN IS A FIRST-CLASS RESULT. `ocd_state_db` records WHY each candidate
#     was rejected; `ocd_app_ready` returns ready/not-ready/undetermined and
#     never guesses a positive.
#   * Fixtures address state through OC_CONFIG_ROOT / OC_STATE_DB / OC_LOG_ROOT
#     (RR-030: HOME is never repurposed).
#
# SOURCED, never executed. Sets OCD_* globals and defines ocd_* functions.
# Compatible with bash 3.2 (no associative arrays, no ${var,,}).
# ============================================================================
[ -n "${_OC_ENV_DESCRIPTOR_LOADED:-}" ] && return 0 2>/dev/null || true
_OC_ENV_DESCRIPTOR_LOADED=1

# ---- resolved descriptor state (populated by ocd_init) ---------------------
OCD_ROOT=""; OCD_ROOT_SOURCE=""; OCD_JSON=""; OCD_JSON_STATE=""; OCD_LOG_DIR=""
OCD_DB=""; OCD_DB_SOURCE=""; OCD_DB_NOTE=""
OCD_LOG_NOTE=""
OCD_BOX_SLUG=""; OCD_BOX_SOURCE=""; OCD_COMPANY_SLUG=""; OCD_COMPANY_NAME=""; OCD_COMPANY_SOURCE=""
OCD_PLATFORM=""; OCD_TARGET_MODE=""; OCD_TARGET_ID=""; OCD_TARGET_NOTE=""
OCD_GATEWAY_PORT=""; OCD_GATEWAY_PORT_SOURCE=""
OCD_READY=""; OCD_READY_DETAIL=""
OCD_QRY_RC=0; OCD_QRY_OUT=""; OCD_QRY_ERR=""

# ---------------------------------------------------------------------------
# Root. Priority: explicit fixture/operator override first (RR-030 contract,
# unchanged from the pre-RR-029 `_oc_root`), then the platform-canonical roots.
# The Contabo layout (/opt/clients/<box>/data/config) is reachable ONLY through
# an explicit OC_TARGET_BOX — we never glob /opt/clients, because on a host
# running several clients that would pick a neighbour's tree (RCV-07).
# ---------------------------------------------------------------------------
ocd_root() {
  if [ -n "${OC_CONFIG_ROOT:-}" ]; then
    OCD_ROOT="$OC_CONFIG_ROOT"; OCD_ROOT_SOURCE="OC_CONFIG_ROOT"; return 0
  fi
  if [ -n "${OC_TARGET_BOX:-}" ]; then
    # Explicit target only. Reads the box's config DIRECTORY (the dir that holds
    # openclaw.json), which is what every reader below expects of a root.
    local cand="/opt/clients/${OC_TARGET_BOX}/data/config"
    if [ -f "$cand/openclaw.json" ]; then
      OCD_ROOT="$cand"; OCD_ROOT_SOURCE="OC_TARGET_BOX=/opt/clients/${OC_TARGET_BOX}/data/config"; return 0
    fi
    local cand2="/opt/clients/${OC_TARGET_BOX}/data/.openclaw"
    if [ -f "$cand2/openclaw.json" ]; then
      OCD_ROOT="$cand2"; OCD_ROOT_SOURCE="OC_TARGET_BOX=/opt/clients/${OC_TARGET_BOX}/data/.openclaw"; return 0
    fi
    OCD_ROOT=""; OCD_ROOT_SOURCE="OC_TARGET_BOX set but no config at /opt/clients/${OC_TARGET_BOX}/data/{config,.openclaw}"
    return 1
  fi
  if [ -d /data/.openclaw ]; then
    OCD_ROOT="/data/.openclaw"; OCD_ROOT_SOURCE="/data/.openclaw"; return 0
  fi
  if [ -d "${HOME:-}/.openclaw" ]; then
    OCD_ROOT="${HOME}/.openclaw"; OCD_ROOT_SOURCE="\$HOME/.openclaw"; return 0
  fi
  OCD_ROOT=""; OCD_ROOT_SOURCE="no root (no /data/.openclaw, no \$HOME/.openclaw)"
  return 1
}

ocd_json_path() {
  [ -n "$OCD_ROOT" ] || ocd_root || true
  [ -n "$OCD_ROOT" ] || return 1
  printf '%s/openclaw.json' "$OCD_ROOT"
}

# ---------------------------------------------------------------------------
# State DB. The pre-RR-029 candidate list ended with $HOME/.openclaw/openclaw.sqlite
# and validated with `select 1;`, which SUCCEEDS on a 0-byte file — the operator
# box carries exactly such a 0-byte decoy. A candidate is accepted only when it
# is non-empty AND its sqlite_master actually lists tables.
# ---------------------------------------------------------------------------
ocd_state_db() {
  local cands="" c rc n note=""
  if [ -n "${OC_STATE_DB:-}" ]; then cands="$OC_STATE_DB"; fi
  if [ -n "$OCD_ROOT" ]; then
    cands="$cands $OCD_ROOT/state/openclaw.sqlite $OCD_ROOT/state.sqlite $OCD_ROOT/data/openclaw.sqlite $OCD_ROOT/data/state.sqlite $OCD_ROOT/openclaw.sqlite"
  fi
  for c in $cands; do
    if [ ! -e "$c" ]; then note="${note}${note:+, }$(basename "$(dirname "$c")")/$(basename "$c"):missing"; continue; fi
    if [ ! -f "$c" ]; then note="${note}${note:+, }$c:not-a-file"; continue; fi
    if [ ! -s "$c" ]; then note="${note}${note:+, }$c:zero-bytes"; continue; fi
    if [ ! -r "$c" ]; then note="${note}${note:+, }$c:not-readable"; continue; fi
    if ! command -v sqlite3 >/dev/null 2>&1; then note="${note}${note:+, }sqlite3-not-on-PATH"; break; fi
    n="$(sqlite3 -readonly "$c" "select count(*) from sqlite_master;" 2>&1)"; rc=$?
    if [ "$rc" -ne 0 ]; then note="${note}${note:+, }$c:open-failed"; continue; fi
    case "$n" in ''|*[!0-9]*) note="${note}${note:+, }$c:unreadable-schema"; continue ;; esac
    if [ "$n" -eq 0 ]; then note="${note}${note:+, }$c:no-tables"; continue; fi
    OCD_DB="$c"; OCD_DB_SOURCE="$( [ -n "${OC_STATE_DB:-}" ] && [ "$c" = "$OC_STATE_DB" ] && printf 'OC_STATE_DB' || printf 'root-candidate' )"
    OCD_DB_NOTE="accepted=$c (tables=$n)${note:+; rejected: $note}"
    return 0
  done
  OCD_DB=""; OCD_DB_SOURCE="none"
  OCD_DB_NOTE="no usable state db${note:+; rejected: $note}"
  return 1
}

# Checked query helper. Never lets a failed query masquerade as an empty result:
# callers must consult ocd_qry_rc. Mirrors the RR-030 doctrine that a broken
# instrument is not a zero.
ocd_qry() {
  local sql="$1"
  OCD_QRY_OUT=""; OCD_QRY_ERR=""; OCD_QRY_RC=0
  if [ -z "$OCD_DB" ]; then OCD_QRY_RC=2; OCD_QRY_ERR="no state db resolved"; return 2; fi
  if ! command -v sqlite3 >/dev/null 2>&1; then OCD_QRY_RC=2; OCD_QRY_ERR="sqlite3 not on PATH"; return 2; fi
  OCD_QRY_OUT="$(sqlite3 -readonly "$OCD_DB" "$sql" 2>&1)"; OCD_QRY_RC=$?
  if [ "$OCD_QRY_RC" -ne 0 ]; then
    OCD_QRY_ERR="$(printf '%s' "$OCD_QRY_OUT" | tr '\n' ' ' | sed 's/  */ /g')"
    OCD_QRY_OUT=""
  fi
  return "$OCD_QRY_RC"
}

# Table + column presence, so "absent" and "empty" are never confused.
ocd_table_present() {  # ocd_table_present <table>
  local t="$1" n
  n="$(sqlite3 -readonly "$OCD_DB" "select count(*) from sqlite_master where type='table' and name='$t';" 2>/dev/null)" || return 2
  [ "$n" = "1" ]
}

ocd_missing_columns() {  # ocd_missing_columns <table> <col>... -> prints missing cols
  local t="$1"; shift
  local cols out="" c
  cols="$(sqlite3 -readonly "$OCD_DB" "pragma table_info($t);" 2>/dev/null | cut -d'|' -f2)" || return 2
  for c in "$@"; do
    printf '%s\n' "$cols" | grep -qx -- "$c" || out="$out$c,"
  done
  printf '%s' "${out%,}"
}

# ---------------------------------------------------------------------------
# Identity — canonical box slug + company. OpenClaw convention (update-skills.sh
# FLEET-STANDING-GATE-V1, apply-fleet-standards.sh): env var first, then
# openclaw.json env.vars, then the short hostname. The secrets store is never
# read here.
# ---------------------------------------------------------------------------
ocd_identity() {
  local slug="" comp="" cname=""
  slug="${OC_BOX_SLUG:-${FLEET_STANDING_BOX_SLUG:-}}"
  [ -n "$slug" ] && OCD_BOX_SOURCE="env" || OCD_BOX_SOURCE=""
  if [ -z "$slug" ] && [ -f "$OCD_JSON" ]; then
    slug="$(python3 - "$OCD_JSON" <<'SLUGPY' 2>/dev/null || true
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    print((((d.get("env") or {}).get("vars") or {}).get("FLEET_STANDING_BOX_SLUG", "") or "").strip())
except Exception:
    print("")
SLUGPY
)"
    [ -n "$slug" ] && OCD_BOX_SOURCE="openclaw.json:env.vars.FLEET_STANDING_BOX_SLUG"
  fi
  if [ -z "$slug" ]; then
    slug="$(hostname -s 2>/dev/null || true)"
    [ -n "$slug" ] && OCD_BOX_SOURCE="hostname -s (degraded: box slug not seeded)"
  fi
  OCD_BOX_SLUG="${slug:-unknown}"
  [ -n "$OCD_BOX_SOURCE" ] || OCD_BOX_SOURCE="unresolved"

  comp="${COMPANY_SLUG:-}"
  if [ -n "$comp" ]; then OCD_COMPANY_SOURCE="env"; fi
  if [ -z "$comp" ] && [ -n "$OCD_ROOT" ] && [ -f "$OCD_ROOT/workspace/company-config.json" ]; then
    comp="$(python3 - "$OCD_ROOT/workspace/company-config.json" <<'COMPY' 2>/dev/null || true
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    print(""); raise SystemExit(0)
slug = (d.get("slug") or "").strip()
name = (d.get("companyName") or d.get("name") or "").strip()
print("%s\t%s" % (slug, name))
COMPY
)"
    if [ -n "$comp" ]; then
      cname="${comp#*$'\t'}"; comp="${comp%%$'\t'*}"
      OCD_COMPANY_SOURCE="workspace/company-config.json"
    fi
  fi
  OCD_COMPANY_SLUG="${comp:-unknown}"
  OCD_COMPANY_NAME="${cname:-}"
  [ -n "$OCD_COMPANY_SOURCE" ] || OCD_COMPANY_SOURCE="unresolved"
}

# Bounded external call: `openclaw gateway status` is on the port-resolution
# fallback path, and a diagnostic must never hang on a wedged CLI. Prefers a
# real timeout(1); degrades to a bare call when none exists (macOS without
# coreutils) rather than inventing a failure.
_ocd_bounded() {
  if command -v timeout >/dev/null 2>&1; then timeout 5 "$@"; return $?; fi
  if command -v gtimeout >/dev/null 2>&1; then gtimeout 5 "$@"; return $?; fi
  "$@"
}

# The identity prefix EVERY diagnostic line carries (RR-029: "Include canonical
# box/company in every diagnostic").
ocd_identity_prefix() { printf '[box=%s company=%s]' "$OCD_BOX_SLUG" "$OCD_COMPANY_SLUG"; }

# ---------------------------------------------------------------------------
# Platform + the ONE exact service/container target.
# ---------------------------------------------------------------------------
ocd_platform() {
  if [ -n "${OC_PLATFORM:-}" ]; then OCD_PLATFORM="$OC_PLATFORM"; return 0; fi
  if [ -d /data/.openclaw ]; then
    if command -v docker >/dev/null 2>&1 && [ "${OC_IN_CONTAINER:-0}" != "1" ]; then
      OCD_PLATFORM="vps-host"
    else
      OCD_PLATFORM="vps-container"
    fi
    return 0
  fi
  case "$(uname -s 2>/dev/null)" in
    Darwin) OCD_PLATFORM="mac" ;;
    *)      OCD_PLATFORM="unknown" ;;
  esac
}

# Exact launchd label for the gateway. NOT a substring match over `launchctl
# list` — the operator box carries eight labels containing "openclaw".
ocd_service_label() {
  printf '%s' "${OC_SERVICE_LABEL:-${GATEWAY_WATCHDOG_LABEL:-ai.openclaw.gateway}}"
}

# Exact docker container name. NOT `--filter name=openclaw | head -1`.
ocd_container_name() {
  if [ -n "${OC_CONTAINER:-}" ]; then printf '%s' "$OC_CONTAINER"; return 0; fi
  if [ -n "${OCD_ROOT:-}" ] && [ "$OCD_ROOT" = "/data/.openclaw" ]; then printf '%s' "openclaw"; return 0; fi
  printf '%s' "${OPENCLAW_CONTAINER_NAME:-openclaw}"
}

ocd_target() {
  local label cname
  label="$(ocd_service_label)"; cname="$(ocd_container_name)"
  case "${OC_TARGET_MODE:-}" in
    launchd|docker|process)
      OCD_TARGET_MODE="$OC_TARGET_MODE"
      [ "$OCD_TARGET_MODE" = "launchd" ] && OCD_TARGET_ID="$label" || OCD_TARGET_ID="$cname"
      OCD_TARGET_NOTE="OC_TARGET_MODE override"
      return 0 ;;
  esac
  case "$OCD_PLATFORM" in
    mac)
      OCD_TARGET_MODE="launchd"; OCD_TARGET_ID="$label"
      OCD_TARGET_NOTE="mac LaunchAgent (exact label)" ;;
    vps-host)
      OCD_TARGET_MODE="docker"; OCD_TARGET_ID="$cname"
      OCD_TARGET_NOTE="docker host (exact container name; no name-scan)" ;;
    vps-container)
      OCD_TARGET_MODE="process"; OCD_TARGET_ID="openclaw-gateway"
      OCD_TARGET_NOTE="inside container: no docker CLI — process + HTTP readiness only" ;;
    *)
      OCD_TARGET_MODE="unknown"; OCD_TARGET_ID=""
      OCD_TARGET_NOTE="platform unresolved — no approved service/container identity" ;;
  esac
}

# ---------------------------------------------------------------------------
# Gateway port (descriptor-owned, so every consumer agrees). Order: explicit
# override, watchdog/tunnel env, openclaw.json gateway.port, `openclaw gateway
# status` Listening, PORT/OPENCLAW_PORT, then 18789.
# ---------------------------------------------------------------------------
ocd_gateway_port() {
  local p
  # Memoized: the fallback below shells `openclaw gateway status` (measured
  # ~4.5s here) and callers such as the triage self-test call ocd_init many
  # times in one process. Re-resolves only when the override itself changes.
  if [ "${OCD_PORT_MEMO_KEY:-\x00}" = "${OC_GATEWAY_PORT:-\x00}${GATEWAY_WATCHDOG_PORT:-\x00}${TGHC_GATEWAY_PORT:-\x00}" ] && [ -n "$OCD_GATEWAY_PORT" ]; then
    return 0
  fi
  for p in "${OC_GATEWAY_PORT:-}" "${GATEWAY_WATCHDOG_PORT:-}" "${TGHC_GATEWAY_PORT:-}"; do
    case "$p" in ''|*[!0-9]*) continue ;; esac
    OCD_GATEWAY_PORT="$p"; OCD_GATEWAY_PORT_SOURCE="env"; return 0
  done
  if [ -f "$OCD_JSON" ]; then
    p="$(python3 - "$OCD_JSON" <<'PORTY' 2>/dev/null || true
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    print(""); raise SystemExit(0)
g = d.get("gateway") or {}
v = g.get("port")
print(v if isinstance(v, int) else "")
PORTY
)"
    case "$p" in ''|*[!0-9]*) ;; *) OCD_GATEWAY_PORT="$p"; OCD_GATEWAY_PORT_SOURCE="openclaw.json:gateway.port"; OCD_PORT_MEMO_KEY="${OC_GATEWAY_PORT:-\x00}${GATEWAY_WATCHDOG_PORT:-\x00}${TGHC_GATEWAY_PORT:-\x00}"; return 0 ;; esac
  fi
  # Offline/CI escape hatch: fixtures and harnesses must not shell a live CLI
  # (measured ~4.5s per call here, which is what made the triage self-test
  # exceed two minutes). Real boxes never set this, so live discovery is intact.
  if [ "${OC_SKIP_CLI_PROBE:-0}" != "1" ] && command -v openclaw >/dev/null 2>&1; then
    p="$(_ocd_bounded openclaw gateway status 2>/dev/null | awk '/Listening:/{for(i=1;i<=NF;i++) if ($i ~ /^127\.0\.0\.1:|^0\.0\.0\.0:|^\[::1\]:/) {n=split($i,a,":"); print a[n]; exit}}' | head -1)"
    case "$p" in ''|*[!0-9]*) ;; *) OCD_GATEWAY_PORT="$p"; OCD_GATEWAY_PORT_SOURCE="openclaw gateway status"; OCD_PORT_MEMO_KEY="${OC_GATEWAY_PORT:-\x00}${GATEWAY_WATCHDOG_PORT:-\x00}${TGHC_GATEWAY_PORT:-\x00}"; return 0 ;; esac
  fi
  for p in "${PORT:-}" "${OPENCLAW_PORT:-}"; do
    case "$p" in ''|*[!0-9]*) continue ;; esac
    OCD_GATEWAY_PORT="$p"; OCD_GATEWAY_PORT_SOURCE="PORT/OPENCLAW_PORT"; return 0
  done
  OCD_GATEWAY_PORT="18789"; OCD_GATEWAY_PORT_SOURCE="default"
  return 0
}

# ---------------------------------------------------------------------------
# APP READINESS — the signal that separates a live gateway from a container
# that is merely Up or a process that exited 0 days ago.
#   ready         : /healthz answers HTTP 200 with "ok":true, or the root body
#                   carries "ok":true (the gateway's own health contract).
#   not-ready     : something answered and it was NOT healthy, or the resolved
#                   port refused the connection (nothing is listening).
#   undetermined  : curl absent, timeout with no answer, or no port resolved.
# Never returns "ready" on absence of evidence.
# ---------------------------------------------------------------------------
ocd_app_ready() {
  local port url code body status payload
  local attempts="${OC_APP_READY_ATTEMPTS:-3}" timeout_s="${OC_APP_READY_TIMEOUT:-5}" i=1
  local last_ready="" last_detail=""
  OCD_READY=""; OCD_READY_DETAIL=""
  case "$attempts" in ''|*[!0-9]*) attempts=1 ;; esac
  [ "$attempts" -lt 1 ] && attempts=1
  if [ -n "${OC_APP_READY_URL:-}" ]; then
    url="$OC_APP_READY_URL"
  else
    [ -n "$OCD_GATEWAY_PORT" ] || ocd_gateway_port
    port="$OCD_GATEWAY_PORT"
    if [ -z "$port" ]; then OCD_READY="undetermined"; OCD_READY_DETAIL="no gateway port resolved"; return 2; fi
    url="http://127.0.0.1:${port}/healthz"
  fi
  if ! command -v curl >/dev/null 2>&1; then
    OCD_READY="undetermined"; OCD_READY_DETAIL="curl not on PATH — cannot prove app readiness"; return 2
  fi
  # A single probe is not evidence of a dead app: a live gateway was measured
  # answering this exact URL in 1.2ms, yet one cold attempt returned rc=28.
  # Retry; only the REPEATED verdict is reported, so a slow first connect can
  # never manufacture a false "undetermined" (and never a false "ready").
  while [ "$i" -le "$attempts" ]; do
    body="$(curl -s -m "$timeout_s" -o - -w $'\n%{http_code}' "$url" 2>/dev/null)"; code=$?
    case "$code" in
      7)
        last_ready="not-ready"; last_detail="connection refused at $url (nothing listening — gateway is down)" ;;
      28)
        last_ready="undetermined"; last_detail="probe to $url timed out with no answer after ${timeout_s}s (attempt $i/$attempts)" ;;
      0)
        status="${body##*$'\n'}"; payload="${body%$'\n'*}"
        case "$payload" in
          *'"ok":true'*|*'"ok": true'*)
            if [ "$status" = "200" ]; then
              last_ready="ready"; last_detail="HTTP 200 + ok:true from $url (attempt $i/$attempts)"
            else
              last_ready="not-ready"; last_detail="HTTP ${status} + ok:true from $url — unexpected status, not a proven healthy gateway (attempt $i/$attempts)"
            fi ;;
          *)
            last_ready="not-ready"; last_detail="HTTP ${status} from $url without \"ok\":true in the body — not the gateway health contract (attempt $i/$attempts)" ;;
        esac ;;
      *)
        last_ready="undetermined"; last_detail="probe to $url failed (curl rc=$code, attempt $i/$attempts)" ;;
    esac
    [ "$last_ready" = "ready" ] && break
    [ "$last_ready" = "not-ready" ] && [ "$code" -eq 7 ] && break
    i=$((i + 1))
    [ "$i" -le "$attempts" ] && sleep 1
  done
  OCD_READY="$last_ready"; OCD_READY_DETAIL="$last_detail"
  case "$last_ready" in
    ready) return 0 ;;
    not-ready) [ "${code:-0}" -eq 7 ] || true; return 1 ;;
    *) return 2 ;;
  esac
}

# ---------------------------------------------------------------------------
# One-line descriptor for every report (and the --json target block).
# ---------------------------------------------------------------------------
# Structured-log directory. Candidates in order; the first that actually holds
# a log file wins, and the rejected list is preserved so a "no log today" result
# can be told apart from "wrong directory".
ocd_log_dir() {
  local c note="" best="" last=""
  local cands=""
  cands="$cands ${OC_LOG_ROOT:-} /tmp/openclaw ${HOME:-}/Library/Logs/openclaw ${OCD_ROOT:-}/logs"
  for c in $cands; do
    [ -n "$c" ] || continue
    if [ ! -d "$c" ]; then note="${note}${note:+, }$c:missing"; continue; fi
    last="$(ls -1 "$c"/openclaw-*.log 2>/dev/null | tail -1)"
    if [ -n "$last" ]; then best="$c"; break; fi
    note="${note}${note:+, }$c:no-log-files"
  done
  if [ -n "$best" ]; then OCD_LOG_DIR="$best"; OCD_LOG_NOTE="accepted=$best latest=$(basename "$last")${note:+; rejected: $note}"; return 0; fi
  OCD_LOG_DIR="${OC_LOG_ROOT:-/tmp/openclaw}"
  OCD_LOG_NOTE="no log directory holds openclaw-*.log${note:+; rejected: $note}"
  return 1
}

ocd_describe() {
  printf 'box=%s company=%s platform=%s root=%s db=%s service=%s:%s port=%s mode=%s' \
    "$OCD_BOX_SLUG" "$OCD_COMPANY_SLUG" "$OCD_PLATFORM" "${OCD_ROOT:-none}" "${OCD_DB:-none}" \
    "$OCD_TARGET_MODE" "${OCD_TARGET_ID:-none}" "${OCD_GATEWAY_PORT:-?}" "$OCD_TARGET_MODE"
}

ocd_init() {
  ocd_root || true
  OCD_JSON=""
  if [ -n "$OCD_ROOT" ] && [ -f "$OCD_ROOT/openclaw.json" ]; then
    OCD_JSON="$OCD_ROOT/openclaw.json"; OCD_JSON_STATE="present"
  else
    OCD_JSON_STATE="absent"
  fi
  ocd_log_dir || true
  ocd_platform
  ocd_target
  ocd_gateway_port
  ocd_state_db || true
  ocd_identity
}
