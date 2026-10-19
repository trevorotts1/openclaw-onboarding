#!/usr/bin/env bash
# tests/unit/ghl-delivery-installers.test.sh
#
# GHL-163 — the two root delivery paths: install.sh (fresh install) and
# update-skills.sh (weekly roll).
#
# Hermetic: both installers are parsed, never executed (running install.sh would
# mutate this box). Asserts:
#   1. install.sh DELIVERS the MODERNIZED client (runs Skill 44 root wire.sh and
#      checks the caf/convertandflow/ghl entrypoints);
#   2. update-skills.sh DELIVERS it through the skill-root wire.sh loop;
#   3. neither installer starts the RETIRED community MCP (only the retirement
#      tool's --retire/--status verbs may appear, and those are exempt);
#   4. the retirement transaction terminal states are present;
#   5. negative controls: the retired-start scanner FAILS on a reintroduced
#      start, and the modern-client check FAILS on a file with no delivery.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL="$REPO/install.sh"
UPDATE="$REPO/update-skills.sh"
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf 'PASS %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf 'FAIL %s\n' "$1" >&2; }
TMP="$(mktemp -d /tmp/operator-GHL-163-installers.XXXXXX)" || exit 9
trap 'rm -rf "$TMP"' EXIT

[ -f "$INSTALL" ] || { echo "missing $INSTALL" >&2; exit 1; }
[ -f "$UPDATE" ] || { echo "missing $UPDATE" >&2; exit 1; }

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

# has_client_delivery <file> -> 0 when the file actually runs Skill 44's root
# wire.sh and checks the installed entrypoints.
has_client_delivery() {
  local f="$1"
  grep -q '44-convert-and-flow-operator' "$f" || return 1
  grep -q 'CLI_WIRE\|SKILL_DIR/wire\.sh' "$f" || return 1
  grep -q 'wire\.sh' "$f" || return 1
  return 0
}

# ------------------------------------------------- 1. fresh install delivery
has_client_delivery "$INSTALL" \
  && pass "install.sh delivers the modernized client (Skill 44 root wire.sh)" \
  || fail "install.sh does not run Skill 44 wire.sh — fresh installs get no caf CLI"
grep -qE '\[ -x "\$CAF_DIR/caf" \]' "$INSTALL" \
  && pass "install.sh asserts the installed caf entrypoint" \
  || fail "install.sh does not assert the installed caf entrypoint"
grep -q 'convert-and-flow-cli' "$INSTALL" \
  && pass "install.sh resolves the platform client tools root" \
  || fail "install.sh does not resolve the client tools root"

# ------------------------------------------------ 2. update roll delivery
grep -q 'SKILL_DIR/wire\.sh' "$UPDATE" \
  && pass "update-skills.sh runs the skill-root wire.sh" \
  || fail "update-skills.sh lost the skill-root wire.sh loop"
grep -q '"$SKILL_DIR/install.sh"' "$UPDATE" \
  && pass "update-skills.sh keeps the install.sh fallback in the priority list" \
  || fail "update-skills.sh lost the install.sh fallback"
[ -f "$REPO/44-convert-and-flow-operator/wire.sh" ] \
  && pass "Skill 44 root wire.sh ships (the loop's first match)" \
  || fail "Skill 44 root wire.sh missing"

# ------------------------------------- 3. no retired start in either installer
scan_retired "$INSTALL" && pass "install.sh never starts the retired community MCP" \
  || fail "install.sh contains a retired-server start"
scan_retired "$UPDATE" && pass "update-skills.sh never starts the retired community MCP" \
  || fail "update-skills.sh contains a retired-server start"
grep -q 'GHL_MCP_RETIRED=1' "$INSTALL" && pass "install.sh carries the retirement marker" \
  || fail "install.sh lost the retirement marker"
grep -q 'GHL_MCP_RETIRED' "$UPDATE" && pass "update-skills.sh references the retirement contract" \
  || fail "update-skills.sh lost the retirement contract"

# --------------------------------------- 4. retirement transaction completeness
for token in VERIFIED_OFF MIGRATION_FAILED; do
  grep -q "$token" "$UPDATE" && pass "update-skills.sh can reach terminal state $token" \
    || fail "update-skills.sh lost terminal state $token"
done

# --------------------------------------------------------- 5. negative controls
cp "$INSTALL" "$TMP/install.sh"
printf '\nbash scripts/ghl-mcp-autostart.sh\n' >> "$TMP/install.sh"
if scan_retired "$TMP/install.sh" >/dev/null; then
  fail "negative control: scanner did NOT catch a retired start in install.sh"
else
  pass "negative control: scanner catches a retired start reintroduced in install.sh"
fi
cp "$UPDATE" "$TMP/update.sh"
printf '\nopenclaw mcp set ghl-community-mcp /tmp/server.js\n' >> "$TMP/update.sh"
if scan_retired "$TMP/update.sh" >/dev/null; then
  fail "negative control: scanner did NOT catch a retired MCP registration in the updater"
else
  pass "negative control: scanner catches a retired MCP registration in the updater"
fi

# The positive check must discriminate: a file with the phrase but no wire.sh
# invocation is NOT delivery.
printf 'echo 44-convert-and-flow-operator\n' > "$TMP/no-delivery.sh"
if has_client_delivery "$TMP/no-delivery.sh"; then
  fail "negative control: modern-client check accepted a file that runs no wire.sh"
else
  pass "negative control: modern-client check rejects a file that runs no wire.sh"
fi

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" = 0 ]
