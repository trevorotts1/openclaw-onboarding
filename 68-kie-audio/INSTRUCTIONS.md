╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TYP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TYP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TYP"
- Look in your session context for prior TYP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TYP:
Proceed to the instructions below. Follow the TYP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TYP:
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TYP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TYP, I will bloat your core .md files and waste your tokens."

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

══════════════════════════════════════════════════════════════════
KIE AUDIO - HOW TO USE THE ENDPOINTS (DAILY USAGE GUIDE)
══════════════════════════════════════════════════════════════════

This document explains how to use KIE audio day to day. If the credential is
not confirmed yet, go to INSTALL.md first. For complete schemas, every enum,
and the limit quotes, see references/tts.md (TTS) and references/music.md (Suno).

## THE BIG PICTURE — THREE SUB-DOMAINS, TWO API FAMILIES

1. TTS (Gemini + ElevenLabs): generic Market
   `POST https://api.kie.ai/api/v1/jobs/createTask`, model enum selects engine.
   Asynchronous: get taskId, wait for callback or poll recordInfo.
2. Music/Suno: DEDICATED family `POST /api/v1/generate` (+ extend/sounds/ops).
   NEVER through createTask.
3. STT: not available. `ADVERTISED_NOT_YET_VERIFIED`, `dispatch_enabled: false`.
   Never route a transcription request here.

Common auth on every call:
  Authorization: Bearer $KIE_API_KEY
  Content-Type: application/json

## TTS — Gemini (multi-speaker dialogue)

Required: `model`, `callBackUrl` (recommended), `input` with `speakers[]` and
`dialogue_turns[]`.

- `speakers[]`: `speaker_id` "Speaker N", `voice_name` (30-voice enum),
  `accent` (8-enum), optional `audio_profile`, `style` (6-enum), `pace` (4-enum).
- `dialogue_turns[]`: `speaker_id` matching a speaker, `text` max 10,000 chars.
- Optional: `scene`, `sample_context`, `temperature` (0-2, default 1).
- Per-turn text ≤ ~9,500 for headroom (hard 10,000).

## TTS — ElevenLabs

- dialogue-v3: `input.dialogue[]` (text + voice, default voice
  EkK5I93UQWFDigLMpZcX); `input.stability` 0/0.5/1 (default 0.5);
  `input.language_code` (~72 codes). Combined text of ALL dialogue fields
  must not exceed 5,000 characters (verbatim) — safe ceiling 4,900.
- multilingual-v2 / turbo-2-5: `input.text` (≤5,000, safe 4,900), `voice`,
  `stability` (0-1, 0.5), `similarity_boost` (0-1, 0.75), `style` (0-1, 0),
  `speed` (0.7-1.2, 1), `timestamps` (bool), `previous_text`/`next_text`
  (each ≤5,000), `language_code`. Turbo v2.5: language enforcement note
  (Turbo v2.5 and Flash v2.5 only).

## Music/Suno — generate

Route never through createTask. Required (non-custom): `prompt`, `customMode`,
`instrumental`, `model` (V4/V4_5/V4_5PLUS/V4_5ALL/V5/V5_5), `callBackUrl`.
Custom: `style`, `title` (+`prompt` if not instrumental). Optional: `negativeTags`,
`vocalGender` ("m"/"f"), `styleWeight`/`weirdnessConstraint`/`audioWeight` (0-1),
`personaId`, `personaModel` (style_persona/voice_persona, V5/5.5 only),
`duration` (only effective for V5_5 custom: 10-360, default 20; otherwise
ignored by provider).

Caps: custom prompt V4 3,000 / others 5,000; non-custom 3,000 (generate-music
page; mashup page says 500 — UNDETERMINED); style V4 200 / others 1,000;
title 80 (all models on generate).

## Music/Suno — extend

`POST /api/v1/generate/extend`. Required: `defaultParamFlag`, `audioId`,
`model`, `callBackUrl`. `continueAt` = seconds to start extending from.
instrumental=true PROHIBITS prompt + vocalGender. Title: V4 80, V4_5/V4_5PLUS 100,
V4_5ALL 80, V5/V5_5 100. Prompt: V4 3,000, others 5,000.

## Music/Suno — sounds

`POST /api/v1/generate/sounds`. Required: `prompt` (max 500), `model` (V5/V5_5).
Optional: `soundLoop` (bool), `soundTempo` (1-300 BPM), `soundKey` (default
"Any"; minor Cm..Bm, major C..B), `grabLyrics` (bool), `callBackUrl`.

## Music/Suno — other operations

Full 14-op table in references/music.md. Highlights:
- mashup: uploadUrlList must contain EXACTLY 2 audio URLs.
- generate-persona: vocalEnd-vocalStart 10-30s; once per audioId.
- replace-section: infillStartS < infillEndS; replacement ≥10s, ≤50% of original.
- cover: one cover per music task (second generation prohibited).
- vocal-removal: separate_vocal 10 cr / split_stem 50 cr / split_stem_advanced 20 cr;
  audioUrl ≤20MB.
- midi: requires a COMPLETED vocal-separation taskId.
- mp4: author/domainName max 50 each.

## Validation before dispatch (MANDATORY)

  python3 scripts/validate_audio_request.py --domain tts --payload req.json
  python3 scripts/validate_audio_request.py --domain music --payload req.json

Exit 2 = do NOT dispatch. Fix the payload, do not bypass the validator.

## Async completion

- Prefer `callBackUrl`; make the handler idempotent; record provider, model,
  task id, state, result URLs, failure details.
- Polling fallback (Market TTS): `GET /api/v1/jobs/recordInfo?taskId=<TASK_ID>`,
  initial delay 2-3s, stepped backoff, respect 429.
- Suno: poll get music details every 30 seconds.
- 200 on create = accepted, NOT complete. Callback stages are `text` →
  `first` → `complete` for Suno; only `complete` is finished output.
- KIE media expires after ~14 days — persist when long-term access is needed.

## STT — never route here

No endpoint, no example, no dispatch. If asked, answer from `references/stt.md`:
KIE advertises ElevenLabs STT but no callable endpoint was found (sitemap
~460 URLs zero hits; elevenlabs docs dir = 4 models, all TTS/audio-isolation;
market page 403; WebSearch zero). Status ADVERTISED_NOT_YET_VERIFIED. When a
first-party page appears, re-prove per references/stt.md, then update registry +
docs + version.

## QC after generation (MANDATORY)

Run the SPEC 9.5 lists in references/qc.md and actually verify the audio:
playable file, language, voice identity, pronunciation, pace, style/emotion,
clipping/distortion, speaker ordering (TTS); playable file, duration/model
behavior, genre/style, vocals/instrumental intent, lyrics fidelity, no
truncation/clipping, callback complete stage (music). Retry only per the
controlled ladder in references/qc.md.
