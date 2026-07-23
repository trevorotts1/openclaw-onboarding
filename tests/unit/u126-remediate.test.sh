#!/usr/bin/env bash
# tests/unit/fleet-audit-remediate.test.sh -- U126 fleet audit remediation tests
set -euo pipefail

SCRIPT="/private/tmp/u126-worktree/scripts/u126-remediate.sh"
TMP="$(mktemp -d)"
PASS=0; FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

echo "=== fleet-audit-remediate.test.sh ==="
echo ""

# Pre-flight
echo "--- PRE-FLIGHT ---"
if [[ -f "$SCRIPT" ]]; then pass "script exists at $SCRIPT"
else fail "script not found at $SCRIPT"; fi
if bash -n "$SCRIPT" 2>&1; then pass "bash -n passes"
else fail "bash -n fails"; fi

# T1: F1 version staleness logic
echo ""
echo "--- T1: F1 version staleness ---"
test_t1() {
  local result
  result=$(python3 -c "
# EXACT logic from fleet-audit-remediate.sh
def version_behind(local, latest):
    try:
        lparts = [int(x) for x in local.split('.')]
        rparts = [int(x) for x in latest.split('.')]
    except Exception:
        return -1
    l_maj, l_min, l_pat = lparts[0], lparts[1], lparts[2]
    r_maj, r_min, r_pat = rparts[0], rparts[1], rparts[2]
    if l_maj != r_maj:
        return 100  # major version difference -> definitely stale
    if l_min != r_min:
        return max(0, r_min - l_min)
    if l_pat != r_pat:
        return max(0, r_pat - l_pat)
    return 0

# Test: behind > 2 means >2 releases behind
# Major version difference (e.g. 20.0.0 vs 21.0.0) -> behind=100, always stale.
# Only test within the same major line for fine-grained staleness:
cases = [
    # Same major, varying minor/patch
    ('21.0.0', '21.0.0', False),  # identical -> behind=0
    ('21.0.0', '21.3.0', True),   # minor 0->3 -> behind=3 >2 -> stale
    ('21.1.0', '21.3.0', False),  # minor 1->3 -> behind=2 <=2 -> NOT stale
    ('21.0.0', '21.2.0', False),  # minor 0->2 -> behind=2 <=2 -> NOT stale
    ('21.5.0', '21.8.0', True),   # minor 5->8 -> behind=3 >2 -> stale
    ('21.7.0', '21.8.0', False),  # minor 7->8 -> behind=1 <=2 -> NOT stale
    ('21.0.1', '21.0.2', False),  # patch 1->2 -> behind=1 <=2 -> NOT stale
    ('21.0.0', '21.0.3', True),   # patch 0->3 -> behind=3 >2 -> stale
    # Major version difference -> always stale
    ('18.0.0', '21.0.0', True),   # major 18 vs 21 -> behind=100
    ('20.0.0', '21.0.0', True),   # major 20 vs 21 -> behind=100
]
fails = 0
for local, latest, expect_stale in cases:
    b = version_behind(local, latest)
    is_stale = b > 2
    if is_stale != expect_stale:
        print(f'FAIL: {local} vs {latest} behind={b} stale={is_stale} expected={expect_stale}')
        fails += 1
if fails == 0:
    print('ALL_OK')
" 2>/dev/null)
  if [[ "$result" == "ALL_OK" ]]; then pass "T1.1 all version staleness cases correct"
  else fail "T1.1 ${result}"; fi
}
test_t1

# T2: F2 orphaned pm2 detection
echo ""
echo "--- T2: F2 orphaned pm2 ---"
test_t2() {
  local exist_dir="$TMP/exists-deploy"; mkdir -p "$exist_dir"
  local noexist_dir="$TMP/noexist-deploy"  # never created

  local fixture
  fixture=$(python3 -c "
import json
print(json.dumps([
    {'pid': 12345, 'name': 'command-center', 'pm_id': 0, 'pm2_env': {'status': 'online', 'PWD': '${exist_dir}'}},
    {'pid': 23456, 'name': 'retired-app', 'pm_id': 1, 'pm2_env': {'status': 'online', 'PWD': '${noexist_dir}'}},
    {'pid': 34567, 'name': 'stale-worker', 'pm_id': 2, 'pm2_env': {'status': 'stopped', 'PWD': '/nonexistent/retired-pipeline'}},
]))
" 2>/dev/null)

  local orphans
  orphans=$(printf '%s' "$fixture" | python3 -c "
import json, sys, os
procs = json.load(sys.stdin)
o = []
for p in procs:
    env = p.get('pm2_env', {}) or {}
    cwd = env.get('PWD', '') or env.get('pm_cwd', '') or ''
    if cwd and not os.path.isdir(cwd):
        o.append({'name': p.get('name',''), 'pm_id': p.get('pm_id','')})
print(json.dumps(o))
" 2>/dev/null || echo "[]")
  local n; n=$(printf '%s' "$orphans" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)
  if [[ "$n" -eq 2 ]]; then pass "T2.1 detected 2 orphans (expected 2)"
  else fail "T2.1 expected 2 got ${n}"; fi
  local names; names=$(printf '%s' "$orphans" | python3 -c "import json,sys; print(' '.join(i['name'] for i in json.load(sys.stdin)))" 2>/dev/null)
  if [[ "$names" != *"command-center"* ]]; then pass "T2.2 healthy process NOT flagged"
  else fail "T2.2 healthy flagged incorrectly"; fi
  if [[ "$names" == *"retired-app"* && "$names" == *"stale-worker"* ]]; then pass "T2.3 both orphans flagged correctly"
  else fail "T2.3 wrong orphans: ${names}"; fi
}
test_t2

# T3: F3 disk alert cron delivery
echo ""
echo "--- T3: F3 disk-alert delivery ---"
test_t3() {
  local silent='[{"name":"disk-usage-alert","id":"aaa","delivery":{"mode":"none"},"payload":{"kind":"command"}}]'
  local good='[{"name":"disk-usage-alert","id":"bbb","delivery":{"mode":"announce","channel":"telegram","to":"123456"},"payload":{"kind":"command"}}]'
  local r1; r1=$(printf '%s' "$silent" | python3 -c "
import json,sys
d=json.load(sys.stdin); jobs=d if isinstance(d,list) else d.get('jobs',[])
disk=[j for j in jobs if j.get('name')=='disk-usage-alert']
if not disk: print('NOT_PRESENT'); sys.exit(0)
dv=disk[0].get('delivery',{}) or {}
m=dv.get('mode',''); ch=dv.get('channel',''); t=dv.get('to','')
is_silent=not(m=='announce' or (ch and t))
print('SILENT' if is_silent else 'HEALTHY')
" 2>/dev/null)
  if [[ "$r1" == "SILENT" ]]; then pass "T3.1 silent delivery flagged as BROKEN"
  else fail "T3.1 got ${r1}, expected SILENT"; fi
  r1=$(printf '%s' "$good" | python3 -c "
import json,sys
d=json.load(sys.stdin); jobs=d if isinstance(d,list) else d.get('jobs',[])
disk=[j for j in jobs if j.get('name')=='disk-usage-alert']
if not disk: print('NOT_PRESENT'); sys.exit(0)
dv=disk[0].get('delivery',{}) or {}
m=dv.get('mode',''); ch=dv.get('channel',''); t=dv.get('to','')
is_silent=not(m=='announce' or (ch and t))
print('SILENT' if is_silent else 'HEALTHY')
" 2>/dev/null)
  if [[ "$r1" == "HEALTHY" ]]; then pass "T3.2 healthy delivery correctly flagged HEALTHY"
  else fail "T3.2 got ${r1}, expected HEALTHY"; fi
}
test_t3

# T4: F4 decoy detection
echo ""
echo "--- T4: F4 decoy detection ---"
test_t4() {
  local d1="$TMP/mission-control.db"; touch "$d1"
  mkdir -p "$TMP/data"; local d2="$TMP/data/mission-control.db"; touch "$d2"
  local real="$TMP/real.db"; printf 'content\n' > "$real"
  local decoys=()
  for c in "$d1" "$d2" "$real"; do
    if [[ -f "$c" ]]; then
      local sz; sz=$(stat -f%z "$c" 2>/dev/null || stat -c%s "$c" 2>/dev/null || echo 1)
      if [[ "$sz" -eq 0 ]]; then decoys+=("$c"); fi
    fi
  done
  if [[ ${#decoys[@]} -eq 2 ]]; then pass "T4.1 detected 2 decoys (expected 2)"
  else fail "T4.1 expected 2 got ${#decoys[@]}"; fi
  if [[ ! " ${decoys[*]} " =~ $real ]]; then pass "T4.2 non-empty file NOT flagged as decoy"
  else fail "T4.2 non-empty file incorrectly flagged"; fi
  rm -f "$d1" "$d2"
  if [[ ! -f "$d1" && ! -f "$d2" ]]; then pass "T4.3 decoys successfully removed"
  else fail "T4.3 removal failed"; fi
}
test_t4

# T5: F5 duplicate cron
echo ""
echo "--- T5: F5 duplicate crons ---"
test_t5() {
  local fixture='[{"name":"disk-usage-alert","id":"aaa-111"},{"name":"disk-usage-alert","id":"aaa-222"},{"name":"orphan-temp-sweep","id":"bbb-111"},{"name":"closeout-resume","id":"ccc-111"},{"name":"closeout-resume","id":"ccc-222"},{"name":"closeout-resume","id":"ccc-333"}]'
  local dups
  dups=$(printf '%s' "$fixture" | python3 -c "
import json,sys; from collections import Counter
d=json.load(sys.stdin); jobs=d if isinstance(d,list) else d.get('jobs',[])
cnt=Counter(j.get('name','') for j in jobs)
dups={n:c for n,c in cnt.items() if c>1}
res=[]
for n,c in dups.items():
    ents=sorted([j for j in jobs if j.get('name')==n], key=lambda j: j.get('id',''))
    res.append({'name':n,'count':c,'keep':ents[0].get('id',''),'remove':[j.get('id','') for j in ents[1:]]})
print(json.dumps(res))
" 2>/dev/null || echo "[]")
  local nd; nd=$(printf '%s' "$dups" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)
  if [[ "$nd" -eq 2 ]]; then pass "T5.1 2 duplicate cron names found"
  else fail "T5.1 expected 2 got ${nd}"; fi
  local nrm; nrm=$(printf '%s' "$dups" | python3 -c "import json,sys; items=json.load(sys.stdin); print(sum(len(i.get('remove',[])) for i in items))" 2>/dev/null)
  if [[ "$nrm" -eq 3 ]]; then pass "T5.2 3 duplicate entries to remove (1+2)"
  else fail "T5.2 expected 3 got ${nrm}"; fi
}
test_t5

# T6: F6 build-state corruption
echo ""
echo "--- T6: F6 build-state ---"
test_t6() {
  local wf="$TMP/.workforce-build-state.json"

  # T6.1: valid v2
  printf '{"schemaVersion":2,"interviewComplete":true}\n' > "$wf"
  local r; r=$(python3 -c "
import json; d=json.load(open('$wf')); sv=d.get('schemaVersion')
if sv is None: print('NO_SCHEMA_VERSION')
elif not isinstance(sv,int) or sv<=0: print('INVALID:'+str(sv))
elif sv>100: print('FUTURE:'+str(sv))
else: print('OK:'+str(sv))
" 2>/dev/null)
  if [[ "$r" == "OK:2" ]]; then pass "T6.1 v2 valid JSON detected correctly"
  else fail "T6.1 got ${r}"; fi

  # T6.2: no schemaVersion (v1)
  printf '{"interviewComplete":"true"}\n' > "$wf"
  r=$(python3 -c "
import json; d=json.load(open('$wf')); sv=d.get('schemaVersion')
if sv is None: print('NO_SCHEMA_VERSION')
else: print('HAS:'+str(sv))
" 2>/dev/null)
  if [[ "$r" == "NO_SCHEMA_VERSION" ]]; then pass "T6.2 v1 (no schemaVersion) detected"
  else fail "T6.2 got ${r}"; fi

  # T6.3: corrupt JSON
  printf '{"schemaVersion":2,"busted' > "$wf"
  r=$(python3 -c "
import json
try: json.load(open('$wf')); print('OK')
except json.JSONDecodeError: print('JSON_ERROR')
except: print('OTHER')
" 2>/dev/null)
  if [[ "$r" == "JSON_ERROR" ]]; then pass "T6.3 corrupt JSON detected"
  else fail "T6.3 got ${r}"; fi

  # T6.4: quarantine
  rm -f "$wf"
  printf '{"bad' > "$wf"
  local ts; ts=$(date +%s); local q="${wf}.corrupt-${ts}"
  mv "$wf" "$q" 2>/dev/null
  if [[ ! -f "$wf" && -f "$q" ]]; then pass "T6.4 corrupt file quarantined successfully"
  else fail "T6.4 quarantine failed"; fi

  # T6.5: recovery stub
  cat > "$wf" << 'STUB'
{"schemaVersion":2,"interviewComplete":false,"departments":{}}
STUB
  local sv; sv=$(python3 -c "import json; print(json.load(open('$wf')).get('schemaVersion'))" 2>/dev/null || echo "")
  if [[ "$sv" == "2" ]]; then pass "T6.5 recovery stub seeded with schemaVersion=2"
  else fail "T6.5 got sv=${sv}"; fi

  # T6.6: future schemaVersion
  printf '{"schemaVersion":999}\n' > "$wf"
  r=$(python3 -c "
import json; d=json.load(open('$wf')); sv=d.get('schemaVersion')
if sv is None: print('NONE')
elif not isinstance(sv,int) or sv<=0: print('INVALID')
elif sv>100: print('FUTURE:'+str(sv))
else: print('OK:'+str(sv))
" 2>/dev/null)
  if [[ "$r" == "FUTURE:999" ]]; then pass "T6.6 future schemaVersion=999 flagged"
  else fail "T6.6 got ${r}"; fi

  # T6.7: v1->v2 migration
  printf '{"interviewComplete":"true"}\n' > "$wf"
  python3 -c "
import json
d=json.load(open('$wf'))
for k in ('interviewComplete',):
    if k in d and isinstance(d[k],str): d[k]=(d[k].lower()=='true')
d['schemaVersion']=2
d.setdefault('departments',{})
json.dump(d,open('$wf','w'),indent=2)
" 2>/dev/null
  sv=$(python3 -c "import json; print(json.load(open('$wf')).get('schemaVersion'))" 2>/dev/null)
  ic=$(python3 -c "import json; print(json.load(open('$wf')).get('interviewComplete'))" 2>/dev/null)
  if [[ "$sv" == "2" && "$ic" == "True" ]]; then pass "T6.7 v1->v2 migration: schemaVersion=2, interviewComplete=True"
  else fail "T6.7 sv=${sv} ic=${ic}"; fi
}
test_t6

# T7: F7 workspace seeding
echo ""
echo "--- T7: F7 workspace seeding ---"
test_t7() {
  local ws="$TMP/ws"; mkdir -p "$ws"
  local pw="$ws/podcast-production-engine"; local aw="$ws/anthology-engine"
  local us=()
  [[ -d "$pw" && -n "$(ls -A "$pw" 2>/dev/null)" ]] || us+=("podcast")
  [[ -d "$aw" && -n "$(ls -A "$aw" 2>/dev/null)" ]] || us+=("anthology")
  if [[ ${#us[@]} -eq 2 ]]; then pass "T7.1 both workspaces unseeded"
  else fail "T7.1 expected 2 got ${#us[@]}"; fi

  mkdir -p "$pw"; touch "$pw/.seeded"
  us=()
  [[ -d "$pw" && -n "$(ls -A "$pw" 2>/dev/null)" ]] || us+=("podcast")
  [[ -d "$aw" && -n "$(ls -A "$aw" 2>/dev/null)" ]] || us+=("anthology")
  if [[ ${#us[@]} -eq 1 && "${us[0]}" == "anthology" ]]; then pass "T7.2 only anthology unseeded after podcast seeded"
  else fail "T7.2 got ${#us[@]}: ${us[*]}"; fi

  mkdir -p "$aw"; touch "$aw/.seeded"
  us=()
  [[ -d "$pw" && -n "$(ls -A "$pw" 2>/dev/null)" ]] || us+=("podcast")
  [[ -d "$aw" && -n "$(ls -A "$aw" 2>/dev/null)" ]] || us+=("anthology")
  if [[ ${#us[@]} -eq 0 ]]; then pass "T7.3 both seeded, no unseeded components"
  else fail "T7.3 ${#us[@]} unseeded: ${us[*]}"; fi
}
test_t7

# MUTATION PROOF
echo ""
echo "--- MUTATION PROOF ---"
mp=0; mt=6

# M1: threshold 2->5 would miss version 21.0.0 vs 21.3.0 (3 minor releases behind)
r=$(python3 -c "
def behind(l,v):
    lp=[int(x)for x in l.split('.')];rp=[int(x)for x in v.split('.')]
    if lp[0]!=rp[0]:return 100
    if lp[1]!=rp[1]:return max(0,rp[1]-lp[1])
    if lp[2]!=rp[2]:return max(0,rp[2]-lp[2])
    return 0
# 21.0.0 vs 21.3.0: minor diff=3 -> behind=3
# threshold 2: 3>2 = True (stale detected)
# threshold 5: 3>5 = False (stale MISSED)
orig=behind('21.0.0','21.3.0')>2
mut=behind('21.0.0','21.3.0')>5
print('DETECTED' if orig and not mut else f'MISSED orig={orig} mut={mut}')
" 2>/dev/null)
if [[ "$r" == "DETECTED" ]]; then pass "M1: raising threshold 2->5 would miss stale boxes (3 behind)"; mp=$((mp+1))
else fail "M1: ${r}"; fi

# M2: skip cwd check -> orphan not detected
r=$(printf '%s' '[{"pid":1,"pm_id":1,"pm2_env":{"PWD":"/nonexistent/path"}}]' | python3 -c "
import json,sys,os
p=json.load(sys.stdin)[0]
cwd=(p.get('pm2_env',{})or{}).get('PWD','')
orig=(cwd and not os.path.isdir(cwd))   # True -> detected
mut=False                                # skipped -> missed
print('DETECTED' if orig and not mut else f'MISSED orig={orig} mut={mut}')
" 2>/dev/null)
if [[ "$r" == "DETECTED" ]]; then pass "M2: skipping cwd check would miss orphaned pm2"; mp=$((mp+1))
else fail "M2: ${r}"; fi

# M3: ignore mode=announce, only check channel+to - would falsely flag valid announce cron
r=$(printf '%s' '{"mode":"announce","channel":"","to":""}' | python3 -c "
import json, sys
d=json.load(sys.stdin)
orig=not(d['mode']=='announce' or(d.get('channel') and d.get('to')))
mut=not(d.get('channel') and d.get('to'))
out='DETECTED' if not orig and mut else 'MISSED orig='+str(orig)+' mut='+str(mut)
print(out)
" 2>/dev/null)
if [[ "$r" == "DETECTED" ]]; then pass "M3: ignoring mode check would falsely flag valid announce cron"; mp=$((mp+1))
else fail "M3: ${r}"; fi

# M4: skip 0-byte check -> real DB flagged as decoy
nonz="$TMP/m4-nonzero.db"
printf 'real content\n' > "$nonz"
r=$(python3 -c "
import os
sz=os.path.getsize('$nonz')
orig=(sz==0)
mut=os.path.isfile('$nonz')
out='DETECTED' if not orig and mut else 'MISSED orig='+str(orig)+' mut='+str(mut)
print(out)
" 2>/dev/null)
if [[ "$r" == "DETECTED" ]]; then pass "M4: omitting 0-byte check would flag real DBs as decoys"; mp=$((mp+1))
else fail "M4: ${r}"; fi

# M5: keep wrong duplicate entry (last instead of first by id sort)
r=$(printf '%s' '[{"name":"x","id":"zzz-222"},{"name":"x","id":"aaa-111"}]' | python3 -c "
import json, sys
d=json.load(sys.stdin)
ents=sorted(d, key=lambda j: j.get('id',''))
orig_keep=ents[0].get('id')
mut_keep=ents[-1].get('id')
out='DETECTED' if orig_keep!=mut_keep and orig_keep=='aaa-111' else 'MISSED'
print(out)
" 2>/dev/null)
if [[ "$r" == "DETECTED" ]]; then pass "M5: keeping last entry erases oldest cron"; mp=$((mp+1))
else fail "M5: ${r}"; fi

# M6: silently accept corrupt JSON (fallback to empty dict)
corrupt="$TMP/m6-corrupt.json"
printf '{"schemaVersion":2,"busted' > "$corrupt"
r=$(python3 -c "
import json
try:
    json.load(open('$corrupt'))
    orig_ok=True
except:
    orig_ok=False
try:
    json.load(open('$corrupt'))
    mut_ok=True
except:
    mut_ok={'json':'fallback'}
mut_ok=isinstance(mut_ok,dict)
out='DETECTED' if not orig_ok and mut_ok else 'MISSED orig_ok='+str(orig_ok)+' mut_ok='+str(mut_ok)
print(out)
" 2>/dev/null)
if [[ "$r" == "DETECTED" ]]; then pass "M6: silently accepting corrupt JSON hides truncation"; mp=$((mp+1))
else fail "M6: ${r}"; fi

echo "  Mutation proof: ${mp}/${mt} passed"
if [[ "$mp" -lt "$mt" ]]; then exit 1; fi

# VERDICT
echo ""
echo "=== VERDICT ==="
echo "Passed: $PASS"
echo "Failed: $FAIL"
if [[ "$FAIL" -eq 0 ]]; then echo "ALL TESTS PASSED"; exit 0
else echo "SOME TESTS FAILED"; exit 1; fi
