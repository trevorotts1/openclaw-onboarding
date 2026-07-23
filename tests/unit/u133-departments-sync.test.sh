#!/usr/bin/env bash
set -uo pipefail
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
S="$R/shared-utils/sync_departments_additive.py"
P=0;F=0;ok(){ P=$((P+1));echo "  PASS: $1";};bad(){ F=$((F+1));echo "  FAIL: $1";}
T=$(mktemp -d -t u133-XXXXXX);trap 'rm -rf "$T"' EXIT
[[ -f "$S" ]]||{ bad "sync script missing";echo "RESULT pass=$P fail=$F";exit 1;}
cnt(){ python3 -c "import json;print(len(json.load(open('$1'))))"; }
echo "Test 1: new department added"
mkdir -p "$T/t1";printf '[{"slug":"ceo","name":"CEO"},{"slug":"ops","name":"Ops"},{"slug":"new","name":"New"}]\n' > "$T/t1/c.json";printf '[{"slug":"ceo","name":"CEO"},{"slug":"ops","name":"Ops"}]\n' > "$T/t1/d.json"
python3 "$S" "$T/t1/c.json" "$T/t1/d.json" 2>/dev/null;[ "$(cnt "$T/t1/d.json")" = "3" ] && grep -q '"new"' "$T/t1/d.json" && ok "new added (2->3)" || bad "new not added"
echo "Test 2: existing department updated"
mkdir -p "$T/t2";printf '[{"slug":"ceo","name":"CEO"},{"slug":"ops","name":"Ops UPDATED","headTitle":"SVP"}]\n' > "$T/t2/c.json";printf '[{"slug":"ceo","name":"CEO"},{"slug":"ops","name":"Ops"}]\n' > "$T/t2/d.json"
python3 "$S" "$T/t2/c.json" "$T/t2/d.json" 2>/dev/null;grep -q 'Ops UPDATED' "$T/t2/d.json" && grep -q '"SVP"' "$T/t2/d.json" && ok "existing updated" || bad "existing not updated"
echo "Test 3: custom departments preserved"
mkdir -p "$T/t3";printf '[{"slug":"ceo","name":"CEO"},{"slug":"new","name":"New"}]\n' > "$T/t3/c.json";printf '[{"slug":"ceo","name":"CEO"},{"slug":"cust","name":"Custom","cf":"keep-me"}]\n' > "$T/t3/d.json"
python3 "$S" "$T/t3/c.json" "$T/t3/d.json" 2>/dev/null;[ "$(cnt "$T/t3/d.json")" = "3" ] && grep -q '"cust"' "$T/t3/d.json" && grep -q '"new"' "$T/t3/d.json" && ok "custom preserved + new added" || bad "custom deleted"
echo "Test 4: idempotent second run"
mkdir -p "$T/t4";printf '[{"slug":"ceo","name":"CEO"},{"slug":"new","name":"New"}]\n' > "$T/t4/c.json";printf '[{"slug":"ceo","name":"CEO"}]\n' > "$T/t4/d.json"
python3 "$S" "$T/t4/c.json" "$T/t4/d.json" 2>/dev/null;cp "$T/t4/d.json" "$T/t4/r1.json"
python3 "$S" "$T/t4/c.json" "$T/t4/d.json" 2>/dev/null;cmp -s "$T/t4/r1.json" "$T/t4/d.json" && ok "second run idempotent" || bad "second run changed"
echo "Test 5: empty canonical safe"
mkdir -p "$T/t5";printf '[]\n' > "$T/t5/c.json";printf '[{"slug":"x","name":"Xtra"}]\n' > "$T/t5/d.json"
python3 "$S" "$T/t5/c.json" "$T/t5/d.json" 2>/dev/null;[ "$(cnt "$T/t5/d.json")" = "1" ] && ok "empty canonical safe" || bad "empty canonical deleted"
echo "Test 6: empty CC populated"
mkdir -p "$T/t6";printf '[{"slug":"a","name":"A"},{"slug":"b","name":"B"}]\n' > "$T/t6/c.json";printf '[]\n' > "$T/t6/d.json"
python3 "$S" "$T/t6/c.json" "$T/t6/d.json" 2>/dev/null;[ "$(cnt "$T/t6/d.json")" = "2" ] && ok "empty CC populated" || bad "empty CC not populated"
echo "Test 7: dept- prefix normalization"
mkdir -p "$T/t7";printf '[{"slug":"dept-ceo","name":"CEO"}]\n' > "$T/t7/d.json";printf '[{"id":"ceo","name":"Chief Exec"}]\n' > "$T/t7/c.json"
python3 "$S" "$T/t7/c.json" "$T/t7/d.json" 2>/dev/null;[ "$(cnt "$T/t7/d.json")" = "1" ] && grep -q 'Chief Exec' "$T/t7/d.json" && ok "dept- prefix normalized" || bad "dept- prefix failed"
echo "--- Mutation proof ---"
mkdir -p "$T/mut";printf '[{"slug":"ceo","name":"CEO"}]\n' > "$T/mut/t.json";printf '[{"slug":"ceo","name":"CEO"},{"slug":"new","name":"New"}]\n' > "$T/mut/c.json"
python3 -c "L=open('$S').readlines()
for i in range(len(L)):
 if 'merged.append' in L[i] and 'added' in L[i]:
  L[i]='   pass  # MUTATED\\n';break
open('$T/mut/sm.py','w').writelines(L)" && chmod +x "$T/mut/sm.py"
if python3 "$T/mut/sm.py" "$T/mut/c.json" "$T/mut/t.json" 2>/dev/null;then
 c=$(cnt "$T/mut/t.json");[ "$c" = "1" ] && ok "MUT: without append count=1 (RED)"||bad "MUT: expected 1 got $c"
else bad "MUT: mutated script failed";fi
python3 "$S" "$T/mut/c.json" "$T/mut/t.json" 2>/dev/null;c2=$(cnt "$T/mut/t.json");[ "$c2" = "2" ] && ok "REVERT: original adds dept (GREEN)"||bad "REVERT: expected 2 got $c2"
echo "RESULT pass=$P fail=$F";[ "$F" -eq 0 ]
