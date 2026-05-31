#!/usr/bin/env bash
# qc-segmentation.sh — machine-enforce the Customer Segmentation Awareness feature
# (F17, Round-2 backlog): the segmentation protocol, the five canonical segments, the
# per-client GHL-tag → segment mapping, the multi-tag precedence, the FOUR behavior
# overrides (response priority, F4/Step 9.6 sentiment-escalation threshold,
# Communication Playbook tier, Step 9.11 confidence threshold), the BEFORE-reply-draft
# placement (AGENTS Step 1.85), the ZHC- segment-tag prefix, the operator-only/never-
# customer-invoked guard, the PII-free F52 log, and the default-OFF toggle are all
# present and wired where they must be — so a regression that drops any load-bearing
# invariant fails the build.
#
# WHY: a 5-year VIP must NOT be treated like a cold Google-ad stranger. The whole point
# of F17 is that the agent recognizes WHO it is talking to (the segment, read from the
# operator's GHL tags) and tunes four behavior knobs accordingly — BEFORE it drafts the
# reply — without ever letting a customer self-promote into a segment or disabling a
# hard-gate. This gate proves the skill's docs/wiring actually carry that guarantee.
#
# WHAT IT CHECKS (all from the repo alone — CI-safe, BASH-only so it respects the .py
# claude-/anthropic ban):
#   1. The protocol exists (customer-segmentation-protocol.md) and states its load-
#      bearing substance: the five canonical segments (vip/prospect/returning/at-risk/
#      churned), the per-client tag_map / segment-map.md mapping, the multi-tag
#      precedence (at-risk > vip > churned > returning > prospect), ALL FOUR override
#      knobs, the BEFORE-reply-draft Step 1.85 placement, the ZHC-segment- tag prefix,
#      the operator-only/never-customer-invoked guard, and the honest "READS membership
#      / NOT a new CRM or scoring engine" scope.
#   2. AGENTS.md gets the STEP_1_85_SEGMENTATION_AWARENESS marker block
#      (05-update-agents-md.sh).
#   3. MEMORY Rule 27 is appended (06-append-memory-rules.sh).
#   4. The F52 log segmentation-events.jsonl: documented in the protocol with a
#      timestamp+event_type example carrying event_type "segment_detected", documented
#      in INSTRUCTIONS.md, and SEEDED by 25-seed-round3-feature-files.sh. The seeder
#      also seeds the segment-map.md companion.
#   5. PII guard: the protocol's JSONL example line must NOT carry a raw customer-value
#      key (value_written/"value"/field_value/raw_value/email/phone/address) — the
#      contract is the opaque segment label + matched tag NAMES + the override knobs.
#   6. The toggle skill38.segmentation.enabled is documented DEFAULT FALSE.
#
# Exit codes: 0 = clean; 1 = at least one F17 invariant violation.
#
# Usage:
#   bash scripts/qc-segmentation.sh
#   bash scripts/qc-segmentation.sh --skill-dir /path/to/38-conversational-ai-system

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help)   sed -n '1,45p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

FAIL=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAIL=1; }

echo "=== qc-segmentation: F17 customer segmentation awareness gate ==="
echo "skill_dir : $SKILL_DIR"
echo ""

PROTO="$SKILL_DIR/protocols/customer-segmentation-protocol.md"
AG_SCRIPT="$SKILL_DIR/scripts/05-update-agents-md.sh"
MEM_SCRIPT="$SKILL_DIR/scripts/06-append-memory-rules.sh"
INSTR="$SKILL_DIR/INSTRUCTIONS.md"
INSTALLER="$SKILL_DIR/scripts/25-seed-round3-feature-files.sh"
JSONL="segmentation-events.jsonl"
EVT="segment_detected"

# 1. Protocol exists + load-bearing substance.
if [ -f "$PROTO" ]; then
  pass "protocols/customer-segmentation-protocol.md exists"

  # The five canonical segments — every one must be named.
  seg_missing=0
  for seg in 'vip' 'prospect' 'returning' 'at-risk' 'churned'; do
    grep -q "$seg" "$PROTO" || { fail "protocol must define the segment: $seg"; seg_missing=1; }
  done
  [ "$seg_missing" -eq 0 ] && pass "protocol defines ALL FIVE canonical segments (vip / prospect / returning / at-risk / churned)"

  # Per-client GHL-tag → segment mapping.
  if grep -q 'tag_map' "$PROTO" && grep -q 'segment-map.md' "$PROTO"; then
    pass "protocol defines the per-client GHL-tag → segment mapping (tag_map + segment-map.md)"
  else
    fail "protocol must define the per-client GHL-tag → segment mapping (tag_map + segment-map.md)"
  fi

  # Multi-tag precedence.
  if grep -q 'at-risk  >  vip  >  churned  >  returning  >  prospect' "$PROTO" \
     || grep -q 'at-risk > vip > churned > returning > prospect' "$PROTO"; then
    pass "protocol states the multi-tag precedence (at-risk > vip > churned > returning > prospect)"
  else
    fail "protocol must state the multi-tag precedence (at-risk > vip > churned > returning > prospect)"
  fi

  # ALL FOUR override knobs.
  ov_missing=0
  grep -qi 'response priority'              "$PROTO" || { fail "protocol must override response priority";              ov_missing=1; }
  grep -qi 'sentiment-escalation threshold' "$PROTO" || { fail "protocol must override the sentiment-escalation threshold (F4/Step 9.6)"; ov_missing=1; }
  grep -qi 'Communication Playbook tier'    "$PROTO" || { fail "protocol must override the Communication Playbook tier"; ov_missing=1; }
  grep -qi 'confidence threshold'           "$PROTO" || { fail "protocol must override the confidence threshold (Step 9.11)"; ov_missing=1; }
  [ "$ov_missing" -eq 0 ] && pass "protocol overrides ALL FOUR knobs (response priority / sentiment-escalation threshold / Communication Playbook tier / confidence threshold)"

  # The two overridden protocols are named (F4/Step 9.6 + Step 9.11).
  if grep -q 'Step 9.6' "$PROTO" && grep -q 'Step 9.11' "$PROTO"; then
    pass "protocol cross-references the overridden knobs (Step 9.6 sentiment + Step 9.11 confidence)"
  else
    fail "protocol must cross-reference the overridden knobs (Step 9.6 + Step 9.11)"
  fi

  # BEFORE-reply-draft Step 1.85 placement.
  if grep -q 'Step 1.85' "$PROTO" && grep -qi 'before.*reply\|reply.*draft' "$PROTO"; then
    pass "protocol places the segment lookup BEFORE the reply draft (AGENTS Step 1.85)"
  else
    fail "protocol must place the segment lookup BEFORE the reply draft (AGENTS Step 1.85)"
  fi

  # ZHC-segment- tag prefix.
  grep -q 'ZHC-segment-' "$PROTO" \
    && pass "protocol uses the ZHC-segment- prefix for agent-created segment tags" \
    || fail "protocol must use the ZHC-segment- prefix for agent-created segment tags"

  # operator-only / never-customer-invoked guard.
  if grep -qi 'operator-only\|operator-owned' "$PROTO" && grep -qi 'never.*customer\|customer.*never\|never-customer\|customer can never\|self-promotion' "$PROTO"; then
    pass "protocol states segment assignment is operator-only / a customer can never claim a segment"
  else
    fail "protocol must state segment assignment is operator-only / never customer-invoked (self-promotion injection guard)"
  fi

  # honest scope: READS membership, not a new CRM/scoring engine.
  if grep -qiE 'NOT (build|create).*(CRM|scoring)|does NOT build a new CRM|READS that membership' "$PROTO"; then
    pass "protocol is honest about scope (READS segment membership from GHL tags; NOT a new CRM/scoring engine)"
  else
    fail "protocol must be honest about scope (READS membership; NOT a new CRM/scoring engine)"
  fi
else
  fail "protocols/customer-segmentation-protocol.md MISSING"
fi

echo ""

# 2. AGENTS.md marker block.
if [ -f "$AG_SCRIPT" ] && grep -q 'STEP_1_85_SEGMENTATION_AWARENESS' "$AG_SCRIPT"; then
  pass "05-update-agents-md.sh inserts the STEP_1_85_SEGMENTATION_AWARENESS block"
else
  fail "05-update-agents-md.sh is missing the STEP_1_85_SEGMENTATION_AWARENESS block"
fi

# 3. MEMORY Rule 27.
if [ -f "$MEM_SCRIPT" ] && grep -qE '^27\. *Customer Segmentation Rule' "$MEM_SCRIPT"; then
  pass "06-append-memory-rules.sh appends MEMORY Rule 27 (Customer Segmentation Rule)"
else
  fail "06-append-memory-rules.sh is missing MEMORY Rule 27 (Customer Segmentation Rule)"
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
  grep -qF "segment-map.md" "$INSTALLER" \
    && pass "25-seed-round3-feature-files.sh seeds the segment-map.md companion" \
    || fail "25-seed-round3-feature-files.sh must seed the segment-map.md companion"
else
  fail "scripts/25-seed-round3-feature-files.sh not found"
fi

echo ""

# 5. PII guard — the JSONL example line must not carry a raw customer-value key.
if [ -f "$PROTO" ]; then
  if grep -E '"timestamp"' "$PROTO" \
       | grep '"event_type"' \
       | grep -Eq '"(value_written|value|field_value|raw_value|email|phone|address|name)"[[:space:]]*:'; then
    fail "protocol JSONL example leaks a raw customer-value key (value_written/value/field_value/raw_value/email/phone/address/name) — the contract is the opaque segment label + matched tag NAMES + override knobs only"
  else
    pass "protocol JSONL example is PII-free (no raw-value key — opaque segment + tag NAMES + override knobs only)"
  fi
fi

# 6. Toggle documented DEFAULT FALSE.
if [ -f "$PROTO" ]; then
  if grep -q 'skill38.segmentation.enabled\|segmentation' "$PROTO" \
     && grep -qiE 'default \*\*false\*\*|default `?false`?|default FALSE|default false' "$PROTO"; then
    pass "toggle skill38.segmentation.enabled is documented default FALSE (opt-in advanced feature)"
  else
    fail "toggle skill38.segmentation.enabled must be documented default FALSE"
  fi
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — F17 customer segmentation awareness is documented (protocol + AGENTS Step 1.85 + MEMORY Rule 27), the five segments + per-client tag_map/segment-map.md mapping + multi-tag precedence + the FOUR behavior overrides + the before-reply-draft placement + the ZHC-segment- tag prefix + the operator-only guard are all present, the PII-free segmentation-events.jsonl contract is documented + seeded (with the segment-map.md companion), and the toggle defaults OFF."
  exit 0
else
  echo "RESULT: FAIL — an F17 customer-segmentation invariant is missing (see above)."
  exit 1
fi
