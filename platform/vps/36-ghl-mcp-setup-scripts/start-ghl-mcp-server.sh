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
# TWO ROOT CAUSES v12.24.0 fixed:
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
# v21.5.0 — this overlay now shares ONE pin/profile source of truth with
# scripts/ghl-mcp-autostart.sh (config/ghl-mcp-pin.env) and inherits the same
# five fixes:
#   D1 stale-dist deafness  — rebuild is keyed to the pin + a build stamp + a
#                             literal artifact assertion, never to "dist exists".
#   D2 858-tool init tax    — GHL_TOOL_PROFILE pinned in every launch surface.
#   D3 bad-token crash loop — crash-only via the .ghl-mcp-launch.sh wrapper +
#                             pm2 stop_exit_codes:[0] / systemd Restart=on-failure.
#   D4 build crash          — build a `git archive` of the pinned commit in a
#                             temp dir; swap dist/ only on success (upstream's
#                             build rm -rf's dist BEFORE compiling and walks
#                             every .ts under src/, including orphaned
#                             node_modules).
#   D5 no liveness proof    — verification is a JSON-RPC response, not a socket.
#
# This script does the start + healthcheck; it is IDEMPOTENT (never
# double-starts) and safe on a cron.
#
# Usage:
#   start-ghl-mcp-server.sh            # start if not healthy, else no-op
#   start-ghl-mcp-server.sh --health   # exit 0 iff :8765 answers JSON-RPC (no start)
#   start-ghl-mcp-server.sh --restart  # force restart
#
# Exit codes: 0 = healthy (running), 1 = not healthy / could not start.

set -u

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# ── Shared pin + profile (single source of truth) ────────────────────────────
for _c in "$SELF_DIR/../../../config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/onboarding/config/ghl-mcp-pin.env" \
          "/data/.openclaw/onboarding/config/ghl-mcp-pin.env" \
          "/data/.openclaw/skills/config/ghl-mcp-pin.env"; do
  # shellcheck disable=SC1090
  [ -f "$_c" ] && { . "$_c"; break; }
done
GHL_MCP_VETTED_COMMIT="${GHL_MCP_VETTED_COMMIT:-bfc2bbe15a4090b82351593b6ca52eed7a8dbbe3}"
GHL_MCP_TOOL_PROFILE="${GHL_TOOL_PROFILE:-${GHL_MCP_TOOL_PROFILE:-curated}}"
GHL_MCP_REPO_URL="${GHL_MCP_REPO_URL:-https://github.com/busybee3333/Go-High-Level-MCP-2026-Complete.git}"
GHL_MCP_PROBE_TIMEOUT="${GHL_MCP_PROBE_TIMEOUT:-10}"
GHL_MCP_LOG_MAX_BYTES="${GHL_MCP_LOG_MAX_BYTES:-10485760}"
GHL_MCP_LOG_KEEP="${GHL_MCP_LOG_KEEP:-3}"

PORT="${GHL_MCP_PORT:-8765}"
HEALTH_URL="http://localhost:${PORT}/health"
MCP_URL="http://localhost:${PORT}/mcp"

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
BUILD_STAMP="${MCP_DIR}/.ghl-mcp-build.json"
LAUNCHER="${MCP_DIR}/.ghl-mcp-launch.sh"
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

# ---- D5: liveness = a JSON-RPC ANSWER, not an open socket ----
# /health is served by express before the MCP transport is wired: a stale/deaf
# dist returns {"status":"healthy"} while every agent init hangs the full
# connectionTimeoutMs. Only an `initialize` round-trip proves the server is alive.
responds_ok() {
  command -v curl >/dev/null 2>&1 || return 1
  curl -sS --max-time "$GHL_MCP_PROBE_TIMEOUT" -X POST "$MCP_URL" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"start-ghl-mcp","version":"1"}}}' \
    2>/dev/null | grep -q 'serverInfo'
}

case "${1:-}" in
  --health)
    if is_healthy && responds_ok; then log "healthy + answering JSON-RPC on :$PORT"; exit 0; fi
    if is_healthy; then log "DEAF on :$PORT (/health green, no JSON-RPC response in ${GHL_MCP_PROBE_TIMEOUT}s)"; exit 1; fi
    log "NOT healthy on :$PORT"; exit 1
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

# ---- idempotency: already healthy AND answering => do NOT double-start ----
if is_healthy && responds_ok; then
  log "already healthy + answering on :$PORT — no start needed (idempotent)"
  exit 0
fi

# ---- a recorded PID is still alive but not yet healthy => give it a beat ----
if [ -f "$PIDFILE" ]; then
  PID=$(cat "$PIDFILE" 2>/dev/null)
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    log "pid $PID alive but not healthy yet; waiting briefly"
    for _ in 1 2 3 4 5 6; do sleep 1; is_healthy && responds_ok && { log "became healthy"; exit 0; }; done
    log "pid $PID alive but still not answering — restarting"
    kill "$PID" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
fi

# ---- supply-chain PIN for the community MCP (SK1-69, hardened v21.5.0) ----
# The community MCP is third-party code cloned onto the client box. An unpinned
# clone/build runs whatever HEAD upstream points at today — and upstream
# force-pushes rewritten history, so "today's main" is not reproducible. Pin to
# the VETTED FULL 40-char commit from config/ghl-mcp-pin.env and REFUSE to start
# on a mismatch. Override ONLY after re-reviewing the new tree.
case "$GHL_MCP_VETTED_COMMIT" in
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) : ;;
  *) log "FATAL: GHL_MCP_VETTED_COMMIT is not a full 40-char SHA — refusing to start an unpinned MCP."; exit 1 ;;
esac

quarantine_src_orphans() {
  [ -d "$MCP_DIR/src" ] || return 0
  local q found=0
  q="$MCP_DIR/.quarantine-$(date -u +%Y%m%dT%H%M%SZ)"
  while IFS= read -r nm; do
    [ -n "$nm" ] || continue
    mkdir -p "$q" 2>/dev/null || true
    mv "$nm" "$q/$(printf '%s' "${nm#"$MCP_DIR/"}" | tr '/' '_')" 2>/dev/null && found=1
  done <<EOF
$(find "$MCP_DIR/src" -type d -name node_modules -maxdepth 6 2>/dev/null)
EOF
  [ "$found" = "1" ] && log "quarantined orphaned node_modules under src/ -> $q (they crash upstream's build)"
  return 0
}

pin_mcp_checkout() {
  command -v git >/dev/null 2>&1 || { log "git unavailable — cannot pin community MCP"; return 1; }
  git -C "$MCP_DIR" fetch --quiet origin "$GHL_MCP_VETTED_COMMIT" 2>/dev/null \
    || git -C "$MCP_DIR" fetch --quiet --tags origin 2>/dev/null || true
  if ! git -C "$MCP_DIR" cat-file -e "${GHL_MCP_VETTED_COMMIT}^{commit}" 2>/dev/null; then
    git -C "$MCP_DIR" fetch --quiet --unshallow origin 2>/dev/null || true
  fi
  if ! git -C "$MCP_DIR" cat-file -e "${GHL_MCP_VETTED_COMMIT}^{commit}" 2>/dev/null; then
    log "FATAL: pinned commit $GHL_MCP_VETTED_COMMIT unreachable from origin — refusing to start an unpinned MCP."
    return 1
  fi
  quarantine_src_orphans
  if ! git -C "$MCP_DIR" checkout --quiet --detach --force "$GHL_MCP_VETTED_COMMIT" 2>>"$RUNLOG"; then
    log "FATAL: cannot check out pinned SHA $GHL_MCP_VETTED_COMMIT — refusing to start."
    return 1
  fi
  local after; after="$(git -C "$MCP_DIR" rev-parse HEAD 2>/dev/null || echo none)"
  [ "$after" = "$GHL_MCP_VETTED_COMMIT" ] || { log "FATAL: pin verify failed (HEAD=$after)"; return 1; }
  return 0
}

# ---- D1/D4: build the PINNED tree in a temp dir; swap dist/ only on success --
dist_is_sane() {
  [ -s "$MCP_DIR/dist/main.js" ] || return 1
  grep -q 'connect(transport)' "$MCP_DIR/dist/main.js" 2>/dev/null || return 1
  return 0
}
stamp_matches() {
  [ -f "$BUILD_STAMP" ] || return 1
  grep -q "\"commit\": *\"$GHL_MCP_VETTED_COMMIT\"" "$BUILD_STAMP" 2>/dev/null || return 1
  return 0
}
build_pinned() {
  command -v npm >/dev/null 2>&1 || { log "npm not on PATH — cannot build"; return 1; }
  local tmp rc=0 ts
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/ghl-mcp-build.XXXXXX")" || return 1
  log "building pinned tree ${GHL_MCP_VETTED_COMMIT} in $tmp (the working tree is NEVER built)"
  if ! git -C "$MCP_DIR" archive "$GHL_MCP_VETTED_COMMIT" | tar -x -C "$tmp" 2>>"$RUNLOG"; then
    log "git archive failed"; rm -rf "$tmp"; return 1
  fi
  (
    cd "$tmp" || exit 1
    if [ -f package-lock.json ]; then
      npm ci --no-audit --no-fund >>"$RUNLOG" 2>&1 || npm install --no-audit --no-fund >>"$RUNLOG" 2>&1 || exit 1
    else
      npm install --no-audit --no-fund >>"$RUNLOG" 2>&1 || exit 1
    fi
    npm run build >>"$RUNLOG" 2>&1 || exit 1
  ) || rc=1
  if [ "$rc" != "0" ] || [ ! -s "$tmp/dist/main.js" ] || ! grep -q 'connect(transport)' "$tmp/dist/main.js" 2>/dev/null; then
    log "BUILD FAILED or unusable dist — existing dist/ left UNTOUCHED"
    rm -rf "$tmp"; return 1
  fi
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  if [ -d "$MCP_DIR/dist" ]; then
    rm -rf "$MCP_DIR/dist.bak-prev" 2>/dev/null || true
    mv "$MCP_DIR/dist" "$MCP_DIR/dist.bak-prev" 2>/dev/null || true
  fi
  if ! mv "$tmp/dist" "$MCP_DIR/dist" 2>/dev/null; then
    cp -R "$tmp/dist" "$MCP_DIR/dist" 2>/dev/null || {
      [ -d "$MCP_DIR/dist.bak-prev" ] && mv "$MCP_DIR/dist.bak-prev" "$MCP_DIR/dist" 2>/dev/null || true
      rm -rf "$tmp"; return 1; }
  fi
  ( cd "$MCP_DIR" && npm install --no-audit --no-fund --omit=dev >>"$RUNLOG" 2>&1 ) || \
    log "WARN: prod dependency refresh returned non-zero (existing node_modules kept)"
  cat > "$BUILD_STAMP" <<EOF
{
  "commit": "$GHL_MCP_VETTED_COMMIT",
  "profile": "$GHL_MCP_TOOL_PROFILE",
  "builtAt": "$ts",
  "node": "$(node --version 2>/dev/null || echo unknown)",
  "builtBy": "start-ghl-mcp-server.sh"
}
EOF
  rm -rf "$tmp"
  log "build OK — dist/ swapped (previous kept at dist.bak-prev)"
  return 0
}

# ---- ensure the server is cloned + pinned ----
if [ ! -d "$MCP_DIR/.git" ]; then
  log "community MCP not cloned at $MCP_DIR — cloning"
  mkdir -p "$(dirname "$MCP_DIR")" 2>/dev/null || true
  if command -v git >/dev/null 2>&1; then
    # NOT --depth 1: a shallow clone often cannot resolve an arbitrary pinned SHA.
    git clone --no-checkout "$GHL_MCP_REPO_URL" "$MCP_DIR" >>"$RUNLOG" 2>&1 \
      || { log "git clone FAILED — cannot start"; exit 1; }
  else
    log "git not available — cannot clone community MCP"; exit 1
  fi
fi
# Pin BEFORE build/start (both fresh and existing clones) — never run an unpinned tree.
pin_mcp_checkout || exit 1
if ! dist_is_sane || ! stamp_matches; then
  build_pinned || { log "npm install/build FAILED — see $RUNLOG"; exit 1; }
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

# D3: crash-only launcher. main.js exits 1 on a bad PIT at boot, so an
# unconditional restart policy turns a rotated token into an endless relaunch
# loop. The wrapper converts an AUTH rejection into a CLEAN exit 0, which pm2
# (stop_exit_codes), systemd (Restart=on-failure) and the fallback loop all
# treat as "stay stopped".
write_launcher() {
  cat > "$LAUNCHER" <<'LAUNCHEOF'
#!/usr/bin/env bash
# .ghl-mcp-launch.sh — generated by start-ghl-mcp-server.sh. DO NOT EDIT BY HAND.
set -u
MCP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
NOTE="${MCP_DIR}/.ghl-mcp-credential-blocked"
# LOG ROTATION (copytruncate — the supervisor holds an open fd, so renaming
# would leave the server writing to an orphaned inode). Nothing in the fleet
# rotated these logs before.
_ghl_rotate() {
  f="$1"; max="${GHL_MCP_LOG_MAX_BYTES:-10485760}"; keep="${GHL_MCP_LOG_KEEP:-3}"
  [ -f "$f" ] || return 0
  sz="$(wc -c < "$f" 2>/dev/null | tr -d ' ')"
  [ -n "$sz" ] || return 0
  [ "$sz" -gt "$max" ] 2>/dev/null || return 0
  rm -f "${f}.${keep}" 2>/dev/null || true
  i=$((keep-1))
  while [ "$i" -ge 1 ]; do
    [ -f "${f}.${i}" ] && mv "${f}.${i}" "${f}.$((i+1))" 2>/dev/null || true
    i=$((i-1))
  done
  cp "$f" "${f}.1" 2>/dev/null && : > "$f"
}
if [ -n "${GHL_MCP_LOG_DIR:-}" ]; then
  for _lf in "${GHL_MCP_LOG_DIR}/ghl-mcp.log" "${GHL_MCP_LOG_DIR}/ghl-mcp.err.log" \
             "${GHL_MCP_LOG_DIR}/stdout.log" "${GHL_MCP_LOG_DIR}/stderr.log"; do
    _ghl_rotate "$_lf"
  done
fi

if [ -f "${MCP_DIR}/.env" ]; then
  set -a; . "${MCP_DIR}/.env" 2>/dev/null || true; set +a
fi
: "${GHL_API_KEY:=}"
: "${GHL_LOCATION_ID:=}"
: "${GHL_BASE_URL:=https://services.leadconnectorhq.com}"
if [ -z "$GHL_API_KEY" ] || [ -z "$GHL_LOCATION_ID" ]; then
  printf '%s ghl-mcp launcher: GHL credential absent — NOT starting (clean exit, no restart loop)\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >&2
  printf 'credential-absent %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$NOTE" 2>/dev/null || true
  exit 0
fi
if command -v curl >/dev/null 2>&1; then
  CODE="$(curl -s -o /dev/null -w '%{http_code}' -m 10 \
    "${GHL_BASE_URL}/locations/${GHL_LOCATION_ID}" \
    -H "Authorization: Bearer ${GHL_API_KEY}" \
    -H "Version: 2021-07-28" 2>/dev/null || echo 000)"
  case "$CODE" in
    401|403)
      printf '%s ghl-mcp launcher: GHL rejected the PIT (HTTP %s) — NOT starting (clean exit, no restart loop)\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$CODE" >&2
      printf 'auth-rejected http=%s %s\n' "$CODE" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$NOTE" 2>/dev/null || true
      exit 0
      ;;
  esac
fi
rm -f "$NOTE" 2>/dev/null || true
NODE_BIN="${GHL_MCP_NODE_BIN:-$(command -v node 2>/dev/null || echo node)}"
cd "$MCP_DIR" || exit 1
exec "$NODE_BIN" "${MCP_DIR}/dist/main.js"
LAUNCHEOF
  chmod +x "$LAUNCHER" 2>/dev/null || true
}

# Write the canonical pm2 ecosystem (PORT + MCP_SERVER_PORT BOTH pinned — main.js
# reads PORT first, so an unpinned PORT is what binds the random 49032/63703) and
# GHL_TOOL_PROFILE pinned (the upstream default `full` serves all 858 tools).
# The GHL PIT is loaded at launch from the 600-perm .ghl-mcp.env (SK1-70), NOT inlined.
write_ecosystem() {
  write_secret_env
  write_launcher
  cat > "$MCP_DIR/ecosystem.config.js" <<ECO
// ghl-community-mcp — pm2 ecosystem (generated by start-ghl-mcp-server.sh)
// main.js reads PORT before MCP_SERVER_PORT (src/main.ts:55) — BOTH pinned to ${PORT}.
// GHL_TOOL_PROFILE pinned to ${GHL_MCP_TOOL_PROFILE} (upstream default is the full 858-tool surface).
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
    // Crash-only launcher: exit 0 = deliberate stop (bad/absent PIT) => no restart.
    script: ".ghl-mcp-launch.sh",
    interpreter: "bash",
    autorestart: true,
    stop_exit_codes: [0],
    max_restarts: 10,
    restart_delay: 5000,
    exp_backoff_restart_delay: 5000,
    env: Object.assign({
      NODE_ENV: "production",
      PORT: "${PORT}",
      MCP_SERVER_PORT: "${PORT}",
      GHL_TOOL_PROFILE: "${GHL_MCP_TOOL_PROFILE}",
      GHL_MCP_NODE_BIN: "${NODE_BIN}",
      GHL_MCP_LOG_DIR: "${LOG_DIR}",
      GHL_MCP_LOG_MAX_BYTES: "${GHL_MCP_LOG_MAX_BYTES}",
      GHL_MCP_LOG_KEEP: "${GHL_MCP_LOG_KEEP}",
      GHL_BASE_URL: "https://services.leadconnectorhq.com",
      GHL_LOCATION_ID: "${GHL_LOC}"
    }, _secret),
    out_file: "${RUNLOG}",
    error_file: "${LOG_DIR}/ghl-mcp.err.log"
  }]
};
ECO
}

# Best-effort platform rotation on top of the always-on launcher rotation:
# pm2-logrotate under pm2, logrotate when a passwordless sudo exists. Never
# prompts, never blocks. Docker boxes should ALSO cap the container log driver
# (max-size 10m / max-file 3) in compose — documented in INSTALL.md §5.6.
install_log_rotation() {
  if command -v pm2 >/dev/null 2>&1; then
    pm2 install pm2-logrotate >/dev/null 2>&1 || true
    pm2 set pm2-logrotate:max_size 10M >/dev/null 2>&1 || true
    pm2 set pm2-logrotate:retain "$GHL_MCP_LOG_KEEP" >/dev/null 2>&1 || true
    pm2 set pm2-logrotate:compress true >/dev/null 2>&1 || true
  fi
  LRCONF="/etc/logrotate.d/ghl-mcp"
  if [ ! -f "$LRCONF" ] && command -v logrotate >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    printf '%s/ghl-mcp*.log {\n    size 10M\n    rotate %s\n    missingok\n    notifempty\n    compress\n    delaycompress\n    copytruncate\n}\n' "$LOG_DIR" "$GHL_MCP_LOG_KEEP" \
      | sudo -n tee "$LRCONF" >/dev/null 2>&1 \
      && log "installed logrotate config $LRCONF (10 MB, keep ${GHL_MCP_LOG_KEEP}, copytruncate)" || true
  fi
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
  log "starting community MCP on :$PORT under pm2 (ecosystem.config.js, profile=${GHL_MCP_TOOL_PROFILE})"
  write_ecosystem
  ( cd "$MCP_DIR" && pm2 startOrReload ecosystem.config.js >>"$RUNLOG" 2>&1 \
      || pm2 start ecosystem.config.js >>"$RUNLOG" 2>&1 ) || true
  pm2 save >>"$RUNLOG" 2>&1 || true
  install_log_rotation
  install_reboot_resurrect
else
  # LAST-RESORT fallback (pm2 genuinely unavailable): a DETACHED, SUPERVISED
  # relaunch loop — NOT a bare nohup. setsid detaches from the controlling
  # terminal so it survives session/exec teardown; the loop re-launches on CRASH
  # and stops on a clean exit 0 (bad/absent PIT).
  log "pm2 not available — installing detached supervised relaunch loop on :$PORT (PORT + profile pinned)"
  write_launcher
  SUP="$MCP_DIR/.ghl-mcp-supervise.sh"
  cat > "$SUP" <<SUPEOF
#!/usr/bin/env bash
cd "${MCP_DIR}" || exit 1
while true; do
  PORT="${PORT}" MCP_SERVER_PORT="${PORT}" GHL_TOOL_PROFILE="${GHL_MCP_TOOL_PROFILE}" \\
    NODE_ENV=production GHL_MCP_NODE_BIN="${NODE_BIN}" \\
    /bin/bash "${LAUNCHER}" >>"${RUNLOG}" 2>&1
  rc=\$?
  [ "\$rc" = "0" ] && break
  sleep 10
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

# ---- wait for a real ANSWER (not just an open socket) ----
for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
  sleep 1
  if is_healthy && responds_ok; then log "started + answering JSON-RPC on :$PORT"; exit 0; fi
done
if [ -f "${MCP_DIR}/.ghl-mcp-credential-blocked" ]; then
  log "NOT started: GHL rejected the PIT (clean stop, no restart loop). Rotate the token then re-run."
  exit 1
fi
if is_healthy; then
  log "DEAF: /health green but no JSON-RPC response within ${GHL_MCP_PROBE_TIMEOUT}s — see $RUNLOG"
else
  log "started but NOT healthy within 12s — see $RUNLOG"
fi
exit 1
