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
#   * On a Mac it heals BOTH dead states, not just the hung one. A gateway
#     LaunchAgent that is DEAD AND BOOTED OUT is bootstrapped from
#     ~/Library/LaunchAgents/<label>.plist first, then kickstarted: kickstart
#     alone against an unloaded label does nothing. Same threshold, same
#     cooldown, same maintenance-lock stand-down as every other action.
#   * Clears the OpenClaw 2026.9.x SESSION-STORE MIGRATION GATE when that is
#     what is holding the gateway down. See the MIGRATION GATE block below for
#     the exact refusal string and its source citation. The import it runs is
#     non-destructive: the legacy JSON files stay on disk.
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
    sed -n '2,59p' "$0"; exit 0 ;;
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
LASTMIG="$STATE_DIR/gateway-watchdog.migration-lastrun" # holds: epoch of last migration-gate doctor run

ts()  { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*" >> "$LOG" 2>/dev/null; }
now() { date +%s; }

# ---- MAINTENANCE LOCK -------------------------------------------------------
# scripts/oc-atomic-upgrade.sh holds this lock while it moves a box onto a new
# OpenClaw build. Throughout that window the gateway is DOWN ON PURPOSE while
# the config is migrated from the legacy `agents.list` array to `agents.entries`
# — a rewrite that is only valid once the new binary is on disk.
#
# This watchdog exists to revive a dead or hung gateway, so without this check
# it would do precisely the wrong thing here: an "unhealthy" verdict is CORRECT
# during the window, and kickstarting the gateway would restart the OLD binary
# against a half-migrated config. The running gateway also re-serializes
# openclaw.json roughly once a minute from an in-memory model that only knows
# `agents.list`, so a revival mid-window silently REVERTS the migration.
#
# A lock older than 60 minutes is treated as STALE and ignored: a crashed
# upgrade must never leave a box with its watchdog permanently disarmed.
LOCK_FILE="$HOME/.openclaw/.openclaw-maintenance-lock"
[ -d "/data/.openclaw" ] && LOCK_FILE="/data/.openclaw/.openclaw-maintenance-lock"
if [ -f "$LOCK_FILE" ]; then
  if [ -n "$(find "$LOCK_FILE" -mmin +60 2>/dev/null)" ]; then
    log "STALE maintenance lock at $LOCK_FILE (older than 60m) — IGNORING it and probing normally."
  else
    log "MAINTENANCE LOCK HELD ($LOCK_FILE) — standing down. An atomic OpenClaw upgrade is in progress; the gateway is down deliberately and reviving it would revert the config migration."
    exit 0
  fi
fi

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

# ---- 2026.9.x SESSION-STORE MIGRATION GATE ---------------------------------
# OpenClaw 2026.9.x REFUSES TO START the gateway while a legacy JSON session
# store is still on disk. No amount of kickstarting or bootstrapping fixes
# that: each restart re-reads the same gate and dies again, so a box can sit
# dark indefinitely with a watchdog dutifully restarting it every cooldown.
#
# THE EXACT REFUSAL, from the OpenClaw 2026.9.4 build installed on the
# operator box (npm root -g)/openclaw:
#   dist/startup-migration-BQjPMV_C.mjs line 124
#   (built from src/config/sessions/startup-migration.ts,
#    function assertSessionStoreMigrationComplete):
#
#     if (legacyStore) throw new SessionStoreMigrationRequiredError(... :
#       `Legacy session store requires migration: ${legacyStore}. Run
#        "${formatCliCommand("openclaw doctor --fix", env)}" against the same
#        state/config before starting OpenClaw.`);
#
#   The error class is line 26 of the same file (from
#   src/config/sessions/migration-required.ts) and carries kind
#   "legacy-session-store", whose reason string is "session store migration"
#   in dist/startup-maintenance-required-ZkTp8BlW.mjs lines 3-11. The gateway
#   run loop turns that into a startup_failed with code
#   "gateway.maintenance_required" (dist/run-fzUO4BXB.mjs lines 1361-1366).
#
# MATCHED SUBSTRING: "Legacy session store requires migration" - the stable,
# path-independent head of that message.
#
# THE COMMAND RUN HERE IS NOT THE ONE THE MESSAGE SUGGESTS, deliberately. The
# message points at `openclaw doctor --fix`, which is the broad repair path
# ("Apply recommended repairs", openclaw doctor --help). The narrow command
# below is the one that actually unparked a stalled client Mac on 2026-09-17:
# it IMPORTS the legacy JSON history into SQLite and LEAVES THE LEGACY FILES
# ON DISK, which is what makes it safe for an unattended watchdog to run.
#
# GUARDRAILS. Only when the gateway is already unhealthy at the fail
# threshold, only when the marker is in the live gateway log, only when the
# `openclaw` CLI exists, at most once per COOLDOWN_SECS, and never under
# DRYRUN. The maintenance-lock stand-down above has already exited the script
# before this point, so an atomic upgrade window is never touched.
MIGRATION_GATE_MARK="Legacy session store requires migration"

# Mac writes the gateway LaunchAgent log to ~/Library/Logs/openclaw/gateway.log
# (platform/mac/power-resilience/lib-power-resilience.sh renders exactly that
# StandardOutPath). ~/.openclaw/logs/gateway.log is the documented fallback,
# and /data/.openclaw/logs/gateway.log is its container equivalent.
gateway_log_path() {
  for gl in "$HOME/Library/Logs/openclaw/gateway.log" \
            "$HOME/.openclaw/logs/gateway.log" \
            "/data/.openclaw/logs/gateway.log"; do
    if [ -f "$gl" ]; then echo "$gl"; return 0; fi
  done
  return 1
}

clear_session_store_migration_gate() {
  glog="$(gateway_log_path)" || {
    log "MIGRATION-GATE: no gateway log at ~/Library/Logs/openclaw/gateway.log, ~/.openclaw/logs/gateway.log or /data/.openclaw/logs/gateway.log - gate NOT checked (undetermined, not ruled out)"
    return 1
  }
  if ! tail -n 500 "$glog" 2>/dev/null | grep -q "$MIGRATION_GATE_MARK"; then
    return 1
  fi
  log "MIGRATION-GATE: '$MIGRATION_GATE_MARK' found in $glog - the 2026.9.x session-store gate is what is holding the gateway down"
  if ! command -v openclaw >/dev/null 2>&1; then
    log "MIGRATION-GATE: no 'openclaw' CLI on PATH, cannot clear it from here. Operator: openclaw doctor --session-sqlite import --session-sqlite-all-agents --yes --non-interactive"
    return 1
  fi
  lastmig="$(cat "$LASTMIG" 2>/dev/null)"
  case "$lastmig" in ''|*[!0-9]*) lastmig=0 ;; esac
  if [ "$(( $(now) - lastmig ))" -lt "$COOLDOWN_SECS" ]; then
    log "MIGRATION-GATE: within the ${COOLDOWN_SECS}s cooldown of the last doctor import - not running it again this cycle"
    return 1
  fi
  if [ "$DRYRUN" = "1" ]; then
    log "MIGRATION-GATE DRYRUN: would run -> openclaw doctor --session-sqlite import --session-sqlite-all-agents --yes --non-interactive"
    return 0
  fi
  now > "$LASTMIG" 2>/dev/null || true
  log "MIGRATION-GATE: running -> openclaw doctor --session-sqlite import --session-sqlite-all-agents --yes --non-interactive (non-destructive: the legacy JSON files are left on disk)"
  openclaw doctor --session-sqlite import --session-sqlite-all-agents --yes --non-interactive >>"$LOG" 2>&1
  mig_rc=$?
  log "MIGRATION-GATE: doctor rc=$mig_rc (the normal heal follows either way)"
  [ "$mig_rc" -eq 0 ] && return 0 || return 1
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
      #
      # The exclusion list is load-bearing. `launchctl list` output is not
      # ordered, and a Mac commonly carries SIBLING labels that also contain
      # both "openclaw" and "gateway": the operator box runs
      # ai.openclaw.gateway-watchdog right next to ai.openclaw.gateway. The old
      # first-match awk could therefore resolve to the watchdog and kickstart
      # the wrong job while the gateway stayed dark.
      lbl="$(launchctl list 2>/dev/null \
             | awk '{print $3}' \
             | grep -E 'openclaw.*gateway' \
             | grep -vE 'watchdog|remediate|tunnel|monitor|selfheal' \
             | head -1)"
      [ -z "$lbl" ] && lbl="$GATEWAY_LABEL"
      gwplist="$HOME/Library/LaunchAgents/$lbl.plist"

      # THE DEAD-AND-BOOTED-OUT CASE.
      # `launchctl kickstart -k gui/<uid>/<label>` against a label that is not
      # bootstrapped does NOTHING: it exits non-zero with "Could not find
      # service". A detached OpenClaw upgrade stops the gateway LaunchAgent for
      # the whole update and only restarts it if the update finishes, so a
      # stalled upgrade leaves exactly this state.
      #
      # remediate.sh cannot cover it either. Its heal_label() does bootstrap a
      # booted-out job, but the moment gateway-watchdog.sh exists on disk
      # remediate.sh DELEGATES the entire gateway leg to this script and never
      # calls heal_label for the gateway at all (remediate.sh, "Gateway:
      # delegate to the watchdog when available"). Installing the watchdog was
      # therefore REMOVING the only bootstrap the gateway had. This branch is
      # what puts it back.
      #
      # Same rules as every other action here: it runs only inside heal(), so
      # it is already behind the consecutive-failure threshold and the
      # post-action cooldown, and the maintenance-lock stand-down at the top of
      # the script has already exited before anything reaches this point.
      if launchctl print "gui/$(id -u)/$lbl" >/dev/null 2>&1; then
        action="launchctl kickstart -k gui/$(id -u)/$lbl"
      elif [ -f "$gwplist" ]; then
        log "BOOTED-OUT: $lbl is not bootstrapped in gui/$(id -u); bootstrapping from $gwplist before the kickstart"
        action="launchctl bootstrap gui/$(id -u) $gwplist && launchctl kickstart -k gui/$(id -u)/$lbl"
      else
        log "ESCALATE: gateway label $lbl is not loaded AND there is no plist at $gwplist - nothing safe to bootstrap from"
        return 1
      fi
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
  # Clear the 2026.9.x session-store migration gate FIRST when that is what is
  # holding the gateway down. A restart against an un-migrated store just hits
  # the same refusal, so healing without this does nothing but burn cooldowns.
  # No-ops silently on every box that is not gated. Never fails the cycle.
  clear_session_store_migration_gate || true
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
