#!/usr/bin/env bash
# qc-notify-client-doc.sh — machine-enforce the MANDATORY Telegram delivery of
# the client's setup-doc LINK.
#
# THE RULE this gate protects: every client gets their setup-doc link via
# Telegram, no matter what. The operator was tired of repeating this, so the
# delivery step is gated — the install is NOT complete until the client has been
# SENT their doc link via Telegram. "Prose in a playbook" is not enforcement; a
# missing/unwired notify step must FAIL the build.
#
# WHAT THIS GATE STATICALLY ASSERTS (from the repo alone, so CI catches a
# regression that drops the step):
#   1. scripts/22-notify-client-doc.sh EXISTS and is bash -n clean.
#   2. It actually sends via the OpenClaw gateway
#      (`openclaw message send --channel telegram`) — NOT curl to api.telegram.org.
#   3. It DISCOVERS the chat from the TRANSCRIPTS (agents/*/sessions/*.jsonl) —
#      grepping the four shapes ("chat":{"id" / telegram:direct: / "chatId": /
#      "from":{"id") and the most-frequent NON-operator id (the Teresa lesson),
#      NOT just sessions.json keys.
#   4. The LOUD-failure contract: on no-chat it writes clientDocDelivered=false
#      and exits non-zero (never silently skips).
#   5. The step is WIRED into the binding instructions: INSTRUCTIONS.md AND the
#      v6.0 source playbook AND both standards reference the mandatory Telegram
#      doc-delivery (so the operator/agent can't miss it).
#
# Exit codes: 0 = all assertions pass; 1 = one or more fail.
#
# BASH only (grep/awk core) — respects qc-static's .py claude-/anthropic ban.
#
# Usage:
#   bash scripts/qc-notify-client-doc.sh
#   bash scripts/qc-notify-client-doc.sh --skill-dir DIR

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '1,40p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

NOTIFY="$SKILL_DIR/scripts/22-notify-client-doc.sh"
INSTR="$SKILL_DIR/INSTRUCTIONS.md"
PLAYBOOK="$SKILL_DIR/references/v6.0-source-playbook.md"
COMMS_STD="$SKILL_DIR/references/communications-playbook-standard.md"
WFAI_STD="$SKILL_DIR/references/workflow-ai-instructions-standard.md"

MISSING=()

# 1. notify script exists + parses
if [ ! -f "$NOTIFY" ]; then
  MISSING+=('scripts/22-notify-client-doc.sh does not exist (the mandatory Telegram doc-delivery script)')
else
  if ! bash -n "$NOTIFY" 2>/dev/null; then
    MISSING+=('scripts/22-notify-client-doc.sh has a bash syntax error (bash -n failed)')
  fi
  # 2. sends via the gateway, not curl to telegram
  grep -qE 'openclaw message send --channel telegram' "$NOTIFY" || \
    MISSING+=('22-notify-client-doc.sh must send via `openclaw message send --channel telegram` (the gateway)')
  # NEVER curl/wget api.telegram.org directly. Ignore comment lines + the
  # prohibition note in this script's own header; flag only an actual
  # curl/wget invocation that targets api.telegram.org.
  if grep -vE '^[[:space:]]*#' "$NOTIFY" | grep -qE '(curl|wget|http[._]?(request|get|post)).*api\.telegram\.org'; then
    MISSING+=('22-notify-client-doc.sh must NOT curl api.telegram.org directly — all Telegram sends go through the OpenClaw gateway')
  fi
  # 3. discovers from transcripts — all four shapes + most-frequent non-operator
  grep -q 'sessions' "$NOTIFY" && grep -q 'jsonl' "$NOTIFY" || \
    MISSING+=('22-notify-client-doc.sh must scan agents/*/sessions/*.jsonl transcripts to discover the chat id')
  grep -q '"chat":\\{"id"' "$NOTIFY" || grep -q '"chat":{"id"' "$NOTIFY" || \
    MISSING+=('22-notify-client-doc.sh must grep the "chat":{"id":<n> shape')
  grep -q 'telegram:direct:' "$NOTIFY" || \
    MISSING+=('22-notify-client-doc.sh must grep the telegram:direct:<n> shape')
  grep -q '"chatId"' "$NOTIFY" || \
    MISSING+=('22-notify-client-doc.sh must grep the "chatId":<n> shape')
  grep -q '"from":\\{"id"' "$NOTIFY" || grep -q '"from":{"id"' "$NOTIFY" || \
    MISSING+=('22-notify-client-doc.sh must grep the "from":{"id":<n> shape')
  grep -qiE 'most-frequent|uniq -c|sort -rn' "$NOTIFY" || \
    MISSING+=('22-notify-client-doc.sh must take the MOST-FREQUENT non-operator id (uniq -c | sort -rn)')
  grep -qE 'grep -vxF "\$OPERATOR_TELEGRAM_CHAT_ID"|grep -v.*OPERATOR_TELEGRAM_CHAT_ID' "$NOTIFY" || \
    MISSING+=('22-notify-client-doc.sh must EXCLUDE the operator id from discovery')
  # 4. LOUD failure contract: clientDocDelivered=false + non-zero exit
  grep -q 'clientDocDelivered' "$NOTIFY" || \
    MISSING+=('22-notify-client-doc.sh must record the clientDocDelivered state field')
  grep -qE 'clientDocDelivered.*false|"clientDocDelivered" "false"' "$NOTIFY" || \
    MISSING+=('22-notify-client-doc.sh must set clientDocDelivered=false when no chat/link is found')
fi

# 5. wired into the binding instructions + standards
[ -f "$INSTR" ] && grep -q '22-notify-client-doc' "$INSTR" || \
  MISSING+=('INSTRUCTIONS.md must reference 22-notify-client-doc.sh (the binding Telegram doc-delivery step)')
[ -f "$PLAYBOOK" ] && grep -qiE 'doc link via Telegram|setup.doc link.*Telegram|Telegram.*(doc|reference) link|link via Telegram' "$PLAYBOOK" || \
  MISSING+=('references/v6.0-source-playbook.md must carry the mandatory "deliver the doc link via Telegram" binding step')
[ -f "$COMMS_STD" ] && grep -qiE '22-notify-client-doc|doc link via Telegram|link via Telegram' "$COMMS_STD" || \
  MISSING+=('references/communications-playbook-standard.md must reference the mandatory Telegram doc-delivery')

echo "=== qc-notify-client-doc: mandatory Telegram doc-delivery gate ==="
echo "skill dir : $SKILL_DIR"
echo ""
if [ "${#MISSING[@]}" -eq 0 ]; then
  echo "  [PASS] 22-notify-client-doc.sh exists, parses, sends via the gateway"
  echo "  [PASS] discovers the chat from agents/*/sessions/*.jsonl (4 shapes, most-frequent non-operator)"
  echo "  [PASS] LOUD-fails (clientDocDelivered=false + non-zero) when no chat is found"
  echo "  [PASS] wired into INSTRUCTIONS.md + v6.0 playbook + the comms standard"
  echo ""
  echo "RESULT: PASS — every client gets their setup-doc link via Telegram, machine-enforced."
  exit 0
else
  echo "RESULT: FAIL — the mandatory Telegram doc-delivery step is missing/unwired:"
  for m in "${MISSING[@]}"; do echo "          - $m"; done
  exit 1
fi
