#!/usr/bin/env bash
# tests/unit/ghl-delivery-hostinger-boot.test.sh
#
# GHL-163 — Hostinger boot-hook delivery family.
#
# Static + hermetic: neither the container startup script nor the host installer
# is executed. Asserts:
#   1. the boot hook carries the retirement contract and never invokes the
#      retired community MCP autostart/start scripts;
#   2. pm2 resurrection strips ghl-community-mcp BEFORE `pm2 resurrect`;
#   3. the host installer wires the hook into compose without ever copying or
#      launching the retired server;
#   4. the MODERNIZED client is anchored on the persistent /data mount and the
#      boot hook reports readiness without executing it;
#   5. negative control: the scanner fails when a retired start is reintroduced.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$REPO/platform/vps/hostinger/container-startup.sh"
INSTALLER="$REPO/platform/vps/hostinger/install-startup-hook.sh"
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf 'PASS %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf 'FAIL %s\n' "$1" >&2; }
TMP="$(mktemp -d /tmp/operator-GHL-163-hostinger.XXXXXX)" || exit 9
trap 'rm -rf "$TMP"' EXIT

[ -f "$HOOK" ] || { echo "missing $HOOK" >&2; exit 1; }
[ -f "$INSTALLER" ] || { echo "missing $INSTALLER" >&2; exit 1; }

FORBIDDEN_RE='launchctl[[:space:]]+(bootstrap|kickstart|load)[^;|]*com\.clawd\.ghl-mcp|pm2[[:space:]]+(start|restart|startOrReload)[^;|]*(ghl-community-mcp|ghl-mcp)|systemctl[[:space:]]+(enable|start|restart)[^;|]*ghl-mcp|openclaw[[:space:]]+mcp[[:space:]]+set[^;|]*ghl-community-mcp|(bash|sh|zsh|exec|nohup|setsid|source)[[:space:]]+[^;|]*(ghl-mcp-autostart\.sh|start-ghl-mcp-server\.sh)|@reboot[^;|]*ghl'

scan_retired() {
  local f="$1" hits
  hits="$(sed 's/#.*$//' "$f" | grep -nE "$FORBIDDEN_RE" || true)"
  [ -n "$hits" ] || return 0
  hits="$(printf '%s\n' "$hits" | grep -vE -- '--retire|--status' || true)"
  [ -n "$hits" ] || return 0
  printf '%s\n' "$hits"
  return 1
}

grep -q 'GHL_MCP_RETIRED' "$HOOK" && pass "hostinger hook carries GHL_MCP_RETIRED" \
  || fail "hostinger hook lost the retirement contract"

scan_retired "$HOOK" && pass "hostinger hook never invokes the retired autostart/start script" \
  || fail "hostinger hook contains a retired-server start"

fn_line="$(awk '{ sub(/#.*/, "") } /pm2_dump_excludes_retired\(\)/ { print FNR; exit }' "$HOOK")"
call_line="$(awk '{ sub(/#.*/, "") } /if pm2_dump_excludes_retired/ { print FNR; exit }' "$HOOK")"
res_line="$(awk '{ sub(/#.*/, "") } /pm2 resurrect/ { print FNR; exit }' "$HOOK")"
if [ -n "$fn_line" ] && [ -n "$call_line" ] && [ -n "$res_line" ] && [ "$call_line" -lt "$res_line" ]; then
  pass "hostinger hook strips the retired app before pm2 resurrect"
else
  fail "hostinger hook resurrects pm2 without the retired-app strip"
fi
grep -q 'ghl\[-_\]community\[-_\]mcp' "$HOOK" \
  && pass "hostinger strip matches the retired app name (ghl[-_]community[-_]mcp)" \
  || fail "hostinger strip lost the retired app match"
grep -q 'pm2 resurrect skipped (fail closed)' "$HOOK" \
  && pass "hostinger fails closed when the dump cannot be proven clean" \
  || fail "hostinger lost the fail-closed resurrect branch"

# Host installer: wires container-startup.sh into compose, copies only the
# current support scripts, never the retired server.
scan_retired "$INSTALLER" && pass "install-startup-hook.sh never starts the retired server" \
  || fail "install-startup-hook.sh contains a retired-server start"
grep -q 'container-startup\.sh' "$INSTALLER" && pass "host installer wires container-startup.sh" \
  || fail "host installer lost the container-startup.sh hook"
grep -q 'ghl-community-mcp' "$INSTALLER" \
  && pass "host installer documents the retired-app strip (never restores it)" \
  || fail "host installer no longer documents the retired-app strip"

# Modern client on the persistent /data mount; report readiness, do not run it.
grep -q 'CAF_DIR="${CAF_DIR:-$DATA/.openclaw/tools/convert-and-flow-cli}"' "$HOOK" \
  && pass "hostinger anchors the modern client on persistent /data" \
  || fail "hostinger does not resolve the modern client install root"
grep -q '\[ghl\] modern client present' "$HOOK" \
  && pass "hostinger boot reports modern client readiness" \
  || fail "hostinger boot has no modern-client readiness report"
if sed 's/#.*$//' "$HOOK" | grep -Eq '\$CAF_DIR/(caf|convertandflow|ghl)[[:space:]]'; then
  fail "hostinger boot EXECUTES the credentials-bearing client at boot"
else
  pass "hostinger boot never executes the credentials-bearing client"
fi

# Negative controls.
cp "$INSTALLER" "$TMP/install.sh"
printf '\nbash "$DATA/.openclaw/scripts/ghl-mcp-autostart.sh"\n' >> "$TMP/install.sh"
if scan_retired "$TMP/install.sh" >/dev/null; then
  fail "negative control: scanner did NOT catch an autostart copied into the host installer"
else
  pass "negative control: scanner catches an autostart invocation in the host installer"
fi
cp "$HOOK" "$TMP/hook.sh"
printf '\npm2 start ecosystem.config.cjs --only ghl-community-mcp\n' >> "$TMP/hook.sh"
if scan_retired "$TMP/hook.sh" >/dev/null; then
  fail "negative control: scanner did NOT catch a reintroduced pm2 start"
else
  pass "negative control: scanner catches a reintroduced pm2 start of the retired app"
fi

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" = 0 ]
