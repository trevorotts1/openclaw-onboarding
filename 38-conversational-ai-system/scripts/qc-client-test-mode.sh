#!/usr/bin/env bash
# qc-client-test-mode.sh - machine-enforce the U-6 Client Test Mode surface (CARD-14).
#
# WHY THIS GATE EXISTS
# --------------------
# Client Test Mode (protocols/client-test-mode-protocol.md) is the CloseBot CB-8
# testing-portal equivalent: a safe rehearsal lane with REAL playbook + REAL
# tool-gating + REAL knowledge but ALL external side effects SUPPRESSED. If a
# deep-fix regression drops the protocol, the AGENTS wiring, or ANY allow-list
# action category from the suppression list, a real side effect could leak during
# a rehearsal. This gate fails closed on that.
#
# WHAT IT ENFORCES (from the repo alone - CI-safe, BASH-only so it respects the
# .py claude-/anthropic ban):
#   1. protocols/client-test-mode-protocol.md exists.
#   2. scripts/05-update-agents-md.sh inserts the CLIENT_TEST_MODE marker block
#      AND the STEP_0_4_TEST_MODE_REREAD block (the read-before-anything re-read).
#   3. scripts/06-append-memory-rules.sh appends MEMORY Rule 37 (Client Test Mode).
#   4. The protocol documents the three-layer enforcement: the active-test.md state
#      flag re-read at Step 0.4, the U-1 tool gate forced to the empty set plus
#      reference_documents, and the WOULD HAVE narration contract.
#   5. The protocol requires the TEST MODE banner on every message.
#   6. The protocol logs test transcripts to test-sessions/ ONLY (never the
#      per-contact conversation logs), and auto-expires after 60 minutes.
#   7. The side-effect SUPPRESSION LIST covers EVERY allow-list action category:
#      book_appointment, check_availability, cancel_reschedule, update_tags,
#      update_contact, crm_field_write, webhook_chain, send_invoice,
#      create_discount_code, escalate_to_human. Omitting any one FAILS.
#
# Exit codes: 0 = clean; 1 = at least one Client Test Mode violation.
#
# Usage:
#   bash scripts/qc-client-test-mode.sh
#   bash scripts/qc-client-test-mode.sh --skill-dir /path/to/38-conversational-ai-system

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help)   sed -n '1,40p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

FAIL=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAIL=1; }

PROTO="$SKILL_DIR/protocols/client-test-mode-protocol.md"
AG="$SKILL_DIR/scripts/05-update-agents-md.sh"
MEM="$SKILL_DIR/scripts/06-append-memory-rules.sh"

echo "=== qc-client-test-mode: U-6 Client Test Mode surface gate ==="
echo "skill_dir : $SKILL_DIR"
echo ""

# 1. Protocol exists.
if [ -f "$PROTO" ]; then
  pass "protocols/client-test-mode-protocol.md exists"
else
  fail "protocols/client-test-mode-protocol.md MISSING"
fi

# require_proto <label> <needle> - fails if the protocol is missing OR the needle absent.
require_proto() {
  local label="$1" needle="$2"
  if [ -f "$PROTO" ] && grep -qiF -- "$needle" "$PROTO"; then
    pass "$label"
  else
    fail "$label - expected in the protocol: \"$needle\""
  fi
}

# 2. AGENTS wiring: both marker blocks.
if [ -f "$AG" ] && grep -q 'CLIENT_TEST_MODE' "$AG"; then
  pass "05-update-agents-md.sh inserts the CLIENT_TEST_MODE block"
else
  fail "05-update-agents-md.sh is MISSING the CLIENT_TEST_MODE block"
fi
if [ -f "$AG" ] && grep -q 'STEP_0_4_TEST_MODE_REREAD' "$AG"; then
  pass "05-update-agents-md.sh inserts the STEP_0_4_TEST_MODE_REREAD block"
else
  fail "05-update-agents-md.sh is MISSING the STEP_0_4_TEST_MODE_REREAD block"
fi

# 3. MEMORY Rule 37.
if [ -f "$MEM" ] && grep -qE '^37\. *Client Test Mode Rule' "$MEM"; then
  pass "06-append-memory-rules.sh appends MEMORY Rule 37 (Client Test Mode)"
else
  fail "06-append-memory-rules.sh is MISSING MEMORY Rule 37 (Client Test Mode)"
fi

# 4. Three-layer enforcement.
require_proto "layer 1: active-test.md state flag re-read"       "test-sessions/active-test.md"
require_proto "layer 1: re-read FIRST at Step 0.4"               "Step 0.4"
require_proto "layer 2: U-1 gate forced to empty set + reference_documents" "EMPTY set plus"
require_proto "layer 2: reuses the U-1 tool gate"               "tool gate"
require_proto "layer 3: WOULD HAVE narration contract"          "WOULD HAVE"

# 5. TEST MODE banner.
require_proto "TEST MODE banner on every message"              "TEST MODE"

# 6. Isolation + expiry.
require_proto "test transcripts log to test-sessions/ only"    "test-sessions/"
require_proto "auto-expires after 60 minutes"                  "60"
require_proto "expiry deletes active-test.md"                  "DELETES"

# 7. Suppression list covers EVERY allow-list action category.
SUPPRESSED_TOOLS=(
  "book_appointment"
  "check_availability"
  "cancel_reschedule"
  "update_tags"
  "update_contact"
  "crm_field_write"
  "webhook_chain"
  "send_invoice"
  "create_discount_code"
  "escalate_to_human"
)
for t in "${SUPPRESSED_TOOLS[@]}"; do
  if [ -f "$PROTO" ] && grep -qF "$t" "$PROTO"; then
    pass "suppression list covers: $t"
  else
    fail "suppression list OMITS an allow-list action category: $t"
  fi
done

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS - Client Test Mode protocol, AGENTS wiring, MEMORY Rule 37, three-layer enforcement, banner, isolation/expiry, and the full suppression list are all present."
  exit 0
else
  echo "RESULT: FAIL - a Client Test Mode requirement is missing (see above)."
  exit 1
fi
