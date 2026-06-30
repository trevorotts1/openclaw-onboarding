#!/bin/sh
# ============================================================================
# gateway-health-watchdog.sh — OpenClaw GATEWAY health watchdog + self-heal.
#
# Purpose
#   Close the gateway-deferral-deadlock gap. A token rotation -> deferred
#   gateway restart -> SIGTERM can leave the gateway process DEAD or HUNG. On a
#   VPS the container `unless-stopped` policy revives an EXITED process in
#   ~14 min, but a process that is alive-yet-hung (port dead) never exits and is
#   therefore invisible to `unless-stopped`. On a Mac the gateway LaunchAgent's
#   KeepAlive only respawns a still-LOADED job, so a hung-but-loaded or
#   booted-out gateway can stay dark indefinitely. This watchdog is the missing
#   HTTP-health leg that catches BOTH the dead and the hung case.
#
#   It is the script that the SHIPPED hook in remediate.sh already looks for:
#       WATCHDOG="$SVC_DIR/gateway-watchdog.sh"     (remediate.sh, var WATCHDOG)
#       if [ -x "$WATCHDOG" ] ... sh "$WATCHDOG"     (remediate.sh, gateway leg)
#   install-service-remediate.sh copies THIS file to
#       ~/.openclaw/service-env/gateway-watchdog.sh
#   so the already-shipped com.openclaw.service-remediate LaunchAgent (every
#   5 min) auto-delegates the gateway leg to it. Health logic lives in one place.
#
# Contract (matches the fleet guardrails)
#   * NEVER runs bare `gws` (bare headless gws self-wipes ~/.config/gws creds).
#     This script does not invoke `gws` at all.
#   * NEVER deletes/edits config, credentials, or any plist. Read-mostly.
#   * Loud, append-only logging. Idempotent. Fail-soft (a watchdog must never be
#     the thing that takes the box down).
#   * Detects box type itself (Mac login-user / VPS-host-with-docker /
#     inside-container). Acts ONLY where it CAN act safely.
#   * --report-only / GATEWAY_WATCHDOG_DRYRUN=1 prints the action and takes none.
#   * Acts only after N CONSECUTIVE failures (default 3) AND honours a
#     post-action cooldown, so it can never become a restart storm.
#   * Does NOT assume port 18789. The repo explicitly warns "the gateway port is
#     often NOT 18789 — read PORT / `openclaw gateway status`"
#     (38-conversational-ai-system/references/VPS-VS-MAC-INSTALL.md). It honours an
#     explicit GATEWAY_WATCHDOG_PORT first, else reads PORT / `openclaw gateway status`.
#
# Health signal references (v16.2.6)
#   * /healthz returns HTTP 200 when the gateway is up
#     (38-conversational-ai-system/scripts/11-run-qc-checklist.sh — local probe
#      `curl ... http://127.0.0.1:${OPENCLAW_PORT:-3000}/healthz` expects 200).
#   * The gateway hook endpoint returns 200 + a body containing `{"ok":true}`
#     (38-conversational-ai-system/INSTRUCTIONS.md, Step 6.6 self-test).
#   * `openclaw gateway status` reports `Listening: 127.0.0.1:<port>`
#     (38-conversational-ai-system/references/cloudflare-tunnel-troubleshooting.md).
#
# Exit codes: 0 = healthy, or a heal action was taken/skipped cleanly;
#             1 = unhealthy and could not act / action failed (so a supervising
#                 cron can alert without this script ever aborting the box).
# ============================================================================
set -u

# ---- Tunables (env-overridable) --------------------------------------------
FAIL_THRESHOLD="${GATEWAY_WATCHDOG_FAILS:-3}"     # consecutive bad checks before acting
COOLDOWN_SECS="${GATEWAY_WATCHDOG_COOLDOWN:-600}" # min seconds between two heal actions
CURL_TIMEOUT="${GATEWAY_WATCHDOG_TIMEOUT:-5}"     # per-probe timeout (seconds)
DRYRUN="${GATEWAY_WATCHDOG_DRYRUN:-0}"            # 1 = report-only
GATEWAY_LABEL="${GATEWAY_WATCHDOG_LABEL:-ai.openclaw.gateway}"  # Mac LaunchAgent label fallback

case "${1:-}" in
  --report-only|--dry-run) DRYRUN=1 ;;
  --help|-h)
    sed -n '2,49p' "$0"; exit 0 ;;
esac

# ---- Box-type + path detection ---------------------------------------------
# vps-container:  /data/.openclaw exists AND no usable docker CLI -> inside the
#                 OpenClaw container; there is NO docker socket here.
# mac:            $HOME/.openclaw exists (login user), no /data/.openclaw.
# vps-host:       docker CLI present, NOT inside a container (no /data/.openclaw),
#                 and an `openclaw` container is running -> the host that can
#                 docker-restart the container.
if [ -d "/data/.openclaw" ]; then
  BOX="vps-container"
  STATE_DIR="/data/.openclaw/logs"
elif [ -d "$HOME/.openclaw" ]; then
  BOX="mac"
  STATE_DIR="$HOME/Library/Logs/openclaw"
else
  BOX="unknown"
  STATE_DIR="/tmp"
fi
# A host that can drive docker (re)start is its own context (even if it has a
# /data dir of its own — the discriminator is "NOT /data/.openclaw AND docker").
if [ "$BOX" != "vps-container" ] && command -v docker >/dev/null 2>&1; then
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qE 'openclaw'; then
    BOX="vps-host"
    STATE_DIR="/tmp"
  fi
fi

mkdir -p "$STATE_DIR" 2>/dev/null || STATE_DIR="/tmp"
LOG="$STATE_DIR/gateway-watchdog.log"
STATE="$STATE_DIR/gateway-watchdog.state"          # holds: <consecutive_fail_count>
LASTACT="$STATE_DIR/gateway-watchdog.lastaction"   # holds: epoch of last heal action

ts()  { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*" >> "$LOG" 2>/dev/null; }
now() { date +%s; }

read_count()  { c="$(cat "$STATE" 2>/dev/null)"; case "$c" in ''|*[!0-9]*) echo 0 ;; *) echo "$c" ;; esac; }
write_count() { echo "$1" > "$STATE" 2>/dev/null || true; }

log "---- watchdog start (box=$BOX dryrun=$DRYRUN threshold=$FAIL_THRESHOLD) ----"

# ---- Resolve the ACTUAL gateway port (never blindly assume 18789) ----------
detect_port() {
  p=""
  # 0. EXPLICIT override wins (highest precedence, checked FIRST). On a VPS Docker
  #    HOST the `openclaw` CLI is absent (install re-execs into the container) and
  #    the host cron env carries no PORT, so EVERY signal below would fall through
  #    to 18789 — and on any box whose published gateway port != 18789 the watchdog
  #    would then probe a dead port against a HEALTHY container and `docker restart`
  #    it on a loop. install-host-watchdog-cron.sh resolves the real host-reachable
  #    port at arm time, confirms it is reachable, and forwards it here as
  #    GATEWAY_WATCHDOG_PORT (and PORT). Honour the explicit port before anything.
  if [ -n "${GATEWAY_WATCHDOG_PORT:-}" ]; then
    case "${GATEWAY_WATCHDOG_PORT}" in
      ''|*[!0-9]*) : ;;                       # ignore a non-numeric override, fall through
      *) echo "${GATEWAY_WATCHDOG_PORT}"; return ;;
    esac
  fi
  if command -v openclaw >/dev/null 2>&1; then
    # `openclaw gateway status` prints e.g. "Listening: 127.0.0.1:18789"
    p="$(openclaw gateway status 2>/dev/null \
         | grep -iE 'listen' \
         | grep -oE '[0-9]{2,5}' | tail -1)"
  fi
  [ -z "$p" ] && [ -n "${PORT:-}" ] && p="$PORT"
  [ -z "$p" ] && [ -n "${OPENCLAW_GATEWAY_PORT:-}" ] && p="$OPENCLAW_GATEWAY_PORT"
  [ -z "$p" ] && [ -n "${OPENCLAW_PORT:-}" ] && p="$OPENCLAW_PORT"
  [ -z "$p" ] && [ -n "${GATEWAY_PORT:-}" ] && p="$GATEWAY_PORT"
  [ -z "$p" ] && p="18789"   # documented default — LAST resort only
  echo "$p"
}
PORT_NUM="$(detect_port)"

# ---- Health probe ----------------------------------------------------------
# Returns 0 healthy, 1 unhealthy. Three corroborating signals; ANY pass = up.
is_healthy() {
  # Signal A: HTTP {"ok":true} on the gateway root (the hook 200 body shape).
  body="$(curl -fsS --max-time "$CURL_TIMEOUT" "http://127.0.0.1:${PORT_NUM}/" 2>/dev/null)"
  case "$body" in
    *'"ok":true'*|*'"ok": true'*) return 0 ;;
  esac
  # Signal B: /healthz returns HTTP 200 (the canonical gateway-up probe).
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time "$CURL_TIMEOUT" \
          "http://127.0.0.1:${PORT_NUM}/healthz" 2>/dev/null)"
  [ "$code" = "200" ] && return 0
  # Signal C: CLI status (TERTIARY fallback — only reached when BOTH HTTP probes
  # above failed and the `openclaw` CLI exists). Conservative + errs-safe: reject
  # the NEGATED forms first ("not running", "probe: failed", ...) so a stray
  # "ok"/"running" substring (e.g. inside "not running" or "broken") can never
  # read as healthy, then require an ANCHORED positive token from the real
  # `openclaw gateway status` output ("Connectivity probe: ok" / "Listening:
  # <ip>:<port>" / "Capability: write-capable", or a JSON "status":"ok|running|
  # healthy"). Note "Service: ... (disabled)" is NOT treated as negative — inside
  # a container it appears even when the gateway is up (INSTALL-GOTCHAS.md #7).
  if command -v openclaw >/dev/null 2>&1; then
    st="$(openclaw gateway status 2>/dev/null)"
    if printf '%s\n' "$st" | grep -qiE 'not running|not listening|not connected|probe:[[:space:]]*(failed|error|timeout)|unhealthy|stopped|dead|offline'; then
      :   # explicit negative — treat as UNHEALTHY (fall through to return 1)
    elif printf '%s\n' "$st" | grep -qE 'Connectivity probe:[[:space:]]*ok|Listening:[[:space:]]*[0-9][0-9.]*:[0-9]{2,5}|Capability:[[:space:]]*write-capable|"status"[[:space:]]*:[[:space:]]*"(ok|running|healthy)"'; then
      return 0
    fi
  fi
  return 1
}

# ---- Heal actions (per box type). NEVER destructive. -----------------------
in_cooldown() {
  last="$(cat "$LASTACT" 2>/dev/null)"; case "$last" in ''|*[!0-9]*) return 1 ;; esac
  [ "$(( $(now) - last ))" -lt "$COOLDOWN_SECS" ]
}
mark_action() { now > "$LASTACT" 2>/dev/null || true; }

heal() {
  if in_cooldown; then
    log "HOLD: within ${COOLDOWN_SECS}s cooldown of the last heal action — not acting again yet"
    return 0
  fi
  case "$BOX" in
    mac)
      # Resolve the live label (fleet fallback label is ai.openclaw.gateway).
      # Mirrors update-skills.sh gateway-restart dispatch.
      lbl="$(launchctl list 2>/dev/null | awk '/openclaw.*gateway/{print $3; exit}')"
      [ -z "$lbl" ] && lbl="$GATEWAY_LABEL"
      action="launchctl kickstart -k gui/$(id -u)/$lbl"
      ;;
    vps-host)
      cname="${OPENCLAW_CONTAINER_NAME:-$(docker ps --format '{{.Names}}' 2>/dev/null | grep -E 'openclaw' | head -1)}"
      [ -z "$cname" ] && { log "ESCALATE: vps-host but no openclaw container resolved — manual check"; return 1; }
      action="docker restart $cname"
      ;;
    vps-container)
      # Inside the container there is NO docker socket. The correct, SAFE heal is
      # to let the container restart policy (unless-stopped) revive the gateway.
      # We do NOT spawn `openclaw gateway run` here (would risk a double gateway).
      log "ESCALATE: gateway unhealthy inside container — relying on container restart policy"
      log "ESCALATE: operator (on HOST): docker restart <openclaw-container>  /  docker compose up -d --force-recreate"
      log "ESCALATE: best fix — install THIS watchdog on the VPS HOST cron (platform/vps/service-selfheal/install-host-watchdog-cron.sh), not inside the container"
      return 1
      ;;
    *)
      log "ESCALATE: unknown box type — cannot determine a safe heal action"
      return 1
      ;;
  esac

  if [ "$DRYRUN" = "1" ]; then
    log "DRYRUN: would run -> $action"
    return 0
  fi
  log "HEAL: gateway dead/hung ${FAIL_THRESHOLD}x -> $action"
  # shellcheck disable=SC2086
  sh -c "$action" >>"$LOG" 2>&1
  rc=$?
  log "HEAL rc=$rc"
  mark_action
  [ "$rc" -eq 0 ] && return 0 || return 1
}

# ---- Main ------------------------------------------------------------------
if is_healthy; then
  prev="$(read_count)"
  [ "$prev" -gt 0 ] && log "RECOVERED: gateway healthy on :${PORT_NUM} (was ${prev} consecutive fails)"
  log "OK: gateway healthy on :${PORT_NUM}"
  write_count 0
  log "---- watchdog end (healthy) ----"
  exit 0
fi

# Unhealthy
fails="$(read_count)"; fails=$(( fails + 1 )); write_count "$fails"
log "BAD: gateway probe failed on :${PORT_NUM} (consecutive=${fails}/${FAIL_THRESHOLD})"

if [ "$fails" -ge "$FAIL_THRESHOLD" ]; then
  if heal; then
    # Leave the counter standing until the NEXT cycle re-probes and confirms;
    # a single heal does NOT pre-emptively reset (avoids masking a flapping box).
    log "---- watchdog end (heal attempted) ----"
    exit 0
  else
    log "---- watchdog end (heal failed / escalated) ----"
    exit 1
  fi
fi

log "WAIT: below threshold — no action this cycle"
log "---- watchdog end (degraded, waiting) ----"
exit 1
