#!/usr/bin/env bash
# tests/unit/ghl-mcp-supervised.test.sh — v12.24.0
#
# Verifies the GHL MCP supervision invariant gate (qc-assert-ghl-mcp-supervised.sh)
# that closes the fleet incident (12/19 boxes down/unsupervised). The gate is a
# STATIC check of the SHIPPED autostart scripts; this test exercises it in a
# sandbox of synthetic scripts.
#
#   (A) The SHIPPED repo scripts PASS (exit 0) — supervised, reboot-surviving,
#       PORT pinned, no bare nohup.
#   (B) A regressed script (bare `nohup node` + only MCP_SERVER_PORT, no pm2/
#       launchd/reboot hook) FAILS (exit 1).
#   (C) A script that merely DOCUMENTS "we removed the bare nohup node" in a
#       comment but is otherwise correct PASSES (no comment false-positive).
#   (D) A correct supervised relaunch LOOP launched via `nohup bash "$SUP"`
#       (the allowed last-resort fallback) PASSES — it is NOT a bare nohup node.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="$REPO_ROOT/scripts/qc-assert-ghl-mcp-supervised.sh"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== ghl-mcp-supervised.test.sh (v12.24.0) ==="
echo ""

if [ ! -f "$GATE" ]; then
  echo "  FAIL: gate script not found at $GATE"
  exit 1
fi

# ── (A) Shipped repo scripts PASS ─────────────────────────────────────────────
if bash "$GATE" >/dev/null 2>&1; then
  pass "(A) shipped repo autostart scripts pass the supervision gate"
else
  fail "(A) shipped repo autostart scripts FAIL the supervision gate (regression!)"
fi

# Helper: build a sandbox with given autostart + vps-overlay contents, run gate.
# Echoes the gate's exit code.
_run_sandbox() {
  local autostart_body="$1" vps_body="$2"
  local tmp; tmp="$(mktemp -d)"
  mkdir -p "$tmp/scripts" "$tmp/platform/vps/36-ghl-mcp-setup-scripts"
  cp "$GATE" "$tmp/scripts/qc-assert-ghl-mcp-supervised.sh"
  printf '%s\n' "$autostart_body" > "$tmp/scripts/ghl-mcp-autostart.sh"
  printf '%s\n' "$vps_body" > "$tmp/platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh"
  bash "$tmp/scripts/qc-assert-ghl-mcp-supervised.sh" >/dev/null 2>&1
  local rc=$?
  rm -rf "$tmp"
  echo "$rc"
}

# A fully-correct synthetic autostart (Mac launchd + VPS pm2 + reboot + both ports).
GOOD_AUTOSTART='#!/usr/bin/env bash
# com.clawd.ghl-mcp launchd plist
echo "<key>KeepAlive</key> <key>RunAtLoad</key><true/>"
echo "PORT=8765 MCP_SERVER_PORT=8765"
pm2 start ecosystem.config.js
pm2 save
pm2 startup
crontab -l | grep "pm2 resurrect"'
GOOD_VPS='#!/usr/bin/env bash
pm2 start ecosystem.config.js
pm2 save
pm2 startup
echo "PORT=8765 MCP_SERVER_PORT=8765"
echo "@reboot pm2 resurrect"'

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
DOC_AUTOSTART='#!/usr/bin/env bash
# NOTE: we REMOVED the bare nohup node path (it killed the fleet).
# <key>KeepAlive</key> <key>RunAtLoad</key> com.clawd.ghl-mcp
pm2 start ecosystem.config.js
pm2 save
pm2 startup
PORT=8765
MCP_SERVER_PORT=8765'
rc="$(_run_sandbox "$DOC_AUTOSTART" "$GOOD_VPS")"
if [ "$rc" = "0" ]; then
  pass "(C) a script that only DOCUMENTS 'nohup node' in a comment PASSES (no false positive)"
else
  fail "(C) comment-only 'nohup node' tripped the gate (exit $rc) — false positive"
fi

# ── (D) Supervised relaunch loop via 'nohup bash' is allowed ──────────────────
LOOP_AUTOSTART='#!/usr/bin/env bash
# <key>KeepAlive</key> <key>RunAtLoad</key> com.clawd.ghl-mcp
pm2 start ecosystem.config.js
pm2 save
pm2 startup
PORT=8765
MCP_SERVER_PORT=8765
setsid nohup bash "$SUP" >/dev/null 2>&1 &'
rc="$(_run_sandbox "$LOOP_AUTOSTART" "$GOOD_VPS")"
if [ "$rc" = "0" ]; then
  pass "(D) a setsid 'nohup bash \$SUP' supervised loop PASSES (allowed fallback)"
else
  fail "(D) supervised 'nohup bash' loop was rejected (exit $rc) — over-strict"
fi

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
