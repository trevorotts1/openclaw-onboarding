#!/usr/bin/env bash
# ghl-mcp-autostart.sh — v21.6.0
#
# 2026-09-17 (skill 36 v2.0.2): THREE DEFECTS, all diagnosed on two live
# client containers whose Tier 2 runtime was provably healthy (pm2 app online
# under a root-persisted PM2_HOME, /health answering with 43 tools, build stamp
# on the pinned commit) while the updater exited 2 with "GHL MCP Tier 2
# MISCONFIGURED". A gate that reports a healthy box as broken is worse than no
# gate: it trains an operator to ignore it.
#
#   1. INSTALL PATH WAS HARDCODED. This script and the runtime gate both pinned
#      the install to /data/mcp-servers (vps) or $HOME/mcp-servers (everything
#      else). On the client-container shape ONLY the OpenClaw root, its
#      workspace and $HOME/.config/openclaw are bind-mounted, so $HOME/mcp-servers
#      is in the container layer and is destroyed on every recreate; the working
#      installs live under the OpenClaw root and neither script could see them.
#      FIX: scripts/lib/ghl-mcp-paths.sh derives <root>/mcp-servers/ghl-community-mcp
#      from the resolved OpenClaw root, keeps the legacy locations as fallbacks
#      when they carry a build stamp (so no existing box is asked to rebuild),
#      and is SOURCED by both scripts so the derivation cannot drift again.
#      PM2_HOME is derived the same way and persisted under the root.
#
#   2. THE GATE KNEW TWO PLATFORMS TO THIS SCRIPT'S THREE. Under a comment
#      claiming "identical derivation", ghl-mcp-assert-runtime.sh had no
#      linux-home branch, so a Linux container with no /data was judged as a Mac
#      and asked for two launchd plists nothing could ever run. Both platform
#      functions now come from the shared library, which also canonicalizes the
#      root so a /data that is really a symlink into $HOME reads as one root.
#
#   3. npm >= 11.19 TURNS NODE_ENV=production INTO omit=dev. Every launch
#      surface here sets NODE_ENV=production; a roll inheriting it made
#      `npm ci` install 106 packages instead of ~415 and the build died on
#      "Cannot find package 'typescript'". npm 11.13 did not. FIX: the compile
#      install runs with NODE_ENV unset and --include=dev, a guard fails loud
#      when typescript is absent afterwards, and the prune + runtime stay on
#      NODE_ENV=production.
#
# v21.6.0 (R1 + R9): the v21.5.0 release above declared config/ghl-mcp-pin.env
# the "single source of truth" — and never delivered it to a single box.
# update-skills.sh copied scripts/ and nothing else, then deleted its temp
# clone; the FIRST resolver candidate ($SELF_DIR/../config) pointed at
# $OC_CONFIG/config/, a directory neither installer created. Every weekly-
# updated box therefore ran on the hardcoded fallback constants baked into
# THIS FILE, a pin bump propagated nowhere, and the box-side QC gate hard-failed
# (proven: box layout rc=1, repo layout rc=0). Two changes, and they MUST ship
# together:
#   R1  both installers now deliver config/ to $OC_CONFIG/config/ and ASSERT it
#       landed; the resolver lists here, in the probe, in the VPS overlay and in
#       the static gate all carry that path, and CI cross-references the lists
#       against the delivery destinations so they cannot drift apart again.
#   R9  fail-closed. No pin file -> PIN_UNVERIFIED, no build, no start. Verdict
#       not CLEAN, or a vetting digest that does not recompute -> PIN_UNVETTED.
#       GHL_MCP_PIN_OVERRIDE now requires a matching vetting digest. The silent
#       built-in fallback commit is GONE — a fallback that quietly substitutes
#       for a missing source of truth is how the split-brain opened.
# R9 is only safe because R1 lands in the same commit: fail-closed BEFORE
# delivery works would brick the install path on every box.
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
#   D6. ALL-INTERFACES BIND ON A CRM-CREDENTIALED PORT (P0, added 2026-08-03).
#       Measured on the operator box: `lsof` -> `TCP *:8765 (LISTEN)`, i.e. 0.0.0.0 —
#       reachable from every host on the LAN — while `GET /tools` answers HTTP
#       200 with NO authentication at all. The endpoint IS the credential: any
#       local process, any LAN host, and (subject to each box's firewall) any
#       internet host can drive the client's CRM without holding the PIT.
#
#       WHY A PLAIN ENV VAR CANNOT FIX THIS — verified by reading the pinned
#       upstream source, not assumed. src/main.ts at the vetted commit ends with
#           app.listen(port, '0.0.0.0', () => { … })
#       The bind address is a HARDCODED STRING LITERAL. There is no HOST, no
#       MCP_SERVER_HOST, no config knob of any kind. Setting `HOST=127.0.0.1`
#       in the plist/pm2/systemd would look like a fix, would satisfy a naive
#       grep-based QC check, and would change NOTHING at runtime. We do not ship
#       fixes we cannot prove.
#
#       FIX (what this repo genuinely controls): we generate the launcher, so we
#       generate a tiny CommonJS bind guard next to it and load it with
#       `NODE_OPTIONS=--require`. It wraps net.Server.prototype.listen and
#       rewrites the host argument to a loopback address before the real listen
#       runs. No upstream change, no root, no firewall, and it applies to EVERY
#       supervisor (launchd, pm2, systemd, the fallback loop) because all four
#       run through the same launcher. Proven, not asserted:
#       tests/unit/ghl-mcp-bind-guard.test.sh boots a real node server that calls
#       `listen(port,'0.0.0.0')` with and without the guard and asserts the
#       observed bind address differs (0.0.0.0 -> 127.0.0.1).
#
#       STILL OPEN, and NOT fixable from this repo — both need a patch carried on
#       an org-controlled MIRROR of the upstream:
#         (a) `Origin` validation. The MCP spec says a local HTTP server MUST
#             validate Origin and answer 403. Upstream's cors() origin callback
#             calls back with an Error, which express renders as HTTP 500 — the
#             measured behaviour. Wrong status, and `!origin` is allowed outright.
#         (b) An `Authorization: Bearer` requirement on /mcp and /tools. There is
#             no auth middleware anywhere in the pinned tree.
#       Loopback binding is the mitigation that removes the LAN and internet
#       exposure today; it does not make a same-box process authenticate.
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

# ── STATUS reporter (callers grep this line; honest, never "done" on a gap) ──
# Declared BEFORE the path/pin resolution below because their fail-closed
# refusals report through it.
STATUS="UNKNOWN"
report() {
  STATUS="$1"; shift
  printf 'STATUS: ghl-mcp-autostart=%s %s\n' "$STATUS" "$*"
}

# ── Platform + paths: ONE derivation, shared with the runtime gate ───────────
# scripts/lib/ghl-mcp-paths.sh owns platform detection, the OpenClaw root, the
# Tier 2 install dir, the log dir and PM2_HOME. It used to be duplicated here
# and in ghl-mcp-assert-runtime.sh under a comment claiming the two were
# identical; they were not (the gate knew two platforms to this script's three)
# and both hardcoded an install path that does not survive a client-container
# recreate. See the header of the library for the full defect.
#
# The library is delivered by the SAME recursive scripts/ copy that delivers
# this file (update-skills.sh deliver_canonical_scripts_tree, install.sh
# `cp -r .../scripts`), so a box that has this script has the library too. If it
# genuinely is not there we refuse rather than guess a path: guessing is what
# produced a confident, wrong verdict about a healthy box.
_GHL_PATHS_LIB=""
for _c in "${GHL_MCP_PATHS_LIB:-}" \
          "$SELF_DIR/lib/ghl-mcp-paths.sh" \
          "$HOME/.openclaw/scripts/lib/ghl-mcp-paths.sh" \
          "$HOME/.openclaw/skills/scripts/lib/ghl-mcp-paths.sh" \
          "$HOME/.openclaw/onboarding/scripts/lib/ghl-mcp-paths.sh" \
          "/data/.openclaw/scripts/lib/ghl-mcp-paths.sh" \
          "/data/.openclaw/skills/scripts/lib/ghl-mcp-paths.sh" \
          "/data/.openclaw/onboarding/scripts/lib/ghl-mcp-paths.sh"; do
  [ -n "$_c" ] && [ -f "$_c" ] && { _GHL_PATHS_LIB="$_c"; break; }
done
if [ -z "$_GHL_PATHS_LIB" ]; then
  log "REFUSING: scripts/lib/ghl-mcp-paths.sh not found in any delivered location"
  report "PATHS_LIB_MISSING" \
    "(scripts/lib/ghl-mcp-paths.sh was not delivered to this box, so the Tier 2 install path and platform cannot be derived, so it refuses to guess. Re-run update-skills.sh or install.sh; both deliver the whole scripts/ tree recursively. Looked in: $SELF_DIR/lib, \$HOME/.openclaw/{scripts,skills/scripts,onboarding/scripts}/lib, /data/.openclaw/{scripts,skills/scripts,onboarding/scripts}/lib)"
  exit 0
fi
# shellcheck disable=SC1090
. "$_GHL_PATHS_LIB"
ghl_mcp_resolve_paths
PLATFORM="$GHL_MCP_RESOLVED_PLATFORM"
OC_ROOT="$GHL_MCP_RESOLVED_ROOT"
MCP_DIR="$GHL_MCP_RESOLVED_DIR"
LOG_DIR="$GHL_MCP_RESOLVED_LOG_DIR"
GHL_MCP_PM2_HOME="$GHL_MCP_RESOLVED_PM2_HOME"
OC_JSON="$OC_ROOT/openclaw.json"
SECRETS_ENV="$OC_ROOT/secrets/.env"

# ═══════════════════════════════════════════════════════════════════════════
# RETIREMENT MODE — GU-019/020/021. OPERATOR DECISION: the community MCP is
# RETIRED. This script is now a RETIREMENT tool, not a starter.
#
# Stages implemented here: 1 INVENTORY, 3 ARCHIVE (secret-free), 4 DISABLE
# RESURRECTION, 5 STOP ONLY THE MATCHED SERVICE, 6 VERIFY OFF, 7 RECEIPT.
# Stage 2 (replacement surfaces) is enforced by update-skills.sh BEFORE it
# calls --retire: a caller that still needs Tier 2 must never be stopped.
#
#   --retire [--dry-run]   run the ordered transaction / print the plan
#   --status               retirement-aware assertion; changes nothing
#   --help
#
# Exit: 0 = VERIFIED_OFF (or a dry run / status); 1 = MIGRATION_FAILED.
# Retirement is the ONE mode that may exit non-zero — the legacy wiring path
# below still exits 0 by its own contract.
#
# IDENTIFICATION IS EXACT. Every probe and every stop matches the plist label,
# the pm2 app name, the systemd unit name or the full supervise-script path.
# There is no pkill/pgrep on a broad pattern ("ghl", "node", the port) and the
# container/box is never touched.
# ═══════════════════════════════════════════════════════════════════════════
GHL_MCP_MODE="start"
GHL_MCP_DRY_RUN=0
for _ghl_arg in "$@"; do
  case "$_ghl_arg" in
    --retire|retire)             GHL_MCP_MODE="retire" ;;
    --status|--inventory|status) GHL_MCP_MODE="status" ;;
    --dry-run|-n)                GHL_MCP_DRY_RUN=1 ;;
    --start|start)               GHL_MCP_MODE="start" ;;
    --help|-h)
      printf 'ghl-mcp-autostart.sh — the community GHL MCP is RETIRED.\n\n'
      printf '  --retire [--dry-run]  inventory, archive, disable resurrection, stop, verify, receipt\n'
      printf '  --status              report VERIFIED_OFF or the live surfaces (no changes)\n'
      printf '  (no arguments)        refuses to start: this script never starts the service again\n'
      exit 0 ;;
    *) log "ignoring unknown argument: $_ghl_arg" ;;
  esac
done
unset _ghl_arg

RETIRE_LABEL="com.clawd.ghl-mcp"
RETIRE_PROBE_LABEL="com.clawd.ghl-mcp-probe"
RETIRE_PLIST="$HOME/Library/LaunchAgents/${RETIRE_LABEL}.plist"
RETIRE_PROBE_PLIST="$HOME/Library/LaunchAgents/${RETIRE_PROBE_LABEL}.plist"
RETIRE_PM2_APP="ghl-community-mcp"
RETIRE_SYSTEMD_UNIT="ghl-mcp"
RETIRE_SYSTEMD_PATH="/etc/systemd/system/ghl-mcp.service"
RETIRE_SUPERVISE="$MCP_DIR/.ghl-mcp-supervise.sh"
RETIRE_DIR="$OC_ROOT/.retired"
RETIRE_STATE_FILE="$RETIRE_DIR/ghl-mcp-retirement.json"
RETIRE_FAIL_FILE="$RETIRE_DIR/ghl-mcp-migration-failed.json"
# A retired box no longer needs the pin. Read it (read-only) only to learn the
# configured port; absence is NOT an error in retirement mode.
RETIRE_PIN=""
for _c in "$SELF_DIR/../config/ghl-mcp-pin.env" \
          "$OC_ROOT/config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/config/ghl-mcp-pin.env" \
          "/data/.openclaw/config/ghl-mcp-pin.env"; do
  [ -f "$_c" ] && { RETIRE_PIN="$(ghl_mcp_canon_dir "$(dirname "$_c")")/$(basename "$_c")"; break; }
done
unset _c
RETIRE_PORT="${GHL_MCP_PORT:-}"
if [ -z "$RETIRE_PORT" ] && [ -n "$RETIRE_PIN" ]; then
  RETIRE_PORT="$( . "$RETIRE_PIN" >/dev/null 2>&1; printf '%s' "${GHL_MCP_PORT:-}" )"
fi
RETIRE_PORT="${RETIRE_PORT:-8765}"

# ── small helpers ───────────────────────────────────────────────────────────
_ghl_sha256_file() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" 2>/dev/null | cut -d' ' -f1
  elif command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" 2>/dev/null | cut -d' ' -f1
  else return 1; fi
}

_ghl_json_str() { printf '%s' "${1:-}" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr '\n\r' '  '; }

_ghl_json_array() {  # newline-separated items -> ["a","b"]
  local out="" first=1 item
  while IFS= read -r item; do
    [ -n "$item" ] || continue
    [ "$first" = "1" ] || out="$out,"
    out="$out\"$(_ghl_json_str "$item")\""
    first=0
  done <<EOF
${1:-}
EOF
  printf '[%s]' "$out"
}

_ghl_launchd_loaded() {
  command -v launchctl >/dev/null 2>&1 || return 1
  launchctl print "gui/$(id -u)/$1" >/dev/null 2>&1
}

# prints: disabled | enabled | absent | unknown
_ghl_launchd_override() {
  command -v launchctl >/dev/null 2>&1 || { printf 'unknown'; return 0; }
  local o
  o="$(launchctl print-disabled "gui/$(id -u)" 2>/dev/null || true)"
  [ -n "$o" ] || { printf 'unknown'; return 0; }
  case "$o" in
    *"\"$1\" => disabled"*) printf 'disabled' ;;
    *"\"$1\" => enabled"*)  printf 'enabled' ;;
    *)                      printf 'absent' ;;
  esac
}

# rc: 0 tag present, 1 absent, 2 cannot read (no crontab on this box)
_ghl_cron_has() {
  command -v crontab >/dev/null 2>&1 || return 2
  local l; l="$(crontab -l 2>/dev/null || true)"
  case "$l" in *"$1"*) return 0 ;; esac
  return 1
}

# rc: 0 probe job present, 1 absent, 2 cannot read
_ghl_oc_cron_has() {
  command -v openclaw >/dev/null 2>&1 || return 2
  local o
  o="$(openclaw cron list 2>/dev/null)" || return 2
  case "$o" in *ghl-mcp-probe*) return 0 ;; esac
  return 1
}

# rc: 0 registered, 1 absent, 2 cannot read
_ghl_mcp_registered() {
  [ -f "$OC_JSON" ] || return 1
  command -v python3 >/dev/null 2>&1 || return 2
  python3 - "$OC_JSON" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(2)
servers = (d.get("mcp") or {}).get("servers") or {}
sys.exit(0 if "ghl-community-mcp" in servers else 1)
PYEOF
}

# The pm2 home (an EXISTING one) in which the app is registered. Empty when pm2
# is absent or the app is not registered anywhere. Never points PM2_HOME at a
# directory that does not exist — that would spawn a daemon on a read.
_ghl_pm2_home_with_app() {
  command -v pm2 >/dev/null 2>&1 || return 0
  local h
  for h in "$GHL_MCP_PM2_HOME" "$OC_ROOT/.pm2" "$HOME/.pm2" "/data/.pm2" "/root/.pm2"; do
    [ -n "$h" ] && [ -d "$h" ] || continue
    if PM2_HOME="$h" pm2 jlist 2>/dev/null | grep -q "\"name\"[[:space:]]*:[[:space:]]*\"$RETIRE_PM2_APP\""; then
      printf '%s' "$h"; return 0
    fi
  done
  for h in $(ps -eo args 2>/dev/null | sed -n 's/.*God Daemon (\(.*\))$/\1/p'); do
    [ -r "$h/pm2.pid" ] || continue
    if PM2_HOME="$h" pm2 jlist 2>/dev/null | grep -q "\"name\"[[:space:]]*:[[:space:]]*\"$RETIRE_PM2_APP\""; then
      printf '%s' "$h"; return 0
    fi
  done
  return 0
}

# PIDs whose COMMAND LINE carries one of THIS INSTALL's exact paths. Never a
# broad name: "ghl", "node" and the port are deliberately absent.
_ghl_matched_pids() {
  command -v pgrep >/dev/null 2>&1 || return 0
  local pat p cmd out=""
  for pat in "$MCP_DIR/dist/main.js" "$MCP_DIR/.ghl-mcp-launch.sh" "$RETIRE_SUPERVISE"; do
    [ -n "$pat" ] || continue
    for p in $(pgrep -f -- "$pat" 2>/dev/null || true); do
      case " $out " in *" $p "*) continue ;; esac
      cmd="$(ps -o command= -p "$p" 2>/dev/null || true)"
      case "$cmd" in *"$pat"*) out="$out $p" ;; esac
    done
  done
  printf '%s' "$out"
}

# prints: listening | none | unknown
_ghl_listener_state() {
  local o
  if command -v lsof >/dev/null 2>&1; then
    o="$(lsof -nP -iTCP:"$RETIRE_PORT" -sTCP:LISTEN 2>/dev/null | tail -n +2)"
    if [ -n "$o" ]; then printf 'listening'; else printf 'none'; fi
    return 0
  fi
  if command -v ss >/dev/null 2>&1; then
    o="$(ss -ltn 2>/dev/null | awk -v p=":${RETIRE_PORT}" 'NR>1 && index($4,p) {print; exit}')"
    if [ -n "$o" ]; then printf 'listening'; else printf 'none'; fi
    return 0
  fi
  if command -v netstat >/dev/null 2>&1; then
    o="$(netstat -an 2>/dev/null | awk -v p=".${RETIRE_PORT} " '/LISTEN/ && index($0,p) {print; exit}')"
    if [ -n "$o" ]; then printf 'listening'; else printf 'none'; fi
    return 0
  fi
  printf 'unknown'
}

# 1 when gateway.tls.enabled is true in the config file named by $1, else 0 (also
# unreadable). A TLS gateway answers https ONLY: an http:// probe gets an empty
# reply, so a healthy gateway would read as down.
_gw_tls_flag() {
  OC_CFG="$1" python3 -c 'import json,os
try:
    t=((json.load(open(os.environ["OC_CFG"])).get("gateway") or {}).get("tls") or {}).get("enabled")
    print(1 if str(t).lower()=="true" else 0)
except Exception:
    print(0)' 2>/dev/null || printf '0'
}

_ghl_gw_up() {
  command -v curl >/dev/null 2>&1 || return 1
  local port code s=http k=""
  port="18789"
  if [ -f "$OC_JSON" ] && command -v python3 >/dev/null 2>&1; then
    port="$(python3 - "$OC_JSON" <<'PYEOF' 2>/dev/null || printf '18789'
import json, sys
try:
    print(int((json.load(open(sys.argv[1])).get("gateway") or {}).get("port") or 18789))
except Exception:
    print(18789)
PYEOF
)"
  fi
  if [ -f "$OC_JSON" ] && [ "$(_gw_tls_flag "$OC_JSON")" = "1" ]; then s=https; k="-k"; fi
  # shellcheck disable=SC2086  # k is empty or the single word -k (loopback only)
  code="$(curl -s $k -o /dev/null -w '%{http_code}' --max-time 3 "$s://127.0.0.1:${port:-18789}/healthz" 2>/dev/null || true)"
  [ "$code" = "200" ]
}

# ── Stage 1: INVENTORY ──────────────────────────────────────────────────────
# Every surface is reported. A surface that cannot be read is `undetermined`,
# and an undetermined surface BLOCKS a VERIFIED_OFF claim (a false negative is
# exactly what this stage exists to prevent).
RET_INV_KINDS=""
RET_INV_UNDET=""
_ret_inv_add()   { RET_INV_KINDS="${RET_INV_KINDS}$1
"; }
_ret_inv_undet() { RET_INV_UNDET="${RET_INV_UNDET}$1
"; }

_ghl_ret_inventory() {
  RET_INV_KINDS=""; RET_INV_UNDET=""; RET_INV_INSTALL=0
  [ -d "$MCP_DIR" ] && RET_INV_INSTALL=1

  if [ "$PLATFORM" = "mac" ]; then
    if command -v launchctl >/dev/null 2>&1; then
      _ghl_launchd_loaded "$RETIRE_LABEL" && _ret_inv_add "launchd-service:$RETIRE_LABEL"
      [ -f "$RETIRE_PLIST" ] && _ret_inv_add "launchd-plist:$RETIRE_PLIST"
      _ghl_launchd_loaded "$RETIRE_PROBE_LABEL" && _ret_inv_add "launchd-probe:$RETIRE_PROBE_LABEL"
      [ -f "$RETIRE_PROBE_PLIST" ] && _ret_inv_add "launchd-probe-plist:$RETIRE_PROBE_PLIST"
    elif [ -f "$RETIRE_PLIST" ]; then
      _ret_inv_add "launchd-plist:$RETIRE_PLIST"
      _ret_inv_undet "launchd-service(no-launchctl)"
    fi
  fi

  if command -v pm2 >/dev/null 2>&1; then
    _ph="$(_ghl_pm2_home_with_app)"
    [ -n "$_ph" ] && _ret_inv_add "pm2-app:$RETIRE_PM2_APP@$_ph"
    unset _ph
  fi

  if [ -f "$RETIRE_SYSTEMD_PATH" ]; then
    _ret_inv_add "systemd-unit-file:$RETIRE_SYSTEMD_PATH"
  elif command -v systemctl >/dev/null 2>&1; then
    case "$(systemctl is-enabled "$RETIRE_SYSTEMD_UNIT" 2>/dev/null || true)" in
      enabled|enabled-runtime) _ret_inv_add "systemd-unit:$RETIRE_SYSTEMD_UNIT" ;;
    esac
  fi

  if command -v pgrep >/dev/null 2>&1; then
    _pids="$(_ghl_matched_pids)"
    [ -n "$_pids" ] && _ret_inv_add "process:$MCP_DIR"
    unset _pids
  else
    _ret_inv_undet "process(no-pgrep)"
  fi

  _ghl_cron_has "# managed:ghl-mcp-probe"
  case $? in 0) _ret_inv_add "cron-probe:managed:ghl-mcp-probe" ;; 2) _ret_inv_undet "cron(no-crontab)" ;; esac
  _ghl_cron_has "# managed:ghl-mcp-pm2-resurrect"
  case $? in 0) _ret_inv_add "cron-resurrect:managed:ghl-mcp-pm2-resurrect" ;; esac

  _ghl_oc_cron_has
  case $? in
    0) _ret_inv_add "openclaw-cron:ghl-mcp-probe" ;;
    2) _ret_inv_undet "openclaw-cron(unreadable)" ;;
  esac

  _ghl_mcp_registered
  case $? in
    0) _ret_inv_add "mcp-servers:ghl-community-mcp" ;;
    2) _ret_inv_undet "mcp-servers(unreadable)" ;;
  esac
}

# ── Stage 6: VERIFY OFF (read-only, evidence not inference) ─────────────────
RET_V_OK=""; RET_V_LIVE=""; RET_V_UNKNOWN=""
_ret_v_ok()   { RET_V_OK="${RET_V_OK} $1"; }
_ret_v_live() { RET_V_LIVE="${RET_V_LIVE} $1"; }
_ret_v_unk()  { RET_V_UNKNOWN="${RET_V_UNKNOWN} $1"; }

_ghl_ret_verify() {
  RET_V_OK=""; RET_V_LIVE=""; RET_V_UNKNOWN=""

  if [ "$PLATFORM" = "mac" ]; then
    if command -v launchctl >/dev/null 2>&1; then
      if _ghl_launchd_loaded "$RETIRE_LABEL"; then
        _ret_v_live "launchd:$RETIRE_LABEL"
      elif [ -f "$RETIRE_PLIST" ]; then
        _ret_v_live "launchd-plist:$RETIRE_PLIST"
      else
        case "$(_ghl_launchd_override "$RETIRE_LABEL")" in
          disabled|absent) _ret_v_ok "launchd:$RETIRE_LABEL" ;;
          enabled)         _ret_v_live "launchd-override:$RETIRE_LABEL" ;;
          *)               _ret_v_unk "launchd:$RETIRE_LABEL" ;;
        esac
      fi
      if _ghl_launchd_loaded "$RETIRE_PROBE_LABEL"; then
        _ret_v_live "launchd-probe:$RETIRE_PROBE_LABEL"
      elif [ -f "$RETIRE_PROBE_PLIST" ]; then
        _ret_v_live "launchd-probe-plist:$RETIRE_PROBE_PLIST"
      else
        case "$(_ghl_launchd_override "$RETIRE_PROBE_LABEL")" in
          disabled|absent) _ret_v_ok "launchd-probe:$RETIRE_PROBE_LABEL" ;;
          enabled)         _ret_v_live "launchd-probe-override:$RETIRE_PROBE_LABEL" ;;
          *)               _ret_v_unk "launchd-probe:$RETIRE_PROBE_LABEL" ;;
        esac
      fi
    else
      _ret_v_unk "launchd(no-launchctl)"
    fi
  fi

  if command -v pm2 >/dev/null 2>&1; then
    if [ -n "$(_ghl_pm2_home_with_app)" ]; then _ret_v_live "pm2:$RETIRE_PM2_APP"; else _ret_v_ok "pm2:$RETIRE_PM2_APP"; fi
  else
    _ret_v_ok "pm2:not-installed"
  fi

  if command -v systemctl >/dev/null 2>&1; then
    _en="$(systemctl is-enabled "$RETIRE_SYSTEMD_UNIT" 2>/dev/null || true)"
    _ac="$(systemctl is-active "$RETIRE_SYSTEMD_UNIT" 2>/dev/null || true)"
    case "$_en" in enabled|enabled-runtime) _ret_v_live "systemd-enabled:$_en" ;; esac
    case "$_ac" in active|activating) _ret_v_live "systemd-active:$_ac" ;; esac
    if [ -z "$_en$_ac" ]; then _ret_v_unk "systemd"; else _ret_v_ok "systemd:${_en:-none}/${_ac:-none}"; fi
    unset _en _ac
  elif [ -f "$RETIRE_SYSTEMD_PATH" ]; then
    _ret_v_live "systemd-unit-file:$RETIRE_SYSTEMD_PATH"
  else
    _ret_v_ok "systemd:not-installed"
  fi

  if command -v pgrep >/dev/null 2>&1; then
    if [ -n "$(_ghl_matched_pids)" ]; then _ret_v_live "process:$MCP_DIR"; else _ret_v_ok "process:none"; fi
  else
    _ret_v_unk "process(no-pgrep)"
  fi

  _ghl_cron_has "# managed:ghl-mcp-probe"
  case $? in 0) _ret_v_live "cron-probe" ;; 1) _ret_v_ok "cron-probe" ;; 2) _ret_v_unk "cron(no-crontab)" ;; esac
  _ghl_cron_has "# managed:ghl-mcp-pm2-resurrect"
  case $? in 0) _ret_v_live "cron-resurrect" ;; 1) _ret_v_ok "cron-resurrect" ;; esac

  _ghl_oc_cron_has
  case $? in 0) _ret_v_live "openclaw-cron:ghl-mcp-probe" ;; 1) _ret_v_ok "openclaw-cron" ;; 2) _ret_v_unk "openclaw-cron" ;; esac

  _ghl_mcp_registered
  case $? in 0) _ret_v_live "mcp-servers:ghl-community-mcp" ;; 1) _ret_v_ok "mcp-servers" ;; 2) _ret_v_unk "mcp-servers" ;; esac

  case "$(_ghl_listener_state)" in
    none)      _ret_v_ok "port:$RETIRE_PORT" ;;
    listening) _ret_v_live "port:$RETIRE_PORT" ;;
    *)         _ret_v_unk "port:$RETIRE_PORT" ;;
  esac
}

_ghl_ret_is_off() {
  [ -z "${RET_V_LIVE// /}" ] && [ -z "${RET_V_UNKNOWN// /}" ]
}
# ── Stage 3: ARCHIVE (secret-free, inert, never auto-restored) ──────────────
RET_ARCHIVE_DIR=""
RET_MANIFEST_HASH=""

# The actual secret VALUES this box holds — used to prove the archive does not
# contain them. Never printed, never written to the manifest.
_ghl_ret_secret_values() {
  local v val
  for v in GOHIGHLEVEL_API_KEY GHL_API_KEY; do
    val="$(printenv "$v" 2>/dev/null || true)"
    [ -n "$val" ] && printf '%s\n' "$val"
    if [ -f "$SECRETS_ENV" ]; then
      val="$(grep -E "^${v}=" "$SECRETS_ENV" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
      [ -n "$val" ] && printf '%s\n' "$val"
    fi
  done
  for v in "$MCP_DIR/.env" "$MCP_DIR/.ghl-mcp.env"; do
    [ -f "$v" ] || continue
    grep -hE '^(GHL_API_KEY|GOHIGHLEVEL_API_KEY)=' "$v" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'"
  done
  if [ -f "$OC_JSON" ] && command -v python3 >/dev/null 2>&1; then
    python3 - "$OC_JSON" <<'PYEOF' 2>/dev/null
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
for k in ("GHL_API_KEY", "GOHIGHLEVEL_API_KEY", "GOHIGHLEVEL_LOCATION_ID"):
    v = ((d.get("env") or {}).get("vars") or {}).get(k)
    if v:
        print(v)
PYEOF
  fi
}

_ghl_ret_archive_secret_scan() {
  local d="$1" val rc=0
  # 1. No credential-shaped FILE may survive the excludes.
  if find "$d" -type f -not -path '*node_modules*' \( -name '.env' -o -name '.ghl-mcp.env' -o -name '*.pem' \
       -o -name '*.key' -o -name 'credentials.json' -o -name 'cookies*' -o -name 'token*' \) \
       2>/dev/null | grep -q .; then
    return 1
  fi
  # 1b. No env-file shape may survive the tar excludes into the tree. Scoped to
  #     tree/: supervisor/ legitimately carries the delivered ghl-mcp-pin.env.
  if find "$d/tree" -type f \( -name '.env' -o -name '.env.*' -o -name '*.env' \
       -o -name '*.env.bak*' -o -name '.env.bak-*' \) 2>/dev/null | grep -q .; then
    return 1
  fi
  # 2. No live secret VALUE may appear anywhere in the archived bytes.
  while IFS= read -r val; do
    [ -n "$val" ] || continue
    if grep -rIlF --exclude-dir="*node_modules*" -- "$val" "$d" 2>/dev/null | grep -q .; then
      rc=1
      break
    fi
  done <<EOF
$(_ghl_ret_secret_values)
EOF
  [ "$rc" = "0" ] || return 1
  # 3. No private-key block.
  if grep -rIlE --exclude-dir="*node_modules*" -- '-----BEGIN [A-Z ]*PRIVATE KEY-----' "$d" 2>/dev/null | grep -q .; then
    return 1
  fi
  return 0
}

_ghl_ret_archive() {
  local src="$MCP_DIR" dest payload f
  dest="$RETIRE_DIR/archive-$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$dest/tree" "$dest/supervisor" 2>/dev/null || return 1

  if [ -d "$src" ]; then
    command -v tar >/dev/null 2>&1 || return 1
    # Every env-file SHAPE stays out of the archive, not just the two exact
    # names: a client's own backup (.env.bak-<ts>, .env.production, prod.env,
    # x.env.bak2) holds the live key, and archiving it made the secret scan
    # below refuse every retirement (Big Fleet Roll 20261029). tar only reads:
    # the files stay exactly where the client put them. The scan keeps these
    # five shapes in step (check 1b) and still guards every other byte.
    payload="$dest/community-mcp.tar"
    ( cd "$src" && tar -cf "$payload" \
        --exclude 'node_modules' --exclude '*/node_modules' --exclude './node_modules' \
        --exclude '*node_modules*' \
        --exclude '.env' --exclude './.env' --exclude '.ghl-mcp.env' --exclude './.ghl-mcp.env' \
        --exclude '.env.*' --exclude '*.env' --exclude '*.env.bak*' --exclude '.env.bak-*' \
        --exclude '.git' --exclude './.git' \
        --exclude '*.log' --exclude 'logs' --exclude './logs' \
        --exclude '*.db' --exclude '*.sqlite' --exclude '*.sqlite3' \
        . 2>/dev/null ) || return 1
    tar -xf "$payload" -C "$dest/tree" 2>/dev/null || return 1
    rm -f "$payload"
  fi

  for f in "$RETIRE_PLIST" "$RETIRE_PROBE_PLIST" "$RETIRE_SYSTEMD_PATH" "$RETIRE_PIN"; do
    [ -n "$f" ] && [ -f "$f" ] && cp -p "$f" "$dest/supervisor/" 2>/dev/null
  done
  for f in "$HOME/Library/LaunchAgents/${RETIRE_LABEL}.plist".* \
           "$HOME/Library/LaunchAgents/${RETIRE_PROBE_LABEL}.plist".* \
           "$MCP_DIR/ecosystem.config.js" "$MCP_DIR/.ghl-mcp-supervise.sh" \
           "$MCP_DIR/.ghl-mcp-launch.sh" "$MCP_DIR/.ghl-mcp-build.json"; do
    [ -f "$f" ] && cp -p "$f" "$dest/supervisor/" 2>/dev/null
  done
  if command -v crontab >/dev/null 2>&1; then
    crontab -l 2>/dev/null | grep -E 'managed:ghl-mcp-(probe|pm2-resurrect)' \
      > "$dest/supervisor/crontab-managed.txt" 2>/dev/null || true
  fi

  # Manifest: sha256 of EVERY archived file, then the digest of the manifest.
  ( cd "$dest" && find . -type f ! -name 'manifest.sha256' -print | LC_ALL=C sort | \
    while IFS= read -r f; do
      h="$(_ghl_sha256_file "$f" 2>/dev/null || true)"
      [ -n "$h" ] && printf '%s  %s\n' "$h" "${f#./}"
    done ) > "$dest/manifest.sha256" 2>/dev/null || return 1
  [ -s "$dest/manifest.sha256" ] || return 1
  RET_MANIFEST_HASH="$(_ghl_sha256_file "$dest/manifest.sha256" 2>/dev/null || true)"
  [ -n "$RET_MANIFEST_HASH" ] || return 1

  RET_ARCHIVE_DIR="$dest"
  _ghl_ret_archive_secret_scan "$dest" || return 2
  return 0
}

# ── Stage 4 + 5: DISABLE RESURRECTION, STOP ONLY THE MATCHED SERVICE ────────
RET_DISABLED=""
RET_STOP_NOTES=""
_ret_dis()  { RET_DISABLED="${RET_DISABLED}$1
"; }
_ret_stop() { RET_STOP_NOTES="${RET_STOP_NOTES}$1
"; }

_ghl_systemctl() {
  if [ "$(id -u 2>/dev/null || echo 0)" = "0" ]; then systemctl "$@"; else sudo -n systemctl "$@"; fi
}
_ghl_rm_root() {
  if [ "$(id -u 2>/dev/null || echo 0)" = "0" ]; then rm -f "$1"; else sudo -n rm -f "$1"; fi
}

_ghl_ret_remove_cron_tag() {  # <tag>
  local tag="$1" cur new
  command -v crontab >/dev/null 2>&1 || return 1
  cur="$(crontab -l 2>/dev/null || true)"
  case "$cur" in *"$tag"*) ;; *) return 0 ;; esac
  new="$(printf '%s\n' "$cur" | grep -vF "$tag" 2>/dev/null || true)"
  printf '%s\n' "$new" | grep -v '^$' | crontab - >/dev/null 2>&1 || return 1
  case "$(crontab -l 2>/dev/null || true)" in *"$tag"*) return 1 ;; esac
  return 0
}

# Move a plist (and its historical .bak copies) into the inert archive.
_ghl_ret_archive_plist() {  # <plist>
  local p="$1" b
  [ -f "$p" ] || return 0
  mkdir -p "$RET_ARCHIVE_DIR/supervisor" 2>/dev/null || return 1
  mv "$p" "$RET_ARCHIVE_DIR/supervisor/$(basename "$p")" 2>/dev/null || return 1
  for b in "$p".*; do
    [ -f "$b" ] || continue
    mv "$b" "$RET_ARCHIVE_DIR/supervisor/$(basename "$b")" 2>/dev/null || true
  done
  return 0
}

_ghl_ret_disable_stop() {
  RET_DISABLED=""; RET_STOP_NOTES=""

  # 4.1 / 4.2 — probe schedules go FIRST. A probe that heals can restart the
  # service after we stop it; the schedule must be gone before the stop.
  if _ghl_cron_has "# managed:ghl-mcp-probe"; then
    if _ghl_ret_remove_cron_tag "# managed:ghl-mcp-probe"; then
      _ret_dis "cron:# managed:ghl-mcp-probe"
    else
      _ret_dis "cron-removal-FAILED:# managed:ghl-mcp-probe"
    fi
  fi
  if _ghl_oc_cron_has; then
    if command -v openclaw >/dev/null 2>&1 && _ghl_gw_up; then
      openclaw cron delete --name "ghl-mcp-probe" >/dev/null 2>&1 || true
    fi
    if _ghl_oc_cron_has; then
      _ret_dis "openclaw-cron-removal-FAILED:ghl-mcp-probe"
    else
      _ret_dis "openclaw-cron:ghl-mcp-probe"
    fi
  fi

  # 4.2b — launchd probe job: bootout + disable + quarantine the plist.
  if [ "$PLATFORM" = "mac" ] && command -v launchctl >/dev/null 2>&1; then
    launchctl bootout "gui/$(id -u)/$RETIRE_PROBE_LABEL" >/dev/null 2>&1 || true
    if [ -f "$RETIRE_PROBE_PLIST" ]; then launchctl bootout "gui/$(id -u)" "$RETIRE_PROBE_PLIST" >/dev/null 2>&1 || true; fi
    launchctl disable "gui/$(id -u)/$RETIRE_PROBE_LABEL" >/dev/null 2>&1 || true
    _ghl_ret_archive_plist "$RETIRE_PROBE_PLIST" || true
    if _ghl_launchd_loaded "$RETIRE_PROBE_LABEL"; then
      _ret_dis "launchd-probe-bootout-FAILED:$RETIRE_PROBE_LABEL"
    else
      _ret_dis "launchd-probe:$RETIRE_PROBE_LABEL"
    fi
  fi

  # 5.0 — the detached setsid RELAUNCH LOOP is a restart authority. Stop it by
  # the exact PID whose cmdline carries the supervise script path; never by a
  # broad pattern. Only after that can the launchd/pm2 job stay stopped.
  if command -v pgrep >/dev/null 2>&1; then
    local p cmd i
    for p in $(_ghl_matched_pids); do
      cmd="$(ps -o command= -p "$p" 2>/dev/null || true)"
      case "$cmd" in
        *"$RETIRE_SUPERVISE"*)
          kill -TERM "$p" 2>/dev/null || true
          i=0
          while kill -0 "$p" 2>/dev/null && [ "$i" -lt 10 ]; do sleep 1; i=$((i+1)); done
          if kill -0 "$p" 2>/dev/null; then kill -KILL "$p" 2>/dev/null || true; sleep 1; fi
          if kill -0 "$p" 2>/dev/null; then
            _ret_stop "setsid-supervise-STILL-RUNNING:pid=$p"
          else
            _ret_dis "setsid-supervise:$p"
          fi
          ;;
      esac
    done
    unset p cmd i
  fi

  # 4.1 / 5.1 — launchd service: bootout (stop) + disable (the resurrection
  # bit; bootout alone leaves the job enabled) + quarantine the plist.
  if [ "$PLATFORM" = "mac" ] && command -v launchctl >/dev/null 2>&1; then
    launchctl bootout "gui/$(id -u)/$RETIRE_LABEL" >/dev/null 2>&1 || true
    if [ -f "$RETIRE_PLIST" ]; then launchctl bootout "gui/$(id -u)" "$RETIRE_PLIST" >/dev/null 2>&1 || true; fi
    launchctl disable "gui/$(id -u)/$RETIRE_LABEL" >/dev/null 2>&1 || true
    _ghl_ret_archive_plist "$RETIRE_PLIST" || true
    _ret_dis "launchd:$RETIRE_LABEL"
    # RE-READ. A bootout that exited 0 (or was swallowed by || true) is not
    # proof the job stopped; launchd can refuse while the job stays loaded.
    if _ghl_launchd_loaded "$RETIRE_LABEL"; then
      _ret_stop "launchd-bootout-FAILED:$RETIRE_LABEL"
    else
      _ret_stop "launchd-bootout:$RETIRE_LABEL"
    fi
  fi

  # 4.3 / 5.2 — pm2: delete ONLY this app under the home that registers it,
  # then SAVE. Delete without save leaves the resurrect dump holding the app.
  local ph
  ph="$(_ghl_pm2_home_with_app)"
  if [ -n "$ph" ]; then
    PM2_HOME="$ph" pm2 delete "$RETIRE_PM2_APP" >/dev/null 2>&1 || true
    # RE-READ: an exit 0 is not proof the app left the list.
    if PM2_HOME="$ph" pm2 jlist 2>/dev/null | grep -q "\"name\"[[:space:]]*:[[:space:]]*\"$RETIRE_PM2_APP\""; then
      _ret_stop "pm2-delete-FAILED:$RETIRE_PM2_APP@$ph"
    else
      _ret_stop "pm2-delete:$RETIRE_PM2_APP@$ph"
    fi
    if PM2_HOME="$ph" pm2 save >/dev/null 2>&1; then
      _ret_dis "pm2-save:$ph"
    else
      _ret_dis "pm2-save-FAILED:$ph"
    fi
    # 4.4 — the @reboot resurrect line. Remove it ONLY when this app was the
    # only thing in the dump; otherwise it serves Command Center and is
    # preserved (save already dropped the retired app, so it cannot come back).
    local remaining=""
    remaining="$(PM2_HOME="$ph" pm2 jlist 2>/dev/null | grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' | wc -l | tr -d ' ')"
    if [ "${remaining:-0}" = "0" ]; then
      if _ghl_ret_remove_cron_tag "# managed:ghl-mcp-pm2-resurrect"; then
        _ret_dis "cron:# managed:ghl-mcp-pm2-resurrect"
      fi
    else
      _ret_dis "cron-resurrect-RETAINED:serves $remaining other pm2 app(s)"
    fi
    unset remaining
  fi
  unset ph

  # 4.5 / 5.3 — systemd: disable --now, remove the unit, daemon-reload.
  if command -v systemctl >/dev/null 2>&1; then
    case "$(systemctl is-enabled "$RETIRE_SYSTEMD_UNIT" 2>/dev/null || true)" in
      enabled|enabled-runtime)
        _ghl_systemctl disable --now "$RETIRE_SYSTEMD_UNIT" >/dev/null 2>&1 || true
        # RE-READ both halves; a quiet systemctl is not a receipt.
        case "$(systemctl is-enabled "$RETIRE_SYSTEMD_UNIT" 2>/dev/null || true)" in
          enabled|enabled-runtime) _ret_dis "systemd-disable-FAILED:$RETIRE_SYSTEMD_UNIT" ;;
          *)                       _ret_dis "systemd-disable:$RETIRE_SYSTEMD_UNIT" ;;
        esac
        case "$(systemctl is-active "$RETIRE_SYSTEMD_UNIT" 2>/dev/null || true)" in
          active|activating) _ret_stop "systemd-stop-FAILED:$RETIRE_SYSTEMD_UNIT" ;;
          *)                 _ret_stop "systemd-stop:$RETIRE_SYSTEMD_UNIT" ;;
        esac
        ;;
    esac
  fi
  if [ -f "$RETIRE_SYSTEMD_PATH" ]; then
    _ghl_rm_root "$RETIRE_SYSTEMD_PATH" >/dev/null 2>&1 || true
    [ -f "$RETIRE_SYSTEMD_PATH" ] && _ret_dis "systemd-unit-removal-FAILED:$RETIRE_SYSTEMD_PATH"
    [ -f "$RETIRE_SYSTEMD_PATH" ] || _ret_dis "systemd-unit-removed:$RETIRE_SYSTEMD_PATH"
    if command -v systemctl >/dev/null 2>&1; then _ghl_systemctl daemon-reload >/dev/null 2>&1 || true; fi
  fi

  # 4.8 — the mcp.servers registration is a persistence surface even without a
  # process. Remove it through the CLI (never hand-edit openclaw.json: the
  # gateway rewrites it from memory) and RE-READ.
  if _ghl_mcp_registered; then
    if command -v openclaw >/dev/null 2>&1 && _ghl_gw_up; then
      openclaw mcp unset "$RETIRE_PM2_APP" >/dev/null 2>&1 || \
        openclaw mcp remove "$RETIRE_PM2_APP" >/dev/null 2>&1 || true
      if _ghl_mcp_registered; then
        _ret_dis "mcp-servers-removal-FAILED:ghl-community-mcp"
      else
        _ret_dis "mcp-servers:ghl-community-mcp"
      fi
    else
      _ret_dis "mcp-servers-removal-FAILED:gateway-not-up"
    fi
  fi

  # The delivered pin is what a start path needs; on a retired box it is a
  # re-installation surface. Remove ONLY the delivered copy, never a repo
  # checkout's own config/ghl-mcp-pin.env.
  if [ -n "$RETIRE_PIN" ] && [ -f "$RETIRE_PIN" ]; then
    case "$RETIRE_PIN" in
      "$OC_ROOT"/config/*|"$HOME"/.openclaw/config/*|/data/.openclaw/config/*)
        rm -f "$RETIRE_PIN" 2>/dev/null || true
        [ -f "$RETIRE_PIN" ] && _ret_dis "pin-removal-FAILED:$RETIRE_PIN"
        [ -f "$RETIRE_PIN" ] || _ret_dis "pin-removed:$RETIRE_PIN"
        ;;
    esac
  fi
}

# ── Stage 7: RECEIPT ────────────────────────────────────────────────────────
_ghl_ret_receipt() {  # <final_state> <stage> <reason>
  local state="$1" stage="$2" reason="$3" path ts kind_list commit
  if [ "$state" = "VERIFIED_OFF" ]; then path="$RETIRE_STATE_FILE"; else path="$RETIRE_FAIL_FILE"; fi
  mkdir -p "$RETIRE_DIR" 2>/dev/null || return 1
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  kind_list="$(printf '%s' "$RET_INV_KINDS" | tr '\n' ',' | sed 's/,$//')"
  commit="${GHL_MCP_VETTED_COMMIT:-}"
  if [ -z "$commit" ] && [ -d "$MCP_DIR/.git" ]; then
    commit="$(git -C "$MCP_DIR" rev-parse HEAD 2>/dev/null || true)"
  fi
  {
    printf '{\n'
    printf '  "schema": "ghl-mcp-retirement-receipt/v1",\n'
    printf '  "final_state": "%s",\n' "$(_ghl_json_str "$state")"
    printf '  "stage": "%s",\n' "$(_ghl_json_str "$stage")"
    printf '  "reason": "%s",\n' "$(_ghl_json_str "$reason")"
    printf '  "timestamp_utc": "%s",\n' "$ts"
    printf '  "box": {"hostname": "%s", "user": "%s", "platform": "%s", "cohort": "%s"},\n' \
      "$(_ghl_json_str "$(hostname 2>/dev/null || printf unknown)")" \
      "$(_ghl_json_str "$(id -un 2>/dev/null || printf unknown)")" \
      "$(_ghl_json_str "$PLATFORM")" "$(_ghl_json_str "$PLATFORM")"
    printf '  "release": {"from": "%s", "to": "%s", "commit": "%s"},\n' \
      "$(_ghl_json_str "${GHL_MCP_RECEIPT_FROM_RELEASE:-unknown}")" \
      "$(_ghl_json_str "${GHL_MCP_RECEIPT_TO_RELEASE:-unknown}")" \
      "$(_ghl_json_str "$commit")"
    printf '  "old_service": {"kind": "%s", "identity": "%s", "install_dir": "%s", "pin": "%s"},\n' \
      "$(_ghl_json_str "$kind_list")" \
      "$(_ghl_json_str "${RETIRE_LABEL}|${RETIRE_PM2_APP}|${RETIRE_SYSTEMD_UNIT}")" \
      "$(_ghl_json_str "$MCP_DIR")" "$(_ghl_json_str "${RETIRE_PIN:-none}")"
    printf '  "archive": {"path": "%s", "manifest_sha256": "%s"},\n' \
      "$(_ghl_json_str "${RET_ARCHIVE_DIR:-none}")" "$(_ghl_json_str "${RET_MANIFEST_HASH:-none}")"
    printf '  "migrated_callers": %s,\n' "$(_ghl_json_array "${GHL_MCP_RECEIPT_CALLERS:-}")"
    printf '  "disabled_hooks": %s,\n' "$(_ghl_json_array "$RET_DISABLED")"
    printf '  "stop_result": %s,\n' "$(_ghl_json_array "$RET_STOP_NOTES")"
    printf '  "verification": {"ok": %s, "live": %s, "unknown": %s},\n' \
      "$(_ghl_json_array "$RET_V_OK")" "$(_ghl_json_array "$RET_V_LIVE")" "$(_ghl_json_array "$RET_V_UNKNOWN")"
    printf '  "remediation": "%s"\n' "$(_ghl_json_str "${GHL_MCP_RECEIPT_REMEDIATION:-}")"
    printf '}\n'
  } > "$path" 2>/dev/null || return 1
  [ -s "$path" ] || return 1
  if [ -n "$RET_ARCHIVE_DIR" ] && [ -d "$RET_ARCHIVE_DIR" ]; then
    cp -p "$path" "$RET_ARCHIVE_DIR/receipt.json" 2>/dev/null || true
  fi
  return 0
}

_ghl_ret_fail() {  # <stage> <reason>
  GHL_MCP_RECEIPT_REMEDIATION="${GHL_MCP_RECEIPT_REMEDIATION:-Resolve the residual surface named above, then re-run: bash $0 --retire}"
  _ghl_ret_receipt "MIGRATION_FAILED" "$1" "$2" || true
  report "MIGRATION_FAILED" "(stage=$1 residual=[live:${RET_V_LIVE:-none} unknown:${RET_V_UNKNOWN:-none}] $(printf '%s' "$2") — success marker NOT written; see $RETIRE_FAIL_FILE)"
  log "MIGRATION_FAILED at stage $1: $2"
  log "residual live:${RET_V_LIVE:-none} unknown:${RET_V_UNKNOWN:-none}"
  exit 1
}

# ── retirement entry point (retire / status only; start falls through) ───────
_ghl_ret_main() {
  _ghl_ret_inventory
  _ghl_ret_verify

  if [ "$GHL_MCP_MODE" = "status" ]; then
    if _ghl_ret_is_off; then
      report "RETIRED_VERIFIED_OFF" "(no community MCP surface is live and none is undetermined — checked launchd, pm2, systemd, the supervise loop, both cron schedules, mcp.servers, the process and :$RETIRE_PORT)"
    else
      report "SERVICE_PRESENT" "(surfaces=[$(printf '%s' "$RET_INV_KINDS" | tr '\n' ' ')] undetermined=[$(printf '%s' "$RET_INV_UNDET" | tr '\n' ' ')] verify_live=[${RET_V_LIVE}] verify_unknown=[${RET_V_UNKNOWN}] — the community MCP is NOT retired on this box)"
    fi
    exit 0
  fi

  if _ghl_ret_is_off; then
    if [ -f "$RETIRE_STATE_FILE" ]; then
      report "RETIRED_VERIFIED_OFF" "(already retired; receipt $RETIRE_STATE_FILE — nothing changed)"
    else
      report "RETIRED_VERIFIED_OFF" "(no community MCP surface exists on this box — nothing to retire, nothing changed)"
    fi
    exit 0
  fi

  if [ "$GHL_MCP_DRY_RUN" = "1" ]; then
    log "DRY RUN — plan (nothing below is executed):"
    log "  1 INVENTORY  install_dir=$MCP_DIR pin=${RETIRE_PIN:-none} port=$RETIRE_PORT"
    printf '%s' "$RET_INV_KINDS" | while IFS= read -r l; do [ -n "$l" ] && log "     surface: $l"; done
    printf '%s' "$RET_INV_UNDET" | while IFS= read -r l; do [ -n "$l" ] && log "     UNDETERMINED (blocks a verified-off claim): $l"; done
    log "  2 STAGE      enforced by the caller (update-skills.sh) BEFORE --retire"
    log "  3 ARCHIVE    -> $RETIRE_DIR/archive-<utc>/ (tree + supervisor artifacts + sha256 manifest; no .env/tokens/logs)"
    log "  4 DISABLE    launchd bootout+disable+quarantine plists; pm2 delete+save+resurrect-cron decision; systemd disable+unit removal; cron probe+resurrect tags; openclaw cron probe; mcp.servers entry"
    log "  5 STOP       only the matched identity (label / pm2 app / unit / exact supervise path)"
    log "  6 VERIFY     no process, no listener on :$RETIRE_PORT, supervisor absent-or-disabled, no mcp.servers entry"
    log "  7 RECEIPT    $RETIRE_STATE_FILE (VERIFIED_OFF) or $RETIRE_FAIL_FILE (MIGRATION_FAILED)"
    report "RETIRE_DRY_RUN" "(plan printed; nothing was touched. live=[${RET_V_LIVE}] unknown=[${RET_V_UNKNOWN}])"
    exit 0
  fi

  # 3 ARCHIVE (fail closed BEFORE anything is stopped)
  _ghl_ret_archive
  local _arc_rc=$?
  if [ "$_arc_rc" = "2" ]; then
    _ghl_ret_verify
    _ghl_ret_fail "archive-secret-risk" "the secret scan found credential-shaped bytes or a live secret value under ${RET_ARCHIVE_DIR:-<archive>}; NOTHING was disabled and the source tree was NOT deleted. Inspect and remove the named bytes, then re-run."
  fi
  if [ "$_arc_rc" != "0" ]; then
    _ghl_ret_fail "archive" "could not build a verified secret-free archive under $RETIRE_DIR (tar/find/sha256 unavailable, or the archive dir is not writable). NOTHING was disabled and the source tree was NOT deleted."
  fi

  # 4 + 5 DISABLE RESURRECTION / STOP ONLY THE MATCHED SERVICE
  _ghl_ret_disable_stop
  case "$RET_DISABLED" in
    *FAILED*) _ghl_ret_verify; _ghl_ret_fail "disable-resurrection" "one or more resurrection paths could not be proven disabled: $(printf '%s' "$RET_DISABLED" | tr '\n' ' ')" ;;
  esac
  case "$RET_STOP_NOTES" in
    *FAILED*|*STILL-RUNNING*) _ghl_ret_verify; _ghl_ret_fail "stop" "the matched service could not be proven stopped: $(printf '%s' "$RET_STOP_NOTES" | tr '\n' ' ')" ;;
  esac

  # 6 VERIFY OFF
  _ghl_ret_verify
  if ! _ghl_ret_is_off; then
    _ghl_ret_fail "verify-off" "the retired surfaces are still observable"
  fi

  # 7 RECEIPT — written only after every surface passed.
  GHL_MCP_RECEIPT_REMEDIATION="none"
  if ! _ghl_ret_receipt "VERIFIED_OFF" "complete" "community MCP retired and verified off"; then
    report "MIGRATION_FAILED" "(stage=receipt — every surface verified OFF but the receipt could not be written to $RETIRE_STATE_FILE. The box IS off; fix the directory and re-run --retire.)"
    exit 1
  fi
  report "RETIRED_VERIFIED_OFF" "(community MCP retired: archive=$RET_ARCHIVE_DIR manifest_sha256=${RET_MANIFEST_HASH}; verified no process, no listener on :$RETIRE_PORT, supervisors absent/disabled, no mcp.servers entry; receipt=$RETIRE_STATE_FILE)"
  exit 0
}

case "$GHL_MCP_MODE" in
  retire|status) _ghl_ret_main ;;
esac
log "platform=$PLATFORM root=$OC_ROOT install=$MCP_DIR logs=$LOG_DIR (paths lib: $_GHL_PATHS_LIB)"
mkdir -p "$LOG_DIR" 2>/dev/null || true

# ── Pin + profile: ONE source of truth (config/ghl-mcp-pin.env) ──────────────
# R1 (v21.6.0): the pin file used to exist ONLY in the repo. update-skills.sh
# delivered scripts/ and nothing else and then deleted its temp clone, so on
# every weekly-updated box all five candidates below missed and the script ran
# on hardcoded fallback constants — a pin bump propagated to no box at all.
# Both installers now deliver config/ to $OC_CONFIG/config/, and that path is
# the FIRST candidate here ($SELF_DIR/../config resolves to it when this script
# runs from its delivered home, $OC_CONFIG/scripts/).
#
# ⚠️ ANY CHANGE TO THIS LIST must be mirrored in ghl-mcp-probe.sh, the VPS
# overlay, qc-assert-ghl-mcp-supervised.sh, AND the delivery step in BOTH
# installers. scripts/qc-assert-pin-delivery-paths.sh fails CI if they drift.
_PIN_FILE=""
for _c in "$SELF_DIR/../config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/onboarding/config/ghl-mcp-pin.env" \
          "/data/.openclaw/config/ghl-mcp-pin.env" \
          "/data/.openclaw/onboarding/config/ghl-mcp-pin.env"; do
  [ -f "$_c" ] && { _PIN_FILE="$_c"; break; }
done

# ── R9: FAIL-CLOSED. No pin file = no build, no start. ───────────────────────
# There is NO built-in fallback commit any more. A silent fallback is exactly
# what let v21.5.0 believe it had one source of truth while every box ran on a
# constant baked into this file — and it is what made a pin bump a no-op
# fleet-wide. If the delivery did not happen, that is a broken install and it
# must be LOUD, not papered over with a hardcoded SHA.
if [ -z "$_PIN_FILE" ]; then
  log "REFUSING: config/ghl-mcp-pin.env not found in any delivered location"
  report "PIN_UNVERIFIED" \
    "(config/ghl-mcp-pin.env was not delivered to this box — refusing to build/start an unverified third-party MCP. Re-run update-skills.sh or install.sh; both deliver config/ to \$OC_CONFIG/config/. Looked in: $SELF_DIR/../config, \$HOME/.openclaw/{config,onboarding/config}, /data/.openclaw/{config,onboarding/config})"
  exit 0
fi
# shellcheck disable=SC1090
. "$_PIN_FILE"
log "pin config: $_PIN_FILE"

# Operational defaults only. NOTHING security-relevant (commit, profile, repo
# URL) may default here — those must come from the delivered pin file.
GHL_MCP_PROBE_TIMEOUT="${GHL_MCP_PROBE_TIMEOUT:-30}"   # v25.1.10: 10s tripped on loaded boxes
GHL_MCP_VETTED_COMMIT="${GHL_MCP_VETTED_COMMIT:-}"
GHL_MCP_TOOL_PROFILE="${GHL_MCP_TOOL_PROFILE:-}"
GHL_MCP_REPO_URL="${GHL_MCP_REPO_URL:-}"
GHL_MCP_PIN_VETTED_VERDICT="${GHL_MCP_PIN_VETTED_VERDICT:-}"
GHL_MCP_PIN_VETTED_DIGEST="${GHL_MCP_PIN_VETTED_DIGEST:-}"

# D6 (P0 SECURITY): the loopback bind host enforced by the generated bind guard.
# READ write_bind_guard() below before changing this — the upstream server does
# NOT read any host variable; this value is consumed by OUR guard, not by main.js.
GHL_MCP_BIND_HOST="${GHL_MCP_BIND_HOST:-127.0.0.1}"
# Supply-chain: sha256 of package-lock.json at the pinned commit. When declared
# (pin file or caller env) the build REFUSES on a mismatch; when empty the build
# still records the observed value in the build stamp so the binding can be armed.
GHL_MCP_DEPS_LOCK_SHA256="${GHL_MCP_DEPS_LOCK_SHA256:-}"

if [ -z "$GHL_MCP_TOOL_PROFILE" ] || [ -z "$GHL_MCP_REPO_URL" ]; then
  report "PIN_UNVERIFIED" \
    "($_PIN_FILE is present but does not declare GHL_MCP_TOOL_PROFILE and/or GHL_MCP_REPO_URL — a truncated/corrupt pin file is not a source of truth. Refusing to build/start.)"
  exit 0
fi

# ── R9: the vetting verdict is ENFORCED, not decorative ──────────────────────
# Two modes, and the switch between them is automatic:
#   DIGEST MODE  (GHL_MCP_PIN_VETTED_DIGEST is non-empty) — the digest must
#     recompute over commit|verdict|on|by|deps_lock_sha256. A hand-edited SHA
#     leaves a stale digest and we refuse. Forgetting produces refusal.
#   FALLBACK MODE (no digest field yet — the transitional state while
#     scripts/ghl-mcp-vet-pin.sh is still being built) — require the explicit
#     CLEAN verdict. Weaker (one word defeats it) but strictly better than
#     v21.5.0, where the verdict was sourced by three scripts and read by none.
# B3 reference shape: this list was ALREADY correct — it carries the delivered
# $OC_ROOT/scripts path on both platforms, with the legacy skills/scripts pair
# after it. That is why the digest tool resolved on the fleet while the probe
# (which listed ONLY the legacy pair) did not. Kept as-is, and the CI gate now
# holds every sibling-resolver list to this same shape.
_PIN_DIGEST_TOOL=""
for _c in "$SELF_DIR/ghl-mcp-pin-digest.sh" \
          "$HOME/.openclaw/scripts/ghl-mcp-pin-digest.sh" \
          "$HOME/.openclaw/skills/scripts/ghl-mcp-pin-digest.sh" \
          "/data/.openclaw/scripts/ghl-mcp-pin-digest.sh" \
          "/data/.openclaw/skills/scripts/ghl-mcp-pin-digest.sh"; do
  [ -f "$_c" ] && { _PIN_DIGEST_TOOL="$_c"; break; }
done

if [ "$GHL_MCP_PIN_VETTED_VERDICT" != "CLEAN" ]; then
  report "PIN_UNVETTED" \
    "(GHL_MCP_PIN_VETTED_VERDICT='${GHL_MCP_PIN_VETTED_VERDICT:-<unset>}' in $_PIN_FILE — only CLEAN may be built. Re-vet the pinned commit and record the verdict before any box builds it.)"
  exit 0
fi

if [ -n "$GHL_MCP_PIN_VETTED_DIGEST" ]; then
  if [ -z "$_PIN_DIGEST_TOOL" ]; then
    report "PIN_UNVETTED" \
      "(the pin declares GHL_MCP_PIN_VETTED_DIGEST but scripts/ghl-mcp-pin-digest.sh was not delivered to this box, so the digest CANNOT be verified — refusing rather than trusting it unchecked. Re-run update-skills.sh.)"
    exit 0
  fi
  if ! bash "$_PIN_DIGEST_TOOL" verify "$_PIN_FILE" >/dev/null 2>&1; then
    report "PIN_UNVETTED" \
      "(the vetting digest in $_PIN_FILE does not recompute — the pin was edited without re-running scripts/ghl-mcp-vet-pin.sh. Refusing to build/start. Run: bash $_PIN_DIGEST_TOOL verify $_PIN_FILE)"
    exit 0
  fi
  log "vetting digest verified (verdict=CLEAN, digest recomputes)"
else
  log "vetting digest ABSENT — enforcing the explicit CLEAN verdict (transitional until scripts/ghl-mcp-vet-pin.sh ships the digest)"
fi

# ── R9: an override is an escape hatch, not a bypass ─────────────────────────
# GHL_MCP_PIN_OVERRIDE used to accept ANY 40-hex string with zero vetting —
# and it is the primary path a fleet roll would use to change a pin, which made
# the primary path the ungated one. It now requires a matching vetting digest
# computed over the OVERRIDE's own tuple, using THE SAME canonical algorithm as
# the pin file — ghl-mcp-pin-v2, which BINDS THE REPOSITORY URL:
#
#   printf '%s\n' ghl-mcp-pin-v2 \
#     "$GHL_MCP_PIN_OVERRIDE" \
#     "$GHL_MCP_PIN_OVERRIDE_VERDICT" \
#     "$GHL_MCP_PIN_OVERRIDE_VETTED_ON" \
#     "$GHL_MCP_PIN_OVERRIDE_VETTED_BY" \
#     "$GHL_MCP_PIN_OVERRIDE_DEPS_LOCK_SHA256" \
#     "$GHL_MCP_REPO_URL" | shasum -a 256 | cut -d' ' -f1
#
# …and that value must be passed as GHL_MCP_PIN_OVERRIDE_VETTED_DIGEST. The
# seventh field is the EFFECTIVE repo URL from the pin file — the source this
# box would actually clone from. It is not separately settable: an override
# changes WHICH COMMIT is built, never WHERE it is fetched from.
#
# THE ALGORITHM IS NOT REIMPLEMENTED HERE. This block materialises the override
# as a pin-shaped record and hands it to scripts/ghl-mcp-pin-digest.sh, the one
# canonical implementation. A second inline copy is precisely how this path
# stayed on v1 — with the repository URL UNBOUND — after the pin file moved to
# v2, which would have let a mirror swap ride in through the primary fleet-roll
# path while every digest still checked out.
if [ -n "${GHL_MCP_PIN_OVERRIDE:-}" ]; then
  _OV_VERDICT="${GHL_MCP_PIN_OVERRIDE_VERDICT:-}"
  _OV_DIGEST="${GHL_MCP_PIN_OVERRIDE_VETTED_DIGEST:-}"
  _OV_REPO="$GHL_MCP_REPO_URL"
  if [ -z "$_OV_DIGEST" ]; then
    report "PIN_UNVETTED" \
      "(GHL_MCP_PIN_OVERRIDE was supplied without GHL_MCP_PIN_OVERRIDE_VETTED_DIGEST — an override is an escape hatch for a VETTED commit, never a way to skip vetting. Vet the candidate, then pass the digest.)"
    exit 0
  fi
  if [ "$_OV_VERDICT" != "CLEAN" ]; then
    report "PIN_UNVETTED" \
      "(GHL_MCP_PIN_OVERRIDE_VERDICT='${_OV_VERDICT:-<unset>}' — only CLEAN may be built.)"
    exit 0
  fi
  if [ -z "$_PIN_DIGEST_TOOL" ]; then
    report "PIN_UNVETTED" \
      "(GHL_MCP_PIN_OVERRIDE was supplied but scripts/ghl-mcp-pin-digest.sh was not delivered to this box, so the override digest CANNOT be verified — refusing rather than trusting it unchecked. Re-run update-skills.sh.)"
    exit 0
  fi
  # A double quote in any bound field would break the pin-shaped record format
  # and could let two different tuples parse to the same value. Refuse instead.
  case "${GHL_MCP_PIN_OVERRIDE}${_OV_VERDICT}${GHL_MCP_PIN_OVERRIDE_VETTED_ON:-}${GHL_MCP_PIN_OVERRIDE_VETTED_BY:-}${GHL_MCP_PIN_OVERRIDE_DEPS_LOCK_SHA256:-}${_OV_REPO}" in
    *'"'*)
      report "PIN_UNVETTED" \
        "(a GHL_MCP_PIN_OVERRIDE_* field contains a double quote — refusing rather than hashing an ambiguous record.)"
      exit 0 ;;
  esac
  _OV_TMP="$(mktemp "${TMPDIR:-/tmp}/ghl-mcp-override.XXXXXX" 2>/dev/null)"
  if [ -z "$_OV_TMP" ]; then
    report "PIN_UNVETTED" "(could not create a temp file to verify the override digest — refusing.)"
    exit 0
  fi
  {
    printf 'GHL_MCP_VETTED_COMMIT="%s"\n'      "$GHL_MCP_PIN_OVERRIDE"
    printf 'GHL_MCP_PIN_VETTED_VERDICT="%s"\n' "$_OV_VERDICT"
    printf 'GHL_MCP_PIN_VETTED_ON="%s"\n'      "${GHL_MCP_PIN_OVERRIDE_VETTED_ON:-}"
    printf 'GHL_MCP_PIN_VETTED_BY="%s"\n'      "${GHL_MCP_PIN_OVERRIDE_VETTED_BY:-}"
    printf 'GHL_MCP_DEPS_LOCK_SHA256="%s"\n'   "${GHL_MCP_PIN_OVERRIDE_DEPS_LOCK_SHA256:-}"
    printf 'GHL_MCP_REPO_URL="%s"\n'           "$_OV_REPO"
  } > "$_OV_TMP"
  _OV_COMPUTED="$(bash "$_PIN_DIGEST_TOOL" compute "$_OV_TMP" 2>/dev/null)"
  rm -f "$_OV_TMP"
  if [ -z "$_OV_COMPUTED" ] || [ "$_OV_COMPUTED" != "$_OV_DIGEST" ]; then
    report "PIN_UNVETTED" \
      "(GHL_MCP_PIN_OVERRIDE_VETTED_DIGEST does not match the override tuple — refusing. Recompute it over ghl-mcp-pin-v2|commit|verdict|on|by|deps_lock_sha256|repo_url, where repo_url is this box's GHL_MCP_REPO_URL.)"
    exit 0
  fi
  log "pin override accepted (digest verified, repo URL bound) — building ${GHL_MCP_PIN_OVERRIDE:0:12} instead of the pin file's commit"
  GHL_MCP_VETTED_COMMIT="$GHL_MCP_PIN_OVERRIDE"
fi

[ -n "${GHL_TOOL_PROFILE:-}" ] && GHL_MCP_TOOL_PROFILE="$GHL_TOOL_PROFILE"

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

# (the STATUS reporter is declared above the pin resolution — R9's refusals
#  report through it before anything else runs.)

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

# >>> GHL-MCP-ROOT-OWNERSHIP-GUARD-BEGIN
#     (extracted verbatim by tests/unit/ghl-mcp-root-ownership-guard.test.sh)
# ── 0. Root/ownership mismatch guard (P0, proven live 2026-08-04) ────────────
# DEFECT (worst of the three found tonight): every git command below used to
# carry a blanket `2>/dev/null`. When this script runs as ROOT against an
# EXISTING $MCP_DIR checkout owned by a different uid — the fleet-standard VPS
# shape, where the box user is uid 1000/node — every single git command in
# this function hits git's "detected dubious ownership in repository at ..."
# fatal, and that `2>/dev/null` swallowed it with NO WARN, NO FATAL, NO trace.
# The MIRROR MIGRATION repoint below then silently no-op'd (an empty
# $_origin_url reads as "no origin to repoint"), the pin-verify fetch/cat-file
# calls below it failed for the identical swallowed reason, and the operator
# saw only the downstream "PIN_MISMATCH — cannot check out vetted commit" and
# reasonably blamed the pin gate, which was innocent. This is the SAME disease
# as the root-cron bug fixed earlier the same night: a privilege mismatch that
# a swallowed stderr turns into an unrelated-looking symptom two layers away.
#
# FIX: detect the mismatch EXPLICITLY, before any git command touches an
# existing checkout, rather than trying to pattern-match git's (locale-
# dependent) stderr text. FAIL LOUD through the same report()/STATUS contract
# every other refusal in this script uses, naming the exact remedy — the
# convention already documented at scripts/activate-loop-protection.sh:118:
# run this script as the box user, never as root (`docker exec -u node <ctr>
# bash ...` on VPS/Docker).
_ghl_owner_uid() {  # <path> -> numeric uid, or empty if it cannot be read
  local p="$1" u=""
  command -v stat >/dev/null 2>&1 || { printf ''; return 0; }
  # GNU stat: -c %u   BSD/macOS stat: -f %u — try both; first one that answers wins.
  u="$(stat -c %u "$p" 2>/dev/null || true)"
  [ -n "$u" ] || u="$(stat -f %u "$p" 2>/dev/null || true)"
  printf '%s' "$u"
}

assert_ownership_matches_runtime_user() {
  [ -d "$MCP_DIR/.git" ] || return 0              # nothing checked out yet — a fresh clone as root is not this failure mode
  [ "$(id -u 2>/dev/null || echo '')" = "0" ] || return 0   # not root — this disease cannot occur
  [ "${GHL_MCP_ALLOW_ROOT:-}" = "1" ] && return 0  # explicit escape hatch (tests / a deliberate root-owned box)
  local _owner_uid; _owner_uid="$(_ghl_owner_uid "$MCP_DIR")"
  [ -n "$_owner_uid" ] || return 0                 # cannot determine — do not block on a guess
  [ "$_owner_uid" = "0" ] && return 0               # already root-owned — no ownership mismatch, git will not refuse

  log "############################################################"
  log "## FATAL: running as root (uid 0) against $MCP_DIR, which is owned by uid $_owner_uid."
  log "## Every git command below would hit git's dubious-ownership refusal, and"
  log "## this script used to swallow that with 2>/dev/null -- surfacing only as an"
  log "## unrelated downstream PIN_MISMATCH. Refusing to proceed rather than repeat that."
  log "## REMEDY (VPS/Docker): run this script as the box user, not root:"
  log "##   docker exec -u node <ctr> bash $SELF_DIR/$(basename "${BASH_SOURCE[0]:-$0}")"
  log "## (the sanctioned convention documented at scripts/activate-loop-protection.sh:118)."
  log "## Mac: this script should never be invoked with sudo."
  log "############################################################"
  report "ROOT_OWNERSHIP_MISMATCH" \
    "(running as root (uid 0) against $MCP_DIR, owned by uid $_owner_uid -- every git command would be silently refused by git's dubious-ownership guard. Re-run as the box user: docker exec -u node <ctr> bash <this script> on VPS/Docker (see scripts/activate-loop-protection.sh:118); never with sudo on Mac.)"
  return 1
}
# <<< GHL-MCP-ROOT-OWNERSHIP-GUARD-END

# >>> GHL-MCP-ENV-CREDENTIAL-GUARD-BEGIN
#     (extracted verbatim by tests/unit/ghl-mcp-env-credential-guard.test.sh)
# ── 3. The server .env — NEVER clobber a WORKING credential pairing ──────────
#
# B1 (P0, proven live on the operator box 2026-08-03). This function used to
# rewrite $MCP_DIR/.env unconditionally, taking GHL_LOCATION_ID straight from
# GOHIGHLEVEL_LOCATION_ID with NO BACKUP and NO VALIDATION. On a box where the
# configured location and the MCP token's scope disagree, the result is fatal
# AND unrecoverable. Measured, same token, same box:
#
#   .env value already on disk      -> HTTP 200
#   value the installer wrote over it -> HTTP 403
#                                        "The token does not have access to this location."
#
# main.js calls `await ghlClient.testConnection()` at boot and process.exit(1)s
# on failure (src/main.ts:69 + 222-225), so a wrong location does not degrade
# quietly — the server goes DOWN and STAYS down. Crash-only supervision then
# does exactly the right thing and keeps it down. And because this function kept
# no copy of what it replaced, the working .env had to be recovered from a Time
# Machine snapshot. That is the whole defect: a destructive write, of an
# unvalidated value, over a proven-good one, with no way back.
#
# THE RULE NOW — a credential pairing PROVEN to work is never replaced by one
# that is not proven to work:
#   * a byte-identical rewrite is a NO-OP: no write, no backup, no churn
#   * before ANY change, .env is backed up timestamped at 600, the copy is READ
#     BACK and compared, and a backup that cannot be made or verified REFUSES
#     the rewrite outright (backups pruned to the newest 5)
#   * when the candidate location differs from the one already on disk, BOTH are
#     validated with a read-only GET against the live API, using the token that
#     will actually be written, and the one that WORKS wins
#   * an EMPTY candidate never overwrites a non-empty existing value
#   * "cannot tell" (curl absent, network down, 5xx, 000) KEEPS the existing
#     value. An unproven candidate never wins by default.
#
# The decision is made ONCE per run and reassigns the global GHL_LOC, so every
# downstream launch surface (the pm2 ecosystem's env block, the systemd unit's
# EnvironmentFile) agrees with the .env rather than re-introducing the rejected
# value one layer up.

# _ghl_location_http_code <token> <location_id> — read-only probe of the
# location record. Prints ONLY the HTTP status code (000 when the call could not
# be made at all). NEVER prints the token, the location, or the response body.
_ghl_location_http_code() {
  local _tok="${1:-}" _loc="${2:-}"
  [ -n "$_tok" ] && [ -n "$_loc" ] || { printf '000'; return 0; }
  command -v curl >/dev/null 2>&1 || { printf '000'; return 0; }
  curl -s -o /dev/null -w '%{http_code}' -m 10 \
    "https://services.leadconnectorhq.com/locations/${_loc}" \
    -H "Authorization: Bearer ${_tok}" \
    -H "Version: 2021-07-28" 2>/dev/null || printf '000'
}

# _ghl_location_verdict <http_code> -> ok | rejected | unknown
# 404 counts as REJECTED: a location this token cannot see is a broken pairing,
# not an ambiguous one. Everything else (000 offline, 5xx, 429) is UNKNOWN and
# must never be treated as either a pass or a fail.
_ghl_location_verdict() {
  case "${1:-}" in
    200|201)     printf 'ok' ;;
    401|403|404) printf 'rejected' ;;
    *)           printf 'unknown' ;;
  esac
}

# Last 4 characters only — enough to tell two ids apart in a log, without
# printing a full credential-adjacent identifier into a shared log file.
_ghl_mask() { printf '…%s' "$(printf '%s' "${1:-}" | tail -c 4)"; }

_env_file_value() {  # <file> <KEY>
  local f="${1:-}" k="${2:-}"
  [ -f "$f" ] || return 0
  sed -n "s/^[[:space:]]*${k}=//p" "$f" 2>/dev/null | tail -1 | tr -d '"' | tr -d "'"
}

# Timestamped, verified, pruned backup. Returns non-zero when a backup could NOT
# be produced — the caller must then leave the file alone. "No backup" is exactly
# the condition that made the live incident unrecoverable, so it is fatal to the
# write, never a warning we proceed past.
_backup_server_env() {
  local f="${1:-}" ts bak n=0
  [ -f "$f" ] || return 0     # nothing to protect yet
  ts="$(date -u +%Y%m%dT%H%M%SZ 2>/dev/null || echo unknown)"
  bak="${f}.bak-${ts}"
  if ! ( umask 077; cp -p "$f" "$bak" ) 2>/dev/null; then
    log "REFUSING to rewrite $f — could not write the backup $bak"
    return 1
  fi
  chmod 600 "$bak" 2>/dev/null || true
  if ! cmp -s "$f" "$bak" 2>/dev/null; then
    log "REFUSING to rewrite $f — the backup $bak does not match what is on disk"
    rm -f "$bak" 2>/dev/null || true
    return 1
  fi
  log "server .env backed up (verified, 600) -> $bak"
  while IFS= read -r _old; do
    [ -n "$_old" ] || continue
    n=$((n+1))
    [ "$n" -le 5 ] && continue
    rm -f "$_old" 2>/dev/null || true
  done <<EOF
$(ls -1 "${f}".bak-* 2>/dev/null | LC_ALL=C sort -r)
EOF
  return 0
}

# Decide the location id ONCE per run and publish it as the global GHL_LOC.
_GHL_LOC_RESOLVED=0
resolve_location_id() {
  [ "$_GHL_LOC_RESOLVED" = "1" ] && return 0
  _GHL_LOC_RESOLVED=1
  local ENVF="$MCP_DIR/.env" _existing="" _cand_code _exist_code _cand_v _exist_v
  _existing="$(_env_file_value "$ENVF" GHL_LOCATION_ID)"

  if [ -z "${GHL_LOC:-}" ]; then
    if [ -n "$_existing" ]; then
      GHL_LOC="$_existing"
      log "location id: no GOHIGHLEVEL_LOCATION_ID/GHL_LOCATION_ID resolvable here — keeping the value already on disk $(_ghl_mask "$_existing") (an EMPTY candidate never overwrites a working one)"
    fi
    return 0
  fi
  if [ -z "$_existing" ] || [ "$_existing" = "$GHL_LOC" ]; then
    return 0    # nothing on disk yet, or no change at all — nothing to prove
  fi

  # A REAL disagreement — the fatal case. Prove both before choosing either.
  _cand_code="$(_ghl_location_http_code "$GHL_TOKEN" "$GHL_LOC")"
  _exist_code="$(_ghl_location_http_code "$GHL_TOKEN" "$_existing")"
  _cand_v="$(_ghl_location_verdict "$_cand_code")"
  _exist_v="$(_ghl_location_verdict "$_exist_code")"
  log "location id DISAGREEMENT: on-disk $(_ghl_mask "$_existing") -> HTTP ${_exist_code} (${_exist_v}); configured $(_ghl_mask "$GHL_LOC") -> HTTP ${_cand_code} (${_cand_v})"

  if [ "$_cand_v" = "ok" ]; then
    log "location id: configured value VALIDATED against this token (HTTP ${_cand_code}) — adopting it"
    return 0
  fi
  if [ "$_exist_v" = "ok" ]; then
    log "############################################################"
    log "## GHL_LOCATION_ID NOT OVERWRITTEN — the configured value would TAKE THIS SERVER DOWN."
    log "##   configured $(_ghl_mask "$GHL_LOC") -> HTTP ${_cand_code} (rejected by this token)"
    log "##   on disk    $(_ghl_mask "$_existing") -> HTTP ${_exist_code} (works)"
    log "## main.js testConnection()s at boot and exit(1)s on failure, so writing the"
    log "## rejected value is a hard outage, not a degradation. KEEPING the working pairing."
    log "## ACTION: fix GOHIGHLEVEL_LOCATION_ID in this box's secrets/openclaw.json to"
    log "## match the MCP token's scope, or rotate the token to one scoped to that location."
    log "############################################################"
    GHL_LOC="$_existing"
    return 0
  fi
  GHL_LOC="$_existing"
  log "location id: NEITHER value could be proven (configured HTTP ${_cand_code}, on-disk HTTP ${_exist_code}) — keeping the on-disk value. An unproven candidate never wins by default."
  return 0
}

write_server_env() {
  [ -n "$GHL_TOKEN" ] || return 0
  resolve_location_id
  local ENVF="$MCP_DIR/.env" _new
  _new="$(cat <<EOF
GHL_API_KEY=${GHL_TOKEN}
GHL_BASE_URL=https://services.leadconnectorhq.com
GHL_LOCATION_ID=${GHL_LOC}
# main.js reads PORT before MCP_SERVER_PORT — pin BOTH so it can never bind random.
PORT=${GHL_MCP_PORT}
MCP_SERVER_PORT=${GHL_MCP_PORT}
# D2: upstream default is the FULL 858-tool surface. Pin the profile explicitly.
GHL_TOOL_PROFILE=${GHL_MCP_TOOL_PROFILE}
# D6: consumed by .ghl-mcp-bind-guard.cjs (NOT by main.js — upstream hardcodes
# its 0.0.0.0 bind). Loopback only; the guard coerces anything else back.
GHL_MCP_BIND_HOST=${GHL_MCP_BIND_HOST}
NODE_ENV=production
EOF
)"
  if [ -f "$ENVF" ] && [ "$(cat "$ENVF" 2>/dev/null)" = "$_new" ]; then
    log "server .env already byte-identical — no write, no backup (idempotent no-op)"
    return 0
  fi
  _backup_server_env "$ENVF" || return 1
  ( umask 077; printf '%s\n' "$_new" > "$ENVF" ) || {
    log "FATAL: could not write $ENVF"; return 1; }
  chmod 600 "$ENVF" 2>/dev/null || true
  log "server .env written (GHL_LOCATION_ID=$(_ghl_mask "$GHL_LOC"))"
  return 0
}
# <<< GHL-MCP-ENV-CREDENTIAL-GUARD-END

# ── 3b. D6: the BIND GUARD — force the listener onto loopback ────────────────
# The pinned upstream binds 0.0.0.0 from a hardcoded literal (src/main.ts:
# `app.listen(port, '0.0.0.0', …)`), so no environment variable can move it.
# This CommonJS preload is loaded via NODE_OPTIONS=--require by the launcher and
# rewrites the host argument of net.Server.prototype.listen — which every
# express/http listen path funnels through — before the real bind happens.
#
# FAIL-OPEN BY CONSTRUCTION: every step is wrapped so a guard that cannot load,
# or an argument shape it does not recognise, falls through to the original
# listen untouched. A security guard that bricks the server on 38 client boxes
# would be a worse outage than the one it prevents.
BIND_GUARD="$MCP_DIR/.ghl-mcp-bind-guard.cjs"
write_bind_guard() {
  cat > "$BIND_GUARD" <<'GUARDEOF'
'use strict';
// .ghl-mcp-bind-guard.cjs — generated by ghl-mcp-autostart.sh. DO NOT EDIT BY HAND.
//
// Forces the GHL community MCP to listen on loopback. Upstream hardcodes
// `app.listen(port, '0.0.0.0')`, exposing a CRM-credentialed, UNAUTHENTICATED
// endpoint to every host on the LAN. Loaded with `node --require`.
//
// Escape hatch: setting GHL_MCP_ALLOW_PUBLIC_BIND to 1 honours GHL_MCP_BIND_HOST
// verbatim. The repo's own launch surfaces never set it and the QC gate forbids
// them to, so it stays a deliberate per-box operator decision.
try {
  const net = require('net');
  const ALLOW_PUBLIC = process.env.GHL_MCP_ALLOW_PUBLIC_BIND === '1';
  let HOST = process.env.GHL_MCP_BIND_HOST || '127.0.0.1';
  const isLoopback = (h) =>
    typeof h === 'string' &&
    (h === 'localhost' || h === '::1' || h === '::ffff:127.0.0.1' || /^127\./.test(h));
  // Fail CLOSED on the host VALUE (a non-loopback value is coerced back to
  // loopback) while failing OPEN on any unexpected argument SHAPE below.
  if (!ALLOW_PUBLIC && !isLoopback(HOST)) HOST = '127.0.0.1';

  const origListen = net.Server.prototype.listen;
  net.Server.prototype.listen = function patchedListen(...args) {
    try {
      const a0 = args[0];
      if (a0 !== null && typeof a0 === 'object' && !Array.isArray(a0)) {
        // listen(options[, cb]) — but never touch IPC (path) or fd handles.
        if (a0.port !== undefined && a0.path === undefined && a0.fd === undefined) {
          args[0] = Object.assign({}, a0, { host: HOST });
        }
      } else if (typeof a0 === 'number' || (typeof a0 === 'string' && /^[0-9]+$/.test(a0))) {
        // listen(port[, host][, backlog][, cb]) — replace an explicit host,
        // otherwise splice ours in directly after the port.
        if (typeof args[1] === 'string') args[1] = HOST;
        else args.splice(1, 0, HOST);
      }
      // Anything else (unix socket path, handle, unknown shape) is left alone.
    } catch (e) { /* never block a start */ }
    return origListen.apply(this, args);
  };
} catch (e) { /* fail-open: a broken guard must never stop the server */ }
GUARDEOF
  chmod 644 "$BIND_GUARD" 2>/dev/null || true
}

# ── Managed cron lines: sentinel-tagged, REPLACED when they drift ────────────
# F13: the old shape was `crontab -l | grep -Fq "ghl-mcp-probe.sh" && skip`. When
# the delivered script path changed (…/skills/scripts → …/scripts, or a /data
# layout change) the substring STILL matched the stale line, so the new line was
# never added and the old one survived pointing at a path that no longer exists —
# a silently dead 15-minute probe and a silently dead reboot-resurrect hook, with
# nothing anywhere reporting a problem. Match on a SENTINEL COMMENT that only we
# write, and REPLACE the line whenever it differs from the one we intend.
CRON_TAG_PROBE="# managed:ghl-mcp-probe"
upsert_cron_line() {
  local tag="$1" line="$2" current desired
  command -v crontab >/dev/null 2>&1 || return 1
  current="$(crontab -l 2>/dev/null || true)"
  # Already exactly right -> no write at all (keeps this idempotent + quiet).
  case "$current" in
    *"$line"*) return 1 ;;
  esac
  # Drop every previously-managed line carrying this tag, then append the new one.
  desired="$(printf '%s\n' "$current" | grep -vF "$tag" 2>/dev/null || true)"
  printf '%s\n%s\n' "$desired" "$line" | grep -v '^$' | crontab - >/dev/null 2>&1 || return 1
  return 0
}

# The REAL test: does a JSON-RPC request get an ANSWER? /health is served by
# express before the MCP transport is wired, so a stale/deaf dist still returns
# {"status":"healthy"} while every agent init hangs the full 30s (D1/D5).
# B3 (DEAD ON ARRIVAL FLEET-WIDE): this resolver listed
# $HOME/.openclaw/skills/scripts/ and /data/.openclaw/skills/scripts/ — an extra
# `skills/` segment that NOTHING delivers to. update-skills.sh delivers the
# canonical scripts/ tree to $OC_ROOT/scripts (deliver_canonical_scripts_tree ->
# _OC_SCRIPTS_DEST), so neither candidate could ever match on a real box. The
# only candidate that ever hit was $SELF_DIR — and on the FLEET path $SELF_DIR is
# the temp extract dir, which the updater `rm -rf`s. Net effect: PROBE resolved
# empty on every rolled box, so install_periodic_probe() took its
# "not co-located — periodic liveness probe NOT installed" branch and the
# 15-minute liveness probe was never installed anywhere. It passed in operator-box testing
# only because that run used a persistent checkout.
#
# The DELIVERED path is now present, on both platforms, ahead of the legacy one.
# $SELF_DIR stays first (it is how a developer checkout and CI resolve). The
# `skills/scripts` pair is KEPT, last, as a legacy fallback: some long-lived
# boxes were provisioned when install.sh copied the whole repo under skills/, and
# dropping it could strand one of them. It is no longer the ONLY option, which is
# what made this dead on arrival.
# scripts/qc-assert-pin-delivery-paths.sh now fails CI if any resolver here omits
# the delivered path.
PROBE="$(
  for c in "$SELF_DIR/ghl-mcp-probe.sh" \
           "$HOME/.openclaw/scripts/ghl-mcp-probe.sh" \
           "/data/.openclaw/scripts/ghl-mcp-probe.sh" \
           "$HOME/.openclaw/skills/scripts/ghl-mcp-probe.sh" \
           "/data/.openclaw/skills/scripts/ghl-mcp-probe.sh"; do
    [ -f "$c" ] && { printf '%s' "$c"; break; }
  done
)"

# gw_up: rc 0 ONLY when the OpenClaw gateway answers GET /healthz with 200.
# NEVER uses the openclaw CLI. On 2026.10.1 a CLI call while the gateway is down
# takes the offline sqlite-maintenance lock and the gateway dies at bootstrap
# (Beverly Grandison crash loop, RestartCount 13). Every CLI call in this script
# is gated on it. Port = gateway.port from openclaw.json (default 18789).
gw_up() {
  command -v curl >/dev/null 2>&1 || return 1
  local _cfg _port _code _s=http _k=""
  _cfg="${OPENCLAW_CONFIG:-${OC_JSON:-$HOME/.openclaw/openclaw.json}}"
  _port="$(OC_CFG="$_cfg" python3 -c 'import json,os
try:
    print(int((json.load(open(os.environ["OC_CFG"])).get("gateway") or {}).get("port") or 18789))
except Exception:
    print(18789)' 2>/dev/null)"
  if [ "$(_gw_tls_flag "$_cfg")" = "1" ]; then _s=https; _k="-k"; fi
  # shellcheck disable=SC2086  # _k is empty or the single word -k (loopback only)
  _code="$(curl -s $_k -o /dev/null -w '%{http_code}' --max-time 3 "$_s://127.0.0.1:${_port:-18789}/healthz" 2>/dev/null || true)"
  [ "$_code" = "200" ]
}

# ── 7. Periodic liveness probe (D5) — every 15 minutes, self-healing once ────
install_periodic_probe() {
  [ -n "${PROBE:-}" ] || { log "ghl-mcp-probe.sh not co-located — periodic liveness probe NOT installed"; return 0; }
  # v25.1.10 — operator off-switch. A marker file (or GHL_MCP_PROBE_DISABLED=1)
  # means the operator turned the probe off on purpose; a fleet roll must not
  # quietly re-arm it. Remove the schedule this installer owns and install
  # nothing. The probe script honours the same switch, so any schedule this
  # function cannot reach (the openclaw cron store) stays inert regardless.
  local _dis="" _m=""
  case "${GHL_MCP_PROBE_DISABLED:-}" in
    1) _dis="GHL_MCP_PROBE_DISABLED=1" ;;
    0) : ;;   # explicit ON: ignore marker files
    *) for _m in "${HOME:-}/.openclaw/.ghl-mcp-probe-disabled" "/data/.openclaw/.ghl-mcp-probe-disabled"; do
         case "$_m" in /.openclaw/*) continue ;; esac
         [ -f "$_m" ] && { _dis="$_m"; break; }
       done ;;
  esac
  if [ -n "$_dis" ]; then
    if [ "$(uname -s)" = "Darwin" ]; then
      local _PPLIST="$HOME/Library/LaunchAgents/com.clawd.ghl-mcp-probe.plist"
      if [ -f "$_PPLIST" ]; then launchctl bootout "gui/$(id -u)" "$_PPLIST" >/dev/null 2>&1 || true; fi
    elif command -v crontab >/dev/null 2>&1; then
      local _cur=""
      _cur="$(crontab -l 2>/dev/null || true)"
      case "$_cur" in
        *"$CRON_TAG_PROBE"*) printf '%s\n' "$_cur" | grep -vF "$CRON_TAG_PROBE" | grep -v '^$' | crontab - >/dev/null 2>&1 || true ;;
      esac
    fi
    log "periodic liveness probe DISABLED by operator off-switch ($_dis) — schedule removed, nothing installed; delete the marker to re-enable"
    return 0
  fi
  # launchd exists ONLY on Darwin. A HOME-layout Linux container must never be
  # handed a plist — nothing will ever run it (the silent failure this class
  # of box hit live). Cron covers linux-home.
  if [ "$PLATFORM" = "mac" ] && [ "$(uname -s)" = "Darwin" ]; then
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
        <!-- R12: pass the log dir EXPLICITLY. The probe used to compute this
             itself and ignore GHL_MCP_LOG_DIR, so its log location was
             coincidental rather than configured — and the unit test wrote real-
             looking verdicts straight into the production probe.log. -->
        <key>GHL_MCP_LOG_DIR</key><string>${LOG_DIR}</string>
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
    if command -v crontab >/dev/null 2>&1; then
      local LINE="*/15 * * * * mkdir -p ${LOG_DIR} && GHL_MCP_LOG_DIR=${LOG_DIR} /bin/bash ${PROBE} --once --heal >>${LOG_DIR}/probe.log 2>&1 ${CRON_TAG_PROBE}"
      upsert_cron_line "$CRON_TAG_PROBE" "$LINE" \
        && log "periodic liveness probe cron installed/refreshed (*/15)" \
        && return 0
    fi
    # The CLI fallbacks below are the only CLI use here: never while the gateway is down.
    gw_up || { log "gateway not up (no /healthz 200) — openclaw CLI not called, periodic probe registration deferred to the next run"; return 0; }
    # HOME-layout containers may have no crontab at all (oc-fixture-client-i).
    # Fall back to the openclaw cron STORE — the gateway runs it, no OS cron
    # needed. A silent return here would leave the probe uninstalled and the
    # crash-only supervisor unwatched.
    _OC_BIN="$(command -v openclaw || true)"
    [ -n "$_OC_BIN" ] || { log "no crontab AND no openclaw CLI — periodic probe NOT installed"; return 0; }
    # D10: a failed/non-JSON `cron list` (gateway down at container boot) is UNKNOWN, not
    # "absent" - adding on it registered ghl-mcp-probe x4. Add only after a good list.
    _OC_LIST="$("$_OC_BIN" cron list --json 2>/dev/null)" || _OC_LIST=""
    case "$(printf '%s' "$_OC_LIST" | tr -d '[:space:]' | cut -c1)" in '['|'{') ;; *)
      log "openclaw cron list unreadable (gateway down?) - ghl-mcp-probe presence unknown, NOT registering; next run retries"
      return 0 ;;
    esac
    if printf '%s' "$_OC_LIST" | grep -q '"name": *"ghl-mcp-probe"'; then
      log "periodic liveness probe already registered in the openclaw cron store"
      return 0
    fi
    if "$_OC_BIN" cron add --name "ghl-mcp-probe" --cron "*/15 * * * *" \
         --command "mkdir -p ${LOG_DIR} && GHL_MCP_LOG_DIR=${LOG_DIR} /bin/bash ${PROBE} --once --heal >>${LOG_DIR}/probe.log 2>&1" >&2; then
      log "periodic liveness probe registered in the openclaw cron store (*/15)"
    else
      log "openclaw cron add FAILED for ghl-mcp-probe — periodic probe NOT installed"
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
# >>> OC-MCP-UNSET-VERB-BEGIN
#     (extracted verbatim by tests/unit/ghl-mcp-unset-verb.test.sh)
# B2 (proven live on OpenClaw 2026.7.1-2): `openclaw mcp remove <name>` IS NOT A
# COMMAND. It exits 1 with "Too many arguments for this command." The verb is
# `unset`. Every de-registration call site in this repo used `remove`, and every
# one of them was swallowed by `|| true` — so Tier 2 was NEVER de-registered on
# ANY box, and check 10 of ghl-mcp-assert-runtime.sh ("ghl-community-mcp ABSENT
# from mcp.servers") could never pass anywhere. That was the last remaining FATAL
# on the pilot box.
#
# oc_mcp_unset tries `unset` first and falls back to `remove` for any older CLI
# that genuinely used it, then RETURNS THE OUTCOME. Callers must not `|| true`
# it: a swallowed failure is precisely how this stayed invisible for so long.
#   0 = the CLI accepted one of the verbs
#   1 = neither verb was accepted (or openclaw is absent)
oc_mcp_unset() {
  local _name="${1:-}"
  [ -n "$_name" ] || return 1
  command -v openclaw >/dev/null 2>&1 || return 1
  openclaw mcp unset "$_name" >/dev/null 2>&1 && return 0
  openclaw mcp remove "$_name" >/dev/null 2>&1 && return 0
  return 1
}

# Which verb does the INSTALLED CLI actually document? Reported (never guessed)
# so an operator reading the log can see whether the repo and the runtime agree.
oc_mcp_unset_verb_supported() {
  command -v openclaw >/dev/null 2>&1 || { printf 'no-cli'; return 0; }
  local _h
  _h="$(openclaw mcp --help 2>&1 || true)"
  case "$_h" in
    *' unset'*|*'unset '*) printf 'unset' ;;
    *' remove'*|*'remove '*) printf 'remove' ;;
    *) printf 'unknown' ;;
  esac
}

# deregister_tier2() is GONE (GHL002): it was unreachable — nothing has called
# it since START was retired — and it still held a live
# `openclaw config set env.vars.GHL_COMMUNITY_MCP_URL` write, a config mutation
# behind a service that no longer exists. Zero callers tree-wide was confirmed
# before the deletion. The two unit tests that EXTRACTED it
# (tests/unit/ghl-mcp-gateway-guard.test.sh, tests/unit/ghl-mcp-autostart-
# idempotent-write.test.sh) assert a function that no longer ships and must be
# re-pointed at whatever still does that job.
# The oc_mcp_unset / oc_mcp_unset_verb_supported helpers above stay: extracted
# verbatim by tests/unit/ghl-mcp-unset-verb.test.sh, and they are the
# correct-verb reference for every other de-registration site in this repo.
# <<< OC-MCP-UNSET-VERB-END

# ── Main flow ────────────────────────────────────────────────────────────────

# GU-019: START IS RETIRED. This point is reached only when the legacy pin gate
# passed (a box with no pin already refused above with PIN_UNVERIFIED). Either
# way NOTHING is built, cloned or started — the community MCP is retired and the
# only supported action is the retirement transaction.
report "START_REFUSED_RETIRED" "(the community GHL MCP is RETIRED: this script no longer starts, builds, clones or supervises it, and it will not restart itself. Nothing was started. To finish retiring an existing install run: bash $0 --retire ; to inspect: bash $0 --status)"
exit 0
