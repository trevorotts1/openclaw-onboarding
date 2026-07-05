#!/usr/bin/env bash
# send-operator-summary.sh -- success-path operator summary for Skill 37 ZHC Closeout.
#
# After every artifact has passed the 8.5 quality gate AND been delivered to the
# client, this sends Trevor (the operator) a single Telegram summary with LINKS
# to every closeout artifact: the two infographics, the celebration video, the
# Notion closeout page, and the live Command Center dashboard.
#
# WHY: run-closeout.sh already escalates HELD artifacts to the operator, but there
# was no success-path summary. The operator had no single message confirming a
# build closed out cleanly + where every deliverable lives. This is that message.
#
# All sends go THROUGH the OpenClaw gateway (openclaw message send). Never curl
# api.telegram.org directly. Chat ID resolution prefers shared-utils
# (env.vars.OPERATOR_ESCALATION_CHAT_ID), then $ZHC_OPERATOR_CHAT_ID. There is NO
# hardcoded operator chat: if none is configured, the operator summary is SKIPPED
# (opt-in only — a client box never proactively messages an operator).
#
# Idempotent: writes .operatorSummarySentAt into state and no-ops if already sent
# for this closeout (cleared when a new build starts).

set -u

if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[operator-summary] no OpenClaw root found; aborting" >&2
  exit 0
fi

# FIX-XC-10a: honor ZHC_STATE_FILE so a test run never reads the LIVE client
# state (this script can send a REAL operator summary message off it).
STATE_FILE="${ZHC_STATE_FILE:-$OC_ROOT/workspace/.workforce-build-state.json}"
LOG_FILE="$OC_ROOT/workspace/.zhc-closeout.log"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() { printf '%s [%-5s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >> "$LOG_FILE"; }
state_get() { jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null; }
state_set() { local tmp; tmp=$(mktemp); jq "$1" "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE"; }
now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

if [[ ! -f "$STATE_FILE" ]]; then
  log "WARN" "operator-summary: no state file -- skipping"
  exit 0
fi

# Idempotency: skip if already sent for this closeout.
already="$(state_get '.operatorSummarySentAt')"
if [[ -n "$already" && "$already" != "null" ]]; then
  log "INFO" "operator-summary: already sent at $already -- skipping"
  exit 0
fi

# ---- resolve operator chat id ----
OPERATOR_CHAT_ID=""
SHARED_UTIL="$OC_ROOT/skills/shared-utils/operator-chat-id.sh"
if [[ -f "$SHARED_UTIL" ]]; then
  # shellcheck disable=SC1090
  source "$SHARED_UTIL" 2>/dev/null || true
fi
# CO-MINGLING GUARD (v12.4.0): operator escalation destination is OPT-IN.
# operator-chat-id.sh resolves env.vars.OPERATOR_ESCALATION_CHAT_ID (or back-compat
# names). NO hardcoded personal chat. Empty => skip the send below.
[[ -z "${OPERATOR_CHAT_ID:-}" ]] && OPERATOR_CHAT_ID="${OPERATOR_ESCALATION_CHAT_ID:-}"
[[ -z "${OPERATOR_CHAT_ID:-}" ]] && OPERATOR_CHAT_ID="${ZHC_OPERATOR_CHAT_ID:-}"

# ---- gather artifact links ----
COMPANY="$(state_get '.companyName')"; [[ -z "$COMPANY" ]] && COMPANY="$(state_get '.companySlug')"
INF1="$(state_get '.infographic1Url')"
INF2="$(state_get '.infographic2Url')"
VIDEO="$(state_get '.celebrationVideoUrl')"
NOTION="$(state_get '.notionRootPageUrl')"
DASH="$(state_get '.commandCenterUrl')"
DRIVE1="$(state_get '.infographic1DriveUrl')"
DRIVE2="$(state_get '.infographic2DriveUrl')"
DRIVE_VID="$(state_get '.celebrationVideoDriveUrl')"
GHL="$(state_get '.ghlMediaUploaded')"
GHL_LIB="$(state_get '.ghlMediaLibraryUrl')"
# v10.x: durable, openable per-file public URLs from the GHL media upload.
GHL_VID="$(state_get '.ghlVideoPublicUrl')"
GHL_INF1="$(state_get '.ghlInfographic1PublicUrl')"
GHL_INF2="$(state_get '.ghlInfographic2PublicUrl')"
HELD="$(state_get '.qualityHeld | join(", ")')"

line() { local label="$1" val="$2"; [[ -n "$val" && "$val" != "null" ]] && printf -- '- %s: %s\n' "$label" "$val"; }

# Prefer the DURABLE link for each artifact: GHL public URL > Drive URL > the
# (ephemeral) KIE/remote URL. So the operator summary links match what the client
# can actually open.
MSG="$(
  printf 'ZHC Closeout COMPLETE -- %s\n\n' "${COMPANY:-(unnamed company)}"
  printf 'Every artifact passed the 8.5 quality gate and was delivered to the client. Links:\n\n'
  line "Command Center dashboard" "$DASH"
  line "Infographic 1 (Workforce Structure)" "${GHL_INF1:-${DRIVE1:-$INF1}}"
  line "Infographic 2 (How Work Flows)" "${GHL_INF2:-${DRIVE2:-$INF2}}"
  line "Celebration video" "${GHL_VID:-${DRIVE_VID:-$VIDEO}}"
  line "Notion closeout page" "$NOTION"
  if [[ -n "$GHL" && "$GHL" == "true" ]]; then line "GHL media library" "$GHL_LIB"; fi
  if [[ -n "$HELD" && "$HELD" != "null" ]]; then printf '\nHELD (not delivered, needs review): %s\n' "$HELD"; fi
)"

if ! command -v openclaw >/dev/null 2>&1; then
  log "ERROR" "operator-summary: openclaw CLI not found -- cannot send summary"
  exit 0
fi

if [[ -z "${OPERATOR_CHAT_ID:-}" ]]; then
  log "INFO" "operator-summary: operator escalation chat not configured (env.vars.OPERATOR_ESCALATION_CHAT_ID unset) -- skipping operator summary send"
  exit 0
fi

if openclaw message send --channel telegram --target "$OPERATOR_CHAT_ID" --message "$MSG" >>"$LOG_FILE" 2>&1; then
  state_set ".operatorSummarySentAt = \"$(now_iso)\" | .operatorSummaryChatId = \"$OPERATOR_CHAT_ID\""
  log "INFO" "operator-summary: sent to $OPERATOR_CHAT_ID"
else
  log "WARN" "operator-summary: send failed (see log) -- not fatal"
fi
exit 0
