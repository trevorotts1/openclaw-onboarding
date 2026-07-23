#!/usr/bin/env bash
# tests/unit/test-tool-allowlist.sh -- U134 Fleet Tool Allowlist
set -euo pipefail
PASS=0; FAIL=0; ERRORS=()
ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); ERRORS+=("$1"); }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AL="$REPO_ROOT/scripts/apply-tool-allowlist.sh"
US="$REPO_ROOT/update-skills.sh"
FS="$REPO_ROOT/FLEET-STANDARDS.md"
AFS="$REPO_ROOT/scripts/apply-fleet-standards.sh"

echo ""; echo "=== U134 -- Fleet Tool Allowlist ==="

# Helper: run the tool-allowlist script against a mock config
run_al() {
  local home_dir="$1"  
  HOME="$home_dir" FLEET_TOOL_ALLOWLIST_SKIP_VALIDATE=1 bash "$AL" >/dev/null 2>&1 || true
}

# (A) Existence + syntax + wiring
echo ""; echo "--- (A) Existence + syntax ---"
[ -f "$AL" ] && ok "(A1) apply-tool-allowlist.sh exists" || fail "(A1) NOT FOUND"
bash -n "$AL" 2>&1 && ok "(A2) bash -n passes" || fail "(A2) bash -n FAILS"
echo ""; echo "--- (A3) Wired into update-skills.sh ---"
grep -q 'apply-tool-allowlist.sh' "$US" && ok "(A3) referenced in update-skills.sh" || fail "(A3) NOT referenced"
bash -n "$US" 2>&1 && ok "(A3b) update-skills.sh bash -n" || fail "(A3b) bash -n FAILS"

# (B) Main behavior
echo ""; echo "--- (B) Main behavior ---"
TD_B=$(mktemp -d); mkdir -p "$TD_B/.openclaw"
echo '{"agents":{"list":[{"id":"main","default":true,"name":"CEO","is_master":true,"workspace":"/tmp/bws"}]}}' > "$TD_B/.openclaw/openclaw.json"
run_al "$TD_B"
R_B="$(HOME="$TD_B" python3 -c "
import json; c=json.load(open('$TD_B/.openclaw/openclaw.json'))
ag=next(a for a in c['agents']['list'] if a.get('id')=='main')
t=ag.get('tools',{}); al=t.get('allow',[]); de=t.get('deny',[]); bp=t.get('byProvider',{})
print('AC=%d DC=%d BPC=%d READ=%s BRW=%s GHL=%s'%(len(al),len(de),len(bp),'read' in al,'browser' in de,'ghl-community-mcp' in bp))
")"
echo "$R_B" | grep -qE 'AC=1[5-9]' && ok "(B1) allow count: $R_B" || fail "(B1) allow count wrong: $R_B"
echo "$R_B" | grep -qE 'DC=[7-9]' && ok "(B2) deny count: $R_B" || fail "(B2) deny count wrong: $R_B"
echo "$R_B" | grep -qE 'BPC=[12]' && ok "(B3) MCP byProvider: $R_B" || fail "(B3) MCP missing: $R_B"
echo "$R_B" | grep -q 'READ=True' && ok "(B4) read in allow" || fail "(B4) read missing: $R_B"
echo "$R_B" | grep -q 'BRW=True' && ok "(B5) browser in deny" || fail "(B5) browser missing: $R_B"

# (C) No-op when unchanged — compare tool content, not bytes (reformatting is expected)
echo ""; echo "--- (C) No-op ---"
TD_C=$(mktemp -d); mkdir -p "$TD_C/.openclaw"
cat > "$TD_C/.openclaw/openclaw.json" <<'JEOF'
{"agents":{"list":[{"id":"main","default":true,"name":"CEO","is_master":true,"workspace":"/tmp/cws","tools":{"allow":["cron","exec","gateway","mc-route__route_task","memory_get","memory_search","message","nodes","read","sessions_history","sessions_list","sessions_send","slack","telegram","web_fetch","web_search"],"deny":["apply_patch","browser","canvas","edit","ghl-community-mcp__*","ghl-mcp__*","image","process","write"],"byProvider":{"ghl-community-mcp":{"deny":["*"]},"ghl-mcp":{"deny":["*"]}}}}]}}
JEOF
run_al "$TD_C"
C_TOOLS="$(python3 -c "
import json; c=json.load(open('$TD_C/.openclaw/openclaw.json'))
ag=next(a for a in c.get('agents',{}).get('list',[]) if isinstance(a,dict) and a.get('id')=='main')
t=ag.get('tools',{})
allow=t.get('allow',[]); deny=t.get('deny',[]); bp=t.get('byProvider',{})
# Must still have all 17 allow, 9 deny, 2 MCP provider entries
ok1=len(allow)==17; ok2=len(deny)==9; ok3=len(bp)==2
ok4='read' in allow; ok5='browser' in deny; ok6='ghl-community-mcp' in bp
print('%s %s %s %s %s %s'%(ok1,ok2,ok3,ok4,ok5,ok6))
")"
echo "$C_TOOLS" | grep -q 'True True True True True True' && ok "(C1) no-op — tool content unchanged" || fail "(C1) tools changed: $C_TOOLS"

# (D) Local-only preserved
echo ""; echo "--- (D) Local-only preserved ---"
TD_D=$(mktemp -d); mkdir -p "$TD_D/.openclaw"
echo '{"agents":{"list":[{"id":"main","default":true,"name":"CEO","is_master":true,"workspace":"/tmp/dws","tools":{"allow":["read","message","local-custom","local-probe"],"deny":["local-deny"]}}]}}' > "$TD_D/.openclaw/openclaw.json"
run_al "$TD_D"
R_D="$(HOME="$TD_D" python3 -c "
import json; c=json.load(open('$TD_D/.openclaw/openclaw.json'))
ag=next(a for a in c['agents']['list'] if a.get('id')=='main')
t=ag.get('tools',{}); al=t.get('allow',[]); de=t.get('deny',[])
print('%s %s %s %s'%('local-custom' in al,'local-probe' in al,'local-deny' in de,'read' in al))
")"
echo "$R_D" | awk '{print $1}' | grep -q True && ok "(D1) local-custom preserved" || fail "(D1) REMOVED"
echo "$R_D" | awk '{print $2}' | grep -q True && ok "(D2) local-probe preserved" || fail "(D2) REMOVED"
echo "$R_D" | awk '{print $3}' | grep -q True && ok "(D3) local-deny preserved" || fail "(D3) REMOVED"
echo "$R_D" | awk '{print $4}' | grep -q True && ok "(D4) fleet read present" || fail "(D4) missing"

# (E) FLEET-STANDARDS.md
echo ""; echo "--- (E) FLEET-STANDARDS.md ---"
grep -qE 'Tool Allowlist|tool allowlist.*skills update|Per-Agent Tool Policy' "$FS" && ok "(E1) documented" || fail "(E1) NOT documented"

# (F) Keep-in-sync
echo ""; echo "--- (F) Keep-in-sync ---"
[ -f "$AFS" ] || { fail "(F) apply-fleet-standards.sh not found"; }
AA="$(python3 -c "import re;c=open('$AFS').read();m=re.search(r'_CEO_TOOL_ALLOW\s*=\s*\[(.*?)\]',c,re.DOTALL);b=re.sub(r'#.*','',m.group(1) if m else '');i=re.findall(r'\"([^\"]+)\"',b);print(' '.join(sorted(i)))")"
LA="$(python3 -c "import re;c=open('$AL').read();m=re.search(r'FLEET_TOOL_ALLOW\s*=\s*\[(.*?)\]',c,re.DOTALL);b=re.sub(r'#.*','',m.group(1) if m else '');i=re.findall(r'\"([^\"]+)\"',b);print(' '.join(sorted(i)))")"
[ "$AA" = "$LA" ] && ok "(F1) ALLOW lists match" || fail "(F1) DIVERGED"
AD="$(python3 -c "import re;c=open('$AFS').read();m=re.search(r'_CEO_TOOL_DENY\s*=\s*\[(.*?)\]',c,re.DOTALL);b=re.sub(r'#.*','',m.group(1) if m else '');i=re.findall(r'\"([^\"]+)\"',b);print(' '.join(sorted(i)))")"
LD="$(python3 -c "import re;c=open('$AL').read();m=re.search(r'FLEET_TOOL_DENY\s*=\s*\[(.*?)\]',c,re.DOTALL);b=re.sub(r'#.*','',m.group(1) if m else '');i=re.findall(r'\"([^\"]+)\"',b);print(' '.join(sorted(i)))")"
[ "$AD" = "$LD" ] && ok "(F2) DENY lists match" || fail "(F2) DIVERGED"

# (G) Mutation proof
echo ""; echo "--- (G) Mutation proof ---"
TD_G=$(mktemp -d); mkdir -p "$TD_G/.openclaw"

echo '{"agents":{"list":[{"id":"main","default":true,"name":"CEO","is_master":true,"workspace":"/tmp/gws"}]}}' > "$TD_G/.openclaw/openclaw.json"
run_al "$TD_G"
G1="$(HOME="$TD_G" python3 -c "import json;c=json.load(open('$TD_G/.openclaw/openclaw.json'));ag=next(a for a in c['agents']['list'] if a.get('id')=='main');print('browser' in ag.get('tools',{}).get('deny',[]))")"
[ "$G1" = "True" ] && ok "(G1) unmutated GREEN" || fail "(G1) RED"

MUT="$TD_G/mutated.sh"; sed 's/"browser"/"browser_mutated_broken"/g' "$AL" > "$MUT"; chmod +x "$MUT"
rm -f "$TD_G/.openclaw/openclaw.json"
echo '{"agents":{"list":[{"id":"main","default":true,"name":"CEO","is_master":true,"workspace":"/tmp/gws"}]}}' > "$TD_G/.openclaw/openclaw.json"
HOME="$TD_G" FLEET_TOOL_ALLOWLIST_SKIP_VALIDATE=1 bash "$MUT" >/dev/null 2>&1 || true
G2="$(HOME="$TD_G" python3 -c "import json;c=json.load(open('$TD_G/.openclaw/openclaw.json'));ag=next(a for a in c['agents']['list'] if a.get('id')=='main');print('browser' in ag.get('tools',{}).get('deny',[]))")"
[ "$G2" = "False" ] && ok "(G2) mutated RED (mutation detected)" || fail "(G2) still GREEN"

rm -f "$TD_G/.openclaw/openclaw.json"
echo '{"agents":{"list":[{"id":"main","default":true,"name":"CEO","is_master":true,"workspace":"/tmp/gws"}]}}' > "$TD_G/.openclaw/openclaw.json"
run_al "$TD_G"
G3="$(HOME="$TD_G" python3 -c "import json;c=json.load(open('$TD_G/.openclaw/openclaw.json'));ag=next(a for a in c['agents']['list'] if a.get('id')=='main');print('browser' in ag.get('tools',{}).get('deny',[]))")"
[ "$G3" = "True" ] && ok "(G3) reverted GREEN restored" || fail "(G3) STILL RED"

rm -rf "$TD_B" "$TD_C" "$TD_D" "$TD_G"

echo ""; echo "=== Summary ==="; echo "  PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -gt 0 ] && { for e in "${ERRORS[@]}"; do echo "    - $e"; done; echo "FINAL: RED"; exit 1; }
echo "FINAL: GREEN"; exit 0
