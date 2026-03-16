# BlackCEO Voice Call Plugin - Skill 30

> **TYP Required:** Read this entire file before executing any install steps.

---

## What Is This Skill?

This skill installs and configures two things that work together to power AI phone calls and podcast-quality voice generation for BlackCEO and its clients:

1. **OpenClaw Voice Call Plugin** - Handles outbound and inbound AI phone calls using Telnyx as the phone provider
2. **Fish Audio TTS Integration** - Uses your cloned voice (or any Fish Audio voice) for all speech generation

Together they enable:
- AI-powered outbound phone calls that speak in your voice
- Inbound call handling with AI responses
- Multi-turn back-and-forth phone conversations
- Podcast/content audio generation at 192 kbps
- Phone call audio generation at 64 kbps

---

## Architecture Overview

```
Telnyx (phone network)
    ↕  call control webhooks
OpenClaw Voice Call Plugin (gateway)
    ↕  TTS requests
Fish Audio API (voice generation)
    ↕  audio stream
Telnyx (plays audio to caller)
```

---

## Prerequisites

You do NOT need these to install the plugin. The plugin installs without credentials. However, you need them to configure and activate calling. If you don't have them yet, the installer will flag setup as pending and your agent will remind you.

**To complete full activation, you need:**

1. **Telnyx account** with:
   - API key
   - A purchased phone number
   - Connection ID (from Mission Control Portal)
   - Public webhook key (from Mission Control Portal)
   - A publicly reachable URL for webhooks (VPS, ngrok, or Tailscale funnel)

2. **Fish Audio account** with:
   - API key
   - Voice model ID (your cloned voice)
   - Paid plan (free tier = 5 concurrent calls max)

3. **OpenClaw gateway** running and accessible

---

## Install

### Step 1 - Install the Voice Call Plugin

```bash
openclaw plugins install @openclaw/voice-call
```

### Step 2 - Restart the Gateway

```
/restart
```

Or via terminal:
```bash
openclaw gateway restart
```

### Step 3 - Configure the Plugin

Add the following to your `~/.openclaw/openclaw.json` under `plugins.entries`:

```json
"voice-call": {
  "enabled": true,
  "config": {
    "provider": "telnyx",
    "fromNumber": "+1YOURNUMBER",

    "telnyx": {
      "apiKey": "YOUR_TELNYX_API_KEY",
      "connectionId": "YOUR_CONNECTION_ID",
      "publicKey": "YOUR_TELNYX_PUBLIC_KEY"
    },

    "serve": {
      "port": 3334,
      "path": "/voice/webhook"
    },

    "publicUrl": "https://YOUR_PUBLIC_URL/voice/webhook",

    "outbound": {
      "defaultMode": "conversation"
    },

    "streaming": {
      "enabled": true,
      "streamPath": "/voice/stream",
      "preStartTimeoutMs": 5000,
      "maxPendingConnections": 32,
      "maxConnections": 128
    },

    "maxDurationSeconds": 300,
    "staleCallReaperSeconds": 360,

    "tts": {
      "provider": "fishaudio",
      "fishaudio": {
        "apiKey": "YOUR_FISH_AUDIO_API_KEY",
        "voiceId": "YOUR_FISH_AUDIO_VOICE_ID",
        "model": "s2-pro"
      }
    }
  }
}
```

### Step 4 - Restart Gateway Again

```
/restart
```

---

## Fish Audio Settings (BlackCEO Standard)

| Use Case | Model | Latency | Bitrate | Normalize |
|----------|-------|---------|---------|-----------|
| Phone calls | s2-pro | normal | 64 kbps | true |
| Podcasts / content | s2-pro | normal | 192 kbps | true |

- **Phone calls:** 64 kbps - sounds great, small file, fast
- **Podcasts:** 192 kbps - maximum quality for content
- **Normal latency always** - best quality output
- **Balanced latency** (~300ms) only for real-time live AI calls where speed is critical

---

## Making Calls

### Via CLI

```bash
# Make an outbound call
openclaw voicecall call --to "+15555550123" --message "Hello, this is an AI call from BlackCEO."

# Continue a call (send next message)
openclaw voicecall continue --call-id <id> --message "How can I help you today?"

# End a call
openclaw voicecall end --call-id <id>

# Check call status
openclaw voicecall status --call-id <id>

# Watch live call logs
openclaw voicecall tail
```

### Via Agent Tool

The agent has access to the `voice_call` tool with these actions:
- `initiate_call` - Start a new outbound call
- `continue_call` - Send next message in an active call
- `speak_to_user` - Inject speech mid-call
- `end_call` - Hang up
- `get_status` - Check call status

---

## Inbound Calls

To accept inbound calls, add to your config:

```json
"inboundPolicy": "allowlist",
"allowFrom": ["+1CALLERSNUMBER"],
"inboundGreeting": "Hello! You've reached BlackCEO. How can I help you?"
```

---

## Call Modes

| Mode | What It Does |
|------|-------------|
| `notify` | One-way outbound message, no response expected |
| `conversation` | Full back-and-forth multi-turn AI conversation |

---

## Concurrent Call Limits

| Fish Audio Tier | Concurrent Calls |
|-----------------|-----------------|
| Starter (under $100 spent) | 5 |
| Elevated (over $100 spent) | 15 |
| Enterprise (custom) | 50+ (request via support@fish.audio) |

**Note:** Telnyx also has its own concurrent call limits based on your plan. The lower of the two limits applies.

---

## Pricing Reference

| Service | Cost |
|---------|------|
| Telnyx outbound calls | $0.002/min |
| Telnyx inbound calls | $0.002/min |
| Fish Audio TTS | $15.00 per 1M UTF-8 bytes (~$0.40 per 30-min podcast) |
| Fish Audio ASR | $0.36/audio hour |

---

## Troubleshooting

**Call connects but no audio:**
- Check Fish Audio API key and voice ID
- Verify `s2-pro` model is specified
- Check gateway logs: `openclaw voicecall tail`

**Webhook not receiving calls:**
- Verify `publicUrl` is reachable from the internet
- Check Telnyx Mission Control Portal webhook configuration
- Ensure gateway is restarted after config changes

**Too many concurrent call errors:**
- You've hit Fish Audio's concurrent limit
- Build a queue on your side to manage call slots
- Contact support@fish.audio to request enterprise limits

---

## Pending Setup Reminder Behavior

If the client did not have their credentials at install time, a `voice-call-plugin` entry was written to `~/.openclaw/skills/.pending-setup.md` with Status: PENDING.

The agent should:
1. Check `.pending-setup.md` at session start
2. If `voice-call-plugin` is PENDING, remind the client once per session (not every message):
   - "Hey, you still need to set up your Telnyx and Fish Audio accounts to activate the voice call plugin. Do you want to do that now?"
3. When the client provides the credentials:
   - Add them to `~/.clawdbot/clawdbot.json` env vars
   - Add them to `~/clawd/secrets/.env`
   - Update `~/.openclaw/openclaw.json` with the full voice-call config
   - Mark the entry as Status: COMPLETE in `.pending-setup.md`
   - Restart the gateway

**Credentials to collect:**
| Credential | Env Var Name | Where to Find It |
|-----------|-------------|-----------------|
| Telnyx API key | `TELNYX_API_KEY` | portal.telnyx.com → Auth → API Keys |
| Telnyx phone number | `TELNYX_FROM_NUMBER` | portal.telnyx.com → Numbers |
| Telnyx Connection ID | `TELNYX_CONNECTION_ID` | portal.telnyx.com → Voice → Connections |
| Telnyx Public Key | `TELNYX_PUBLIC_KEY` | portal.telnyx.com → Auth → Public Keys |
| Fish Audio API key | `FISH_AUDIO_API_KEY` | fish.audio/app/api-keys |
| Fish Audio Voice ID | `FISH_AUDIO_VOICE_ID` | From voice model URL |
| Public webhook URL | `VOICE_WEBHOOK_URL` | Your VPS domain or ngrok URL |

---

## Fish Audio Voice Behavior (S2 / S2-Pro)

> **TYP Deep Reference:** `fish-audio-voice-sop.md` is a large document. Do NOT load it into core files or paste it into the system prompt. Instead, read it once using the Teach Yourself Protocol, internalize the tag system and behavior rules, then apply them contextually when generating voice output.

When generating any Fish Audio S2 voice output (phone calls or podcasts), the agent must:

1. Run: read `fish-audio-voice-sop.md` using TYP before the first voice generation session
2. Apply the 12 Universal Operating Rules (spoken language, short chunks, pause system, tag system)
3. Use Phone Call SOP (Part 3) for all `voice_call` tool interactions
4. Use Podcast SOP (Part 4) for content/audio generation at 192 kbps
5. Run the 8-step AI Decision Logic (Part 5) before every voice response

**The core principle:** Do not speak like written text. Speak like a human being thinking out loud in real time.

---

## Files in This Skill

| File | Purpose |
|------|---------|
| `SKILL.md` | This file - install guide and reference |
| `INSTALL.md` | Step-by-step installation checklist |
| `fish-audio-voice-sop.md` | **Deep reference** - Fish Audio S2 voice behavior SOP (TYP required, do not load into core) |
| `references/fish-audio-api.md` | Complete Fish Audio API reference |
| `references/telnyx-config.md` | Telnyx configuration reference |
