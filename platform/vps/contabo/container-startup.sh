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
#   4. the saved process list is resurrected at boot ONLY after the RETIRED
#      community GHL MCP has been stripped out of it — this script no longer
#      invokes the GHL MCP autostart at all (GHL_MCP_RETIRED), and nothing it
#      runs may bring that service back;
#   5. $HOME/{999-setup,.claude,.local} live in <volume>/persist-home (symlinked
#      back on every boot), so a recreate keeps the 999 repo, the ~/.claude skill
#      links and pip --user packages;
#   6. wait-gateway-owner-stale.sh runs right before the gateway exec (a fast
#      `docker restart` otherwise leaves the gateway dead: "cannot verify
#      Gateway ownership"). Copy it beside this file in <volume>/scripts/.
# Compose must ALSO set PATH and PM2_HOME in `environment:` (see README.md):
# this script only covers its own process tree, not later `docker exec` shells.
# Never touches, restarts or signals the gateway; it ends by exec'ing it.
set -u

OC="${OPENCLAW_ROOT:-$HOME/.openclaw}"
export PATH="$OC/npm-global/bin:$PATH"
export PM2_HOME="${PM2_HOME:-$OC/.pm2}"
# Master files (company folders, playbooks) on the volume, never in the
# temporary $HOME/Downloads that a recreate wipes. For the gateway's own
# processes; shared-utils/detect_platform.py resolves the same path for the
# others, and compose can set it too (see README.md).
export MASTER_FILES_DIR="${MASTER_FILES_DIR:-$OC/openclaw-master-files}"
LOGS="$OC/logs"
mkdir -p "$LOGS" "$PM2_HOME" 2>/dev/null || true

# A login shell (the fleet roll's `docker exec ... bash -l`) takes PATH from
# /etc/profile, which drops the npm-global bin, so pm2 is "not found" unless
# ~/.profile puts it back. HOME is ephemeral: write it on every start.
PROFILE_PATH_LINE="export PATH=\"$OC/npm-global/bin:\$PATH\"  # openclaw npm-global"
grep -qxF "$PROFILE_PATH_LINE" "$HOME/.profile" 2>/dev/null \
  || printf '%s\n' "$PROFILE_PATH_LINE" >> "$HOME/.profile" 2>/dev/null || true

# A real folder already at $HOME/.pm2 (a stray daemon's home) is moved aside,
# never deleted, then replaced by the link.
if [ ! -L "$HOME/.pm2" ]; then
  [ -e "$HOME/.pm2" ] && mv "$HOME/.pm2" "$HOME/.pm2.stray-$(date -u +%Y%m%dT%H%M%SZ)" 2>/dev/null
  ln -sfn "$PM2_HOME" "$HOME/.pm2" 2>/dev/null || true
fi

# Only /home/node/.openclaw (the volume) survives a recreate. Keep the real copies of these
# home folders there and symlink them back on every boot. Idempotent: a symlink is left alone;
# a real folder is merged into the persistent copy without overwriting (cp -an) and removed
# only if every file in it now exists in the persistent copy; then the link is made. Fail-soft.
# (cp -n exits non-zero when it skips an existing file on BSD and newer GNU cp, so its exit
# status cannot be the success test.)
_merged() { ( cd "$1" && find . -mindepth 1 ! -type d -print ) | while IFS= read -r _f; do
  [ -e "$2/$_f" ] || [ -L "$2/$_f" ] || exit 1; done; }
PERSIST_HOME="$OC/persist-home"
mkdir -p "$PERSIST_HOME" 2>/dev/null || true
for _n in 999-setup .claude .local; do
  _p="$HOME/$_n"; _d="$PERSIST_HOME/$_n"
  [ -L "$_p" ] && continue
  mkdir -p "$_d" 2>/dev/null || continue
  if [ -d "$_p" ]; then
    cp -an "$_p"/. "$_d"/ 2>/dev/null; _merged "$_p" "$_d" && rm -rf "$_p"
  fi
  [ -e "$_p" ] || ln -s "$_d" "$_p" 2>/dev/null || true
done

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

# The wait runs first so its (up to 120 s) delay is not charged to the gateway-ready cap.
WAIT_SCRIPT="${GW_WAIT_SCRIPT:-$OC/scripts/wait-gateway-owner-stale.sh}"
[ -f "$WAIT_SCRIPT" ] && { OPENCLAW_ROOT="$OC" bash "$WAIT_SCRIPT" >> "$LOGS/wait-gateway-owner-stale.boot.log" 2>&1 || true; }

# The community GHL MCP (Tier 2) is RETIRED — GHL_MCP_RETIRED. This boot path
# used to invoke its autostart script here, gated on a real /healthz 200; that
# invocation is gone entirely, so there is no start command left in this file.
#
# `pm2 resurrect` needs no CLI, so it still runs once the gateway-first wait
# returns — but pm2 LAUNCHES every app named in dump.pm2, and deleting the
# retired app after the resurrect would still have started it once. The dump is
# therefore stripped FIRST, and when it cannot be proven clean the resurrect is
# skipped rather than run blind (fail closed: a box whose dump is unreadable
# starts no pm2 process at all, which is safe; it is never a retired service).
pm2_dump_excludes_retired() {
  local dump="$PM2_HOME/dump.pm2"
  [ -f "$dump" ] || return 0                       # nothing saved -> nothing to resurrect
  command -v node >/dev/null 2>&1 || return 1      # cannot prove it -> caller must not resurrect
  # node, not python/jq: this container is guaranteed node (it execs the gateway
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

(
  gw_wait_ready || true
  if command -v pm2 >/dev/null 2>&1; then
    if pm2_dump_excludes_retired; then
      pm2 resurrect >> "$LOGS/pm2-resurrect.log" 2>&1 || true
    else
      echo "[$(date -u +%FT%TZ)] dump.pm2 could not be proven free of the RETIRED community MCP — pm2 resurrect skipped (fail closed)" >> "$LOGS/pm2-resurrect.log" 2>/dev/null || true
    fi
  fi
) &

# The persistent npm-global OpenClaw, never the image's older baked-in copy.
# (The npm-global entry is a non-executable symlink: test for a file.)
OC_MJS="$OC/npm-global/lib/node_modules/openclaw/openclaw.mjs"
[ -f "$OC_MJS" ] && exec node "$OC_MJS" gateway
exec node openclaw.mjs gateway
