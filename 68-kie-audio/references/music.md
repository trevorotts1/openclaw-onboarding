# KIE Suno Music/Sound Reference (verified 2026-08-26)

Suno is a DEDICATED API family on KIE. It must NEVER be routed through the
generic `/api/v1/jobs/createTask` Market route (SPEC section 6.5).

Server: `https://api.kie.ai`. Auth: `Authorization: Bearer $KIE_API_KEY`.

Facts below are from first-party KIE docs pages fetched 2026-08-26; limits
quoted verbatim with source URLs. Pricing is NOT published on these pages —
no numbers are invented here.

## 1. Generate music — `POST /api/v1/generate` — VERIFIED

Source: https://docs.kie.ai/suno-api/generate-music/

Models enum: `V4`, `V4_5`, `V4_5PLUS`, `V4_5ALL`, `V5`, `V5_5`.

### Prompt limits
- Custom mode: V4 "Maximum 3000 characters"; V4_5, V4_5PLUS, V4_5ALL, V5, V5_5
  "Maximum 5000 characters".
- Non-custom mode (customMode false): "prompt length limit: 3000 characters" —
  NOT 500. (CONFLICT: the generate-mashup page says non-custom max 500 chars.
  Both verbatim; conflict UNDETERMINED — do not resolve by guessing.)

### Style limits (custom mode)
V4 "Maximum 200 characters"; V4_5/V4_5PLUS/V4_5ALL/V5/V5_5 "Maximum 1000 characters".

### Title
"title length limit: 80 characters (all models)" / "Max length: 80 characters."
— a SINGLE 80 for all models on generate (80/100 split is EXTEND-only).

### Duration
"only effective when custom_mode is true and model is V5_5." Default 20,
min 10, max 360.

### Fields
Required non-custom: `prompt`, `customMode`, `instrumental`, `model`,
`callBackUrl`. Custom instrumental: `style`, `title`. Custom non-instrumental:
`style`, `prompt`, `title`.

Optional: `negativeTags`, `vocalGender` ("m"/"f"), `styleWeight` (0-1),
`weirdnessConstraint` (0-1), `audioWeight` (0-1), `personaId`, `personaModel`
("style_persona"/"voice_persona" — V5/5.5 only), `duration`.

### Output
`data.taskId`. Callback stages: `text`, `first`, `complete`. Callback items:
`id`, `audio_url`, `stream_audio_url`, `image_url`, `prompt`, `model_name`,
`title`, `tags`, `createTime`, `duration`.

## 2. Extend music — `POST /api/v1/generate/extend` — VERIFIED

Source: https://docs.kie.ai/suno-api/extend-music/

### Title limits per model (verbatim)
- V4: "Maximum 80 characters"
- V4_5 & V4_5PLUS: "Maximum 100 characters"
- V4_5ALL: "Maximum 80 characters"
- V5_5 & V5: "Maximum 100 characters"

### Prompt limits per model
- V4 "Max 3,000 characters"; V4_5/V4_5PLUS "Max 5,000 characters";
  V4_5ALL "Max 5,000 characters"; V5_5/V5 "Max 5,000 characters"

### Fields
Required: `defaultParamFlag`, `audioId`, `model`, `callBackUrl`. Optional:
`prompt`, `style`, `title`, `continueAt` ("The time point (in seconds) from
which to start extending the music"), `negativeTags`, `vocalGender`,
`styleWeight`, `weirdnessConstraint`, `audioWeight`, `personaId`,
`personaModel`, `instrumental` — if `instrumental` true, passing `prompt` and
`vocalGender` is PROHIBITED.

`defaultParamFlag` true = use custom params; false = only `audioId` needed.
Retention 14 days.

Output: `data.taskId`; callback same shape as generate with `model_name`
example `chirp-v3-5`.

No `duration` field on extend at all — extension length is implicit;
`continueAt` marks the start point.

## 3. Sounds — `POST /api/v1/generate/sounds` — VERIFIED

Source: https://docs.kie.ai/suno-api/generate-sounds

- Required: `prompt` (string, "limit: 500 characters"), `model`
  (enum `V5`, `V5_5`).
- Optional: `soundLoop` (boolean, default false), `soundTempo` (integer, BPM,
  "minimum: 1 maximum: 300"), `soundKey` (string, default "Any", enum minor
  `Cm`..`Bm` and major `C`..`B`), `grabLyrics` (boolean, default false),
  `callBackUrl` (string).
- Output: `data.taskId`. Poll via get music details, **"every 30 seconds."**
- Example: `{"prompt":"sint","model":"V5","soundLoop":true,"soundTempo":166,"soundKey":"D#m","grabLyrics":true}`

## 4. Other Suno operations — VERIFIED (routes documented)

| Operation | Route | Notes |
|---|---|---|
| Upload + cover | `POST /api/v1/generate/upload-cover` | uploadUrl audio <= 8 min; non-custom prompt limit 500 |
| Upload + extend | `POST /api/v1/generate/upload-extend` | continueAt > 0 and < total duration; model must match source |
| Add instrumental | `POST /api/v1/generate/add-instrumental` | model enum V4_5PLUS/V5/V5_5 default V4_5PLUS; negativeTags max 200, tags max 1000 |
| Add vocals | `POST /api/v1/generate/add-vocals` | negativeTags max 200, style max 1000 |
| Cover generation | `POST /api/v1/suno/cover/generate` | taskId + callBackUrl; one cover per task ("Each music task can only generate a Cover once") |
| Replace section | `POST /api/v1/generate/replace-section` | infillStartS < infillEndS; replacement min 10 sec, max 50% of original duration |
| Persona | `POST /api/v1/generate/generate-persona` | vocalEnd-vocalStart 10-30s; v3.5 not supported; once per audioId |
| Mashup | `POST /api/v1/generate/mashup` | "must contain exactly 2 audio file URLs" (uploadUrlList min/max 2) |
| Lyrics generation | `POST /api/v1/lyrics` | "maximum word limit is 200 characters" (page text verbatim) |
| Timestamped lyrics | `POST /api/v1/generate/get-timestamped-lyrics` | taskId+audioId; instrumental returns no lyrics |
| WAV conversion | `POST /api/v1/wav/generate` | taskId+audioId+callBackUrl; WAV 5-10x MP3 size |
| Vocal/stem separation | `POST /api/v1/vocal-removal/generate` | type separate_vocal (10 cr) / split_stem (50 cr, up to 12 stems) / split_stem_advanced (20 cr); audioUrl max 20MB |
| MIDI generation | `POST /api/v1/midi/generate` | requires completed vocal separation taskId |
| Music video | `POST /api/v1/mp4/generate` | taskId+audioId+callBackUrl; author/domainName max 50 each |

## 5. UNDETERMINED / NOT EXPOSED (do not invent)

1. Mashup non-custom-mode prompt limit: mashup doc says "Non-custom mode max
   500 chars"; generate-music says 3000 non-custom. Both verbatim; conflict
   NOT resolved.
2. Rate limits/concurrency numbers: not on these pages; docs homepage cites a
   "Rate Limits & Concurrency" section without extracted numbers.
3. Pricing: not published on these pages — no numbers recorded.
4. Suno voice family endpoints (suno-voice-validate, suno-voice-generate,
   suno-voice-regenerate, suno-voice-record-info, suno-voice-check-voice +
   callbacks) exist in the sitemap but were NOT fetched in the 2026-08-26 pass.

## 6. Callback stages and items (generate/extend)

Stages: `text` → `first` → `complete`. Items: `id`, `audio_url`,
`stream_audio_url`, `image_url`, `prompt`, `model_name`, `title`, `tags`,
`createTime`, `duration`. Retention 14 days — persist final media into durable
storage immediately when long-term access is required.
