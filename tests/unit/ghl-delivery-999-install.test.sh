#!/usr/bin/env bash
# tests/unit/ghl-delivery-999-install.test.sh
#
# GHL-163 — 999 install-path delivery family.
#
# The 999 path is the front door: update-skills.sh refreshes every installed
# 999-setup checkout (frontdoor_update_999 in shared-utils/lib-frontdoor.sh)
# before the shared repair/health stage. Asserts, statically and hermetically
# (no clone, no network, no install):
#   1. the 999 refresh is defined and called, in that order, by the updater;
#   2. the 999 path never installs or starts the RETIRED community MCP;
#   3. the same roll delivers the MODERNIZED client: the skill wiring loop runs
#      the skill-root wire.sh, and Skill 44's wire.sh builds caf;
#   4. the updater carries the ordered retirement transaction terminal states;
#   5. negative control: the scanner fails when a retired start is reintroduced.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATE="$REPO/update-skills.sh"
FD="$REPO/shared-utils/lib-frontdoor.sh"
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf 'PASS %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf 'FAIL %s\n' "$1" >&2; }
TMP="$(mktemp -d /tmp/operator-GHL-163-999.XXXXXX)" || exit 9
trap 'rm -rf "$TMP"' EXIT

[ -f "$UPDATE" ] || { echo "missing $UPDATE" >&2; exit 1; }
[ -f "$FD" ] || { echo "missing $FD" >&2; exit 1; }

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

# ------------------------------------------------- 1. the 999 refresh is wired
grep -q '^frontdoor_update_999()' "$FD" && pass "lib-frontdoor.sh defines frontdoor_update_999" \
  || fail "lib-frontdoor.sh lost frontdoor_update_999"
grep -q 'frontdoor_update_999' "$UPDATE" && pass "update-skills.sh calls the 999 refresh" \
  || fail "update-skills.sh no longer refreshes 999-setup"
u_call="$(grep -n 'frontdoor_update_999 ||' "$UPDATE" | head -1 | cut -d: -f1)"
s_call="$(grep -n 'frontdoor_run_stage "$_FRONTDOOR_STAGE_PY"' "$UPDATE" | head -1 | cut -d: -f1)"
if [ -n "$u_call" ] && [ -n "$s_call" ] && [ "$u_call" -lt "$s_call" ]; then
  pass "999 refresh runs BEFORE the shared repair/health stage"
else
  fail "999 refresh is missing or ordered after the shared stage (u=$u_call s=$s_call)"
fi

# ------------------------------------- 2. the 999 path never starts the retired
scan_retired "$FD" && pass "999 front door never starts the RETIRED community MCP" \
  || fail "999 front door contains a retired-server start"
if sed 's/#.*$//' "$FD" | grep -Eq 'ghl-community-mcp|ghl-mcp-autostart|start-ghl-mcp-server'; then
  fail "999 front door references a retired lifecycle script"
else
  pass "999 front door references no retired lifecycle script"
fi
grep -q 'installer never run' "$FD" \
  && pass "999 clone path stays links-only (installer never run)" \
  || fail "999 clone path no longer states the links-only contract"

# ---------------------------------- 3. same roll delivers the MODERNIZED client
grep -q 'SKILL_DIR/wire.sh' "$UPDATE" \
  && pass "update-skills.sh wiring loop runs the skill-root wire.sh first" \
  || fail "update-skills.sh lost the skill-root wire.sh priority"
grep -qE '44-\*|skill-44-convert-and-flow-cli' "$UPDATE" \
  && pass "update-skills.sh tracks Skill 44 (modernized GHL client)" \
  || fail "update-skills.sh no longer tracks Skill 44"
WIRE="$REPO/44-convert-and-flow-operator/wire.sh"
[ -f "$WIRE" ] || { fail "Skill 44 wire.sh missing"; }
if [ -f "$WIRE" ]; then
  grep -q 'pip install -e' "$WIRE" && pass "Skill 44 wire.sh installs the client (pip install -e)" \
    || fail "Skill 44 wire.sh no longer installs the client"
  grep -q 'convert-and-flow-cli' "$WIRE" && pass "Skill 44 wire.sh targets the client tools root" \
    || fail "Skill 44 wire.sh lost the client tools root"
fi

# --------------------------------------- 4. retirement transaction is complete
for token in GHL_MCP_RETIRED VERIFIED_OFF MIGRATION_FAILED; do
  grep -q "$token" "$UPDATE" && pass "updater carries retirement token $token" \
    || fail "updater lost retirement token $token"
done
grep -q -- '--retire' "$UPDATE" && pass "updater exposes the retirement entry point" \
  || fail "updater lost the retirement entry point"

# --------------------------------------------------------- 5. negative controls
cp "$FD" "$TMP/fd.sh"
printf '\nbash "$HOME/.openclaw/scripts/ghl-mcp-autostart.sh"\n' >> "$TMP/fd.sh"
if scan_retired "$TMP/fd.sh" >/dev/null; then
  fail "negative control: scanner did NOT catch an autostart added to the 999 path"
else
  pass "negative control: scanner catches an autostart added to the 999 path"
fi
cp "$UPDATE" "$TMP/update.sh"
printf '\npm2 start ecosystem.config.cjs --only ghl-community-mcp\n' >> "$TMP/update.sh"
if scan_retired "$TMP/update.sh" >/dev/null; then
  fail "negative control: scanner did NOT catch a pm2 start added to the updater"
else
  pass "negative control: scanner catches a pm2 start added to the updater"
fi

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" = 0 ]
