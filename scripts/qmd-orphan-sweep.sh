#!/usr/bin/env bash
# scripts/qmd-orphan-sweep.sh -- U132: remove orphaned .qmd render temp files
QMD_ORPHAN_SWEEP_VERSION="v1.0.0"
set -u
if [[ -d /data/.openclaw ]]; then OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then OC_ROOT="$HOME/.openclaw"
else echo "[qmd-orphan-sweep] no OpenClaw root found; nothing to do" >&2; exit 2; fi
RENDER_DIR="${QMD_RENDER_DIR:-$OC_ROOT/workspace}"
SWEEP_LOG="$OC_ROOT/qmd-orphan-sweep.log"
MIN_AGE_MIN="${QMD_MIN_AGE_MIN:-1440}"; DRY_RUN="${QMD_DRY_RUN:-0}"
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2" >> "$SWEEP_LOG" 2>/dev/null || true; printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2"; }
[[ -d "$RENDER_DIR" ]] || { log "INFO" "no render temp dir yet ($RENDER_DIR) - nothing to sweep"; exit 0; }
case "$RENDER_DIR" in "$OC_ROOT"/*) ;; *)
  [[ "${QMD_RENDER_ACK:-0}" == "1" ]] || { log "WARN" "outside OC_ROOT - set QMD_RENDER_ACK=1"; exit 2; } ;; esac
removed=0; reclaimed=0; errors=0
while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  sz=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || echo 0)
  if [[ "$DRY_RUN" == "1" ]]; then log "DRY" "would remove orphan ($sz bytes): $f"; removed=$((removed+1)); reclaimed=$((reclaimed+sz)); continue; fi
  rm -f "$f" 2>/dev/null && log "SWEPT" "removed orphan ($sz bytes): $f" && removed=$((removed+1)) && reclaimed=$((reclaimed+sz)) \
    || { log "WARN" "could not remove: $f"; errors=$((errors+1)); }
done < <(find "$RENDER_DIR" -type f -name "*.qmd" -mmin +"$MIN_AGE_MIN" 2>/dev/null)
mb=$(python3 -c "print(round($reclaimed/1024/1024,2))" 2>/dev/null || echo "?")
[[ "$removed" -eq 0 ]] && log "OK" "no orphaned .qmd files older than ${MIN_AGE_MIN}m - clean" \
  || log "OK" "swept $removed orphan(s), reclaimed ~${mb} MB (errors=$errors, dry_run=$DRY_RUN)"
exit 0
