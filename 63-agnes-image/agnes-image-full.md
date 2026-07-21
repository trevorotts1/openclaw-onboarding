# Agnes Image 2.1 Flash — Full API Reference

The complete reference for the Agnes Image 2.1 Flash endpoint: model name,
endpoint, headers, every request parameter, the full output-dimension table,
working curl examples (text-to-image and image-to-image, URL and Base64), the
response shape, error handling, prompting guidance, the pricing/tier/rate-limit
model, and the credential.

Official docs index: https://wiki.agnes-ai.com/llms.txt

---

## At a Glance

| Field | Value |
|-------|-------|
| Model | `agnes-image-2.1-flash` |
| Endpoint | `POST https://apihub.agnes-ai.com/v1/images/generations` |
| Pattern | SYNCHRONOUS — one request, one response with the finished image |
| Auth | `Authorization: Bearer <AGNES_AI_API_KEY>` |
| Output | image URL (`data[0].url`) or Base64 (`data[0].b64_json`) |
| Price | currently `$0 / image` (standard reference rate `$0.003 / image`) |

Agnes Image 2.1 Flash supports text-to-image and image-to-image. Compared with
version 2.0 it is tuned for high-information-density images: complex
compositions, dense detail, and stronger prompt/semantic alignment. During
image-to-image it preserves the original composition and subject layout as much
as possible.

**The image endpoint is synchronous.** Unlike a "create a task, then poll for
the result" API (Skill 07 / KIE.ai, and the separate Agnes VIDEO endpoint), the
image call returns the finished image in the same HTTP response. Do not write a
polling loop for it.

---

## Endpoint

```text
POST https://apihub.agnes-ai.com/v1/images/generations
```

### Headers

```bash
-H "Authorization: Bearer YOUR_API_KEY"
-H "Content-Type: application/json"
```

`YOUR_API_KEY` is the value of `AGNES_AI_API_KEY` (see "Credential" below).
Never place a real key in shared docs, commits, or logs.

---

## Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | Yes | Model name. Use `agnes-image-2.1-flash`. |
| `prompt` | string | Yes | Text instruction for generation or editing. |
| `size` | string | Yes | Output size TIER. Recommended: `1K`, `2K`, `3K`, `4K`. Legacy exact sizes such as `1024x768` are accepted, but unsupported exact sizes may be normalized to the nearest tier. |
| `ratio` | string | No | Aspect ratio, paired with a tier `size`. One of `1:1`, `3:4`, `4:3`, `16:9`, `9:16`, `2:3`, `3:2`, `21:9`. Default `1:1`. |
| `image` | string[] | For image-to-image | Input image array. Public image URLs or Data-URI Base64. (Also accepted under `extra_body.image` — see the img2img section.) |
| `return_base64` | boolean | No | Top-level shortcut for text-to-image Base64 output. |
| `extra_body` | object | No | Container for advanced parameters. |
| `extra_body.response_format` | string | No | Output format: `"url"` or `"b64_json"`. **This is where response_format belongs — NOT the top level.** |
| `extra_body.image` | string[] | For image-to-image | Input image array for image-to-image (URL or Data-URI Base64). |

### The two gotchas

1. **`response_format` lives in `extra_body`, never at the top level.** A
   top-level `response_format` is rejected. Correct: `extra_body.response_format:
   "url"` (or `"b64_json"`).
2. **Image-to-image requires NO `tags`.** Do not send `tags: ["img2img"]`.
   Providing the input image array (in `extra_body.image`) is the only signal
   the endpoint needs.

---

## Size and Ratio

For predictable output dimensions, use a tier `size` together with a `ratio`.

- Recommended `size` tiers: `1K`, `2K`, `3K`, `4K`.
- Supported `ratio` values: `1:1`, `3:4`, `4:3`, `16:9`, `9:16`, `2:3`, `3:2`,
  `21:9`.
- If you request an unsupported EXACT size such as `1920x1080` or `2560x1440`,
  the service may map it to the nearest supported tier and aspect ratio. For
  example, an unsupported 16:9 request can normalize to the `16:9` `1K` output
  size `1312x736`.
- For common 16:9 display assets (`1920x1080`, `2560x1440`), request
  `size: "2K"` with `ratio: "16:9"` (native `2624x1472`) and crop/resize
  downstream to the exact canvas you need.

### Output Dimension Reference

Exact output pixels for each ratio × tier:

| Ratio | 1K | 2K | 3K | 4K |
|-------|-----|-----|-----|-----|
| `1:1` | `1024x1024` | `2048x2048` | `3072x3072` | `4096x4096` |
| `3:4` | `864x1152` | `1728x2304` | `2592x3456` | `3456x4608` |
| `4:3` | `1152x864` | `2304x1728` | `3456x2592` | `4608x3456` |
| `16:9` | `1312x736` | `2624x1472` | `3936x2208` | `5248x2944` |
| `9:16` | `736x1312` | `1472x2624` | `2208x3936` | `2944x5248` |
| `2:3` | `832x1248` | `1664x2496` | `2496x3744` | `3328x4992` |
| `3:2` | `1248x832` | `2496x1664` | `3744x2496` | `4992x3328` |
| `21:9` | `1568x672` | `3136x1344` | `4704x2016` | `6272x2688` |

---

## Request Examples

### Text-to-image → URL output

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "A luminous floating city above a misty canyon at sunrise, cinematic realism, wide-angle composition, rich architectural details, soft golden light, high visual density",
    "size": "2K",
    "ratio": "16:9",
    "extra_body": {
      "response_format": "url"
    }
  }'
```

Returns the `16:9` `2K` output size, `2624x1472`, at `data[0].url`.

### Text-to-image → Base64 output (top-level shortcut)

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "A clean product photo of a glass cube on a white studio background, soft shadows, high detail",
    "size": "1K",
    "ratio": "1:1",
    "return_base64": true
  }'
```

The image comes back at `data[0].b64_json`.

### Image-to-image → URL input + URL output

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "Transform the scene into a rain-soaked cyberpunk night with neon reflections while preserving the original composition",
    "size": "2K",
    "ratio": "16:9",
    "extra_body": {
      "image": [
        "https://example.com/input-image.png"
      ],
      "response_format": "url"
    }
  }'
```

### Image-to-image → Base64 output

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "Make the object matte black while preserving the original composition",
    "size": "1K",
    "extra_body": {
      "image": [
        "https://example.com/input-image.png"
      ],
      "response_format": "b64_json"
    }
  }'
```

### Image-to-image → Data-URI Base64 input

When the input image is not reachable at a public URL, pass it inline as a
Data URI in `extra_body.image`:

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "Make the object orange while preserving the original composition",
    "size": "1K",
    "extra_body": {
      "image": [
        "data:image/png;base64,BASE64_HERE"
      ],
      "response_format": "b64_json"
    }
  }'
```

---

## Response Format

### URL output

```json
{
  "created": 1780000000,
  "data": [
    {
      "url": "https://storage.googleapis.com/agnes-aigc/xxx.png",
      "b64_json": null,
      "revised_prompt": null
    }
  ]
}
```

Generated image path: `data[0].url`.

### Base64 output

```json
{
  "created": 1780000000,
  "data": [
    {
      "url": null,
      "b64_json": "iVBORw0KGgoAAAANSUhEUgAA...",
      "revised_prompt": null
    }
  ]
}
```

Generated image path: `data[0].b64_json`.

### Response fields

| Field | Type | Description |
|-------|------|-------------|
| `created` | integer | Request creation timestamp. |
| `data` | array | List of generated image results. |
| `data[].url` | string / null | Generated image URL. Usually `null` when using Base64 output. |
| `data[].b64_json` | string / null | Base64 image data. Usually `null` when using URL output. |
| `data[].revised_prompt` | string / null | Revised prompt if available, else `null`. |

Download URL-output images promptly and store them locally — hosted URLs are not
guaranteed to be permanent.

---

## Prompting Guide

**Text-to-image structure:**

```text
[Subject] + [Scene / Environment] + [Style] + [Lighting] + [Composition] + [Quality Requirements]
```

Example:

```text
A luminous floating city above a misty canyon at sunrise, cinematic realism, wide-angle composition, rich architectural details, soft golden light, high visual density
```

**Image-to-image structure** — say clearly what CHANGES and what stays the same:

```text
[Change Request] + [New Style / Scene] + [Elements to Add or Remove] + [Elements to Preserve]
```

Example:

```text
Turn the daytime street scene into a cinematic cyberpunk night scene, add neon signs and wet road reflections, while preserving the original street layout, camera angle, and main building shapes.
```

**High-information-density images** — this model is tuned for dense, complex
visuals. Describe the visual hierarchy: main subject, background environment,
important secondary details, style and lighting, composition constraints, and
(for image-to-image) the elements to preserve.

---

## Common Errors and Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Request rejected on `response_format` | `response_format` placed at the top level | Move it into `extra_body.response_format`. |
| Image-to-image ignored / unexpected result | Missing input image array | Provide `extra_body.image` (URL or Data-URI Base64). Do NOT add `tags`. |
| Input image URL cannot be accessed | URL needs login, cookies, or private headers | Use a public HTTPS URL, or pass the image as Data-URI Base64. |
| Output size not what you requested | Unsupported exact size normalized to nearest tier | Use a tier `size` (`1K`..`4K`) + `ratio`, then read the exact pixels from the dimension table. |
| Request timeout | Large size / complex prompt / server load | Use a client timeout of 60s–360s. |
| HTTP 401 | Missing or wrong API key | Confirm `AGNES_AI_API_KEY` is set and passed as `Authorization: Bearer`. |
| HTTP 429 | Rate/quota limit for the account tier | Back off (exponential) and retry. Treat 429 as the live ceiling — see below. |

Do NOT place `response_format` at the top level:

```json
// WRONG
{ "model": "agnes-image-2.1-flash", "prompt": "A futuristic city", "size": "1K", "response_format": "url" }

// CORRECT
{ "model": "agnes-image-2.1-flash", "prompt": "A futuristic city", "size": "1K", "extra_body": { "response_format": "url" } }
```

---

## Pricing, Tiers, and Rate Limits

There are TWO separate pricing axes on the Agnes platform. Do not conflate them.

### Axis 1 — per-unit usage price

Image generation is currently a promotional `$0 / image`. The standard
(non-promotional) reference rate is `$0.003 / image`. Using the model today
costs nothing per image.

| Type | Standard Price | Current Price |
|------|----------------|---------------|
| Image generation | `$0.003 / image` | `$0 / image` |

### Axis 2 — access tier and rate limits

Separately from per-unit price, Agnes meters on TWO simultaneous dimensions:

- **Requests-per-minute (RPM)** — set by ACCESS TYPE (free/default,
  enterprise-verified, or a paid Token Plan).
- **Daily / weekly quotas** — set only when the account is on a paid Token Plan.
  Free/default accounts have NO published daily image quota; they are
  RPM-throttled only.

The published reference values below are dated **2026-06-28** (source:
AgnesAI-Labs/AgnesAI-Models `MODEL_CATALOG.md` + `docs/TOKEN_PLAN_FAQ.md`). The
vendor explicitly labels these as **current reference values, not permanent
contractual limits**, and names the account console (Usage / Billing) as the
final source of truth. Numbers have already moved inside a 6-day window. **Do
not hardcode any of these into skill logic.**

Image RPM (public / actual requests-per-minute), by access type:

| Access type | 1K | 2K | 3K | 4K |
|-------------|-----|-----|-----|-----|
| Free / default | 30 / 20 | 20 / 10 | 2 / 1 | 1 / 1 |
| Enterprise-verified | 60 / 40 | 40 / 20 | 2 / 1 | 2 / 1 |
| Token Plan (any paid tier) | 120 / 100 | 120 / 80 | 2 / 1 | 2 / 1 |

Paid Token Plan tiers (per-day image quota is IDENTICAL across all three — paying
up buys RPM/text quota, NOT extra image volume):

| Tier | Price (billing period UNVERIFIED) | Images / day | Video seconds / day |
|------|-----------------------------------|--------------|---------------------|
| Starter | `$4` | 4,000 | 500 |
| Plus | `$10` | 4,000 | 500 |
| Pro | `$50` | 4,000 | 500 |

Notes on the unverified cells:

- The **billing period** for `$4` / `$10` / `$50` (monthly vs one-time) is
  UNVERIFIED — the catalog lists bare dollar amounts with no period.
- Whether **enterprise verification** carries any fee is UNVERIFIED (it is
  granted by verification, not published as a purchase).
- There is NO `$40` tier and NO `$100` tier. The real ladder is `$4` / `$10` /
  `$50`.

### How to treat limits in practice

1. **Read the account's tier from operator-set config, not from this doc.**
   Which tier a given box is on (free / enterprise / token-starter / -plus /
   -pro) is an ACCOUNT property this reference cannot know statically. If a box
   needs tier-aware behavior, key it off an operator-set value (for example an
   `AGNES_TIER` env), seeded from the dated table above and clearly stamped with
   its 2026-06-28 source date — never a bare constant buried in code.
2. **Treat HTTP 429 as the live source of truth.** Agnes meters RPM AND daily
   quota at once; a static number cannot capture both, but a 429 handler with
   exponential backoff always can.
3. **Point at the console for production planning.** The account dashboard
   (Usage / Billing) is the vendor's stated final authority.
4. **Cost insight for media workloads:** all three paid tiers give the same
   4,000 images/day and 500 video-seconds/day and share one Token-Plan RPM pool.
   Only the text-model request quota scales with tier. For an image/video
   workload, `$50` Pro buys ZERO extra image throughput over `$4` Starter — do
   not overpay for image volume.

---

## Credential

- Variable: `AGNES_AI_API_KEY`.
- This is an EXISTING fleet credential — the same key the registered `agnes` /
  `agnes-2.0-flash` model on the boxes already uses against
  `apihub.agnes-ai.com/v1`. This skill REFERENCES it; it does not create a new
  one.
- It rides the `Authorization: Bearer <AGNES_AI_API_KEY>` header on every call.
- Verify it is SET only. NEVER echo, cat, print, or log the value. Never place a
  real key in any doc, commit, or chat.

---

## Sources

- Operator reference: Agnes Image 2.1 Flash documentation (endpoint, parameters,
  output-dimension table, examples, pricing).
- Rate-limit / tier values (dated 2026-06-28): AgnesAI-Labs/AgnesAI-Models
  `MODEL_CATALOG.md` and `docs/TOKEN_PLAN_FAQ.md`;
  https://wiki.agnes-ai.com/en/docs/faqs (free users are RPM-metered; read your
  own quota from the dashboard under Usage or Billing).
- Docs index: https://wiki.agnes-ai.com/llms.txt
