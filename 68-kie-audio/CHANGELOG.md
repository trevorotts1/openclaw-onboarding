# Changelog - kie-audio

All notable changes to this skill are documented here.

---

## [2.0.0] - 2026-08-26

### Added
- Initial release: KIE.ai audio skill (Skill 68) covering three sub-domains with
  DISTINCT API families:
  - **TTS** via the generic Market route
    `POST https://api.kie.ai/api/v1/jobs/createTask` (query
    `GET /api/v1/jobs/recordInfo`): `google/gemini-3-1-flash-tts` and
    `google/gemini-2-5-pro-tts` (30-voice enum, 8 accents, 6 styles, 4 paces,
    per-turn text max 10,000, `speakers[]` + `dialogue_turns[]` schema), and the
    three ElevenLabs routes `elevenlabs/text-to-dialogue-v3` (combined text of
    all dialogue fields max 5,000 — verbatim), `text-to-speech-multilingual-v2`
    and `text-to-speech-turbo-2-5` (text max 5,000; turbo v2.5 language
    enforcement note; failure `failCode: GENERATION_FAILED`).
  - **Music** — Suno DEDICATED API family (SPEC 6.5; NEVER routed through
    createTask): `POST /api/v1/generate`, `/generate/extend`, `/generate/sounds`,
    plus the 14 documented operations (upload-cover, upload-extend,
    add-instrumental, add-vocals, cover, replace-section, generate-persona,
    mashup, lyrics, get-timestamped-lyrics, wav, vocal-removal, midi, mp4) with
    verbatim limits (models V4/V4_5/V4_5PLUS/V4_5ALL/V5/V5_5; custom prompt V4
    3,000 / others 5,000; non-custom 3,000; style V4 200 / others 1,000; title
    80 generate; duration effective ONLY for V5_5 custom 10-360 default 20;
    sounds prompt 500; mashup exactly 2 URLs; persona vocal window 10-30s;
    replace-section min 10s max 50%; lyrics 200; mp4 author/domain 50).
  - **STT** — `ADVERTISED_NOT_YET_VERIFIED`, `dispatch_enabled: false`: the
    skill ships NO endpoint and refuses to invent one. The full negative-result
    trail (2026-08-26) is documented in `references/stt.md`: docs sitemap (EN+CN,
    ~460 URLs) zero matches for stt/asr/transcribe/transcription/whisper/
    speech-to-text/deepgram/google/speech; the KIE docs elevenlabs directory
    holds exactly 4 models, all TTS or audio isolation; `kie.ai/market` returned
    HTTP 403 to WebFetch; WebSearch variants returned zero results.
- Machine-readable capability registry `models.json` (SPEC 12): 9 entries —
  TTS 5, Suno 4 families (generate, extend, sounds, other-operations with a
  14-operation records table), STT 1 special entry. Every entry carries
  source_url from the first-party docs page verified 2026-08-26.
- Deterministic validator `scripts/validate_audio_request.py` (SPEC 14) with
  `--self-test` (13 checks): per-turn 10,000/combined 5,000 caps, enum checks,
  Suno family guard (never createTask), duration advisory, sounds 500, mashup
  exactly 2 URLs, persona window, replace-section bounds, instrumental-true
  prohibition, STT dispatch hard-rejected with the negative-result reference.
- Alias normalizer `scripts/normalize_alias.py` (SPEC 13): shared image/video
  alias map; audio terms resolve FAMILY_OF = None (no audio aliases exist).
- `references/tts.md`, `references/music.md`, `references/stt.md`,
  `references/qc.md` (SPEC 9.5 verbatim TTS/music audio QC lists + file-level
  checks + retry ladder 15).
- `wire.sh` idempotent marker-based installer (63 pattern): writes AGENTS/TOOLS/
  MEMORY pointer blocks REPLACE-IN-PLACE behind
  `<!-- BEGIN/END skill:68-kie-audio:<target> -->`, resolves
  `[MASTER_FILES_FOLDER]` to an absolute path, stamps
  `<!-- skill:68-kie-audio:core-update-applied -->`, backs up only on change.
- `PREREQS.json` (Skills 01/02 + required credential `kie-api-key` KIE_API_KEY),
  `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `QC.md`, `skill-version.txt`.

### Notes
- NOT published by KIE docs: numeric rate limits/concurrency (429 handled live),
  pricing (no numbers invented), a dedicated `/api/v1/elevenlabs/*` route, and
  the KIE `KIE_API_KEY` environment name (docs use `YOUR_API_KEY`; repo
  convention wins).
- UNDETERMINED (both verbatim, conflict not resolved): Suno non-custom prompt
  limit — generate-music page says 3,000, mashup page says 500.
- `kie.ai/market` (source of the STT advertisement) is 403-blocked; the claim
  text itself was never read on-page.

## [v2.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
