#!/usr/bin/env bash
# disk-usage-alert.sh — EMBEDDING-PREVENTION BUNDLE item 6.
# v14.1.10 — U126 fleet-audit: explicit operator-channel delivery + webhook fallback.
DISK_USAGE_ALERT_VERSION="v14.1.10"
set -u
if [[ -d /data/.openclaw ]]; then OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then OC_ROOT="$HOME/.openclaw"
else echo "[disk-usage-alert] no OpenClaw root found" >&2; exit 2; fi
THRESHOLD="${OC_DISK_THRESHOLD:-85}"
DISK_LOG="$OC_ROOT/disk-usage-alert.log"
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2" >> "$DISK_LOG" 2>/dev/null || true; printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2"; }
command -v df >/dev/null 2>&1 || { log "WARN" "df not available"; exit 2; }
pct_used() { df -P "$1" 2>/dev/null|awk 'NR==2{gsub(/%/,"",$5);print $5}'; }
mount_of() { df -P "$1" 2>/dev/null|awk 'NR==2{print $6}'; }
alert=0
check_fs() {
  local path="$1" label="$2" used mnt
  used="$(pct_used "$path")"; mnt="$(mount_of "$path")"
  if [[ -z "$used" || ! "$used" =~ ^[0-9]+$ ]]; then log "WARN" "$label: could not read disk usage for $path"; return 0; fi
  if [[ "$used" -ge "$THRESHOLD" ]]; then log "ALERT" "$label disk ${used}% used (>= ${THRESHOLD}%) on mount $mnt ($path)"; alert=1
  else log "OK" "$label disk ${used}% used (< ${THRESHOLD}%) on mount $mnt"; fi
}
check_fs "$OC_ROOT" "openclaw-root"
ROOT_MNT="$(mount_of /)"; OC_MNT="$(mount_of "$OC_ROOT")"
if [[ -n "$ROOT_MNT" && "$ROOT_MNT" != "$OC_MNT" ]]; then check_fs "/" "root-fs"; fi
if [[ "$alert" -eq 1 ]]; then
  log "INFO" "top space consumers under $OC_ROOT:"
  du -sh "$OC_ROOT"/* 2>/dev/null|sort -rh|head -8|while IFS= read -r line; do log "INFO" "    $line"; done
  _host="$(hostname 2>/dev/null||echo box)"
  _esc_msg="[disk-alert] ${_host}: OpenClaw disk >= ${THRESHOLD}% used. Check memory index / orphan temp files. See $DISK_LOG."
  _op_chat=""
  if [[ -f "${OC_ROOT}/openclaw.json" ]] && command -v python3 >/dev/null 2>&1; then
    _op_chat=$(OC_JSON="${OC_ROOT}/openclaw.json" python3 - 2>/dev/null <<'PYEOF'
import json,os
try: cfg=json.load(open(os.environ["OC_JSON"]))
except: cfg={}
env=(cfg.get("env",{}) or {}).get("vars",{}) or {}
for k in ("OPERATOR_ESCALATION_CHAT_ID","OPERATOR_HELP_CHAT_ID"):
    v=str(env.get(k,"") or "").strip()
    if v: print(v); raise SystemExit(0)
print("")
PYEOF
    )
  fi
  local _delivered=0
  if [[ -n "$_op_chat" ]] && command -v openclaw >/dev/null 2>&1; then
    if openclaw message send --channel telegram --account operator --message "$_esc_msg" >/dev/null 2>&1; then
      log "INFO" "alert delivered via gateway operator-chat ($_op_chat)"; _delivered=1
    fi
  fi
  if [[ "$_delivered" -eq 0 ]] && [[ "${OC_DISK_ESCALATE:-0}" == "1" ]] && [[ -n "${RESCUE_RANGERS_WEBHOOK_URL:-}" ]]; then
    _esc_json_msg="${_esc_msg//\\/\\\\}"; _esc_json_msg="${_esc_json_msg//\"/\\\"}"
    if curl -s -X POST "${RESCUE_RANGERS_WEBHOOK_URL}" -H 'Content-Type: application/json' ${RESCUE_RANGERS_WEBHOOK_SECRET:+-H X-Rescue-Secret:${RESCUE_RANGERS_WEBHOOK_SECRET}} -d "{\"action\":\"escalate\",\"client\":\"${_host}\",\"agent\":\"disk-usage-alert\",\"message\":\"${_esc_json_msg}\"}" --max-time 15 >/dev/null 2>&1; then
      log "INFO" "alert delivered via rescue-rangers webhook (operator gateway unavailable)"; _delivered=1
    else log "WARN" "rescue-rangers webhook escalation failed (non-fatal)"; fi
  fi
  if [[ "$_delivered" -eq 0 ]]; then log "WARN" "alert NOT delivered to any channel — no operator chat, no webhook. Alert is in this log only."; fi
  exit 6
fi
exit 0
