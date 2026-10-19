#!/usr/bin/env bash
# container-startup.sh -- a Hostinger client container's command. The image's
# /entrypoint.sh still runs first (it fixes /data ownership, cds to /hostinger
# and execs this as the node user). Installed by install-startup-hook.sh on the
# host, which copies this file to <project>/data/.openclaw/scripts/ and sets
# the compose `command:` to run it.
#
# Why: `docker compose up -d --force-recreate` starts the container with an
# empty pm2. Without a resurrect the Command Center stays down (seen
# 2026-09-28), and nothing inside the container brings it back. The community
# GHL MCP is RETIRED (GHL_MCP_RETIRED) and is deliberately NOT one of the
# things a boot restores: its entry is stripped out of the saved list first.
# Contabo parity: platform/vps/contabo/container-startup.sh.
#
#   0. the boot patcher hostinger-wrapper-patch.py (if present in
#      $DATA/.openclaw/scripts) neutralises the wrapper's harmful boot writes, including the
#      re-created legacy agents/main/agent/auth-profiles.json (fail-soft);
#   1. once the gateway answers /healthz 200, `pm2 resurrect` restores the saved
#      list WITH the RETIRED community GHL MCP entry stripped out of it first
#      (nothing that may call the openclaw CLI runs before that);
#   2. if the Command Center is still not in pm2 (no saved list, or a list that
#      lacks it), it is started from its own ecosystem file and the list saved;
#   3. wait-gateway-owner-stale.sh runs right before the exec (a fast `docker restart`
#      otherwise leaves the gateway dead: "cannot verify Gateway ownership");
#   4. ends by exec'ing the image's own server (Hostinger's gateway wrapper).
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


# GATEWAY-FIRST (2026-10-12): on openclaw 2026.10.1 an `openclaw` CLI call made while NO gateway
# owns the state database takes the offline "sqlite-maintenance" lock, and the gateway then dies
# at bootstrap ("state ... is undergoing offline maintenance"; seen on Beverly Grandison, a
# crash loop). So nothing that may call the CLI starts until the gateway answers /healthz 200.
# Pure bash (no curl, no openclaw CLI). GW_READY_CAP seconds (default 180) bounds the wait.
GW_PORT="${OPENCLAW_GATEWAY_PORT:-18789}"
gw_healthz_200() {
  ( exec 3<>"/dev/tcp/127.0.0.1/$GW_PORT" \
    && printf 'GET /healthz HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n' >&3 \
    && IFS= read -r -t 5 _line <&3 && case "$_line" in HTTP/*" 200"*) exit 0 ;; esac; exit 1 ) 2>/dev/null
}
gw_wait_ready() {
  local end=$((SECONDS + ${GW_READY_CAP:-180}))
  until gw_healthz_200; do
    [ "$SECONDS" -ge "$end" ] && return 1
    sleep 2
  done
}

# Boot patcher, fail-soft. install-startup-hook.sh copies it to $DATA/.openclaw/scripts/.
HWP="$DATA/.openclaw/scripts/hostinger-wrapper-patch.py"
[ -f "$HWP" ] && { python3 "$HWP" >> "$LOGS/hostinger-wrapper-patch.boot.log" 2>&1 || true; }

# The wait runs first so its (up to 120 s) delay is not charged to the gateway-ready cap.
WAIT_SCRIPT="${GW_WAIT_SCRIPT:-$DATA/.openclaw/scripts/wait-gateway-owner-stale.sh}"
[ -f "$WAIT_SCRIPT" ] && { OPENCLAW_DATA="$DATA" bash "$WAIT_SCRIPT" >> "$LOGS/wait-gateway-owner-stale.boot.log" 2>&1 || true; }

# The community GHL MCP (Tier 2) is RETIRED — GHL_MCP_RETIRED. pm2 LAUNCHES
# every app named in dump.pm2, so deleting the retired app after a resurrect
# would still have started it once: the dump is stripped FIRST, and a dump that
# cannot be proven clean is left alone (resurrect skipped, fail closed — the
# Command Center fallback below then starts the Command Center anyway).
pm2_dump_excludes_retired() {
  local dump="$PM2_HOME/dump.pm2"
  [ -f "$dump" ] || return 0                       # nothing saved -> nothing to resurrect
  command -v node >/dev/null 2>&1 || return 1      # cannot prove it -> caller must not resurrect
  # node, not python/jq: this container is guaranteed node (it execs server.mjs
  # below). Exit 0 = clean (dump rewritten if anything was removed), 1 = unknown.
  node -e '
const fs = require("fs");
const p = process.argv[1];
let list;
try { list = JSON.parse(fs.readFileSync(p, "utf8")); } catch (e) { process.exit(1); }
if (!Array.isArray(list)) { process.exit(1); }
const hit = (s) => /ghl[-_]community[-_]mcp/.test(String(s || ""));
const keep = list.filter((x) => x && !hit(x.name) && !hit(x.pm_exec_path) && !hit(x.script) && !hit(x.pm_exec_path_args));
if (keep.length === list.length) { process.exit(0); }
try { fs.writeFileSync(p, JSON.stringify(keep, null, 2)); } catch (e) { process.exit(1); }
process.exit(0);
' "$dump"
}

if command -v pm2 >/dev/null 2>&1; then
  (
    gw_wait_ready || true   # cap passed: pm2 needs no CLI, so the Command Center still comes up
    if pm2_dump_excludes_retired; then
      pm2 resurrect >> "$LOGS/pm2-resurrect.log" 2>&1 || true
    else
      echo "[$(date -u +%FT%TZ)] dump.pm2 could not be proven free of the RETIRED community MCP — pm2 resurrect skipped (fail closed)" >> "$LOGS/pm2-resurrect.log" 2>/dev/null || true
    fi
    if ! pm2 describe blackceo-command-center >/dev/null 2>&1 && [ -f "$CC_DIR/ecosystem.config.cjs" ]; then
      { cd "$CC_DIR" && pm2 start ecosystem.config.cjs && pm2 save; } >> "$LOGS/pm2-resurrect.log" 2>&1 || true
    fi
  ) &
fi

exec node server.mjs
