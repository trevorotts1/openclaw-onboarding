#!/usr/bin/env bash
# test-operator-telegram-same-as-client-bot.sh (D12)
#
# configure-operator-telegram.sh must never give the operator account the same
# bot as this box's own client bot (accounts.default / legacy botToken):
# OpenClaw 2026.10.1 rejects it ("Duplicate Telegram bot token"). Equal bot ids
# -> operator botToken "", no operator binding, STATUS REFUSED_SAME_AS_CLIENT_BOT.
# Different ids -> token written, CONFIGURED. Fixture tokens are synthetic.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPTG="$SCRIPT_DIR/configure-operator-telegram.sh"
TMP="$(mktemp -d 2>/dev/null || mktemp -d -t optgsame)"
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok()  { printf '  PASS  %s\n' "$*"; PASS=$((PASS + 1)); }
nope(){ printf '  FAIL  %s\n' "$*"; FAIL=$((FAIL + 1)); }

# run_case NAME DEFAULT_TOKEN LEGACY_TOKEN ENV_TOKEN EXISTING_OPERATOR_TOKEN -> sets OUT, CFG
run_case() {
  local name="$1" dtok="$2" ltok="$3" etok="$4" otok="$5" h="$TMP/$1"
  mkdir -p "$h/.openclaw"; CFG="$h/.openclaw/openclaw.json"
  DT="$dtok" LT="$ltok" OT="$otok" CFG="$CFG" python3 - <<'PY'
import json, os
tg = {"accounts": {"default": {"dmPolicy": "pairing"}}}
if os.environ["DT"]: tg["accounts"]["default"]["botToken"] = os.environ["DT"]
if os.environ["LT"]: tg["botToken"] = os.environ["LT"]
if os.environ["OT"]: tg["accounts"]["operator"] = {"botToken": os.environ["OT"]}
json.dump({"channels": {"telegram": tg}}, open(os.environ["CFG"], "w"))
PY
  OUT="$(HOME="$h" OPERATOR_TELEGRAM_BOT_TOKEN="$etok" bash "$OPTG" 2>&1)"
}
optok() { python3 -c "import json,sys;print(json.load(open('$CFG'))['channels']['telegram']['accounts']['operator']['botToken'])"; }
has_binding() { python3 -c "import json;print(any(b.get('match',{}).get('accountId')=='operator' for b in json.load(open('$CFG')).get('bindings',[])))"; }
leaks() { printf '%s' "$OUT" | grep -q 'secretA\|secretB'; }

[ -x /bin/bash ] && { /bin/bash -n "$OPTG" 2>/dev/null && ok "parses under /bin/bash (3.2 on macOS)" || nope "does not parse under /bin/bash"; }

echo "== equal bot id (env token == accounts.default) =="
run_case eq 111:secretA "" 111:secretA ""
[ "$(optok)" = "" ] && ok "operator botToken empty" || nope "operator botToken not empty"
printf '%s' "$OUT" | grep -q 'STATUS: operator-telegram=REFUSED_SAME_AS_CLIENT_BOT' && ok "REFUSED status printed" || nope "no REFUSED status"
[ "$(has_binding)" = "False" ] && ok "no operator binding" || nope "operator binding written"
leaks && nope "token secret printed" || ok "no secret printed"

echo "== equal bot id (env token == legacy channels.telegram.botToken) =="
run_case legacy "" 222:secretA 222:secretB ""
[ "$(optok)" = "" ] && ok "operator botToken empty" || nope "operator botToken not empty"
printf '%s' "$OUT" | grep -q 'REFUSED_SAME_AS_CLIENT_BOT' && ok "REFUSED status printed" || nope "no REFUSED status"

echo "== equal bot id (operator token already in config is blanked) =="
run_case existing 333:secretA "" "" 333:secretB
[ "$(optok)" = "" ] && ok "existing duplicate operator token blanked" || nope "existing duplicate kept"
printf '%s' "$OUT" | grep -q 'REFUSED_SAME_AS_CLIENT_BOT' && ok "REFUSED status printed" || nope "no REFUSED status"

echo "== different bot id =="
run_case diff 111:secretA "" 999:secretB ""
[ "$(optok)" = "999:secretB" ] && ok "operator token written" || nope "operator token not written"
printf '%s' "$OUT" | grep -q 'REFUSED_SAME_AS_CLIENT_BOT' && nope "wrongly refused" || ok "not refused"
printf '%s' "$OUT" | grep -q 'STATUS: operator-telegram=CONFIGURED' && ok "CONFIGURED status" || nope "no CONFIGURED status"
[ "$(has_binding)" = "True" ] && ok "operator binding written" || nope "operator binding missing"

echo "== no operator token at all =="
run_case none 111:secretA "" "" ""
printf '%s' "$OUT" | grep -q 'STRUCTURE_ONLY_NEEDS_TOKEN' && ok "unchanged STRUCTURE_ONLY status" || nope "status changed"

echo "passed=$PASS failed=$FAIL"
[ "$FAIL" -eq 0 ]
