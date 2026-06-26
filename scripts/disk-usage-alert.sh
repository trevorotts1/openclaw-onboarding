#!/usr/bin/env bash
# disk-usage-alert.sh — EMBEDDING-PREVENTION BUNDLE item 6.
#
# THE PROBLEM:
#   Runaway memory-index bloat, orphaned reindex temp files, and dual vector
#   storage have all silently filled boxes to the disk wall. A full disk kills
#   the gateway, corrupts in-flight DB writes, and blocks reindex/repair — the
#   exact downstream of the stale-index problem this bundle prevents. We need a
#   loud alarm BEFORE the disk fills.
#
# WHAT THIS DOES:
#   Checks the filesystem holding the OpenClaw root ($OC_ROOT) — and the root
#   filesystem if different — and ALERTS when usage crosses a threshold
#   (default 85%). On alert it logs a clear line, prints the biggest space
#   consumers under $OC_ROOT (so the operator sees WHAT to clear — usually the
#   memory index), and optionally sends ONE operator Telegram line.
#
# DESIGN: host-level, idempotent, platform-detected OC_ROOT, dedicated log.
#   Mirrors scripts/capacity-monitor.sh. bash-not-zsh. No external deps beyond df/du.
#
# EXIT CODES:
#   0  under threshold (healthy)
#   6  AT/OVER threshold (alert raised)
#   2  could not run (no OpenClaw root / df unavailable)
#
# ENV OVERRIDES:
#   OC_DISK_THRESHOLD=85     percent-used alert threshold (integer)
#   OC_DISK_ESCALATE=1       send one operator Telegram line on alert
#
# Version marker (kept in sync by scripts/bump-version.sh):
DISK_USAGE_ALERT_VERSION="v13.2.0"

set -u

# ─── Platform detection (VPS /data first, Mac fallback) ───────────────────────
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[disk-usage-alert] no OpenClaw root found; nothing to do" >&2
  exit 2
fi

THRESHOLD="${OC_DISK_THRESHOLD:-85}"
DISK_LOG="$OC_ROOT/disk-usage-alert.log"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() {
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2" >> "$DISK_LOG" 2>/dev/null || true
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2"
}

command -v df >/dev/null 2>&1 || { log "WARN" "df not available — skipping"; exit 2; }

# Portable percent-used for a given path (strip the trailing %).
# `df -P` is POSIX and renders one data line; field 5 = use%.
pct_used() {
  df -P "$1" 2>/dev/null | awk 'NR==2 {gsub(/%/,"",$5); print $5}'
}
mount_of() {
  df -P "$1" 2>/dev/null | awk 'NR==2 {print $6}'
}

alert=0

check_fs() {
  local path="$1" label="$2"
  local used mnt
  used="$(pct_used "$path")"
  mnt="$(mount_of "$path")"
  if [[ -z "$used" || ! "$used" =~ ^[0-9]+$ ]]; then
    log "WARN" "$label: could not read disk usage for $path"
    return 0
  fi
  if [[ "$used" -ge "$THRESHOLD" ]]; then
    log "ALERT" "$label disk ${used}% used (>= ${THRESHOLD}%) on mount $mnt ($path)"
    alert=1
  else
    log "OK" "$label disk ${used}% used (< ${THRESHOLD}%) on mount $mnt"
  fi
}

# 1. The filesystem holding the OpenClaw root (where the memory index lives).
check_fs "$OC_ROOT" "openclaw-root"

# 2. The root filesystem, if it is a different mount.
ROOT_MNT="$(mount_of /)"
OC_MNT="$(mount_of "$OC_ROOT")"
if [[ -n "$ROOT_MNT" && "$ROOT_MNT" != "$OC_MNT" ]]; then
  check_fs "/" "root-fs"
fi

if [[ "$alert" -eq 1 ]]; then
  # Show the biggest consumers under OC_ROOT so the operator knows what to clear
  # (the memory index is the usual culprit). Best-effort; never fatal.
  log "INFO" "top space consumers under $OC_ROOT:"
  du -sh "$OC_ROOT"/* 2>/dev/null | sort -rh | head -8 | while IFS= read -r line; do
    log "INFO" "    $line"
  done

  if [[ "${OC_DISK_ESCALATE:-0}" == "1" ]] && [[ -n "${RESCUE_RANGERS_WEBHOOK_URL:-}" ]]; then
    _esc_msg="[disk-alert] $(hostname): OpenClaw disk >= ${THRESHOLD}% used. Check the memory index / orphan temp files before the gateway is starved. See $DISK_LOG."
    _esc_msg="${_esc_msg//\\/\\\\}"; _esc_msg="${_esc_msg//\"/\\\"}"
    curl -s -X POST "${RESCUE_RANGERS_WEBHOOK_URL}" \
      -H 'Content-Type: application/json' \
      -d "{\"action\":\"escalate\",\"client\":\"$(hostname 2>/dev/null||echo box)\",\"agent\":\"disk-usage-alert\",\"message\":\"${_esc_msg}\"}" \
      --max-time 15 >/dev/null 2>&1 || log "WARN" "rescue-rangers webhook escalation failed (non-fatal)"
  fi
  exit 6
fi

exit 0
