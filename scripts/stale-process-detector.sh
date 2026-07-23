#!/usr/bin/env bash
# stale-process-detector.sh — U126 fleet-audit: gateway staleness + orphaned pm2 cleanup.
STALE_PROCESS_DETECTOR_VERSION="v14.1.10"
set -u
if [[ -d /data/.openclaw ]]; then OC_ROOT=/data/.openclaw
elif [[ -d "${HOME}/.openclaw" ]]; then OC_ROOT="${HOME}/.openclaw"
else echo "[stale-process-detector] no OpenClaw root found" >&2; exit 2; fi
STALE_LOG="$OC_ROOT/stale-process-detector.log"
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2" >> "$STALE_LOG" 2>/dev/null || true; printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2"; }
GATEWAY_STALE=0; PM2_ORPHANS=0
check_gateway_staleness() {
  command -v openclaw >/dev/null 2>&1 || { log "WARN" "openclaw CLI not found"; return 2; }
  command -v npm >/dev/null 2>&1 || { log "WARN" "npm not found"; return 2; }
  local installed; installed=$(openclaw --version 2>/dev/null|grep -oE '[0-9]+\.[0-9]+\.[0-9]+'|head -1||true)
  [[ -z "$installed" ]] && { log "WARN" "cannot parse installed openclaw version"; return 2; }
  local latest; latest=$(npm view openclaw version 2>/dev/null|grep -oE '^[0-9]+\.[0-9]+\.[0-9]+'|head -1||true)
  [[ -z "$latest" ]] && { log "WARN" "cannot resolve latest openclaw version"; return 2; }
  local i_major i_minor l_major l_minor; IFS='.' read -r i_major i_minor _ <<< "$installed"
  IFS='.' read -r l_major l_minor _ <<< "$latest"
  i_major="${i_major:-0}"; i_minor="${i_minor:-0}"; l_major="${l_major:-0}"; l_minor="${l_minor:-0}"
  local gap=$(( (l_major - i_major) * 1000 + (l_minor - i_minor) ))
  [[ "$gap" -lt 0 ]] && gap=0
  if [[ "$gap" -gt 2 ]]; then log "ALERT" "GATEWAY STALE: installed=$installed, latest=$latest ($gap releases behind)"; GATEWAY_STALE=1
  else log "OK" "gateway: installed=$installed, latest=$latest (gap=$gap)"; fi
}
detect_orphaned_pm2() {
  command -v pm2 >/dev/null 2>&1 || { log "INFO" "pm2 not installed"; return 0; }
  local pm2_list; pm2_list=$(pm2 jlist 2>/dev/null || echo "[]")
  [[ "$pm2_list" == "[]" ]] && { log "OK" "no pm2 processes"; return 0; }
  if command -v python3 >/dev/null 2>&1; then
    local orphan_data; orphan_data=$(OC_PM2_JSON="$pm2_list" python3 - 2>/dev/null <<'PYEOF'
import json,os
try: apps=json.loads(os.environ.get("OC_PM2_JSON","[]"))
except: sys.exit(1)
orphans=[]
for app in apps:
    pm2_env=app.get("pm2_env",{}) or {}
    cwd=pm2_env.get("cwd","") or pm2_env.get("pm_cwd","") or ""
    name=app.get("name","unknown"); pid=app.get("pid","?")
    if cwd and not os.path.isdir(cwd): orphans.append({"name":name,"pid":str(pid),"cwd":cwd})
import sys
for o in orphans: print(json.dumps(o))
PYEOF
    )
    if [[ -z "$orphan_data" ]]; then log "OK" "no orphaned pm2"; return 0; fi
    local cleaned=0
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      local o_name; o_name=$(echo "$line" | python3 -c "import json,sys;print(json.loads(sys.stdin.read())['name'])" 2>/dev/null||echo "unknown")
      log "ALERT" "ORPHANED PM2: $o_name"
      pm2 stop "$o_name" >/dev/null 2>&1 || true
      if pm2 delete "$o_name" >/dev/null 2>&1; then log "CLEAN" "deleted orphan: $o_name"; cleaned=$((cleaned+1))
      else log "WARN" "cannot delete orphan: $o_name"; fi
    done <<< "$orphan_data"
    [[ "$cleaned" -gt 0 ]] && { PM2_ORPHANS="$cleaned"; log "OK" "cleaned $cleaned orphaned pm2"; }
  fi
}
trigger_gateway_update() {
  [[ "$GATEWAY_STALE" -eq 0 ]] && return 0
  log "ACTION" "npm install -g openclaw@latest"
  if command -v npm >/dev/null 2>&1; then
    if npm install -g openclaw@latest >/dev/null 2>&1; then
      local new_ver; new_ver=$(openclaw --version 2>/dev/null|grep -oE '[0-9]+\.[0-9]+\.[0-9]+'|head -1||echo "?")
      log "DONE" "gateway updated to $new_ver"
    else log "WARN" "npm install failed — gateway remains stale"; fi
  fi
}
main() {
  log "INFO" "stale-process-detector $STALE_PROCESS_DETECTOR_VERSION"
  check_gateway_staleness; detect_orphaned_pm2; trigger_gateway_update
  if [[ "$GATEWAY_STALE" -eq 1 ]] && [[ "$PM2_ORPHANS" -gt 0 ]]; then log "DONE" "both: stale gateway + $PM2_ORPHANS orphaned pm2"; exit 9
  elif [[ "$GATEWAY_STALE" -eq 1 ]]; then log "DONE" "stale gateway"; exit 7
  elif [[ "$PM2_ORPHANS" -gt 0 ]]; then log "DONE" "$PM2_ORPHANS orphaned pm2 cleaned"; exit 8; fi
  log "DONE" "clean"; exit 0
}
main "$@"
