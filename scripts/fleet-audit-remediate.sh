#!/usr/bin/env bash
# scripts/fleet-audit-remediate.sh — Fleet audit remediation (U126)
# 30-box fleet audit (Maria + 29) — one-shot remediation script.
# Addresses 7 finding categories. Dry-run by default; --apply enables mutations.
set -euo pipefail

FLEET_AUDIT_VERSION="v1.0.0"
if [[ -d /data/.openclaw ]]; then OC_ROOT="/data/.openclaw"; PLATFORM="vps"
elif [[ -d "${HOME}/.openclaw" ]]; then OC_ROOT="${HOME}/.openclaw"; PLATFORM="mac"
else echo "ERROR: no OpenClaw root" >&2; exit 2; fi

WORKSPACE="${OC_ROOT}/workspace"; SKILLS_DIR="${OC_ROOT}/skills"
SCRIPTS_DIR="${OC_ROOT}/scripts"; BUILD_STATE="${WORKSPACE}/.workforce-build-state.json"
_APPLY=0; while [[ $# -gt 0 ]]; do case "$1" in --apply) _APPLY=1 ;; --audit-only) : ;; esac; shift; done
declare -a _FINDINGS=()
_finding() { local id="$1" s="$2" d="$3" t f="false"; t=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null); [[ "$s" == "FIXED" ]] && f="true"; _FINDINGS+=("{\"id\":\"${id}\",\"status\":\"${s}\",\"detail\":$(printf '%s' "$d" | python3 -c "import sys,json;print(json.dumps(sys.stdin.read()))" 2>/dev/null || printf '"%s"' "$d"),\"fixed\":${f},\"checked_at\":\"${t}\"}"); _log "${s}: ${d}"; }
_log() { echo "[fleet-audit] $*"; }
_fix() { echo "[fleet-audit] FIX: $*"; }

_quarantine() {
  local wf="$1" ts q; ts=$(date +%s); q="${wf}.corrupt-${ts}"
  if mv "$wf" "$q" 2>/dev/null; then
    local nt; nt=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)
    printf '{"schemaVersion":2,"interviewComplete":false,"departments":{},"_recoveryNote":"Auto-seeded by fleet-audit-remediate.sh","_recoveryTimestamp":"%s"}\n' "$nt" > "$wf"
    _finding "F6" "FIXED" "quarantined + recovery stub"
  else _finding "F6" "FAILED" "quarantine failed"; fi
}
_migrate_v2() {
  local wf="$1"; command -v python3 >/dev/null 2>&1 || { _finding "F6" "FAILED" "no python3"; return; }
  python3 -c "import json;d=json.load(open('$wf'));d['schemaVersion']=2;d.setdefault('departments',{});json.dump(d,open('$wf','w'),indent=2)" 2>/dev/null && _finding "F6" "FIXED" "migrated" || _finding "F6" "FAILED" "migrate failed"
}

check_f1() {
  _log "F1: gateway staleness"; if ! command -v openclaw >/dev/null 2>&1; then _finding "F1" "SKIP" "no openclaw"; return 0; fi
  local lv; lv=$(openclaw --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "")
  [[ -z "$lv" ]] && { _finding "F1" "SKIP" "no version"; return 0; }
  local rv=""; command -v npm >/dev/null 2>&1 && rv=$(npm view openclaw version 2>/dev/null | tr -d '[:space:]' || echo "")
  [[ -z "$rv" ]] && { _finding "F1" "WARN" "no latest"; return 0; }
  local behind=0; IFS='.' read -r la lm lp <<< "$lv"; IFS='.' read -r ra rm rp <<< "$rv"
  if [[ "$la" != "$ra" ]]; then behind=100; elif [[ "$lm" != "$rm" ]]; then behind=$(( rm - lm )); elif [[ "$lp" != "$rp" ]]; then behind=$(( rp - lp )); fi
  [[ "$behind" -lt 0 ]] && behind=0
  if [[ "$behind" -gt 2 ]]; then
    _finding "F1" "STALE" "gateway ${lv} >2 behind ${rv}"
    if [[ "$_APPLY" -eq 1 ]]; then
      if npm update -g openclaw 2>&1; then _finding "F1" "FIXED" "updated"; else _finding "F1" "FAILED" "update failed"; fi
    fi
  else _finding "F1" "OK" "gateway ${lv} (latest=${rv}, behind=${behind})"; fi
}

check_f2() {
  _log "F2: orphaned pm2"; if ! command -v pm2 >/dev/null 2>&1; then _finding "F2" "SKIP" "no pm2"; return 0; fi
  local jl; jl=$(pm2 jlist 2>/dev/null || echo "[]"); [[ -z "$jl" || "$jl" == "[]" ]] && { _finding "F2" "OK" "no processes"; return 0; }
  local orphans
  orphans=$(python3 -c "
import json,sys,os; s=sys.stdin.read(); procs=json.loads(s) if s else []
print(json.dumps([{'pm_id':p.get('pm_id',''),'name':p.get('name',''),'pid':p.get('pid','')} for p in procs if (e:=p.get('pm2_env',{}) or {}) and not os.path.isdir(e.get('PWD','') or e.get('pm_cwd','') or '.')]))
" 2>/dev/null <<< "$jl" || echo "[]")
  local n; n=$(printf '%s' "$orphans" | python3 -c "import json,sys;print(len(json.loads(sys.stdin.read())))" 2>/dev/null || echo "0")
  [[ "$n" -eq 0 ]] && { _finding "F2" "OK" "no orphans"; return 0; }
  local names; names=$(printf '%s' "$orphans" | python3 -c "import json,sys;o=json.loads(sys.stdin.read());print(', '.join(f\"{i['name']}(pm_id={i['pm_id']})\" for i in o))" 2>/dev/null || echo "?")
  _finding "F2" "ORPHAN" "${n} orphan(s): ${names}"
  if [[ "$_APPLY" -eq 1 ]]; then
    local ids del=0 fld=0; ids=$(printf '%s' "$orphans" | python3 -c "import json,sys;print(' '.join(str(i.get('pm_id','')) for i in json.loads(sys.stdin.read())))" 2>/dev/null || echo "")
    for pid in $ids; do pm2 delete "$pid" 2>&1 && del=$((del+1)) || fld=$((fld+1)); done
    [[ "$fld" -eq 0 ]] && _finding "F2" "FIXED" "deleted ${del}" || _finding "F2" "PARTIAL" "deleted ${del}; ${fld} fail"; fi
}

check_f3() {
  _log "F3: disk-usage-alert cron"; if ! command -v openclaw >/dev/null 2>&1; then _finding "F3" "SKIP" "no openclaw"; return 0; fi
  local cj; cj=$(openclaw cron list --json 2>/dev/null || echo "[]")
  local info; info=$(printf '%s' "$cj" | python3 -c "
import json,sys;d=json.loads(sys.stdin.read());jobs=d if isinstance(d,list) else d.get('jobs',[])
du=[j for j in jobs if j.get('name')=='disk-usage-alert']
if not du: print('NOT_PRESENT'); sys.exit(0)
dv=du[0].get('delivery',{}) or {}; print(json.dumps({'id':du[0].get('id',''),'mode':dv.get('mode',''),'channel':dv.get('channel',''),'to':dv.get('to','')}))" 2>/dev/null || echo "NOT_PRESENT")
  [[ "$info" == "NOT_PRESENT" ]] && { _finding "F3" "OK" "cron not present"; return 0; }
  local mo; mo=$(printf '%s' "$info" | python3 -c "import json,sys;print(json.loads(sys.stdin.read()).get('mode',''))" 2>/dev/null || echo "")
  local ch; ch=$(printf '%s' "$info" | python3 -c "import json,sys;print(json.loads(sys.stdin.read()).get('channel',''))" 2>/dev/null || echo "")
  local to; to=$(printf '%s' "$info" | python3 -c "import json,sys;print(json.loads(sys.stdin.read()).get('to',''))" 2>/dev/null || echo "")
  local ji; ji=$(printf '%s' "$info" | python3 -c "import json,sys;print(json.loads(sys.stdin.read()).get('id',''))" 2>/dev/null || echo "")
  local silent=1; [[ "$mo" == "announce" ]] || [[ -n "$ch" && -n "$to" ]] && silent=0
  if [[ "$silent" -eq 1 ]]; then
    _finding "F3" "BROKEN" "silent delivery (mode=${mo:-none})"
  else _finding "F3" "OK" "valid delivery"; fi
}

check_f4() {
  _log "F4: 0-byte decoy"; local dps=()
  for c in "/mission-control.db" "/data/mission-control.db" "${HOME}/mission-control.db" "${WORKSPACE}/mission-control.db" "${OC_ROOT}/mission-control.db"; do
    if [[ -f "$c" ]]; then local sz; sz=$(stat -f%z "$c" 2>/dev/null || stat -c%s "$c" 2>/dev/null || echo "1"); [[ "$sz" == "0" ]] && dps+=("$c"); fi
  done
  [[ ${#dps[@]} -eq 0 ]] && { _finding "F4" "OK" "no decoys"; return 0; }
  local dl; dl=$(printf '%s, ' "${dps[@]}"); dl="${dl%, }"; _finding "F4" "DECOY" "${#dps[@]} decoy(s): ${dl}"
  if [[ "$_APPLY" -eq 1 ]]; then local r=0; for p in "${dps[@]}"; do rm -f "$p" 2>/dev/null && r=$((r+1)); done; _finding "F4" "FIXED" "removed ${r}"; fi
}

check_f5() {
  _log "F5: duplicate crons"; if ! command -v openclaw >/dev/null 2>&1; then _finding "F5" "SKIP" "no openclaw"; return 0; fi
  local cj; cj=$(openclaw cron list --json 2>/dev/null || echo "[]")
  local dups; dups=$(printf '%s' "$cj" | python3 -c "
import json,sys;from collections import Counter
d=json.loads(sys.stdin.read());jobs=d if isinstance(d,list) else d.get('jobs',[])
cnt=Counter(j.get('name','') for j in jobs);dups={n:c for n,c in cnt.items() if c>1}
r=[]; [r.append({'name':n,'count':c,'remove':[sorted([j for j in jobs if j.get('name')==n],key=lambda x:x.get('id',''))[k].get('id','') for k in range(1,c)]}) for n,c in dups.items()]
print(json.dumps(r))" 2>/dev/null || echo "[]")
  local dc; dc=$(printf '%s' "$dups" | python3 -c "import json,sys;print(len(json.loads(sys.stdin.read())))" 2>/dev/null || echo "0")
  [[ "$dc" -eq 0 ]] && { _finding "F5" "OK" "no duplicates"; return 0; }
  local dn; dn=$(printf '%s' "$dups" | python3 -c "import json,sys;o=json.loads(sys.stdin.read());print(', '.join(f\"{i['name']}(x{i['count']})\" for i in o))" 2>/dev/null || echo "?")
  _finding "F5" "DUPLICATE" "${dc} dup(s): ${dn}"
  if [[ "$_APPLY" -eq 1 ]]; then
    local rids tr=0; rids=$(printf '%s' "$dups" | python3 -c "import json,sys;o=json.loads(sys.stdin.read());ids=[];[ids.extend(i.get('remove',[])) for i in o];print(' '.join(ids))" 2>/dev/null || echo "")
    for rid in $rids; do openclaw cron rm "$rid" >/dev/null 2>&1 && tr=$((tr+1)); done
    _finding "F5" "FIXED" "removed ${tr}"; fi
}

check_f6() {
  _log "F6: build-state integrity"; local wf="$BUILD_STATE"
  [[ ! -f "$wf" ]] && { _finding "F6" "OK" "no build-state"; return 0; }
  local sz; sz=$(stat -f%z "$wf" 2>/dev/null || stat -c%s "$wf" 2>/dev/null || echo "0")
  [[ "$sz" -eq 0 ]] && { _finding "F6" "CORRUPT" "0-byte"; [[ "$_APPLY" -eq 1 ]] && _quarantine "$wf" "0-byte"; return 0; }
  local r; r=$(python3 -c "
import json,sys;wf=sys.argv[1]
try:d=json.load(open(wf))
except json.JSONDecodeError:print('JSON_ERROR');sys.exit(0)
except:print('READ_ERROR');sys.exit(0)
sv=d.get('schemaVersion');print('NO_SCHEMA' if sv is None else ('FUTURE:'+str(sv) if isinstance(sv,int) and sv>100 else ('OK:'+str(sv) if isinstance(sv,int) and sv>0 else 'INVALID')))
" "$wf" 2>/dev/null || echo "PYTHON_UNAVAILABLE")
  case "$r" in
    JSON_ERROR) _finding "F6" "CORRUPT" "invalid JSON"; [[ "$_APPLY" -eq 1 ]] && _quarantine "$wf" "invalid JSON" ;;
    NO_SCHEMA) _finding "F6" "STALE" "no schemaVersion"; [[ "$_APPLY" -eq 1 ]] && _migrate_v2 "$wf" ;;
    FUTURE:*) _finding "F6" "WARN" "future";;
    OK:*) _finding "F6" "OK" "valid sv=${r#OK:}";;
    INVALID) _finding "F6" "CORRUPT" "invalid sv";;
    PYTHON_UNAVAILABLE) _finding "F6" "SKIP" "python3 absent";;
  esac
}

check_f7() {
  _log "F7: workspace seeding"; local pw="${WORKSPACE}/podcast-production-engine" aw="${WORKSPACE}/anthology-engine" ps="false" as="false"
  [[ -d "$pw" && -n "$(ls -A "$pw" 2>/dev/null)" ]] && ps="true"
  [[ -d "$aw" && -n "$(ls -A "$aw" 2>/dev/null)" ]] && as="true"
  [[ "$ps" == "true" && "$as" == "true" ]] && { _finding "F7" "OK" "seeded"; return 0; }
  local us=""; [[ "$ps" != "true" ]] && us="${us}podcast "; [[ "$as" != "true" ]] && us="${us}anthology "; us="${us% }"
  _finding "F7" "UNSEEDED" "missing: ${us}"
  if [[ "$_APPLY" -eq 1 ]]; then local sa=0
    [[ "$ps" != "true" ]] && mkdir -p "$pw" 2>/dev/null && touch "$pw/.seeded" 2>/dev/null && sa=1
    [[ "$as" != "true" ]] && mkdir -p "$aw" 2>/dev/null && touch "$aw/.seeded" 2>/dev/null && sa=1
    [[ "$sa" -eq 1 ]] && _finding "F7" "FIXED" "seeded" || _finding "F7" "FAILED" "seed failed"; fi
}

main() {
  echo "=== fleet-audit-remediate.sh ${FLEET_AUDIT_VERSION} ==="
  _log "platform=${PLATFORM}"; check_f1; check_f2; check_f3; check_f4; check_f5; check_f6; check_f7
  local t=${#_FINDINGS[@]}; local ok=0 skip=0 fixed=0 failed=0 issues=0
  for f in "${_FINDINGS[@]}"; do
    local s; s=$(printf '%s' "$f" | python3 -c "import json,sys;print(json.loads(sys.stdin.read()).get('status',''))" 2>/dev/null || echo "")
    case "$s" in OK) ok=$((ok+1)) ;; SKIP) skip=$((skip+1)) ;; FIXED) fixed=$((fixed+1)) ;; FAILED) failed=$((failed+1)) ;; *) issues=$((issues+1)) ;; esac
  done
  _log "SUMMARY: ${t} checks -- ${ok} OK, ${skip} SKIP, ${fixed} FIXED, ${issues} issues, ${failed} FAILED"
  if [[ "$_APPLY" -eq 1 ]]; then [[ "$failed" -gt 0 ]] && exit 1 || exit 0
  else [[ "$((issues+failed))" -gt 0 ]] && { _log "dry-run -- $((issues+failed)) finding(s). Re-run with --apply."; exit 3; } || exit 0; fi
}
main "$@"
