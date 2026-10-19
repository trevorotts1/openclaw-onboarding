#!/usr/bin/env bash
# tests/unit/ghl-delivery-contabo-boot.test.sh
#
# GHL-163 — Contabo container boot-hook delivery family.
#
# Static + hermetic: the hook is parsed, never executed (executing it would
# start a gateway). Asserts:
#   1. the boot hook carries the retirement contract (GHL_MCP_RETIRED) and never
#      invokes the retired community MCP autostart/start scripts;
#   2. pm2 resurrection strips ghl-community-mcp BEFORE `pm2 resurrect`;
#   3. the MODERNIZED client is anchored on the persistent volume
#      ($OC/tools/convert-and-flow-cli) and the hook reports its readiness
#      without running it;
#   4. negative control: the scanner fails when a retired start is reintroduced.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$REPO/platform/vps/contabo/container-startup.sh"
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf 'PASS %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf 'FAIL %s\n' "$1" >&2; }
TMP="$(mktemp -d /tmp/operator-GHL-163-contabo.XXXXXX)" || exit 9
trap 'rm -rf "$TMP"' EXIT

[ -f "$HOOK" ] || { echo "missing $HOOK" >&2; exit 1; }

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

grep -q 'GHL_MCP_RETIRED' "$HOOK" && pass "contabo hook carries GHL_MCP_RETIRED" \
  || fail "contabo hook lost the retirement contract"

scan_retired "$HOOK" && pass "contabo hook never invokes the retired autostart/start script" \
  || fail "contabo hook contains a retired-server start"

# Resurrection must be guarded, and the guard must run first.
fn_line="$(awk '{ sub(/#.*/, "") } /pm2_dump_excludes_retired\(\)/ { print FNR; exit }' "$HOOK")"
call_line="$(awk '{ sub(/#.*/, "") } /if pm2_dump_excludes_retired/ { print FNR; exit }' "$HOOK")"
res_line="$(awk '{ sub(/#.*/, "") } /pm2 resurrect/ { print FNR; exit }' "$HOOK")"
if [ -n "$fn_line" ] && [ -n "$call_line" ] && [ -n "$res_line" ] && [ "$call_line" -lt "$res_line" ]; then
  pass "contabo hook strips the retired app before pm2 resurrect"
else
  fail "contabo hook resurrects pm2 without the retired-app strip"
fi
grep -q 'ghl\[-_\]community\[-_\]mcp' "$HOOK" \
  && pass "contabo strip matches the retired app name (ghl[-_]community[-_]mcp)" \
  || fail "contabo strip lost the retired app match"
grep -q 'pm2 resurrect skipped (fail closed)' "$HOOK" \
  && pass "contabo fails closed when the dump cannot be proven clean" \
  || fail "contabo lost the fail-closed resurrect branch"

# Modern client: persistent volume anchor + readiness report, never executed.
grep -q 'CAF_DIR="${CAF_DIR:-$OC/tools/convert-and-flow-cli}"' "$HOOK" \
  && pass "contabo anchors the modern client on the persistent volume (\$OC/tools/convert-and-flow-cli)" \
  || fail "contabo does not resolve the modern client install root"
grep -q '\[ghl\] modern client present' "$HOOK" \
  && pass "contabo boot reports modern client readiness" \
  || fail "contabo boot has no modern-client readiness report"
if sed 's/#.*$//' "$HOOK" | grep -Eq '\$CAF_DIR/(caf|convertandflow|ghl)[[:space:]]'; then
  fail "contabo boot EXECUTES the credentials-bearing client at boot"
else
  pass "contabo boot never executes the credentials-bearing client"
fi

# Negative control: force the retired autostart back into a copy.
cp "$HOOK" "$TMP/hook.sh"
printf '\nOPENCLAW_ROOT="$OC" bash "$OC/scripts/ghl-mcp-autostart.sh"\n' >> "$TMP/hook.sh"
if scan_retired "$TMP/hook.sh" >/dev/null; then
  fail "negative control: scanner did NOT catch a reintroduced autostart invocation"
else
  pass "negative control: scanner catches a reintroduced ghl-mcp-autostart invocation"
fi
cp "$HOOK" "$TMP/hook2.sh"
printf '\npm2 start ecosystem.config.js --only ghl-community-mcp\n' >> "$TMP/hook2.sh"
if scan_retired "$TMP/hook2.sh" >/dev/null; then
  fail "negative control: scanner did NOT catch a reintroduced pm2 start"
else
  pass "negative control: scanner catches a reintroduced pm2 start of the retired app"
fi

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" = 0 ]
