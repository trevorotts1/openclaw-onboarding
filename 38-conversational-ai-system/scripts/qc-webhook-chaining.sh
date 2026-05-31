#!/usr/bin/env bash
# qc-webhook-chaining.sh — machine-enforce the Webhook Chaining feature (F18,
# Round-2 backlog): the webhook-chaining protocol, the operator-defined chain
# registry (webhook-chains/), the four allow-listed trigger events, the https-only
# target + PII-free payload, the retry policy (exponential backoff + max attempts),
# the fire-after-a-completed-action AGENTS.md Step 2.9 wiring, the operator-only/
# never-customer-invoked outbound guard, the ZHC-webhook-chain-* tags, the PII-free
# F52 log, and the default-OFF toggle are all present and wired where they must be —
# so a regression that drops any load-bearing invariant fails the build.
#
# WHY: F18 makes the AI the FRONT DOOR of a downstream automated workflow — a
# completed action (booking / invoice / escalation / transcript export) fires an
# OUTBOUND webhook to an operator-defined system. An outbound POST reaches outside +
# may spend money downstream, so this gate proves the feature keeps it OPERATOR-ONLY
# (a customer can never name/add/trigger a target — SSRF/exfiltration guard), logs
# PII-free (opaque refs + target host + counts, never a full URL with a token or the
# payload), retries with bounded backoff, and defaults OFF.
#
# WHAT IT CHECKS (all from the repo alone — CI-safe, BASH-only so it respects the
# .py claude-/anthropic ban):
#   1. The protocol exists (webhook-chaining-protocol.md) and states its
#      load-bearing substance: the front-door/post-action framing; the operator-
#      defined registry webhook-chains/; the FOUR allow-listed trigger events
#      (booking_completed / invoice_sent / escalation_raised / transcript_exported);
#      the https-only target; the PII-free payload (opaque contact_ref, no
#      name/email/phone/address/transcript); the retry policy (exponential backoff +
#      max_attempts); the async/never-block-the-reply invariant; the operator-only/
#      never-customer-invoked OUTBOUND guard (SSRF/exfiltration); the
#      ZHC-webhook-chain-fired / ZHC-webhook-chain-failed tags.
#   2. AGENTS.md Step 2.9 block (STEP_2_9_WEBHOOK_CHAINING) is inserted
#      (05-update-agents-md.sh).
#   3. MEMORY Rule 31 is appended (06-append-memory-rules.sh).
#   4. The registry + example chain are seeded (25-seed-round3-feature-files.sh):
#      webhook-chains/ dir + booking-to-zapier.md.
#   5. The F52 log webhook-chain-events.jsonl: documented in the protocol with a
#      timestamp+event_type example carrying event_type "webhook_chain", documented
#      in INSTRUCTIONS.md, and SEEDED by 25-seed-round3-feature-files.sh.
#   6. PII guard: the protocol's JSONL example lines must NOT carry a raw
#      customer-value key (value/raw_value/email/phone/phone_number/address/name/
#      transcript/payload/url) — the contract is opaque refs + target HOST + counts.
#   7. The toggle skill38.webhook_chaining.enabled is documented DEFAULT FALSE.
#
# Exit codes: 0 = clean; 1 = at least one F18 invariant violation.
#
# Usage:
#   bash scripts/qc-webhook-chaining.sh
#   bash scripts/qc-webhook-chaining.sh --skill-dir /path/to/38-conversational-ai-system

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help)   sed -n '1,55p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

FAIL=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAIL=1; }

echo "=== qc-webhook-chaining: F18 webhook chaining gate ==="
echo "skill_dir : $SKILL_DIR"
echo ""

PROTO="$SKILL_DIR/protocols/webhook-chaining-protocol.md"
AG_SCRIPT="$SKILL_DIR/scripts/05-update-agents-md.sh"
MEM_SCRIPT="$SKILL_DIR/scripts/06-append-memory-rules.sh"
INSTR="$SKILL_DIR/INSTRUCTIONS.md"
INSTALLER="$SKILL_DIR/scripts/25-seed-round3-feature-files.sh"
JSONL="webhook-chain-events.jsonl"
EVT="webhook_chain"

# 1. Protocol exists + load-bearing substance.
if [ -f "$PROTO" ]; then
  pass "protocols/webhook-chaining-protocol.md exists"

  # Front-door / post-action framing.
  if grep -qiE 'front door|post-action|downstream' "$PROTO" \
     && grep -qiE 'outbound' "$PROTO"; then
    pass "protocol frames it as the OUTBOUND, post-action front-door of a downstream workflow"
  else
    fail "protocol must frame the feature as the OUTBOUND post-action front-door of a downstream workflow"
  fi

  # Operator-defined registry under webhook-chains/.
  if grep -qF 'webhook-chains/' "$PROTO"; then
    pass "protocol documents the operator-defined registry (webhook-chains/)"
  else
    fail "protocol must document the operator-defined registry dir (webhook-chains/)"
  fi

  # The FOUR allow-listed trigger events.
  te_missing=0
  grep -qF 'booking_completed'    "$PROTO" || { fail "protocol must document the 'booking_completed' trigger event";    te_missing=1; }
  grep -qF 'invoice_sent'         "$PROTO" || { fail "protocol must document the 'invoice_sent' trigger event";         te_missing=1; }
  grep -qF 'escalation_raised'    "$PROTO" || { fail "protocol must document the 'escalation_raised' trigger event";    te_missing=1; }
  grep -qF 'transcript_exported'  "$PROTO" || { fail "protocol must document the 'transcript_exported' trigger event";  te_missing=1; }
  [ "$te_missing" -eq 0 ] && pass "protocol documents all four allow-listed trigger events (booking_completed / invoice_sent / escalation_raised / transcript_exported)"

  # The allow-list framing itself (only these four, others ignored).
  if grep -qiE 'allow-list' "$PROTO" && grep -qiE 'ignored|IGNORED' "$PROTO"; then
    pass "protocol states the trigger events are an ALLOW-LIST (any other event is ignored)"
  else
    fail "protocol must state the trigger events are an allow-list (a non-allow-listed event is ignored)"
  fi

  # https-only target.
  if grep -qiE 'https://' "$PROTO" \
     && grep -qiE 'https only|https-only|http:// .*reject|http://.* is rejected|an `?http://`? target is rejected' "$PROTO"; then
    pass "protocol documents the https-only target URL (an http:// target is rejected)"
  else
    fail "protocol must document the https-only target URL (an http:// target is rejected)"
  fi

  # Retry policy — exponential backoff + max attempts.
  if grep -qiE 'backoff' "$PROTO" \
     && grep -qiE 'exponential' "$PROTO" \
     && grep -qiE 'max_attempts|max attempts' "$PROTO"; then
    pass "protocol documents the retry policy (exponential backoff + max_attempts)"
  else
    fail "protocol must document the retry policy (exponential backoff + max_attempts)"
  fi

  # PII-free payload (opaque contact_ref, no name/email/phone/address/transcript in the body).
  if grep -qiE 'PII-free|PII FREE|opaque' "$PROTO" \
     && grep -qF 'contact_ref' "$PROTO" \
     && grep -qiE 'never .*(name|email|phone|address)|NEVER .*(name|email|phone|address)' "$PROTO"; then
    pass "protocol documents the PII-free payload (opaque contact_ref + action ids; never a name/email/phone/address or transcript)"
  else
    fail "protocol must document the PII-free payload (opaque contact_ref; never a customer name/email/phone/address or the transcript body)"
  fi

  # Async / never-block-the-reply invariant.
  if grep -qiE 'async' "$PROTO" \
     && grep -qiE 'never block|NEVER block|not block.*reply|never blocking' "$PROTO"; then
    pass "protocol states the chain fires ASYNC and never blocks the customer-facing reply"
  else
    fail "protocol must state the chain fires async + never blocks the customer-facing reply (failure is an operator notification)"
  fi

  # operator-only / never-customer-invoked OUTBOUND guard (SSRF / exfiltration). Keyed on
  # the operator-only statement PLUS the customer-can-never-supply-a-target / SSRF /
  # exfiltration phrasing specifically (NOT the generic PII disclaimer).
  if grep -qiE 'operator-only|operator only|operator-defined' "$PROTO" \
     && grep -qiE 'SSRF|exfiltration|customer can never .*(name|add|trigger|supply)|never .*(POST|webhook) .*customer-supplied|never fires a POST to a URL a CUSTOMER supplied|never POSTs to a customer-supplied' "$PROTO"; then
    pass "protocol states firing is operator-only / a customer can never name, add, or trigger a target (SSRF/exfiltration guard)"
  else
    fail "protocol must state firing is operator-only / never customer-invoked (SSRF / outbound-exfiltration guard — a customer can never name/add/trigger a target URL)"
  fi

  # ZHC-webhook-chain- tags (both fired + failed).
  if grep -qF 'ZHC-webhook-chain-fired' "$PROTO" && grep -qF 'ZHC-webhook-chain-failed' "$PROTO"; then
    pass "protocol uses the ZHC-webhook-chain-fired / ZHC-webhook-chain-failed tags for agent-created tags"
  else
    fail "protocol must use the ZHC-webhook-chain-fired / ZHC-webhook-chain-failed tags"
  fi
else
  fail "protocols/webhook-chaining-protocol.md MISSING"
fi

echo ""

# 2. AGENTS.md Step 2.9 block.
if [ -f "$AG_SCRIPT" ] && grep -qF 'STEP_2_9_WEBHOOK_CHAINING' "$AG_SCRIPT"; then
  pass "05-update-agents-md.sh inserts the STEP_2_9_WEBHOOK_CHAINING post-action block"
else
  fail "05-update-agents-md.sh must insert the STEP_2_9_WEBHOOK_CHAINING post-action block"
fi

# 3. MEMORY Rule 31.
if [ -f "$MEM_SCRIPT" ] && grep -qE '^31\. *Webhook Chaining' "$MEM_SCRIPT"; then
  pass "06-append-memory-rules.sh appends MEMORY Rule 31 (Webhook Chaining Rule)"
else
  fail "06-append-memory-rules.sh is missing MEMORY Rule 31 (Webhook Chaining Rule)"
fi

# 4. Registry + example chain seeded.
if [ -f "$INSTALLER" ]; then
  if grep -qF 'webhook-chains' "$INSTALLER" && grep -qF 'booking-to-zapier' "$INSTALLER"; then
    pass "25-seed-round3-feature-files.sh seeds the webhook-chains/ registry + the booking-to-zapier example chain"
  else
    fail "25-seed-round3-feature-files.sh must seed the webhook-chains/ registry dir + the example chain (booking-to-zapier)"
  fi
else
  fail "scripts/25-seed-round3-feature-files.sh not found"
fi

echo ""

# 5. F52 log: protocol example + INSTRUCTIONS + seeded.
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
else
  fail "scripts/25-seed-round3-feature-files.sh not found"
fi

echo ""

# 6. PII guard — no JSONL example line in the protocol may carry a raw customer-value
#    key. The contract is opaque refs + target HOST + counts only — NEVER a name/email/
#    phone/address, the transcript body, the rendered payload, or a full URL with a token.
if [ -f "$PROTO" ]; then
  if grep -E '"timestamp"' "$PROTO" \
       | grep '"event_type"' \
       | grep -Eq '"(value|raw_value|field_value|email|phone|phone_number|address|name|customer_name|transcript|payload|url|target_url|full_url)"[[:space:]]*:'; then
    fail "protocol JSONL example leaks a raw customer-value/payload/url key — the contract is opaque refs + target HOST + counts only (never a name/email/phone/address, the payload, or the full URL with a token)"
  else
    pass "protocol JSONL example is PII-free (opaque refs + target host + counts only — no raw value, payload, or full URL)"
  fi
fi

# 7. Toggle documented DEFAULT FALSE.
if [ -f "$PROTO" ]; then
  if grep -q 'skill38.webhook_chaining.enabled\|webhook_chaining' "$PROTO" \
     && grep -qiE 'default \*\*false\*\*|default `?false`?|default FALSE|default false' "$PROTO"; then
    pass "toggle skill38.webhook_chaining.enabled is documented default FALSE (opt-in advanced feature)"
  else
    fail "toggle skill38.webhook_chaining.enabled must be documented default FALSE"
  fi
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — F18 webhook chaining is documented (protocol + AGENTS Step 2.9 + MEMORY Rule 31), the operator-defined webhook-chains/ registry + the four allow-listed trigger events + the https-only target + the PII-free payload + the exponential-backoff/max-attempts retry policy + the async/never-block-the-reply invariant + the operator-only/never-customer-invoked outbound (SSRF/exfiltration) guard + the ZHC-webhook-chain-* tags are all present, the PII-free webhook-chain-events.jsonl contract is documented + seeded with the registry + example chain, and the toggle defaults OFF."
  exit 0
else
  echo "RESULT: FAIL — an F18 webhook-chaining invariant is missing (see above)."
  exit 1
fi
