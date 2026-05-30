#!/usr/bin/env bash
# qc-self-test.sh — machine-enforce the AI BACKEND SELF-TEST standard (REQ 5).
#
# THE RULE this gate protects: after the agent configures the hook and BEFORE the
# client is ever told to test, the agent MUST self-test the full inbound->reply
# chain by ground truth (readiness -> synthetic flat-23-key POST -> verify
# 200/{ok:true} + configured model with no 401/429 + conversation-log read + GHL
# Conversations API 200/201, with temp-contact create/delete + cleanup). Setup is
# NOT complete and the client is NOT told to test until the self-test passes.
# "Prose in a playbook" is not enforcement — a missing/unwired self-test must FAIL
# the build.
#
# WHAT THIS GATE STATICALLY ASSERTS (from the repo alone):
#   1. scripts/12-self-test-hook.sh EXISTS and is bash -n clean.
#   2. It POSTs a SYNTHETIC inbound to the OWN public hook URL with the REAL Bearer
#      token (curl POST to /hooks/ + Authorization: Bearer).
#   3. It builds a FLAT 23-key body (channel sms) field-by-field (not as a
#      ```json block) and self-checks it is 23 keys + flat before sending.
#   4. It verifies BY GROUND TRUTH: hook 200/{ok:true}; no 401/429 from the model;
#      a conversational-logs read; and a GHL Conversations API 200/201 messageId.
#   5. It does temp-contact CREATE + DELETE + log cleanup for the real send.
#   6. It writes the selfTestPassed state field and FAILS (non-zero) on any failure.
#   7. It is WIRED as a BLOCKING readiness gate in scripts/11-run-qc-checklist.sh
#      (the checklist must assert selfTestPassed=true), and documented in
#      references/GHL-INBOUND-AND-PLAYBOOKS.md (the self-test standard).
#
# Exit codes: 0 = all assertions pass; 1 = one or more fail.
# BASH only (grep core) — respects qc-static's .py claude-/anthropic ban.
#
# Usage: bash scripts/qc-self-test.sh [--skill-dir DIR]

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

ST="$SKILL_DIR/scripts/12-self-test-hook.sh"
QCC="$SKILL_DIR/scripts/11-run-qc-checklist.sh"
DOC="$SKILL_DIR/references/GHL-INBOUND-AND-PLAYBOOKS.md"

MISSING=()

if [ ! -f "$ST" ]; then
  MISSING+=('scripts/12-self-test-hook.sh does not exist (the backend self-test)')
else
  bash -n "$ST" 2>/dev/null || MISSING+=('scripts/12-self-test-hook.sh has a bash syntax error (bash -n failed)')
  grep -qiE 'POST .*\$ENDPOINT|-X POST "\$ENDPOINT"|curl .* -X POST' "$ST" || \
    MISSING+=('12-self-test-hook.sh must POST a synthetic inbound (curl -X POST to the hook)')
  grep -qE 'hooks/\$\{?HOOK_NAME' "$ST" || grep -qE '/hooks/' "$ST" || \
    MISSING+=('12-self-test-hook.sh must POST to its OWN public hook URL (/hooks/<HOOK_NAME>)')
  grep -qE 'Authorization: Bearer \$\{?HOOKS_TOKEN' "$ST" || grep -qiE 'Bearer .*HOOKS_TOKEN' "$ST" || \
    MISSING+=('12-self-test-hook.sh must send the REAL Bearer token (Authorization: Bearer $HOOKS_TOKEN)')
  grep -q '"channel":"sms"' "$ST" || MISSING+=('12-self-test-hook.sh synthetic body must be channel=sms')
  grep -qiE '23-key|23 key|len\(d\)==23|==23' "$ST" || \
    MISSING+=('12-self-test-hook.sh must build/verify a 23-key body')
  grep -qiE 'ok.*:.*true|"ok"\[\[:space:\]\]\*:\[\[:space:\]\]\*true|ok.*true' "$ST" || \
    MISSING+=('12-self-test-hook.sh must verify the hook returns {ok:true}')
  grep -qE '401|429' "$ST" || MISSING+=('12-self-test-hook.sh must check for 401/429 from the model')
  grep -q 'conversational-logs' "$ST" || MISSING+=('12-self-test-hook.sh must verify a conversational-logs read')
  grep -qi 'conversations/messages' "$ST" || \
    MISSING+=('12-self-test-hook.sh must call the GHL Conversations API (conversations/messages) for the real send')
  grep -qiE 'messageId' "$ST" || MISSING+=('12-self-test-hook.sh must confirm the GHL send returns a messageId')
  grep -qiE 'DELETE .*contacts/|delete.*temp.*contact' "$ST" || \
    MISSING+=('12-self-test-hook.sh must DELETE the temporary test contact (cleanup)')
  grep -q 'selfTestPassed' "$ST" || MISSING+=('12-self-test-hook.sh must write the selfTestPassed state field')
  grep -qE 'selfTestPassed.*false|"selfTestPassed" "false"' "$ST" || \
    MISSING+=('12-self-test-hook.sh must set selfTestPassed=false on failure')
fi

# wired as a BLOCKING readiness gate in 11-run-qc-checklist.sh
[ -f "$QCC" ] && grep -q 'selfTestPassed' "$QCC" || \
  MISSING+=('scripts/11-run-qc-checklist.sh must assert selfTestPassed=true (the blocking readiness gate)')
[ -f "$QCC" ] && grep -q '12-self-test-hook' "$QCC" || \
  MISSING+=('scripts/11-run-qc-checklist.sh must reference scripts/12-self-test-hook.sh')

# documented as the standard in the authoritative reference
[ -f "$DOC" ] && grep -qiE 'self-test|self test' "$DOC" || \
  MISSING+=('references/GHL-INBOUND-AND-PLAYBOOKS.md must document the backend self-test standard')

echo "=== qc-self-test: backend self-test standard + gate ==="
echo "skill dir : $SKILL_DIR"
echo ""
if [ "${#MISSING[@]}" -eq 0 ]; then
  echo "  [PASS] 12-self-test-hook.sh exists, parses, POSTs a synthetic flat-23-key inbound with the real Bearer"
  echo "  [PASS] verifies 200/{ok:true} + no 401/429 + conversation-log read + GHL send messageId + temp-contact cleanup"
  echo "  [PASS] writes selfTestPassed, fails on error, wired as a blocking readiness gate + documented"
  echo ""
  echo "RESULT: PASS — the agent self-tests the backend by ground truth before the client ever does."
  exit 0
else
  echo "RESULT: FAIL — the backend self-test standard is missing/unwired:"
  for m in "${MISSING[@]}"; do echo "          - $m"; done
  exit 1
fi
