#!/usr/bin/env bash
# qc-voice-phone.sh — machine-enforce the Voice / Phone Integration feature
# (F14, Round-2 backlog): the voice/phone protocol, the STT→brain→TTS pipeline over
# Twilio Voice + Media Streams, the inbound /hooks/voice-call-event SCAFFOLDING, the
# call-lifecycle state machine (greeting→listen→respond→handoff/booking), the
# < 800ms first-audio latency target + the degrade-to-text fallback, the setup
# wizard, the operator-only/never-customer-invoked OUTBOUND-dial guard, the
# ZHC-voice-* tags, the HONEST live-telephony gap, the PII-free F52 log, and the
# default-OFF toggle are all present and wired where they must be — so a regression
# that drops any load-bearing invariant fails the build.
#
# WHY: F14 lets the AI take and place real phone calls with the SAME brain it uses
# for text — the cost-savings pitch vs Convert-and-Flow's paid Voice AI add-on. But
# live telephony needs operator-provisioned Twilio/STT/TTS credentials + a
# media-stream bridge provisioned at setup; this gate proves the skill ships an
# HONEST scaffold + wizard (not a faked live call), keeps OUTBOUND dialing
# operator-gated, and logs PII-free (no phone numbers / transcripts).
#
# WHAT IT CHECKS (all from the repo alone — CI-safe, BASH-only so it respects the
# .py claude-/anthropic ban):
#   1. The protocol exists (voice-phone-protocol.md) and states its load-bearing
#      substance: the STT (Whisper-large-v3 via OpenRouter/Groq/Ollama) → brain →
#      TTS (ElevenLabs Flash 2.5 / OSS) pipeline; Twilio Voice + Media Streams; the
#      /hooks/voice-call-event hook scaffolding; the FOUR lifecycle states
#      (greeting/listen/respond/handoff + booking); the < 800ms first-audio target;
#      the degrade-to-text fallback; the setup wizard; the operator-only OUTBOUND
#      guard; the ZHC-voice-inbound / ZHC-voice-outbound tags; and the HONEST
#      live-telephony gap (NOT faked / provisioned at setup).
#   2. MEMORY Rule 30 is appended (06-append-memory-rules.sh).
#   3. The setup wizard exists (scripts/30-voice-phone-setup-wizard.sh).
#   4. The F52 log voice-call-events.jsonl: documented in the protocol with a
#      timestamp+event_type example carrying event_type "voice_call", documented in
#      INSTRUCTIONS.md, and SEEDED by 25-seed-round3-feature-files.sh.
#   5. PII guard: the protocol's JSONL example lines must NOT carry a raw
#      customer-value key (value/raw_value/email/phone/phone_number/transcript/
#      address/name) — the contract is opaque refs + provider names + counts only.
#   6. The toggle skill38.voice_phone.enabled is documented DEFAULT FALSE.
#
# Exit codes: 0 = clean; 1 = at least one F14 invariant violation.
#
# Usage:
#   bash scripts/qc-voice-phone.sh
#   bash scripts/qc-voice-phone.sh --skill-dir /path/to/38-conversational-ai-system

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

echo "=== qc-voice-phone: F14 voice/phone integration gate ==="
echo "skill_dir : $SKILL_DIR"
echo ""

PROTO="$SKILL_DIR/protocols/voice-phone-protocol.md"
MEM_SCRIPT="$SKILL_DIR/scripts/06-append-memory-rules.sh"
INSTR="$SKILL_DIR/INSTRUCTIONS.md"
INSTALLER="$SKILL_DIR/scripts/25-seed-round3-feature-files.sh"
WIZARD="$SKILL_DIR/scripts/30-voice-phone-setup-wizard.sh"
JSONL="voice-call-events.jsonl"
EVT="voice_call"

# 1. Protocol exists + load-bearing substance.
if [ -f "$PROTO" ]; then
  pass "protocols/voice-phone-protocol.md exists"

  # STT → brain → TTS pipeline with the named engines.
  if grep -qiE 'Whisper-large-v3|Whisper large v3' "$PROTO" \
     && grep -qiE 'OpenRouter' "$PROTO" && grep -qiE 'Groq' "$PROTO" && grep -qiE 'Ollama' "$PROTO" \
     && grep -qiE 'ElevenLabs|Flash 2\.5' "$PROTO" && grep -qiE 'OSS|open-source' "$PROTO"; then
    pass "protocol documents the STT→brain→TTS pipeline (Whisper-large-v3 via OpenRouter/Groq/Ollama; ElevenLabs Flash 2.5 / OSS TTS)"
  else
    fail "protocol must document the STT (Whisper-large-v3 via OpenRouter/Groq/Ollama) → brain → TTS (ElevenLabs Flash 2.5 / OSS) pipeline"
  fi

  # Twilio Voice + Media Streams (SIP/PSTN).
  if grep -qiE 'Twilio' "$PROTO" && grep -qiE 'Media Streams?' "$PROTO" && grep -qiE 'SIP|PSTN' "$PROTO"; then
    pass "protocol documents the telephony transport (Twilio Voice + Media Streams, SIP/PSTN)"
  else
    fail "protocol must document the telephony transport (Twilio Voice + Media Streams, SIP/PSTN)"
  fi

  # The inbound voice hook scaffolding.
  if grep -qF '/hooks/voice-call-event' "$PROTO"; then
    pass "protocol documents the inbound voice hook scaffolding (/hooks/voice-call-event)"
  else
    fail "protocol must document the inbound voice hook scaffolding (/hooks/voice-call-event)"
  fi

  # The call-lifecycle state machine — all four named states + booking.
  lm_missing=0
  grep -qi 'greeting' "$PROTO" || { fail "protocol must document the 'greeting' lifecycle state"; lm_missing=1; }
  grep -qi 'listen'   "$PROTO" || { fail "protocol must document the 'listen' lifecycle state";   lm_missing=1; }
  grep -qi 'respond'  "$PROTO" || { fail "protocol must document the 'respond' lifecycle state";  lm_missing=1; }
  grep -qi 'handoff'  "$PROTO" || { fail "protocol must document the 'handoff' lifecycle state";  lm_missing=1; }
  grep -qi 'booking'  "$PROTO" || { fail "protocol must document the 'booking' lifecycle state";  lm_missing=1; }
  [ "$lm_missing" -eq 0 ] && pass "protocol documents the call-lifecycle state machine (greeting → listen → respond → handoff / booking)"

  # < 800ms first-audio latency target.
  if grep -qiE '800 ?ms|< ?800|first_audio_latency_target_ms|first.audio' "$PROTO" \
     && grep -qiE 'latency' "$PROTO"; then
    pass "protocol documents the < 800ms first-audio latency target"
  else
    fail "protocol must document the < 800ms first-audio latency target"
  fi

  # Degrade-to-text fallback.
  if grep -qiE 'degrade|degraded' "$PROTO" \
     && grep -qiE 'fall ?back|fallback' "$PROTO" \
     && grep -qiE 'degrade_fallback_channel|sms|text channel' "$PROTO"; then
    pass "protocol documents the degrade-to-text fallback (call quality drops → SMS/text)"
  else
    fail "protocol must document the degrade-to-text fallback (call quality drops → SMS/text)"
  fi

  # Setup wizard referenced.
  if grep -qiE 'setup wizard|30-voice-phone-setup-wizard' "$PROTO"; then
    pass "protocol documents the setup wizard (captures Twilio creds/number + STT/TTS choice; provisions the bridge)"
  else
    fail "protocol must document the setup wizard"
  fi

  # operator-only / never-customer-invoked OUTBOUND-dial guard. Keyed on the
  # OUTBOUND-DIAL guard language specifically (NOT the generic PII disclaimer): the
  # operator-only statement PLUS the outbound-dial / call-placement-injection /
  # can-never-(cause|place)-an-outbound-call phrasing.
  if grep -qi 'operator-only\|operator only\|operator-gated' "$PROTO" \
     && grep -qiE 'outbound.?dial injection|call-placement instruction|can NEVER cause the agent to place an outbound call|never cause an outbound dial' "$PROTO"; then
    pass "protocol states OUTBOUND calls are operator-only / a customer can never cause an outbound dial"
  else
    fail "protocol must state OUTBOUND calls are operator-only / never customer-invoked (outbound-dial injection guard)"
  fi

  # ZHC-voice- tags (both inbound + outbound).
  if grep -qF 'ZHC-voice-inbound' "$PROTO" && grep -qF 'ZHC-voice-outbound' "$PROTO"; then
    pass "protocol uses the ZHC-voice-inbound / ZHC-voice-outbound tags for agent-created tags"
  else
    fail "protocol must use the ZHC-voice-inbound / ZHC-voice-outbound tags"
  fi

  # HONEST live-telephony gap (not faked / provisioned at setup).
  if grep -qiE 'NOT (faked|fake)|not faked|do not fake|provisioned at setup|honest gap|scaffold \+ wizard' "$PROTO" \
     && grep -qiE 'requires operator-provisioned|operator-provisioned.*credentials|media-stream bridge.*provisioned' "$PROTO"; then
    pass "protocol is HONEST about the live-telephony gap (requires operator-provisioned creds + the media-stream bridge provisioned at setup — NOT faked)"
  else
    fail "protocol must be HONEST about the live-telephony gap (operator-provisioned creds + bridge provisioned at setup; not a faked live call)"
  fi
else
  fail "protocols/voice-phone-protocol.md MISSING"
fi

echo ""

# 2. MEMORY Rule 30.
if [ -f "$MEM_SCRIPT" ] && grep -qE '^30\. *Voice' "$MEM_SCRIPT"; then
  pass "06-append-memory-rules.sh appends MEMORY Rule 30 (Voice/Phone Rule)"
else
  fail "06-append-memory-rules.sh is missing MEMORY Rule 30 (Voice/Phone Rule)"
fi

# 3. The setup wizard exists.
if [ -f "$WIZARD" ]; then
  pass "scripts/30-voice-phone-setup-wizard.sh exists (the operator setup wizard)"
else
  fail "scripts/30-voice-phone-setup-wizard.sh MISSING (the operator setup wizard)"
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
else
  fail "scripts/25-seed-round3-feature-files.sh not found"
fi

echo ""

# 5. PII guard — no JSONL example line in the protocol may carry a raw customer-value
#    key. The contract is opaque call/contact refs + provider names + counts only —
#    NEVER a phone number, caller name/address, or transcript body.
if [ -f "$PROTO" ]; then
  if grep -E '"timestamp"' "$PROTO" \
       | grep '"event_type"' \
       | grep -Eq '"(value|raw_value|field_value|email|phone|phone_number|caller_number|transcript|address|name|caller_name)"[[:space:]]*:'; then
    fail "protocol JSONL example leaks a raw customer-value key (value/raw_value/email/phone/phone_number/transcript/address/name) — the contract is opaque call/contact refs + provider names + counts only"
  else
    pass "protocol JSONL example is PII-free (no raw-value key — opaque refs + provider names + counts only, no phone number/transcript)"
  fi
fi

# 6. Toggle documented DEFAULT FALSE.
if [ -f "$PROTO" ]; then
  if grep -q 'skill38.voice_phone.enabled\|voice_phone' "$PROTO" \
     && grep -qiE 'default \*\*false\*\*|default `?false`?|default FALSE|default false' "$PROTO"; then
    pass "toggle skill38.voice_phone.enabled is documented default FALSE (opt-in advanced feature)"
  else
    fail "toggle skill38.voice_phone.enabled must be documented default FALSE"
  fi
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — F14 voice/phone integration is documented (protocol + MEMORY Rule 30 + setup wizard), the STT→brain→TTS pipeline over Twilio Media Streams + the /hooks/voice-call-event scaffolding + the greeting→listen→respond→handoff/booking state machine + the < 800ms first-audio target + the degrade-to-text fallback + the operator-only outbound-dial guard + the ZHC-voice-* tags + the HONEST live-telephony gap are all present, the PII-free voice-call-events.jsonl contract is documented + seeded, and the toggle defaults OFF."
  exit 0
else
  echo "RESULT: FAIL — an F14 voice/phone invariant is missing (see above)."
  exit 1
fi
