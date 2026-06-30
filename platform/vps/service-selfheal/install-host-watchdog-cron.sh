#!/usr/bin/env bash
# install-host-watchdog-cron.sh
# VPS HOST-side installer for the OpenClaw gateway-health watchdog.
#
# WHERE THIS RUNS: on the Docker HOST — NOT inside the container.
#   The watchdog must reach the Docker socket to `docker restart` a hung
#   container, which is impossible from inside the container. install.sh re-execs
#   INTO the container (platform/vps/bootstrap.sh §1), so install.sh can never
#   install this — the operator runs it once, by hand, on the host.
#
# WHAT IT DOES (idempotent):
#   1. Resolves the REAL gateway port for THIS host before doing anything: the
#      host has no `openclaw` CLI and the cron env has no PORT, so the watchdog
#      alone would fall through to its 18789 last-resort default. Here — where
#      docker IS available — it asks the container directly
#      (`docker exec <container> openclaw gateway status` / the container's PORT
#      env) and maps that to the host-published port (`docker port <container>`).
#   2. Runs a ONE-SHOT reachability probe over the exact host->container path the
#      cron will use (curl http://127.0.0.1:<resolved-port>/ and /healthz). If the
#      gateway is NOT reachable there, it REFUSES to arm the cron (loud warning +
#      dry-run hint, exits non-zero) — never installs a cron that would mark a
#      HEALTHY container unhealthy and docker-restart it on a loop.
#   3. Only if reachable: copies the box-aware gateway-health-watchdog.sh to a
#      durable host dir and installs a */5 host crontab entry that runs it,
#      FORWARDING the resolved port (GATEWAY_WATCHDOG_PORT + PORT) and the
#      resolved container name so the watchdog probes/acts against the real port
#      and the right container — never the 18789 fallback. On vps-host the
#      watchdog HTTP-probes the gateway and, only after N consecutive fails + a
#      cooldown, `docker restart`s the openclaw container — acting on HEALTH, not
#      just process exit. A HUNG gateway whose PID never dies is invisible to the
#      container's `restart: unless-stopped` policy; this is the belt-and-
#      suspenders that catches exactly that case.
#
# Contract: never edits openclaw config/creds/plists, never runs bare `gws`,
# fail-soft. No sudo required if the host dir + crontab are user-writable.
#
# Env overrides:
#   OPENCLAW_HOST_WATCHDOG_DIR           install + log dir (default ~/.openclaw-host-watchdog)
#   OPENCLAW_HOST_WATCHDOG_INTERVAL_MIN  cron cadence in minutes (default 5)
#   OPENCLAW_CONTAINER_NAME / _USER      target container + exec user (auto-detected)
#   GATEWAY_WATCHDOG_PORT                force the host-reachable gateway port
#                                        (skips auto-resolution; still probed)
#   GATEWAY_WATCHDOG_FAILS / _COOLDOWN / _TIMEOUT  forwarded to the watchdog
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# The single canonical watchdog ships under the mac self-heal dir (it is box-aware
# and shared by both platforms). Resolve it relative to this script:
#   platform/vps/service-selfheal/  ->  platform/mac/service-selfheal/
SRC_WATCHDOG="$HERE/../../mac/service-selfheal/gateway-health-watchdog.sh"
WATCHDOG_DIR="${OPENCLAW_HOST_WATCHDOG_DIR:-$HOME/.openclaw-host-watchdog}"
DEST_WATCHDOG="$WATCHDOG_DIR/gateway-health-watchdog.sh"
CRON_LOG="$WATCHDOG_DIR/gateway-watchdog-cron.log"
INTERVAL_MIN="${OPENCLAW_HOST_WATCHDOG_INTERVAL_MIN:-5}"
PROBE_TIMEOUT="${GATEWAY_WATCHDOG_TIMEOUT:-5}"
case "$PROBE_TIMEOUT" in ''|*[!0-9]*) PROBE_TIMEOUT=5 ;; esac

# ---- Sanity: must be on the HOST, with docker, not inside the container ------
if [ -d /data/.openclaw ] && ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: this looks like INSIDE the OpenClaw container (/data/.openclaw present," >&2
  echo "       no docker CLI). The host watchdog must run on the Docker HOST so it can" >&2
  echo "       'docker restart' a hung container. Re-run on the host." >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker CLI not found on PATH. This installer is for the Docker HOST." >&2
  echo "       (On a Mac use ../mac/service-selfheal/install-service-remediate.sh.)" >&2
  exit 1
fi
if [ ! -f "$SRC_WATCHDOG" ]; then
  echo "ERROR: watchdog source not found at $SRC_WATCHDOG" >&2
  echo "       Run this from a checkout of trevorotts1/openclaw-onboarding so the" >&2
  echo "       box-aware watchdog (platform/mac/service-selfheal/gateway-health-watchdog.sh)" >&2
  echo "       is present in the tree." >&2
  exit 1
fi
if ! command -v crontab >/dev/null 2>&1; then
  echo "ERROR: crontab not found. Install cron (e.g. apt-get install -y cron) and retry." >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "ERROR: curl not found. It is required for the pre-arm reachability probe." >&2
  exit 1
fi

# ---- Resolve the target container (mirror bootstrap.sh multi-container guard) -
CONTAINER="${OPENCLAW_CONTAINER_NAME:-}"
if [ -z "$CONTAINER" ]; then
  _matches="$(docker ps --format '{{.Names}}' 2>/dev/null | grep -E 'openclaw' || true)"
  _count="$(printf '%s\n' "$_matches" | grep -c . || true)"
  if [ "${_count:-0}" -gt 1 ]; then
    echo "ERROR: multiple running OpenClaw containers detected on this host:" >&2
    printf '%s\n' "$_matches" | sed 's/^/  - /' >&2
    echo "       Cannot auto-pick. Re-run with the name explicit:" >&2
    echo "         OPENCLAW_CONTAINER_NAME=<name-from-list-above> bash $0" >&2
    exit 1
  fi
  CONTAINER="$(printf '%s\n' "$_matches" | head -1)"
fi
if [ -z "$CONTAINER" ]; then
  echo "ERROR: no running OpenClaw container found (docker ps | grep openclaw is empty)." >&2
  echo "       Start the container first, or set OPENCLAW_CONTAINER_NAME=<name>." >&2
  exit 1
fi
CUSER="${OPENCLAW_CONTAINER_USER:-}"
if [ -z "$CUSER" ]; then
  CUSER="$(docker inspect "$CONTAINER" --format '{{.Config.User}}' 2>/dev/null || true)"
  [ -z "$CUSER" ] && CUSER="node"
fi

# Run a command inside the resolved container with the gateway CLI on PATH.
# (bootstrap.sh installs the CLI at /data/.npm-global/bin; older images at
# /usr/local/bin.) Never fails the script — every caller guards on the output.
oc_exec() {
  docker exec -u "$CUSER" "$CONTAINER" sh -c \
    'export PATH="/data/.npm-global/bin:/usr/local/bin:$PATH"; '"$1" 2>/dev/null || true
}

# ---- Resolve the host-reachable gateway port --------------------------------
# Precedence: explicit GATEWAY_WATCHDOG_PORT override -> container `openclaw
# gateway status` "Listening: <ip>:<port>" -> container PORT env -> `docker port`
# published mapping for the inner port -> inner port itself (host networking) ->
# the sole published tcp mapping. Whatever we land on is then PROVEN by the
# reachability probe below before we arm anything.
OVERRIDE_PORT="${GATEWAY_WATCHDOG_PORT:-}"
case "$OVERRIDE_PORT" in ''|*[!0-9]*) OVERRIDE_PORT="" ;; esac

INNER_PORT=""
if [ -z "$OVERRIDE_PORT" ]; then
  INNER_PORT="$(oc_exec 'command -v openclaw >/dev/null 2>&1 && openclaw gateway status 2>/dev/null' \
                | grep -iE 'listen' | grep -oE '[0-9]{2,5}' | tail -1 || true)"
  if [ -z "$INNER_PORT" ]; then
    INNER_PORT="$(oc_exec 'printf %s "${PORT:-}"' | grep -oE '^[0-9]{2,5}$' || true)"
  fi
fi

HOST_PORT="$OVERRIDE_PORT"
if [ -z "$HOST_PORT" ] && [ -n "$INNER_PORT" ]; then
  # docker port maps the container-internal port to a host-published "ADDR:PORT".
  _map="$(docker port "$CONTAINER" "$INNER_PORT" 2>/dev/null | head -1 || true)"
  [ -n "$_map" ] && HOST_PORT="$(printf '%s' "$_map" | grep -oE '[0-9]{2,5}$' || true)"
fi
if [ -z "$HOST_PORT" ] && [ -n "$INNER_PORT" ]; then
  # No published mapping -> host networking (network_mode: host) or a loopback-only
  # gateway. With host networking the inner port IS the host port; the probe below
  # decides. (A loopback-only gateway will fail the probe and we refuse — correct.)
  HOST_PORT="$INNER_PORT"
fi
if [ -z "$HOST_PORT" ]; then
  # Inner port unknown: only adopt a published port if there is exactly ONE.
  _allmap="$(docker port "$CONTAINER" 2>/dev/null | grep -iE 'tcp' || true)"
  _mapcount="$(printf '%s\n' "$_allmap" | grep -c . || true)"
  if [ "${_mapcount:-0}" = "1" ]; then
    HOST_PORT="$(printf '%s' "$_allmap" | grep -oE '[0-9]{2,5}$' || true)"
  fi
fi

# ---- Pre-arm reachability gate (the D1 blocker fix) -------------------------
# Probe the EXACT host->container path the cron will use. Two corroborating
# signals (mirrors the watchdog's is_healthy A/B): {"ok":true} on / OR 200 on
# /healthz. A few quick attempts guard against a single transient miss; this only
# ever PREVENTS a false arm, it can never cause a false arm.
probe_reachable() {
  _port="$1"
  case "$_port" in ''|*[!0-9]*) return 1 ;; esac
  _body="$(curl -fsS --max-time "$PROBE_TIMEOUT" "http://127.0.0.1:${_port}/" 2>/dev/null || true)"
  case "$_body" in *'"ok":true'*|*'"ok": true'*) return 0 ;; esac
  _code="$(curl -s -o /dev/null -w '%{http_code}' --max-time "$PROBE_TIMEOUT" \
           "http://127.0.0.1:${_port}/healthz" 2>/dev/null || true)"
  [ "$_code" = "200" ] && return 0
  return 1
}

REACHABLE=0
if [ -n "$HOST_PORT" ]; then
  for _attempt in 1 2 3; do
    if probe_reachable "$HOST_PORT"; then REACHABLE=1; break; fi
    [ "$_attempt" -lt 3 ] && sleep 1 || true
  done
fi

if [ "$REACHABLE" != "1" ]; then
  echo "" >&2
  echo "REFUSING TO ARM the host watchdog cron — could not confirm the gateway is" >&2
  echo "reachable from THIS host at the resolved port." >&2
  echo "" >&2
  echo "  Container         : ${CONTAINER}" >&2
  echo "  Exec user         : ${CUSER}" >&2
  echo "  Inner gw port      : ${INNER_PORT:-<unresolved>}" >&2
  echo "  Host probe port    : ${HOST_PORT:-<unresolved>}" >&2
  echo "  Probed (both failed): http://127.0.0.1:${HOST_PORT:-<port>}/  (no {\"ok\":true})" >&2
  echo "                        http://127.0.0.1:${HOST_PORT:-<port>}/healthz  (no HTTP 200)" >&2
  echo "" >&2
  echo "  A */${INTERVAL_MIN} cron probing an unreachable port would count a HEALTHY" >&2
  echo "  container as failing and 'docker restart' it on a loop. Not arming." >&2
  echo "" >&2
  echo "  Likely causes:" >&2
  echo "    - The gateway is published only on the CONTAINER's loopback (no host -p" >&2
  echo "      mapping) and is reached via the in-container cloudflared tunnel. The host" >&2
  echo "      cannot health-check it directly; the in-container restart policy is the" >&2
  echo "      correct recovery there, not a host cron." >&2
  echo "    - The published host port differs from what was resolved." >&2
  echo "" >&2
  echo "  Investigate, then re-run once you know the host-reachable port:" >&2
  echo "    docker exec -u ${CUSER} ${CONTAINER} openclaw gateway status" >&2
  echo "    docker port ${CONTAINER}" >&2
  echo "    GATEWAY_WATCHDOG_PORT=<host-port> bash $0" >&2
  echo "" >&2
  echo "  Dry-run the watchdog itself (no action taken) to confirm the port first:" >&2
  echo "    GATEWAY_WATCHDOG_PORT=<host-port> GATEWAY_WATCHDOG_DRYRUN=1 /bin/sh \\" >&2
  echo "        \"$SRC_WATCHDOG\" --report-only; tail -n 20 /tmp/gateway-watchdog.log" >&2
  exit 1
fi
echo "Gateway reachable from host at 127.0.0.1:${HOST_PORT} (container: ${CONTAINER}) — proceeding."

# ---- 1) Install the watchdog into a durable host dir ------------------------
mkdir -p "$WATCHDOG_DIR"
cp "$SRC_WATCHDOG" "$DEST_WATCHDOG"
chmod 700 "$DEST_WATCHDOG"
echo "Installed: $DEST_WATCHDOG"

# ---- 2) Install / refresh the */N host crontab entry ------------------------
# Forward the PROVEN host port (GATEWAY_WATCHDOG_PORT + PORT) and the resolved
# container so the watchdog's detect_port() uses the real port FIRST (never its
# 18789 fallback) and docker-restarts the right container. The cron also tees run
# output to a durable host log so it survives a /tmp wipe on reboot.
CRON_ENV="GATEWAY_WATCHDOG_PORT=${HOST_PORT} PORT=${HOST_PORT} OPENCLAW_CONTAINER_NAME=${CONTAINER}"
[ -n "${GATEWAY_WATCHDOG_FAILS:-}" ]    && CRON_ENV="$CRON_ENV GATEWAY_WATCHDOG_FAILS=${GATEWAY_WATCHDOG_FAILS}"
[ -n "${GATEWAY_WATCHDOG_COOLDOWN:-}" ] && CRON_ENV="$CRON_ENV GATEWAY_WATCHDOG_COOLDOWN=${GATEWAY_WATCHDOG_COOLDOWN}"
[ -n "${GATEWAY_WATCHDOG_TIMEOUT:-}" ]  && CRON_ENV="$CRON_ENV GATEWAY_WATCHDOG_TIMEOUT=${GATEWAY_WATCHDOG_TIMEOUT}"
CRON_LINE="*/${INTERVAL_MIN} * * * * ${CRON_ENV} /bin/sh ${DEST_WATCHDOG} >> ${CRON_LOG} 2>&1"

# NOTE on the `|| true` guards below: under `set -euo pipefail`, `crontab -l`
# exits non-zero when the user has no crontab yet, and `grep -vF` exits non-zero
# when it filters out EVERY line (the replace case). Without the guards that
# non-zero would abort the subshell BEFORE `echo "$CRON_LINE"` ran — feeding
# `crontab -` an empty stdin and WIPING the crontab, then aborting the script.
# The guards keep this fail-soft and genuinely idempotent.
if crontab -l 2>/dev/null | grep -qF "gateway-health-watchdog.sh"; then
  # Replace any prior line so the entry stays current + idempotent.
  ( crontab -l 2>/dev/null | grep -vF "gateway-health-watchdog.sh" || true; echo "$CRON_LINE" ) | crontab -
  echo "Updated existing host crontab entry (*/${INTERVAL_MIN} min)"
else
  ( crontab -l 2>/dev/null || true; echo "$CRON_LINE" ) | crontab -
  echo "Installed host crontab entry (*/${INTERVAL_MIN} min)"
fi

# ---- 3) Report --------------------------------------------------------------
echo ""
echo "OK: gateway-health watchdog cron installed on this HOST."
echo "    Script:    $DEST_WATCHDOG"
echo "    Container: $CONTAINER"
echo "    Port:      $HOST_PORT  (confirmed reachable; forwarded as GATEWAY_WATCHDOG_PORT)"
echo "    Cron log:  $CRON_LOG  (durable)"
echo "    Watchdog state/log on vps-host defaults to /tmp/gateway-watchdog.{log,state}."
echo "    It HTTP-probes the gateway and 'docker restart's the openclaw container"
echo "    ONLY after consecutive health failures + cooldown."
echo ""
echo "Verify:   crontab -l | grep gateway-health-watchdog"
echo "Dry-run:  GATEWAY_WATCHDOG_PORT=$HOST_PORT GATEWAY_WATCHDOG_DRYRUN=1 /bin/sh $DEST_WATCHDOG --report-only; tail -n 20 /tmp/gateway-watchdog.log"
