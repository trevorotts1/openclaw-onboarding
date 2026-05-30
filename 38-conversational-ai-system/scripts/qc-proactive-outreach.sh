#!/usr/bin/env bash
# qc-proactive-outreach.sh — machine-enforce the Proactive Outreach Campaigns feature
# (F15, Round-2 backlog): the outreach-engine protocol, the campaign-definition format
# (trigger cron|event / GHL-tag audience / message template via Communication Playbook /
# frequency cap / opt-out / ZHC-outreach- tag), the STRICT quiet-hours respect (Step 9.8),
# the reactive-vs-proactive separation (direction:proactive on every log line), the
# operator-only/never-customer-invoked SEND guard, the F29-migration relationship, the
# PII-free F52 log, and the default-OFF toggle are all present and wired where they must
# be — so a regression that drops any load-bearing invariant fails the build.
#
# WHY: this is the ONE part of the conversational system that reaches OUT to people who
# did not message first (and on paid channels, spends money). The whole point of F15 is
# that the agent can run scheduled/event-driven outbound campaigns — re-engagement,
# reminders, follow-ups, win-back, birthday touches — using the SAME brand voice
# (Communication Playbooks) and the SAME hard-gates (quiet hours, compliance, opt-out,
# frequency cap, operator-gated send) as a reactive reply, while keeping proactive and
# reactive events analyzable apart. This gate proves the skill's docs/wiring actually
# carry that guarantee.
#
# WHAT IT CHECKS (all from the repo alone — CI-safe, BASH-only so it respects the .py
# claude-/anthropic ban):
#   1. The protocol exists (proactive-outreach-protocol.md) and states its load-bearing
#      substance: the campaign-definitions dir, the trigger kinds (cron + event), the
#      GHL-tag audience filter, the message template rendered THROUGH the Communication
#      Playbook, the frequency cap, opt-out respect (ZHC-outreach-opted-out), the
#      ZHC-outreach-<campaign> tag, the STRICT quiet-hours respect (Step 9.8), the
#      reactive-vs-proactive-tracked-separately (direction:proactive) invariant, the
#      operator-only/never-customer-invoked SEND guard, the F29-migration relationship,
#      and the honest "NOT a new sending service / scheduler / CRM" scope.
#   2. AGENTS.md is INTENTIONALLY not given an inbound-reply step (cron/event-driven) — the
#      protocol must document the cron + event wiring instead, and there must be no
#      STEP_9_46 inbound marker.
#   3. MEMORY Rule 28 is appended (06-append-memory-rules.sh).
#   4. The F52 log outreach-events.jsonl: documented in the protocol with a
#      timestamp+event_type example carrying event_type "campaign_fired", documented in
#      INSTRUCTIONS.md, and SEEDED by 25-seed-round3-feature-files.sh. The seeder also
#      seeds the outreach-campaigns/ dir + the example campaign file.
#   5. PII guard: the protocol's JSONL example lines must NOT carry a raw customer-value
#      key (value/field_value/raw_value/message_body/email/phone/address/name) — the
#      contract is the campaign id + opaque contact_ref + counts + tag/playbook NAMES.
#   6. The toggle skill38.proactive_outreach.enabled is documented DEFAULT FALSE.
#
# Exit codes: 0 = clean; 1 = at least one F15 invariant violation.
#
# Usage:
#   bash scripts/qc-proactive-outreach.sh
#   bash scripts/qc-proactive-outreach.sh --skill-dir /path/to/38-conversational-ai-system

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help)   sed -n '1,50p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

FAIL=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAIL=1; }

echo "=== qc-proactive-outreach: F15 proactive outreach campaigns gate ==="
echo "skill_dir : $SKILL_DIR"
echo ""

PROTO="$SKILL_DIR/protocols/proactive-outreach-protocol.md"
AG_SCRIPT="$SKILL_DIR/scripts/05-update-agents-md.sh"
MEM_SCRIPT="$SKILL_DIR/scripts/06-append-memory-rules.sh"
INSTR="$SKILL_DIR/INSTRUCTIONS.md"
INSTALLER="$SKILL_DIR/scripts/25-seed-round3-feature-files.sh"
JSONL="outreach-events.jsonl"
EVT="campaign_fired"
EXAMPLE_CAMPAIGN="cold-lead-reengagement.md"

# 1. Protocol exists + load-bearing substance.
if [ -f "$PROTO" ]; then
  pass "protocols/proactive-outreach-protocol.md exists"

  # Campaign definitions dir.
  grep -q 'outreach-campaigns/' "$PROTO" \
    && pass "protocol defines the campaign-definitions dir (outreach-campaigns/)" \
    || fail "protocol must define the campaign-definitions dir (outreach-campaigns/)"

  # Both trigger kinds (cron AND event).
  if grep -qi 'time-based' "$PROTO" && grep -qi 'event-based' "$PROTO" \
     && grep -q 'trigger.type: cron' "$PROTO" && grep -q 'trigger.type: event' "$PROTO"; then
    pass "protocol defines BOTH trigger kinds (time-based cron + event-based)"
  else
    fail "protocol must define BOTH trigger kinds (time-based cron + event-based)"
  fi

  # GHL-tag audience filter.
  if grep -qi 'audience' "$PROTO" && grep -qi 'GHL tag query\|tag filter\|include_tags\|tag query' "$PROTO"; then
    pass "protocol defines the GHL-tag audience filter"
  else
    fail "protocol must define the GHL-tag audience filter (include_tags/exclude_tags)"
  fi

  # Message rendered THROUGH the Communication Playbook (reuses brand voice).
  if grep -qi 'Communication Playbook' "$PROTO" && grep -qi 'tone\|voice\|brand voice' "$PROTO"; then
    pass "protocol renders the message THROUGH the Communication Playbook (same brand voice as a reactive reply)"
  else
    fail "protocol must render the message through the existing Communication Playbooks (tone/voice)"
  fi

  # Frequency cap.
  grep -qi 'frequency cap\|frequency_cap' "$PROTO" \
    && pass "protocol defines the frequency cap (anti-fatigue)" \
    || fail "protocol must define the frequency cap"

  # Opt-out respect.
  if grep -qi 'opt-out\|opt_out\|opted out' "$PROTO" && grep -q 'ZHC-outreach-opted-out' "$PROTO"; then
    pass "protocol defines opt-out respect (ZHC-outreach-opted-out, global)"
  else
    fail "protocol must define opt-out respect (ZHC-outreach-opted-out)"
  fi

  # ZHC-outreach-<campaign> tag prefix.
  grep -q 'ZHC-outreach-' "$PROTO" \
    && pass "protocol uses the ZHC-outreach- prefix for agent-created campaign tags" \
    || fail "protocol must use the ZHC-outreach- prefix for agent-created campaign tags"

  # STRICT quiet-hours respect, referencing Step 9.8.
  if grep -qi 'quiet hours\|quiet-hours' "$PROTO" && grep -q 'Step 9.8' "$PROTO" \
     && grep -qi 'strictly\|STRICTLY\|queue\|defer' "$PROTO"; then
    pass "protocol STRICTLY respects quiet hours (Step 9.8 — a quiet-window touch queues/defers)"
  else
    fail "protocol must STRICTLY respect quiet hours (cross-reference Step 9.8; queue/defer in a quiet window)"
  fi

  # Reactive vs proactive tracked separately — direction:proactive.
  if grep -qi 'reactive' "$PROTO" && grep -qi 'proactive' "$PROTO" \
     && grep -qi 'separately\|tracked separately\|analyzed apart\|analyze apart' "$PROTO" \
     && grep -q 'direction' "$PROTO"; then
    pass "protocol tracks reactive vs proactive SEPARATELY (direction:proactive on every outreach line)"
  else
    fail "protocol must track reactive vs proactive separately (the direction:proactive marker)"
  fi

  # Operator-only / never-customer-invoked SEND guard.
  if grep -qi 'operator-only\|operator only\|allow-list' "$PROTO" \
     && grep -qi 'never.*customer\|customer.*never\|never-customer\|customer can never\|outbound-injection\|injection vector' "$PROTO"; then
    pass "protocol states the SEND is operator-only / a customer can never drive a campaign (outbound-injection guard)"
  else
    fail "protocol must state the SEND is operator-only / never customer-invoked (outbound-injection guard)"
  fi

  # F29 migration relationship.
  if grep -qi 'F29\|intelligent-followup\|intelligent follow-up\|follow-up' "$PROTO" \
     && grep -qi 'migrat' "$PROTO"; then
    pass "protocol references the F29 Intelligent Follow-up migration relationship (F29 migrates onto this infrastructure)"
  else
    fail "protocol must reference that F29 Intelligent Follow-up MIGRATES onto this infrastructure"
  fi

  # Honest scope: NOT a new sending service / scheduler / CRM.
  if grep -qiE 'does NOT build a new|NOT (build|a new).*(sending|service|scheduler|CRM)' "$PROTO"; then
    pass "protocol is honest about scope (reuses GHL send + openclaw cron + Communication Playbooks; NOT a new sending service/scheduler/CRM)"
  else
    fail "protocol must be honest about scope (NOT a new sending service / scheduler / CRM)"
  fi
else
  fail "protocols/proactive-outreach-protocol.md MISSING"
fi

echo ""

# 2. AGENTS.md is INTENTIONALLY not given an inbound-reply step; the protocol must
#    document the cron + event wiring instead, and there must be NO STEP_9_46 inbound marker.
if [ -f "$PROTO" ] && grep -qi 'cron + event wiring\|cron/event-driven\|cron-driven\|event-driven' "$PROTO" \
   && grep -qi 'openclaw cron' "$PROTO"; then
  pass "protocol documents the cron + event wiring (this engine is cron/event-driven, not an inbound-reply step)"
else
  fail "protocol must document the cron + event wiring (no AGENTS.md inbound-reply step — cron/event-driven)"
fi
if [ -f "$AG_SCRIPT" ]; then
  if grep -q 'STEP_9_46\|PROACTIVE_OUTREACH' "$AG_SCRIPT"; then
    fail "05-update-agents-md.sh must NOT add an inbound-reply step for F15 (the engine is cron/event-driven) — found a STEP_9_46/PROACTIVE_OUTREACH marker"
  else
    pass "05-update-agents-md.sh correctly adds NO inbound-reply step for F15 (cron/event-driven, documented in the protocol)"
  fi
fi

# 3. MEMORY Rule 28.
if [ -f "$MEM_SCRIPT" ] && grep -qE '^28\. *Proactive Outreach' "$MEM_SCRIPT"; then
  pass "06-append-memory-rules.sh appends MEMORY Rule 28 (Proactive Outreach Rule)"
else
  fail "06-append-memory-rules.sh is missing MEMORY Rule 28 (Proactive Outreach Rule)"
fi

echo ""

# 4. F52 log: protocol example + INSTRUCTIONS + seeded; campaign dir + example seeded.
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
  # Every JSONL example line carries direction:proactive (the separation marker).
  if grep -E '"timestamp"' "$PROTO" | grep '"event_type"' | grep -vq '"direction"[[:space:]]*:[[:space:]]*"proactive"'; then
    fail "every outreach JSONL example line must carry \"direction\":\"proactive\" (the reactive-vs-proactive separation marker)"
  else
    pass "every outreach JSONL example line carries \"direction\":\"proactive\""
  fi
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
  grep -qF "outreach-campaigns" "$INSTALLER" \
    && pass "25-seed-round3-feature-files.sh seeds the outreach-campaigns/ dir" \
    || fail "25-seed-round3-feature-files.sh must seed the outreach-campaigns/ dir"
  grep -qF "$EXAMPLE_CAMPAIGN" "$INSTALLER" \
    && pass "25-seed-round3-feature-files.sh seeds the example campaign ($EXAMPLE_CAMPAIGN)" \
    || fail "25-seed-round3-feature-files.sh must seed the example campaign ($EXAMPLE_CAMPAIGN)"
else
  fail "scripts/25-seed-round3-feature-files.sh not found"
fi

echo ""

# 5. PII guard — the JSONL example lines must not carry a raw customer-value key.
if [ -f "$PROTO" ]; then
  if grep -E '"timestamp"' "$PROTO" \
       | grep '"event_type"' \
       | grep -Eq '"(value|field_value|raw_value|message_body|message_text|email|phone|address|name|first_name)"[[:space:]]*:'; then
    fail "protocol JSONL example leaks a raw customer-value key (value/field_value/raw_value/message_body/email/phone/address/name) — the contract is campaign id + opaque contact_ref + counts + tag/playbook NAMES only"
  else
    pass "protocol JSONL example is PII-free (no raw-value key — campaign id + opaque contact_ref + counts + NAMES only)"
  fi
fi

# 6. Toggle documented DEFAULT FALSE.
if [ -f "$PROTO" ]; then
  if grep -q 'skill38.proactive_outreach.enabled\|proactive_outreach' "$PROTO" \
     && grep -qiE 'default \*\*false\*\*|default `?false`?|default FALSE|default false' "$PROTO"; then
    pass "toggle skill38.proactive_outreach.enabled is documented default FALSE (opt-in advanced feature)"
  else
    fail "toggle skill38.proactive_outreach.enabled must be documented default FALSE"
  fi
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — F15 proactive outreach campaigns is documented (protocol + MEMORY Rule 28, NO inbound AGENTS step — cron/event-driven), the campaign-definition format (cron|event trigger + GHL-tag audience + Communication-Playbook-rendered message + frequency cap + opt-out + ZHC-outreach- tag) is present, quiet hours are STRICTLY respected (Step 9.8), reactive vs proactive are tracked separately (direction:proactive), the SEND is operator-only/never-customer-invoked, F29 migrates onto this infrastructure, the PII-free outreach-events.jsonl contract is documented + seeded (with the outreach-campaigns/ dir + example campaign), and the toggle defaults OFF."
  exit 0
else
  echo "RESULT: FAIL — an F15 proactive-outreach invariant is missing (see above)."
  exit 1
fi
