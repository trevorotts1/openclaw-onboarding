#!/usr/bin/env bash
# ghl-mcp-autostart.sh — v21.5.0
#
# FIX 3 (systemic): Skill 36 registers the GHL community MCP in mcp.servers but
# nothing ever STARTS the local server on :8765, so the GHL tools never resolve
# at runtime. The launchd plist lived only as PROSE in
# 36-ghl-mcp-setup/INSTALL.md §5.5 — downloaded, never executed.
#
# v12.24.0 HARDENING (fleet incident: 12/19 boxes down/unsupervised):
#   1. PORT IS PINNED EXPLICITLY. main.js reads `PORT` BEFORE `MCP_SERVER_PORT`
#      (src/main.ts:55) — so without an explicit PORT a stray inherited PORT
#      binds a random port (49032/63703) instead of 8765. We now pin BOTH
#      PORT and MCP_SERVER_PORT to 8765 in EVERY launch surface (launchd plist,
#      pm2 ecosystem, systemd unit, .env, supervisor loop).
#   2. NO BARE NOHUP. A bare `nohup node …` does NOT survive session/exec
#      teardown and is NOT supervised — the exact failure that took the fleet
#      down. VPS now runs under pm2 (fleet-standard supervisor) with `pm2 save`
#      + an @reboot `pm2 resurrect` hook so it survives reboot/container restart.
#      systemd is the non-container fallback; a detached setsid relaunch LOOP
#      (poor-man's pm2, PORT pinned) is the last resort — never bare nohup.
#
# v21.5.0 HARDENING — the five installer diseases found on 2026-08-02/03 after a
# 2-day fleet-wide agent-init stall. Each one is now structurally impossible:
#
#   D1. STALE-DIST DEAFNESS. This script used to `git pull --ff-only` and then
#       build ONLY when dist/main.js was ABSENT. So a pull that advanced the
#       source left the OLD compiled dist in place forever. The deployed
#       dist/main.js predated upstream's `await server.connect(transport)` fix:
#       the socket accepted the connection and answered NOTHING, so every agent
#       init blocked the full 30s connectionTimeoutMs, on every box, for 2 days.
#       KeepAlive could not see it — the process was alive, just deaf.
#       FIX: rebuild is keyed to the PIN + a build stamp + a literal artifact
#       assertion (dist/main.js must contain `connect(transport)`), never to
#       "does a dist directory happen to exist".
#
#   D2. 858 TOOLS IN EVERY INIT. The server's default GHL_TOOL_PROFILE is
#       `full` (src/tool-registry.ts:509) — the entire 858-tool catalogue. When
#       the server is ALSO registered under mcp.servers, that catalogue is
#       injected into every agent's init.
#       FIX: GHL_TOOL_PROFILE is set explicitly in EVERY launch surface, and
#       this script no longer registers the community MCP (skill 36 v1.1.0
#       doctrine + qc-ghl-mcp-setup.sh Section D + wire.sh migration M2 all
#       say Tier 2 is ON-DEMAND CURL; this script was silently re-registering
#       what wire.sh had just removed).
#
#   D3. LATENT 10s CRASH LOOP. main.js calls `await ghlClient.testConnection()`
#       at boot and `process.exit(1)` on failure (src/main.ts:69 + 222-225).
#       A bad/expired/rotated PIT therefore makes the server exit non-zero on
#       EVERY launch; with ThrottleInterval=10 that is a 10s relaunch loop
#       burning the box until someone notices.
#       FIX: a launcher wrapper does a bounded credential preflight and exits
#       CLEANLY (0) on an auth rejection. Crash-only restart semantics then do
#       the right thing everywhere: launchd `KeepAlive{SuccessfulExit:false}`
#       does not restart a clean exit, pm2 `stop_exit_codes:[0]` does not,
#       systemd `Restart=on-failure` does not, and the fallback loop breaks.
#
#   D4. BUILD CRASH FROM ORPHANED node_modules IN src/. Upstream's build
#       (scripts/build-server.mjs) `rmSync(dist)` FIRST and then transpiles
#       EVERY .ts file it finds by walking src/ recursively — including any
#       node_modules that ever got installed inside src/ (the operator box had
#       src/ui/react-app/node_modules). One diagnostic anywhere in that walk
#       exits 1 AFTER dist was already deleted → a broken/partial dist and a
#       server that cannot start at all.
#       FIX: we never build the working tree. We `git archive` the pinned
#       commit into a temp dir, build THERE, verify the artifact, and only then
#       swap it into dist/ (previous dist kept as dist.bak-<ts>). Any orphaned
#       src/**/node_modules found in the working tree is quarantined so a human
#       running `npm run build` by hand cannot re-trigger the same crash.
#
#   D5. NO LIVENESS PROOF. Nothing asserted that a RESPONSE arrives. A GET
#       /health is served by express before the MCP transport is wired, so a
#       deaf server still returns {"status":"healthy"}.
#       FIX: scripts/ghl-mcp-probe.sh POSTs a real JSON-RPC `initialize` to
#       /mcp and requires a serverInfo response inside N seconds. It runs once
#       post-install and then every 15 minutes (launchd StartInterval on Mac,
#       cron on VPS).
#
# This script is the EXECUTED form of INSTALL.md §5.1–5.7. It is idempotent and
# additive: it (1) clones + pins + builds the community MCP, (2) installs the
# platform-appropriate supervisor (Mac=launchd KeepAlive plist com.clawd.ghl-mcp;
# VPS=pm2 ecosystem + save + reboot-resurrect, or systemd), (3) probes :8765 for
# a real JSON-RPC response, and (4) installs the periodic probe. Re-running is a
# safe UPGRADE path: it is also the fleet REMEDIATION path — re-running this
# script on a deaf box re-pins, rebuilds, and restarts it.
#
# Exit 0 = healthy (or a clean, honestly-reported skip). Exit non-zero NEVER —
# this is wiring; callers gate on the printed STATUS line + their own checks.

set -u

log() { printf '  [ghl-mcp-autostart] %s\n' "$*"; }

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# ── Platform + paths ─────────────────────────────────────────────────────────
if [ -f /data/.openclaw/openclaw.json ]; then
  PLATFORM="vps"
  OC_ROOT="/data/.openclaw"
  MCP_DIR="/data/mcp-servers/ghl-community-mcp"
  LOG_DIR="/data/logs"
else
  PLATFORM="mac"
  OC_ROOT="$HOME/.openclaw"
  MCP_DIR="$HOME/mcp-servers/ghl-community-mcp"
  LOG_DIR="$HOME/Library/Logs/ghl-mcp"
fi
OC_JSON="$OC_ROOT/openclaw.json"
SECRETS_ENV="$OC_ROOT/secrets/.env"
mkdir -p "$LOG_DIR" 2>/dev/null || true

# ── Pin + profile: ONE source of truth (config/ghl-mcp-pin.env) ──────────────
# Precedence: caller env  >  pin file  >  built-in fallback.
_PIN_FILE=""
for _c in "$SELF_DIR/../config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/onboarding/config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/skills/config/ghl-mcp-pin.env" \
          "/data/.openclaw/onboarding/config/ghl-mcp-pin.env" \
          "/data/.openclaw/skills/config/ghl-mcp-pin.env"; do
  [ -f "$_c" ] && { _PIN_FILE="$_c"; break; }
done
if [ -n "$_PIN_FILE" ]; then
  # shellcheck disable=SC1090
  . "$_PIN_FILE"
  log "pin config: $_PIN_FILE"
else
  log "pin config not found — using built-in fallback pin"
fi

# Built-in fallbacks (kept in sync with config/ghl-mcp-pin.env).
GHL_MCP_VETTED_COMMIT="${GHL_MCP_VETTED_COMMIT:-bfc2bbe15a4090b82351593b6ca52eed7a8dbbe3}"
GHL_MCP_TOOL_PROFILE="${GHL_MCP_TOOL_PROFILE:-curated}"
GHL_MCP_REPO_URL="${GHL_MCP_REPO_URL:-https://github.com/busybee3333/Go-High-Level-MCP-2026-Complete.git}"
GHL_MCP_PROBE_TIMEOUT="${GHL_MCP_PROBE_TIMEOUT:-10}"
GHL_MCP_LOG_MAX_BYTES="${GHL_MCP_LOG_MAX_BYTES:-10485760}"
GHL_MCP_LOG_KEEP="${GHL_MCP_LOG_KEEP:-3}"
# Caller override wins over the pin file (fleet roll can pass an env).
[ -n "${GHL_MCP_PIN_OVERRIDE:-}" ] && GHL_MCP_VETTED_COMMIT="$GHL_MCP_PIN_OVERRIDE"
[ -n "${GHL_TOOL_PROFILE:-}" ]     && GHL_MCP_TOOL_PROFILE="$GHL_TOOL_PROFILE"

# A pin MUST be a full 40-char SHA. A short SHA or a branch name is not a pin —
# `git checkout main` succeeds forever while the tree underneath changes.
case "$GHL_MCP_VETTED_COMMIT" in
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) : ;;
  *) log "REFUSING: GHL_MCP_VETTED_COMMIT='${GHL_MCP_VETTED_COMMIT}' is not a full 40-char SHA"
     printf 'STATUS: ghl-mcp-autostart=%s %s\n' "PIN_INVALID" \
       "(GHL_MCP_VETTED_COMMIT is not a full 40-char commit SHA — refusing to build/start an unpinned third-party MCP)"
     exit 0 ;;
esac

# ── Resolve a free/canonical port (8765 canonical) ──────────────────────────
GHL_MCP_PORT="${GHL_MCP_PORT:-8765}"

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

# ── D4: quarantine orphaned node_modules living INSIDE src/ ──────────────────
# build-server.mjs walks src/ recursively and transpiles every .ts it finds. A
# node_modules tree that ever landed under src/ turns a build into thousands of
# third-party transpiles and, on one diagnostic, exits 1 AFTER dist was deleted.
# We build from `git archive` so this cannot bite the automated path, but a
# human running `npm run build` in the working tree would still hit it.
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
  [ "$found" = "1" ] && log "quarantined orphaned node_modules found under src/ -> $q (D4: they crash upstream's build)"
  return 0
}

# ── 1. Clone + PIN the community MCP working tree (idempotent) ───────────────
ensure_repo_at_pin() {
  command -v git >/dev/null 2>&1 || { log "git not on PATH — cannot pin/build GHL MCP"; return 1; }
  mkdir -p "$(dirname "$MCP_DIR")" 2>/dev/null || true

  if [ ! -d "$MCP_DIR/.git" ]; then
    log "cloning community GHL MCP into $MCP_DIR"
    # NOT --depth 1: a shallow clone frequently cannot resolve an arbitrary
    # pinned SHA, which is exactly what turned the old script into a floating
    # "whatever main is today" install.
    git clone --no-checkout "$GHL_MCP_REPO_URL" "$MCP_DIR" >>"$LOG_DIR/ghl-mcp-build.log" 2>&1 || {
      log "git clone failed — server cannot be built"; return 1; }
  fi

  # Fetch the exact object; unshallow an old --depth 1 clone if needed.
  git -C "$MCP_DIR" fetch --quiet origin "$GHL_MCP_VETTED_COMMIT" 2>/dev/null \
    || git -C "$MCP_DIR" fetch --quiet --tags origin 2>/dev/null \
    || true
  if ! git -C "$MCP_DIR" cat-file -e "${GHL_MCP_VETTED_COMMIT}^{commit}" 2>/dev/null; then
    git -C "$MCP_DIR" fetch --quiet --unshallow origin 2>/dev/null || true
  fi
  if ! git -C "$MCP_DIR" cat-file -e "${GHL_MCP_VETTED_COMMIT}^{commit}" 2>/dev/null; then
    log "FATAL: pinned commit $GHL_MCP_VETTED_COMMIT not reachable from origin (upstream force-push? bad pin?)"
    return 2
  fi

  quarantine_src_orphans
  # --force: the third-party tree is disposable; local edits are never ours.
  git -C "$MCP_DIR" checkout --quiet --detach --force "$GHL_MCP_VETTED_COMMIT" 2>>"$LOG_DIR/ghl-mcp-build.log" || {
    log "FATAL: could not check out pinned commit $GHL_MCP_VETTED_COMMIT"; return 2; }
  local head
  head="$(git -C "$MCP_DIR" rev-parse HEAD 2>/dev/null || echo none)"
  if [ "$head" != "$GHL_MCP_VETTED_COMMIT" ]; then
    log "FATAL: pin verify failed (HEAD=$head want $GHL_MCP_VETTED_COMMIT)"
    return 2
  fi
  log "working tree pinned at $GHL_MCP_VETTED_COMMIT"
  return 0
}

# ── 2. Build hygiene: build the PINNED tree in a temp dir, swap on success ───
BUILD_STAMP="$MCP_DIR/.ghl-mcp-build.json"

dist_is_sane() {
  # A dist that exists proves nothing (D1). Require the entrypoint AND the one
  # line whose absence produced the 30s deafness: `server.connect(transport)`.
  [ -s "$MCP_DIR/dist/main.js" ] || return 1
  grep -q 'connect(transport)' "$MCP_DIR/dist/main.js" 2>/dev/null || return 1
  return 0
}

stamp_matches() {
  [ -f "$BUILD_STAMP" ] || return 1
  grep -q "\"commit\": *\"$GHL_MCP_VETTED_COMMIT\"" "$BUILD_STAMP" 2>/dev/null || return 1
  return 0
}

needs_build() {
  dist_is_sane || return 0
  stamp_matches || return 0
  return 1
}

build_pinned() {
  command -v npm >/dev/null 2>&1 || { log "npm not on PATH — cannot build"; return 1; }
  local tmp rc=0
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/ghl-mcp-build.XXXXXX")" || return 1
  log "building pinned tree ${GHL_MCP_VETTED_COMMIT:0:12} in $tmp (working tree is NEVER built — D4)"
  # git archive gives a pristine snapshot of the PINNED commit: no untracked
  # junk, no orphaned node_modules, no half-applied local edits.
  if ! git -C "$MCP_DIR" archive "$GHL_MCP_VETTED_COMMIT" | tar -x -C "$tmp" 2>>"$LOG_DIR/ghl-mcp-build.log"; then
    log "git archive failed"; rm -rf "$tmp"; return 1
  fi
  (
    cd "$tmp" || exit 1
    if [ -f package-lock.json ]; then
      npm ci --no-audit --no-fund >>"$LOG_DIR/ghl-mcp-build.log" 2>&1 || \
      npm install --no-audit --no-fund >>"$LOG_DIR/ghl-mcp-build.log" 2>&1 || exit 1
    else
      npm install --no-audit --no-fund >>"$LOG_DIR/ghl-mcp-build.log" 2>&1 || exit 1
    fi
    npm run build >>"$LOG_DIR/ghl-mcp-build.log" 2>&1 || exit 1
  ) || rc=1
  if [ "$rc" != "0" ] || [ ! -s "$tmp/dist/main.js" ] || ! grep -q 'connect(transport)' "$tmp/dist/main.js" 2>/dev/null; then
    log "BUILD FAILED or produced an unusable dist — existing dist/ left UNTOUCHED (never rm -rf before a good build)"
    rm -rf "$tmp"; return 1
  fi

  # Atomic-ish swap: keep the old dist as a rollback, move the verified one in.
  local ts; ts="$(date -u +%Y%m%dT%H%M%SZ)"
  if [ -d "$MCP_DIR/dist" ]; then
    rm -rf "$MCP_DIR/dist.bak-prev" 2>/dev/null || true
    mv "$MCP_DIR/dist" "$MCP_DIR/dist.bak-prev" 2>/dev/null || true
  fi
  if ! mv "$tmp/dist" "$MCP_DIR/dist" 2>/dev/null; then
    cp -R "$tmp/dist" "$MCP_DIR/dist" 2>/dev/null || {
      log "FATAL: could not install new dist — rolling back previous dist"
      [ -d "$MCP_DIR/dist.bak-prev" ] && mv "$MCP_DIR/dist.bak-prev" "$MCP_DIR/dist" 2>/dev/null || true
      rm -rf "$tmp"; return 1; }
  fi
  # Runtime deps live next to dist/ in the working tree; refresh prod deps only.
  ( cd "$MCP_DIR" && npm install --no-audit --no-fund --omit=dev >>"$LOG_DIR/ghl-mcp-build.log" 2>&1 ) || \
    log "WARN: prod dependency refresh returned non-zero (existing node_modules kept)"
  cat > "$BUILD_STAMP" <<EOF
{
  "commit": "$GHL_MCP_VETTED_COMMIT",
  "profile": "$GHL_MCP_TOOL_PROFILE",
  "builtAt": "$ts",
  "node": "$(node --version 2>/dev/null || echo unknown)",
  "builtBy": "ghl-mcp-autostart.sh"
}
EOF
  rm -rf "$tmp"
  log "build OK — dist/ swapped (previous kept at dist.bak-prev)"
  return 0
}

# ── 3. The server .env (idempotent rewrite — chmod 600) ─────────────────────
write_server_env() {
  [ -n "$GHL_TOKEN" ] || return 0
  ( umask 077; cat > "$MCP_DIR/.env" <<EOF
GHL_API_KEY=${GHL_TOKEN}
GHL_BASE_URL=https://services.leadconnectorhq.com
GHL_LOCATION_ID=${GHL_LOC}
# main.js reads PORT before MCP_SERVER_PORT — pin BOTH so it can never bind random.
PORT=${GHL_MCP_PORT}
MCP_SERVER_PORT=${GHL_MCP_PORT}
# D2: upstream default is the FULL 858-tool surface. Pin the profile explicitly.
GHL_TOOL_PROFILE=${GHL_MCP_TOOL_PROFILE}
NODE_ENV=production
EOF
  )
  chmod 600 "$MCP_DIR/.env" 2>/dev/null || true
}

# ── 4. D3: the launcher wrapper — crash-only restart, no bad-token loop ──────
# main.js exits 1 on a bad token at boot. Every supervisor treats non-zero as
# "crashed" and relaunches → a 10s loop. The wrapper turns an AUTH rejection
# into a CLEAN exit 0, which every supervisor here is configured NOT to restart.
LAUNCHER="$MCP_DIR/.ghl-mcp-launch.sh"
write_launcher() {
  cat > "$LAUNCHER" <<'LAUNCHEOF'
#!/usr/bin/env bash
# .ghl-mcp-launch.sh — generated by ghl-mcp-autostart.sh. DO NOT EDIT BY HAND.
#
# Crash-only launcher for the GHL community MCP.
#   exit 0  -> a deliberate, non-restartable stop (missing/rejected credential).
#              launchd KeepAlive{SuccessfulExit:false}, pm2 stop_exit_codes:[0],
#              systemd Restart=on-failure and the fallback loop all honour this,
#              so a bad PIT can never become a 10s relaunch loop.
#   exec    -> otherwise the node server REPLACES this shell, so the supervisor
#              still watches the real process (no wrapper PID indirection).
set -u
MCP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
STAMP_DIR="${MCP_DIR}"
NOTE="${STAMP_DIR}/.ghl-mcp-credential-blocked"

# Load the server env (600-perm) without echoing it.
# LOG ROTATION (copytruncate). The supervisor holds an open fd on these files,
# so we copy-then-truncate IN PLACE; renaming would leave the server writing to
# an orphaned inode. Runs at every (re)start; the periodic probe repeats it so a
# long-lived process still gets rotated.
_ghl_rotate() {
  local f="$1" max="${GHL_MCP_LOG_MAX_BYTES:-10485760}" keep="${GHL_MCP_LOG_KEEP:-3}" sz i
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
  for _lf in "${GHL_MCP_LOG_DIR}/stdout.log" "${GHL_MCP_LOG_DIR}/stderr.log" \
             "${GHL_MCP_LOG_DIR}/ghl-mcp.log" "${GHL_MCP_LOG_DIR}/ghl-mcp.err.log"; do
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

# Bounded auth preflight: one call, 10s cap. 401/403 => the token is bad; exit
# cleanly instead of letting main.js exit(1) forever. Any other outcome
# (network blip, 5xx, curl missing) falls through and starts the server — we
# never block a start on a transient.
if command -v curl >/dev/null 2>&1; then
  CODE="$(curl -s -o /dev/null -w '%{http_code}' -m 10 \
    "${GHL_BASE_URL}/locations/${GHL_LOCATION_ID}" \
    -H "Authorization: Bearer ${GHL_API_KEY}" \
    -H "Version: 2021-07-28" 2>/dev/null || echo 000)"
  case "$CODE" in
    401|403)
      printf '%s ghl-mcp launcher: GHL rejected the PIT (HTTP %s) — NOT starting (clean exit, no restart loop). Rotate/repair the token then re-run ghl-mcp-autostart.sh\n' \
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

# ── 5. Health + liveness ─────────────────────────────────────────────────────
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

# The REAL test: does a JSON-RPC request get an ANSWER? /health is served by
# express before the MCP transport is wired, so a stale/deaf dist still returns
# {"status":"healthy"} while every agent init hangs the full 30s (D1/D5).
PROBE="$(
  for c in "$SELF_DIR/ghl-mcp-probe.sh" \
           "$HOME/.openclaw/skills/scripts/ghl-mcp-probe.sh" \
           "/data/.openclaw/skills/scripts/ghl-mcp-probe.sh"; do
    [ -f "$c" ] && { printf '%s' "$c"; break; }
  done
)"
responds_ok() {
  if [ -n "${PROBE:-}" ]; then
    # --skip-profile: here we only want the LIVENESS verdict; profile drift is
    # reported separately by the periodic probe and must not be misread as deaf.
    GHL_MCP_PORT="$GHL_MCP_PORT" GHL_MCP_PROBE_TIMEOUT="$GHL_MCP_PROBE_TIMEOUT" \
      bash "$PROBE" --once --quiet --skip-profile >/dev/null 2>&1
    return $?
  fi
  # Inline fallback if the probe script is not co-located.
  command -v curl >/dev/null 2>&1 || return 1
  curl -sS --max-time "$GHL_MCP_PROBE_TIMEOUT" -X POST "http://localhost:${GHL_MCP_PORT}/mcp" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"ghl-mcp-autostart","version":"1"}}}' \
    2>/dev/null | grep -q 'serverInfo'
}

# ── 6. Write canonical launchd plist + boot (Mac); pm2/systemd (VPS) ─────────
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
    <!-- Runs the crash-only launcher, not node directly: the launcher exits 0
         (no restart) when the PIT is missing/rejected, so a bad token can never
         become a 10s relaunch loop (D3). It exec's node, so launchd still
         supervises the real server process. -->
    <key>ProgramArguments</key><array>
        <string>/bin/bash</string>
        <string>${LAUNCHER}</string>
    </array>
    <key>WorkingDirectory</key><string>${MCP_DIR}</string>
    <key>EnvironmentVariables</key><dict>
        <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>NODE_ENV</key><string>production</string>
        <!-- main.js/http-server.ts read PORT BEFORE MCP_SERVER_PORT (src/main.ts:55).
             Pin BOTH to ${GHL_MCP_PORT} so a stray inherited PORT can never bind a random port. -->
        <key>PORT</key><string>${GHL_MCP_PORT}</string>
        <key>MCP_SERVER_PORT</key><string>${GHL_MCP_PORT}</string>
        <!-- D2: without this the registry serves the FULL 858-tool surface. -->
        <key>GHL_TOOL_PROFILE</key><string>${GHL_MCP_TOOL_PROFILE}</string>
        <key>GHL_MCP_NODE_BIN</key><string>${NODE_PATH}</string>
        <!-- Log rotation: the launcher copytruncates these at every (re)start
             and the periodic probe repeats it while the process is long-lived.
             Nothing in the fleet rotated them before (5.4 MB and counting). -->
        <key>GHL_MCP_LOG_DIR</key><string>${HOME}/Library/Logs/ghl-mcp</string>
        <key>GHL_MCP_LOG_MAX_BYTES</key><string>${GHL_MCP_LOG_MAX_BYTES}</string>
        <key>GHL_MCP_LOG_KEEP</key><string>${GHL_MCP_LOG_KEEP}</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <!-- CRASH-ONLY (ghl-mcp-setup doctrine). NEVER the unconditional boolean
         form of KeepAlive: it restarts even a deliberate clean exit, which is
         what turns the bad-token exit into an infinite 10s relaunch loop.
         The QC gate rejects the boolean form outright. -->
    <key>KeepAlive</key><dict>
        <key>SuccessfulExit</key><false/>
        <key>Crashed</key><true/>
    </dict>
    <!-- 300s: the canonical fleet shape (matches the reference plist verified on
         a fleet box). Long enough that even a mis-detected crash cannot
         become a hot relaunch loop. -->
    <key>ThrottleInterval</key><integer>300</integer>
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

# Write the canonical pm2 ecosystem.config.js (PORT + MCP_SERVER_PORT + the tool
# profile pinned). pm2 is the fleet-standard supervisor on VPS/Docker (no systemd
# in Hostinger containers). The ecosystem file is the single source of truth pm2
# reads, so the port/profile can never be inherited and the env is reproducible.
# SK1-70: the GHL PIT is NOT inlined here (world-readable) — it is loaded at
# launch from the 600-perm .ghl-mcp.env sitting next to this config.
write_vps_ecosystem() {
  ( umask 077; printf 'GHL_API_KEY=%s\n' "$GHL_TOKEN" > "$MCP_DIR/.ghl-mcp.env" ) 2>/dev/null || true
  chmod 600 "$MCP_DIR/.ghl-mcp.env" 2>/dev/null || true
  cat > "$MCP_DIR/ecosystem.config.js" <<EOF
// ghl-community-mcp — pm2 ecosystem (generated by ghl-mcp-autostart.sh)
// main.js reads PORT before MCP_SERVER_PORT (src/main.ts:55) — BOTH pinned to ${GHL_MCP_PORT}.
// GHL_TOOL_PROFILE is pinned so the registry never serves the full 858-tool surface.
// SK1-70: the GHL PIT is loaded from the 600-perm .ghl-mcp.env, never inlined here.
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
    // Crash-only launcher (D3): exit 0 = deliberate stop, pm2 must NOT restart.
    script: ".ghl-mcp-launch.sh",
    interpreter: "bash",
    autorestart: true,
    stop_exit_codes: [0],
    max_restarts: 10,
    restart_delay: 5000,
    exp_backoff_restart_delay: 5000,
    env: Object.assign({
      NODE_ENV: "production",
      PORT: "${GHL_MCP_PORT}",
      MCP_SERVER_PORT: "${GHL_MCP_PORT}",
      GHL_TOOL_PROFILE: "${GHL_MCP_TOOL_PROFILE}",
      GHL_MCP_LOG_DIR: "/data/logs",
      GHL_MCP_LOG_MAX_BYTES: "${GHL_MCP_LOG_MAX_BYTES}",
      GHL_MCP_LOG_KEEP: "${GHL_MCP_LOG_KEEP}",
      GHL_BASE_URL: "https://services.leadconnectorhq.com",
      GHL_LOCATION_ID: "${GHL_LOC}"
    }, _secret),
    out_file: "/data/logs/ghl-mcp.log",
    error_file: "/data/logs/ghl-mcp.err.log"
  }]
};
EOF
}

start_service_vps() {
  local NODE_PATH; NODE_PATH="$(command -v node)"
  mkdir -p /data/logs 2>/dev/null || true
  write_vps_ecosystem

  # ── PRIMARY: pm2 (the fleet-standard supervisor; survives container restart via
  #    `pm2 save` + a reboot-resurrect hook). NEVER a bare nohup. ──────────────
  if command -v pm2 >/dev/null 2>&1; then
    log "starting GHL MCP under pm2 (ecosystem.config.js, PORT=${GHL_MCP_PORT}, profile=${GHL_MCP_TOOL_PROFILE})"
    ( cd "$MCP_DIR" && pm2 startOrReload ecosystem.config.js >/dev/null 2>&1 \
        || pm2 start ecosystem.config.js >/dev/null 2>&1 ) || true
    pm2 save >/dev/null 2>&1 || true
    install_vps_reboot_resurrect
    return 0
  fi

  # ── FALLBACK A: systemd (non-container VPS). Reboot-surviving via enable. ────
  # GATED ON PASSWORDLESS SUDO (v21.5.0). Writing the unit file needs root, and a
  # bare `sudo` PROMPTS on a TTY — sudo writes its prompt to /dev/tty, so the
  # `>/dev/null 2>&1` below does NOT silence it. install.sh Step 14a calls this
  # script, so a prompt here hangs a whole install. Worse, the old shape swallowed
  # every sudo failure with `|| true` and then `return 0` — reporting a supervised
  # server while having installed absolutely nothing, which is precisely the class
  # of silent false-success this release exists to kill. If root is not available
  # non-interactively we say so and fall through to the supervised relaunch loop
  # (FALLBACK B), which needs no privileges at all.
  if command -v systemctl >/dev/null 2>&1 && ! sudo -n true 2>/dev/null; then
    log "systemctl present but no passwordless sudo — cannot install the unit; falling through to the supervised relaunch loop"
  elif command -v systemctl >/dev/null 2>&1; then
    log "pm2 not found — installing systemd unit ghl-mcp (PORT + profile pinned via Environment=)"
    sudo -n tee /etc/systemd/system/ghl-mcp.service > /dev/null <<EOF
[Unit]
Description=GHL Community MCP Server
After=network.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${MCP_DIR}
# Pin PORT explicitly (main.js reads PORT before MCP_SERVER_PORT).
Environment=PORT=${GHL_MCP_PORT}
Environment=MCP_SERVER_PORT=${GHL_MCP_PORT}
Environment=GHL_TOOL_PROFILE=${GHL_MCP_TOOL_PROFILE}
Environment=GHL_MCP_LOG_DIR=/data/logs
Environment=GHL_MCP_LOG_MAX_BYTES=${GHL_MCP_LOG_MAX_BYTES}
Environment=GHL_MCP_LOG_KEEP=${GHL_MCP_LOG_KEEP}
Environment=NODE_ENV=production
Environment=GHL_MCP_NODE_BIN=${NODE_PATH}
# Crash-only launcher (D3): a clean exit 0 (bad/absent PIT) must NOT restart.
ExecStart=/bin/bash ${LAUNCHER}
Restart=on-failure
RestartSec=30
EnvironmentFile=${MCP_DIR}/.env
StandardOutput=append:/data/logs/ghl-mcp.log
StandardError=append:/data/logs/ghl-mcp.err.log

[Install]
WantedBy=multi-user.target
EOF
    sudo -n systemctl daemon-reload >/dev/null 2>&1 || true
    # Only claim success if the unit actually came up. Otherwise fall through to
    # the supervised loop rather than returning a supervised-looking lie.
    if sudo -n systemctl enable --now ghl-mcp >/dev/null 2>&1; then
      return 0
    fi
    log "systemd unit did not enable/start — falling through to the supervised relaunch loop"
  fi

  # ── FALLBACK B (last resort): supervised relaunch loop, NOT a bare nohup. ────
  # A bare `nohup node …` does NOT survive session/exec teardown and is the exact
  # failure that took 12/19 fleet boxes down. This wrapper double-forks a detached
  # watch loop that re-launches the server if it ever CRASHES (poor-man's pm2),
  # with PORT + profile pinned, and STOPS on a clean exit 0 (D3).
  log "neither pm2 nor systemd available — installing supervised relaunch loop (PORT=${GHL_MCP_PORT})"
  local SUP="$MCP_DIR/.ghl-mcp-supervise.sh"
  cat > "$SUP" <<EOF
#!/usr/bin/env bash
# Detached supervisor for ghl-community-mcp — re-launches on CRASH only.
cd "${MCP_DIR}" || exit 1
while true; do
  PORT="${GHL_MCP_PORT}" MCP_SERVER_PORT="${GHL_MCP_PORT}" \\
    GHL_TOOL_PROFILE="${GHL_MCP_TOOL_PROFILE}" NODE_ENV=production \\
    GHL_MCP_NODE_BIN="${NODE_PATH}" GHL_MCP_LOG_DIR="/data/logs" \\
    GHL_MCP_LOG_MAX_BYTES="${GHL_MCP_LOG_MAX_BYTES}" GHL_MCP_LOG_KEEP="${GHL_MCP_LOG_KEEP}" \\
    /bin/bash "${LAUNCHER}" >> /data/logs/ghl-mcp.log 2>&1
  rc=\$?
  # Clean exit = deliberate stop (missing/rejected credential). Do NOT loop.
  [ "\$rc" = "0" ] && break
  sleep 10
done
EOF
  chmod +x "$SUP" 2>/dev/null || true
  # setsid detaches from the controlling terminal so it survives exec/session teardown.
  if command -v setsid >/dev/null 2>&1; then
    setsid nohup bash "$SUP" >> /data/logs/ghl-mcp.log 2>&1 < /dev/null &
  else
    nohup bash "$SUP" >> /data/logs/ghl-mcp.log 2>&1 < /dev/null &
  fi
  disown 2>/dev/null || true
}

# Wire a reboot-resurrect hook so the pm2-managed MCP comes back after a host
# reboot / container restart. Matches the fleet pattern used by the Command
# Center: `pm2 resurrect` via the host @reboot cron AND/OR the Docker container
# `command:` override. We add the @reboot cron idempotently here; the
# container-command override is documented in INSTALL.md §5.6 for compose edits.
install_vps_reboot_resurrect() {
  command -v pm2 >/dev/null 2>&1 || return 0
  local PM2_BIN; PM2_BIN="$(command -v pm2)"
  # Prefer pm2's own startup integration where init systems exist (no-op in bare
  # containers, which is fine — the @reboot cron + container command cover those).
  pm2 startup >/dev/null 2>&1 || true
  # Idempotent @reboot cron entry (covers bare containers + plain VPS reboots).
  if command -v crontab >/dev/null 2>&1; then
    local LINE="@reboot ${PM2_BIN} resurrect >/data/logs/pm2-resurrect.log 2>&1"
    if ! crontab -l 2>/dev/null | grep -Fq "pm2 resurrect"; then
      ( crontab -l 2>/dev/null; printf '%s\n' "$LINE" ) | crontab - >/dev/null 2>&1 || true
      log "installed @reboot 'pm2 resurrect' cron (reboot-surviving)"
    fi
  fi
}

# ── 6b. LOG ROTATION (fleet gap: nothing ever rotated these) ─────────────────
# Two layers, because neither alone is guaranteed:
#   1. ALWAYS: the generated launcher copytruncates at every (re)start and the
#      periodic probe repeats it every 15 min. No root, no daemons, works in a
#      bare container. This is the layer we rely on.
#   2. BEST-EFFORT: the platform's own rotator (newsyslog on Mac, logrotate on
#      VPS, pm2-logrotate under pm2) when it can be configured WITHOUT an
#      interactive sudo prompt. Never blocks, never prompts.
install_log_rotation() {
  if [ "$PLATFORM" = "mac" ]; then
    local NSCONF="/etc/newsyslog.d/com.clawd.ghl-mcp.conf"
    if [ ! -f "$NSCONF" ] && sudo -n true 2>/dev/null; then
      printf '# logfilename                                  [owner:group]  mode count size(KB) when  flags\n%s/Library/Logs/ghl-mcp/stderr.log  %s:staff  644  %s  10240  *  GJ\n%s/Library/Logs/ghl-mcp/stdout.log  %s:staff  644  %s  10240  *  GJ\n' \
        "$HOME" "$(id -un)" "$GHL_MCP_LOG_KEEP" "$HOME" "$(id -un)" "$GHL_MCP_LOG_KEEP" \
        | sudo -n tee "$NSCONF" >/dev/null 2>&1 \
        && log "installed newsyslog rotation config $NSCONF (10 MB, keep ${GHL_MCP_LOG_KEEP})" \
        || log "newsyslog config not installed (no passwordless sudo) — the launcher/probe rotation still applies"
    else
      log "newsyslog config present or sudo unavailable — relying on launcher/probe rotation"
    fi
  else
    if command -v pm2 >/dev/null 2>&1; then
      # pm2-logrotate is the fleet-standard pm2 companion; install is a no-op if present.
      pm2 install pm2-logrotate >/dev/null 2>&1 || true
      pm2 set pm2-logrotate:max_size 10M >/dev/null 2>&1 || true
      pm2 set pm2-logrotate:retain "$GHL_MCP_LOG_KEEP" >/dev/null 2>&1 || true
      pm2 set pm2-logrotate:compress true >/dev/null 2>&1 || true
    fi
    local LRCONF="/etc/logrotate.d/ghl-mcp"
    if [ ! -f "$LRCONF" ] && command -v logrotate >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
      printf '/data/logs/ghl-mcp*.log {\n    size 10M\n    rotate %s\n    missingok\n    notifempty\n    compress\n    delaycompress\n    copytruncate\n}\n' "$GHL_MCP_LOG_KEEP" \
        | sudo -n tee "$LRCONF" >/dev/null 2>&1 \
        && log "installed logrotate config $LRCONF (10 MB, keep ${GHL_MCP_LOG_KEEP}, copytruncate)" \
        || log "logrotate config not installed — the launcher/probe rotation still applies"
    fi
    # Hostinger Docker note: also cap the container driver in compose —
    #   logging: { driver: "json-file", options: { max-size: "10m", max-file: "3" } }
    # That is a compose-file edit, documented in INSTALL.md §5.6.
  fi
}

# ── 7. Periodic liveness probe (D5) — every 15 minutes, self-healing once ────
install_periodic_probe() {
  [ -n "${PROBE:-}" ] || { log "ghl-mcp-probe.sh not co-located — periodic liveness probe NOT installed"; return 0; }
  if [ "$PLATFORM" = "mac" ]; then
    local PPLIST="$HOME/Library/LaunchAgents/com.clawd.ghl-mcp-probe.plist"
    cat > "$PPLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.clawd.ghl-mcp-probe</string>
    <key>ProgramArguments</key><array>
        <string>/bin/bash</string>
        <string>${PROBE}</string>
        <string>--once</string>
        <string>--heal</string>
    </array>
    <key>EnvironmentVariables</key><dict>
        <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>GHL_MCP_PORT</key><string>${GHL_MCP_PORT}</string>
        <key>GHL_MCP_PROBE_TIMEOUT</key><string>${GHL_MCP_PROBE_TIMEOUT}</string>
    </dict>
    <key>StartInterval</key><integer>900</integer>
    <key>RunAtLoad</key><false/>
    <key>StandardOutPath</key><string>${HOME}/Library/Logs/ghl-mcp/probe.log</string>
    <key>StandardErrorPath</key><string>${HOME}/Library/Logs/ghl-mcp/probe.log</string>
    <key>ProcessType</key><string>Background</string>
</dict>
</plist>
EOF
    launchctl bootout "gui/$(id -u)" "$PPLIST" >/dev/null 2>&1 || true
    launchctl bootstrap "gui/$(id -u)" "$PPLIST" >/dev/null 2>&1 || \
      launchctl load "$PPLIST" >/dev/null 2>&1 || true
    log "periodic liveness probe installed (com.clawd.ghl-mcp-probe, every 900s)"
  else
    command -v crontab >/dev/null 2>&1 || return 0
    local LINE="*/15 * * * * /bin/bash ${PROBE} --once --heal >>${LOG_DIR}/probe.log 2>&1"
    if ! crontab -l 2>/dev/null | grep -Fq "ghl-mcp-probe.sh"; then
      ( crontab -l 2>/dev/null; printf '%s\n' "$LINE" ) | crontab - >/dev/null 2>&1 || true
      log "periodic liveness probe cron installed (*/15)"
    fi
  fi
}

# ── 8. Tier 2 is ON-DEMAND CURL — de-register any legacy mcp.servers entry ───
# skill 36 v1.1.0 doctrine, qc-ghl-mcp-setup.sh Section D and 36/wire.sh
# migration M2 all require ghl-community-mcp to be ABSENT from mcp.servers: its
# tool schemas would ride in every session's init whether or not GHL is touched,
# and a deaf/down server makes every init pay the full connectionTimeoutMs.
# This script used to re-register it right after wire.sh removed it. It no
# longer does; it removes a legacy registration instead and only publishes the
# canonical URL env var that the on-demand curl path reads.
deregister_tier2() {
  command -v openclaw >/dev/null 2>&1 || return 0
  openclaw config set env.vars.GHL_COMMUNITY_MCP_URL "http://localhost:${GHL_MCP_PORT}" >/dev/null 2>&1 || true
  if openclaw mcp list 2>/dev/null | grep -q 'ghl-community-mcp'; then
    log "removing legacy ghl-community-mcp registration (Tier 2 is on-demand curl)"
    openclaw mcp remove ghl-community-mcp >/dev/null 2>&1 || true
  fi
}

# ── Main flow ────────────────────────────────────────────────────────────────

# Fast idempotent no-op: healthy AND answering JSON-RPC AND already built from
# the pinned commit. "A dist exists" is NOT a no-op condition (that is exactly
# how the stale deaf dist survived two days).
if [ -f "$BUILD_STAMP" ] && stamp_matches && dist_is_sane && health_ok && responds_ok; then
  deregister_tier2
  install_log_rotation
  install_periodic_probe
  report "HEALTHY_ALREADY" "(pinned ${GHL_MCP_VETTED_COMMIT:0:12}, profile=${GHL_MCP_TOOL_PROFILE}, :${GHL_MCP_PORT} answers JSON-RPC — idempotent no-op)"
  exit 0
fi

# Need GHL creds to build a usable server. Honest skip otherwise — NEVER claim
# the MCP is up when it cannot be.
if [ -z "$GHL_TOKEN" ]; then
  report "SKIPPED_NO_CREDS" "(GOHIGHLEVEL_API_KEY/GHL_API_KEY absent — server NOT started; this is an honest gap, not a failure. Set the GHL token then re-run.)"
  exit 0
fi

ensure_repo_at_pin
_PIN_RC=$?
if [ "$_PIN_RC" = "2" ]; then
  report "PIN_MISMATCH" "(cannot check out vetted commit ${GHL_MCP_VETTED_COMMIT:0:12} at $MCP_DIR — refusing to build/start an unpinned third-party MCP. Re-vet upstream and update config/ghl-mcp-pin.env.)"
  exit 0
elif [ "$_PIN_RC" != "0" ]; then
  report "BUILD_FAILED" "(could not clone/pin community MCP at $MCP_DIR — GHL tools will NOT resolve until fixed)"
  exit 0
fi

write_server_env
write_launcher

if needs_build; then
  if ! build_pinned; then
    report "BUILD_FAILED" "(build of pinned ${GHL_MCP_VETTED_COMMIT:0:12} failed — previous dist/ left intact; see $LOG_DIR/ghl-mcp-build.log)"
    exit 0
  fi
else
  log "dist/ already built from the pinned commit and passes the artifact check — skipping build"
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

deregister_tier2
install_log_rotation
install_periodic_probe

# Credential rejection is reported honestly, not as a mystery failure.
if [ -f "$MCP_DIR/.ghl-mcp-credential-blocked" ]; then
  report "TOKEN_REJECTED" "(GHL rejected the PIT at launch — server deliberately NOT running and NOT restart-looping. Rotate/repair GOHIGHLEVEL_API_KEY then re-run this script.)"
  exit 0
fi

if health_ok && responds_ok; then
  report "HEALTHY" "(pinned ${GHL_MCP_VETTED_COMMIT:0:12}, profile=${GHL_MCP_TOOL_PROFILE}, :${GHL_MCP_PORT} answers JSON-RPC; Tier 2 stays on-demand curl — not registered in mcp.servers)"
elif health_ok; then
  report "DEAF" "(:${GHL_MCP_PORT} /health is green but the MCP endpoint returned NO JSON-RPC response within ${GHL_MCP_PROBE_TIMEOUT}s — this is the stale-dist deafness signature. Check $LOG_DIR/ghl-mcp-build.log and re-run.)"
else
  report "STARTED_UNHEALTHY" "(supervisor installed on :${GHL_MCP_PORT} but /health not green yet — crash-only restart will retry; check $LOG_DIR. GHL tools may not resolve until healthy.)"
fi
exit 0
