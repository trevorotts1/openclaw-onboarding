#!/usr/bin/env bash
# tests/unit/ghl-delivery-macos-launchd.test.sh
#
# GHL-163 — macOS launchd delivery-path family.
#
# Asserts, statically and hermetically (nothing is loaded, bootstrapped or
# started; no service on this box is touched):
#   1. every shipped LaunchAgent template under platform/mac is NOT a GHL
#      launch surface for the RETIRED community MCP;
#   2. install.sh carries the retirement contract (GHL_MCP_RETIRED) and never
#      bootstraps/kickstarts com.clawd.ghl-mcp;
#   3. the macOS path DELIVERS the MODERNIZED client: install.sh runs Skill 44's
#      root wire.sh, and the engine ships the caf/convertandflow/ghl entrypoints;
#   4. negative control: the scanner FAILS when a retired launchd start is
#      reintroduced into a temporary copy.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf 'PASS %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf 'FAIL %s\n' "$1" >&2; }
TMP="$(mktemp -d /tmp/operator-GHL-163-macos.XXXXXX)" || exit 9
trap 'rm -rf "$TMP"' EXIT

# A retired-server START is any of these on a non-comment line. A bare mention
# (documentation, a strip-before-resurrect filter) is not a start.
FORBIDDEN_RE='launchctl[[:space:]]+(bootstrap|kickstart|load)[^;|]*com\.clawd\.ghl-mcp|pm2[[:space:]]+(start|restart|startOrReload)[^;|]*(ghl-community-mcp|ghl-mcp)|systemctl[[:space:]]+(enable|start|restart)[^;|]*ghl-mcp|openclaw[[:space:]]+mcp[[:space:]]+set[^;|]*ghl-community-mcp|(bash|sh|zsh|exec|nohup|setsid|source)[[:space:]]+[^;|]*(ghl-mcp-autostart\.sh|start-ghl-mcp-server\.sh)|@reboot[^;|]*ghl'

# scan_retired <file> -> 0 clean, 1 hit (hits printed). --retire/--status are
# retirement operations, never a start.
scan_retired() {
  local f="$1" hits
  hits="$(sed 's/#.*$//' "$f" | grep -nE "$FORBIDDEN_RE" || true)"
  [ -n "$hits" ] || return 0
  hits="$(printf '%s\n' "$hits" | grep -vE -- '--retire|--status' || true)"
  [ -n "$hits" ] || return 0
  printf '%s\n' "$hits"
  return 1
}

# ---------------------------------------------------------------- 1. plists
PLISTS="$(find "$REPO/platform/mac" -name '*.plist.template' -type f 2>/dev/null | sort)"
[ -n "$PLISTS" ] && pass "launchd family present ($(printf '%s\n' "$PLISTS" | wc -l | tr -d ' ') templates)" \
  || fail "no LaunchAgent templates under platform/mac — macOS delivery family missing"

bad=0
while IFS= read -r p; do
  [ -n "$p" ] || continue
  scan_retired "$p" || { bad=1; fail "retired launchd start in ${p#$REPO/}"; }
  if grep -Eq 'com\.clawd\.ghl-mcp|ghl-community-mcp|start-ghl-mcp-server' "$p"; then
    bad=1; fail "${p#$REPO/} declares a retired GHL launch surface"
  fi
done <<EOF
$PLISTS
EOF
[ "$bad" = 0 ] && pass "no shipped LaunchAgent template starts or declares the RETIRED community MCP"

# ------------------------------------------------------------- 2. install.sh
INSTALL="$REPO/install.sh"
[ -f "$INSTALL" ] || { echo "missing $INSTALL" >&2; exit 1; }
grep -q 'GHL_MCP_RETIRED=1' "$INSTALL" && pass "install.sh carries the retirement marker (GHL_MCP_RETIRED=1)" \
  || fail "install.sh lost the retirement marker"
scan_retired "$INSTALL" && pass "install.sh never bootstraps/kickstarts the retired launchd label" \
  || fail "install.sh contains a retired launchd start"

# The retirement TOOL is the macOS removal surface; it must stay refusal-marked.
AUTOSTART="$REPO/scripts/ghl-mcp-autostart.sh"
if [ -f "$AUTOSTART" ]; then
  grep -qE 'GHL_MCP_RETIRED|START_REFUSED_RETIRED' "$AUTOSTART" \
    && pass "scripts/ghl-mcp-autostart.sh is a refusal-marked retirement tool" \
    || fail "scripts/ghl-mcp-autostart.sh ships without a retirement marker"
  grep -q -- '--retire' "$AUTOSTART" && pass "retirement tool exposes --retire (removes the old launchd unit)" \
    || fail "retirement tool lost --retire"
else
  pass "scripts/ghl-mcp-autostart.sh is retired (absent from the shipped tree)"
fi

# ------------------------------------------- 3. modernized client delivery
grep -q '44-convert-and-flow-operator' "$INSTALL" && grep -q 'wire\.sh' "$INSTALL" \
  && pass "install.sh runs Skill 44's root wire.sh (fresh-install delivery of the modernized client)" \
  || fail "install.sh does not run Skill 44 wire.sh — fresh macOS installs would ship no caf CLI"
for e in caf convertandflow ghl; do
  [ -f "$REPO/44-convert-and-flow-operator/tools/engine/$e" ] \
    && pass "modern client entrypoint ships: tools/engine/$e" \
    || fail "missing modern client entrypoint tools/engine/$e"
done
grep -q 'convert-and-flow-cli' "$REPO/44-convert-and-flow-operator/wire.sh" \
  && pass "wire.sh installs the client under the platform tools root" \
  || fail "wire.sh no longer declares the client install root"

# --------------------------------------------------------- 4. negative control
cp "$INSTALL" "$TMP/install.sh"
printf '\nlaunchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.clawd.ghl-mcp.plist"\n' >> "$TMP/install.sh"
if scan_retired "$TMP/install.sh" >/dev/null; then
  fail "negative control: scanner did NOT catch a reintroduced launchd start"
else
  pass "negative control: scanner catches a reintroduced com.clawd.ghl-mcp bootstrap"
fi
cp "$REPO/platform/mac/service-selfheal/com.openclaw.service-remediate.plist.template" "$TMP/bad.plist" 2>/dev/null || :
printf '%s\n' 'launchctl load -w ~/Library/LaunchAgents/com.clawd.ghl-mcp.plist' >> "$TMP/bad.plist"
if scan_retired "$TMP/bad.plist" >/dev/null; then
  fail "negative control: scanner did NOT catch a retired label added to a plist"
else
  pass "negative control: scanner catches a retired label added to a plist"
fi

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" = 0 ]
