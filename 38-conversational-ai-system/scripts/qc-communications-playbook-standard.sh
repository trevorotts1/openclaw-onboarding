#!/usr/bin/env bash
# qc-communications-playbook-standard.sh — machine-enforce the COMMUNICATION PLAYBOOK
# STANDARD (references/communications-playbook-standard.md).
#
# WHY: the communication-playbook output drifted run-to-run. This gate asserts the
# standard doc carries the hard leading "EVERY COMMUNICATION PLAYBOOK MUST INCLUDE ALL
# OF THE FOLLOWING" mandatory checklist (Section 0) AND every required item (a)-(i),
# so a regression that deletes or guts the checklist fails the build.
#
# WHAT IT CHECKS (from the repo alone — CI-safe, BASH-only so it respects the .py
# claude-/anthropic ban):
#   1. references/communications-playbook-standard.md exists.
#   2. It has the leading mandatory-checklist headline (Section 0).
#   3. It names all 8 channels in that section.
#   4. Each mandatory item (a)-(i) is present with its load-bearing concept.
#   5. The doc points at the enforcing gate (this script) — self-consistency.
#   6. SKILL.md / INSTRUCTIONS.md carry a pointer to the standard.
#
# Exit codes: 0 = clean; 1 = at least one mandatory item missing.
#
# Usage:
#   bash scripts/qc-communications-playbook-standard.sh
#   bash scripts/qc-communications-playbook-standard.sh --skill-dir DIR
#   bash scripts/qc-communications-playbook-standard.sh --doc PATH   # negative-test a fixture

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DOC=""

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    --doc)       DOC="$2"; shift 2 ;;
    -h|--help)   sed -n '1,30p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

[ -n "$DOC" ] || DOC="$SKILL_DIR/references/communications-playbook-standard.md"

FAIL=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAIL=1; }

echo "=== qc-communications-playbook-standard: COMMUNICATION PLAYBOOK STANDARD gate ==="
echo "doc : $DOC"
echo ""

if [ ! -f "$DOC" ]; then
  echo "  [FAIL] standard doc MISSING: $DOC"
  echo ""
  echo "RESULT: FAIL"
  exit 1
fi

# 1. The hard leading mandatory-checklist headline (Section 0).
if grep -qiE 'EVERY COMMUNICATION PLAYBOOK MUST INCLUDE ALL OF THE FOLLOWING' "$DOC"; then
  pass "Section 0 mandatory-checklist headline present"
else
  fail "missing the leading 'EVERY COMMUNICATION PLAYBOOK MUST INCLUDE ALL OF THE FOLLOWING' headline"
fi

# 2. NON-NEGOTIABLE framing.
grep -qiE 'NON-NEGOTIABLE' "$DOC" && pass "checklist framed NON-NEGOTIABLE" || fail "checklist must be framed NON-NEGOTIABLE"

# 3. All 8 channels named.
CHANNELS=("SMS" "Email" "FB Messenger" "FB comments" "IG DM" "LinkedIn" "Live Chat" "All-in-One")
for c in "${CHANNELS[@]}"; do
  if grep -qF "$c" "$DOC"; then pass "channel named: $c"; else fail "channel NOT named: $c"; fi
done

# 4. Each mandatory item (a)-(i) — match on the load-bearing concept, not just the letter.
declare -a ITEM_KEYS=(
  "channel + persona|persona / voice identity|persona/voice"
  "opening behavior|how to greet|greet"
  "conversation GOAL|GOAL / desired outcome|desired outcome"
  "MANDATORY SEND|GHL Conversations API|drafting/composing is NOT sending|Drafting"
  "Conversation-memory|read-before|append-after|conversational-logs"
  "Escalation|HONESTY FLOOR|honesty floor|NEEDS_HUMAN"
  "Quiet-hours|quiet hours|compliance|STOP"
  "ZHC- tag-prefix|ZHC- prefix for|programmatic tags? carr|programmatic.{0,12}ZHC-"
  "Per-channel formatting|formatting constraints|160 chars|24-hour"
)
declare -a ITEM_NAMES=(
  "(a) channel + persona/voice identity"
  "(b) opening behavior + how to greet"
  "(c) conversation goal / desired outcome"
  "(d) mandatory SEND rule (Conversations API, mirror, drafting != sending)"
  "(e) conversation-memory read-before/append-after"
  "(f) escalation/handoff + honesty floor"
  "(g) quiet-hours + compliance-keyword respect"
  "(h) ZHC- tag-prefix for programmatic tags"
  "(i) per-channel formatting constraints"
)
i=0
for keyset in "${ITEM_KEYS[@]}"; do
  if grep -qiE "$keyset" "$DOC"; then
    pass "mandatory item present: ${ITEM_NAMES[$i]}"
  else
    fail "mandatory item MISSING: ${ITEM_NAMES[$i]}"
  fi
  i=$((i+1))
done

# 5. Self-consistency: the doc names its enforcing gate.
grep -qF 'qc-communications-playbook-standard.sh' "$DOC" \
  && pass "doc references its enforcing gate (qc-communications-playbook-standard.sh)" \
  || fail "doc must reference its enforcing gate (qc-communications-playbook-standard.sh)"

# 6. SKILL.md / INSTRUCTIONS.md pointer (skip when running against a fixture --doc).
if [ -z "${DOC##*communications-playbook-standard.md}" ]; then
  PTR=0
  for f in "$SKILL_DIR/SKILL.md" "$SKILL_DIR/INSTRUCTIONS.md"; do
    [ -f "$f" ] && grep -qF 'communications-playbook-standard.md' "$f" && PTR=1
  done
  [ "$PTR" -eq 1 ] && pass "SKILL.md/INSTRUCTIONS.md point to the standard" \
                    || fail "SKILL.md or INSTRUCTIONS.md must point to references/communications-playbook-standard.md"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — the communication playbook standard carries the mandatory checklist + every required item (a)-(i)."
  exit 0
else
  echo "RESULT: FAIL — a communication-playbook-standard mandatory item is missing (see above)."
  exit 1
fi
