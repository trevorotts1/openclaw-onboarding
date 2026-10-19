#!/usr/bin/env bash
# tests/unit/ghl-delivery-vps-pm2-systemd.test.sh
#
# GHL-163 — VPS PM2 / systemd delivery-path family.
#
# Hermetic: no pm2, systemd, launchctl or gateway command is invoked. The only
# executed file is the INERT tombstone under a throwaway HOME (it prints and
# exits 69; it writes nothing).
#
# Asserts:
#   1. no shipped PM2 ecosystem / systemd unit declares or starts the RETIRED
#      community MCP;
#   2. the tombstone refuses with the retirement marker (exit 69), so no caller
#      can read it as "started";
#   3. boot-time resurrection is guarded: dump.pm2 is stripped BEFORE resurrect;
#   4. the MODERNIZED client is delivered to the persistent tools root by the
#      same updater (Skill 44 wire.sh), and its entrypoints ship;
#   5. negative control: the scanner fails when a retired pm2/systemd start is
#      reintroduced.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf 'PASS %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf 'FAIL %s\n' "$1" >&2; }
TMP="$(mktemp -d /tmp/operator-GHL-163-vps.XXXXXX)" || exit 9
trap 'rm -rf "$TMP"' EXIT

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

# ------------------------------------- 1. no retired PM2/systemd definition
UNITS="$(find "$REPO" -path "$REPO/.git" -prune -o -type f \
  \( -name 'ecosystem*.js' -o -name 'ecosystem*.cjs' -o -name 'ecosystem*.json' \
     -o -name '*.service' -o -name '*.timer' \) -print 2>/dev/null | sort)"
bad=0
if [ -n "$UNITS" ]; then
  while IFS= read -r u; do
    [ -n "$u" ] || continue
    if grep -Eq 'ghl-community-mcp|ghl-mcp\.service|start-ghl-mcp-server|ghl-mcp-autostart' "$u"; then
      bad=1; fail "${u#$REPO/} declares the RETIRED community MCP"
    fi
  done <<EOF
$UNITS
EOF
fi
[ "$bad" = 0 ] && pass "no shipped PM2 ecosystem or systemd unit declares the RETIRED community MCP"

# ------------------------------------------------- 2. tombstone refuses loudly
TOMB="$REPO/platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh"
[ -f "$TOMB" ] || { echo "missing $TOMB" >&2; exit 1; }
grep -q 'GHL_MCP_RETIRED=1' "$TOMB" && pass "tombstone carries GHL_MCP_RETIRED=1" \
  || fail "tombstone lost the retirement marker"
out="$(HOME="$TMP/home" bash "$TOMB" 2>&1)"; rc=$?
[ "$rc" = 69 ] && pass "tombstone exits 69 (EX_UNAVAILABLE), never 0 = started" \
  || fail "tombstone exit was $rc, expected 69"
printf '%s' "$out" | grep -q 'RETIRED' && pass "tombstone output names the retirement" \
  || fail "tombstone output does not name the retirement"
printf '%s' "$out" | grep -q 'Do not add a start or restart path back' \
  && pass "tombstone states the no-restart contract" \
  || fail "tombstone lost its explicit no-restart contract"

# ------------------------------------------- 3. strip-before-resurrect guard
for hook in "$REPO/platform/vps/contabo/container-startup.sh" \
            "$REPO/platform/vps/hostinger/container-startup.sh"; do
  [ -f "$hook" ] || { fail "missing boot hook ${hook#$REPO/}"; continue; }
  fn_line="$(awk '{ sub(/#.*/, "") } /pm2_dump_excludes_retired\(\)/ { print FNR; exit }' "$hook")"
  call_line="$(awk '{ sub(/#.*/, "") } /if pm2_dump_excludes_retired/ { print FNR; exit }' "$hook")"
  res_line="$(awk '{ sub(/#.*/, "") } /pm2 resurrect/ { print FNR; exit }' "$hook")"
  { [ -n "$fn_line" ] && [ -n "$call_line" ] && [ "$call_line" -lt "$res_line" ]; } \
    && pass "${hook#$REPO/}: strip-before-resurrect guard runs before pm2 resurrect" \
    || fail "${hook#$REPO/}: pm2 resurrect is not guarded by the retired-app strip"
  grep -q 'GHL_MCP_RETIRED' "$hook" && pass "${hook#$REPO/}: carries the retirement contract" \
    || fail "${hook#$REPO/}: no GHL_MCP_RETIRED marker"
done

# ------------------------------------------ 4. modernized client delivery
grep -q 'wire.sh' "$REPO/update-skills.sh" \
  && pass "update-skills.sh runs the skill-root wire.sh delivery loop" \
  || fail "update-skills.sh lost the skill-root wire.sh loop"
[ -f "$REPO/44-convert-and-flow-operator/wire.sh" ] \
  && pass "Skill 44 root wire.sh ships" \
  || fail "Skill 44 root wire.sh missing — modern client never rebuilt on VPS"
grep -q '/data/.openclaw/tools/convert-and-flow-cli' "$REPO/44-convert-and-flow-operator/wire.sh" \
  && pass "wire.sh targets the VPS persistent tools root /data/.openclaw/tools/convert-and-flow-cli" \
  || fail "wire.sh lost the VPS tools root"
for e in caf convertandflow ghl; do
  [ -f "$REPO/44-convert-and-flow-operator/tools/engine/$e" ] \
    || fail "missing modern client entrypoint tools/engine/$e"
done
[ -f "$REPO/44-convert-and-flow-operator/tools/engine/convertandflow" ] \
  && [ -f "$REPO/44-convert-and-flow-operator/tools/engine/ghl" ] \
  && pass "modern client entrypoints ship (caf / convertandflow / ghl)"

# --------------------------------------------------------- 5. negative controls
cat > "$TMP/ecosystem.bad.cjs" <<'JS'
module.exports = { apps: [{ name: "ghl-community-mcp", script: "server.js" }] }
JS
cat > "$TMP/start.bad.sh" <<'SH'
pm2 start ecosystem.config.cjs --only ghl-community-mcp
systemctl enable --now ghl-mcp.service
SH
if scan_retired "$TMP/start.bad.sh" >/dev/null; then
  fail "negative control: scanner did NOT catch a reintroduced pm2/systemd start"
else
  pass "negative control: scanner catches reintroduced pm2 and systemd starts"
fi
grep -Eq 'ghl-community-mcp|ghl-mcp\.service' "$TMP/ecosystem.bad.cjs" \
  && pass "negative control: unit-declaration check catches a retired app name" \
  || fail "negative control: unit-declaration check missed a retired app name"

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" = 0 ]
