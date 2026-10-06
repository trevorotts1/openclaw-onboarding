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
#
# pm2 runs as node, NEVER root, with a node-owned PM2_HOME (2026-09-29): a pm2
# daemon at /data/.pm2 running as root ran the Command Center as root, its
# python skill calls left root-owned __pycache__ in the skills tree, and the
# next update refused and rolled the box back. Started as root, this script
# hands PM2_HOME to node and re-runs itself as node.
set -u

DATA="${OPENCLAW_DATA:-/data}"
export PM2_HOME="${PM2_HOME:-$DATA/.pm2}"
if [ "$(id -u)" = "0" ]; then
  mkdir -p "$PM2_HOME" 2>/dev/null || true
  chown -R node:node "$PM2_HOME" 2>/dev/null || true
  exec runuser -u node -- env HOME="$DATA" PATH="$PATH" PM2_HOME="$PM2_HOME" OPENCLAW_DATA="$DATA" bash "$0"
fi
export PATH="$DATA/.npm-global/bin:$DATA/linuxbrew/.linuxbrew/bin:$PATH"
export NODE_PATH="$DATA/.npm-global/lib/node_modules"
LOGS="$DATA/.openclaw/logs"
CC_DIR="$DATA/projects/command-center"
mkdir -p "$LOGS" 2>/dev/null || true

# Headquarters persistent roots (SPEC S10: "Outbox and bridge identity use
# existing persistent workspace locations. Verify container replacement retains
# them"). These are exactly the vps-docker paths in CC src/lib/platform.ts:
#   /data/.openclaw/workspace           -> vault/scratch AND the telemetry roots
#                                          hq-telemetry/correlation + /outbox
#   /data/.openclaw/mission-control/identity -> the paired bridge keypair
#   /data/.openclaw/extensions          -> path-loaded plugins (origin:"config")
# They sit under $DATA, the persistent mount, so a `--force-recreate` keeps
# them. This block only CREATES what is missing — mkdir -p, never a delete, a
# move or a truncate — and it runs as node (the root pass re-execs above, and
# the image's own /entrypoint.sh has already fixed /data ownership), so a
# directory created here is node-owned and the telemetry plugin's own mkdir
# succeeds. Idempotent by construction.
HQ_ROOT="$DATA/.openclaw"
for _hq_dir in "$HQ_ROOT/workspace" "$HQ_ROOT/workspace/hq-telemetry/correlation" \
               "$HQ_ROOT/workspace/hq-telemetry/outbox" \
               "$HQ_ROOT/mission-control/identity" "$HQ_ROOT/extensions"; do
  mkdir -p "$_hq_dir" 2>/dev/null || true
done

# Headquarters availability flag written by vps-docker-bootstrap.sh step 8d /
# run-full-install.sh phase 6k. Report the box's own recorded value; absent
# means the capability check has not run yet, which is NOT "enabled". One line
# per start, always written, so the box's own view is never silent.
_HQ_FLAG=""
if [ -f "$HQ_ROOT/.env" ]; then
  # The value is written by the shared service-env encoder, which may quote it
  # (`HEADQUARTERS_ENABLED='1'`), so surrounding single/double quotes are
  # stripped here. Reader-side tolerance only — the writer stays the one
  # canonical encoder.
  _HQ_FLAG="$(sed -n 's/^[[:space:]]*\(export[[:space:]]*\)\{0,1\}HEADQUARTERS_ENABLED[[:space:]]*=[[:space:]]*//p' "$HQ_ROOT/.env" | tail -1 | sed -e "s/^'\(.*\)'$/\1/" -e 's/^"\(.*\)"$/\1/')"
fi
case "$_HQ_FLAG" in
  1) echo "[hq] HEADQUARTERS_ENABLED=1 (capture advertised)" >> "$LOGS/container-startup.log" ;;
  0) echo "[hq] HEADQUARTERS_ENABLED=0 (capability unavailable; see $HQ_ROOT/.env)" >> "$LOGS/container-startup.log" ;;
  *) echo "[hq] HEADQUARTERS_ENABLED unset — capability check has not run on this box" >> "$LOGS/container-startup.log" ;;
esac

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
