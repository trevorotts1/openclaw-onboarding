#!/usr/bin/env bash
# Verified public interview invitation through the OpenClaw gateway.
# Usage: send-interview-link.sh [--dry-run] [--resume] [--renew]
# --renew (or FORCE=1) bypasses only accepted-send cooldown. Unknown delivery must be reconciled and is never retried automatically.
# Identity/origin: canonical workforce state plus matching MC_* compatibility env.
# OPENCLAW_DASHBOARD_URL is accepted only after exact authenticated readiness.
# Exit: 0 accepted/dry-run; 2 usage; 3 complete; 4 owner unresolved; 5 missing CLI;
# 6 pre-send rejection; 7 cooldown; 8 readiness/receipt pending; 9 delivery uncertain;
# 10 accepted but legacy ledger write failed (durable acceptance retained).
# No direct Telegram API and no silent chat invitation fallback.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DRY_RUN=0
RESUME_REQUESTED=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --resume) RESUME_REQUESTED=1; shift ;;
    --renew) export FORCE=1; RESUME_REQUESTED=1; shift ;;
    -h|--help) sed -n '1,10p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Resolve the selected client using the installer platform contract, including
# custom workspace pins. An unrelated /data directory never overrides them.
PLATFORM_HELPER="$SCRIPT_DIR/../../platform/common.sh"
if [ ! -f "$PLATFORM_HELPER" ]; then PLATFORM_HELPER="$SCRIPT_DIR/../../../platform/common.sh"; fi
if [ ! -f "$PLATFORM_HELPER" ]; then
  echo "[send-interview-link] PENDING: selected-client platform helper missing." >&2
  exit 8
fi
source "$PLATFORM_HELPER"
oc_set_platform_paths || exit 8
WS="$OC_WORKSPACE_DEFAULT"
STATE_FILE="$WS/.workforce-build-state.json"
HANDOFF_FILE="$WS/company-discovery/interview-handoff.md"
LEDGER_FILE="$WS/company-discovery/.interview-link-sends.log"

# ── Read wording state; helper below rejects missing/invalid canonical state ───
read_state() {
  python3 - "$STATE_FILE" <<'PYEOF'
import json, sys
try:
    s = json.load(open(sys.argv[1]))
except Exception:
    s = {}
if not isinstance(s, dict): s = {}
complete = "1" if (s.get("interviewComplete") is True or s.get("buildCompletedAt")) else "0"
slug = str(s.get("companySlug") or s.get("interviewSessionId") or "").strip()
# buildType: absent or "legacy" -> legacy lane (today's wording, byte-identical);
# "standard-first" -> standard-first lane (day-one-link wording).
standard = "1" if s.get("buildType") == "standard-first" else "0"
print(f"{complete}|{slug}|{standard}")
PYEOF
}
STATE_OUT="$(read_state)"
IS_COMPLETE="${STATE_OUT%%|*}"
STATE_REST="${STATE_OUT#*|}"
SLUG="${STATE_REST%%|*}"
STANDARD_FIRST="${STATE_REST##*|}"
LANE="legacy"
if [ "$STANDARD_FIRST" = "1" ]; then
  LANE="standard-first"
fi

if [ "$IS_COMPLETE" = "1" ]; then
  echo "[send-interview-link] REFUSED: the interview is already complete — nothing to invite the owner to." >&2
  exit 3
fi

# Started = a handoff exists AND we have a slug to build the resume link with.
MODE="start"
if [ "$RESUME_REQUESTED" = "1" ] || { [ -f "$HANDOFF_FILE" ] && [ -n "$SLUG" ]; }; then
  MODE="resume"
fi

# ── Build the message (jargon-free; the link is the only instruction) ─────────
# Wording is lane-selected from build-state buildType:
#   legacy lane (buildType absent or "legacy")  -> today's wording, unchanged.
#   standard-first lane (buildType == "standard-first") -> day-one framing:
#   the owner's company already has its standard foundation, and the
#   interview tailors it (master plan section 3.2: "your company's standard
#   foundation is already set up — this conversation tailors it to you").
# The RESUME variants are lane-neutral (the interview is underway either way,
# so the "continue where you left off" wording is identical in both lanes).
FIRST_NAME="${CLIENT_FIRST_NAME:-there}"
HELPER="$SCRIPT_DIR/../../shared-utils/interview_invitation.py"
if [ ! -f "$HELPER" ]; then HELPER="$SCRIPT_DIR/../../../shared-utils/interview_invitation.py"; fi
if [ ! -f "$HELPER" ]; then
  echo "[send-interview-link] PENDING: verified invitation helper missing." >&2
  exit 8
fi
# Default is a public web invitation. Missing or unverified web readiness is
# pending, never silently replaced by a Telegram-native interview.
TMP_RESOLUTION="$(mktemp)"
TMP_MSG=""
trap 'rm -f "$TMP_RESOLUTION" "${TMP_MSG:-}"' EXIT
DASH="$(python3 "$HELPER" resolve --state "$STATE_FILE" --resolution-file "$TMP_RESOLUTION")" || exit 8
LINK="$DASH/interview"


TMP_MSG="$(mktemp)"
if [ -n "$LINK" ] && [ "$MODE" = "resume" ]; then
  cat > "$TMP_MSG" <<EOF
Welcome back, $FIRST_NAME — continue your AI Workforce Interview here: $LINK

{{INVITATION_VALIDITY}}
You can stop and return later. Any saved answers will resume after sign-in.

Bookmark your private interview page after signing in: $DASH/interview
If sign-in has expired, tell your Telegram assistant “resume my interview” to get a fresh private link. Your saved answers stay in place.
EOF
elif [ -n "$LINK" ] && [ "$LANE" = "standard-first" ]; then
  cat > "$TMP_MSG" <<EOF
Hi $FIRST_NAME — your company's standard foundation is already set up, and your AI Workforce Interview is ready. It's a short conversation in your own words that tailors that foundation to you. When you're ready, start here: $LINK

{{INVITATION_VALIDITY}}
Answers are saved as you go. You can stop and return later.

Bookmark your private interview page after signing in: $DASH/interview
If sign-in has expired, tell your Telegram assistant “resume my interview” to get a fresh private link. Your saved answers stay in place.
EOF
elif [ -n "$LINK" ]; then
  cat > "$TMP_MSG" <<EOF
Hi $FIRST_NAME — your AI Workforce Interview is ready. It's a short conversation in your own words, and we build your company from what you tell us. When you're ready, start here: $LINK

{{INVITATION_VALIDITY}}
Answers are saved as you go. You can stop and return later.

Bookmark your private interview page after signing in: $DASH/interview
If sign-in has expired, tell your Telegram assistant “resume my interview” to get a fresh private link. Your saved answers stay in place.
EOF

fi

# ── Resolve the owner chat (operator-rejecting shared resolver) ───────────────
RESOLVER="$SCRIPT_DIR/../../shared-utils/resolve-owner-chat.sh"
if [ ! -f "$RESOLVER" ]; then
  # Repo-checkout layout fallback (scripts two levels under the repo root).
  RESOLVER="$SCRIPT_DIR/../../../shared-utils/resolve-owner-chat.sh"
fi
if [ ! -f "$RESOLVER" ]; then
  echo "[send-interview-link] FATAL: shared-utils/resolve-owner-chat.sh not found — cannot resolve the owner chat safely." >&2
  exit 4
fi
# shellcheck source=/dev/null
source "$RESOLVER"
# resolve_owner_chat_id implements the full S0→S1→S2 chain — INCLUDING the
# OPENCLAW_OWNER_CHAT_ID env pin — with operator-rejection on every source.
# Never pre-empt it with a raw env read: that would bypass the denylist.
CHAT_ID="$(resolve_owner_chat_id || true)"
if [ -z "$CHAT_ID" ]; then
  echo "[send-interview-link] FAILED: no non-operator owner chat id could be resolved (owner not paired / not in allowFrom). Nothing sent." >&2
  exit 4
fi
MASKED="…${CHAT_ID: -4}"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "[send-interview-link] DRY-RUN lane=$LANE mode=$MODE chat=$MASKED"
  echo "----- preview only: enrollment is issued at send time -----"
  sed 's/{{INVITATION_VALIDITY}}/The exact expiry is included when the private sign-in link is issued./g' "$TMP_MSG"
  echo "-------------------"
  exit 0
fi

# Supported gateway contract + durable acceptance/uncertainty ledger. Owner chat
# comes exclusively from the existing operator-rejecting resolver above.
python3 "$HELPER" send --state "$STATE_FILE" --resolution-file "$TMP_RESOLUTION" --message-file "$TMP_MSG" \
  --target "$CHAT_ID" --ledger "$LEDGER_FILE" --mode "$MODE" --lane "$LANE"
