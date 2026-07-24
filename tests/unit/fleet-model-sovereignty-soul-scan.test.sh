#!/usr/bin/env bash
# tests/unit/fleet-model-sovereignty-soul-scan.test.sh
# U123: Fleet-wide model-sovereignty SOUL.md scanning behavioral tests.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE_PY="$REPO_ROOT/shared-utils/assert_model_sovereignty.py"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
echo "=== fleet-model-sovereignty-soul-scan.test.sh ==="; echo ""
[ -f "$GATE_PY" ] || { echo "FATAL: $GATE_PY not found"; exit 1; }

# (a) scan_agent_soul_files finds Anthropic in dept-*/SOUL.md
echo "--- Test A: scan_agent_soul_files finds Anthropic refs ---"
A="$(mktemp -d)"
trap 'rm -rf "$A" 2>/dev/null || true' EXIT
ws="$A/workspace"; mkdir -p "$ws/departments/"{graphics,audio,video} "$A/.openclaw"
printf 'Uses anthropic/claude-5-sonnet\n' > "$ws/departments/graphics/SOUL.md"
printf 'Uses openai/gpt-4o\n' > "$ws/departments/audio/SOUL.md"
printf 'us.anthropic.claude-opus-4 + openrouter/anthropic/opus\n' > "$ws/departments/video/SOUL.md"
python3 -c "import json; cfg={'agents':{'defaults':{'workspace':'$ws'},'list':[]}}; json.dump(cfg,open('$A/.openclaw/openclaw.json','w'))"
rA="$(HOME="$A" python3 - "$GATE_PY" <<'PN'
import sys,os,json; sys.path.insert(0,os.path.dirname(sys.argv[1]))
import assert_model_sovereignty as g
o,s=g.scan_agent_soul_files(os.path.join(os.environ["HOME"],".openclaw","openclaw.json"))
print(json.dumps({"o":o,"s":s}))
PN)"
sA="$(echo "$rA"|python3 -c "import json,sys;d=json.load(sys.stdin);print(len(d['s']))" 2>/dev/null||echo 0)"
oA="$(echo "$rA"|python3 -c "import json,sys;d=json.load(sys.stdin);print(len(d['o']))" 2>/dev/null||echo 0)"
[ "$sA" = "3" ] && pass "scanned 3 SOUL.md" || fail "expected 3 scanned; got $sA"
[ "$oA" = "2" ] && pass "found 2 offenders (graphics+video)" || fail "expected 2 offenders; got $oA"
echo ""

# (b) scan_agent_soul_files empty when no Anthropic
echo "--- Test B: scan_agent_soul_files empty on clean depts ---"
B="$(mktemp -d)"
trap 'rm -rf "$B" 2>/dev/null || true' EXIT
wsB="$B/workspace"; mkdir -p "$wsB/departments/"{ops,legal} "$B/.openclaw"
printf 'openai/gpt-4o\n' > "$wsB/departments/ops/SOUL.md"
printf 'ollama/qwen3\n' > "$wsB/departments/legal/SOUL.md"
python3 -c "import json;json.dump({'agents':{'defaults':{'workspace':'$wsB'},'list':[]}},open('$B/.openclaw/openclaw.json','w'))"
rB="$(HOME="$B" python3 - "$GATE_PY" <<'PN'
import sys,os,json; sys.path.insert(0,os.path.dirname(sys.argv[1]))
import assert_model_sovereignty as g
o,s=g.scan_agent_soul_files(os.path.join(os.environ["HOME"],".openclaw","openclaw.json"))
print(json.dumps({"o":o,"s":s}))
PN)"
sB="$(echo "$rB"|python3 -c "import json,sys;d=json.load(sys.stdin);print(len(d['s']))" 2>/dev/null||echo 0)"
oB="$(echo "$rB"|python3 -c "import json,sys;d=json.load(sys.stdin);print(len(d['o']))" 2>/dev/null||echo 0)"
[ "$sB" = "2" ] && pass "scanned 2 clean SOUL.md" || fail "expected 2 scanned; got $sB"
[ "$oB" = "0" ] && pass "0 offenders on clean depts" || fail "expected 0 offenders; got $oB"
echo ""

# (c) _strip_anthropic_from_soul_file replaces model-ids
echo "--- Test C: _strip_anthropic replaces model-ids ---"
C="$(mktemp -d)"; trap 'rm -rf "$C" 2>/dev/null || true' EXIT; soulC="$C/SOUL.md"
printf 'anthropic/claude-5-sonnet\nus.anthropic.claude-opus-4\nopenrouter/anthropic/opus\n' > "$soulC"
rC="$(python3 - "$GATE_PY" "$soulC" <<'PN'
import sys,os,json; sys.path.insert(0,os.path.dirname(sys.argv[1]))
import assert_model_sovereignty as g
m=g._strip_anthropic_from_soul_file(sys.argv[2]); print(json.dumps({"m":m}))
PN)"
mC="$(echo "$rC"|python3 -c "import json,sys;d=json.load(sys.stdin);print(d['m'])" 2>/dev/null||echo 0)"
[ "$mC" = "3" ] && pass "replaced 3 model-ids" || fail "expected 3; got $mC"
grep -q "client-provider/model" "$soulC" && pass "has client-provider/model" || fail "no replacement"
echo ""

# (d) _strip_anthropic creates backup
echo "--- Test D: backup before mutation ---"
D="$(mktemp -d)"; trap 'rm -rf "$D" 2>/dev/null || true' EXIT; soulD="$D/SOUL.md"
printf 'anthropic/claude-opus-4\n' > "$soulD"
shaD="$(shasum -a 256 "$soulD"|awk '{print $1}')"
python3 - "$GATE_PY" "$soulD" >/dev/null 2>&1 <<'PN'
import sys,os; sys.path.insert(0,os.path.dirname(sys.argv[1]))
import assert_model_sovereignty as g; g._strip_anthropic_from_soul_file(sys.argv[2])
PN
bD="$(find "$D" -name "*.bak-soul-sweep-*" -maxdepth 1 2>/dev/null|wc -l|tr -d ' ')"
[ "$bD" -ge 1 ] && pass "backup created ($bD)" || fail "no backup"
bF="$(find "$D" -name "*.bak-soul-sweep-*" -maxdepth 1 2>/dev/null|head -1)"
if [ -n "$bF" ]; then bSha="$(shasum -a 256 "$bF"|awk '{print $1}')"; [ "$bSha" = "$shaD" ] && pass "backup SHA matches" || fail "SHA mismatch"; fi
echo ""

# (e) _strip_anthropic idempotent
echo "--- Test E: idempotent ---"
E="$(mktemp -d)"; trap 'rm -rf "$E" 2>/dev/null || true' EXIT; soulE="$E/SOUL.md"
printf 'anthropic/claude-5-sonnet openrouter/anthropic/opus\n' > "$soulE"
python3 - "$GATE_PY" "$soulE" >/dev/null 2>&1 <<'PN'
import sys,os; sys.path.insert(0,os.path.dirname(sys.argv[1]))
import assert_model_sovereignty as g; g._strip_anthropic_from_soul_file(sys.argv[2])
PN
rE="$(python3 - "$GATE_PY" "$soulE" <<'PN'
import sys,os,json; sys.path.insert(0,os.path.dirname(sys.argv[1]))
import assert_model_sovereignty as g
m=g._strip_anthropic_from_soul_file(sys.argv[2]); print(json.dumps({"m":m}))
PN)"
mE="$(echo "$rE"|python3 -c "import json,sys;d=json.load(sys.stdin);print(d['m'])" 2>/dev/null||echo -1)"
[ "$mE" = "0" ] && pass "second pass mutated 0" || fail "expected 0; got $mE"
echo ""

# (f) _scan_soul_file_text detects ids
echo "--- Test F: _scan_soul_file_text ---"
F="$(mktemp)"; trap 'rm -f "$F" 2>/dev/null || true' EXIT
printf 'safe\nanthropic/claude-5-sonnet\nsafe\nus.anthropic.claude-opus-4\njust claude\nopenrouter/anthropic/opus\n' > "$F"
rF="$(python3 - "$GATE_PY" "$F" <<'PN'
import sys,os,json; sys.path.insert(0,os.path.dirname(sys.argv[1]))
import assert_model_sovereignty as g
h=g._scan_soul_file_text(sys.argv[2]); print(json.dumps({"h":h}))
PN)"
hF="$(echo "$rF"|python3 -c "import json,sys;d=json.load(sys.stdin);print(len(d['h']))" 2>/dev/null||echo 0)"
[ "$hF" = "3" ] && pass "found 3 model-id lines" || fail "expected 3; got $hF"
echo "$rF"|python3 -c "
import json,sys;d=json.load(sys.stdin);lines=[h['line']for h in d['h']]
assert 2 in lines and 4 in lines and 6 in lines,f'wrong lines:{lines}'
assert 5 not in lines,f'line 5 should not flag; got {lines}'
print('OK')" 2>/dev/null && pass "lines 2,4,6 flagged (5 NOT)" || fail "flagging mismatch"
echo ""

# (g) text_has_anthropic_model_id discriminates
echo "--- Test G: text_has_anthropic_model_id ---"
python3 - "$GATE_PY" >/dev/null 2>&1 <<'PN'
import sys,os; sys.path.insert(0,os.path.dirname(sys.argv[1]))
import assert_model_sovereignty as g
tests=[("anthropic/claude-5-sonnet",True),("us.anthropic.claude-opus-4",True),
("claude-3-opus",True),("openrouter/anthropic/opus",True),
("Anthropic infrastructure",False),("Anthropic-Sonnet removed per policy",False),
("just claude prose",False),("G-NOANTHROPIC /anthropic|claude/i",False)]
for t,e in tests: assert g.text_has_anthropic_model_id(t)==e,f'{t!r}: expected {e}'
print('ALL_PASS')
PN
rcG=$?
[ $rcG -eq 0 ] && pass "8 cases correct" || fail "discrimination failed"
echo ""

# (h) _strip_anthropic no-op on clean
echo "--- Test H: no-op on clean ---"
H="$(mktemp -d)"; trap 'rm -rf "$H" 2>/dev/null || true' EXIT; soulH="$H/SOUL.md"
printf 'openai/gpt-4o\n' > "$soulH"
rH="$(python3 - "$GATE_PY" "$soulH" <<'PN'
import sys,os,json; sys.path.insert(0,os.path.dirname(sys.argv[1]))
import assert_model_sovereignty as g
m=g._strip_anthropic_from_soul_file(sys.argv[2]); print(json.dumps({"m":m}))
PN)"
mH="$(echo "$rH"|python3 -c "import json,sys;d=json.load(sys.stdin);print(d['m'])" 2>/dev/null||echo -1)"
[ "$mH" = "0" ] && pass "returns 0 on clean" || fail "expected 0; got $mH"
echo ""

echo ""
echo "PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -eq 0 ] || exit 1
