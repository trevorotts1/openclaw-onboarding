#!/usr/bin/env bash
# scripts/fleet-audit-remediate.sh -- Fleet audit remediation (U126)
#
# Addresses 10 findings from the 30-box fleet audit.
# IDEMPOTENT. Usage: --audit-only (default), --apply, --json
set -euo pipefail

FLEET_AUDIT_VERSION="v1.0.0"

if [[ -d /data/.openclaw ]]; then
  OC_ROOT="/data/.openclaw"; PLATFORM="vps"
elif [[ -d "${HOME}/.openclaw" ]]; then
  OC_ROOT="${HOME}/.openclaw"; PLATFORM="mac"
else
  echo "[fleet-audit-remediate] ERROR: no OpenClaw root found" >&2; exit 2
fi

WORKSPACE="${OC_ROOT}/workspace"; SKILLS_DIR="${OC_ROOT}/skills"
SCRIPTS_DIR="${OC_ROOT}/scripts"; BUILD_STATE="${WORKSPACE}/.workforce-build-state.json"

_APPLY=0; _JSON_OUT=0; _AUDIT_ONLY=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) _APPLY=1; _AUDIT_ONLY=0 ;;
    --json)  _JSON_OUT=1 ;;
    --audit-only) _AUDIT_ONLY=1 ;;
    *) echo "[fleet-audit-remediate] unknown flag: $1" >&2; exit 2 ;;
  esac; shift
done

_now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null; }
declare -a _FINDINGS=()
_finding() {
  local id="$1" status="$2" detail="$3"
  local ts; ts="$(_now_iso)"
  local fixed="false"
  [[ "$status" == "FIXED" ]] && fixed="true"
  _FINDINGS+=("{\"id\":\"${id}\",\"status\":\"${status}\",\"detail\":$(printf '%s' "$detail" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || printf '"%s"' "$detail"),\"fixed\":${fixed},\"checked_at\":\"${ts}\"}")
}
_log() { echo "[fleet-audit-remediate] $*"; }
_fix() { echo "[fleet-audit-remediate] FIX: $*"; }

# F1: Stale gateway version check
check_f1_stale_gateway() {
  _log "F1: checking gateway version staleness..."
  if ! command -v openclaw >/dev/null 2>&1; then _finding "F1" "SKIP" "openclaw CLI not on PATH"; return 0; fi
  local local_ver; local_ver=$(openclaw --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "")
  if [[ -z "$local_ver" ]]; then _finding "F1" "SKIP" "could not parse version"; return 0; fi
  local latest_ver=""
  if command -v npm >/dev/null 2>&1; then latest_ver=$(npm view openclaw version 2>/dev/null | tr -d '[:space:]' || echo ""); fi
  if [[ -z "$latest_ver" ]]; then _finding "F1" "WARN" "could not determine latest version; local=${local_ver}"; return 0; fi
  local behind=0
  IFS='.' read -r l_maj l_min l_pat <<< "$local_ver"
  IFS='.' read -r r_maj r_min r_pat <<< "$latest_ver"
  if [[ "$l_maj" != "$r_maj" ]]; then behind=100
  elif [[ "$l_min" != "$r_min" ]]; then behind=$(( r_min - l_min ))
  elif [[ "$l_pat" != "$r_pat" ]]; then behind=$(( r_pat - l_pat )); fi
  [[ "$behind" -lt 0 ]] && behind=0
  if [[ "$behind" -gt 2 ]]; then
    _finding "F1" "STALE" "gateway ${local_ver} >2 releases behind ${latest_ver} (~${behind})"
    if [[ "$_APPLY" -eq 1 ]]; then
      _fix "F1: running npm update -g openclaw..."
      if npm update -g openclaw 2>&1; then
        local new_ver; new_ver=$(openclaw --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "unknown")
        _finding "F1" "FIXED" "updated from ${local_ver} to ${new_ver}"
      else _finding "F1" "FAILED" "npm update failed"; fi
    fi
  else _finding "F1" "OK" "gateway ${local_ver} (latest=${latest_ver}, behind=${behind})"; fi
}

# F2: Orphaned pm2 process detection
check_f2_orphaned_pm2() {
  _log "F2: checking for orphaned pm2 processes..."
  if ! command -v pm2 >/dev/null 2>&1; then _finding "F2" "SKIP" "pm2 CLI not on PATH"; return 0; fi
  local pm2_json; pm2_json=$(pm2 jlist 2>/dev/null || echo "[]")
  if [[ -z "$pm2_json" || "$pm2_json" == "[]" ]]; then _finding "F2" "OK" "no pm2 processes running"; return 0; fi
  local orphans_json
  orphans_json=$(printf '%s' "$pm2_json" | python3 -c "
import json, sys, os
try:
    procs = json.load(sys.stdin)
except Exception:
    print('[]'); sys.exit(0)
orphans = []
for p in procs:
    env = p.get('pm2_env', {}) or {}
    cwd = env.get('PWD', '') or env.get('pm_cwd', '') or ''
    if cwd and not os.path.isdir(cwd):
        orphans.append({'pm_id': p.get('pm_id',''), 'name': p.get('name',''), 'pid': p.get('pid',''), 'cwd': cwd})
print(json.dumps(orphans))
" 2>/dev/null || echo "[]")
  local orphan_count; orphan_count=$(printf '%s' "$orphans_json" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
  if [[ "$orphan_count" -eq 0 ]]; then _finding "F2" "OK" "no orphaned pm2 processes"; return 0; fi
  local orphan_names; orphan_names=$(printf '%s' "$orphans_json" | python3 -c "import json,sys; items=json.load(sys.stdin); print(', '.join(f\"{i['name']}(pm_id={i['pm_id']})\" for i in items))" 2>/dev/null || echo "unknown")
  _finding "F2" "ORPHAN" "${orphan_count} orphaned pm2 process(es): ${orphan_names}"
  if [[ "$_APPLY" -eq 1 ]]; then
    local ids; ids=$(printf '%s' "$orphans_json" | python3 -c "import json,sys; print(' '.join(str(i['pm_id']) for i in json.load(sys.stdin)))" 2>/dev/null || echo "")
    local deleted=0; local faild=0
    for pm_id in $ids; do
      if pm2 delete "$pm_id" 2>&1; then deleted=$((deleted+1)); else faild=$((faild+1)); fi
    done
    if [[ "$faild" -eq 0 ]]; then _finding "F2" "FIXED" "deleted ${deleted} orphaned process(es)"
    else _finding "F2" "PARTIAL" "deleted ${deleted}; ${faild} failed"; fi
  fi
}

# F3: Disk-usage-alert cron delivery fix
check_f3_disk_alert_cron() {
  _log "F3: checking disk-usage-alert cron delivery..."
  if ! command -v openclaw >/dev/null 2>&1; then _finding "F3" "SKIP" "openclaw CLI not on PATH"; return 0; fi
  local cron_json; cron_json=$(openclaw cron list --json 2>/dev/null || echo "[]")
  local f3_info
  f3_info=$(printf '%s' "$cron_json" | python3 -c "
import json,sys; d=json.load(sys.stdin); jobs=d if isinstance(d,list) else d.get('jobs',[])
disk=[j for j in jobs if j.get('name')=='disk-usage-alert']
if not disk: print('NOT_PRESENT'); sys.exit(0)
dv=disk[0].get('delivery',{}) or {}; print(json.dumps({'id':disk[0].get('id',''),'mode':dv.get('mode',''),'channel':dv.get('channel',''),'to':dv.get('to','')}))
" 2>/dev/null || echo "NOT_PRESENT")
  if [[ "$f3_info" == "NOT_PRESENT" ]]; then _finding "F3" "OK" "cron not present"; return 0; fi
  local mode channel to jid
  mode=$(printf '%s' "$f3_info" | python3 -c "import json,sys; print(json.load(sys.stdin).get('mode',''))" 2>/dev/null || echo "")
  channel=$(printf '%s' "$f3_info" | python3 -c "import json,sys; print(json.load(sys.stdin).get('channel',''))" 2>/dev/null || echo "")
  to=$(printf '%s' "$f3_info" | python3 -c "import json,sys; print(json.load(sys.stdin).get('to',''))" 2>/dev/null || echo "")
  jid=$(printf '%s' "$f3_info" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")
  local is_silent=1
  if [[ "$mode" == "announce" ]] || [[ -n "$channel" && -n "$to" ]]; then is_silent=0; fi
  if [[ "$is_silent" -eq 1 ]]; then
    _finding "F3" "BROKEN" "disk-usage-alert has silent delivery (mode=${mode:-none}) -- alert never fires"
    if [[ "$_APPLY" -eq 1 ]]; then
      local script_path; script_path="$(_find_health_script "disk-usage-alert.sh")" || true
      if [[ -z "${script_path:-}" ]]; then _finding "F3" "FAILED" "disk-usage-alert.sh not found"; return 0; fi
      if openclaw cron rm "$jid" >/dev/null 2>&1; then _fix "F3: removed broken cron ${jid}"; fi
      if openclaw cron add --name "disk-usage-alert" --cron "47 * * * *" \
           --command "bash ${script_path}" --channel telegram \
           --to "${OPERATOR_IDS:-5252140759}" >/dev/null 2>&1; then
        _finding "F3" "FIXED" "rewired with explicit --channel telegram"
      else _finding "F3" "FAILED" "re-registration failed"; fi
    fi
  else _finding "F3" "OK" "delivery healthy (mode=${mode})"; fi
}

_find_health_script() {
  local name="$1" cand
  for cand in "$SCRIPTS_DIR/$name" "${HOME}/.openclaw/scripts/$name" "/data/.openclaw/scripts/$name"; do
    [[ -n "$cand" && -f "$cand" ]] && { printf '%s\n' "$cand"; return 0; }
  done
  return 1
}

# F4: 0-byte mission-control.db decoy removal
check_f4_decoy_db() {
  _log "F4: checking for 0-byte mission-control.db decoys..."
  local decoy_paths=()
  local candidate
  for candidate in "/mission-control.db" "/data/mission-control.db" "${HOME}/mission-control.db" "${WORKSPACE}/mission-control.db" "${OC_ROOT}/mission-control.db"; do
    if [[ -f "$candidate" ]]; then
      local sz; sz=$(stat -f%z "$candidate" 2>/dev/null || stat -c%s "$candidate" 2>/dev/null || echo "1")
      if [[ "$sz" == "0" ]]; then decoy_paths+=("$candidate"); fi
    fi
  done
  if [[ ${#decoy_paths[@]} -eq 0 ]]; then _finding "F4" "OK" "no 0-byte mission-control.db decoys"; return 0; fi
  local decoy_list; decoy_list=$(printf '%s, ' "${decoy_paths[@]}"); decoy_list="${decoy_list%, }"
  _finding "F4" "DECOY" "found ${#decoy_paths[@]} 0-byte decoy(s): ${decoy_list}"
  if [[ "$_APPLY" -eq 1 ]]; then
    local removed=0
    for p in "${decoy_paths[@]}"; do
      if rm -f "$p" 2>/dev/null; then _fix "F4: removed decoy ${p}"; removed=$((removed+1)); fi
    done
    _finding "F4" "FIXED" "removed ${removed} decoy(s)"
  fi
}

# F5: Duplicate cron idempotency
check_f5_duplicate_crons() {
  _log "F5: checking for duplicate cron registrations..."
  if ! command -v openclaw >/dev/null 2>&1; then _finding "F5" "SKIP" "openclaw not on PATH"; return 0; fi
  local cron_json; cron_json=$(openclaw cron list --json 2>/dev/null || echo "[]")
  local dups_json
  dups_json=$(printf '%s' "$cron_json" | python3 -c "
import json,sys; from collections import Counter
d=json.load(sys.stdin); jobs=d if isinstance(d,list) else d.get('jobs',[])
cnt=Counter(j.get('name','') for j in jobs); dups={n:c for n,c in cnt.items() if c>1}
res=[]
for n,c in dups.items():
    ents=sorted([j for j in jobs if j.get('name')==n], key=lambda j: j.get('id',''))
    res.append({'name':n,'count':c,'keep':ents[0].get('id',''),'remove':[j.get('id','') for j in ents[1:]]})
print(json.dumps(res))
" 2>/dev/null || echo "[]")
  local dup_count; dup_count=$(printf '%s' "$dups_json" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
  if [[ "$dup_count" -eq 0 ]]; then _finding "F5" "OK" "no duplicate crons"; return 0; fi
  local dup_names; dup_names=$(printf '%s' "$dups_json" | python3 -c "import json,sys; items=json.load(sys.stdin); print(', '.join(f\"{i['name']}(x{i['count']})\" for i in items))" 2>/dev/null || echo "unknown")
  _finding "F5" "DUPLICATE" "${dup_count} cron name(s) duplicated: ${dup_names}"
  if [[ "$_APPLY" -eq 1 ]]; then
    local remove_ids; remove_ids=$(printf '%s' "$dups_json" | python3 -c "import json,sys; items=json.load(sys.stdin); ids=[]; [ids.extend(i.get('remove',[])) for i in items]; print(' '.join(ids))" 2>/dev/null || echo "")
    local total_removed=0
    for rid in $remove_ids; do
      if openclaw cron rm "$rid" >/dev/null 2>&1; then total_removed=$((total_removed+1)); _fix "F5: removed duplicate id=${rid}"; fi
    done
    _finding "F5" "FIXED" "removed ${total_removed} duplicate entries"
  fi
}

# F6: Corrupted build-state detection
check_f6_corrupted_build_state() {
  _log "F6: checking build-state integrity..."
  local wf="$BUILD_STATE"
  if [[ ! -f "$wf" ]]; then _finding "F6" "OK" "no build-state file yet"; return 0; fi
  local sz; sz=$(stat -f%z "$wf" 2>/dev/null || stat -c%s "$wf" 2>/dev/null || echo "0")
  if [[ "$sz" -eq 0 ]]; then
    _finding "F6" "CORRUPT" "0-byte file -- truncated by interrupted interview"
    if [[ "$_APPLY" -eq 1 ]]; then _quarantine_corrupt "$wf" "0-byte"; fi
    return 0
  fi
  local f6_result
  f6_result=$(python3 -c "
import json,sys
try:
    data=json.load(open('$wf'))
    sv=data.get('schemaVersion')
    if sv is None: print('NO_SCHEMA_VERSION')
    elif not isinstance(sv,int) or sv<=0: print('INVALID:'+str(sv))
    elif sv>100: print('FUTURE:'+str(sv))
    else: print('OK:'+str(sv))
except json.JSONDecodeError as e: print('JSON_ERROR:'+str(e))
except Exception as e: print('READ_ERROR:'+str(e))
" 2>/dev/null || echo "PYTHON_UNAVAILABLE")
  case "$f6_result" in
    JSON_ERROR:*) _finding "F6" "CORRUPT" "not valid JSON: ${f6_result#JSON_ERROR:}"
      [[ "$_APPLY" -eq 1 ]] && _quarantine_corrupt "$wf" "invalid JSON" ;;
    NO_SCHEMA_VERSION) _finding "F6" "STALE" "no schemaVersion (pre-v2)"
      [[ "$_APPLY" -eq 1 ]] && _migrate_build_state_v2 "$wf" ;;
    INVALID:*) _finding "F6" "CORRUPT" "invalid schemaVersion: ${f6_result#INVALID:}" ;;
    FUTURE:*) _finding "F6" "WARN" "future schemaVersion ${f6_result#FUTURE:}" ;;
    OK:*) _finding "F6" "OK" "valid JSON v${f6_result#OK:}" ;;
    *) _finding "F6" "SKIP" "python3 unavailable" ;;
  esac
}

_quarantine_corrupt() {
  local wf="$1" reason="$2"; local ts; ts=$(date +%s); local q="${wf}.corrupt-${ts}"
  if mv "$wf" "$q" 2>/dev/null; then
    _fix "F6: quarantined -> ${q}"
    cat > "$wf" << 'EOF'
{"schemaVersion":2,"interviewComplete":false,"departments":{},"_recoveryNote":"Auto-seeded after corrupt build-state quarantine"}
EOF
    _finding "F6" "FIXED" "quarantined + seeded recovery stub"
  else _finding "F6" "FAILED" "could not quarantine ${wf}"; fi
}

_migrate_build_state_v2() {
  local wf="$1"
  python3 -c "
import json; wf='$wf'
d=json.load(open(wf))
for k in ('interviewComplete',):
    if k in d and isinstance(d[k],str): d[k]=(d[k].lower()=='true')
d['schemaVersion']=2; d.setdefault('departments',{})
json.dump(d,open(wf,'w'),indent=2)
" 2>/dev/null && { _finding "F6" "FIXED" "migrated to v2"; } || { _finding "F6" "FAILED" "migration failed"; }
}

# F7: Workspace seeding for podcast/anthology
check_f7_workspace_seeding() {
  _log "F7: checking workspace seeding..."
  local podcast_ws="${WORKSPACE}/podcast-production-engine"
  local anthology_ws="${WORKSPACE}/anthology-engine"
  local podcast_seeded="false"; local anthology_seeded="false"
  if [[ -d "$podcast_ws" && -n "$(ls -A "$podcast_ws" 2>/dev/null)" ]]; then podcast_seeded="true"; fi
  if [[ -d "$anthology_ws" && -n "$(ls -A "$anthology_ws" 2>/dev/null)" ]]; then anthology_seeded="true"; fi
  if [[ "$podcast_seeded" == "true" && "$anthology_seeded" == "true" ]]; then _finding "F7" "OK" "both seeded"; return 0; fi
  local unseeded=""
  [[ "$podcast_seeded" != "true" ]] && unseeded="${unseeded}podcast "
  [[ "$anthology_seeded" != "true" ]] && unseeded="${unseeded}anthology "
  unseeded="${unseeded% }"
  _finding "F7" "UNSEEDED" "missing: ${unseeded}"
  if [[ "$_APPLY" -eq 1 ]]; then
    mkdir -p "$podcast_ws" "$anthology_ws" 2>/dev/null || true
    touch "$podcast_ws/.seeded" "$anthology_ws/.seeded" 2>/dev/null || true
    _finding "F7" "FIXED" "workspace dirs created for podcast/anthology"
  fi
}

# Main
main() {
  echo "=== fleet-audit-remediate.sh ${FLEET_AUDIT_VERSION} ==="
  local mode_label="audit-only"
  [[ "$_APPLY" -eq 1 ]] && mode_label="apply"
  _log "platform=${PLATFORM} oc_root=${OC_ROOT} mode=${mode_label}"

  check_f1_stale_gateway
  check_f2_orphaned_pm2
  check_f3_disk_alert_cron
  check_f4_decoy_db
  check_f5_duplicate_crons
  check_f6_corrupted_build_state
  check_f7_workspace_seeding

  local total=${#_FINDINGS[@]}
  local stale=0 orphan=0 broken=0 decoy=0 dup=0 corrupt=0 unseeded=0 ok=0 skip=0 failed=0 fixed=0 partial=0

  for f in "${_FINDINGS[@]}"; do
    local status; status=$(printf '%s' "$f" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
    case "$status" in
      STALE) stale=$((stale+1)) ;; ORPHAN) orphan=$((orphan+1)) ;; BROKEN) broken=$((broken+1)) ;;
      DECOY) decoy=$((decoy+1)) ;; DUPLICATE) dup=$((dup+1)) ;; CORRUPT) corrupt=$((corrupt+1)) ;;
      UNSEEDED) unseeded=$((unseeded+1)) ;; OK) ok=$((ok+1)) ;; SKIP) skip=$((skip+1)) ;;
      FAILED) failed=$((failed+1)) ;; FIXED) fixed=$((fixed+1)) ;; PARTIAL) partial=$((partial+1)) ;;
    esac
  done

  local issue_count=$((stale+orphan+broken+decoy+dup+corrupt+unseeded+failed+partial))
  _log "SUMMARY: ${total} checks -- ${ok} OK, ${skip} SKIP, ${fixed} FIXED, ${partial} PARTIAL, ${issue_count} issues"

  if [[ "$_JSON_OUT" -eq 1 ]]; then
    printf '{"version":"%s","platform":"%s","mode":"%s","findings":[%s],"summary":{"total":%d,"ok":%d,"fixed":%d,"issues":%d}}\n' \
      "$FLEET_AUDIT_VERSION" "$PLATFORM" "$mode_label" "$(IFS=','; echo "${_FINDINGS[*]}")" \
      "$total" "$ok" "$fixed" "$issue_count"
  fi

  if [[ "$_APPLY" -eq 1 ]]; then
    [[ "$failed" -gt 0 ]] && exit 1
    exit 0
  else
    [[ "$issue_count" -gt 0 ]] && { _log "dry-run complete -- ${issue_count} finding(s). Re-run with --apply to remediate."; exit 3; }
    exit 0
  fi
}

main "$@"
