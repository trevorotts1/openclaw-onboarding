#!/usr/bin/env bash
# =============================================================================
# tests/unit/power-resilience-gate.test.sh
# =============================================================================
# A provisioner change with no test is how the power-outage defect shipped in
# the first place: the installer laid login-gated services onto FileVault-locked
# boxes and REPORTED SUCCESS, and nothing anywhere asserted otherwise.
#
# This test is the thing that would have caught it. It proves:
#
#   (1) THE FILEVAULT GATE FAILS CLOSED on a simulated FileVault-ON box.
#       Default behaviour, no opt-out set → rc 78 (EX_CONFIG), not 0.
#   (2) The gate ALSO fails closed when auto-login is unset (the login-gated
#       LaunchAgent trap) even with FileVault off.
#   (3) The gate PASSES only when BOTH preconditions hold.
#   (4) The gate is not silently bypassable — the opt-out must be the exact,
#       deliberately clumsy acknowledgement string.
#   (5) THE PMSET CALL IS ACTUALLY PRESENT — `autorestart 1` is really issued
#       (this was absent from the provisioner ENTIRELY), and it is NOT applied
#       blindly to a laptop's battery.
#   (6) cloudflared is resolved, never hardcoded to /opt/homebrew (dead on Intel).
#   (7) Tunnel tokens go to a mode-600 token-FILE, never onto a command line
#       where `ps` exposes them to any local user.
#   (8) The three hand-rolled pm2 launchd names collapse into ONE canonical job.
#   (9) The gateway is NOT blindly converted to a LaunchDaemon on a box with a
#       session-coupled plugin enabled.
#
# Fully offline. No root. No live box. Every system command is faked via the
# library's injectable seams (PR_FDESETUP / PR_PMSET / PR_DEFAULTS / ...).
#
# Exit 0 = all pass. Exit 1 = one or more failed.
# =============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LIB="$REPO_ROOT/platform/mac/power-resilience/lib-power-resilience.sh"
BOOTSTRAP="$REPO_ROOT/platform/mac/bootstrap.sh"
FIXER="$REPO_ROOT/scripts/fix-power-resilience.sh"
CC_TUNNEL="$REPO_ROOT/32-command-center-setup/scripts/setup-tunnel-daemon.sh"
HARDEN="$REPO_ROOT/platform/mac/tunnel-hardening/harden-mac-tunnel.sh"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== power-resilience-gate.test.sh ==="

[ -f "$LIB" ] || { echo "  FAIL: library not found at $LIB"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
BIN="$WORK/bin"; mkdir -p "$BIN"

# ---- Fake system commands (the library's injectable seams) -------------------
# fdesetup: prints whatever FV_STATE says.
cat > "$BIN/fdesetup" <<'EOF'
#!/bin/sh
echo "FileVault is ${FV_STATE:-On}."
EOF

# defaults: `defaults read <plist> autoLoginUser` → AUTOLOGIN, or rc 1 if empty
# (that is exactly what real `defaults` does when the key does not exist).
cat > "$BIN/defaults" <<'EOF'
#!/bin/sh
if [ "${1:-}" = "read" ] && [ "${3:-}" = "autoLoginUser" ]; then
  if [ -n "${AUTOLOGIN:-}" ]; then echo "$AUTOLOGIN"; exit 0; fi
  echo "does not exist" >&2; exit 1
fi
exit 0
EOF

# pmset: records every invocation so we can assert WHAT was actually issued.
cat > "$BIN/pmset" <<'EOF'
#!/bin/sh
echo "pmset $*" >> "$PMSET_LOG"
if [ "${1:-}" = "-g" ]; then
  printf ' autorestart          %s\n' "${FAKE_AUTORESTART:-1}"
  printf ' sleep                %s\n' "${FAKE_SLEEP:-0}"
fi
exit 0
EOF

# ioreg: battery present iff FAKE_LAPTOP=1  (drives pr_is_laptop)
cat > "$BIN/ioreg" <<'EOF'
#!/bin/sh
[ "${FAKE_LAPTOP:-0}" = "1" ] && echo "  +-o AppleSmartBattery  <class AppleSmartBattery>"
exit 0
EOF

# networksetup: no Ethernet IP (so pr_check_ethernet takes the WARN path)
cat > "$BIN/networksetup" <<'EOF'
#!/bin/sh
echo "IP address: none"
exit 0
EOF

chmod +x "$BIN"/*

export PR_FDESETUP="$BIN/fdesetup"
export PR_DEFAULTS="$BIN/defaults"
export PR_PMSET="$BIN/pmset"
export PR_IOREG="$BIN/ioreg"
export PR_SYSSETUP="$BIN/networksetup"
export PR_LOGINWINDOW_PLIST="$WORK/loginwindow"
export PR_SECRETS_DIR="$WORK/secrets"
export PR_LAUNCHAGENTS_DIR="$WORK/LaunchAgents"
export PR_LAUNCHDAEMONS_DIR="$WORK/LaunchDaemons"
export PR_MARKER_ATTENDED="$WORK/ATTENDED-ONLY-BOX"
export PR_OPENCLAW_JSON="$WORK/openclaw.json"
mkdir -p "$PR_LAUNCHAGENTS_DIR" "$PR_LAUNCHDAEMONS_DIR"

# shellcheck source=/dev/null
. "$LIB"

# =============================================================================
# (1) THE FILEVAULT GATE FAILS CLOSED — the headline assertion
# =============================================================================
echo "--- (1) FileVault ON  → gate MUST fail closed (rc 78) ---"
export FV_STATE="On"
export AUTOLOGIN="someuser"          # auto-login set, so FileVault is the ONLY defect
unset OPENCLAW_ACCEPT_ATTENDED_ONLY_BOX
OUT1="$(pr_assert_unattended_boot_capable 2>&1)"; RC1=$?

[ "$RC1" -eq 78 ] \
    && pass "1a: FileVault-ON box → rc=78 (EX_CONFIG). GATE FAILS CLOSED." \
    || fail "1a: FileVault-ON box returned rc=$RC1, expected 78. GATE DID NOT FAIL CLOSED."
[ "$RC1" -ne 0 ] \
    && pass "1b: rc is non-zero — provisioning would ABORT, not report success" \
    || fail "1b: rc=0 — the installer would happily ship another undead Mac"
echo "$OUT1" | grep -q "PROVISIONING REFUSED" \
    && pass "1c: failure message is loud ('PROVISIONING REFUSED')" \
    || fail "1c: failure message not loud"
echo "$OUT1" | grep -q "PRE-BOOT unlock screen" \
    && pass "1d: message explains the Apple Silicon pre-boot halt" \
    || fail "1d: message does not explain the pre-boot halt"
echo "$OUT1" | grep -q "LaunchDaemons DO NOT RUN EITHER" \
    && pass "1e: message kills the 'a LaunchDaemon will save us' myth" \
    || fail "1e: message does not say LaunchDaemons also fail"
echo "$OUT1" | grep -qi "physically present\|PHYSICALLY PRESENT\|physically at the machine" \
    && pass "1f: message states a human must be PHYSICALLY PRESENT (the trade-off)" \
    || fail "1f: message does not state the physical-presence trade-off"
echo "$OUT1" | grep -q "UNATTENDED RECOVERY IS IMPOSSIBLE" \
    && pass "1g: message states unattended recovery is impossible with FileVault on" \
    || fail "1g: message does not state that unattended recovery is impossible"

# =============================================================================
# (2) Auto-login unset → gate fails closed too (the login-gated LaunchAgent trap)
# =============================================================================
echo "--- (2) FileVault OFF but NO auto-login → gate MUST still fail ---"
export FV_STATE="Off"
unset AUTOLOGIN
OUT2="$(pr_assert_unattended_boot_capable 2>&1)"; RC2=$?
[ "$RC2" -eq 78 ] \
    && pass "2a: no-auto-login box → rc=78. Login-gated services are refused." \
    || fail "2a: no-auto-login box returned rc=$RC2, expected 78"
echo "$OUT2" | grep -q "RunAtLoad=true and KeepAlive=true DO NOT HELP" \
    && pass "2b: message names the RunAtLoad/KeepAlive red herring" \
    || fail "2b: message does not name the red herring"
echo "$OUT2" | grep -q "3 days 14 hours" \
    && pass "2c: message cites the measured 3d14h dead-gateway evidence" \
    || fail "2c: message does not cite the measured evidence"

# =============================================================================
# (3) Both preconditions met → gate PASSES (it is not just always-fail)
# =============================================================================
echo "--- (3) FileVault OFF + auto-login SET → gate must PASS ---"
export FV_STATE="Off"; export AUTOLOGIN="clientuser"
OUT3="$(pr_assert_unattended_boot_capable 2>&1)"; RC3=$?
[ "$RC3" -eq 0 ] \
    && pass "3a: correctly-configured box → rc=0 (gate is not a blanket fail)" \
    || fail "3a: correctly-configured box returned rc=$RC3, expected 0"
echo "$OUT3" | grep -q "GATE PASS" \
    && pass "3b: says GATE PASS" \
    || fail "3b: no GATE PASS in output"

# =============================================================================
# (4) The gate is not silently bypassable
# =============================================================================
echo "--- (4) opt-out must be the EXACT acknowledgement string ---"
export FV_STATE="On"; export AUTOLOGIN="someuser"
OPENCLAW_ACCEPT_ATTENDED_ONLY_BOX=1 \
  pr_assert_unattended_boot_capable >/dev/null 2>&1; RC4A=$?
[ "$RC4A" -eq 78 ] \
    && pass "4a: a truthy '1' does NOT bypass the gate (rc=78)" \
    || fail "4a: '1' bypassed the gate (rc=$RC4A) — that is a silent bypass"
OPENCLAW_ACCEPT_ATTENDED_ONLY_BOX=yes \
  pr_assert_unattended_boot_capable >/dev/null 2>&1; RC4B=$?
[ "$RC4B" -eq 78 ] \
    && pass "4b: 'yes' does NOT bypass the gate (rc=78)" \
    || fail "4b: 'yes' bypassed the gate (rc=$RC4B)"
OUT4C="$(OPENCLAW_ACCEPT_ATTENDED_ONLY_BOX=i-will-be-physically-present \
          pr_assert_unattended_boot_capable 2>&1)"; RC4C=$?
[ "$RC4C" -eq 0 ] \
    && pass "4c: the exact acknowledgement string is honoured (rc=0)" \
    || fail "4c: exact acknowledgement not honoured (rc=$RC4C)"
echo "$OUT4C" | grep -q "DEGRADED" \
    && pass "4d: an acknowledged box is still branded DEGRADED" \
    || fail "4d: acknowledged box not branded DEGRADED"
[ -f "$PR_MARKER_ATTENDED" ] \
    && pass "4e: a durable ATTENDED-ONLY marker is written (audits stay honest)" \
    || fail "4e: no durable marker written"

# =============================================================================
# (5) THE PMSET CALL IS ACTUALLY PRESENT  (it was absent ENTIRELY)
# =============================================================================
echo "--- (5) pmset: autorestart 1 is really issued ---"
export PMSET_LOG="$WORK/pmset.log"; : > "$PMSET_LOG"
export FAKE_LAPTOP=0
pr_apply_pmset >/dev/null 2>&1

grep -q -- "-a autorestart 1" "$PMSET_LOG" \
    && pass "5a: DESKTOP → 'pmset -a autorestart 1' IS issued (was never called at all)" \
    || fail "5a: 'pmset -a autorestart 1' NOT issued. Mains returns, the Mac stays OFF."
grep -q -- "-a sleep 0" "$PMSET_LOG" \
    && pass "5b: 'pmset -a sleep 0' issued" \
    || fail "5b: 'pmset -a sleep 0' not issued"
grep -q -- "-a disksleep 0" "$PMSET_LOG" \
    && pass "5c: 'pmset -a disksleep 0' issued" \
    || fail "5c: 'pmset -a disksleep 0' not issued"
grep -q -- "-a womp 1" "$PMSET_LOG" \
    && pass "5d: 'pmset -a womp 1' issued" \
    || fail "5d: 'pmset -a womp 1' not issued"

echo "--- (5e) pmset: a LAPTOP is handled explicitly, not as a mini ---"
: > "$PMSET_LOG"
export FAKE_LAPTOP=1
OUT5="$(pr_apply_pmset 2>&1)"
grep -q -- "-a sleep 0" "$PMSET_LOG" \
    && fail "5e: 'sleep 0' applied to ALL power sources on a LAPTOP — drains the battery flat" \
    || pass "5e: laptop does NOT get '-a sleep 0' (no battery-drain footgun)"
grep -q -- "-c sleep 0" "$PMSET_LOG" \
    && pass "5f: laptop gets AC-only ('-c') settings" \
    || fail "5f: laptop got no AC-only settings"
echo "$OUT5" | grep -qi "laptop" \
    && pass "5g: laptop case is called out explicitly in the output" \
    || fail "5g: laptop case not called out"
export FAKE_LAPTOP=0

echo "--- (5h) the provisioner actually CALLS pmset (wired, not just defined) ---"
grep -q "pr_apply_pmset" "$BOOTSTRAP" \
    && pass "5h: platform/mac/bootstrap.sh calls pr_apply_pmset" \
    || fail "5h: the provisioner never calls pr_apply_pmset — dead code"
# bootstrap now reaches the FileVault gate through the mode-aware dispatcher
# pr_preflight_gate (provision → pr_assert_unattended_boot_capable; update →
# advisory). Behavioural proof that provision still hits the HARD gate is section
# (11a). This asserts the gate is not dead code — it IS invoked.
grep -q "pr_preflight_gate" "$BOOTSTRAP" \
    && pass "5i: platform/mac/bootstrap.sh reaches the FileVault gate via pr_preflight_gate" \
    || fail "5i: the provisioner never calls the gate — dead code"
grep -q "exit 78" "$BOOTSTRAP" \
    && pass "5j: the provisioner HARD-EXITS 78 on gate failure" \
    || fail "5j: the provisioner does not hard-exit on gate failure"
grep -qE "pmset.*autorestart" "$HARDEN" \
    && pass "5k: harden-mac-tunnel.sh Layer D now sets autorestart (it never did)" \
    || fail "5k: harden-mac-tunnel.sh still does not set autorestart"

# =============================================================================
# (6) cloudflared is RESOLVED, not hardcoded (dead on Intel)
# =============================================================================
echo "--- (6) cloudflared binary resolution ---"
grep -q "command -v cloudflared" "$CC_TUNNEL" \
    && pass "6a: setup-tunnel-daemon.sh resolves cloudflared with 'command -v'" \
    || fail "6a: setup-tunnel-daemon.sh does not resolve the binary"
if grep -qE '<string>/opt/homebrew/bin/cloudflared</string>' "$CC_TUNNEL"; then
    fail "6b: setup-tunnel-daemon.sh STILL hardcodes /opt/homebrew/bin/cloudflared into the plist (exit 78 on every Intel Mac)"
else
    pass "6b: no hardcoded /opt/homebrew/bin/cloudflared in the rendered plist"
fi
grep -q "usr/local/bin/cloudflared" "$CC_TUNNEL" \
    && pass "6c: /usr/local (Intel Homebrew prefix) is a fallback" \
    || fail "6c: Intel Homebrew prefix is not considered"

# =============================================================================
# (7) SECURITY: token-file mode 600, never a cleartext CLI arg
# =============================================================================
echo "--- (7) tunnel token never in cleartext on a command line ---"
TF="$(pr_install_tunnel_token_file "unit-test" "eyJhIjoiZmFrZS10ZXN0LXRva2VuIn0")"
[ -f "$TF" ] \
    && pass "7a: token file written at $TF" \
    || fail "7a: token file not written"
MODE="$(stat -c '%a' "$TF" 2>/dev/null || stat -f '%Lp' "$TF" 2>/dev/null)"
[ "$MODE" = "600" ] \
    && pass "7b: token file is mode 600 (was: world-readable root plist)" \
    || fail "7b: token file mode is $MODE, expected 600"

PLIST_OUT="$(pr_render_tunnel_daemon_plist "com.cloudflare.unit-test" "/usr/local/bin/cloudflared" "$TF")"
echo "$PLIST_OUT" | grep -q -- "--token-file" \
    && pass "7c: rendered plist uses --token-file" \
    || fail "7c: rendered plist does not use --token-file"
if echo "$PLIST_OUT" | grep -qE '<string>--token</string>'; then
    fail "7d: rendered plist STILL passes a bare --token (visible in \`ps\` to any local user)"
else
    pass "7d: rendered plist never passes a bare --token"
fi
if echo "$PLIST_OUT" | grep -q "eyJhIjoiZmFrZS10ZXN0LXRva2VuIn0"; then
    fail "7e: THE TOKEN VALUE ITSELF is embedded in the plist — cleartext secret"
else
    pass "7e: the token VALUE never appears in the plist"
fi
echo "$PLIST_OUT" | grep -q "<key>UserName</key>" \
    && fail "7f: tunnel daemon should run as root (no UserName), got a UserName key" \
    || pass "7f: tunnel runs as a root system daemon (no GUI session needed)"
grep -q -- "--token-file" "$CC_TUNNEL" \
    && pass "7g: setup-tunnel-daemon.sh uses --token-file" \
    || fail "7g: setup-tunnel-daemon.sh does not use --token-file"
grep -q "LaunchDaemons" "$CC_TUNNEL" \
    && pass "7h: setup-tunnel-daemon.sh installs into /Library/LaunchDaemons (was LaunchAgents)" \
    || fail "7h: setup-tunnel-daemon.sh is still a LaunchAgent"

# =============================================================================
# (8) pm2: three hand-rolled names collapse into ONE
# =============================================================================
echo "--- (8) pm2 launchd naming drift is collapsed ---"
touch "$PR_LAUNCHAGENTS_DIR/com.someuser.pm2-resurrect.plist" \
      "$PR_LAUNCHAGENTS_DIR/pm2.someuser.plist" \
      "$PR_LAUNCHAGENTS_DIR/io.pm2.launch.plist" \
      "$PR_LAUNCHAGENTS_DIR/com.openclaw.pm2-resurrect.plist"
LEG="$(pr_legacy_pm2_plists)"
LEGN="$(printf '%s\n' "$LEG" | grep -c . || true)"
[ "$LEGN" -eq 3 ] \
    && pass "8a: all 3 drifted pm2 names detected as legacy" \
    || fail "8a: detected $LEGN legacy pm2 plists, expected 3"
printf '%s\n' "$LEG" | grep -q "com.openclaw.pm2-resurrect" \
    && fail "8b: the CANONICAL job was wrongly flagged as legacy (would delete itself)" \
    || pass "8b: the canonical job is NOT flagged as legacy (idempotent)"
PM2_PLIST="$(pr_render_pm2_plist "someuser" "/Users/someuser" "/usr/local/bin/pm2" "/usr/local/bin")"
echo "$PM2_PLIST" | grep -q "<string>com.openclaw.pm2-resurrect</string>" \
    && pass "8c: rendered pm2 plist uses the ONE canonical label" \
    || fail "8c: rendered pm2 plist does not use the canonical label"

# =============================================================================
# (9) The gateway is NOT blindly converted to a LaunchDaemon
# =============================================================================
echo "--- (9) session-coupling probe guards the daemon conversion ---"
cat > "$PR_OPENCLAW_JSON" <<'JSON'
{"plugins":{"entries":{"imessage":{"enabled":true},"browser":{"enabled":true}}},
 "browser":{"enabled":true,"headless":true}}
JSON
pr_gateway_can_be_daemon >/dev/null 2>&1; RC9A=$?
[ "$RC9A" -ne 0 ] \
    && pass "9a: box with iMessage enabled → REFUSES the daemon conversion (TCC would break it)" \
    || fail "9a: box with iMessage enabled was cleared for a LaunchDaemon — would silently break iMessage"

cat > "$PR_OPENCLAW_JSON" <<'JSON'
{"plugins":{"entries":{"telegram":{"enabled":true},"browser":{"enabled":true}}},
 "browser":{"enabled":true,"headless":true}}
JSON
pr_gateway_can_be_daemon >/dev/null 2>&1; RC9B=$?
[ "$RC9B" -eq 0 ] \
    && pass "9b: headless box with no session-coupled plugin → daemon is viable" \
    || fail "9b: a genuinely headless box was wrongly refused"

cat > "$PR_OPENCLAW_JSON" <<'JSON'
{"plugins":{"entries":{"browser":{"enabled":true}}},
 "browser":{"enabled":true,"headless":false}}
JSON
COUPLED="$(pr_gateway_session_coupled)"
echo "$COUPLED" | grep -q "browser(headful)" \
    && pass "9c: a HEADFUL browser is correctly detected as session-coupled" \
    || fail "9c: headful browser not detected as session-coupled"

# =============================================================================
# (10) The remediation script refuses on a FileVault-on box
# =============================================================================
echo "--- (10) fix-power-resilience.sh refuses on a FileVault-ON box ---"
[ -x "$FIXER" ] || chmod +x "$FIXER" 2>/dev/null
FV_STATE="On" PATH="$BIN:$PATH" \
  bash "$FIXER" --local >"$WORK/fix.out" 2>&1; RCF=$?
[ "$RCF" -eq 78 ] \
    && pass "10a: remediation script exits 78 on a FileVault-ON box (refuses, does not pretend)" \
    || fail "10a: remediation script exited $RCF on a FileVault-ON box, expected 78"
grep -q "REFUSING TO REMEDIATE" "$WORK/fix.out" \
    && pass "10b: it says REFUSING TO REMEDIATE" \
    || fail "10b: no refusal message"
grep -q "PHYSICALLY AT THIS MACHINE" "$WORK/fix.out" \
    && pass "10c: it prints exactly what a human must do ON SITE" \
    || fail "10c: no on-site instructions"
grep -q "sshd never starts\|sshd doesn't run\|sshd is NOT running" "$WORK/fix.out" \
    && pass "10d: it kills the 'SSH rescue will save us' myth" \
    || fail "10d: it does not address the SSH-rescue myth"

# =============================================================================
# (11) UPDATE PATH — a physical-security posture must NOT abort a routine update
# =============================================================================
# THE BUG THIS CLOSES: update-skills.sh sources platform/mac/bootstrap.sh, which
# ran the PROVISIONING hard gate (pr_assert_unattended_boot_capable) on EVERY run.
# On a healthy, reachable, ALREADY-PROVISIONED FileVault-ON box, that gate exits
# 78 and the ENTIRE update aborts before installing anything — blocking the fleet
# roll over a posture (FileVault on / no auto-login) that a live update, delivered
# over an existing connection, does not depend on. The fix scopes the hard gate to
# provisioning and downgrades it to an ADVISORY on the update path.
echo "--- (11) routine UPDATE on a FileVault-ON / no-auto-login box must PROCEED ---"
export FV_STATE="On"; unset AUTOLOGIN
unset OPENCLAW_ACCEPT_ATTENDED_ONLY_BOX
rm -f "$PR_MARKER_ATTENDED"

# 11a: the PROVISION path still fails closed (the hard gate is UNCHANGED).
pr_preflight_gate provision >/dev/null 2>&1; RC11P=$?
[ "$RC11P" -eq 78 ] \
    && pass "11a: pr_preflight_gate provision → rc=78 (first-time provisioning still hard-gates)" \
    || fail "11a: provision path returned rc=$RC11P, expected 78 — the provisioning gate regressed"

# 11b: the UPDATE path PROCEEDS on the SAME box (rc 0, not 78). THIS is the fix —
# it must FAIL against origin/main (where pr_preflight_gate does not exist) and
# PASS here.
OUT11="$(pr_preflight_gate update 2>&1)"; RC11U=$?
[ "$RC11U" -eq 0 ] \
    && pass "11b: pr_preflight_gate update → rc=0 (reachable box updates, does NOT abort 78)" \
    || fail "11b: update path returned rc=$RC11U, expected 0 — the update would still abort"

# 11c-e: the advisory explains it is not blocking + names the on-site remedy.
echo "$OUT11" | grep -q "ADVISORY" \
    && pass "11c: update path prints an ADVISORY (not a provisioning REFUSED)" \
    || fail "11c: update path did not print an advisory"
echo "$OUT11" | grep -q "does NOT block the update" \
    && pass "11d: advisory states it does NOT block the update" \
    || fail "11d: advisory does not say the update proceeds"
echo "$OUT11" | grep -q "fix-power-resilience.sh" \
    && pass "11e: advisory names the remedy (scripts/fix-power-resilience.sh)" \
    || fail "11e: advisory does not name fix-power-resilience.sh"

# 11f: an UPDATE must NOT write the permanent ATTENDED-ONLY marker — committing a
# box to attended-only forever is a provisioning decision, not an update side effect.
[ ! -f "$PR_MARKER_ATTENDED" ] \
    && pass "11f: update advisory writes NO durable ATTENDED-ONLY marker" \
    || fail "11f: update advisory wrote the permanent attended-only marker (must not)"

# 11g: an UNKNOWN/empty mode fails SAFE toward the hard gate (no accidental bypass).
pr_preflight_gate >/dev/null 2>&1; RC11D=$?
[ "$RC11D" -eq 78 ] \
    && pass "11g: default/empty mode → hard gate (rc=78), no accidental bypass" \
    || fail "11g: default mode returned rc=$RC11D, expected 78 (fail-safe default lost)"

# 11h-i: the update path still PASSES cleanly on a correctly-configured box.
export FV_STATE="Off"; export AUTOLOGIN="clientuser"
OUT11OK="$(pr_preflight_gate update 2>&1)"; RC11OK=$?
[ "$RC11OK" -eq 0 ] \
    && pass "11h: update path on a resilient box → rc=0" \
    || fail "11h: update path on a resilient box returned rc=$RC11OK, expected 0"
echo "$OUT11OK" | grep -q "Power-resilience OK" \
    && pass "11i: resilient box under update prints the OK note" \
    || fail "11i: resilient box under update missing the OK note"

# --- WIRING: the decision is actually reachable from the real entrypoints ------
echo "--- (11 wiring) bootstrap + update-skills route through the mode gate ---"
grep -q "pr_preflight_gate" "$BOOTSTRAP" \
    && pass "11j: platform/mac/bootstrap.sh calls pr_preflight_gate (mode-aware)" \
    || fail "11j: bootstrap.sh does not call pr_preflight_gate — decision unreachable"
grep -q "OPENCLAW_BOOTSTRAP_MODE" "$BOOTSTRAP" \
    && pass "11k: bootstrap.sh branches on OPENCLAW_BOOTSTRAP_MODE" \
    || fail "11k: bootstrap.sh does not read OPENCLAW_BOOTSTRAP_MODE"
grep -q "exit 78" "$BOOTSTRAP" \
    && pass "11l: bootstrap.sh STILL hard-exits 78 on a provisioning gate failure" \
    || fail "11l: bootstrap.sh lost its provisioning hard-exit"
UPDATER="$REPO_ROOT/update-skills.sh"
grep -qE "export OPENCLAW_BOOTSTRAP_MODE=update" "$UPDATER" \
    && pass "11m: update-skills.sh exports OPENCLAW_BOOTSTRAP_MODE=update (update path scoped)" \
    || fail "11m: update-skills.sh does not signal update mode — the roll would still abort"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: $FAIL assertion(s) failed"
    exit 1
fi
echo "PASS: all assertions passed"
exit 0
