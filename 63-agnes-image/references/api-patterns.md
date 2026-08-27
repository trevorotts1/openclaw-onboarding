# Agnes Image 2.1 Flash — API Patterns & Request Contract

Verification Date: 2026-08-26
Authority: First-party documentation (`https://wiki.agnes-ai.com/en/docs/agnes-image-21-flash.md`), Spec §10

---

## 1. Endpoint & Authentication

```text
POST https://apihub.agnes-ai.com/v1/images/generations
Authorization: Bearer $AGNES_AI_API_KEY
Content-Type: application/json
```

- Canonical environment variable name: `AGNES_AI_API_KEY` (keep this name across repo configs).
- Never echo, print, or log credential values.

---

## 2. Synchronous Execution

The Agnes Image endpoint is **SYNCHRONOUS**:
- A single `POST` request blocks until generation completes.
- The `200 OK` response payload contains the finished image directly (`data[0].url` or `data[0].b64_json`).
- There is **no task id** and **no polling endpoint** (`query_endpoint: null`).
- *Contrast with Agnes Video*: Video is asynchronous (create task, poll `/agnesapi?video_id=...`). Do not poll the image endpoint.

---

## 3. Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `model` | string | Yes | Must be `"agnes-image-2.1-flash"`. |
| `prompt` | string | Yes | Text instruction describing scene or edit. |
| `size` | string | Yes | Size tier: `"1K"`, `"2K"`, `"3K"`, or `"4K"`. Legacy `"WxH"` strings are accepted but may be normalized. |
| `ratio` | string | No | Aspect ratio: `"1:1"` (default), `"3:4"`, `"4:3"`, `"16:9"`, `"9:16"`, `"2:3"`, `"3:2"`, `"21:9"`. |
| `return_base64` | boolean | No | Top-level shortcut for T2I Base64 output. Set `true` to return Base64 in `data[0].b64_json`. |
| `extra_body` | object | No | Advanced parameters container. |
| `extra_body.response_format` | string | No | Output format: `"url"` (default) or `"b64_json"`. **MUST be inside extra_body, NEVER top-level.** |
| `extra_body.image` | array of strings | For I2I | Array of input reference images (public HTTPS URLs or Data-URI Base64). |

---

## 4. Critical Placement & Payload Rules

### A. `response_format` Placement
- `response_format` placed at the top level causes HTTP 400 rejection.
- It MUST be nested in `extra_body.response_format`.

### B. No `tags: ["img2img"]`
- Do NOT add `tags: ["img2img"]` or `tags` arrays.
- Passing `extra_body.image` is the sole and sufficient signal for image-to-image.

### C. `extra_body.image` Convention
- Accepts an array of strings:
  - Public HTTPS URLs: `["https://example.com/character-1.png", "https://example.com/character-2.png"]`
  - Data-URI Base64: `["data:image/png;base64,iVBORw0KGgoAAAANSUhEUg..."]`
- Multi-image inputs supported.

### D. Reference Image Counts & Pricing
- First 3 input reference images incur no extra fee at list pricing.
- 4th input image onward: list rate `$0.003 / image` (`max(0, count - 3) * $0.003`).
- Currently all input reference images are `$0` during promotional pricing.
- Maximum reference image count is **NOT PUBLISHED** by the vendor — do not invent a hard count rejection.

---

## 5. Output Dimension Matrix

Native output pixels for each `ratio` × `size` tier:

| Ratio | 1K | 2K | 3K | 4K |
|---|---|---|---|---|
| `1:1` | `1024x1024` | `2048x2048` | `3072x3072` | `4096x4096` |
| `3:4` | `864x1152` | `1728x2304` | `2592x3456` | `3456x4608` |
| `4:3` | `1152x864` | `2304x1728` | `3456x2592` | `4608x3456` |
| `16:9` | `1312x736` | `2624x1472` | `3936x2208` | `5248x2944` |
| `9:16` | `736x1312` | `1472x2624` | `2208x3936` | `2944x5248` |
| `2:3` | `832x1248` | `1664x2496` | `2496x3744` | `3328x4992` |
| `3:2` | `1248x832` | `2496x1664` | `3744x2496` | `4992x3328` |
| `21:9` | `1568x672` | `3136x1344` | `4704x2016` | `6272x2688` |

---

## 6. Response Shape

```json
{
  "created": 1780000000,
  "data": [
    {
      "url": "https://storage.googleapis.com/agnes-aigc/...",
      "b64_json": null,
      "revised_prompt": null
    }
  ]
}
```

- When `response_format: "url"`, image is in `data[0].url`.
- When `response_format: "b64_json"` (or `return_base64: true`), image is in `data[0].b64_json`.

---

## 7. Rate Limits & Error Handling

- **400 Bad Request**: Malformed payload, missing `model`/`prompt`/`size`, or top-level `response_format`.
- **401 / 403 Unauthorized**: Invalid or missing `AGNES_AI_API_KEY`.
- **429 Rate Limit**: Rate or quota ceiling hit. Back off exponentially. Treat 429 as authority.
- **500 / 503 Server Error**: Upstream transient error. Retry with backoff.

### Rate Limits by Tier (RPM)
- **1K**: Free 20 / Enterprise 40 / TokenPlan 100
- **2K**: Free 10 / Enterprise 20 / TokenPlan 80
- **3K**: Free 1 / Enterprise 1 / TokenPlan 1
- **4K**: Free 1 / Enterprise 1 / TokenPlan 1
- **Token Plan Quota**: 4,000 images per day across Starter, Plus, and Pro tiers.
- **Client Timeout**: Documented range 60–360 seconds.
