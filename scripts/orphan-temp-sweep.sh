#!/usr/bin/env bash
# orphan-temp-sweep.sh — EMBEDDING-PREVENTION BUNDLE item 5.
#
# THE PROBLEM (fleet-confirmed disk creep):
#   A reindex / re-embed builds the new vector DB at a temp path
#   (<name>.sqlite.tmp, <name>.sqlite.tmp-<pid>, *.sqlite-journal, *.sqlite.building)
#   and atomically renames it over the live DB on success. If the reindex CRASHES
#   (provider rate-limit, OOM, gateway restart mid-build), the temp file is
#   ORPHANED. Repeated failed reindexes pile up orphans, each potentially the full
#   size of the index — silently eating disk until the box hits the disk wall.
#
# WHAT THIS DOES:
#   Finds orphaned reindex temp artifacts under $OC_ROOT/memory that are OLDER
#   than a safety age (default 60 min — long enough that a legitimately in-flight
#   reindex is never touched) and deletes them. Logs every removal + a reclaimed-
#   bytes total. Idempotent + safe to run hourly. Never touches a live *.sqlite.
#
# SAFETY:
#   - Only matches KNOWN temp suffixes (never a bare *.sqlite).
#   - Only deletes files older than OC_TMP_MIN_AGE_MIN (default 60) — so an
#     active reindex's temp file is skipped (it would be younger).
#   - Stays strictly inside $OC_ROOT/memory.
#   - Dry-run mode lists candidates without deleting.
#
# DESIGN: host-level, idempotent, platform-detected OC_ROOT, dedicated log.
#   Mirrors scripts/capacity-monitor.sh. bash-not-zsh.
#
# EXIT CODES:
#   0  ran clean (swept N orphans, or nothing to sweep)
#   2  could not run (no OpenClaw root)
#
# ENV OVERRIDES:
#   OC_TMP_MIN_AGE_MIN=60   minimum age (minutes) before an orphan is removable
#   OC_TMP_DRY_RUN=1        list candidates, delete nothing
#
# Version marker (kept in sync by scripts/bump-version.sh):
ORPHAN_TEMP_SWEEP_VERSION="v13.2.0"

set -u

# ─── Platform detection (VPS /data first, Mac fallback) ───────────────────────
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[orphan-temp-sweep] no OpenClaw root found; nothing to do" >&2
  exit 2
fi

MEMORY_DIR="$OC_ROOT/memory"
SWEEP_LOG="$OC_ROOT/orphan-temp-sweep.log"
MIN_AGE_MIN="${OC_TMP_MIN_AGE_MIN:-60}"
DRY_RUN="${OC_TMP_DRY_RUN:-0}"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() {
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2" >> "$SWEEP_LOG" 2>/dev/null || true
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2"
}

if [[ ! -d "$MEMORY_DIR" ]]; then
  log "INFO" "no memory dir yet ($MEMORY_DIR) — nothing to sweep"
  exit 0
fi

# Known orphaned-reindex temp artifact patterns. Deliberately NEVER a bare
# *.sqlite. The -mmin +N guard means only files older than the safety age match.
declare -a PATTERNS=(
  "*.sqlite.tmp"
  "*.sqlite.tmp-*"
  "*.sqlite.tmp.*"
  "*.sqlite.building"
  "*.sqlite.rebuild"
  "*.sqlite-journal"
  "*.sqlite-wal.tmp"
  "*.db.tmp"
  "*.db.tmp-*"
)

# Build the find expression: ( -name p1 -o -name p2 ... ) -type f -mmin +AGE
FIND_EXPR=()
first=1
for p in "${PATTERNS[@]}"; do
  if [[ $first -eq 1 ]]; then
    FIND_EXPR+=( "(" -name "$p" )
    first=0
  else
    FIND_EXPR+=( -o -name "$p" )
  fi
done
FIND_EXPR+=( ")" )

removed=0
reclaimed=0
errors=0

# -mmin +N: strictly older than N minutes (active reindex temp is younger → skipped)
while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  # size (portable: macOS stat -f%z, GNU stat -c%s)
  sz=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || echo 0)
  if [[ "$DRY_RUN" == "1" ]]; then
    log "DRY" "would remove orphan ($sz bytes): $f"
    removed=$((removed + 1))
    reclaimed=$((reclaimed + sz))
    continue
  fi
  if rm -f "$f" 2>/dev/null; then
    log "SWEPT" "removed orphan ($sz bytes): $f"
    removed=$((removed + 1))
    reclaimed=$((reclaimed + sz))
  else
    log "WARN" "could not remove: $f"
    errors=$((errors + 1))
  fi
done < <(find "$MEMORY_DIR" -type f "${FIND_EXPR[@]}" -mmin +"$MIN_AGE_MIN" 2>/dev/null)

mb=$(python3 -c "print(round($reclaimed/1024/1024, 2))" 2>/dev/null || echo "?")
if [[ "$removed" -eq 0 ]]; then
  log "OK" "no orphaned reindex temp files older than ${MIN_AGE_MIN}m — clean"
else
  log "OK" "swept $removed orphan(s), reclaimed ~${mb} MB (errors=$errors, dry_run=$DRY_RUN)"
fi
exit 0
