#!/usr/bin/env bash
# ghl-mcp-probe.sh — v21.5.0
#
# THE ALIVE-NOT-JUST-LISTENING TEST for the GHL Community MCP (Tier 2, skill 36).
#
# WHY THIS EXISTS
#   For two days every agent init on the fleet hung for the full 30s
#   connectionTimeoutMs against a GHL MCP that was UP. The compiled
#   dist/main.js was stale — it predated upstream's `await
#   server.connect(transport)` — so the socket accepted the connection and the
#   MCP handshake was answered by nobody.
#
#   Nothing detected it, because nothing asked for an ANSWER:
#     - launchd KeepAlive / pm2 / systemd only watch the PROCESS. It was alive.
#     - `lsof -i :8765` only watches the SOCKET. It was open.
#     - GET /health is served by express BEFORE the MCP transport is wired, so
#       a deaf server happily returns {"status":"healthy","tools":N}.
#   A liveness check that cannot fail is not a liveness check.
#
# WHAT THIS DOES
#   1. GET  /health           — is a GHL MCP (not Cognee) listening at all?
#   2. POST /mcp  JSON-RPC    — `initialize`; a real MCP response containing
#                               serverInfo MUST arrive within --timeout seconds.
#                               This is the assertion the outage would have failed.
#   3. Tool-surface sanity    — the live tool count must sit inside the band for
#                               the configured GHL_TOOL_PROFILE, proving the
#                               profile actually took effect and the box is not
#                               quietly serving the full 858-tool catalogue.
#
# USAGE
#   ghl-mcp-probe.sh --once                 # probe, print STATUS, exit
#   ghl-mcp-probe.sh --once --heal          # + ONE bounded restart, then re-probe
#   ghl-mcp-probe.sh --once --skip-profile  # liveness only (used by the installer)
#   ghl-mcp-probe.sh --once --quiet         # exit code only
#   [--timeout N] [--url http://localhost:8765]
#
# EXIT CODES (callers gate on these)
#   0  OK            — answering JSON-RPC, profile in band
#   2  NO_LISTENER   — nothing (or the wrong service) on the port
#   3  DEAF          — listening + /health green, NO JSON-RPC response  ← the outage
#   4  PROFILE_DRIFT — answering, but the tool surface is not the configured profile
#   5  UNHEALTHY     — /health responded but not as a healthy GHL MCP
#
# Never exits non-zero for its own internal problems (missing curl/python3 is
# reported as an honest SKIP with exit 0) — a broken probe must not masquerade
# as a broken server.

set -u

ONCE=1
QUIET=0
HEAL=0
SKIP_PROFILE=0
URL=""
TIMEOUT=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --once)         ONCE=1 ;;
    --quiet)        QUIET=1 ;;
    --heal)         HEAL=1 ;;
    --skip-profile) SKIP_PROFILE=1 ;;
    --timeout)      TIMEOUT="${2:-}"; shift ;;
    --url)          URL="${2:-}"; shift ;;
    *) : ;;
  esac
  shift
done

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# ── Shared pin/profile config (single source of truth) ───────────────────────
# v21.6.0/R1: $OC_CONFIG/config/ (the FIRST two candidates) is where both
# installers now deliver config/. Before that fix this list missed on every
# box, so the probe could not see GHL_MCP_EXPECT_MIN_TOOLS /
# GHL_MCP_EXPECT_MAX_TOOLS / a non-default profile — meaning a box deliberately
# moved to `stable` would report PROFILE_DRIFT forever and page the operator
# every 15 minutes.
#
# ⚠️ KEEP IN SYNC with ghl-mcp-autostart.sh, the VPS overlay,
# qc-assert-ghl-mcp-supervised.sh and the delivery step in BOTH installers.
# scripts/qc-assert-pin-delivery-paths.sh fails CI if they drift.
for _c in "$SELF_DIR/../config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/onboarding/config/ghl-mcp-pin.env" \
          "/data/.openclaw/config/ghl-mcp-pin.env" \
          "/data/.openclaw/onboarding/config/ghl-mcp-pin.env"; do
  # shellcheck disable=SC1090
  [ -f "$_c" ] && { . "$_c"; break; }
done

GHL_MCP_PORT="${GHL_MCP_PORT:-8765}"
GHL_MCP_PROBE_TIMEOUT="${GHL_MCP_PROBE_TIMEOUT:-10}"
GHL_MCP_TOOL_PROFILE="${GHL_MCP_TOOL_PROFILE:-curated}"
GHL_MCP_EXPECT_MIN_TOOLS="${GHL_MCP_EXPECT_MIN_TOOLS:-1}"
GHL_MCP_EXPECT_MAX_TOOLS="${GHL_MCP_EXPECT_MAX_TOOLS:-200}"
[ -n "$TIMEOUT" ] && GHL_MCP_PROBE_TIMEOUT="$TIMEOUT"
[ -z "$URL" ] && URL="http://localhost:${GHL_MCP_PORT}"
URL="${URL%/}"

# R12 — HONOUR GHL_MCP_LOG_DIR. This used to be computed here and the caller's
# GHL_MCP_LOG_DIR was ignored outright — the very variable the autostart passes
# into the launchd plist, the pm2 ecosystem, the systemd unit and the supervisor
# loop. Two consequences, both real:
#   1. The probe's log location was coincidental rather than configured.
#   2. tests/unit/ghl-mcp-probe.test.sh had no way to redirect it, so running the
#      unit test appended real-looking OK/DEAF/NO_LISTENER/PROFILE_DRIFT verdicts
#      to the BOX's production probe.log. The operator box's probe.log was found
#      to be 100% test output, which makes a genuine DEAF verdict indistinguish-
#      able from a fixture in the probe's only durable record.
if [ -n "${GHL_MCP_LOG_DIR:-}" ]; then
  LOG_DIR="$GHL_MCP_LOG_DIR"
elif [ -d /data/logs ]; then
  LOG_DIR="/data/logs"
else
  LOG_DIR="$HOME/Library/Logs/ghl-mcp"
fi
mkdir -p "$LOG_DIR" 2>/dev/null || true

# ── LOG ROTATION (fleet gap: these logs never rotated — 5.4 MB on the operator
# box, 2.2 MB on a second fleet box, both growing since May). copytruncate,
# because the supervisor holds an open fd: renaming would leave the server
# writing to an
# orphaned inode. The launcher rotates at (re)start; this repeats it every run so
# a server that stays up for months still gets rotated.
GHL_MCP_LOG_MAX_BYTES="${GHL_MCP_LOG_MAX_BYTES:-10485760}"
GHL_MCP_LOG_KEEP="${GHL_MCP_LOG_KEEP:-3}"
rotate_log() {
  local f="$1" max="$GHL_MCP_LOG_MAX_BYTES" keep="$GHL_MCP_LOG_KEEP" sz i
  [ -f "$f" ] || return 0
  sz="$(wc -c < "$f" 2>/dev/null | tr -d ' ')"
  [ -n "$sz" ] || return 0
  [ "$sz" -gt "$max" ] 2>/dev/null || return 0
  rm -f "${f}.${keep}" 2>/dev/null || true
  i=$((keep-1))
  while [ "$i" -ge 1 ]; do
    [ -f "${f}.${i}" ] && mv "${f}.${i}" "${f}.$((i+1))" 2>/dev/null || true
    i=$((i-1))
  done
  cp "$f" "${f}.1" 2>/dev/null && : > "$f"
}
for _lf in "$LOG_DIR/stderr.log" "$LOG_DIR/stdout.log" \
           "$LOG_DIR/ghl-mcp.log" "$LOG_DIR/ghl-mcp.err.log" "$LOG_DIR/probe.log"; do
  rotate_log "$_lf"
done

say() { [ "$QUIET" = "1" ] || printf '%s\n' "$*"; }
report() {
  local state="$1"; shift
  say "STATUS: ghl-mcp-probe=${state} $*"
  printf '%s STATUS: ghl-mcp-probe=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$state" "$*" >> "$LOG_DIR/probe.log" 2>/dev/null || true
}

if ! command -v curl >/dev/null 2>&1; then
  report "SKIPPED_NO_CURL" "(curl not on PATH — cannot probe; this is a probe gap, NOT a server verdict)"
  exit 0
fi

# ── Operator alert (fail-soft, operator-only, never a client channel) ────────
# Uses the repo's own signed Command Center ingest helper when it is present.
# No Telegram, no client messaging, and never fails the probe.
alert_operator() {
  local title="$1" body="$2" route=""
  for c in "$SELF_DIR/mc-route.sh" \
           "$HOME/.openclaw/onboarding/scripts/mc-route.sh" \
           "$HOME/.openclaw/skills/scripts/mc-route.sh" \
           "/data/.openclaw/onboarding/scripts/mc-route.sh"; do
    [ -x "$c" ] && { route="$c"; break; }
  done
  [ -n "$route" ] || return 0
  bash "$route" general-task "$title" "$body" >/dev/null 2>&1 || true
}

# ── R13: ALERT ROUTING — card by default, Rangers only on a sustained outage ──
# The probe already self-heals ONCE, so a single transient must never page a
# human. The escalation threshold is therefore 3 CONSECUTIVE identical non-OK
# verdicts — 45 minutes at the 15-minute cadence — which is a genuinely stuck
# server, not a blip. State lives in one small file so it survives between runs.
#
#   $LOG_DIR/.probe-streak  ->  "<state> <consecutive_count> <escalated:0|1>"
#
# Reset on OK/RECOVERED. Escalation fires EXACTLY ONCE per unbroken streak (the
# `escalated` flag): Rescue Rangers enforces a hard 25-exchange-per-day cap, so a
# probe that re-paged every 15 minutes would burn a client's whole daily budget
# on one incident and lock out real escalations.
STREAK_FILE="$LOG_DIR/.probe-streak"

read_streak() {   # echoes "state count escalated"
  if [ -f "$STREAK_FILE" ]; then
    tr -d '\r' < "$STREAK_FILE" 2>/dev/null | head -1
  else
    printf 'NONE 0 0'
  fi
}
write_streak() { printf '%s %s %s\n' "$1" "$2" "$3" > "$STREAK_FILE" 2>/dev/null || true; }
clear_streak() { rm -f "$STREAK_FILE" 2>/dev/null || true; }

# Rescue Rangers escalation — the n8n webhook documented in
# scripts/rescue-escalation-section.md.tpl. Fail-soft in every direction and it
# NEVER changes the probe's exit code.
#
# IDENTITY IS FAIL-CLOSED ON PURPOSE. An escalation whose boxName is not this
# box's canonical fleet slug cannot be attributed, is not counted against the
# right account, and pollutes the shared Rangers queue. If either the webhook URL
# or FLEET_STANDING_BOX_SLUG is absent we do NOT invent one and do NOT send a
# malformed payload — we say so on the operator card instead, which is always
# sent alongside. No client identity is hardcoded here; every field comes from
# the box's own environment at runtime.
escalate_rescue_rangers() {
  local state="$1" detail="$2"
  local url="${RESCUE_RANGERS_WEBHOOK_URL:-}"
  local slug="${FLEET_STANDING_BOX_SLUG:-}"
  if [ -z "$url" ] || [ -z "$slug" ]; then
    local missing=""
    [ -z "$url" ]  && missing="RESCUE_RANGERS_WEBHOOK_URL"
    [ -z "$slug" ] && missing="${missing:+$missing and }FLEET_STANDING_BOX_SLUG"
    say "  [ghl-mcp-probe] Rangers escalation SKIPPED (missing $missing) — the operator card carries the signal instead"
    return 0
  fi
  command -v curl >/dev/null 2>&1 || return 0
  local payload ver
  ver="$(openclaw --version 2>/dev/null | head -1 | tr -d '"' || echo unknown)"
  payload="$(GHLP_SLUG="$slug" GHLP_STATE="$state" GHLP_DETAIL="$detail" GHLP_VER="${ver:-unknown}" \
    GHLP_PERSON="${RESCUE_RANGERS_PERSON:-operator}" \
    GHLP_CLIENT="${RESCUE_RANGERS_CLIENT_NAME:-$slug}" \
    GHLP_AGENT="${RESCUE_RANGERS_AGENT_NAME:-ghl-mcp-probe}" \
    GHLP_BOXTYPE="${RESCUE_RANGERS_BOX_TYPE:-unknown}" \
    GHLP_RETURN="${RESCUE_RANGERS_RETURN_TO:-}" \
    python3 - <<'PYEOF' 2>/dev/null || true
import json, os
p = {
    "action": "escalate",
    "person": os.environ.get("GHLP_PERSON", "operator"),
    "clientName": os.environ.get("GHLP_CLIENT", ""),
    "agentName": os.environ.get("GHLP_AGENT", "ghl-mcp-probe"),
    "boxName": os.environ.get("GHLP_SLUG", ""),
    "boxType": os.environ.get("GHLP_BOXTYPE", "unknown"),
    "openclawVersion": os.environ.get("GHLP_VER", "unknown"),
    "problem": ("GHL Tier 2 community MCP has been " + os.environ.get("GHLP_STATE", "")
                + " for 3 consecutive 15-minute probes (~45 minutes). " + os.environ.get("GHLP_DETAIL", "")),
    "alreadyTried": ("1. ghl-mcp-probe --heal performed one bounded supervisor restart and re-probed. "
                     "2. The restart did not restore a JSON-RPC response. "
                     "3. Next step is scripts/ghl-mcp-autostart.sh, which re-pins, rebuilds from the vetted "
                     "commit into a temp dir and swaps dist/ only on success."),
    "returnTo": os.environ.get("GHLP_RETURN", ""),
}
print(json.dumps(p))
PYEOF
)"
  [ -n "$payload" ] || return 0
  # NO ARRAYS HERE, deliberately. macOS ships bash 3.2 and BOTH periodic callers
  # invoke this script as `/bin/bash …` (the launchd probe plist and the VPS cron
  # line), so expanding an EMPTY array as "${hdr[@]}" under `set -u` aborts with
  # `hdr[@]: unbound variable` — which is the common case, since most boxes have
  # no RESCUE_RANGERS_WEBHOOK_SECRET. Two explicit branches are bash-3.2 safe.
  if [ -n "${RESCUE_RANGERS_WEBHOOK_SECRET:-}" ]; then
    curl -sS -m 10 -X POST "$url" -H 'Content-Type: application/json' \
      -H "X-Rescue-Secret: ${RESCUE_RANGERS_WEBHOOK_SECRET}" \
      --data-binary "$payload" >/dev/null 2>&1 || true
  else
    curl -sS -m 10 -X POST "$url" -H 'Content-Type: application/json' \
      --data-binary "$payload" >/dev/null 2>&1 || true
  fi
  say "  [ghl-mcp-probe] escalated to Rescue Rangers (3 consecutive ${state} verdicts)"
}

# ── 1. Is anything (and the RIGHT thing) listening? ──────────────────────────
HEALTH_BODY=""
check_health() {
  HEALTH_BODY="$(curl -fsS --max-time 5 "${URL}/health" 2>/dev/null || true)"
  [ -n "$HEALTH_BODY" ] || return 2
  case "$HEALTH_BODY" in
    *0.5.3-local*|*cognee*|*Cognee*) return 2 ;;   # wrong service on the port
  esac
  case "$HEALTH_BODY" in
    *'"status":"healthy"'*|*healthy*) return 0 ;;
    *) return 5 ;;
  esac
}

# ── 2. Does it ANSWER? (the assertion the outage would have failed) ──────────
MCP_BODY=""
check_responds() {
  MCP_BODY="$(curl -sS --max-time "$GHL_MCP_PROBE_TIMEOUT" -X POST "${URL}/mcp" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"ghl-mcp-probe","version":"1"}}}' \
    2>/dev/null || true)"
  case "$MCP_BODY" in
    *serverInfo*) return 0 ;;
    *) return 3 ;;
  esac
}

# ── 3. Did the tool profile actually take effect? ────────────────────────────
TOOL_COUNT=""
check_profile() {
  TOOL_COUNT="$(printf '%s' "$HEALTH_BODY" | sed -n 's/.*"tools":[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -1)"
  [ -n "$TOOL_COUNT" ] || return 0     # cannot read a count -> do not invent a verdict
  [ "$TOOL_COUNT" -ge "$GHL_MCP_EXPECT_MIN_TOOLS" ] 2>/dev/null || return 4
  [ "$TOOL_COUNT" -le "$GHL_MCP_EXPECT_MAX_TOOLS" ] 2>/dev/null || return 4
  return 0
}

# ── Bounded self-heal: exactly ONE restart attempt, then re-probe ────────────
heal_once() {
  say "  [ghl-mcp-probe] attempting ONE bounded restart"
  if [ "$(uname -s)" = "Darwin" ]; then
    launchctl kickstart -k "gui/$(id -u)/com.clawd.ghl-mcp" >/dev/null 2>&1 || true
  elif command -v pm2 >/dev/null 2>&1 && pm2 describe ghl-community-mcp >/dev/null 2>&1; then
    pm2 restart ghl-community-mcp >/dev/null 2>&1 || true
  elif command -v systemctl >/dev/null 2>&1; then
    # sudo -n (non-interactive): this probe runs unattended from launchd/cron and
    # may also be run by hand in a TTY. A bare `sudo` would PROMPT for a password
    # in the interactive case and block the heal indefinitely. Never prompt —
    # on a box without passwordless sudo this simply skips, and the probe still
    # reports the honest DEAF/NO_LISTENER verdict below.
    sudo -n systemctl restart ghl-mcp >/dev/null 2>&1 || true
  fi
  local i=0
  while [ "$i" -lt 10 ]; do
    sleep 2
    if check_health && check_responds; then return 0; fi
    i=$((i+1))
  done
  return 1
}

run_probe() {
  local rc
  check_health; rc=$?
  if [ "$rc" != "0" ]; then
    return "$rc"
  fi
  check_responds; rc=$?
  if [ "$rc" != "0" ]; then
    return "$rc"
  fi
  if [ "$SKIP_PROFILE" = "0" ]; then
    check_profile; rc=$?
    [ "$rc" != "0" ] && return "$rc"
  fi
  return 0
}

run_probe
RC=$?

if [ "$RC" != "0" ] && [ "$HEAL" = "1" ]; then
  if heal_once; then
    report "RECOVERED" "(a bounded restart restored a JSON-RPC response on ${URL}; prior state rc=${RC})"
    # R13: RATE-LIMIT the RECOVERED notice to at most one per hour. A flapping
    # server (heal → drop → heal) would otherwise card the operator every 15
    # minutes and train them to ignore the channel. The verdict is still written
    # to probe.log every time; only the ALERT is throttled.
    _RECOV_STAMP="$LOG_DIR/.probe-recovered-last"
    _now="$(date -u +%s 2>/dev/null || echo 0)"
    _last=0
    [ -f "$_RECOV_STAMP" ] && _last="$(tr -dc '0-9' < "$_RECOV_STAMP" 2>/dev/null | head -1)"
    [ -n "$_last" ] || _last=0
    if [ "$((_now - _last))" -ge 3600 ] 2>/dev/null; then
      alert_operator "GHL MCP recovered after probe restart" \
        "ghl-mcp-probe restarted the Tier 2 community MCP on ${URL} after it stopped answering JSON-RPC (prior rc=${RC}). It is answering now. Check ${LOG_DIR} if this repeats."
      printf '%s\n' "$_now" > "$_RECOV_STAMP" 2>/dev/null || true
    else
      say "  [ghl-mcp-probe] RECOVERED alert suppressed (one per hour per box; last $((_now - _last))s ago)"
    fi
    clear_streak
    exit 0
  fi
  run_probe; RC=$?
fi

# ── R13: streak accounting, computed BEFORE the verdict dispatch below ────────
_STATE_NAME="OK"
case "$RC" in
  0) _STATE_NAME="OK" ;;
  2) _STATE_NAME="NO_LISTENER" ;;
  3) _STATE_NAME="DEAF" ;;
  4) _STATE_NAME="PROFILE_DRIFT" ;;
  *) _STATE_NAME="UNHEALTHY" ;;
esac
_PREV="$(read_streak)"
_PREV_STATE="$(printf '%s' "$_PREV" | awk '{print $1}')"
_PREV_COUNT="$(printf '%s' "$_PREV" | awk '{print $2}')"
_PREV_ESC="$(printf '%s' "$_PREV" | awk '{print $3}')"
[ -n "$_PREV_STATE" ] || _PREV_STATE="NONE"
case "$_PREV_COUNT" in ''|*[!0-9]*) _PREV_COUNT=0 ;; esac
case "$_PREV_ESC"   in ''|*[!0-9]*) _PREV_ESC=0 ;; esac

_STREAK=1
_ESCALATED=0
if [ "$RC" = "0" ]; then
  clear_streak
else
  if [ "$_PREV_STATE" = "$_STATE_NAME" ]; then
    _STREAK=$((_PREV_COUNT + 1))
    _ESCALATED="$_PREV_ESC"
  fi
  write_streak "$_STATE_NAME" "$_STREAK" "$_ESCALATED"
fi

# Escalate to Rescue Rangers on the 3rd CONSECUTIVE identical non-OK verdict
# (~45 minutes), exactly once per unbroken streak. The operator card below is
# still sent every cycle — escalation is additive, never a replacement.
maybe_escalate() {
  local detail="$1"
  [ "$RC" = "0" ] && return 0
  [ "$_STREAK" -ge 3 ] 2>/dev/null || return 0
  [ "$_ESCALATED" = "0" ] || return 0
  escalate_rescue_rangers "$_STATE_NAME" "$detail"
  write_streak "$_STATE_NAME" "$_STREAK" 1
}

case "$RC" in
  0)
    report "OK" "(${URL} answers JSON-RPC; tools=${TOOL_COUNT:-?}, profile=${GHL_MCP_TOOL_PROFILE})"
    exit 0 ;;
  2)
    report "NO_LISTENER" "(nothing healthy on ${URL} — the Tier 2 MCP is DOWN or another service owns the port)"
    alert_operator "GHL MCP DOWN (no listener)" \
      "ghl-mcp-probe found no healthy GHL MCP on ${URL}. Tier 2 GHL tools will not resolve. Re-run scripts/ghl-mcp-autostart.sh on this box. (consecutive NO_LISTENER probes: ${_STREAK})"
    maybe_escalate "Nothing healthy is listening on ${URL}; Tier 2 GHL tools do not resolve."
    exit 2 ;;
  3)
    report "DEAF" "(/health is green but NO JSON-RPC response within ${GHL_MCP_PROBE_TIMEOUT}s — the stale-dist deafness signature: every agent init will burn the full connectionTimeoutMs)"
    alert_operator "GHL MCP DEAF (alive but not answering)" \
      "ghl-mcp-probe: ${URL}/health is green but /mcp returned no JSON-RPC response in ${GHL_MCP_PROBE_TIMEOUT}s. This is the stale-compiled-dist signature. Re-run scripts/ghl-mcp-autostart.sh (it rebuilds from the pinned commit and verifies the artifact). (consecutive DEAF probes: ${_STREAK})"
    maybe_escalate "/health is green but /mcp answers no JSON-RPC within ${GHL_MCP_PROBE_TIMEOUT}s — the stale-compiled-dist deafness signature. Every agent init on this box burns the full connectionTimeoutMs."
    exit 3 ;;
  4)
    report "PROFILE_DRIFT" "(answering, but tools=${TOOL_COUNT} is outside the ${GHL_MCP_EXPECT_MIN_TOOLS}..${GHL_MCP_EXPECT_MAX_TOOLS} band for profile=${GHL_MCP_TOOL_PROFILE} — GHL_TOOL_PROFILE is not taking effect)"
    alert_operator "GHL MCP tool-profile drift" \
      "ghl-mcp-probe: ${URL} reports ${TOOL_COUNT} tools, outside the band for GHL_TOOL_PROFILE=${GHL_MCP_TOOL_PROFILE}. The service definition may have lost the profile env. Re-run scripts/ghl-mcp-autostart.sh. (consecutive PROFILE_DRIFT probes: ${_STREAK})"
    maybe_escalate "The live tool count (${TOOL_COUNT}) is outside the band for GHL_TOOL_PROFILE=${GHL_MCP_TOOL_PROFILE}; the service definition appears to have lost the profile env."
    exit 4 ;;
  *)
    report "UNHEALTHY" "(${URL}/health responded but not as a healthy GHL MCP)"
    exit 5 ;;
esac
