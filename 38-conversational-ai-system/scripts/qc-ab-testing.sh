#!/usr/bin/env bash
# qc-ab-testing.sh — machine-enforce the A/B Testing of Reply Variants feature
# (F16, Round-2 backlog): the A/B-testing protocol, the TWO variants per channel, the
# DETERMINISTIC-BY-CONTACT assignment (a contact stays in one arm), the AT-DRAFT-TIME
# variant selection (AGENTS Step 1.87), the three outcome metrics (booked / converted /
# sentiment trajectory), the documented two-proportion z-test significance check + the
# sane default N, the auto-promote-with-operator-notify flow, the ZHC-abtest-variant-
# tags, the operator-only/never-customer-invoked guard, the PII-free F52 log, and the
# default-OFF toggle are all present and wired where they must be — so a regression that
# drops any load-bearing invariant fails the build.
#
# WHY: when the operator doesn't KNOW which reply style converts, F16 lets them MEASURE
# it instead of guessing — two playbook variants, a deterministic split so a contact
# stays in one arm, outcome tracking, a real significance test, and an auto-promoted
# winner — without ever letting a customer drive the experiment or letting a variant
# disable a hard-gate. This gate proves the skill's docs/wiring actually carry that
# guarantee.
#
# WHAT IT CHECKS (all from the repo alone — CI-safe, BASH-only so it respects the .py
# claude-/anthropic ban):
#   1. The protocol exists (ab-testing-protocol.md) and states its load-bearing
#      substance: TWO variants (a/b) per channel, the per-channel experiment definition
#      (experiments + ab-experiments/<channel>.md), the DETERMINISTIC-BY-CONTACT
#      assignment (a contact stays in one arm — sticky), the AT-DRAFT-TIME Step 1.87
#      placement, ALL THREE outcome metrics (booked / converted / sentiment trajectory),
#      the two-proportion z-test + the sane default N (30/arm), the auto-promote +
#      operator-notify flow, the ZHC-abtest-variant- tag prefix, the operator-only/
#      never-customer-invoked guard, and the honest "REUSES the reply-draft path +
#      existing signals / NOT a new statistics engine or platform" scope.
#   2. AGENTS.md gets the STEP_1_87_AB_TESTING marker block (05-update-agents-md.sh).
#   3. MEMORY Rule 29 is appended (06-append-memory-rules.sh).
#   4. The F52 log ab-test-events.jsonl: documented in the protocol with a
#      timestamp+event_type example carrying event_type "variant_assigned", documented
#      in INSTRUCTIONS.md, and SEEDED by 25-seed-round3-feature-files.sh. The seeder
#      also seeds the ab-experiments/ dir + the example experiment + the two overlays.
#   5. PII guard: the protocol's JSONL example lines must NOT carry a raw customer-value
#      key (value_written/"value"/field_value/raw_value/email/phone/address/name) — the
#      contract is the experiment id + channel + arm label + opaque contact ref +
#      outcome flags + counts.
#   6. The toggle skill38.ab_testing.enabled is documented DEFAULT FALSE.
#
# Exit codes: 0 = clean; 1 = at least one F16 invariant violation.
#
# Usage:
#   bash scripts/qc-ab-testing.sh
#   bash scripts/qc-ab-testing.sh --skill-dir /path/to/38-conversational-ai-system

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help)   sed -n '1,52p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

FAIL=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAIL=1; }

echo "=== qc-ab-testing: F16 A/B testing of reply variants gate ==="
echo "skill_dir : $SKILL_DIR"
echo ""

PROTO="$SKILL_DIR/protocols/ab-testing-protocol.md"
AG_SCRIPT="$SKILL_DIR/scripts/05-update-agents-md.sh"
MEM_SCRIPT="$SKILL_DIR/scripts/06-append-memory-rules.sh"
INSTR="$SKILL_DIR/INSTRUCTIONS.md"
INSTALLER="$SKILL_DIR/scripts/25-seed-round3-feature-files.sh"
JSONL="ab-test-events.jsonl"
EVT="variant_assigned"

# 1. Protocol exists + load-bearing substance.
if [ -f "$PROTO" ]; then
  pass "protocols/ab-testing-protocol.md exists"

  # TWO variants per channel (a/b).
  if grep -q 'variant_a' "$PROTO" && grep -q 'variant_b' "$PROTO" \
     && grep -qiE 'two (communication-playbook )?variants|TWO variants|two variants' "$PROTO"; then
    pass "protocol defines TWO variants per channel (variant_a / variant_b)"
  else
    fail "protocol must define TWO variants per channel (variant_a / variant_b)"
  fi

  # Per-channel experiment definition (experiments + ab-experiments/<channel>.md).
  if grep -q 'ab_testing.experiments\|skill38.ab_testing.experiments\|"experiments"' "$PROTO" \
     && grep -q 'ab-experiments/' "$PROTO"; then
    pass "protocol defines the per-channel experiment mapping (experiments + ab-experiments/<channel>.md)"
  else
    fail "protocol must define the per-channel experiment mapping (experiments + ab-experiments/<channel>.md companion)"
  fi

  # DETERMINISTIC-BY-CONTACT assignment, sticky (a contact stays in one arm).
  if grep -qiE 'deterministic[ -]?by[ -]?contact|deterministic_by_contact' "$PROTO" \
     && grep -qiE 'stays in one arm|same (variant|arm)|sticky' "$PROTO"; then
    pass "protocol assigns each conversation DETERMINISTICALLY BY CONTACT (a contact stays in one arm — sticky)"
  else
    fail "protocol must assign deterministically by contact (a contact stays in one arm — sticky)"
  fi

  # AT-DRAFT-TIME Step 1.87 placement.
  if grep -q 'Step 1.87' "$PROTO" && grep -qiE 'draft time|at draft|reply.?draft' "$PROTO"; then
    pass "protocol selects the variant AT DRAFT TIME (AGENTS Step 1.87)"
  else
    fail "protocol must select the variant AT DRAFT TIME (AGENTS Step 1.87)"
  fi

  # ALL THREE outcome metrics.
  om_missing=0
  grep -qi 'booked'                "$PROTO" || { fail "protocol must track the 'booked' outcome";    om_missing=1; }
  grep -qi 'converted'             "$PROTO" || { fail "protocol must track the 'converted' outcome"; om_missing=1; }
  grep -qi 'sentiment_trajectory\|sentiment trajectory' "$PROTO" || { fail "protocol must track the sentiment trajectory outcome"; om_missing=1; }
  [ "$om_missing" -eq 0 ] && pass "protocol tracks ALL THREE outcome metrics (booked / converted / sentiment trajectory)"

  # Significance method + the sane default N.
  if grep -qiE 'two-proportion z-test|two proportion z-test|z-test' "$PROTO" \
     && grep -qiE 'min_conversations_per_arm|min_per_arm|N ?= ?30|30/arm|30 (per|conversations) (arm|per arm)' "$PROTO"; then
    pass "protocol documents the significance method (two-proportion z-test) + a sane default N (30/arm)"
  else
    fail "protocol must document the significance method (two-proportion z-test) + a sane default N (e.g. 30/arm)"
  fi

  # Auto-promote + operator-notify.
  if grep -qiE 'auto[ -]?promote|auto_promote' "$PROTO" \
     && grep -qiE 'operator.?notif|notif(y|ied|ies) the operator|operator is (notified|informed)' "$PROTO"; then
    pass "protocol auto-promotes the winner WITH operator notification"
  else
    fail "protocol must auto-promote the winner WITH operator notification"
  fi

  # ZHC-abtest-variant- tag prefix (both arms).
  if grep -q 'ZHC-abtest-variant-a' "$PROTO" && grep -q 'ZHC-abtest-variant-b' "$PROTO"; then
    pass "protocol uses the ZHC-abtest-variant-a / ZHC-abtest-variant-b tags for agent-created arm tags"
  else
    fail "protocol must use the ZHC-abtest-variant-a / ZHC-abtest-variant-b tags for agent-created arm tags"
  fi

  # operator-only / never-customer-invoked guard. Keyed on the EXPERIMENT-CONTROL guard
  # language specifically (NOT the generic PII "never a customer name" disclaimer): the
  # operator-only statement PLUS the A/B-injection / experiment-control-instruction /
  # can-never-(define|alter|control)-an-experiment phrasing.
  if grep -qi 'operator-only\|operator only' "$PROTO" \
     && grep -qiE 'A/B-injection|experiment-control instruction|can never (define or alter|control) (an )?(the )?experiment' "$PROTO"; then
    pass "protocol states experiment control is operator-only / a customer can never control the experiment"
  else
    fail "protocol must state experiment control is operator-only / never customer-invoked (A/B-injection guard)"
  fi

  # honest scope: REUSES the reply-draft path + existing signals; NOT a new stats engine/platform.
  if grep -qiE 'NOT (build|a new).*(statistics|experimentation|platform|CRM)|does NOT build|REUSES the (reply-draft|existing)' "$PROTO"; then
    pass "protocol is honest about scope (REUSES the reply-draft path + existing signals; NOT a new statistics engine/platform)"
  else
    fail "protocol must be honest about scope (REUSES the reply-draft path + existing signals; NOT a new statistics engine/platform)"
  fi
else
  fail "protocols/ab-testing-protocol.md MISSING"
fi

echo ""

# 2. AGENTS.md marker block.
if [ -f "$AG_SCRIPT" ] && grep -q 'STEP_1_87_AB_TESTING' "$AG_SCRIPT"; then
  pass "05-update-agents-md.sh inserts the STEP_1_87_AB_TESTING block"
else
  fail "05-update-agents-md.sh is missing the STEP_1_87_AB_TESTING block"
fi

# 3. MEMORY Rule 29.
if [ -f "$MEM_SCRIPT" ] && grep -qE '^29\. *A/B Testing Rule' "$MEM_SCRIPT"; then
  pass "06-append-memory-rules.sh appends MEMORY Rule 29 (A/B Testing Rule)"
else
  fail "06-append-memory-rules.sh is missing MEMORY Rule 29 (A/B Testing Rule)"
fi

echo ""

# 4. F52 log: protocol example + INSTRUCTIONS + seeded.
if [ -f "$PROTO" ]; then
  grep -qF "$JSONL" "$PROTO" \
    && pass "protocol documents the JSONL path ($JSONL)" \
    || fail "protocol must document the JSONL path ($JSONL)"
  if grep -E '"timestamp"' "$PROTO" | grep -q '"event_type"'; then
    pass "protocol shows a timestamp+event_type JSONL example"
  else
    fail "protocol JSONL example must carry both \"timestamp\" and \"event_type\" on one line"
  fi
  grep -qF "$EVT" "$PROTO" \
    && pass "protocol JSONL example carries event_type value \"$EVT\"" \
    || fail "protocol JSONL example missing event_type value \"$EVT\""
fi

if [ -f "$INSTR" ]; then
  if grep -qF "$JSONL" "$INSTR" && grep -qF "$EVT" "$INSTR"; then
    pass "INSTRUCTIONS.md documents the data contract for $JSONL (path + event_type \"$EVT\")"
  else
    fail "INSTRUCTIONS.md does not document the data contract for $JSONL (path + event_type \"$EVT\")"
  fi
else
  fail "INSTRUCTIONS.md not found"
fi

if [ -f "$INSTALLER" ]; then
  grep -qF "$JSONL" "$INSTALLER" \
    && pass "25-seed-round3-feature-files.sh seeds the JSONL sink ($JSONL)" \
    || fail "25-seed-round3-feature-files.sh does not seed $JSONL"
  grep -qF "ab-experiments" "$INSTALLER" \
    && pass "25-seed-round3-feature-files.sh seeds the ab-experiments/ scaffold (experiment + overlays)" \
    || fail "25-seed-round3-feature-files.sh must seed the ab-experiments/ scaffold (experiment + overlays)"
else
  fail "scripts/25-seed-round3-feature-files.sh not found"
fi

echo ""

# 5. PII guard — no JSONL example line in the protocol may carry a raw customer-value key.
if [ -f "$PROTO" ]; then
  if grep -E '"timestamp"' "$PROTO" \
       | grep '"event_type"' \
       | grep -Eq '"(value_written|value|field_value|raw_value|email|phone|address|name)"[[:space:]]*:'; then
    fail "protocol JSONL example leaks a raw customer-value key (value_written/value/field_value/raw_value/email/phone/address/name) — the contract is the experiment id + channel + arm label + opaque contact ref + outcome flags + counts only"
  else
    pass "protocol JSONL example is PII-free (no raw-value key — experiment id + channel + arm label + opaque contact ref + outcome flags + counts only)"
  fi
fi

# 6. Toggle documented DEFAULT FALSE.
if [ -f "$PROTO" ]; then
  if grep -q 'skill38.ab_testing.enabled\|ab_testing' "$PROTO" \
     && grep -qiE 'default \*\*false\*\*|default `?false`?|default FALSE|default false' "$PROTO"; then
    pass "toggle skill38.ab_testing.enabled is documented default FALSE (opt-in advanced feature)"
  else
    fail "toggle skill38.ab_testing.enabled must be documented default FALSE"
  fi
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — F16 A/B testing of reply variants is documented (protocol + AGENTS Step 1.87 + MEMORY Rule 29), the two variants per channel + the deterministic-by-contact (sticky) assignment + the at-draft-time placement + the three outcome metrics + the two-proportion z-test with a sane default N + the auto-promote-with-operator-notify flow + the ZHC-abtest-variant- tags + the operator-only guard are all present, the PII-free ab-test-events.jsonl contract is documented + seeded (with the ab-experiments/ scaffold), and the toggle defaults OFF."
  exit 0
else
  echo "RESULT: FAIL — an F16 A/B-testing invariant is missing (see above)."
  exit 1
fi
