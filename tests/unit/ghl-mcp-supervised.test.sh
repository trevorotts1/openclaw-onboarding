#!/usr/bin/env bash
# tests/unit/ghl-mcp-supervised.test.sh — v21.5.0
#
# Verifies the GHL MCP supervision + install invariant gate
# (qc-assert-ghl-mcp-supervised.sh). The gate is a STATIC check of the SHIPPED
# autostart scripts; this test exercises it in a sandbox of synthetic scripts.
#
# v12.24.0 cases (the fleet incident: 12/19 boxes down/unsupervised):
#   (A) The SHIPPED repo scripts PASS (exit 0) — supervised, reboot-surviving,
#       PORT pinned, no bare nohup.
#   (B) A regressed script (bare `nohup node` + only MCP_SERVER_PORT, no pm2/
#       launchd/reboot hook) FAILS (exit 1).
#   (C) A script that merely DOCUMENTS "we removed the bare nohup node" in a
#       comment but is otherwise correct PASSES (no comment false-positive).
#   (D) A correct supervised relaunch LOOP launched via `nohup bash "$SUP"`
#       (the allowed last-resort fallback) PASSES — it is NOT a bare nohup.
#
# v21.5.0 cases (the 2026-08-02/03 outage: every box supervised, listening,
# "healthy" — and deaf for two days):
#   (E) A floating checkout (`git pull`, no pin) FAILS.
#   (F) A shallow clone (`--depth 1`, cannot resolve a pinned SHA) FAILS.
#   (G) No GHL_TOOL_PROFILE (upstream default = the full 858-tool surface) FAILS.
#   (H) The unconditional launchd KeepAlive boolean (turns a bad-token exit into
#       a 10s relaunch loop) FAILS.
#   (I) `rm -rf dist` before a successful build FAILS.
#   (J) A missing liveness probe FAILS.
#   (K) Re-registering ghl-community-mcp in mcp.servers FAILS.
#   (L) No log rotation FAILS (the fleet's ghl-mcp stderr.log had grown to
#       5.4 MB on the operator box / 2.2 MB on a second fleet box, unrotated
#       since May).
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="$REPO_ROOT/scripts/qc-assert-ghl-mcp-supervised.sh"
PROBE_SRC="$REPO_ROOT/scripts/ghl-mcp-probe.sh"
PIN_SRC="$REPO_ROOT/config/ghl-mcp-pin.env"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== ghl-mcp-supervised.test.sh (v21.5.0) ==="
echo ""

if [ ! -f "$GATE" ]; then
  echo "  FAIL: gate script not found at $GATE"
  exit 1
fi

# ── (A) Shipped repo scripts PASS ─────────────────────────────────────────────
if bash "$GATE" >/dev/null 2>&1; then
  pass "(A) shipped repo autostart scripts pass the supervision + install gate"
else
  fail "(A) shipped repo autostart scripts FAIL the gate (regression!)"
fi

# Helper: build a sandbox with given autostart + vps-overlay contents, run gate.
# $3 (optional): "no-probe" to omit scripts/ghl-mcp-probe.sh from the sandbox.
# Echoes the gate's exit code.
_run_sandbox() {
  local autostart_body="$1" vps_body="$2" mode="${3:-}"
  local tmp; tmp="$(mktemp -d)"
  mkdir -p "$tmp/scripts" "$tmp/config" "$tmp/platform/vps/36-ghl-mcp-setup-scripts"
  cp "$GATE" "$tmp/scripts/qc-assert-ghl-mcp-supervised.sh"
  [ -f "$PIN_SRC" ] && cp "$PIN_SRC" "$tmp/config/ghl-mcp-pin.env"
  if [ "$mode" != "no-probe" ] && [ -f "$PROBE_SRC" ]; then
    cp "$PROBE_SRC" "$tmp/scripts/ghl-mcp-probe.sh"
  fi
  printf '%s\n' "$autostart_body" > "$tmp/scripts/ghl-mcp-autostart.sh"
  printf '%s\n' "$vps_body" > "$tmp/platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh"
  bash "$tmp/scripts/qc-assert-ghl-mcp-supervised.sh" >/dev/null 2>&1
  local rc=$?
  rm -rf "$tmp"
  echo "$rc"
}

# A fully-correct synthetic autostart: Mac launchd (crash-only) + VPS pm2 +
# reboot hook + both ports + pinned commit + pinned tool profile + archive build
# + artifact assertion + probe wiring.
GOOD_AUTOSTART='#!/usr/bin/env bash
# com.clawd.ghl-mcp launchd plist
GHL_MCP_VETTED_COMMIT="bfc2bbe15a4090b82351593b6ca52eed7a8dbbe3"
git -C "$MCP_DIR" checkout --detach --force "$GHL_MCP_VETTED_COMMIT"
git -C "$MCP_DIR" archive "$GHL_MCP_VETTED_COMMIT" | tar -x -C "$tmp"
grep -q "connect(transport)" "$tmp/dist/main.js"
echo "<key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict> <key>RunAtLoad</key><true/>"
echo "<key>GHL_TOOL_PROFILE</key><string>curated</string>"
echo "GHL_TOOL_PROFILE: \"curated\","
echo "stop_exit_codes: [0],"
echo "PORT=8765 MCP_SERVER_PORT=8765"
echo "<key>GHL_MCP_LOG_DIR</key><string>$HOME/Library/Logs/ghl-mcp</string>"
GHL_MCP_LOG_MAX_BYTES=10485760
bash "$SELF_DIR/ghl-mcp-probe.sh" --once
pm2 start ecosystem.config.js
pm2 save
pm2 startup
crontab -l | grep "pm2 resurrect"
GHL_MCP_BIND_HOST="127.0.0.1"
cat > "$MCP_DIR/.ghl-mcp-bind-guard.cjs" <<GUARDEOF
net.Server.prototype.listen = function () {};
GUARDEOF
NODE_OPTIONS="--require \"$BIND_GUARD\" $NODE_OPTIONS"
npm ci --ignore-scripts --no-audit --no-fund
npm ci --omit=dev --ignore-scripts --no-audit --no-fund'
GOOD_VPS='#!/usr/bin/env bash
GHL_MCP_VETTED_COMMIT="bfc2bbe15a4090b82351593b6ca52eed7a8dbbe3"
git -C "$MCP_DIR" checkout --detach --force "$GHL_MCP_VETTED_COMMIT"
git -C "$MCP_DIR" archive "$GHL_MCP_VETTED_COMMIT" | tar -x -C "$tmp"
grep -q "connect(transport)" "$tmp/dist/main.js"
echo "GHL_TOOL_PROFILE: \"curated\","
echo "stop_exit_codes: [0],"
GHL_MCP_LOG_MAX_BYTES=10485760
pm2 start ecosystem.config.js
pm2 save
pm2 startup
echo "PORT=8765 MCP_SERVER_PORT=8765"
echo "@reboot pm2 resurrect"
GHL_MCP_BIND_HOST="127.0.0.1"
cat > "$MCP_DIR/.ghl-mcp-bind-guard.cjs" <<GUARDEOF
net.Server.prototype.listen = function () {};
GUARDEOF
NODE_OPTIONS="--require \"$BIND_GUARD\" $NODE_OPTIONS"
npm ci --ignore-scripts --no-audit --no-fund
npm ci --omit=dev --ignore-scripts --no-audit --no-fund'

# Sanity: the synthetic GOOD pair must itself pass, otherwise every negative
# case below would "pass" for the wrong reason.
rc="$(_run_sandbox "$GOOD_AUTOSTART" "$GOOD_VPS")"
if [ "$rc" = "0" ]; then
  pass "(A2) the synthetic fully-correct pair passes the gate (fixtures are valid)"
else
  fail "(A2) the synthetic fully-correct pair FAILED the gate (exit $rc) — fixtures are stale vs the gate"
fi

# ── (B) Regressed scripts FAIL ────────────────────────────────────────────────
BAD_AUTOSTART='#!/usr/bin/env bash
MCP_SERVER_PORT=8765 nohup node "$MCP_DIR/dist/main.js" &'
rc="$(_run_sandbox "$BAD_AUTOSTART" "$BAD_AUTOSTART")"
if [ "$rc" = "1" ]; then
  pass "(B) regressed bare-nohup + unpinned-PORT scripts FAIL (exit 1)"
else
  fail "(B) regressed scripts did NOT fail (exit $rc) — gate is not catching the incident pattern"
fi

# ── (C) Comment mentioning 'nohup node' is NOT a false positive ───────────────
DOC_AUTOSTART="${GOOD_AUTOSTART}
# NOTE: we REMOVED the bare nohup node path (it killed the fleet)."
rc="$(_run_sandbox "$DOC_AUTOSTART" "$GOOD_VPS")"
if [ "$rc" = "0" ]; then
  pass "(C) a script that only DOCUMENTS 'nohup node' in a comment PASSES (no false positive)"
else
  fail "(C) comment-only 'nohup node' tripped the gate (exit $rc) — false positive"
fi

# ── (D) Supervised relaunch loop via 'nohup bash' is allowed ──────────────────
LOOP_AUTOSTART="${GOOD_AUTOSTART}
setsid nohup bash \"\$SUP\" >/dev/null 2>&1 &"
rc="$(_run_sandbox "$LOOP_AUTOSTART" "$GOOD_VPS")"
if [ "$rc" = "0" ]; then
  pass "(D) a setsid 'nohup bash \$SUP' supervised loop PASSES (allowed fallback)"
else
  fail "(D) supervised 'nohup bash' loop was rejected (exit $rc) — over-strict"
fi

# ── (E) Floating checkout (git pull, no pin) FAILS ────────────────────────────
FLOATING="$(printf '%s\n' "$GOOD_AUTOSTART" | grep -v 'GHL_MCP_VETTED_COMMIT')
git -C \"\$MCP_DIR\" pull --ff-only"
rc="$(_run_sandbox "$FLOATING" "$GOOD_VPS")"
if [ "$rc" = "1" ]; then
  pass "(E) a floating 'git pull' checkout with no pinned commit FAILS"
else
  fail "(E) floating checkout was accepted (exit $rc) — supply-chain roulette would ship"
fi

# ── (F) Shallow clone cannot resolve a pin -> FAILS ───────────────────────────
SHALLOW="${GOOD_AUTOSTART}
git clone --depth 1 https://example.invalid/repo.git \"\$MCP_DIR\""
rc="$(_run_sandbox "$SHALLOW" "$GOOD_VPS")"
if [ "$rc" = "1" ]; then
  pass "(F) a --depth 1 clone FAILS (a shallow clone cannot resolve the pinned SHA)"
else
  fail "(F) shallow clone was accepted (exit $rc)"
fi

# ── (G) No GHL_TOOL_PROFILE -> the 858-tool default -> FAILS ─────────────────
NOPROFILE="$(printf '%s\n' "$GOOD_AUTOSTART" | grep -v 'GHL_TOOL_PROFILE')"
rc="$(_run_sandbox "$NOPROFILE" "$GOOD_VPS")"
if [ "$rc" = "1" ]; then
  pass "(G) an autostart that never sets GHL_TOOL_PROFILE FAILS (858-tool default)"
else
  fail "(G) missing GHL_TOOL_PROFILE was accepted (exit $rc)"
fi

# ── (H) Unconditional KeepAlive boolean -> bad-token 10s loop -> FAILS ───────
KEEPALIVE_TRUE="$(printf '%s\n' "$GOOD_AUTOSTART" | grep -v 'SuccessfulExit')
echo \"<key>KeepAlive</key><true/>\""
rc="$(_run_sandbox "$KEEPALIVE_TRUE" "$GOOD_VPS")"
if [ "$rc" = "1" ]; then
  pass "(H) an unconditional launchd KeepAlive=true FAILS (crash-only is mandatory)"
else
  fail "(H) unconditional KeepAlive was accepted (exit $rc) — the bad-token relaunch loop could ship"
fi

# ── (I) rm -rf dist before a successful build -> FAILS ───────────────────────
RM_DIST="${GOOD_AUTOSTART}
rm -rf \"\$MCP_DIR/dist\""
rc="$(_run_sandbox "$RM_DIST" "$GOOD_VPS")"
if [ "$rc" = "1" ]; then
  pass "(I) deleting dist/ before a successful build FAILS"
else
  fail "(I) 'rm -rf dist' was accepted (exit $rc) — a failed build could leave a box with no server"
fi

# ── (J) Missing liveness probe -> FAILS ──────────────────────────────────────
rc="$(_run_sandbox "$GOOD_AUTOSTART" "$GOOD_VPS" "no-probe")"
if [ "$rc" = "1" ]; then
  pass "(J) a missing scripts/ghl-mcp-probe.sh FAILS (nothing would detect alive-but-deaf)"
else
  fail "(J) missing liveness probe was accepted (exit $rc)"
fi

# ── (K) Re-registering Tier 2 in mcp.servers -> FAILS ────────────────────────
REGISTERS="${GOOD_AUTOSTART}
openclaw mcp set ghl-community-mcp \"{}\""
rc="$(_run_sandbox "$REGISTERS" "$GOOD_VPS")"
if [ "$rc" = "1" ]; then
  pass "(K) re-registering ghl-community-mcp in mcp.servers FAILS (Tier 2 is on-demand curl)"
else
  fail "(K) Tier 2 registration was accepted (exit $rc) — the per-init tool-catalogue tax would return"
fi

# ── (L) No log rotation -> FAILS ─────────────────────────────────────────────
NOROTATE="$(printf '%s\n' "$GOOD_AUTOSTART" | grep -v 'GHL_MCP_LOG_MAX_BYTES')"
rc="$(_run_sandbox "$NOROTATE" "$GOOD_VPS")"
if [ "$rc" = "1" ]; then
  pass "(L) an autostart with no log rotation FAILS (stderr.log grew to 5.4 MB fleet-side)"
else
  fail "(L) missing log rotation was accepted (exit $rc)"
fi

# ── (M) D6: no loopback bind guard -> FAILS ──────────────────────────────────
# The P0 of this release. Upstream hardcodes app.listen(port,'0.0.0.0') in BOTH
# entry points, so an env var alone is not a fix — the gate must require the
# GUARD MECHANISM, not a reassuring-looking string.
NOGUARD="$(printf '%s\n' "$GOOD_AUTOSTART" | grep -v 'bind-guard\|net.Server.prototype.listen')"
rc="$(_run_sandbox "$NOGUARD" "$GOOD_VPS")"
if [ "$rc" = "1" ]; then
  pass "(M) an autostart with no loopback bind guard FAILS (19 Mac boxes were LAN-exposed in exactly this state)"
else
  fail "(M) a missing bind guard was accepted (exit $rc) — an unauthenticated CRM endpoint would ship on 0.0.0.0"
fi

# ── (M2) Guard generated but never preloaded -> FAILS ────────────────────────
# Writing the file and forgetting NODE_OPTIONS=--require is the realistic
# half-fix: everything LOOKS present and nothing is enforced at runtime.
NOPRELOAD="$(printf '%s\n' "$GOOD_AUTOSTART" | grep -v 'NODE_OPTIONS')"
rc="$(_run_sandbox "$NOPRELOAD" "$GOOD_VPS")"
if [ "$rc" = "1" ]; then
  pass "(M2) generating the bind guard but never preloading it FAILS (a guard that is not loaded is theatre)"
else
  fail "(M2) an unloaded bind guard was accepted (exit $rc)"
fi

# ── (M3) A routable bind host -> FAILS ───────────────────────────────────────
ROUTABLE="${GOOD_AUTOSTART}
GHL_MCP_BIND_HOST=0.0.0.0"
rc="$(_run_sandbox "$ROUTABLE" "$GOOD_VPS")"
if [ "$rc" = "1" ]; then
  pass "(M3) declaring a ROUTABLE GHL_MCP_BIND_HOST FAILS"
else
  fail "(M3) a routable bind host was accepted (exit $rc)"
fi

# ── (N) R5: the 'npm ci || npm install' lockfile-defeating fallback -> FAILS ──
# This is the shape that shipped: it fires exactly when package.json and the
# lockfile disagree, then resolves fresh from the registry — voiding the vetting
# verdict's "dependency graph unchanged" claim at the worst possible moment.
NPMFALLBACK="$(printf '%s\n' "$GOOD_AUTOSTART" | grep -v '^npm ci')
npm ci --no-audit --no-fund || npm install --no-audit --no-fund"
rc="$(_run_sandbox "$NPMFALLBACK" "$GOOD_VPS")"
if [ "$rc" = "1" ]; then
  pass "(N) an 'npm ci || npm install' fallback FAILS (it silently discards the lockfile)"
else
  fail "(N) the lockfile-defeating npm fallback was accepted (exit $rc)"
fi

# ── (O) R5: npm without --ignore-scripts -> FAILS ────────────────────────────
NOIGNORE="$(printf '%s\n' "$GOOD_AUTOSTART" | grep -v -- '--ignore-scripts')
npm ci --no-audit --no-fund"
rc="$(_run_sandbox "$NOIGNORE" "$GOOD_VPS")"
if [ "$rc" = "1" ]; then
  pass "(O) running npm without --ignore-scripts FAILS (transitive postinstall hooks run with the GHL PIT in the env)"
else
  fail "(O) npm without --ignore-scripts was accepted (exit $rc)"
fi

# ── (P) R5: the unpinned working-tree prod refresh -> FAILS ──────────────────
UNPINNED_REFRESH="${GOOD_AUTOSTART}
( cd \"\$MCP_DIR\" && npm install --no-audit --no-fund --omit=dev )"
rc="$(_run_sandbox "$UNPINNED_REFRESH" "$GOOD_VPS")"
if [ "$rc" = "1" ]; then
  pass "(P) an unpinned 'npm install --omit=dev' against the working tree FAILS"
else
  fail "(P) the unpinned production refresh was accepted (exit $rc)"
fi

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
