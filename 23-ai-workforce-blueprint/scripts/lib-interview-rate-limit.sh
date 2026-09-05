#!/usr/bin/env bash
# lib-interview-rate-limit.sh -- Rate-limiting gate for interview submission
set -euo pipefail
# Default budget: 60 submissions per rolling hour (env-overridable). The prior
# default of 5/hour was the other half of the P0 rate-limit incident (2026-07,
# a real client interview): a real client typing answers on a phone, or clicking through
# department Yes/No/Later cards, clears 5 inside minutes -- so the very first
# genuine interview tripped this "anti-abuse" ceiling before abuse was ever in
# question. 60 is one submission per minute sustained for a full hour:
# comfortably above any human pace (a ~25-35 question interview, or a ~28-42
# department decision pass) while still bounding a runaway/scripted caller.
# Still fully env-overridable -- a box running hotter can raise it further
# (the affected client's box currently carries an interim
# INTERVIEW_RATE_LIMIT_MAX=30 override; this default is meant to make that
# per-box override unnecessary going forward, not to cap anyone below it).
: "${INTERVIEW_RATE_LIMIT_MAX:=60}"
: "${INTERVIEW_RATE_LIMIT_WINDOW_SECONDS:=3600}"
# The Command Center's /api/interview/answer route (src/app/api/interview/answer/
# route.ts) defaults its --asked-by argument to this EXACT literal whenever a
# request carries no Cf-Access-Authenticated-User-Email / x-operator-email /
# explicit askedBy -- which is ALWAYS true for a Telegram-conducted or otherwise
# unauthenticated session. THE P0 INCIDENT: that literal was used directly as
# the rate-limit bucket key, so every unauthenticated interview session on a box
# shared ONE ledger bucket -- whichever session answered first exhausted the
# shared budget and every other session (or every later stretch of the SAME
# session, once even the interview_session_id() fallback below degraded to the
# same literal) was silently refused. interview_rate_limit_session_key() below
# is the fix: this sentinel is never allowed to become a bucket key, from any
# caller, present or future.
INTERVIEW_RATE_LIMIT_SHARED_LITERAL_SENTINEL="interview-web"
_rate_limit_state_file() {
  # An explicitly configured ledger keeps offline fixtures and separately
  # provisioned runtimes out of another installation's default workspace.
  # Reject relative paths instead of silently falling back to a shared ledger.
  if [ "${INTERVIEW_RATE_LIMIT_STATE_FILE+x}" = x ]; then
    case "$INTERVIEW_RATE_LIMIT_STATE_FILE" in
      /*) printf '%s' "$INTERVIEW_RATE_LIMIT_STATE_FILE" ;;
      *) printf '' ;;
    esac
    return 0
  fi
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
    # FIX (P0 incident): prefer the STABLE interviewSessionId over
    # lastQuestionAskedBy. The old order read lastQuestionAskedBy FIRST, and
    # once a rate-limited caller had ever stamped that field with the shared
    # "interview-web" literal, this fallback resolver read the SAME literal
    # straight back out of build-state -- so even this "fix path" reproduced
    # the shared bucket. Both candidates are also rejected outright if they
    # happen to equal the sentinel, so a legacy/pre-fix state file can never
    # hand the sentinel back out either.
    _sid="$(python3 -c "import json,sys
sentinel = sys.argv[2]
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print('', end='')
    raise SystemExit(0)
sid = d.get('interviewSessionId') or ''
if not sid or sid == sentinel:
    by = (d.get('interviewProgress') or {}).get('lastQuestionAskedBy') or ''
    if by and by != sentinel:
        sid = by
    else:
        sid = ''
print(sid, end='')
" "$_state_dir/.workforce-build-state.json" "$INTERVIEW_RATE_LIMIT_SHARED_LITERAL_SENTINEL" 2>/dev/null || true)"
    if [ -n "$_sid" ]; then printf '%s' "$_sid"; return 0; fi
  fi
  printf 'box:unknown'
}

# Resolve the ledger bucket key for a rate-limited request.
#
# Precedence (highest first):
#   1. $1, an explicit session id the caller already resolved/minted for this
#      request (e.g. the Command Center's stable interviewSessionId, or
#      $INTERVIEW_SESSION_ID) -- used whenever it is non-empty and is not
#      itself the shared-literal sentinel.
#   2. $2, the --asked-by value, PRESERVED AS-IS for the authenticated path --
#      a real Cf-Access / operator email (or an agent identity such as
#      SKILL.md's $AGENT_NAME) is a legitimate per-caller bucket key and this
#      branch must not change that behavior. SKIPPED only when it is empty or
#      equals the shared-literal sentinel, so that literal can never become a
#      bucket key again, from any caller, present or future.
#   3. interview_session_id() -- reads the stable interviewSessionId straight
#      out of build-state, so even a caller supplying neither (1) nor a real
#      (2) still lands on a per-interview bucket instead of colliding with
#      every other unauthenticated session on the box.
interview_rate_limit_session_key() {
  local _explicit="${1:-}"; local _asked_by="${2:-}"
  if [ -n "$_explicit" ] && [ "$_explicit" != "$INTERVIEW_RATE_LIMIT_SHARED_LITERAL_SENTINEL" ]; then
    printf '%s' "$_explicit"; return 0
  fi
  if [ -n "$_asked_by" ] && [ "$_asked_by" != "$INTERVIEW_RATE_LIMIT_SHARED_LITERAL_SENTINEL" ]; then
    printf '%s' "$_asked_by"; return 0
  fi
  interview_session_id
}
