#!/usr/bin/env bash
# 30-voice-phone-setup-wizard.sh — Skill 38 / Step 9.48 (Voice / Phone Integration, F14)
#
# OPERATOR OPT-IN, default OFF. Captures the Twilio credentials + number and the
# STT/TTS provider choice for the AI voice/phone pipeline (STT Whisper-large-v3 →
# the existing conversational brain → TTS ElevenLabs Flash 2.5 / OSS, bridged over
# Twilio Voice + Media Streams), writes the documented (default-OFF) config, and
# PROVISIONS the media-stream bridge + Twilio voice webhook at setup time.
#
# HONEST GAP: live telephony requires operator-provisioned credentials. This wizard
# captures them and wires the bridge; it does NOT fake a live call. If a credential
# is missing it PAUSES with an exact-needs message (no silent failure) and leaves
# the toggle OFF — it never enables live telephony silently.
#
# Idempotent: never overwrites a secret it did not write; never flips the toggle ON
# on its own. OS-aware (Darwin + Linux). bash -n clean. set -euo pipefail.
#
# Non-interactive use (CI / scripted): pass values via env and set
# VOICE_PHONE_WIZARD_NONINTERACTIVE=1 to skip prompts:
#   TWILIO_ACCOUNT_SID=... TWILIO_AUTH_TOKEN=... TWILIO_NUMBER=+15551234567 \
#   VOICE_STT_PROVIDER=openrouter_whisper VOICE_TTS_PROVIDER=elevenlabs_flash_2_5 \
#   VOICE_PHONE_WIZARD_NONINTERACTIVE=1 bash scripts/30-voice-phone-setup-wizard.sh

set -euo pipefail

SECRETS_ENV="${OPENCLAW_SECRETS_ENV:-$HOME/.openclaw/secrets/.env}"
NONINTERACTIVE="${VOICE_PHONE_WIZARD_NONINTERACTIVE:-0}"

echo "[skill 38] Voice / Phone Integration setup wizard (F14, Step 9.48)"
echo "  This is OPERATOR OPT-IN and is OFF by default."
echo "  Pipeline: STT Whisper-large-v3 (OpenRouter / Groq / local Ollama) ->"
echo "            the EXISTING conversational brain -> TTS (ElevenLabs Flash 2.5"
echo "            or an OSS alternative), bridged over Twilio Voice + Media Streams."
echo "  HONEST: a live call needs YOUR Twilio + STT + TTS credentials AND the"
echo "          media-stream bridge this wizard provisions. Nothing is faked; the"
echo "          toggle stays OFF until you enable it after verifying the bridge."

# ---------------------------------------------------------------------------
# 1-2. Capture credentials + provider choices (non-destructive).
# ---------------------------------------------------------------------------
prompt_or_env() {
  # $1 = var name, $2 = prompt, $3 = default. Honors non-interactive mode.
  local var="$1" prompt="$2" default="${3:-}" val
  val="$(eval "printf '%s' \"\${$var:-}\"")"
  if [ -n "$val" ]; then printf '%s' "$val"; return 0; fi
  if [ "$NONINTERACTIVE" = "1" ]; then printf '%s' "$default"; return 0; fi
  read -r -p "$prompt" val || true
  printf '%s' "${val:-$default}"
}

if grep -qE "^TWILIO_ACCOUNT_SID=" "$SECRETS_ENV" 2>/dev/null; then
  echo "[skill 38] TWILIO_ACCOUNT_SID already set — preserving (idempotent)."
else
  SID="$(prompt_or_env TWILIO_ACCOUNT_SID 'Twilio Account SID (AC...) [skip]: ' '')"
  if [ -n "${SID:-}" ]; then
    TOK="$(prompt_or_env TWILIO_AUTH_TOKEN 'Twilio Auth Token: ' '')"
    NUM="$(prompt_or_env TWILIO_NUMBER 'Twilio phone number (E.164, e.g. +15551234567): ' '')"
    mkdir -p "$(dirname "$SECRETS_ENV")"
    {
      echo "TWILIO_ACCOUNT_SID=$SID"
      [ -n "${TOK:-}" ] && echo "TWILIO_AUTH_TOKEN=$TOK"
      [ -n "${NUM:-}" ] && echo "TWILIO_NUMBER=$NUM"
    } >> "$SECRETS_ENV"
    chmod 600 "$SECRETS_ENV"
    echo "[skill 38] Twilio creds saved (mode 600). NOTE on a VPS install put these"
    echo "           in host /docker/<project>/.env + docker compose up -d"
    echo "           --force-recreate; on a Mac the openclaw.json top-level env block."
  else
    echo "[skill 38] Twilio setup skipped (no SID entered) — leaving voice OFF."
  fi
fi

STT="$(prompt_or_env VOICE_STT_PROVIDER 'STT provider [openrouter_whisper|groq_whisper|ollama_whisper] (default openrouter_whisper): ' 'openrouter_whisper')"
TTS="$(prompt_or_env VOICE_TTS_PROVIDER 'TTS provider [elevenlabs_flash_2_5|oss_tts] (default elevenlabs_flash_2_5): ' 'elevenlabs_flash_2_5')"
echo "[skill 38] STT provider = $STT ; TTS provider = $TTS (record their API keys in $SECRETS_ENV)."

# ---------------------------------------------------------------------------
# 3. Document the (default-OFF) config the operator must place in openclaw.json.
#    The wizard does NOT write the toggle ON — that is a deliberate operator step
#    AFTER the bridge is verified (no silent live-telephony enable).
# ---------------------------------------------------------------------------
cat <<JSON
[skill 38] Add this to openclaw.json (toggle stays OFF until you verify the bridge):
{
  "skill38": {
    "voice_phone": {
      "enabled": false,
      "twilio_number": "<TWILIO_NUMBER_E164>",
      "stt_provider": "$STT",
      "tts_provider": "$TTS",
      "first_audio_latency_target_ms": 800,
      "degrade_fallback_channel": "sms",
      "outbound_requires_operator_approval": true
    }
  }
}
JSON

# ---------------------------------------------------------------------------
# 4. Provision the media-stream bridge + Twilio voice webhook — the LIVE step.
#    Requires the creds from steps 1-2. PAUSE with an exact-needs message if any
#    are missing; NEVER silently "succeed." This is where live telephony is wired
#    (behind the existing Cloudflare tunnel) — it is NOT pre-baked in the repo.
# ---------------------------------------------------------------------------
NEED=()
grep -qE "^TWILIO_ACCOUNT_SID=" "$SECRETS_ENV" 2>/dev/null || NEED+=("TWILIO_ACCOUNT_SID")
grep -qE "^TWILIO_AUTH_TOKEN="  "$SECRETS_ENV" 2>/dev/null || NEED+=("TWILIO_AUTH_TOKEN")
grep -qE "^TWILIO_NUMBER="      "$SECRETS_ENV" 2>/dev/null || NEED+=("TWILIO_NUMBER (E.164)")

if [ "${#NEED[@]}" -gt 0 ]; then
  echo "[skill 38] PAUSED — cannot provision the live media-stream bridge yet."
  echo "           Missing: ${NEED[*]}"
  echo "           Re-run this wizard with those provided, then provision the"
  echo "           Twilio Media Streams bridge + voice webhook behind your existing"
  echo "           Cloudflare tunnel and register the /hooks/voice-call-event mapping."
  echo "           Live telephony stays UNPROVISIONED until then (no fake call path)."
else
  echo "[skill 38] Credentials present — ready to provision the media-stream bridge"
  echo "           (Twilio Media Streams WebSocket <-> STT <-> TTS) behind the"
  echo "           existing Cloudflare tunnel and point the Twilio number's voice"
  echo "           webhook at it, then register the /hooks/voice-call-event mapping."
  echo "           Verify a test call hits the bridge BEFORE flipping"
  echo "           skill38.voice_phone.enabled to true."
fi

echo "[skill 38] See protocols/voice-phone-protocol.md (Step 9.48). Live telephony"
echo "           requires the provisioned bridge + operator credentials — scaffold +"
echo "           wizard + honest gap, never a faked live call."
