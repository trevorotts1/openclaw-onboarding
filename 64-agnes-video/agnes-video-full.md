
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
Proceed to the reference below. Follow the TYP file storage structure — save
this full document to the master files folder and keep only a lean pointer in
your core .md files.

IF YOU HAVE NOT BEEN TAUGHT TYP:
STOP IMMEDIATELY. Do not read further. Tell the user you have not been taught
the Teach Yourself Protocol yet and cannot safely learn these instructions
until you have.

══════════════════════════════════════════════════════════════════

# Agnes Video — Complete Endpoint Reference (2.5 Flash + V2.0)

> Asynchronous video-generation API on the Agnes AI gateway
> (`apihub.agnes-ai.com`). Two approved models in this skill's registry:
> **`agnes-video-2.5-flash`** (string-enum seconds, 720P only, 3 modes) and
> **`agnes-video-v2.0`** (frame-driven duration, width/height, 480p-1080p).
> Create a task first, then retrieve by `video_id`.
>
> Official docs index: https://wiki.agnes-ai.com/llms.txt

| | |
|---|---|
| **Create task (both models)** | `POST https://apihub.agnes-ai.com/v1/videos` |
| **Get result — Flash (ALL modes)** | `GET https://apihub.agnes-ai.com/agnesapi?video_id=<VIDEO_ID>&model_name=agnes-video-2.5-flash` |
| **Get result — V2.0** | `GET https://apihub.agnes-ai.com/agnesapi?video_id=<VIDEO_ID>` (optional `&model_name=agnes-video-v2.0`) |
| **Get result — legacy (V2.0)** | `GET https://apihub.agnes-ai.com/v1/videos/<TASK_ID>` |
| **Model without a router decision** | `scripts/select_agnes_video_model.py` — run it FIRST |

> **MODEL CHOICE IS NOT MANUAL.** The deterministic router
> `scripts/select_agnes_video_model.py` is the single source of truth for which
> model a request goes to. Explicit model wins. Never silently switch. The
> semantic guard refuses to reinterpret Flash reference images as V2.0
> keyframes. Run the router, read its JSON verdict, then build the payload the
> verdict names.

## Overview

Both models generate videos from text prompts, from images, or by tweening
between keyframes. They differ sharply:

| Aspect | `agnes-video-2.5-flash` | `agnes-video-v2.0` |
|---|---|---|
| Duration | `seconds` STRING `"4"`–`"12"` (default `"5"`) | `num_frames`/`frame_rate`; `seconds = num_frames / frame_rate` |
| Size | ONLY `"720P"` (else HTTP 400 `size must be 720P`) | `480p` / `720p` / `1080p`; width/height normalized |
| Aspect ratios | `21:9, 16:9, 4:3, 1:1, 3:4, 9:16` | `16:9, 9:16, 1:1, 4:3, 3:4` |
| Modes | `text`, `keyframe`, `reference` | `ti2vid` / `keyframes` (via `extra_body`) |
| Single image | — (reference mode takes `images[]`) | top-level `image` URL string |
| Frames/counts | `num_frames`, `frame_rate`, `negative_prompt`, `inference_steps` NOT fields | `num_frames` <= 441 AND 8n+1; `frame_rate` 1-60 |
| Seed | integer, supported | integer, supported |
| n | only `1` (default 1) | not published |
| Audio refs | `audios` string[] in reference mode | not published |
| Video refs | NOT supported (HTTP 400 `videos is not supported`) | not published |

Video generation is **asynchronous**: create a task, then poll for the result.
This is different from Agnes *image* generation (`agnes-image-2.1-flash`),
which is synchronous and returns the image in the same response.

## Authentication

Every request carries the fleet-provisioned key as a Bearer token. The key lives
as `AGNES_AI_API_KEY`. Verify it is SET; never print its value.

```bash
-H "Authorization: Bearer $AGNES_AI_API_KEY"
-H "Content-Type: application/json"
```

---

## PART A — AGNES VIDEO 2.5 FLASH (`agnes-video-2.5-flash`)

### Create Task Parameters — `POST /v1/videos`

| Parameter        | Type   | Required | Description |
| ---------------- | ------ | -------- | ----------- |
| `model`          | string | **Yes**  | `agnes-video-2.5-flash` |
| `prompt`         | string | **Yes**  | Text description of the video content |
| `mode`           | string | No       | `text` (default) / `keyframe` / `reference` |
| `seconds`        | string | No       | **STRING** `"4"`–`"12"`. Default `"5"`. Any string outside the enum -> HTTP 400 |
| `size`           | string | No       | **ONLY** `"720P"`. Any other value -> HTTP 400 `size must be 720P` |
| `aspect_ratio`   | string | No       | One of `21:9, 16:9, 4:3, 1:1, 3:4, 9:16` (default `16:9`) |
| `seed`           | int    | No       | Reproducibility seed |
| `n`              | int    | No       | Only `1` is supported; default `1`. Never send another value |
| `first_frame`    | string | keyframe | First-frame image URL. At least one of first_frame/last_frame for keyframe mode |
| `last_frame`     | string | keyframe | Last-frame image URL |
| `images`         | array  | reference | Reference image URLs. **Max 5** — beyond -> HTTP 400 `images length must not exceed 5` |
| `audios`         | array  | reference | Audio URLs (string[], "following Agnes Video 2.5 common rules") |
| `videos`         | array  | **NEVER** | NOT supported -> HTTP 400 `videos is not supported` |

Flash has NO `width`, `height`, `num_frames`, `frame_rate`, `negative_prompt`,
or `num_inference_steps`. Adding them produces 400s.

### Flash aspect pixels (verbatim vendor table)

| `aspect_ratio` | Output pixels |
| -------------- | ------------- |
| `21:9`         | `1680x720`    |
| `16:9`         | `1280x720`    |
| `4:3`          | `960x720`     |
| `1:1`          | `720x720`     |
| `3:4`          | `720x960`     |
| `9:16`         | `720x1280`    |

### Flash modes

- **text** — `model` + `prompt` (+ optional seconds/size/aspect/seed). No
  first_frame, last_frame, images, audios, videos.
- **keyframe** — at least one of `first_frame` / `last_frame`. No
  images/audios/videos arrays.
- **reference** — at least one non-empty `images` or `audios` array. `images`
  max 5. `videos` never. Use `<Picture N>` / `<Audio N>` placeholder semantics
  in the prompt where appropriate.

### Flash create example

```bash
curl -X POST https://apihub.agnes-ai.com/v1/videos \
  -H "Authorization: Bearer $AGNES_AI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-2.5-flash",
    "prompt": "A cinematic shot of a cat walking on the beach at sunset",
    "mode": "text",
    "seconds": "5",
    "size": "720P",
    "aspect_ratio": "16:9",
    "seed": 42
  }'
```

### Flash retrieve — always include `model_name`

`video_id`-only retrieval is valid **only** for text mode. Keyframe and
reference tasks REQUIRE `&model_name=agnes-video-2.5-flash`. Use the consistent
safe form for every Flash task:

```bash
curl --location --request GET \
  'https://apihub.agnes-ai.com/agnesapi?video_id=<VIDEO_ID>&model_name=agnes-video-2.5-flash' \
  --header "Authorization: Bearer $AGNES_AI_API_KEY"
```

---

## PART B — AGNES VIDEO V2.0 (`agnes-video-v2.0`)

### Create Task Parameters — `POST /v1/videos`

| Parameter             | Type    | Required | Description |
| --------------------- | ------- | -------- | ----------- |
| `model`               | string  | **Yes**  | `agnes-video-v2.0` |
| `prompt`              | string  | **Yes**  | Text description of the video content |
| `image`               | string  | No       | Image URL for image-to-video |
| `mode`                | string  | No       | Such as `ti2vid` or `keyframes` |
| `width`               | integer | No       | Default `1152`. Normalized to nearest tier |
| `height`              | integer | No       | Default `768`. Normalized to nearest tier |
| `num_frames`          | integer | No       | **`<= 441`** and **`8n + 1`** (81, 121, 241, 441, ...) |
| `frame_rate`          | number  | No       | `1`–`60` |
| `num_inference_steps` | integer | No       | Inference steps |
| `seed`                | integer | No       | Reproducibility seed |
| `negative_prompt`     | string  | No       | Content to avoid |
| `extra_body.image`    | array   | No       | Input image URL array for **keyframe** workflows |
| `extra_body.mode`     | string  | No       | Such as `keyframes` |

### Choosing the V2.0 mode

- **Text-to-video / ti2vid** — `model` + `prompt` (+ optional size / frames).
- **Image-to-video** — add the top-level `image` string (a public URL).
- **Keyframe animation** — add `extra_body.image` (an ARRAY of public image
  URLs) and `extra_body.mode: "keyframes"`.

### V2.0 duration — frame-driven, no seconds enum

```
seconds = num_frames / frame_rate
```

- `num_frames` must be `<= 441` and on the `8n + 1` grid.
- `frame_rate` supports `1`–`60`.
- Examples at frame_rate 24: 81/24≈3s, 121/24≈5s, 241/24≈10s, 441/24≈18s.

### V2.0 normalization — the service maps your numbers

Resolutions: `480p` / `720p` / `1080p`. Ratios: `16:9`, `9:16`, `1:1`, `4:3`,
`3:4`.

The service normalizes any requested width/height/aspect that does not exactly
match a supported spec. Example (vendor): input `1024x576` was mapped to the
nearest preset `480p/16:9 (832x448)`.

> **Source of truth after normalization:** the request values may NOT match the
> render. When you display task info, compute duration, calculate cost, or debug
> output, use the returned `size`, `seconds`, and `metadata.size_mapping` fields
> — never the request.

### V2.0 create example (text-to-video)

```bash
curl -X POST https://apihub.agnes-ai.com/v1/videos \
  -H "Authorization: Bearer $AGNES_AI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-v2.0",
    "prompt": "A cinematic shot of a cat walking on the beach at sunset, soft ocean waves, warm golden lighting, realistic motion",
    "height": 768,
    "width": 1152,
    "num_frames": 121,
    "frame_rate": 24
  }'
```

### V2.0 retrieve

```bash
curl --location --request GET \
  'https://apihub.agnes-ai.com/agnesapi?video_id=<VIDEO_ID>' \
  --header "Authorization: Bearer $AGNES_AI_API_KEY"

# optional explicit model form:
curl --location --request GET \
  'https://apihub.agnes-ai.com/agnesapi?video_id=<VIDEO_ID>&model_name=agnes-video-v2.0' \
  --header "Authorization: Bearer $AGNES_AI_API_KEY"
```

Legacy-compatible by `task_id`:

```bash
curl --location --request GET \
  'https://apihub.agnes-ai.com/v1/videos/<TASK_ID>' \
  --header "Authorization: Bearer $AGNES_AI_API_KEY"
```

---

## Create Task Response (both models)

A successful create returns task info. The response includes BOTH `task_id` and
`video_id`. **`video_id` is the recommended id for retrieving the result.**

```json
{
  "id": "task_YOUR_TASK_ID",
  "task_id": "task_YOUR_TASK_ID",
  "video_id": "video_YOUR_VIDEO_ID",
  "object": "video",
  "model": "agnes-video-v2.0",
  "status": "queued",
  "progress": 0,
  "created_at": 1780457477,
  "seconds": "10.0",
  "size": "1280x768"
}
```

## Final Result Response

When the task is `completed`, the response carries the final video. The generated
URL is in `metadata.url`.

```json
{
  "id": "task_YOUR_TASK_ID",
  "video_id": "task_YOUR_TASK_ID",
  "task_id": "task_YOUR_TASK_ID",
  "object": "video",
  "model": "agnes-video-v2.0",
  "status": "completed",
  "progress": 100,
  "created_at": 1784530473,
  "completed_at": 1784530510,
  "seconds": "1.0",
  "size": "832x448",
  "metadata": {
    "size_mapping": {
      "adjusted": true,
      "height": 448,
      "message": "Input size 1024x576 was mapped to nearest preset 480p/16:9 (832x448)",
      "ratio": "16:9",
      "requested_height": 576,
      "requested_width": 1024,
      "resolution": "480p",
      "width": 832
    },
    "url": "https://platform-outputs.agnes-ai.space/videos/agnes-video-v2.0/task_YOUR_TASK_ID.mp4"
  }
}
```

| Field                   | Type          | Description                                                                 |
| ----------------------- | ------------- | --------------------------------------------------------------------------- |
| `id`                    | string        | Task ID. Works with the legacy query endpoint.                              |
| `video_id`              | string        | Video ID. **Recommended** for retrieving the result.                        |
| `task_id`               | string        | Task ID. Same purpose as `id`.                                              |
| `object`                | string        | Object type, usually `video`.                                               |
| `model`                 | string        | Model used for the task.                                                    |
| `status`                | string        | `queued` / `in_progress` / `completed` / `failed`.                          |
| `progress`              | integer       | Task progress percentage.                                                   |
| `created_at`            | integer       | Task creation timestamp.                                                    |
| `completed_at`          | integer       | Completion timestamp (present when done).                                   |
| `seconds`               | string        | Video duration in seconds.                                                  |
| `size`                  | string        | **Actual** output resolution after normalization.                           |
| `metadata`              | object        | Additional result metadata.                                                 |
| `metadata.url`          | string        | Final video URL. Present when `status` is `completed`.                     |
| `metadata.size_mapping` | object        | Normalization details: requested vs actual dimensions, ratio, tier.         |
| `error`                 | object / null | Error info if the task failed.                                              |

## Task Status

| Status        | Description                           |
| ------------- | ------------------------------------- |
| `queued`      | The task is waiting in the queue.     |
| `in_progress` | The video is being generated.         |
| `completed`   | The video was generated successfully. |
| `failed`      | The video generation task failed.     |

## Error Codes

| Status Code | Description                                    |
| ----------- | ---------------------------------------------- |
| `400`       | Invalid request (exact vendor messages above: `size must be 720P`, `images length must not exceed 5`, `videos is not supported`, invalid mode/media combo, duration, aspect ratio). |
| `401` / `403` | Bad or missing API key.                      |
| `404`       | Task or video not found.                       |
| `429`       | Rate limited (RPM or daily/weekly quota). Back off and retry. |
| `500`       | Server error.                                  |
| `503`       | Service is busy. Try again later.              |

## Polling Discipline

- Poll approximately **1–2 seconds** initially as vendor docs allow, then back
  off to a sane cadence while `queued` / `in_progress`.
- On HTTP `429` back off exponentially (RPM + daily/weekly quota both meter);
  treat `429` as the live ceiling — never hardcode a rate limit.
- Stop and report on `status: failed` (read `error`) or after a few minutes
  without completion.
- Download `metadata.url` promptly and store the file locally.

## Billing and Token Plan

| Model | List price | Current | Token plan |
|---|---|---|---|
| `agnes-video-2.5-flash` | `$0.025 / second` (720P) | `$0 / second` (limited-time free promo) | YES — 500 video-seconds/day, all tiers |
| `agnes-video-v2.0` | `$0.005 / second` | `$0 / second` | YES — 500 video-seconds/day, all tiers |
| `agnes-video-2.5` (full, non-flash) | `$0.025 / $0.040 / $0.055 / second` (720P / 960P / 2K) | same ("current same") | **NOT in token plan** |

> **NEVER auto-select `agnes-video-2.5`.** The token plan (tokenplan.md) lists
> ONLY `agnes-video-2.5-flash` and `agnes-video-v2.0`. Full 2.5 is pay-per-use
> and not in any tier. If something names `agnes-video-2.5`, stop and ask.

Prices are non-contractual reference values. Use the Agnes platform console as
the final source of truth for production planning.

## Prompt Cap — NOT PUBLISHED (both models)

The vendor publishes no prompt maximum for either model. The registry carries
`cap_status: "NOT_PUBLISHED"` and no invented cap. The BlackCEO house prompt
band (5,000 min / 9,000 target / 19,000 preferred) applies per spec 5.1 — but its
status is `PENDING_ACCEPTANCE_TEST` until an authorized boundary/smoke test
demonstrates the endpoint accepts it. Long prompts must add useful control
(spec 5.4), never padding.

## Integration Checklist

- [ ] Run `scripts/select_agnes_video_model.py` FIRST — model choice is not manual.
- [ ] Use `model_name=agnes-video-2.5-flash` on EVERY Flash retrieve (safe form).
- [ ] V2.0 retrieve: `video_id` (+ optional `model_name`); legacy `task_id` path exists.
- [ ] Flash `seconds` is a STRING `"4"`–`"12"`; `size` only `"720P"`.
- [ ] Flash `images` max 5; `videos` never; `n` only 1.
- [ ] V2.0 `num_frames <= 441` AND `8n+1`; `frame_rate` 1-60; `seconds = num_frames / frame_rate`.
- [ ] V2.0 normalization: read returned `size` / `seconds` / `metadata.size_mapping`.
- [ ] Video references: neither model supports them — route to KIE Video.
- [ ] The 6-image semantic guard: 6+ refs is NOT a V2.0 keyframe job automatically.
- [ ] Treat `429` as the live rate-limit signal; back off, do not hardcode a cap.
