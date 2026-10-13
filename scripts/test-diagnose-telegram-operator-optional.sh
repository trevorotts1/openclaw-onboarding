#!/usr/bin/env bash
# test-diagnose-telegram-operator-optional.sh (D26b)
#
# After D26, configure-operator-telegram.sh creates NO accounts.operator when no
# operator bot token is provisioned, and drops the top-level channels.telegram
# botToken once accounts.default holds it. The checks that read that config must
# agree: operator absent = PASS (+ info note), operator with its own token =
# PASS, operator that resolves to the client bot = FAIL, top-level botToken
# absent while accounts.default has one = PASS. Fixture tokens are synthetic.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPTG="$SCRIPT_DIR/configure-operator-telegram.sh"
DIAG="$SCRIPT_DIR/diagnose-telegram-config.sh"
HEAL="$SCRIPT_DIR/telegram-offset-healthcheck.sh"
TMP="$(mktemp -d 2>/dev/null || mktemp -d -t diagopt)"
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok()  { printf '  PASS  %s\n' "$*"; PASS=$((PASS + 1)); }
nope(){ printf '  FAIL  %s\n' "$*"; FAIL=$((FAIL + 1)); }

# mkcfg NAME JSON -> sets H, CFG
mkcfg() { H="$TMP/$1"; mkdir -p "$H/.openclaw"; CFG="$H/.openclaw/openclaw.json"; printf '%s' "$2" > "$CFG"; }
diag() { OUT="$(HOME="$H" bash "$DIAG" 2>&1)"; }
nfail() { printf '%s\n' "$OUT" | sed -n '/Operator channel separation/,$p' | grep -c '✗ FAIL'; }

echo "== operator not provisioned: configure output (no operator, no top-level token) =="
mkcfg none '{"channels":{"telegram":{"botToken":"111:secretA","allowFrom":["42"]}}}'
HOME="$H" OPERATOR_TELEGRAM_BOT_TOKEN= bash "$OPTG" >/dev/null 2>&1
diag
[ "$(nfail)" = "0" ] && ok "no FAIL line" || { nope "FAIL lines on a no-operator box"; printf '%s\n' "$OUT" | grep '✗ FAIL'; }
printf '%s' "$OUT" | grep -q 'STRUCTURE_ONLY_NEEDS_TOKEN' && ok "informational note printed" || nope "no informational note"
printf '%s' "$OUT" | grep -q 'accounts.operator (OPERATOR bot) present' && nope "still requires accounts.operator" || ok "accounts.operator not required"

echo "== operator with its own token (configure output) =="
mkcfg own '{"channels":{"telegram":{"botToken":"111:secretA","allowFrom":["42"]}}}'
HOME="$H" OPERATOR_TELEGRAM_BOT_TOKEN=999:secretB bash "$OPTG" >/dev/null 2>&1
diag
[ "$(nfail)" = "0" ] && ok "no FAIL line" || { nope "FAIL lines on a distinct-operator box"; printf '%s\n' "$OUT" | grep '✗ FAIL'; }

echo "== operator empty, top-level fallback to the client bot (the D26 duplicate bug) =="
mkcfg dupempty '{"channels":{"telegram":{"botToken":"111:secretA","defaultAccount":"default","accounts":{"default":{"botToken":"111:secretA"},"operator":{"botToken":"","dmPolicy":"allowlist"}}}}}'
diag
printf '%s\n' "$OUT" | grep -q '✗ FAIL  operator bot differs from the CLIENT bot' && ok "duplicate flagged FAIL" || nope "duplicate not flagged"

echo "== operator token equals the client bot =="
mkcfg dupeq '{"channels":{"telegram":{"defaultAccount":"default","accounts":{"default":{"botToken":"111:secretA"},"operator":{"botToken":"111:secretB","dmPolicy":"allowlist"}}}}}'
diag
printf '%s\n' "$OUT" | grep -q '✗ FAIL  operator bot differs from the CLIENT bot' && ok "equal bot id flagged FAIL" || nope "equal bot id not flagged"

echo "== top-level botToken absent, accounts.default has a token =="
mkcfg notop '{"channels":{"telegram":{"defaultAccount":"default","accounts":{"default":{"botToken":"111:secretA","allowFrom":["42"]}}}}}'
diag
[ "$(nfail)" = "0" ] && ok "no FAIL line" || nope "FAIL lines when only the top-level token is absent"

echo "== diagnostic never prints a bot token =="
mkcfg leak '{"channels":{"telegram":{"botToken":"111:secretAAA","allowFrom":["42"],"accounts":{"default":{"botToken":"111:secretAAA"},"operator":{"botToken":"999:secretBBB"}}}}}'
diag
printf '%s' "$OUT" | grep -qE 'secretAAA|secretBBB' && nope "bot token printed" || ok "no bot token in output"

echo "== telegram-offset-healthcheck.sh finds the token in accounts.default =="
mkdir -p "$TMP/bin"; printf '#!/bin/sh\nexit 7\n' > "$TMP/bin/curl"; chmod +x "$TMP/bin/curl"
mkcfg hc '{"channels":{"telegram":{"accounts":{"default":{"botToken":"111:secretA"}}}}}'
OUT="$(HOME="$H" PATH="$TMP/bin:$PATH" bash "$HEAL" 2>&1)"
printf '%s' "$OUT" | grep -q 'no telegram botToken' && nope "healthcheck skips a box with only accounts.default.botToken" || ok "healthcheck sees accounts.default.botToken"
mkcfg hc0 '{"channels":{"telegram":{}}}'
OUT="$(HOME="$H" PATH="$TMP/bin:$PATH" bash "$HEAL" 2>&1)"
printf '%s' "$OUT" | grep -q 'no telegram botToken' && ok "control: a box with no token anywhere still skips" || nope "control failed"

echo "passed=$PASS failed=$FAIL"
[ "$FAIL" -eq 0 ]
