# Fish Audio API Reference - Skill 31

> **TYP Required:** Read this entire SKILL.md before executing any install steps or making any Fish Audio API calls.

---

## What Is This Skill?

This skill gives your AI agent complete working knowledge of the Fish Audio API. It installs a full API reference document into your master files and indexes it with QMD so the agent can look up exact endpoints, parameters, and curl examples at query time - without guessing.

**What this enables:**
- Text-to-speech generation via API (podcasts, phone calls, voicemails, content)
- Voice cloning and model management
- Real-time streaming audio via WebSocket
- Speech-to-text transcription (ASR)

**This skill is standalone.** You do not need Skill 30 (Voice Call Plugin) to use it. However, if you have Skill 30 installed, this skill is required.

---

## TYP - Teach Yourself Protocol

**Before making ANY Fish Audio API call, the agent MUST:**

1. Read `references/fish-audio-api-reference.md` OR run a QMD search to find the specific section needed
2. Never guess at endpoints, parameters, or syntax
3. Always use exact parameter names and values from the reference doc

**QMD search pattern:**
```bash
qmd search master-files "fish audio tts endpoint parameters"
qmd search master-files "fish audio websocket streaming"
qmd search master-files "fish audio voice cloning"
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
| TTS Endpoint | `POST /v1/tts` |
| Auth Header | `Authorization: Bearer $FISH_AUDIO_API_KEY` |
| Model Header | `model: s2-pro` |
| Default Model | `s2-pro` (ALWAYS - never use s1 unless explicitly told) |
| Voice ID | `$FISH_AUDIO_VOICE_ID` |

---

## BlackCEO Standard Settings

| Use Case | Model | Latency | Bitrate | Normalize | Format |
|----------|-------|---------|---------|-----------|--------|
| Phone calls | s2-pro | normal | 64 kbps | true | mp3 |
| Podcasts / content | s2-pro | normal | 192 kbps | true | mp3 |

- **Normal latency always** - best quality output
- **Balanced latency** (~300ms) only for real-time live AI calling
- Pricing: $15.00 per 1M UTF-8 bytes (~$0.40 per 30-minute podcast)

---

## Standard curl Template (Phone Calls)

```bash
curl -s -X POST "https://api.fish.audio/v1/tts" \
  -H "Authorization: Bearer $FISH_AUDIO_API_KEY" \
  -H "Content-Type: application/json" \
  -H "model: s2-pro" \
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
  -H "model: s2-pro" \
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

## Emotion Tags (S2-Pro Natural Language)

S2-Pro uses natural language in square brackets. Place before the sentence or phrase:

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
   - Run `python3 ~/clawd/scripts/gemini-indexer.py` to re-index
   - Mark entry as Status: COMPLETE in `.pending-setup.md`

---

## Fish Audio Voice Behavior (S2 / S2-Pro)

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
| `references/fish-audio-api-reference.md` | Full 841-line API reference (all endpoints, parameters, examples) |
