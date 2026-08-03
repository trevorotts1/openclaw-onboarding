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
for _c in "$SELF_DIR/../config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/onboarding/config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/skills/config/ghl-mcp-pin.env" \
          "/data/.openclaw/onboarding/config/ghl-mcp-pin.env" \
          "/data/.openclaw/skills/config/ghl-mcp-pin.env"; do
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

if [ -d /data/logs ]; then LOG_DIR="/data/logs"; else LOG_DIR="$HOME/Library/Logs/ghl-mcp"; fi
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
    alert_operator "GHL MCP recovered after probe restart" \
      "ghl-mcp-probe restarted the Tier 2 community MCP on ${URL} after it stopped answering JSON-RPC (prior rc=${RC}). It is answering now. Check ${LOG_DIR} if this repeats."
    exit 0
  fi
  run_probe; RC=$?
fi

case "$RC" in
  0)
    report "OK" "(${URL} answers JSON-RPC; tools=${TOOL_COUNT:-?}, profile=${GHL_MCP_TOOL_PROFILE})"
    exit 0 ;;
  2)
    report "NO_LISTENER" "(nothing healthy on ${URL} — the Tier 2 MCP is DOWN or another service owns the port)"
    alert_operator "GHL MCP DOWN (no listener)" \
      "ghl-mcp-probe found no healthy GHL MCP on ${URL}. Tier 2 GHL tools will not resolve. Re-run scripts/ghl-mcp-autostart.sh on this box."
    exit 2 ;;
  3)
    report "DEAF" "(/health is green but NO JSON-RPC response within ${GHL_MCP_PROBE_TIMEOUT}s — the stale-dist deafness signature: every agent init will burn the full connectionTimeoutMs)"
    alert_operator "GHL MCP DEAF (alive but not answering)" \
      "ghl-mcp-probe: ${URL}/health is green but /mcp returned no JSON-RPC response in ${GHL_MCP_PROBE_TIMEOUT}s. This is the stale-compiled-dist signature. Re-run scripts/ghl-mcp-autostart.sh (it rebuilds from the pinned commit and verifies the artifact)."
    exit 3 ;;
  4)
    report "PROFILE_DRIFT" "(answering, but tools=${TOOL_COUNT} is outside the ${GHL_MCP_EXPECT_MIN_TOOLS}..${GHL_MCP_EXPECT_MAX_TOOLS} band for profile=${GHL_MCP_TOOL_PROFILE} — GHL_TOOL_PROFILE is not taking effect)"
    alert_operator "GHL MCP tool-profile drift" \
      "ghl-mcp-probe: ${URL} reports ${TOOL_COUNT} tools, outside the band for GHL_TOOL_PROFILE=${GHL_MCP_TOOL_PROFILE}. The service definition may have lost the profile env. Re-run scripts/ghl-mcp-autostart.sh."
    exit 4 ;;
  *)
    report "UNHEALTHY" "(${URL}/health responded but not as a healthy GHL MCP)"
    exit 5 ;;
esac
