# KIE Image — API Patterns & Per-Family Request Contracts

Verification date: 2026-08-26. Authority: first-party KIE research
(`01-kie-common.md` generic conventions; `02-kie-image-a.md`,
`03-kie-image-b.md` per-family schemas). All image models verified use the
generic Market API.

---

## 1. Generic Market createTask (all image models)

```
POST https://api.kie.ai/api/v1/jobs/createTask
Authorization: Bearer <KIE_API_KEY>
Content-Type: application/json
```

Payload shape:

```json
{
  "model": "<canonical-model-id>",
  "callBackUrl": "https://your-domain.example/kie/callback",
  "input": { "prompt": "...", "...model-specific fields..." }
}
```

- `model`: required, string, format `family/version`.
- `callBackUrl`: optional, uri. "The URL to receive generation task completion
  updates." Prefer in production when Skill 46 (KIE Callback Relay) or
  equivalent is available; requirement that it be public HTTPS (spec 6.2).
- `input`: object; field set is model-specific (below).

Response (200) means the task was CREATED, not completed:

```json
{ "code": 200, "msg": "success", "data": { "taskId": "task_..." } }
```

All generation tasks on KIE are asynchronous.

## 2. Query — recordInfo

```
GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<TASK_ID>
Authorization: Bearer <KIE_API_KEY>
```

Response `data` fields: `taskId`, `model`, `state` (enum `waiting`, `queuing`,
`generating`, `success`, `fail`), `param` (original request JSON), `resultJson`
(only on success; images: `{"resultUrls": []}`), `failCode`/`failMsg` (empty on
success), `costTime` ms, `completeTime`/`createTime`/`updateTime` Unix ms,
`creditsConsumed`.

HTTP codes: 200 success, 400 (taskId required), 401 unauthorized, 402
insufficient credits, 404 not found, 408 upstream (no result over 10 min), 422
validation error (`recordInfo is null`), 429 rate limited, 433, 455 maintenance,
500 server error, 501 generation failed, 505 feature disabled.

## 3. Polling policy

- Initial delay 2–3s; then stepped/exponential backoff (spec 6.3).
- Respect 429 (rejected requests do not enter the queue); back off.
- Cap total wait by modality/model; stop after 10–15 min (docs verbatim).
- Download results immediately — result URLs expire after ~24h.

## 4. Callbacks

- Field `callBackUrl`; system POSTs task status and results when generation
  completes. Callback body carries `code`, `msg`, `data` with taskId/model/
  state/param/resultJson/failCode/failMsg/costTime/timestamps/creditsConsumed.
- Success: `code: 200, msg: "Playground task completed successfully."`; failure:
  `code: 501, msg: "Playground task failed."`, state `fail`, resultJson null.
- Expected callback response: `{"code":200,"msg":"success"}`.
- Signature scheme (webhook verification guide): `base64(HMAC-SHA256(taskId +
  "." + timestampSeconds, webhookHmacKey))`; timestamp from header
  `X-Webhook-Timestamp` (Unix seconds); result in header `X-Webhook-Signature`
  (Base64). `webhookHmacKey` generated in kie.ai/settings; keep secret.
- Retry policy: NOT EXPOSED — make callback handling idempotent, record
  provider/model/task id/request hash/state/result URLs/failure details,
  acknowledge duplicates safely, and use polling as fallback (spec 6.2).

## 5. Rate limits & retention (docs home, verbatim)

- "Up to 20 new generation requests per 10 seconds" per account.
- "100+ concurrent running tasks".
- Limits per account. Excess → HTTP 429, rejected before queueing.
- "Generated media files: stored for 14 days, then automatically deleted" —
  persist final media into durable storage immediately when long-term access is
  needed (spec 6.4). Result URLs expire ~24h.

## 6. Per-family request schemas (verbatim from research)

### 6.1 GPT Image 2

t2i model `gpt-image-2-text-to-image`; i2i model `gpt-image-2-image-to-image`.

- `prompt` (required; max 20,000 chars on docs page text, but the endpoint page
  per spec 7.4 publishes no exact hard cap — owner-observed ~25K, see
  prompt-policy.md).
- `aspect_ratio`: `auto, 1:1, 3:2, 2:3, 4:3, 3:4, 5:4, 4:5, 16:9, 9:16, 2:1, 1:2,
  3:1, 1:3, 21:9, 9:21`.
- `resolution`: `1K`, `2K`, `4K`.
- i2i refs: `input_urls` array, **maxItems: 16**; playground page: "Supported
  formats: JPEG, PNG, WEBP, JPG" + "Maximum file size: 30MB; Maximum files: 16".
- Per-resolution exclusions (verbatim): "for 2K and 4K resolution, the following
  aspect ratios are not supported: 5:4, 4:5, 3:1, 1:3, and 9:21".
- "Images with the aspect ratio set to \"auto\" or without a specified aspect
  ratio parameter will only be converted to 1K images"; "Images with a 1:1
  aspect ratio cannot be converted to 4K images".

### 6.2 Qwen Image 3.0 / Pro

- Base `qwen3/text-to-image`; Pro `qwen3-pro/text-to-image`; i2i `qwen3/image-to-image`,
  `qwen3-pro/image-to-image`.
- `prompt`: maxLength 5000, minLength 0; "Chinese and English supported".
- `resolution`: `1K` | `2K`. `image_size`: `1:1, 3:2, 2:3, 4:3, 3:4, 16:9,
  9:16, 21:9` (default 16:9).
- `output_format`: `png` | `jpeg` (default png).
- Controls: `prompt_extend` bool (default true), `negative_prompt` (maxLength
  5000), `seed` int [0, 2147483647] default 1, `nsfw_checker` bool default false
  (playground defaults true — docs differ, recorded).
- i2i refs: `image_urls` array, minItems 1, maxItems 3; "Maximum file size: 10
  MB per image"; formats `image/jpeg`, `image/png`, `image/webp`, `image/bmp`,
  `image/gif`, `image/tiff`.

### 6.3 Seedream 5.0 Pro / Lite / 4.5

- Pro: `seedream/5-pro-text-to-image`, `seedream/5-pro-image-to-image`,
  `seedream/5-pro-layer-decomposition`. i2i refs `image_urls` — "Supported
  formats: JPEG, PNG, WEBP Maximum file size: 30MB; Maximum files: 10".
- Lite: `seedream/5-lite-text-to-image`, `seedream/5-lite-image-to-image`; refs
  14 @ 30 MB.
- 4.5: `seedream/4.5-text-to-image`, `seedream/4-5-edit`; refs 14 @ 30 MB
  (playground editor; README says 10 — UNDETERMINED); NO `output_format` field.
- `quality`: `Basic` | `High` | `Ultra` (Lite only for Ultra). Pro: Basic=1K /
  High=2K. Lite: Basic=2K / High=3K / Ultra=4K. 4.5: Basic=2K / High=4K.
- `aspect_ratio` (pro/lite/4.5): `1:1, 4:3, 3:4, 16:9, 9:16, 2:3, 3:2, 21:9`.
- `output_format`: `png` | `jpeg` (Pro/Lite; NOT on 4.5). `nsfw_checker` bool.
- Single image per request; no `n` param.

### 6.4 Nano Banana family

- NB2 `nano-banana-2`: refs `image_input` array optional — 14 @ 30 MB, JPEG/PNG/
  WEBP; `resolution` 1K|2K|4K; `output_format` JPG|PNG; `aspect_ratio` 15 values:
  `1:1, 2:3, 3:2, 1:4, 4:1, 3:4, 4:3, 4:5, 5:4, 1:8, 8:1, 9:16, 16:9, 21:9, Auto`.
- NB2 Lite `nano-banana-2-lite`: only 3 exposed fields — `prompt`, `image_urls`
  (10 @ 30 MB), `aspect_ratio` (15 values: `1:1, 1:4, 1:8, 2:3, 3:2, 3:4, 4:1,
  4:3, 4:5, 5:4, 8:1, 9:16, 16:9, 21:9, Auto`). No resolution/output_format
  params exposed.
- NB Pro `nano-banana-pro`: `image_input` 8 @ 30 MB optional; resolution
  1K|2K|4K; output_format PNG|JPG; aspect_ratio 11 values: `1:1, 2:3, 3:2, 3:4,
  4:3, 4:5, 5:4, 9:16, 16:9, 21:9, Auto` (NO 1:4/4:1/1:8/8:1).
- Legacy `google/nano-banana`: edit path refs `image_urls` REQUIRED — 10 @ **10
  MB** (not 30 MB), JPEG/PNG/WEBP. T2I prompt + output_format (png|jpeg) +
  aspect_ratio (`1:1, 9:16, 16:9, 3:4, 4:3, 3:2, 2:3, 5:4, 4:5, 21:9, auto`) +
  nsfw_checker. No resolution param.

### 6.5 Wan 2.7 Image (12-field contract)

- `wan/2-7-image`, `wan/2-7-image-pro`.
- `prompt`: required, 1–5,000 chars, "Supports both Chinese and English".
- `input_urls`: optional, up to **9**; formats JPEG/PNG/WEBP/JPG; **max 10 MB**;
  "Image dimensions must be at least 240 pixels in length and width."
- `bbox_list`: string (JSON-as-string) parallel to input_urls; "Each image
  supports up to 2 boxes." Coordinates `[x1, y1, x2, y2]` original pixel coords.
- `n`: 1–4 normal; 1–12 when `enable_sequential` (gallery mode) is on — "the
  actual value is determined by the model."
- `enable_sequential` bool = Gallery Mode.
- `thinking_mode` bool: "Only available when Gallery Mode is off and no images
  are uploaded."
- `color_palette`: "Optional custom theme with 3 to 10 colors. Recommended: 8."
- `resolution`: standard `1K | 2K`; Pro `1K | 2K | 4K` (4K T2I only — README:
  "That 4K support applies to text-to-image only").
- `aspect_ratio`: `1:1, 3:4, 4:3, 1:8, 8:1, 9:16, 16:9, 21:9`.
- `watermark` bool, `seed` number, `nsfw_checker` bool.

### 6.6 FLUX.2

- `flux-2/pro-text-to-image`, `flux-2/pro-image-to-image`, `flux-2/flex-text-to-image`,
  `flux-2/flex-image-to-image`.
- T2I input: `prompt, aspect_ratio, resolution, nsfw_checker`. I2I adds
  `input_urls`. Example values: `"aspect_ratio": "1:1"`, `"resolution": "1K"`,
  `"nsfw_checker": false`.
- Prompt/reference limits NOT EXPOSED on docs routes; no fabricated caps.
- Flux Kontext is a SEPARATE dedicated API (`/api/v1/flux/kontext/generate`) —
  do not use createTask for it.

### 6.7 Z-Image

- `z-image`. T2I only, 3 fields: `prompt` (required), `aspect_ratio` (required;
  enum `1:1, 4:3, 3:4, 16:9, 9:16` — `auto` in help text only, NOT in enum),
  `nsfw_checker` bool. No image input, no resolution, no output_format, no `n`.

### 6.8 Ideogram V3

- `ideogram/v3-text-to-image`: prompt max 5000 chars; negative_prompt max 5000
  ("positive prompt takes precedence" on conflict); `rendering_speed`
  TURBO/BALANCED/QUALITY; `style` AUTO/GENERAL/REALISTIC/DESIGN ("Cannot be used
  together with `style_codes`"); `expand_prompt` bool; `image_size` named enums
  (`square, square_hd, portrait_4_3, portrait_16_9, landscape_4_3,
  landscape_16_9` — no pixel ratios published); `seed` integer.
- `ideogram/v3-edit`: single `image_url` + `mask_url` (mask "Needs to match the
  dimensions of the input image"); both 10.0 MB max, image/jpeg, image/png,
  image/webp; rendering_speed TURBO/BALANCED/QUALITY (default BALANCED);
  expand_prompt bool default true; seed int.
- `ideogram/v3-remix`: single `image_url` ("Please provide the URL of the
  uploaded file, not raw file content") 10.0 MB; `strength` "Minimum: 0.01",
  "Maximum: 1", "Step: 0.01" (example 0.8); style enum; rendering_speed;
  expand_prompt; image_size; `num_images` string enum '1'–'4'; seed;
  negative_prompt max 5000.

### 6.9 Imagen 4 family

- `google/imagen4-fast` (default aspect_ratio 16:9), `google/imagen4` (default
  1:1), `google/imagen4-ultra` (default 1:1).
- `prompt`: required, "Max length: 5000 characters"; `negative_prompt`: "Max
  length: 5000 characters".
- `aspect_ratio`: `1:1, 16:9, 9:16, 3:4, 4:3, auto`.
- `seed`: integer on fast; STRING "Max length: 500 characters" on standard and
  ultra. No reference-image fields on any verified route.
