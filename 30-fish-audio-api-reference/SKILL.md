---
name: fish-audio-api-reference
description: Complete working knowledge of the Fish Audio API — text-to-speech generation, voice cloning, real-time streaming audio via WebSocket, and speech-to-text transcription. Installs a full API reference into master files indexed with Gemini Engine for at-query-time lookup.
---

# Fish Audio API Reference - Skill 31

> **TYP Required:** Read this entire SKILL.md before executing any install steps or making any Fish Audio API calls.

---

## What Is This Skill?

This skill gives your AI agent complete working knowledge of the Fish Audio API. It installs a full API reference document into your master files and indexes it with Gemini Engine so the agent can look up exact endpoints, parameters, and curl examples at query time - without guessing.

**What this enables:**
- Text-to-speech generation via API (podcasts, phone calls, voicemails, content)
- Voice cloning and model management
- Real-time streaming audio via WebSocket
- Speech-to-text transcription (ASR)

**This skill is standalone.** You do not need Skill 30 (Voice Call Plugin) to use it. However, if you have Skill 30 installed, this skill is required.

---

## TYP - Teach Yourself Protocol

**Before making ANY Fish Audio API call, the agent MUST:**

1. Read `references/fish-audio-api-reference.md` OR run a Gemini Engine search to find the specific section needed
2. Never guess at endpoints, parameters, or syntax
3. Always use exact parameter names and values from the reference doc

**Gemini Engine search pattern:**
```bash
python3 ~/.openclaw/scripts/gemini-search.py "fish audio tts endpoint parameters"
python3 ~/.openclaw/scripts/gemini-search.py "fish audio websocket streaming"
python3 ~/.openclaw/scripts/gemini-search.py "fish audio voice cloning"
```

**Direct reference path:**
```
~/Downloads/openclaw-master-files/service-integrations/fish-audio/fish-audio-api-reference.md
```

---

## Quick Reference Card

| Item | Value |
|------|-------|
| Base URL | `https://api.fish.audio` |
| TTS Endpoint | `POST /v1/tts` (same endpoint for paid and free tiers) |
| Auth Header | `Authorization: Bearer $FISH_AUDIO_API_KEY` |
| Model Header | `model: s2.1-pro` — a HEADER value, never a request-body field. Fish Audio's own free-tier examples confirm the same mechanic: `headers: { model: "s2.1-pro-free" }`. |
| Default Model (client/production) | `s2.1-pro` — PAID. ALWAYS the default for client-facing work. Never `s1`, the interim `s2-pro`, or the free `s2.1-pro-free` tier for client production. |
| Free Dev Model (operator-internal ONLY) | `s2.1-pro-free` — see "Model Selection: Paid vs Free" below before touching this. Never client production. |
| Voice ID | `$FISH_AUDIO_VOICE_ID` |

---

## Model Selection: Paid vs Free (Read Before Any TTS Call)

Fish Audio ships S2.1 Pro in two tiers on the same `POST /v1/tts` endpoint. Both tiers select the model the same way — via the HTTP `model` HEADER, never the JSON/msgpack request body. Confirmed by Fish Audio's own free-tier JS example: `headers: { model: "s2.1-pro-free" }` (source: https://fish.audio/blog/s2-1-pro-free-api/).

### `s2.1-pro` — PAID — the client/production default

This stays the default for ALL client-facing work, always. Rationale:
- SLA + latency guarantee — the tier Fish Audio contrasts against when it says the free tier has "no SLA" and "no latency guarantee"
- Commercial-safe for production / revenue-generating use
- Not subject to the free tier's "requests may be used to improve model quality" data-retention notice

### `s2.1-pro-free` — FREE — operator-internal dev/prototyping ONLY

**Do NOT use for client production, ever.** Straight from Fish Audio's own announcement (https://fish.audio/blog/s2-1-pro-free-api/) and docs (https://docs.fish.audio/features/text-to-speech):

- **No SLA / no uptime / no latency guarantee.** Fish Audio's own words: "No SLA: No uptime/TTFA guarantees; built for experimentation and prototyping" and "No latency guarantee: Best-effort, not contractual." Client-facing calls cannot run on a best-effort, non-contractual tier.
- **Data retention risk.** Free-tier requests "may be used to improve model quality" — a client-data / sovereignty risk we do not accept for client production content.
- **Commercial restriction.** Fish Audio: "Products generating more than $1M ARR should contact us before using S2.1 Pro Free." Client production is commercial use; we hold no such clearance from Fish Audio and are not seeking one.
- **Time-limited.** Free access was originally "available till July 24, 2026," then Fish Audio announced "extending the free window to cover all of July" — free access ends END OF JULY 2026, with advance notice promised before further changes. Anything built on this tier can break or reprice on short notice.

> ⚠️ **NEVER hardcode `s2.1-pro-free` anywhere as a durable default.** It is a time-boxed, no-SLA, no-retention-guarantee dev convenience that expires end of July 2026 and whose cost/availability can change without much warning. If you see it hardcoded as a default in client-facing code, flag it and fix it back to `s2.1-pro`.

### Capability refresh (S2.1 Pro, both tiers — July 2026 announcement)

- **83 languages** — one model, no per-language endpoint, no per-language pricing
- **~90ms TTFA** (time-to-first-audio) on the standard API; **~70ms TTFA** on a single request
- **61% win rate** vs the prior S2 Pro model in head-to-head listening evaluations
- **Voice cloning** via `reference_id` (a trained voice model) plus a reference audio sample
- Requests accept **both `application/msgpack` and `application/json`**
- `format` is selectable (e.g., `mp3`, `wav` — see the full parameter table in `references/fish-audio-api-reference.md`)

Sources: https://fish.audio/blog/s2-1-pro-free-api/ (S2.1 Pro Free announcement), https://docs.fish.audio/features/text-to-speech (model reference).

---

## BlackCEO Standard Settings

| Use Case | Model | Latency | Bitrate | Normalize | Format |
|----------|-------|---------|---------|-----------|--------|
| Phone calls | s2.1-pro | normal | 64 kbps | true | mp3 |
| Podcasts / content | s2.1-pro | normal | 192 kbps | true | mp3 |

- **Normal latency always** - best quality output
- **Balanced latency** (~300ms) only for real-time live AI calling
- Pricing: $15.00 per 1M UTF-8 bytes (~$0.40 per 30-minute podcast)

---

## Standard curl Template (Phone Calls)

```bash
curl -s -X POST "https://api.fish.audio/v1/tts" \
  -H "Authorization: Bearer $FISH_AUDIO_API_KEY" \
  -H "Content-Type: application/json" \
  -H "model: s2.1-pro" \
  -d "{
    \"text\": \"YOUR TEXT HERE\",
    \"reference_id\": \"$FISH_AUDIO_VOICE_ID\",
    \"format\": \"mp3\",
    \"mp3_bitrate\": 64,
    \"normalize\": true,
    \"latency\": \"normal\"
  }" \
  --output output.mp3
```

## Standard curl Template (Podcasts / Content)

```bash
curl -s -X POST "https://api.fish.audio/v1/tts" \
  -H "Authorization: Bearer $FISH_AUDIO_API_KEY" \
  -H "Content-Type: application/json" \
  -H "model: s2.1-pro" \
  -d "{
    \"text\": \"YOUR TEXT HERE\",
    \"reference_id\": \"$FISH_AUDIO_VOICE_ID\",
    \"format\": \"mp3\",
    \"mp3_bitrate\": 192,
    \"normalize\": true,
    \"latency\": \"normal\"
  }" \
  --output output.mp3
```

---

## Long-Form Content (Over 15,000 Characters)

The Fish Audio web platform has a 15,000 character limit. The API has no documented hard limit but for reliability, split long scripts into chunks of ~4,000 characters and stitch with FFmpeg:

```bash
# After generating chunk_1.mp3, chunk_2.mp3, chunk_3.mp3:
ffmpeg -i "concat:chunk_1.mp3|chunk_2.mp3|chunk_3.mp3" -acodec copy full_podcast.mp3
```

---

## Emotion Tags (S2.1 Pro Natural Language)

S2.1 Pro uses natural language in square brackets. Place before the sentence or phrase:

```
[excited] Big announcement today!
[calm and professional] Here is your briefing.
[whispering] Keep this between us.
[laughing slightly] That's actually funny.
```

Paralanguage effects (insert inline):
- `(breath)` - breathing sound
- `(break)` - short pause
- `(long-break)` - longer pause
- `(laugh)` - laughter
- `(sigh)` - sighing sound
- `um`, `uh` - natural filler words

---

## Pending Setup Behavior

If `FISH_AUDIO_API_KEY` or `FISH_AUDIO_VOICE_ID` are missing, the installer writes a pending entry to `~/.openclaw/skills/.pending-setup.md`.

**The agent should:**
1. Remind the client once per session if status is PENDING
2. When credentials are provided:
   - Add `FISH_AUDIO_API_KEY` to `~/.clawdbot/clawdbot.json` env vars
   - Add `FISH_AUDIO_VOICE_ID` to `~/.clawdbot/clawdbot.json` env vars
   - Add both to `~/clawd/secrets/.env`
   - Run `python3 ~/.openclaw/scripts/gemini-indexer.py` to re-index
   - Mark entry as Status: COMPLETE in `.pending-setup.md`

---

## Fish Audio Voice Behavior (S2 / S2.1 Pro)

> **TYP Deep Reference:** `fish-audio-voice-sop.md` is a large document. Do NOT load it into core files. Read it once using TYP, internalize the rules, then apply them when generating voice output.

When generating any Fish Audio S2 voice output (phone calls OR podcast/content), the agent must:

1. Read `fish-audio-voice-sop.md` using TYP before the first voice generation session
2. Apply the 12 Universal Operating Rules (spoken language, short chunks, pause system, tag system)
3. Use **Phone Call SOP (Part 3)** for live call interactions
4. Use **Podcast SOP (Part 4)** for content/podcast/audio generation at 192 kbps
5. Run the **8-step AI Decision Logic (Part 5)** before every voice response

**The core principle:** Do not speak like written text. Speak like a human being thinking out loud in real time.

---

## Files in This Skill

| File | Purpose |
|------|---------|
| `SKILL.md` | This file - TYP, quick reference, standard templates |
| `INSTALL.md` | Step-by-step installation checklist |
| `README.md` | One-page summary |
| `fish-audio-voice-sop.md` | **Deep reference** - Fish Audio S2 voice behavior SOP v3.0 (TYP required, do not load into core) |
| `references/fish-audio-api-reference.md` | Full API reference (all endpoints, parameters, examples) |
