#!/usr/bin/env bash
# U042 — presentation-routing helper requester payload guard
set -uo pipefail
PASS=0;FAIL=0;ERRORS=()
ok(){ echo "  PASS: $1";PASS=$((PASS+1)); }
fail(){ echo "  FAIL: $1";FAIL=$((FAIL+1));ERRORS+=("$1"); }
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.."&&pwd)"
GENERATOR="$REPO_ROOT/scripts/apply-fleet-standards.sh"
echo;echo "=== route-presentation.sh requester payload guard (U042) ===";echo
[! -f "$GENERATOR"]&&{echo "FAIL: generator not found";exit 1;}
PYBODY="$(python3 - "$GENERATOR" <<'XT'
import re,sys
s=open(sys.argv[1]).read()
h=re.search(r"<<'ROUTE_HELPER_SH'\n(.*?)\nROUTE_HELPER_SH\n",s,re.S)
assert h,"ROUTE_HELPER_SH not found"
p=re.search(r"<<'PYBODY'\n(.*?)\nPYBODY\n",h.group(1),re.S)
assert p,"PYBODY not found"
sys.stdout.write(p.group(1))
XT
)"
W=$(mktemp -d /tmp/rpt.XXXXXX);trap 'rm -rf "$W"' EXIT
printf '%s\n' "$PYBODY">"$W/payload.py"
run(){ TITLE="$1" DESCRIPTION="$2" REQUESTER_CHAT_ID="${3:-}" REQUESTER_CHANNEL="${4:-}" python3 "$W/payload.py"</dev/null 2>/dev/null||echo "";}
echo "--- (A) no chat id -> omitted ---"
b="$(run "deck title" "deck desc")"
[ -z "$b" ]&&{ fail "(A) no output";}||{ printf '%s' "$b"|python3 -c "import json,sys;d=json.load(sys.stdin);assert 'requester_chat_id' not in d" 2>/dev/null&&ok "(A) omitted"||fail "(A) must omit: $b";}
echo "--- (B) chat id set -> passed through ---"
b="$(run "x" "x" "987654321")"
[ -z "$b" ]&&{ fail "(B) no output";}||{ printf '%s' "$b"|python3 -c "import json,sys;d=json.load(sys.stdin);assert d.get('requester_chat_id')=='987654321';assert d.get('requester_channel')=='telegram'" 2>/dev/null&&{ ok "(B) chat_id";ok "(B) channel=telegram";}||fail "(B) expected: $b";}
echo "--- (C) explicit channel ---"
b="$(run "x" "x" "111" "ceo-chat")"
[ -z "$b" ]&&{ fail "(C) no output";}||{ printf '%s' "$b"|python3 -c "import json,sys;d=json.load(sys.stdin);assert d.get('requester_channel')=='ceo-chat'" 2>/dev/null&&ok "(C) channel passes"||fail "(C) fail: $b";}
echo "--- (D) whitespace-only -> omitted ---"
b="$(run "x" "x" "   ")"
[ -z "$b" ]&&{ fail "(D) no output";}||{ printf '%s' "$b"|python3 -c "import json,sys;d=json.load(sys.stdin);assert 'requester_chat_id' not in d" 2>/dev/null&&ok "(D) stripped"||fail "(D) must strip: $b";}
echo;echo "=== $PASS passed, $FAIL failed ==="
[ "$FAIL" -gt 0 ]&&{ echo;echo "Failures:";for e in "${ERRORS[@]}";do echo "  - $e";done;exit 1;}
exit 0
