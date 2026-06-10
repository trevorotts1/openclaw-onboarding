#!/usr/bin/env bash
# start-ghl-mcp-server.sh — start + supervise the GHL Community MCP (:8765)
#
# v10.16.48 — FIX 3 (GHL MCP AUTOSTART).
#
# WHY: skill 36 REGISTERS the GHL Community MCP under mcp.servers
# (http://localhost:8765/mcp) but nothing ever STARTS that local server. With
# the server down, the registered MCP resolves no tools — the agent silently has
# no GHL MCP. On Hostinger Docker there is NO systemd and NO launchd, so the
# INSTALL.md's systemd unit never runs. The supported supervision here is:
# container nohup (persistent background process) + a :8765 healthcheck + an
# auto-restart cron (installed by the caller). This script does the start +
# healthcheck half; it is IDEMPOTENT (never double-starts) and safe on a cron.
#
# Usage:
#   start-ghl-mcp-server.sh            # start if not healthy, else no-op
#   start-ghl-mcp-server.sh --health   # exit 0 iff :8765 is healthy (no start)
#   start-ghl-mcp-server.sh --restart  # force restart
#
# Exit codes: 0 = healthy (running), 1 = not healthy / could not start.

set -u

PORT="${GHL_MCP_PORT:-8765}"
HEALTH_URL="http://localhost:${PORT}/health"

# Canonical clone dir (matches INSTALL.md Action 5.2 VPS path).
if [ -d /data ]; then
  MCP_DIR="${GHL_MCP_DIR:-/data/mcp-servers/ghl-community-mcp}"
  LOG_DIR="/data/logs"
else
  MCP_DIR="${GHL_MCP_DIR:-$HOME/mcp-servers/ghl-community-mcp}"
  LOG_DIR="$HOME/Library/Logs/ghl-mcp"
fi
PIDFILE="${MCP_DIR}/.ghl-mcp.pid"
RUNLOG="${LOG_DIR}/ghl-mcp.log"
mkdir -p "$LOG_DIR" 2>/dev/null || true

log() { printf '%s [start-ghl-mcp] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# ---- healthcheck: is the community MCP answering on :8765? ----
# Cognee also squats some ports; require the GHL server's tool count, not just a
# 200, so we don't mistake a different service for the GHL MCP.
is_healthy() {
  command -v curl >/dev/null 2>&1 || return 1
  local body
  body=$(curl -fsS --max-time 5 "$HEALTH_URL" 2>/dev/null) || return 1
  # GHL community MCP /health => {"status":"healthy","tools":<n>,...}
  printf '%s' "$body" | grep -qiE '"?status"?\s*:\s*"?healthy' || return 1
  # Reject Cognee's "ready"/version response masquerading on the port.
  printf '%s' "$body" | grep -qiE 'cognee' && return 1
  return 0
}

case "${1:-}" in
  --health)
    is_healthy && { log "healthy on :$PORT"; exit 0; } || { log "NOT healthy on :$PORT"; exit 1; }
    ;;
esac

# ---- force restart path ----
if [ "${1:-}" = "--restart" ]; then
  if [ -f "$PIDFILE" ]; then
    OLDPID=$(cat "$PIDFILE" 2>/dev/null)
    [ -n "$OLDPID" ] && kill "$OLDPID" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
fi

# ---- idempotency: already healthy => do NOT double-start ----
if is_healthy; then
  log "already healthy on :$PORT — no start needed (idempotent)"
  exit 0
fi

# ---- a recorded PID is still alive but not yet healthy => give it a beat ----
if [ -f "$PIDFILE" ]; then
  PID=$(cat "$PIDFILE" 2>/dev/null)
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    log "pid $PID alive but not healthy yet; waiting briefly"
    for _ in 1 2 3 4 5 6; do sleep 1; is_healthy && { log "became healthy"; exit 0; }; done
    log "pid $PID alive but still not healthy — restarting"
    kill "$PID" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
fi

# ---- ensure the server is built (idempotent) ----
if [ ! -d "$MCP_DIR/.git" ]; then
  log "community MCP not cloned at $MCP_DIR — cloning"
  mkdir -p "$(dirname "$MCP_DIR")" 2>/dev/null || true
  if command -v git >/dev/null 2>&1; then
    git clone https://github.com/busybee3333/Go-High-Level-MCP-2026-Complete.git "$MCP_DIR" >>"$RUNLOG" 2>&1 \
      || { log "git clone FAILED — cannot start"; exit 1; }
  else
    log "git not available — cannot clone community MCP"; exit 1
  fi
fi
if [ ! -f "$MCP_DIR/dist/main.js" ]; then
  log "building community MCP (npm install + build)"
  ( cd "$MCP_DIR" && npm install --no-audit --no-fund >>"$RUNLOG" 2>&1 && npm run build >>"$RUNLOG" 2>&1 ) \
    || { log "npm install/build FAILED — see $RUNLOG"; exit 1; }
fi

# ---- start under nohup (container-supervised; NO systemd/launchd) ----
command -v node >/dev/null 2>&1 || { log "node not on PATH — cannot start MCP"; exit 1; }
log "starting community MCP on :$PORT via nohup"
( cd "$MCP_DIR" && MCP_SERVER_PORT="$PORT" NODE_ENV=production \
    nohup node "$MCP_DIR/dist/main.js" >>"$RUNLOG" 2>&1 & echo $! > "$PIDFILE" )

# ---- wait for health ----
for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
  sleep 1
  is_healthy && { log "started + healthy on :$PORT (pid $(cat "$PIDFILE" 2>/dev/null))"; exit 0; }
done
log "started but NOT healthy within 12s — see $RUNLOG"
exit 1
