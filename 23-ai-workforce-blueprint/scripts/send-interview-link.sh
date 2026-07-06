#!/usr/bin/env bash
# send-interview-link.sh — OPERATOR-TRIGGERED delivery of the AI Workforce
# Interview link to the client owner, via the OpenClaw gateway ONLY.
#
# WHAT THIS IS
#   The clean "when you're ready, start here" trigger for the Skill-23
#   interview. The operator runs this ON THE CLIENT'S BOX (directly or over
#   SSH); the box resolves ITS OWN owner chat (operator ids auto-rejected) and
#   sends ONE Telegram message carrying either:
#     START  — <dashboard>/interview            (nothing answered yet), or
#     RESUME — <dashboard>/onboarding/resume/<slug>  (interview underway;
#              the Command Center resumes at the exact next unanswered
#              question from interview-handoff.md)
#   When no dashboard URL is configured, the message instead invites the owner
#   to reply here in Telegram to begin/continue — the interview is fully
#   conductable in chat (INSTALL.md §5c Options A/B/C). It NEVER emits a
#   placeholder/broken link.
#
# DOCTRINE (binding)
#   • OPERATOR-TRIGGERED ONLY. This script is NEVER registered on a cron and
#     never auto-fires. The idle re-engagement cadence is a different tool
#     (interview-nudge-cron.sh → shared-utils/nudge-incomplete-interviews.py).
#   • GATEWAY ONLY. All sends go through `openclaw message send`. Direct HTTP
#     to api.telegram.org is FORBIDDEN. No openclaw CLI → log and FAIL, never
#     fall back.
#   • OPERATOR-REJECTION. The owner chat comes from
#     shared-utils/resolve-owner-chat.sh (env pin → allowFrom →
#     commands.ownerAllowFrom), which refuses every known operator id. This
#     script hardcodes NO chat ids.
#   • NO SECRETS. Nothing from openclaw.json is printed; the resolved chat id
#     is masked (last 4 digits) in all output.
#   • ANTI-SPAM. A send within the last 30 minutes (per-box ledger
#     company-discovery/.interview-link-sends.log) refuses unless FORCE=1.
#   • CANONICAL FILES ARE READ-ONLY here. This script reads
#     .workforce-build-state.json + interview-handoff.md and writes ONLY its
#     own non-canonical ledger line. It never touches build-state, the
#     transcript, or the handoff.
#
# Usage:
#   bash scripts/send-interview-link.sh              # resolve + send
#   bash scripts/send-interview-link.sh --dry-run    # print what WOULD send
#   FORCE=1 bash scripts/send-interview-link.sh      # bypass the 30-min guard
#
# Env:
#   OPENCLAW_DASHBOARD_URL   (optional) the client's Command Center base URL
#                            (e.g. https://<client>.zerohumanworkforce.com).
#                            With it: a tappable web link (works great on a
#                            phone). Without it: the Telegram-native
#                            reply-here invitation is sent instead.
#   OPENCLAW_OWNER_CHAT_ID   (optional) explicit owner chat pin (resolver S0;
#                            operator ids still rejected).
#   OPENCLAW_WORKSPACE_ROOT  (optional) workspace override (tests).
#   CLIENT_FIRST_NAME        (optional, default "there").
#   FORCE=1                  (optional) bypass the 30-minute re-send guard.
#
# Exit codes:
#   0 sent (or dry-run printed)   2 usage error
#   3 interview already complete  4 no owner chat resolvable
#   5 openclaw CLI missing        6 gateway send failed
#   7 re-send guard (use FORCE=1)
#
# set -euo pipefail; bash -n clean; OS-aware (uname) not required — pure
# POSIX-y bash + python3 for JSON reads (same pattern as resolve-owner-chat.sh).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '1,66p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# ── Workspace resolution (same probe order as update-interview-state.sh) ──────
if [ -n "${OPENCLAW_WORKSPACE_ROOT:-}" ]; then
  WS="$OPENCLAW_WORKSPACE_ROOT"
elif [ -d /data/.openclaw/workspace ]; then
  WS=/data/.openclaw/workspace
else
  WS="$HOME/.openclaw/workspace"
fi
STATE_FILE="$WS/.workforce-build-state.json"
HANDOFF_FILE="$WS/company-discovery/interview-handoff.md"
LEDGER_FILE="$WS/company-discovery/.interview-link-sends.log"

# ── Read interview state (read-only; tolerate a missing/garbled state file) ───
read_state() {
  python3 - "$STATE_FILE" <<'PYEOF'
import json, sys
try:
    s = json.load(open(sys.argv[1]))
except Exception:
    s = {}
complete = "1" if (s.get("interviewComplete") is True or s.get("buildCompletedAt")) else "0"
slug = str(s.get("companySlug") or s.get("interviewSessionId") or "").strip()
print(f"{complete}|{slug}")
PYEOF
}
STATE_OUT="$(read_state)"
IS_COMPLETE="${STATE_OUT%%|*}"
SLUG="${STATE_OUT#*|}"

if [ "$IS_COMPLETE" = "1" ]; then
  echo "[send-interview-link] REFUSED: the interview is already complete — nothing to invite the owner to." >&2
  exit 3
fi

# Started = a handoff exists AND we have a slug to build the resume link with.
MODE="start"
if [ -f "$HANDOFF_FILE" ] && [ -n "$SLUG" ]; then
  MODE="resume"
fi

# ── Build the message (jargon-free; the link is the only instruction) ─────────
FIRST_NAME="${CLIENT_FIRST_NAME:-there}"
DASH="${OPENCLAW_DASHBOARD_URL:-}"
DASH="${DASH%/}"
LINK=""
if [ -n "$DASH" ]; then
  if [ "$MODE" = "resume" ]; then
    LINK="$DASH/onboarding/resume/$SLUG"
  else
    LINK="$DASH/interview"
  fi
fi

TMP_MSG="$(mktemp)"
trap 'rm -f "$TMP_MSG"' EXIT
if [ -n "$LINK" ] && [ "$MODE" = "resume" ]; then
  cat > "$TMP_MSG" <<EOF
Welcome back, $FIRST_NAME — your interview is saved exactly where you left off. Continue here: $LINK

It works great on your phone, and you can pause again anytime.
EOF
elif [ -n "$LINK" ]; then
  cat > "$TMP_MSG" <<EOF
Hi $FIRST_NAME — your AI Workforce Interview is ready. It's a short conversation in your own words, and we build your company from what you tell us. When you're ready, start here: $LINK

It works great on your phone. Every answer is saved as you go, so you can pause anytime and pick up right where you left off.
EOF
elif [ "$MODE" = "resume" ]; then
  cat > "$TMP_MSG" <<EOF
Welcome back, $FIRST_NAME — your interview is saved exactly where you left off. Whenever you're ready, just reply here and we'll continue from your next question.
EOF
else
  cat > "$TMP_MSG" <<EOF
Hi $FIRST_NAME — your AI Workforce Interview is ready. It's a short conversation in your own words, and we build your company from what you tell us. Whenever you're ready, just reply "ready" here and we'll begin. Every answer is saved as you go, so you can pause anytime.
EOF
fi

# ── Anti-spam guard (30 min, per-box ledger; FORCE=1 bypasses) ────────────────
GUARD_SECS=1800
if [ "$DRY_RUN" -eq 0 ] && [ "${FORCE:-0}" != "1" ] && [ -f "$LEDGER_FILE" ]; then
  LAST_EPOCH="$(tail -1 "$LEDGER_FILE" 2>/dev/null | cut -d'|' -f1 || true)"
  NOW_EPOCH="$(date +%s)"
  if [ -n "$LAST_EPOCH" ] && [ "$LAST_EPOCH" -eq "$LAST_EPOCH" ] 2>/dev/null; then
    AGE=$(( NOW_EPOCH - LAST_EPOCH ))
    if [ "$AGE" -lt "$GUARD_SECS" ]; then
      echo "[send-interview-link] REFUSED: a link was sent $(( AGE / 60 )) minute(s) ago. Re-run with FORCE=1 to re-send deliberately." >&2
      exit 7
    fi
  fi
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
  echo "[send-interview-link] DRY-RUN mode=$MODE chat=$MASKED"
  echo "----- message -----"
  cat "$TMP_MSG"
  echo "-------------------"
  exit 0
fi

# ── Send via the gateway (NEVER direct Bot API) ───────────────────────────────
if ! command -v openclaw >/dev/null 2>&1; then
  echo "[send-interview-link] FATAL: openclaw CLI not on PATH — refusing to fall back to direct HTTP." >&2
  exit 5
fi
if ! openclaw message send --channel telegram --target "$CHAT_ID" --file "$TMP_MSG" >/dev/null 2>&1; then
  echo "[send-interview-link] FAILED: gateway send to chat $MASKED did not succeed. Nothing recorded — safe to retry." >&2
  exit 6
fi

# ── Audit ledger (non-canonical; epoch|mode|link-or-chat-invite) ──────────────
mkdir -p "$(dirname "$LEDGER_FILE")"
printf '%s|%s|%s\n' "$(date +%s)" "$MODE" "${LINK:-telegram-chat-invite}" >> "$LEDGER_FILE"

echo "[send-interview-link] SENT mode=$MODE chat=$MASKED link=${LINK:-telegram-chat-invite}"
