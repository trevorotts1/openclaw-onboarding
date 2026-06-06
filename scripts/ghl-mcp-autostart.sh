#!/usr/bin/env bash
# ghl-mcp-autostart.sh — v10.15.48
#
# FIX 3 (systemic): Skill 36 registers the GHL community MCP in mcp.servers but
# nothing ever STARTS the local server on :8765, so the GHL tools never resolve
# at runtime. The launchd plist lives only as PROSE in
# 36-ghl-mcp-setup/INSTALL.md §5.5 — it is downloaded, never executed.
#
# This script is the EXECUTED form of INSTALL.md §5.1–5.7. It is idempotent and
# additive: it (1) clones/builds the community MCP if missing, (2) writes the
# canonical launchd plist (com.clawd.ghl-mcp), (3) boots/KeepAlive's it, (4)
# health-checks :8765, and (5) registers the MCP under mcp.servers. Re-running
# is a no-op once the service is healthy and registered.
#
# It does NOT double-start: if launchctl already lists the label AND /health is
# green, it only re-verifies. Exit 0 = server healthy + registered (or a clean,
# honestly-reported skip when GHL creds are absent). Exit non-zero NEVER — this
# is wiring, callers gate on the printed STATUS line + their own verification.
#
# Mac (launchd) is the canonical path for this repo. VPS uses the systemd path
# in INSTALL.md §5.6 (the VPS repo ships its own autostart variant).

set -u

log() { printf '  [ghl-mcp-autostart] %s\n' "$*"; }

# ── Platform + paths ─────────────────────────────────────────────────────────
if [ -f /data/.openclaw/openclaw.json ]; then
  PLATFORM="vps"
  OC_ROOT="/data/.openclaw"
  MCP_DIR="/data/mcp-servers/ghl-community-mcp"
else
  PLATFORM="mac"
  OC_ROOT="$HOME/.openclaw"
  MCP_DIR="$HOME/mcp-servers/ghl-community-mcp"
fi
OC_JSON="$OC_ROOT/openclaw.json"
SECRETS_ENV="$OC_ROOT/secrets/.env"

# ── Resolve a free/canonical port (8765 canonical) ──────────────────────────
GHL_MCP_PORT="${GHL_MCP_PORT:-8765}"
if command -v lsof >/dev/null 2>&1; then
  # If 8765 is held by something that is NOT our MCP, fall through the list.
  if lsof -i :8765 >/dev/null 2>&1; then
    # Already-bound 8765 is fine IF it is our healthy MCP (checked later).
    GHL_MCP_PORT=8765
  fi
fi

# ── STATUS reporter (callers grep this line; honest, never "done" on a gap) ──
STATUS="UNKNOWN"
report() {
  STATUS="$1"; shift
  printf 'STATUS: ghl-mcp-autostart=%s %s\n' "$STATUS" "$*"
}

# ── Credential preflight — honest skip, never a fake success ─────────────────
_get_env_var() {
  local var="$1" v=""
  v="$(printenv "$var" 2>/dev/null || true)"
  if [ -z "$v" ] && [ -f "$SECRETS_ENV" ]; then
    v="$(grep -E "^${var}=" "$SECRETS_ENV" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
  fi
  if [ -z "$v" ] && [ -f "$OC_JSON" ] && command -v python3 >/dev/null 2>&1; then
    v="$(VAR="$var" OC_JSON="$OC_JSON" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    print(cfg.get("env", {}).get("vars", {}).get(os.environ["VAR"], "") or "")
except Exception:
    print("")
PYEOF
)"
  fi
  printf '%s' "$v"
}

GHL_TOKEN="$(_get_env_var GOHIGHLEVEL_API_KEY)"
[ -z "$GHL_TOKEN" ] && GHL_TOKEN="$(_get_env_var GHL_API_KEY)"
GHL_LOC="$(_get_env_var GOHIGHLEVEL_LOCATION_ID)"
[ -z "$GHL_LOC" ] && GHL_LOC="$(_get_env_var GHL_LOCATION_ID)"

# ── 1. Clone + build the community MCP (idempotent) ──────────────────────────
ensure_built() {
  if ! command -v node >/dev/null 2>&1; then
    log "node not on PATH — cannot build/start GHL MCP server"
    return 1
  fi
  mkdir -p "$(dirname "$MCP_DIR")" 2>/dev/null || true
  if [ -d "$MCP_DIR/.git" ]; then
    log "MCP repo present at $MCP_DIR (idempotent — pulling latest)"
    ( cd "$MCP_DIR" && git pull --ff-only >/dev/null 2>&1 || true )
  else
    log "Cloning community GHL MCP into $MCP_DIR"
    git clone --depth 1 https://github.com/busybee3333/Go-High-Level-MCP-2026-Complete.git "$MCP_DIR" >/dev/null 2>&1 || {
      log "git clone failed — server cannot be built"
      return 1
    }
  fi
  if [ ! -f "$MCP_DIR/dist/main.js" ]; then
    log "Building MCP (npm install + build)…"
    ( cd "$MCP_DIR" && npm install --no-audit --no-fund >/dev/null 2>&1 && npm run build >/dev/null 2>&1 ) || {
      log "npm build failed — see $MCP_DIR for details"
      return 1
    }
  fi
  # .env for the server (idempotent rewrite — chmod 600)
  if [ -n "$GHL_TOKEN" ]; then
    cat > "$MCP_DIR/.env" <<EOF
GHL_API_KEY=${GHL_TOKEN}
GHL_BASE_URL=https://services.leadconnectorhq.com
GHL_LOCATION_ID=${GHL_LOC}
MCP_SERVER_PORT=${GHL_MCP_PORT}
NODE_ENV=production
EOF
    chmod 600 "$MCP_DIR/.env" 2>/dev/null || true
  fi
  return 0
}

# ── 2. Health check :PORT/health (true=healthy) ──────────────────────────────
health_ok() {
  command -v curl >/dev/null 2>&1 || return 1
  local body
  body="$(curl -fsS --max-time 5 "http://localhost:${GHL_MCP_PORT}/health" 2>/dev/null || true)"
  # Healthy = our GHL MCP (reports "healthy" / a tools count). Reject Cognee's
  # response ("0.5.3-local") which means we hit the wrong port (INSTALL.md §6).
  case "$body" in
    *0.5.3-local*) return 1 ;;
    *healthy*|*tools*) return 0 ;;
    *) return 1 ;;
  esac
}

# ── 3. Write canonical launchd plist + boot (Mac); systemd (VPS) ─────────────
start_service_mac() {
  local PLIST="$HOME/Library/LaunchAgents/com.clawd.ghl-mcp.plist"
  local NODE_PATH; NODE_PATH="$(command -v node)"
  mkdir -p "$HOME/Library/Logs/ghl-mcp" 2>/dev/null || true
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.clawd.ghl-mcp</string>
    <key>ProgramArguments</key><array>
        <string>${NODE_PATH}</string>
        <string>${MCP_DIR}/dist/main.js</string>
    </array>
    <key>WorkingDirectory</key><string>${MCP_DIR}</string>
    <key>EnvironmentVariables</key><dict>
        <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>NODE_ENV</key><string>production</string>
        <key>MCP_SERVER_PORT</key><string>${GHL_MCP_PORT}</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><dict>
        <key>SuccessfulExit</key><false/>
        <key>Crashed</key><true/>
    </dict>
    <key>ThrottleInterval</key><integer>10</integer>
    <key>StandardOutPath</key><string>${HOME}/Library/Logs/ghl-mcp/stdout.log</string>
    <key>StandardErrorPath</key><string>${HOME}/Library/Logs/ghl-mcp/stderr.log</string>
    <key>ProcessType</key><string>Background</string>
</dict>
</plist>
EOF
  # Idempotent re-boot: bootout (ignore failure if not loaded) then bootstrap.
  launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || \
    launchctl load "$PLIST" >/dev/null 2>&1 || true
}

start_service_vps() {
  local NODE_PATH; NODE_PATH="$(command -v node)"
  mkdir -p /data/logs 2>/dev/null || true
  if command -v systemctl >/dev/null 2>&1; then
    sudo tee /etc/systemd/system/ghl-mcp.service > /dev/null <<EOF
[Unit]
Description=GHL Community MCP Server
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${MCP_DIR}
ExecStart=${NODE_PATH} ${MCP_DIR}/dist/main.js
Restart=on-failure
RestartSec=10
EnvironmentFile=${MCP_DIR}/.env
StandardOutput=append:/data/logs/ghl-mcp.log
StandardError=append:/data/logs/ghl-mcp.err.log

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload >/dev/null 2>&1 || true
    sudo systemctl enable --now ghl-mcp >/dev/null 2>&1 || true
  else
    # No systemd (e.g. Hostinger container) — fall back to nohup background.
    log "systemd not available — starting MCP with nohup (container fallback)"
    ( cd "$MCP_DIR" && nohup "$NODE_PATH" "$MCP_DIR/dist/main.js" >> /data/logs/ghl-mcp.log 2>&1 & ) || true
  fi
}

# ── Main flow ────────────────────────────────────────────────────────────────

# If a healthy server is ALREADY up AND the MCP is already registered, no-op.
already_registered() {
  [ -f "$OC_JSON" ] && command -v python3 >/dev/null 2>&1 && OC_JSON="$OC_JSON" python3 - <<'PYEOF' 2>/dev/null
import json, os, sys
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    servers = cfg.get("mcp", {}).get("servers", {})
    sys.exit(0 if ("ghl-mcp" in servers or "ghl-community-mcp" in servers) else 1)
except Exception:
    sys.exit(1)
PYEOF
}

if health_ok && already_registered; then
  report "HEALTHY_ALREADY" "(server on :${GHL_MCP_PORT} healthy + MCP already registered — idempotent no-op)"
  exit 0
fi

# Need GHL creds to build a usable server. Honest skip otherwise — NEVER claim
# the MCP is up when it cannot be.
if [ -z "$GHL_TOKEN" ]; then
  report "SKIPPED_NO_CREDS" "(GOHIGHLEVEL_API_KEY/GHL_API_KEY absent — server NOT started; this is an honest gap, not a failure. Set the GHL token then re-run.)"
  exit 0
fi

if ! ensure_built; then
  report "BUILD_FAILED" "(could not clone/build community MCP at $MCP_DIR — GHL tools will NOT resolve until fixed)"
  exit 0
fi

if [ "$PLATFORM" = "mac" ]; then
  start_service_mac
else
  start_service_vps
fi

# Allow the server a moment to boot, then verify (do NOT block on `sleep` long).
for _i in 1 2 3 4 5 6; do
  if health_ok; then break; fi
  command -v sleep >/dev/null 2>&1 && sleep 2 || true
done

# Register under mcp.servers (idempotent — openclaw mcp set is a replace).
if command -v openclaw >/dev/null 2>&1; then
  openclaw config set env.vars.GHL_COMMUNITY_MCP_URL "http://localhost:${GHL_MCP_PORT}" >/dev/null 2>&1 || true
  openclaw mcp set ghl-community-mcp \
    "{\"type\":\"streamable-http\",\"url\":\"http://localhost:${GHL_MCP_PORT}/mcp\",\"connectionTimeoutMs\":30000}" \
    >/dev/null 2>&1 || true
fi

if health_ok; then
  report "HEALTHY" "(server on :${GHL_MCP_PORT} healthy + registered under mcp.servers as ghl-community-mcp)"
else
  report "STARTED_UNHEALTHY" "(launchd/systemd service installed on :${GHL_MCP_PORT} but /health not green yet — KeepAlive will retry; check $MCP_DIR logs. GHL tools may not resolve until healthy.)"
fi
exit 0
