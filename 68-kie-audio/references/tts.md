# KIE TTS Reference — Gemini + ElevenLabs (verified 2026-08-26)

All facts below are from first-party KIE docs pages fetched directly on
2026-08-26 (markdown conversion of docs.kie.ai via WebFetch). Limits are quoted
verbatim. Source URL is named per model/claim. Every TTS route on KIE is a
GENERIC MARKET ROUTE: `POST https://api.kie.ai/api/v1/jobs/createTask` with the
`model` enum selecting the engine. There are NO dedicated
`/api/v1/elevenlabs/...` or `/api/v1/tts/...` routes in the docs.

Query callback/polling (all TTS models): `GET /api/v1/jobs/recordInfo?taskId=<TASK_ID>`
(see https://docs.kie.ai/market/common/get-task-detail). Auth on every call:
`Authorization: Bearer $KIE_API_KEY`, `Content-Type: application/json`.

## 1. Gemini 3.1 Flash TTS — VERIFIED

Source: https://docs.kie.ai/market/google/gemini-3-1-flash-tts

- Model id: `google/gemini-3-1-flash-tts` (enum, single value)
- Create: `POST /api/v1/jobs/createTask`. Query: unified `GET /api/v1/jobs/recordInfo`.

### Top-level payload

```json
{
  "model": "google/gemini-3-1-flash-tts",
  "callBackUrl": "https://your-domain.example/kie/callback",
  "input": { "…schema below…" }
}
```

### input schema

| Field | Type | Requirement | Notes |
|---|---|---|---|
| `temperature` | number | optional | min 0, max 2, default 1 |
| `scene` | string | optional | "Scene description" |
| `sample_context` | string | optional | "Sample context/overall tone" |
| `speakers` | array | **required** | see below |
| `dialogue_turns` | array | **required** | see below |

`speakers[]` items:

- `speaker_id` (required) — "Must be 「Speaker N」format" (e.g. `"Speaker 1"`)
- `voice_name` (required) — enum of 30 voices:
  Achernar, Achird, Algenib, Algieba, Alnilam, Aoede, Autonoe, Callirrhoe,
  Charon, Despina, Enceladus, Erinome, Fenrir, Gacrux, Iapetus, Kore,
  Laomedeia, Leda, Orus, Puck, Pulcherrima, Rasalgethi, Sadachbia, Sadaltager,
  Schedar, Sulafat, Umbriel, Vindemiatrix, Zephyr, Zubenelgenubi
- `audio_profile` (string, optional)
- `accent` (required) — enum 8: Neutral, American (Gen), American (Valley),
  American (South), British (RP), British (Brixton), Transatlantic, Australian
- `style` (enum, optional) — 6: Vocal Smile, Newscaster, Whisper, Empathetic,
  Promo/Hype, Deadpan
- `pace` (enum, optional) — 4: Natural, Rapid Fire, The Drift, Staccato

`dialogue_turns[]` items: `speaker_id` (required), `text` (required, **max 10000 chars**).

No `voices` / `dialogue` / `context` flat fields — the schema uses
`speakers` + `dialogue_turns` only.

### Output

200: `{"code":200,"msg":"success","data":{"taskId":"task_1765185282276"}}`

Callback `musicTaskCompleted` POSTs to `callBackUrl`:

- success `code:200` / failure `code:501`
- `data.state` = `success` / `fail`
- audio at `resultJson` → `{"resultUrls":["https://example.com/generated-audio.mp3"],"resultObject":null}`

## 2. Gemini 2.5 Pro TTS — VERIFIED

Source: https://docs.kie.ai/google/gemini-2-5-pro-tts

- Model id: `google/gemini-2-5-pro-tts`
- Create: `POST /api/v1/jobs/createTask` (same generic Market route; page links
  to the unified query endpoint — no dedicated route spelled out in-page).
- Live body schema — SAME SHAPE as 3.1 Flash: `input.temperature` (0-2, default 1),
  `scene`, `sample_context`, `speakers` (required; `speaker_id` "«Speaker N»",
  `voice_name` required, same 30-voice enum, `audio_profile`, `accent` required
  same 8-enum, `style` same 6-enum, `pace` same 4-enum), `dialogue_turns`
  (required; `speaker_id`, `text` maxLength 10000).
- Output: taskId `task_1765185282276`; callback with `resultJson.resultUrls`.

## 3. ElevenLabs routes on KIE — ALL THREE VERIFIED

Sources: sitemap + per-model pages
https://docs.kie.ai/market/elevenlabs/text-to-dialogue-v3,
.../text-to-speech-multilingual-v2, .../text-to-speech-turbo-2-5

All three are generic Market routes: `POST https://api.kie.ai/api/v1/jobs/createTask`
with `model` enum selecting the model. Query via unified `GET /api/v1/jobs/recordInfo`.

### elevenlabs/text-to-dialogue-v3

OperationId `elevenlabs-text-to-dialogue-v3`.

| Field | Type | Notes |
|---|---|---|
| `input.dialogue` | array, **required** | items: `text` string, `voice` string enum of voice IDs, default `EkK5I93UQWFDigLMpZcX` |
| `input.stability` | enum | 0 / 0.5 / 1, default 0.5 |
| `input.language_code` | enum | ~72 codes |

Verbatim constraint: **"total character count of all text fields combined must
not exceed 5000 characters."**

Output: `data.taskId` AND `data.recordId` — e.g.
`"taskId":"task_elevenlabs_1765185448724","recordId":"elevenlabs_1765185448724"`.

### elevenlabs/text-to-speech-multilingual-v2

| Field | Type | Notes |
|---|---|---|
| `input.text` | string | max 5000 |
| `input.voice` | enum ~70 IDs | default `EkK5I93UQWFDigLMpZcX` |
| `input.stability` | number 0-1 | default 0.5 |
| `input.similarity_boost` | number 0-1 | default 0.75 |
| `input.style` | number 0-1 | default 0 |
| `input.speed` | number 0.7-1.2 | default 1 |
| `input.timestamps` | bool | default false |
| `input.previous_text` | string | max 5000 |
| `input.next_text` | string | max 5000 |
| `input.language_code` | string | max 500 (ISO 639-1) |

### elevenlabs/text-to-speech-turbo-2-5

Same fields as multilingual-v2 with the same defaults (`text` maxLength 5000).
Voice preview: `https://static.aiquickdraw.com/elevenlabs/voice/<voice_id>.mp3`.

Verbatim: **"Currently only Turbo v2.5 and Flash v2.5 support language enforcement."**

Callback failure: `code:501`, `failCode:"GENERATION_FAILED"`.

No documented interface-level rate-limit numbers on these pages; error enums
include 429 rate limited.

## 4. House prompt band vs TTS model caps (SPEC section 5)

The 5,000 / ~9,000 / 19,000 BlackCEO prompt band is a HOUSE POLICY, not a
provider limit. For TTS the model caps are far below 5,000 in the ElevenLabs
cases — per SPEC rule B (verified cap 5,000-19,999): use a safe ceiling with
headroom; do not force the 5,000 floor where the cap is 5,000.

| Route | Cap | Safe ceiling | Rule |
|---|---|---|---|
| Gemini TTS (both) | 10,000 per dialogue turn | ~9,500 per turn | B (per turn; combined script not capped by one field) |
| dialogue-v3 | 5,000 combined | 4,900 | B; floor 5,000 impossible |
| multilingual-v2 / turbo-2-5 | 5,000 text | 4,900 | B; floor 5,000 impossible |

## 5. Retry ladder (SPEC section 15)

1. Same model, corrected prompt/parameters.
2. Same model, alternate valid mode/reference encoding.
3. Another compatible model in the same provider only if model selection was
   automatic or user permits it.
4. Another provider only when generic provider routing is allowed or user approves.
5. Stop after the configured retry cap and report why.

Never silently burn credits across multiple models.
