#!/usr/bin/env bash
# lib-interview-rate-limit.sh -- Rate-limiting gate for interview submission
set -euo pipefail
: "${INTERVIEW_RATE_LIMIT_MAX:=5}"
: "${INTERVIEW_RATE_LIMIT_WINDOW_SECONDS:=3600}"
_rate_limit_state_file() {
  if [ -d /data/.openclaw/workspace ]; then printf '%s' "/data/.openclaw/workspace/.interview-rate-limit.json"
  elif [ -d "$HOME/.openclaw/workspace" ]; then printf '%s' "$HOME/.openclaw/workspace/.interview-rate-limit.json"
  else local _ws="${OC_WORKSPACE_DEFAULT:-}"
    if [ -n "$_ws" ] && [ -d "$_ws" ]; then printf '%s' "$_ws/.interview-rate-limit.json"
    else printf ''; fi
  fi
}
check_interview_rate_limit() {
  local _session="$1"; local _now _rl_file _max _window
  _now="$(date -u +%s)"; _rl_file="$(_rate_limit_state_file)"
  _max="${INTERVIEW_RATE_LIMIT_MAX}"; _window="${INTERVIEW_RATE_LIMIT_WINDOW_SECONDS}"
  if [ -z "$_rl_file" ]; then printf 'RATE-LIMIT: no state file path - REFUSED\n' >&2; return 1; fi
  mkdir -p "$(dirname "$_rl_file")" 2>/dev/null || true
  local -a _timestamps=()
  if [ -f "$_rl_file" ]; then
    IFS=' ' read -r -a _timestamps <<< "$(python3 -c "import json,sys
try:
    d=json.load(open(sys.argv[1]))
    for ts in d.get('sessions',{}).get(sys.argv[2],[]): print(ts,end=' ')
except: sys.exit(0)" "$_rl_file" "$_session" 2>/dev/null || true)"
  fi
  local _cutoff=$(( _now - _window )); local -a _active=()
  for _ts in "${_timestamps[@]:-}"; do
    if [ -n "$_ts" ] && [ "$_ts" -ge "$_cutoff" ] 2>/dev/null; then _active+=("$_ts"); fi
  done
  if [ "${#_active[@]}" -ge "$_max" ]; then
    local _oldest="${_active[0]}"; local _retry_after=$(( _oldest + _window - _now ))
    printf 'RATE-LIMIT: session %s has %d submissions (max %d). Retry in %ds.\n' "$_session" "${#_active[@]}" "$_max" "$_retry_after" >&2
    return 1
  fi
  _active+=("$_now")
  python3 -c "import json,os,sys,tempfile
r,s,n,c=sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4])
try:
    with open(r) as f: data=json.load(f)
except: data={}
se=data.setdefault('sessions',{})
ts=[t for t in se.get(s,[]) if isinstance(t,int) and t>=c]; ts.append(n); se[s]=ts
d=os.path.dirname(os.path.abspath(r)) or '.'
fd,t=tempfile.mkstemp(dir=d,prefix='.rl-',suffix='.tmp')
try:
    with os.fdopen(fd,'w') as fh: json.dump(data,fh,indent=2); fh.flush(); os.fsync(fh.fileno())
    os.replace(t,r)
except:
    if os.path.exists(t): os.unlink(t); raise
" "$_rl_file" "$_session" "$_now" "$_cutoff" || { printf 'RATE-LIMIT: write failed - REFUSED\n' >&2; return 1; }
  return 0
}
interview_session_id() {
  local _state_dir
  if [ -d /data/.openclaw/workspace ]; then _state_dir=/data/.openclaw/workspace
  elif [ -d "$HOME/.openclaw/workspace" ]; then _state_dir="$HOME/.openclaw/workspace"
  else _state_dir="${OC_WORKSPACE_DEFAULT:-}"; fi
  if [ -n "$_state_dir" ] && [ -f "$_state_dir/.workforce-build-state.json" ]; then
    local _sid
    _sid="$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));s=d.get('interviewProgress',{}).get('lastQuestionAskedBy') or d.get('interviewSessionId') or '';print(s,end='')" "$_state_dir/.workforce-build-state.json" 2>/dev/null || true)"
    if [ -n "$_sid" ]; then printf '%s' "$_sid"; return 0; fi
  fi
  printf 'box:unknown'
}
