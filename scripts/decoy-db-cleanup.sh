#!/usr/bin/env bash
# decoy-db-cleanup.sh — U126 fleet-audit: remove 0-byte decoy mission-control.db.
DECOY_DB_CLEANUP_VERSION="v14.1.10"
set -u
if [[ -d /data/.openclaw ]]; then OC_ROOT=/data/.openclaw
elif [[ -d "${HOME}/.openclaw" ]]; then OC_ROOT="${HOME}/.openclaw"
else echo "[decoy-db-cleanup] no OpenClaw root found" >&2; exit 2; fi
DECOY_LOG="$OC_ROOT/decoy-db-cleanup.log"
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2" >> "$DECOY_LOG" 2>/dev/null || true; printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2"; }
command -v stat >/dev/null 2>&1 || { log "WARN" "stat not available — skipping"; exit 2; }
CANDIDATES=("$HOME/projects/mission-control/mission-control.db" "$HOME/projects/command-center/mission-control.db" "$HOME/blackceo-command-center/mission-control.db" "$HOME/clawd/mission-control.db" "/data/projects/command-center/mission-control.db" "/data/projects/mission-control/mission-control.db" "/data/.openclaw/workspace/mission-control.db")
removed=0
for cand in "${CANDIDATES[@]}"; do
  [[ -z "$cand" ]] && continue; [[ -f "$cand" ]] || continue
  local sz; sz=$(stat -f%z "$cand" 2>/dev/null || stat -c%s "$cand" 2>/dev/null || echo "")
  [[ -z "$sz" ]] && { log "WARN" "could not stat $cand — skipping"; continue; }
  if [[ "$sz" -gt 0 ]]; then log "OK" "$cand is a real DB (${sz} bytes) — NOT a decoy"; continue; fi
  if rm -f "$cand" 2>/dev/null; then log "CLEAN" "removed 0-byte decoy: $cand"; removed=$((removed+1))
  else log "WARN" "could not remove $cand"; fi
done
if [[ "$removed" -gt 0 ]]; then log "DONE" "removed $removed decoy mission-control.db file(s)"
else log "OK" "no decoy mission-control.db files found"; fi
exit 0
