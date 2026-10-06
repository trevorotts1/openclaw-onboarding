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
#  (12) LAYER E, the reboot-stale RESCUE tunnel watchdog, actually BITES. The
#       rescue connector com.blackceo.rescue-<slug> can return from a reboot
#       holding a stale cached edge address and dial an RFC1918 address on port
#       7844 forever. The process is ALIVE, so launchd KeepAlive keeps it and
#       the existing pgrep-based watchdog reports OK. These assertions run the
#       watchdog against a synthetic log window with launchctl and nc stubbed on
#       PATH and read the stub's own call log: a stale window IS kicked, a
#       window with one registration is NOT, a cooldown blocks a second kick, an
#       unreadable window is UNDETERMINED rather than zero, and a disabled sshd
#       is re-enabled and PROVEN with a real connection attempt.
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

# =============================================================================
# (12) LAYER E: the reboot-stale RESCUE tunnel watchdog
# =============================================================================
# The gap this closes: the rescue connector com.blackceo.rescue-<slug> can come
# back from a reboot holding a stale cached edge address and dial the LAN router
# (RFC1918:7844) forever. The process is ALIVE, so launchd KeepAlive keeps it,
# install-watchdog-agent.sh's pgrep check reports OK, and the box is dark to the
# operator. Nothing in this repo detected "alive but never registered" before.
#
# Every assertion below is BEHAVIOURAL: the watchdog is executed against a
# synthetic log window with launchctl and nc stubbed on PATH, and the stub's own
# call log is the evidence. A presence grep would not have caught the defect.
echo "--- (12) Layer E: rescue-tunnel reboot-stale watchdog ---"

RTW="$REPO_ROOT/platform/mac/tunnel-hardening/rescue-tunnel-watchdog.sh"
RTW_PLIST="$REPO_ROOT/platform/mac/tunnel-hardening/com.blackceo.rescue-tunnel-watchdog.plist.template"
RTW_INSTALL="$REPO_ROOT/platform/mac/tunnel-hardening/install-rescue-tunnel-watchdog.sh"

# 12a-c: the three artifacts exist and parse.
[ -f "$RTW" ] \
    && pass "12a: rescue-tunnel-watchdog.sh ships" \
    || fail "12a: rescue-tunnel-watchdog.sh is missing"
[ -f "$RTW_PLIST" ] \
    && pass "12b: com.blackceo.rescue-tunnel-watchdog.plist.template ships" \
    || fail "12b: the Layer E LaunchDaemon template is missing"
[ -f "$RTW_INSTALL" ] \
    && pass "12c: install-rescue-tunnel-watchdog.sh ships" \
    || fail "12c: the Layer E installer is missing"
if [ -f "$RTW" ] && bash -n "$RTW" 2>/dev/null; then
    pass "12d: rescue-tunnel-watchdog.sh is bash -n clean"
else
    fail "12d: rescue-tunnel-watchdog.sh does not parse"
fi
if [ -f "$RTW_INSTALL" ] && bash -n "$RTW_INSTALL" 2>/dev/null; then
    pass "12e: install-rescue-tunnel-watchdog.sh is bash -n clean"
else
    fail "12e: install-rescue-tunnel-watchdog.sh does not parse"
fi

# ---- Harness: stub launchctl + nc, synthesize a connector log window ---------
E="$WORK/layerE"
EBIN="$E/bin"; EDAEMONS="$E/LaunchDaemons"; ELOGS="$E/Logs"; ESTATE="$E/state"
mkdir -p "$EBIN" "$EDAEMONS" "$ELOGS" "$ESTATE"
LCLOG="$E/launchctl.calls"

cat > "$EBIN/launchctl" <<'EOF'
#!/bin/sh
echo "launchctl $*" >> "$LCLOG"
if [ "${1:-}" = "print-disabled" ]; then
  printf 'disabled services = {\n'
  printf '\t"com.openssh.sshd" => %s\n' "${FAKE_SSHD_DISABLED:-false}"
  printf '\t"com.apple.somethingelse" => false\n'
  printf '}\n'
  exit 0
fi
exit "${FAKE_LAUNCHCTL_RC:-0}"
EOF

cat > "$EBIN/nc" <<'EOF'
#!/bin/sh
exit "${FAKE_NC_RC:-0}"
EOF

# tail: a READ FAILURE seam. Passes straight through to the real tail unless
# FAKE_TAIL_FAIL=1. Modelling "the log could not be read" by other means is not
# portable: macOS `tail <dir>` exits 0 with empty output while GNU `tail <dir>`
# exits 1, and a chmod-000 file is readable anyway when the suite runs as root.
# A seam is the only way this case is exercised identically everywhere.
REAL_TAIL="$(command -v tail)"
cat > "$EBIN/tail" <<EOF
#!/bin/sh
if [ "\${FAKE_TAIL_FAIL:-0}" = "1" ]; then
  echo "tail: simulated read error" >&2
  exit 1
fi
exec "$REAL_TAIL" "\$@"
EOF
chmod +x "$EBIN/launchctl" "$EBIN/nc" "$EBIN/tail"

RESCUE_TEST_LABEL="com.blackceo.rescue-testbox"
: > "$EDAEMONS/${RESCUE_TEST_LABEL}.plist"

# write_window <lan-line-count> <registered-line-count>
write_window() {
    : > "$ELOGS/${RESCUE_TEST_LABEL}.err.log"
    : > "$ELOGS/${RESCUE_TEST_LABEL}.out.log"
    _i=0
    while [ "$_i" -lt "$1" ]; do
        echo "ERR connection error dialing edge 192.168.1.1:7844: connect: no route" \
            >> "$ELOGS/${RESCUE_TEST_LABEL}.err.log"
        _i=$((_i + 1))
    done
    _i=0
    while [ "$_i" -lt "$2" ]; do
        echo "INF Registered tunnel connection connIndex=0 location=iad" \
            >> "$ELOGS/${RESCUE_TEST_LABEL}.out.log"
        _i=$((_i + 1))
    done
}

# run_rtw [extra env assignments are inherited from the caller]
run_rtw() {
    : > "$LCLOG"
    PATH="$EBIN:$PATH" \
    LCLOG="$LCLOG" \
    RESCUE_WATCHDOG_DAEMON_DIR="$EDAEMONS" \
    RESCUE_WATCHDOG_LOG_DIR="$ELOGS" \
    RESCUE_WATCHDOG_STATE_DIR="$ESTATE" \
    bash "$RTW" 2>&1
}

# ---- 12f-h: 5 LAN dials, 0 registered -> KICK -------------------------------
write_window 5 0
rm -f "$ESTATE/rescue-watchdog.last-kick"
OUT12A="$(FAKE_SSHD_DISABLED=false run_rtw)"
echo "$OUT12A" | grep -q "STALE" \
    && pass "12f: 5 LAN dials + 0 registrations is classified STALE" \
    || fail "12f: the stale-connector signature was not detected"
grep -q "launchctl kickstart -k system/${RESCUE_TEST_LABEL}" "$LCLOG" \
    && pass "12g: the stale connector is KICKED (launchctl kickstart -k system/<label>)" \
    || fail "12g: no kickstart was issued for a provably stale connector"
[ -s "$ESTATE/rescue-watchdog.last-kick" ] \
    && pass "12h: the cooldown stamp is written after a kick" \
    || fail "12h: no cooldown stamp, so the next pass could storm"

# ---- 12i: the SAME condition inside the cooldown must NOT kick again ---------
OUT12B="$(FAKE_SSHD_DISABLED=false run_rtw)"
if grep -q "kickstart -k system/${RESCUE_TEST_LABEL}" "$LCLOG"; then
    fail "12i: the watchdog kicked again inside its own cooldown (restart storm)"
else
    pass "12i: a second pass inside the cooldown HOLDS instead of kicking again"
fi
echo "$OUT12B" | grep -q "HOLD" \
    && pass "12j: the hold is stated in the log, not silent" \
    || fail "12j: the cooldown hold was not logged"

# ---- 12k-l: CONTROL, 5 LAN dials but ONE registration -> NO kick -------------
# This is the control that proves 12g is a class-specific FAULT and not a
# class-specific TEST: same 5 LAN lines, one extra registered line, no action.
write_window 5 1
rm -f "$ESTATE/rescue-watchdog.last-kick"
OUT12C="$(FAKE_SSHD_DISABLED=false run_rtw)"
if grep -q "kickstart -k system/${RESCUE_TEST_LABEL}" "$LCLOG"; then
    fail "12k: a connector that DID register was kicked anyway"
else
    pass "12k: CONTROL, 5 LAN dials + 1 registration is NOT kicked"
fi
echo "$OUT12C" | grep -q "registered=1" \
    && pass "12l: the measured counts are printed, so the verdict is auditable" \
    || fail "12l: the watchdog did not print what it measured"

# ---- 12m-n: a count that cannot be established is UNDETERMINED, never zero ---
# The log window is present and FULL of the stale signature, but the read fails.
# A watchdog that read a failed measurement as 0 would draw a conclusion from
# nothing. This is the exact shape the negative-result contract forbids.
write_window 5 0
rm -f "$ESTATE/rescue-watchdog.last-kick"
OUT12D="$(FAKE_SSHD_DISABLED=false FAKE_TAIL_FAIL=1 run_rtw)"
echo "$OUT12D" | grep -q "undetermined" \
    && pass "12m: an unreadable log window reports UNDETERMINED" \
    || fail "12m: an unreadable log window did not report undetermined"
if grep -q "kickstart -k system/${RESCUE_TEST_LABEL}" "$LCLOG"; then
    fail "12n: the watchdog acted on a count it could not establish"
else
    pass "12n: UNDETERMINED takes NO action (a failed measurement is not a zero)"
fi
# CONTROL on the instrument: the SAME window, same box, read succeeding, DOES
# kick. Without this, 12n could be passing because the harness is broken.
OUT12D2="$(FAKE_SSHD_DISABLED=false run_rtw)"
grep -q "kickstart -k system/${RESCUE_TEST_LABEL}" "$LCLOG" \
    && pass "12n-control: the identical window WITH a readable log does kick (the harness is live)" \
    || fail "12n-control: the harness never kicks at all, so 12n proves nothing"

# ---- 12o: no rescue daemon on this box -> say so and exit 0 ------------------
mv "$EDAEMONS/${RESCUE_TEST_LABEL}.plist" "$E/plist.parked"
OUT12E="$(FAKE_SSHD_DISABLED=false run_rtw)"; RC12E=$?
echo "$OUT12E" | grep -q "no-rescue-daemon" \
    && pass "12o: a box with no rescue daemon logs no-rescue-daemon and exits 0" \
    || fail "12o: a box with no rescue daemon did not say so"
[ "$RC12E" -eq 0 ] \
    && pass "12p: that case exits 0 (it is not an error, it is a box without the daemon)" \
    || fail "12p: a box with no rescue daemon exited $RC12E"
mv "$E/plist.parked" "$EDAEMONS/${RESCUE_TEST_LABEL}.plist"

# ---- 12q: RESCUE_LABEL pins the label, including the cloudflared slot --------
write_window 5 0
rm -f "$ESTATE/rescue-watchdog.last-kick"
: > "$ELOGS/com.cloudflare.cloudflared.err.log"
_i=0
while [ "$_i" -lt 5 ]; do
    echo "ERR dialing edge 10.0.0.1:7844: connect: connection refused" \
        >> "$ELOGS/com.cloudflare.cloudflared.err.log"
    _i=$((_i + 1))
done
: > "$LCLOG"
PATH="$EBIN:$PATH" LCLOG="$LCLOG" \
  RESCUE_LABEL="com.cloudflare.cloudflared" \
  RESCUE_WATCHDOG_DAEMON_DIR="$EDAEMONS" \
  RESCUE_WATCHDOG_LOG_DIR="$ELOGS" \
  RESCUE_WATCHDOG_STATE_DIR="$ESTATE" \
  FAKE_SSHD_DISABLED=false \
  bash "$RTW" >/dev/null 2>&1
grep -q "kickstart -k system/com.cloudflare.cloudflared" "$LCLOG" \
    && pass "12q: RESCUE_LABEL pins the label (boxes whose rescue tunnel IS the cloudflared slot)" \
    || fail "12q: RESCUE_LABEL was ignored"

# ---- 12r-t: the sshd leg ----------------------------------------------------
write_window 0 1
rm -f "$ESTATE/rescue-watchdog.last-kick"
OUT12F="$(FAKE_SSHD_DISABLED=true FAKE_NC_RC=0 run_rtw)"
grep -q "launchctl enable system/com.openssh.sshd" "$LCLOG" \
    && pass "12r: a DISABLED sshd (authoritative print-disabled view) is re-enabled" \
    || fail "12r: sshd stayed disabled, so the box stays unreachable"
grep -q "launchctl kickstart -k system/com.openssh.sshd" "$LCLOG" \
    && pass "12s: sshd is kickstarted after the enable" \
    || fail "12s: sshd was enabled but never started"
echo "$OUT12F" | grep -q "VERIFIED" \
    && pass "12t: the listener is PROVEN with a real connection attempt (nc -z 127.0.0.1 22)" \
    || fail "12t: no connection attempt proved the listener"

# 12u: nc failing must be reported as NOT VERIFIED, never as success.
OUT12G="$(FAKE_SSHD_DISABLED=true FAKE_NC_RC=1 run_rtw)"
echo "$OUT12G" | grep -q "NOT VERIFIED" \
    && pass "12u: a failed listener probe is reported NOT VERIFIED, not smoothed over" \
    || fail "12u: a dead listener was not reported"

# 12v: CONTROL, sshd NOT disabled must be left completely alone.
OUT12H="$(FAKE_SSHD_DISABLED=false run_rtw)"
if grep -q "launchctl enable system/com.openssh.sshd" "$LCLOG"; then
    fail "12v: sshd was touched on a box where Remote Login is already on"
else
    pass "12v: CONTROL, an enabled sshd is left alone"
fi

# 12w: the shipped ssh.plist Disabled marker must never be the source of truth.
grep -q "print-disabled" "$RTW" \
    && pass "12w: the watchdog reads 'launchctl print-disabled system' (authoritative)" \
    || fail "12w: the watchdog does not use the authoritative disabled view"
if grep -qE '/System/Library/LaunchDaemons/ssh\.plist"' "$RTW"; then
    fail "12x: the watchdog READS Apple's ssh.plist Disabled marker (true even when Remote Login is ON)"
else
    pass "12x: Apple's ssh.plist Disabled default marker is never read as state"
fi

# ---- 12y-z: the installer and the plist are correctly shaped ----------------
grep -qE 'install -m 0755 -o root -g wheel' "$RTW_INSTALL" \
    && pass "12y: the installer lays the script down 0755 root:wheel" \
    || fail "12y: the installer does not install the script as root:wheel 0755"
grep -qE 'install -m 0644' "$RTW_INSTALL" \
    && pass "12z: the installer lays the plist down 0644" \
    || fail "12z: the installer does not install the plist 0644"
grep -q "bootstrap system" "$RTW_INSTALL" \
    && pass "12aa: the installer bootstraps into the SYSTEM domain (not gui/)" \
    || fail "12aa: the installer does not bootstrap a system-domain daemon"
grep -q '<integer>120</integer>' "$RTW_PLIST" \
    && pass "12ab: the LaunchDaemon runs every 120s" \
    || fail "12ab: StartInterval is not 120"
grep -q '/Library/BlackCEO/rescue-tunnel-watchdog.sh' "$RTW_PLIST" \
    && pass "12ac: the plist points at /Library/BlackCEO/rescue-tunnel-watchdog.sh" \
    || fail "12ac: the plist does not point at the installed script path"

# ---- 12ad-ae: WIRING, the installer is actually reachable -------------------
INSTALLER="$REPO_ROOT/install.sh"
UPDATER_E="$REPO_ROOT/update-skills.sh"
grep -q "install-rescue-tunnel-watchdog.sh" "$INSTALLER" \
    && pass "12ad: install.sh calls the Layer E installer (not dead code)" \
    || fail "12ad: install.sh never installs the rescue-tunnel watchdog"
grep -q "install-rescue-tunnel-watchdog.sh" "$UPDATER_E" \
    && pass "12ae: update-skills.sh calls the Layer E installer on its Mac leg" \
    || fail "12ae: update-skills.sh never installs the rescue-tunnel watchdog"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: $FAIL assertion(s) failed"
    exit 1
fi
echo "PASS: all assertions passed"
exit 0
