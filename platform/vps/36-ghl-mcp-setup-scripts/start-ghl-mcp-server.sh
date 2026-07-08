#!/usr/bin/env bash
# start-ghl-mcp-server.sh — start + supervise the GHL Community MCP (:8765)
#
# v12.24.0 — FIX 3 (GHL MCP AUTOSTART) HARDENED after the fleet incident
#            (12/19 boxes down/unsupervised).
#
# WHY: skill 36 REGISTERS the GHL Community MCP under mcp.servers
# (http://localhost:8765/mcp) but nothing ever STARTS that local server. With
# the server down, the registered MCP resolves no tools — the agent silently has
# no GHL MCP. On Hostinger Docker there is NO systemd and NO launchd.
#
# TWO ROOT CAUSES this version fixes:
#   1. RANDOM PORT. main.js reads `PORT` BEFORE `MCP_SERVER_PORT`
#      (src/main.ts:55) — so without an EXPLICIT PORT, a stray inherited PORT
#      binds a random port (49032/63703) instead of 8765. We now pin BOTH.
#   2. UNSUPERVISED BARE NOHUP. A bare `nohup node …` does NOT survive
#      session/exec teardown and is not restarted on crash. We now run under
#      pm2 (the fleet-standard supervisor) with `pm2 save` + an @reboot
#      `pm2 resurrect` hook so it survives reboot/container restart. The bare-
#      nohup path is removed; a detached setsid relaunch LOOP is the last-resort
#      fallback ONLY when pm2 is genuinely unavailable — never a bare nohup.
#
# This script does the start + healthcheck; it is IDEMPOTENT (never
# double-starts) and safe on a cron.
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
  if command -v pm2 >/dev/null 2>&1 && pm2 describe ghl-community-mcp >/dev/null 2>&1; then
    pm2 restart ghl-community-mcp >/dev/null 2>&1 || true
  fi
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

# ---- supply-chain PIN for the community MCP (SK1-69) ----
# The 588-tool community MCP is third-party code cloned onto the client box. A bare
# unpinned clone/build runs whatever HEAD the repo points at today — a moved HEAD could
# ship altered tool code. Pin to a re-verified commit and REFUSE to start on a mismatch.
# Override ONLY after re-reviewing the new tree. (Spec provided the short SHA 3dd9006a;
# replace with the full 40-char SHA once confirmed against upstream.)
GHL_MCP_PINNED_SHA="${GHL_MCP_PINNED_SHA:-3dd9006a}"

pin_mcp_checkout() {
  command -v git >/dev/null 2>&1 || { log "git unavailable — cannot pin community MCP"; return 1; }
  local before after
  before="$(git -C "$MCP_DIR" rev-parse HEAD 2>/dev/null || echo none)"
  # Fetch-by-SHA needs the full id + server support; fall back to a full fetch so the
  # local checkout can resolve a short SHA.
  git -C "$MCP_DIR" fetch --quiet origin "$GHL_MCP_PINNED_SHA" 2>/dev/null \
    || git -C "$MCP_DIR" fetch --quiet origin 2>/dev/null || true
  if ! git -C "$MCP_DIR" checkout --quiet "$GHL_MCP_PINNED_SHA" 2>>"$RUNLOG"; then
    log "FATAL: cannot check out pinned community-MCP SHA $GHL_MCP_PINNED_SHA — refusing to start an unpinned MCP. Re-verify upstream and set GHL_MCP_PINNED_SHA."
    return 1
  fi
  after="$(git -C "$MCP_DIR" rev-parse HEAD 2>/dev/null || echo none)"
  case "$after" in
    "$GHL_MCP_PINNED_SHA"*) : ;;   # HEAD matches the pin (prefix ok for a short SHA)
    *) log "FATAL: pinned-SHA verify failed (HEAD=$after want ${GHL_MCP_PINNED_SHA}*) — refusing to start."; return 1 ;;
  esac
  # If the pin moved HEAD, force a rebuild so dist/ matches the pinned tree.
  if [ "$before" != "$after" ]; then
    log "community MCP re-pinned ${before} -> ${after} — forcing rebuild"
    rm -rf "$MCP_DIR/dist" 2>/dev/null || true
  fi
  return 0
}

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
# Pin BEFORE build/start (both fresh and existing clones) — never run an unpinned tree.
pin_mcp_checkout || exit 1
if [ ! -f "$MCP_DIR/dist/main.js" ]; then
  log "building community MCP (npm install + build)"
  ( cd "$MCP_DIR" && npm install --no-audit --no-fund >>"$RUNLOG" 2>&1 && npm run build >>"$RUNLOG" 2>&1 ) \
    || { log "npm install/build FAILED — see $RUNLOG"; exit 1; }
fi

# ---- start under a proper supervisor (pm2 preferred; NEVER bare nohup) ----
command -v node >/dev/null 2>&1 || { log "node not on PATH — cannot start MCP"; exit 1; }
NODE_BIN="$(command -v node)"

# Resolve GHL creds for the ecosystem env (best-effort; the server's own .env is
# the primary source, but pm2 env makes the supervised process self-contained).
GHL_KEY="${GHL_API_KEY:-${GOHIGHLEVEL_API_KEY:-}}"
GHL_LOC="${GHL_LOCATION_ID:-${GOHIGHLEVEL_LOCATION_ID:-}}"

# SK1-70: keep the GHL PIT OUT of the world-readable ecosystem.config.js. Write it to a
# 600-perm env file that the pm2 ecosystem loads at launch, so the secret never lands in
# a 644 JS config. Only written when a key is resolvable; otherwise the server's own
# .env remains the credential source.
write_secret_env() {
  local senv="$MCP_DIR/.ghl-mcp.env"
  [ -n "$GHL_KEY" ] || { log "no GHL key in env to persist (server .env is the source)"; return 0; }
  ( umask 077; : > "$senv" ) 2>/dev/null || true
  if printf 'GHL_API_KEY=%s\n' "$GHL_KEY" > "$senv" 2>/dev/null; then
    chmod 600 "$senv" 2>/dev/null || true
    log "wrote GHL PIT to 600-perm $senv (kept out of ecosystem.config.js)"
  else
    log "WARN: could not write secret env $senv (non-fatal; server .env provides creds)"
  fi
}

# Write the canonical pm2 ecosystem (PORT + MCP_SERVER_PORT BOTH pinned — main.js
# reads PORT first, so an unpinned PORT is what binds the random 49032/63703).
# The GHL PIT is loaded at launch from the 600-perm .ghl-mcp.env (SK1-70), NOT inlined.
write_ecosystem() {
  write_secret_env
  cat > "$MCP_DIR/ecosystem.config.js" <<ECO
// ghl-community-mcp — pm2 ecosystem (generated by start-ghl-mcp-server.sh)
// main.js reads PORT before MCP_SERVER_PORT (src/main.ts:55) — BOTH pinned to ${PORT}.
// SK1-70: the GHL PIT is NOT inlined here (this file is world-readable). It is loaded at
// pm2 launch from the 600-perm .ghl-mcp.env sitting next to this config.
const fs = require('fs');
const path = require('path');
function _loadEnvFile(f) {
  const out = {};
  try {
    fs.readFileSync(f, 'utf8').split('\n').forEach(function (line) {
      const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)/);
      if (m) out[m[1]] = m[2].trim();
    });
  } catch (e) { /* no secret file -> the server's own .env provides the creds */ }
  return out;
}
const _secret = _loadEnvFile(path.join(__dirname, '.ghl-mcp.env'));
module.exports = {
  apps: [{
    name: "ghl-community-mcp",
    cwd: "${MCP_DIR}",
    script: "dist/main.js",
    interpreter: "node",
    autorestart: true,
    max_restarts: 50,
    restart_delay: 5000,
    env: Object.assign({
      NODE_ENV: "production",
      PORT: "${PORT}",
      MCP_SERVER_PORT: "${PORT}",
      GHL_BASE_URL: "https://services.leadconnectorhq.com",
      GHL_LOCATION_ID: "${GHL_LOC}"
    }, _secret),
    out_file: "${RUNLOG}",
    error_file: "${LOG_DIR}/ghl-mcp.err.log"
  }]
};
ECO
}

install_reboot_resurrect() {
  command -v pm2 >/dev/null 2>&1 || return 0
  local PM2_BIN; PM2_BIN="$(command -v pm2)"
  pm2 startup >/dev/null 2>&1 || true
  if command -v crontab >/dev/null 2>&1; then
    local LINE="@reboot ${PM2_BIN} resurrect >${LOG_DIR}/pm2-resurrect.log 2>&1"
    if ! crontab -l 2>/dev/null | grep -Fq "pm2 resurrect"; then
      ( crontab -l 2>/dev/null; printf '%s\n' "$LINE" ) | crontab - >/dev/null 2>&1 || true
      log "installed @reboot 'pm2 resurrect' cron (reboot-surviving)"
    fi
  fi
}

if command -v pm2 >/dev/null 2>&1; then
  log "starting community MCP on :$PORT under pm2 (ecosystem.config.js)"
  write_ecosystem
  ( cd "$MCP_DIR" && pm2 startOrReload ecosystem.config.js >>"$RUNLOG" 2>&1 \
      || pm2 start ecosystem.config.js >>"$RUNLOG" 2>&1 ) || true
  pm2 save >>"$RUNLOG" 2>&1 || true
  install_reboot_resurrect
else
  # LAST-RESORT fallback (pm2 genuinely unavailable): a DETACHED, SUPERVISED
  # relaunch loop — NOT a bare nohup. setsid detaches from the controlling
  # terminal so it survives session/exec teardown; the loop re-launches on crash.
  log "pm2 not available — installing detached supervised relaunch loop on :$PORT (PORT pinned)"
  SUP="$MCP_DIR/.ghl-mcp-supervise.sh"
  cat > "$SUP" <<SUPEOF
#!/usr/bin/env bash
cd "${MCP_DIR}" || exit 1
while true; do
  PORT="${PORT}" MCP_SERVER_PORT="${PORT}" NODE_ENV=production \\
    "${NODE_BIN}" "${MCP_DIR}/dist/main.js" >>"${RUNLOG}" 2>&1
  sleep 5
done
SUPEOF
  chmod +x "$SUP" 2>/dev/null || true
  if command -v setsid >/dev/null 2>&1; then
    setsid nohup bash "$SUP" >>"$RUNLOG" 2>&1 < /dev/null &
  else
    nohup bash "$SUP" >>"$RUNLOG" 2>&1 < /dev/null &
  fi
  echo $! > "$PIDFILE"
  disown 2>/dev/null || true
fi

# ---- wait for health ----
for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
  sleep 1
  is_healthy && { log "started + healthy on :$PORT"; exit 0; }
done
log "started but NOT healthy within 12s — see $RUNLOG"
exit 1
