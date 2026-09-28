#!/usr/bin/env bash
# container-startup.sh -- a Contabo client container's command (compose
# `command: [bash, /home/node/.openclaw/scripts/container-startup.sh]`).
# Copy it to <volume>/scripts/container-startup.sh when provisioning a box.
#
# Hostinger parity for pm2 (2026-09-28): on Hostinger HOME is the persistent
# /data, so every shell -- including a bare `docker exec` from the fleet roll --
# drives the one pm2 daemon that runs the Command Center. Here HOME
# (/home/node) is the ephemeral container layer, so:
#   1. pm2 lives in the persistent npm-global prefix, first on PATH;
#   2. PM2_HOME is the persistent <volume>/.pm2;
#   3. $HOME/.pm2 is a symlink to it, so a shell WITHOUT PM2_HOME set never
#      spawns an empty second daemon and restarts nothing (seen on two boxes);
#   4. the saved process list (Command Center, GHL MCP) is resurrected at boot.
# Compose must ALSO set PATH and PM2_HOME in `environment:` (see README.md):
# this script only covers its own process tree, not later `docker exec` shells.
# Never touches, restarts or signals the gateway; it ends by exec'ing it.
set -u

OC="${OPENCLAW_ROOT:-$HOME/.openclaw}"
export PATH="$OC/npm-global/bin:$PATH"
export PM2_HOME="${PM2_HOME:-$OC/.pm2}"
LOGS="$OC/logs"
mkdir -p "$LOGS" "$PM2_HOME" 2>/dev/null || true

# A real folder already at $HOME/.pm2 (a stray daemon's home) is moved aside,
# never deleted, then replaced by the link.
if [ ! -L "$HOME/.pm2" ]; then
  [ -e "$HOME/.pm2" ] && mv "$HOME/.pm2" "$HOME/.pm2.stray-$(date -u +%Y%m%dT%H%M%SZ)" 2>/dev/null
  ln -sfn "$PM2_HOME" "$HOME/.pm2" 2>/dev/null || true
fi

if command -v pm2 >/dev/null 2>&1; then
  # After the gateway has warmed up, like Hostinger's delayed resurrect.
  ( sleep "${PM2_RESURRECT_DELAY:-20}"; pm2 resurrect >> "$LOGS/pm2-resurrect.log" 2>&1 || true ) &
fi

AUTOSTART="$OC/scripts/ghl-mcp-autostart.sh"
[ -f "$AUTOSTART" ] && { bash "$AUTOSTART" >> "$LOGS/ghl-mcp-startup.log" 2>&1 & }

# The persistent npm-global OpenClaw, never the image's older baked-in copy.
# (The npm-global entry is a non-executable symlink: test for a file.)
OC_MJS="$OC/npm-global/lib/node_modules/openclaw/openclaw.mjs"
[ -f "$OC_MJS" ] && exec node "$OC_MJS" gateway
exec node openclaw.mjs gateway
