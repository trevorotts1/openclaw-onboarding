#!/usr/bin/env bash
# ============================================================
#  OpenClaw Wave Concurrency Gate
#  Hard cap enforcement: Mac=10, VPS=5 concurrent sub-agents per wave.
#  Standing observers (Memory Wiki, Devil's Advocate) DO NOT count.
#
#  The Master Orchestrator MUST call this script before spawning sub-agents
#  in a wave. Returns:
#    exit 0     → allowed (proposed count <= platform cap)
#    exit 1     → rejected (proposed > platform cap); stderr explains
#    exit 2     → misuse
#
#  v10.8.0 — P0-8 fix for Phase 5 score 0.40.
# ============================================================
set -u

# Platform detect
if [ -d "/data/.openclaw" ]; then
  PLATFORM=vps
  OC_ROOT=/data/.openclaw
  CAP=5
else
  PLATFORM=mac
  OC_ROOT="$HOME/.openclaw"
  CAP=10
fi

# WS-8: prefer the hardware-derived cap from .capacity-profile.json (written by
# capacity-monitor.sh) over the static Mac=10/VPS=5 fallback. The profile knows
# this box's real CPU/RAM; the static numbers don't. Falls back silently to the
# platform default if the profile is missing or unreadable.
_PROFILE="$OC_ROOT/.capacity-profile.json"
if [ -f "$_PROFILE" ] && command -v python3 >/dev/null 2>&1; then
  _PCAP=$(python3 -c "import json,sys;print(json.load(open('$_PROFILE')).get('maxConcurrentAgents',''))" 2>/dev/null || true)
  if [[ "$_PCAP" =~ ^[0-9]+$ ]] && [ "$_PCAP" -gt 0 ]; then
    CAP="$_PCAP"
  fi
fi

# Args: --proposed <n>  [--reason "<short string>"]
PROPOSED=""
REASON=""
while [ $# -gt 0 ]; do
  case "$1" in
    --proposed)  PROPOSED="$2"; shift 2 ;;
    --reason)    REASON="$2"; shift 2 ;;
    --platform)  PLATFORM="$2"; CAP=$([ "$2" = "vps" ] && echo 5 || echo 10); shift 2 ;;
    --help|-h)
      cat <<EOF
check-wave-concurrency.sh — wave concurrency gate

Usage:
  bash scripts/check-wave-concurrency.sh --proposed <n> [--reason "<text>"]

Exit codes:
  0  proposed <= platform cap (Mac=10, VPS=5)
  1  proposed exceeds cap — orchestrator MUST reduce before spawning
  2  misuse / missing args
EOF
      exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$PROPOSED" ]; then
  echo "ERROR: --proposed <n> is required" >&2
  exit 2
fi

if ! [[ "$PROPOSED" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --proposed must be an integer (got: $PROPOSED)" >&2
  exit 2
fi

# Standing observers do NOT count. Document this so the orchestrator's math
# is clear: PROPOSED is the number of WORKER sub-agents, not the total.
if [ "$PROPOSED" -le "$CAP" ]; then
  cat <<EOF
{"ok": true, "platform": "$PLATFORM", "cap": $CAP, "proposed": $PROPOSED, "decision": "allow", "reason": "${REASON:-}", "note": "standing observers (Memory Wiki, Devil's Advocate) do not count toward the cap"}
EOF
  exit 0
else
  cat <<EOF
{"ok": false, "platform": "$PLATFORM", "cap": $CAP, "proposed": $PROPOSED, "decision": "reject", "reason": "${REASON:-}", "fix": "reduce proposed to <= $CAP (platform cap) OR split into multiple waves"}
EOF
  echo "[wave-concurrency-gate] REJECT: proposed=$PROPOSED > cap=$CAP for platform=$PLATFORM" >&2
  exit 1
fi
