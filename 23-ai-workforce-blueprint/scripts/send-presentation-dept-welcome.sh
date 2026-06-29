#!/usr/bin/env bash
# send-presentation-dept-welcome.sh -- v1.0.0
#
# Auto-sends the "your Presentations Department is live" welcome message to the
# client owner the moment their presentations department passes both the
# wiring gate (wiringStatus==done) and the library gate (roleLibraryFilled &&
# sopLibraryFilled). Reads ALL values from the box's own config -- never
# hardcodes a client name, chat ID, or credential.
#
# IDEMPOTENCY: checks .workforce-build-state.json for
#   .departments[] | select(.slug=="presentations") | .presentationDeptWelcomeSent
# If that is already true, the script exits 0 immediately without sending.
#
# PASS GATE: the message is ONLY sent when:
#   (a) the presentations dept entry has wiringStatus == "done"
#   (b) the presentations dept entry has roleLibraryFilled == true
#   (c) the presentations dept entry has sopLibraryFilled == true
# Any condition not met = exit 2 (not a failure; gate not yet passed).
#
# PLACEHOLDER RESOLUTION (from state file; no hardcoding):
#   {{OWNER_FIRST_NAME}}           -- .ownerName (first word); fallback "there"
#   {{BUSINESS_NAME}}              -- .companyName; fallback "your business"
#   {{DEPT_HEAD_PERSONA_OR_ROLE}}  -- departments[presentations].deptHeadPersona;
#                                     fallback "your Presentations Department head"
#
# Canonical template location:
#   templates/role-library/presentations/first-time-onboarding-presentations.md
#   Section 20 -- Auto-Send Welcome Message
#
# FLEET GENERIC: works identically on Mac (~/. openclaw) and VPS (/data/.openclaw).
#
# USAGE:
#   bash send-presentation-dept-welcome.sh               # live send
#   bash send-presentation-dept-welcome.sh --dry-run     # print resolved message; no send, no marker
#   bash send-presentation-dept-welcome.sh --force       # skip idempotency check (re-send)
#
# EXIT CODES:
#   0 -- sent (or already sent + idempotency guard triggered, or --dry-run success)
#   2 -- gate not yet passed (dept not fully wired + library done)
#   3 -- ownerChat missing or unparseable in state file
#   9 -- fatal prereq (jq missing, no state file, openclaw not available for live send)

set -uo pipefail

# ---- platform detection -------------------------------------------------------
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[send-presentation-dept-welcome] FATAL: no OpenClaw root at /data/.openclaw or \$HOME/.openclaw" >&2
  exit 9
fi

STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"

# ---- args --------------------------------------------------------------------
DRY_RUN=0
FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --force)   FORCE=1;   shift ;;
    -h|--help)
      sed -n '2,50p' "$0"
      exit 0
      ;;
    *)
      echo "[send-presentation-dept-welcome] WARN: unknown arg '$1' (ignored)" >&2
      shift
      ;;
  esac
done

# ---- prereqs -----------------------------------------------------------------
if ! command -v jq >/dev/null 2>&1; then
  echo "[send-presentation-dept-welcome] FATAL: jq not installed" >&2
  exit 9
fi
if [[ ! -f "$STATE_FILE" ]]; then
  echo "[send-presentation-dept-welcome] FATAL: no state file at $STATE_FILE" >&2
  exit 9
fi

# ---- idempotency check -------------------------------------------------------
if [[ "$FORCE" -eq 0 ]]; then
  ALREADY_SENT=$(jq -r '
    (.departments // [])
    | map(select(.slug == "presentations"))
    | first
    | .presentationDeptWelcomeSent // false
  ' "$STATE_FILE" 2>/dev/null || echo "false")
  if [[ "$ALREADY_SENT" == "true" ]]; then
    echo "[send-presentation-dept-welcome] Already sent (presentationDeptWelcomeSent=true). Nothing to do. Use --force to re-send."
    exit 0
  fi
fi

# ---- gate check --------------------------------------------------------------
PRESENTATIONS_ENTRY=$(jq -r '
  (.departments // [])
  | map(select(.slug == "presentations"))
  | first // null
' "$STATE_FILE" 2>/dev/null || echo "null")

if [[ "$PRESENTATIONS_ENTRY" == "null" ]]; then
  echo "[send-presentation-dept-welcome] Gate not passed: presentations department not found in state file." >&2
  exit 2
fi

WIRING_STATUS=$(printf '%s' "$PRESENTATIONS_ENTRY" | jq -r '.wiringStatus // "pending"')
ROLE_LIB_FILLED=$(printf '%s' "$PRESENTATIONS_ENTRY" | jq -r '.roleLibraryFilled // false')
SOP_LIB_FILLED=$(printf '%s' "$PRESENTATIONS_ENTRY" | jq -r '.sopLibraryFilled // false')

GATE_PASS=1
GATE_REASONS=()
[[ "$WIRING_STATUS" != "done" ]]     && GATE_PASS=0 && GATE_REASONS+=("wiringStatus=$WIRING_STATUS (need done)")
[[ "$ROLE_LIB_FILLED" != "true" ]]   && GATE_PASS=0 && GATE_REASONS+=("roleLibraryFilled=$ROLE_LIB_FILLED (need true)")
[[ "$SOP_LIB_FILLED" != "true" ]]    && GATE_PASS=0 && GATE_REASONS+=("sopLibraryFilled=$SOP_LIB_FILLED (need true)")

if [[ "$GATE_PASS" -eq 0 ]]; then
  echo "[send-presentation-dept-welcome] Gate not yet passed. Conditions not met: ${GATE_REASONS[*]}" >&2
  exit 2
fi

echo "[send-presentation-dept-welcome] Gate PASSED: wiring=done, roleLibraryFilled=true, sopLibraryFilled=true"

# ---- resolve placeholders from state file ------------------------------------
RAW_OWNER_NAME=$(jq -r '.ownerName // ""' "$STATE_FILE" 2>/dev/null || echo "")
OWNER_FIRST_NAME=$(printf '%s' "$RAW_OWNER_NAME" | awk '{print $1}')
[[ -z "$OWNER_FIRST_NAME" ]] && OWNER_FIRST_NAME="there"

BUSINESS_NAME=$(jq -r '.companyName // ""' "$STATE_FILE" 2>/dev/null || echo "")
[[ -z "$BUSINESS_NAME" || "$BUSINESS_NAME" == "null" ]] && BUSINESS_NAME="your business"

DEPT_HEAD_PERSONA=$(printf '%s' "$PRESENTATIONS_ENTRY" | jq -r '.deptHeadPersona // ""' 2>/dev/null || echo "")
[[ -z "$DEPT_HEAD_PERSONA" || "$DEPT_HEAD_PERSONA" == "null" ]] && DEPT_HEAD_PERSONA="your Presentations Department head"

# ---- owner chat ID -----------------------------------------------------------
OWNER_CHAT=$(jq -r '.ownerChat // ""' "$STATE_FILE" 2>/dev/null || echo "")
if [[ -z "$OWNER_CHAT" || "$OWNER_CHAT" == "null" ]]; then
  echo "[send-presentation-dept-welcome] FATAL: ownerChat not set in state file -- cannot send" >&2
  exit 3
fi

# ---- compose message (fill placeholders) -------------------------------------
# Canonical template: first-time-onboarding-presentations.md Section 20.
# Uses -- instead of em dash throughout (em dash KPI = 0).
MESSAGE="Hi ${OWNER_FIRST_NAME}! I'm the head of your Presentations Department at ${BUSINESS_NAME}. Think of me as your creative partner, not just a tool that converts files. You do NOT need a finished presentation, a script, or even a rough draft -- you can start from a blank page. Here's how it works from scratch: 1) Tell me what you want to give -- a talk, pitch, webinar, even just a goal or feeling; one sentence is enough. 2) We brainstorm together, and you set the pace: first you pick a quick interview (a few key questions) or a more in-depth one, then I ask one question at a time, never a wall of questions. 3) I draft the outline and read it back for your yes/adjust/redirect. 4) Once you greenlight it, the team builds the full package: cinematic slide deck, Presenter's Guide, word-for-word speech, and audio demonstration -- you review and tweak at each stage. You get a finished PowerPoint and PDF ready to deliver. The key thing: I brainstorm WITH you -- you don't need it figured out, that's what I'm here for. Ready to start one right now? Just send me: 'Help me brainstorm a presentation about ___ for ___' -- or even just 'I want to create a new presentation, let's brainstorm.'"

# ---- dry-run mode -----------------------------------------------------------
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo ""
  echo "[send-presentation-dept-welcome] DRY-RUN -- resolved values:"
  echo "  OWNER_FIRST_NAME : $OWNER_FIRST_NAME"
  echo "  BUSINESS_NAME    : $BUSINESS_NAME"
  echo "  DEPT_HEAD_PERSONA: $DEPT_HEAD_PERSONA"
  echo "  OWNER_CHAT       : $OWNER_CHAT"
  echo ""
  echo "--- RESOLVED MESSAGE ---"
  printf '%s\n' "$MESSAGE"
  echo "--- END MESSAGE ---"
  echo ""
  echo "[send-presentation-dept-welcome] DRY-RUN complete. No message sent, no marker written."
  exit 0
fi

# ---- live send ---------------------------------------------------------------
if ! command -v openclaw >/dev/null 2>&1; then
  echo "[send-presentation-dept-welcome] FATAL: openclaw CLI not found -- cannot send live message. Run with --dry-run to test without sending." >&2
  exit 9
fi

echo "[send-presentation-dept-welcome] Sending welcome to ownerChat=$OWNER_CHAT ..."
SEND_RC=0
openclaw message send --channel telegram -t "$OWNER_CHAT" -m "$MESSAGE" || SEND_RC=$?

if [[ "$SEND_RC" -ne 0 ]]; then
  echo "[send-presentation-dept-welcome] ERROR: openclaw message send returned rc=$SEND_RC -- NOT writing idempotency marker (will retry next gate pass)" >&2
  exit "$SEND_RC"
fi

# ---- write idempotency marker ------------------------------------------------
TS_NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TMP_STATE=$(mktemp)
jq --arg ts "$TS_NOW" '
  .departments = ((.departments // []) | map(
    if .slug == "presentations"
    then . + {presentationDeptWelcomeSent: true, presentationDeptWelcomeSentAt: $ts}
    else .
    end
  ))
' "$STATE_FILE" > "$TMP_STATE" 2>/dev/null && mv "$TMP_STATE" "$STATE_FILE" \
  || { rm -f "$TMP_STATE"; echo "[send-presentation-dept-welcome] WARN: could not write idempotency marker to state file (send succeeded)" >&2; }

echo "[send-presentation-dept-welcome] Welcome sent and idempotency marker written (presentationDeptWelcomeSent=true at $TS_NOW)."
exit 0
