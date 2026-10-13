#!/usr/bin/env bash
# test-telegram-token-readers-default-account.sh (D26c)
#
# D26 removes the top-level channels.telegram.botToken when it equals
# accounts.default. Every reader of the Telegram bot token must therefore resolve
# like OpenClaw's resolveTelegramToken: accounts.<id>.tokenFile/botToken, then
# the top-level tokenFile/botToken, then (default account only)
# TELEGRAM_BOT_TOKEN. Post-D26 shape (no top-level token, no env var) must work
# in every reader; the legacy top-level-only shape must keep working.
# Fixture tokens are synthetic.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d 2>/dev/null || mktemp -d -t tgtok)"
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok()  { printf '  PASS  %s\n' "$*"; PASS=$((PASS + 1)); }
nope(){ printf '  FAIL  %s\n' "$*"; FAIL=$((FAIL + 1)); }
unset TELEGRAM_BOT_TOKEN
mkcfg() { H="$TMP/$1"; mkdir -p "$H/.openclaw"; CFG="$H/.openclaw/openclaw.json"; printf '%s' "$2" > "$CFG"; }

POST='{"channels":{"telegram":{"allowFrom":["999000111","888000222"],"accounts":{"default":{"botToken":"999000111:AAAAdefault"}}}}}'
LEGACY='{"channels":{"telegram":{"botToken":"999000111:AAAAlegacy","allowFrom":["999000111","888000222"]}}}'

echo "== every reader carries the identical resolver block =="
BLK="$(python3 - "$ROOT" <<'PYEOF'
import re, sys
root = sys.argv[1]
files = ["install.sh", "scripts/telegram-offset-healthcheck.sh", "scripts/ensure-pipeline-crons.sh",
         "shared-utils/resolve-owner-chat.sh", "38-conversational-ai-system/scripts/check-ghl-pit-liveness.sh",
         "44-convert-and-flow-operator/tools/check-ghl-token-liveness.sh"]
rx = re.compile(r"# D26c tg-token-resolve BEGIN.*?# D26c tg-token-resolve END\n", re.S)
blocks = {}
for f in files:
    found = rx.findall(open(f"{root}/{f}").read())
    want = 2 if f == "install.sh" else 1
    print(("PASS  " if len(found) == want else "FAIL  ") + f"{f}: {len(found)} resolver block(s), want {want}")
    for b in found: blocks[b] = 1
print(("PASS  " if len(blocks) == 1 else "FAIL  ") + f"resolver blocks identical ({len(blocks)} distinct)")
if len(blocks) == 1:
    open(sys.argv[1] + "/.tgtok_snippet.py", "w").write(next(iter(blocks)))
PYEOF
)"
while IFS= read -r l; do case "$l" in PASS*) ok "${l#PASS  }" ;; FAIL*) nope "${l#FAIL  }" ;; esac; done <<< "$BLK"
SN="$ROOT/.tgtok_snippet.py"

echo "== resolver block semantics =="
if [ -f "$SN" ]; then
  r() { python3 -c "
import json, os, sys
exec(open('$SN').read())
print(tg_token(json.loads(sys.argv[1]), *sys.argv[2:]))" "$@"; }
  [ "$(r "$POST")" = "999000111:AAAAdefault" ] && ok "post-D26 (accounts.default only) resolves" || nope "post-D26 shape"
  [ "$(r "$LEGACY")" = "999000111:AAAAlegacy" ] && ok "legacy top-level only resolves" || nope "legacy shape"
  [ "$(r '{"channels":{"telegram":{"botToken":"1:top","accounts":{"default":{"botToken":"2:acct"}}}}}')" = "2:acct" ] && ok "account beats top-level" || nope "account precedence"
  printf '3:file\n' > "$TMP/tok"
  [ "$(r '{"channels":{"telegram":{"accounts":{"default":{"tokenFile":"'"$TMP"'/tok","botToken":"2:acct"}}}}}')" = "3:file" ] && ok "account tokenFile beats account botToken" || nope "account tokenFile"
  [ "$(r '{"channels":{"telegram":{"tokenFile":"'"$TMP"'/tok"}}}')" = "3:file" ] && ok "top-level tokenFile resolves" || nope "top-level tokenFile"
  [ "$(TELEGRAM_BOT_TOKEN=4:env r '{"channels":{"telegram":{}}}')" = "4:env" ] && ok "env fallback for default" || nope "env fallback"
  [ -z "$(TELEGRAM_BOT_TOKEN=4:env r '{"channels":{"telegram":{}}}' operator)" ] && ok "no env fallback for non-default account" || nope "env leaked to operator"
else nope "no resolver block to test"; fi
rm -f "$SN"

echo "== resolve-owner-chat.sh: the bot id (from accounts.default) is never an owner chat =="
for shape in POST LEGACY; do
  mkcfg "roc$shape" "${!shape}"
  got="$(HOME="$H" bash -c 'source "$1"; resolve_owner_chat_id' _ "$ROOT/shared-utils/resolve-owner-chat.sh" 2>/dev/null)"
  [ "$got" = "888000222" ] && ok "$shape: skips the bot id, returns the next chat" || nope "$shape: got '$got' (want 888000222)"
done

echo "== install.sh tg_send_direct finds the token (no top-level token, no env var) =="
mkdir -p "$TMP/bin"
printf '#!/bin/sh\nfor a in "$@"; do echo "$a"; done > "$CURL_ARGS"\necho "{\\"ok\\":true}"\n' > "$TMP/bin/curl"; chmod +x "$TMP/bin/curl"
sed -n '/^tg_send_direct() {/,/^}/p' "$ROOT/install.sh" > "$TMP/fn.sh"
for shape in POST LEGACY; do
  mkcfg "send$shape" "${!shape}"
  export CURL_ARGS="$TMP/curl.$shape"; rm -f "$CURL_ARGS"
  HOME="$H" PATH="$TMP/bin:$PATH" LOG_FILE="$TMP/log" bash -c 'source "$1"; tg_send_direct hi' _ "$TMP/fn.sh" >/dev/null 2>&1
  grep -q '/bot999000111:AAAA' "$CURL_ARGS" 2>/dev/null && ok "$shape: direct send used the account token" || nope "$shape: no direct send"
done

echo "== telegram-offset-healthcheck.sh =="
printf '#!/bin/sh\nexit 7\n' > "$TMP/bin/curl"
skipped() { HOME="$H" PATH="$TMP/bin:$PATH" bash "$ROOT/scripts/telegram-offset-healthcheck.sh" </dev/null 2>&1 | grep -c "no telegram botToken"; }
mkcfg hcpost "$POST"; [ "$(skipped)" = 0 ] && ok "post-D26 shape seen" || nope "post-D26 shape skipped"
mkcfg hcleg "$LEGACY"; [ "$(skipped)" = 0 ] && ok "legacy shape seen" || nope "legacy shape skipped"
mkcfg hcnone '{"channels":{"telegram":{}}}'; [ "$(skipped)" = 1 ] && ok "control: no token anywhere still skips" || nope "control failed"

echo "passed=$PASS failed=$FAIL"
[ "$FAIL" -eq 0 ]
