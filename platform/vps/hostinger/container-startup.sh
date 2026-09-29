#!/usr/bin/env bash
# container-startup.sh -- a Hostinger client container's command. The image's
# /entrypoint.sh still runs first (it fixes /data ownership, cds to /hostinger
# and execs this as the node user). Installed by install-startup-hook.sh on the
# host, which copies this file to <project>/data/.openclaw/scripts/ and sets
# the compose `command:` to run it.
#
# Why: `docker compose up -d --force-recreate` starts the container with an
# empty pm2. Without a resurrect the Command Center and the GHL MCP server stay
# down (seen 2026-09-28), and nothing inside the container brings them back.
# Contabo parity: platform/vps/contabo/container-startup.sh.
#
#   1. after the gateway has warmed up, `pm2 resurrect` restores the saved list;
#   2. if the Command Center is still not in pm2 (no saved list, or a list that
#      lacks it), it is started from its own ecosystem file and the list saved;
#   3. ends by exec'ing the image's own server (Hostinger's gateway wrapper).
# Never touches, restarts or signals the gateway.
set -u

DATA="${OPENCLAW_DATA:-/data}"
export PATH="$DATA/.npm-global/bin:$DATA/linuxbrew/.linuxbrew/bin:$PATH"
export NODE_PATH="$DATA/.npm-global/lib/node_modules"
LOGS="$DATA/.openclaw/logs"
CC_DIR="$DATA/projects/command-center"
mkdir -p "$LOGS" 2>/dev/null || true

if command -v pm2 >/dev/null 2>&1; then
  (
    sleep "${PM2_RESURRECT_DELAY:-45}"
    pm2 resurrect >> "$LOGS/pm2-resurrect.log" 2>&1 || true
    if ! pm2 describe blackceo-command-center >/dev/null 2>&1 && [ -f "$CC_DIR/ecosystem.config.cjs" ]; then
      { cd "$CC_DIR" && pm2 start ecosystem.config.cjs && pm2 save; } >> "$LOGS/pm2-resurrect.log" 2>&1 || true
    fi
  ) &
fi

exec node server.mjs
