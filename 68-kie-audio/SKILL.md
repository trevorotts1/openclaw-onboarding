---
name: kie-audio
description: >
  KIE.ai audio skill: TTS (Gemini 3.1 Flash / 2.5 Pro + ElevenLabs dialogue-v3 /
  multilingual-v2 / turbo-2-5 via generic Market createTask), Suno music/sound
  generation (DEDICATED /api/v1/generate family — never createTask), supported
  audio processing operations, and speech-to-text CAPABILITY DETECTION
  (ADVERTISED_NOT_YET_VERIFIED — no endpoint, dispatch_enabled false).
metadata:

  version: "1.0.0"
  priority: HIGH
---

# KIE Audio — TTS, Music/Suno, STT status

KIE Audio owns model selection, payload validation, prompt sizing, async
completion, and audio QC for three sub-domains with DISTINCT API families:

1. **TTS** — generic Market `POST /api/v1/jobs/createTask` (Gemini + ElevenLabs
   engines; see `references/tts.md`).
2. **MUSIC** — Suno DEDICATED family `POST /api/v1/generate` (+ `/extend`,
   `/sounds`, and 14 documented operations; see `references/music.md`). NEVER
   routed through createTask.
3. **STT** — `ADVERTISED_NOT_YET_VERIFIED`, `dispatch_enabled: false`. KIE's
   market page advertises ElevenLabs speech-to-text, but no first-party callable
   endpoint was located on 2026-08-26. This skill refuses to invent one
   (`references/stt.md`).

Server: `https://api.kie.ai`. Auth: `Authorization: Bearer $KIE_API_KEY`.

## When to Use This Skill

- The user (or an upstream skill) asks for TTS — text-to-speech, voiceover,
  narration, multi-speaker dialogue.
- The user asks for music or sound generation (Suno): a song, instrumental,
  extension, mashup, cover, sound effect, persona, lyrics, WAV/MIDI conversion,
  vocal separation, or music video.
- The user asks whether KIE can do speech-to-text: answer from the registry —
  NOT YET VERIFIED, currently not dispatchable. Do NOT route transcription here.

This skill is for KIE AUDIO specifically. It is NOT the general TTS default:
department pipelines and other skills pin their own audio model. When the
request reaches the generic media router with KIE selected and the ask is
audio/music/TTS, route here (AGENTS.md routing block).

## Supported models

### TTS (Market createTask)

| Model id | Use |
|---|---|
| `google/gemini-3-1-flash-tts` | multi-speaker dialogue; `speakers[]` + `dialogue_turns[]`; 30-voice enum; per-turn text max 10000 |
| `google/gemini-2-5-pro-tts` | same schema; live body shape verified 2026-08-26 |
| `elevenlabs/text-to-dialogue-v3` | `dialogue[]` text+voice; combined text max 5000 (verbatim); stability 0/0.5/1 |
| `elevenlabs/text-to-speech-multilingual-v2` | single `text` max 5000; voice ~70 enum; speed 0.7-1.2 |
| `elevenlabs/text-to-speech-turbo-2-5` | same; language enforcement note (Turbo v2.5/Flash v2.5 only) |

Full schema in `references/tts.md` (every field, enums, output shape, callback).

### Music (Suno DEDICATED family — never createTask)

| Route | Purpose |
|---|---|
| `POST /api/v1/generate` | songs; models V4/V4_5/V4_5PLUS/V4_5ALL/V5/V5_5 |
| `POST /api/v1/generate/extend` | extend a track from `continueAt` |
| `POST /api/v1/generate/sounds` | sound effects; V5/V5_5; prompt 500 |
| + 14 operations | upload-cover, upload-extend, add-instrumental, add-vocals, cover, replace-section, generate-persona, mashup (exactly 2 URLs), lyrics, get-timestamped-lyrics, wav, vocal-removal, midi, mp4 |

Full table + limits in `references/music.md`.

### STT

No route. `dispatch_enabled: false`, `status: ADVERTISED_NOT_YET_VERIFIED`.
See `references/stt.md` for the negative-result trail and re-proof procedure.

## Prompt sizing (SPEC section 5)

House band 5,000 / ~9,000 / 19,000 chars is HOUSE POLICY; the model hard cap
always wins (rule A/B/C).

- Gemini TTS: per-turn 10,000 cap → target ≤ ~9,500 per turn (rule B);
  the combined production script band applies per turn.
- dialogue-v3: combined 5,000 (verbatim "total character count of all text
  fields combined must not exceed 5000 characters") → safe ceiling 4,900
  (rule B); house floor 5,000 is impossible.
- multilingual-v2 / turbo-2-5: text 5,000 → safe ceiling 4,900.
- Suno generate: V4 custom 3,000; V4_5+ custom 5,000; non-custom 3,000
  (generate-music page; mashup page says 500 — UNDETERMINED conflict);
  style V4 200 / others 1,000; title 80.
- Suno sounds: prompt 500 (rule C).
- Never pad with junk; short user prompts are expanded into the model-appropriate
  robust prompt, not rejected.

## Validation before dispatch (MANDATORY)

```
python3 scripts/validate_audio_request.py --domain tts --payload req.json
python3 scripts/validate_audio_request.py --domain music --payload req.json
python3 scripts/validate_audio_request.py --domain stt --payload req.json
```

Exit 0 = legal to dispatch (warnings advisory). Exit 2 = HARD REJECT: over-limit
text, wrong API family (Suno via createTask), out-of-enum voice/accent/style/pace,
bad speed/stability, mashup with ≠2 URLs, persona window outside 10-30s,
replace-section below 10s or above 50%, instrumental-true with prompt+vocalGender
on extend, or ANY STT dispatch attempt. Validation happens BEFORE credits are
charged.

## Async completion

- Prefer `callBackUrl` (public HTTPS, idempotent handler, record task id/state/
  result URLs) when Skill 46 KIE Callback Relay or equivalent is available.
- Polling fallback (generic Market TTS): `GET /api/v1/jobs/recordInfo?taskId=...`
  with initial delay 2-3s then stepped backoff; respect 429; never hammer.
- Suno: get music details every 30 seconds (sounds page guidance).
- A 200 on create = accepted, not complete.
- Media expires after ~14 days — persist when long-term access is needed.

## Audio QC (MANDATORY after completion)

API success is NOT QC. Run the SPEC section 9.5 lists — TTS: playable file,
language, voice identity, pronunciation, pace, style/emotion, clipping/distortion,
speaker ordering/dialogue correctness. Music: playable file, duration/model
behavior, genre/style, vocals/instrumental intent, lyrics fidelity, no
truncation/clipping, callback `complete` stage. Plus file-level checks (duration
and sample-rate sanity via header, no truncation). STT: n/a — not dispatchable.
Full checklist in `references/qc.md`.

## Retry ladder (SPEC section 15)

Same model corrected → same model alternate mode → another compatible model
(only if selection was automatic or user permits) → another provider (only when
routing allowed or user approves) → stop at cap and report why. Never burn
credits across multiple models silently.

## Files in This Folder (reading order)

1. **SKILL.md** — you are here.
2. **references/tts.md** — Gemini + ElevenLabs schemas, enums, caps, retry ladder.
3. **references/music.md** — Suno generate/extend/sounds + 14 operations, caps.
4. **references/stt.md** — the STT negative-result contract (do not "fix").
5. **references/qc.md** — 9.5 QC checklists + file-level checks.
6. **models.json** — machine-readable capability registry (TTS/Music/STT entries).
7. **scripts/validate_audio_request.py** — deterministic pre-dispatch validator.
8. **scripts/normalize_alias.py** — alias map (audio terms resolve to None).
9. **INSTALL.md / EXAMPLES.md / PREREQS.json / CHANGELOG.md / CORE_UPDATES.md.**

## Credential

`KIE_API_KEY` — the operator's KIE key (Skill 07 cheat sheet). SET/NOT-SET only;
never print the value. For TTS/music this is the same key as images/video on KIE.
There is NO separate STT key — there is no STT route at all.
