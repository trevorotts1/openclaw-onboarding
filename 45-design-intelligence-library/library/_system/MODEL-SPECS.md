# MODEL SPECS — API Limits, Routing & Request Templates
**Version:** 1.3 | **Last Updated:** 2026-06-14 | **Source:** Verified Kie.ai API documentation (not blog estimates)
**Audience:** AI agents. This is the ONLY file that changes when models update. Style cards never reference model versions directly — they reference tiers and capabilities defined here.

---

## 1. THE MODEL ROSTER (verified specs — 7 endpoints)

| # | Endpoint | Kie.ai model ID | Prompt limit | Negative prompt | Reference images | Resolutions | Notes |
|---|---|---|---|---|---|---|---|
| 1a | **GPT-Image 2 — Text-to-Image** | `gpt-image-2-text-to-image` | **20,000 chars** | No (inline only) | None | 1K / 2K / 4K | Layout king, longest prompts |
| 1b | **GPT-Image 2 — Image-to-Image** | `gpt-image-2-image-to-image` | **20,000 chars** | No (inline only) | `input_urls`, optional, multiple, **30MB each** (jpeg/png/webp/jpg) | 1K / 2K / 4K | Long prompts + refs combined |
| 2 | **Nano Banana 2** (Gemini 3.1 Flash Image) | `nano-banana-2` | **20,000 chars** | No (inline only) | `image_input`, optional, **up to 14**, 30MB each | 1K / 2K / 4K | jpg/png output; ultra-wide ratios |
| 3a | **Seedream 4.5 — Text-to-Image** | `seedream/4.5-text-to-image` | **3,000 chars** | No (inline only) | None | basic = 2K, high = 4K | `aspect_ratio` REQUIRED |
| 3b | **Seedream 4.5 — Edit** | `seedream/4.5-edit` | **3,000 chars** | No (inline only) | `image_urls` **REQUIRED**, multiple, 10MB each | basic = 2K, high = 4K | Edit-instruction phrasing |
| 4 | **Ideogram V3** | `ideogram/v3-text-to-image` | **5,000 chars** | **YES — `negative_prompt`, 5,000 chars** | None | image_size presets | Typography engine |
| 5 | **Wan 2.7** | `wan/2-7-image` | **5,000 chars** | No (inline only) | `input_urls`, optional, 10MB each | 1K / 2K | n=1–4 batch, seed |

> **Note:** the 7 endpoints above are all GENERATION endpoints (they output images) and share the `jobs/createTask` lifecycle in Section 5. There is a separate, non-generation **image-to-JSON / vision-analysis** capability documented in Section 1B + Section 5.8 below: it INGESTS an image and returns structured text/JSON, used by Workflow A (analyze an image to a style card).

### Aspect ratio support (critical for routing)

| Endpoint | Supported ratios |
|---|---|
| GPT-Image 2 (both T2I and I2I) | auto, 1:1, 3:2, 2:3, 4:3, 3:4, 5:4, 4:5, 16:9, 9:16, 2:1, 1:2, 3:1, 1:3, 21:9, 9:21 |
| Nano Banana 2 | auto, 1:1, **1:4, 4:1, 1:8, 8:1** (ultra-wide!), 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9 |
| Seedream 4.5 (both T2I and Edit) | 1:1, 4:3, 3:4, 16:9, 9:16, 2:3, 3:2, 21:9 — **required parameter, no auto** |
| Ideogram V3 | Presets only: square, square_hd, portrait_4_3, portrait_16_9, landscape_4_3, landscape_16_9 |
| Wan 2.7 | 1:1, 3:4, 4:3, 1:8, 8:1, 9:16, 16:9, 21:9 |

---

## 1B. IMAGE-TO-JSON (VISION ANALYSIS) MODE: image in, structured style JSON out

This is the THIRD Kie.ai mode, alongside text-to-image (T2I) and image-to-image (I2I). It does NOT generate an image; it **reads** an input image with a multimodal model and returns a structured description. It is the machine path for **Workflow A** (analyze an image to a style card): instead of (or alongside) the agent eyeballing the image, you can POST the image to Kie.ai's multimodal chat endpoint and ask for the 12 style dimensions back as JSON, then map that JSON into `STYLE-CARD-TEMPLATE.md`.

**Verified against live Kie.ai docs (`docs.kie.ai/market/chat/gpt-5-2`, fetched 2026-06-14), NOT guessed:**

| Property | Value |
|---|---|
| Mode | Vision / image-understanding (multimodal chat completion): image IN, text/JSON OUT |
| Endpoint | `POST https://api.kie.ai/gpt-5-2/v1/chat/completions` |
| Lifecycle | **Synchronous chat-completions** (request → response in one call). This is NOT the `jobs/createTask` + `recordInfo` polling lifecycle the generation endpoints use. |
| Model ID | `gpt-5-2` (multimodal: accepts text + image input; backup options: other `gpt-5-*` chat models in the `docs.kie.ai/market/chat/` family; confirm the exact slug in live docs before substituting) |
| Auth | `Authorization: Bearer {API_KEY}` (same KIE_API_KEY as the generation endpoints) |
| Image input | inside `messages[].content[]` as an item `{"type": "image_url", "image_url": {"url": "{IMAGE_URL}"}}`. Multiple images = multiple `image_url` items in the same `content` array. |
| Text instruction | a sibling content item `{"type": "text", "text": "{ANALYSIS_INSTRUCTION}"}` in the same array. |
| Structured output | The Kie.ai chat docs do **NOT** document an OpenAI-style `response_format` / `json_schema` parameter. Get JSON by INSTRUCTING the model in the text item ("Return ONLY valid JSON matching this schema: ..."), then parse `choices[0].message.content`. Do not pass `response_format` unless live docs add it; passing an undocumented field can be rejected. |
| Where the answer lives | `choices[0].message.content` (a string; parse it as JSON when you asked for JSON). |
| Usage accounting | `usage.prompt_tokens` / `completion_tokens` / `total_tokens` in the response. |

**When to use it:** an operator hands you a reference image/deck and there is no registered style for it (INSTRUCTIONS.md job 2, branch c/d). Route to the Style Analyst, who may use this mode to bootstrap the 12-dimension read, then still applies MASTER-SOP judgment and writes/tests the card. The agent's own multimodal vision remains a valid alternative; this mode is the API-driven option for batch or headless analysis.

**Hard rules:**
- This mode produces a STYLE CARD DRAFT, never a final card. The Style Analyst still fills `STYLE-CARD-TEMPLATE.md` and runs `TEST-PROTOCOL.md`.
- It NEVER edits an existing card (Workflow B / model-update rules unchanged).
- Verify the model slug and request shape against live `docs.kie.ai` before each library version bump; chat model ids rev faster than the image endpoints.

---

## 2. MODEL ROUTING TABLE

> **PRESENTATIONS MODEL SOVEREIGNTY:** For client presentation decks, the model is PINNED in the client's intake.json (field: `model_pin`). The canonical primary is `gpt-image-2-text-to-image` (text-to-image) or `gpt-image-2-image-to-image` (with reference images). The routing table below applies to ALL OTHER use cases. For presentations, `nano-banana-2` is FALLBACK-ONLY and requires a logged hard API failure event. See CLIENT-WEBINAR-DECK-SOP.md Section 1A and AF-MODEL-SOVEREIGNTY.

Choose by task. Category `_RULES.md` files may override.

| Task | First choice | Backup | Why |
|---|---|---|---|
| Text-heavy design (book cover, magazine cover, banner with copy) | GPT-Image 2 T2I (LONG tier) | Nano Banana 2 | 20K chars specs every text element; strongest layout adherence |
| **Text-heavy design FROM a style reference image** | **GPT-Image 2 I2I (LONG tier + refs)** | Nano Banana 2 | The only combo of 20K prompt + reference images + full layout control |
| Design built around typography as the art | Ideogram V3, `style: "DESIGN"` | GPT-Image 2 T2I | Purpose-built typographic engine + true negative_prompt |
| **Ultra-wide banners (8:1, 4:1)** | **Nano Banana 2 — ONLY option** (Wan 2.7 backup for 8:1) | — | Only models supporting ultra-wide ratios |
| Style transfer FROM multiple references | Nano Banana 2 (up to 14 refs) | GPT-Image 2 I2I | Reference capacity |
| Editing/iterating an existing generated image | Seedream 4.5 Edit | GPT-Image 2 I2I | Built as a unified edit model; GPT I2I when the edit needs a long spec |
| **Surgical edits on a real photo (retouching, wardrobe swap, single-element change)** | **Seedream 4.5 Edit — only true editor** | GPT-Image 2 I2I (expect more drift) | See Editing Hierarchy note below |
| Personal Photo Shoot — new identity-locked scenes | Nano Banana 2 (multi-ref) | GPT-Image 2 I2I | Per PHOTO-SHOOT-SOP routing |
| Photorealistic people / portraits | Nano Banana 2 | GPT-Image 2 T2I | Strong skin/lighting fidelity |
| Fast clean T2I drafts at 2K, short prompts | Seedream 4.5 T2I (SHORT/MEDIUM) | Wan 2.7 | Quality-per-character efficiency |
| Volume draft runs (many variants, seed control) | Wan 2.7 (n=1–4 per call) | Nano Banana 2 @1K | Batch + seed reproducibility |
| Complex multi-element ad layouts | GPT-Image 2 T2I | Nano Banana 2 | Scene composition strength |

### THE EDITING HIERARCHY (important)
**Seedream 4.5 Edit is the only endpoint in this roster that performs true surgical image editing** — change the named element while genuinely preserving everything else. GPT-Image 2 I2I and Nano Banana 2 *can* modify images, but they lean toward regeneration: expect drift in untouched areas, especially faces. Routing rule: if the task is "change X on THIS photo, keep the rest," it goes to Seedream 4.5 Edit unless the instruction won't fit in 3,000 chars. This matters most for Personal Photo Shoot retouching (PHOTO-SHOOT-SOP §6).

## 3. TIER ↔ ENDPOINT COMPATIBILITY

| Tier | Budget | GPT-Image 2 (T2I + I2I) | Nano Banana 2 | Seedream 4.5 (T2I + Edit) | Ideogram V3 | Wan 2.7 |
|---|---|---|---|---|---|---|
| SHORT | ≤500 | ✅ | ✅ | ✅ | ✅ | ✅ |
| MEDIUM | ≤2,800 | ✅ | ✅ | ✅ (3,000 cap) | ✅ (5,000 cap) | ✅ (5,000 cap) |
| LONG | ≤18,000 | ✅ (20,000 cap) | ✅ (20,000 cap) | ❌ | ❌ | ❌ |

**Rule:** If a LONG-tier generation is requested on an endpoint that can't take it, automatically fall back to MEDIUM and tell the operator.

---

## 4. MODEL-SPECIFIC PROMPTING NOTES

### GPT-Image 2 (T2I and I2I)
- Handles long, structured prompts better than short ones — LONG tier is its home.
- T2I endpoint: everything must be in words.
- **I2I endpoint: refs are optional.** When passing refs for STYLE (not editing), the style-reference-only directive is MANDATORY (see Nano Banana 2 note below — same directive, same reason).
- Negatives go inline as "Do not..." sentences in the final paragraph.

### Nano Banana 2
- Up to 14 reference images. For style work: pass 1–3 refs labeled in the prompt as STYLE REFERENCE ONLY: *"Use the attached images only as style reference for color grading, lighting, and composition — do not copy their subjects, faces, or text."* This sentence is MANDATORY whenever refs are attached for style (prevents verbatim copying — a known failure mode from past work). **Applies equally to GPT-Image 2 I2I.**
- The ultra-wide specialist (8:1, 4:1, 1:8, 1:4). All banner work routes here.
- `output_format`: use `png` for anything with text or that needs further editing; `jpg` for final photographs.

### Seedream 4.5 (T2I and Edit)
- 3,000-char ceiling on BOTH endpoints: MEDIUM tier max. Be surgical with characters.
- `aspect_ratio` is REQUIRED on both endpoints — there is no auto. Always set it explicitly.
- **T2I endpoint** (`seedream/4.5-text-to-image`): no reference input. Best draft-to-quality ratio for short, well-engineered prompts.
- **Edit endpoint** (`seedream/4.5-edit`): `image_urls` REQUIRED. Edit-instruction phrasing works best: "Keep X unchanged. Change Y to Z." Lead with what to PRESERVE, then what to change.
- `quality`: `basic` = 2K (drafts), `high` = 4K (production).

### Ideogram V3
- **ALWAYS set `expand_prompt: false` for style-card generations.** MagicPrompt rewrites prompts and destroys engineered style fidelity. Only allow `true` for exploratory ideation.
- Use `style: "DESIGN"` for graphic-design work, `"REALISTIC"` for photographic styles.
- The ONLY model with a true `negative_prompt` field — put the card's full avoid-list there (up to 5,000 chars).
- `rendering_speed`: `QUALITY` for production, `TURBO` for drafts.
- `seed`: record it on successful generations for reproducibility.
- Aspect ratios are fixed presets — check the card's ratio maps to an available preset before routing here.

### Wan 2.7
- `n` = 1–4 images per call: the variant-exploration workhorse.
- `thinking_mode: true` improves quality but only works with no input images and gallery mode off.
- `seed` supported: same seed + same prompt = stable output. Record seeds for winners.
- `watermark`: ALWAYS set `false` for client deliverables.

---

## 5. READY-TO-SEND JSON TEMPLATES (Kie.ai)

All GENERATION endpoints (5.1–5.7) share the same task lifecycle:
1. `POST https://api.kie.ai/api/v1/jobs/createTask` with `Authorization: Bearer {API_KEY}`
2. Extract `data.taskId`
3. Poll `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId={taskId}` (or use `callBackUrl`)
4. When `state` = `success`, image URL(s) are in `resultJson.resultUrls`

> **Exception:** the image-to-JSON / vision-analysis template (5.8) does NOT use this lifecycle. It is a synchronous chat-completions call to a different endpoint; see Section 1B.

### 5.1 GPT-Image 2 — Text-to-Image
```json
{
  "model": "gpt-image-2-text-to-image",
  "input": {
    "prompt": "{ASSEMBLED_PROMPT — up to 20000 chars}",
    "aspect_ratio": "{ASPECT_RATIO}",
    "resolution": "2K"
  },
  "callBackUrl": "{OPTIONAL_WEBHOOK}"
}
```

### 5.2 GPT-Image 2 — Image-to-Image (refs optional)
```json
{
  "model": "gpt-image-2-image-to-image",
  "input": {
    "prompt": "{ASSEMBLED_PROMPT — up to 20000 chars. If refs are for style, MUST include the style-reference-only directive.}",
    "input_urls": ["{REF_URL_1}", "{REF_URL_2}"],
    "aspect_ratio": "{ASPECT_RATIO}",
    "resolution": "2K"
  },
  "callBackUrl": "{OPTIONAL_WEBHOOK}"
}
```

### 5.3 Nano Banana 2 (text-to-image or with style refs)
```json
{
  "model": "nano-banana-2",
  "input": {
    "prompt": "{ASSEMBLED_PROMPT — up to 20000 chars. If image_input present, MUST include the style-reference-only directive.}",
    "image_input": ["{OPTIONAL_REF_URL_1}", "{OPTIONAL_REF_URL_2}"],
    "aspect_ratio": "{ASPECT_RATIO}",
    "resolution": "2K",
    "output_format": "png"
  },
  "callBackUrl": "{OPTIONAL_WEBHOOK}"
}
```

### 5.4 Seedream 4.5 — Text-to-Image (aspect_ratio REQUIRED)
```json
{
  "model": "seedream/4.5-text-to-image",
  "input": {
    "prompt": "{ASSEMBLED_PROMPT — up to 3000 chars, SHORT or MEDIUM tier only}",
    "aspect_ratio": "{ASPECT_RATIO — required, no auto}",
    "quality": "high",
    "nsfw_checker": true
  },
  "callBackUrl": "{OPTIONAL_WEBHOOK}"
}
```

### 5.5 Seedream 4.5 — Edit (image_urls REQUIRED)
```json
{
  "model": "seedream/4.5-edit",
  "input": {
    "prompt": "{EDIT_PROMPT — up to 3000 chars. Lead with what to keep, then what to change.}",
    "image_urls": ["{SOURCE_IMAGE_URL}"],
    "aspect_ratio": "{ASPECT_RATIO — required, no auto}",
    "quality": "high",
    "nsfw_checker": true
  },
  "callBackUrl": "{OPTIONAL_WEBHOOK}"
}
```

### 5.6 Ideogram V3 (typography-first)
```json
{
  "model": "ideogram/v3-text-to-image",
  "input": {
    "prompt": "{ASSEMBLED_PROMPT — up to 5000 chars}",
    "rendering_speed": "QUALITY",
    "style": "DESIGN",
    "expand_prompt": false,
    "image_size": "{PRESET — e.g. landscape_16_9}",
    "seed": "{OPTIONAL_INT}",
    "negative_prompt": "{CARD_AVOID_LIST — up to 5000 chars}",
    "nsfw_checker": true
  },
  "callBackUrl": "{OPTIONAL_WEBHOOK}"
}
```

### 5.7 Wan 2.7 (variants / drafts)
```json
{
  "model": "wan/2-7-image",
  "input": {
    "prompt": "{ASSEMBLED_PROMPT — up to 5000 chars}",
    "n": 4,
    "enable_sequential": false,
    "resolution": "2K",
    "thinking_mode": true,
    "aspect_ratio": "{ASPECT_RATIO}",
    "watermark": false,
    "seed": "{OPTIONAL_INT}",
    "nsfw_checker": true
  },
  "callBackUrl": "{OPTIONAL_WEBHOOK}"
}
```

### 5.8 Image-to-JSON / vision analysis (image in → structured style JSON out)

**Different endpoint, different lifecycle** (synchronous chat-completions, no `createTask`/`recordInfo` polling). See Section 1B. Verified against `docs.kie.ai/market/chat/gpt-5-2`.

`POST https://api.kie.ai/gpt-5-2/v1/chat/completions` with header `Authorization: Bearer {API_KEY}`:

```json
{
  "model": "gpt-5-2",
  "messages": [
    {
      "role": "system",
      "content": "You are a design style analyst. Extract the transferable STYLE of the attached image across the 12 dimensions. Return ONLY valid JSON, no prose."
    },
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "Analyze this image and return JSON with keys: render, composition, subject_treatment, color_palette, color_grading, lighting, typography, layering, subject_background, negative_space, workflow_notes, unifying_dna. Each value is a concise style description. Describe STYLE only, never the specific content/subject."
        },
        {
          "type": "image_url",
          "image_url": { "url": "{IMAGE_URL}" }
        }
      ]
    }
  ],
  "reasoning_effort": "high"
}
```

**Reading the result:** the JSON string is in `choices[0].message.content`. Parse it, then map each key into `STYLE-CARD-TEMPLATE.md`. This is a DRAFT input to Workflow A; the Style Analyst still completes and tests the card.

**Notes:**
- `reasoning_effort` accepts `"high"` for thorough analysis; lower it for speed. `tools` (e.g. `web_search`) is optional and not needed for pure image analysis.
- Pass additional `image_url` items in the same `content` array to analyze a small batch in one call (e.g. a 3-slide sample of a deck); for full decks use Deck Systems Specialist + PPT-ANALYSIS-SOP.
- Do NOT add `response_format`/`json_schema`; not documented for this Kie.ai endpoint as of 2026-06-14. Enforce JSON by instruction + parse-and-retry, not by an undocumented parameter.

---

## 6. ADDING A NEW MODEL (future-proofing protocol)

When a new model or endpoint becomes available (e.g., GPT-Image 3, Nano Banana 3, Seedream 5.x on Kie.ai):
1. Obtain the actual API doc. Record: model ID, prompt char limit, negative prompt support, reference image support/count/size, aspect ratios, resolutions, required vs optional parameters, special parameters.
2. Add a row to the roster table (Section 1) and aspect-ratio table.
3. Update the routing table (Section 2) if the new endpoint wins any task category.
4. Update tier compatibility (Section 3).
5. Add a prompting-notes block (Section 4) and JSON template (Section 5).
6. Bump this file's version and date, and log the change below.
7. **Do NOT touch any style card.** Cards are model-agnostic by design.

## 7. CHANGELOG
| Date | Version | Change |
|---|---|---|
| 2026-06-12 | v1.0 | Initial: 5 endpoints (GPT-Image 2 T2I, Nano Banana 2, Seedream 4.5 Edit, Ideogram V3, Wan 2.7) |
| 2026-06-12 | v1.1 | Added GPT-Image 2 Image-to-Image (20K + refs 30MB) and Seedream 4.5 Text-to-Image (3K, ratio required). Updated routing: GPT I2I now first choice for text-heavy style-reference work; Seedream T2I added as fast-draft option. Style-reference-only directive extended to GPT I2I. |
| 2026-06-12 | v1.2 | Added Editing Hierarchy (Seedream 4.5 Edit = only true surgical editor) and Personal Photo Shoot routing rows. |
| 2026-06-14 | v1.3 | Documented the THIRD mode: image-to-JSON / vision analysis (Section 1B + template 5.8). Synchronous chat-completions endpoint `POST https://api.kie.ai/gpt-5-2/v1/chat/completions`, model `gpt-5-2`, image via `messages[].content[].image_url`, answer at `choices[0].message.content`. Verified against live `docs.kie.ai/market/chat/gpt-5-2`; no `response_format`/`json_schema` documented (JSON by instruction). Powers Workflow A image-to-style-card. No style cards touched. |
| 2026-06-14 | v1.4 | Added CLIENT SOVEREIGNTY note to MODEL ROUTING TABLE: presentations always use gpt-image-2-text-to-image or gpt-image-2-image-to-image as primary. nano-banana-2 is FALLBACK-ONLY for presentations (logs required). Added AF-MODEL-SOVEREIGNTY auto-fail reference. |
