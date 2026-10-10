---
name: kie-audio
description: >
  KIE.ai audio skill: TTS (Gemini 3.1 Flash / 2.5 Pro + ElevenLabs dialogue-v3 /
  multilingual-v2 / turbo-2-5 via generic Market createTask), Suno music/sound
  generation (CURRENT createTask envelope ai-music-api/* default V6 + LEGACY
  dedicated /api/v1/generate family), supported audio processing operations,
  and speech-to-text CAPABILITY DETECTION (ADVERTISED_NOT_YET_VERIFIED — no
  endpoint, dispatch_enabled false).
version: v2.3.1
metadata:
  version: "2.3.1"
  priority: HIGH
---

# KIE Audio — TTS, Music/Suno, STT status

KIE Audio owns model selection, payload validation, prompt sizing, async
completion, and audio QC for three sub-domains with DISTINCT API families:

1. **TTS** — generic Market `POST /api/v1/jobs/createTask` (Gemini + ElevenLabs
   engines; see `references/tts.md`).
2. **MUSIC** — Suno in TWO routes (see `references/music.md`): CURRENT
   `POST /api/v1/jobs/createTask` with top-level model `ai-music-api/*`
   (version at `input.model`, default V6) for generate / extend /
   upload-and-extend-audio / generate-persona / sounds, plus the LEGACY
   dedicated `POST /api/v1/generate` family (+ `/extend`, `/sounds`, and 14
   documented operations) kept for V4..V5_5 (live-marked Discontinued —
   accepted with a warning, never dropped). ONLY `ai-music-api/*` rides
   createTask.
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

### Music (Suno LAYERED routes — current createTask envelope + legacy dedicated family)

| Route | Purpose |
|---|---|
| `POST /api/v1/jobs/createTask` + `ai-music-api/generate` | songs (CURRENT); `input.model` V4..V6_WILD, default V6 |
| `POST /api/v1/jobs/createTask` + `ai-music-api/extend` / `ai-music-api/upload-and-extend-audio` | extend a track from `continue_at` (CURRENT) |
| `POST /api/v1/jobs/createTask` + `ai-music-api/sounds` | sound effects (CURRENT); V5/V5_5/V6/V6_MINI/V6_WILD; prompt 500 |
| `POST /api/v1/jobs/createTask` + `ai-music-api/generate-persona` | persona (CURRENT); vocal window 10-30s |
| `POST /api/v1/generate` | songs (LEGACY; V4..V5_5 Discontinued — warned, kept) |
| `POST /api/v1/generate/extend` | extend a track from `continueAt` (LEGACY) |
| `POST /api/v1/generate/sounds` | sound effects (LEGACY); V5/V5_5; prompt 500 |
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
- Suno generate: V4 custom 3,000; V4_5+ custom 5,000 (V6 family included);
  non-custom 3,000 (generate-music page; mashup page says 500 — UNDETERMINED
  conflict, validator enforces the smaller 500 with no floor); lyrics 5,000
  (verbatim, floor-exempt); style V4 200 / others 1,000; title 80; duration
  effective for V5_5/V6/V6_MINI/V6_WILD custom only (10-360, default 20).
- Suno sounds: prompt 500 (rule C); models V5/V5_5/V6/V6_MINI/V6_WILD.
- Never pad with junk; short user prompts are expanded into the model-appropriate
  robust prompt, not rejected.

## Validation before dispatch (MANDATORY)

```
python3 scripts/validate_audio_request.py --domain tts --payload req.json
python3 scripts/validate_audio_request.py --domain music --payload req.json
python3 scripts/validate_audio_request.py --domain stt --payload req.json
```

Exit 0 = legal to dispatch (warnings advisory). Exit 2 = HARD REJECT: over-limit
text, wrong API family (non-ai-music-api Suno via createTask), out-of-enum voice/accent/style/pace,
bad speed/stability, mashup with ≠2 URLs, persona window outside 10-30s,
replace-section below 10s or above 50%, instrumental-true with prompt+vocalGender
on extend, or ANY STT dispatch attempt. Validation happens BEFORE credits are
charged.

## Registry role and Skill 74 dispatch

`models.json` is this skill's CURATED POLICY and verified-override registry (TTS and Suno
limits, enums, owner rulings, the closed STT gate). It is not the exhaustive KIE catalog and
not the live source of limits or prices: Skill 74 `validate` (live schema, registry
fallback), `price` and `preflight` (balance must cover price x 1.30) are. TTS dispatch runs
`validate`, `preflight`, then `submit --mode active` (production batches add `--callback-url`
of the Skill 46 relay), then this skill's audio QC; see INSTRUCTIONS.md. A model missing from
`models.json` is DISCOVERED, never an automatic default (no auto-latest for audio). Suno keeps
its curated layered route (current createTask envelope + legacy dedicated family). The STT gate
stays fail-closed: the validator may report, from a free catalog GET, that a speech-to-text
model exists, and still refuses dispatch.

## Async completion

- Prefer `callBackUrl` (public HTTPS, idempotent handler, record task id/state/
  result URLs) when Skill 46 KIE Callback Relay or equivalent is available.
- Polling fallback (generic Market TTS): `GET /api/v1/jobs/recordInfo?taskId=...`
  with initial delay 2-3s then stepped backoff; respect 429; never hammer.
- Suno: get music details every 30 seconds (sounds page guidance). Vendor note
  (KIE's official kie-models text, 2026-10-09): newer Suno tasks sent through
  the generic `createTask` envelope are polled with the normal `recordInfo`
  call, with tracks at `response.data[].audio_url` (and text/analysis tasks at
  `response.resultObject`). This is vendor text, not a live test; the legacy
  `/api/v1/generate` family's record path stays UNVERIFIED (the official
  get-task-detail/query-task-detail doc URLs return HTTP 404).
- A 200 on create = accepted, not complete.
- Retention: KIE documents 14 days for generated media but its task-detail page says result URLs typically expire after 24 hours; download/persist immediately.

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
