# KIE Image — Model Registry (Human Golden Matrix)

Verification date: 2026-08-26. Every limit below is quoted from a first-party
KIE page fetched that day. The machine-readable source of truth is
`../models.json` (30 entries; every entry carries `source_url`,
`last_verified_at`, `cap_status`). This page is the human-readable view.

Encoding sources (research files, verbatim quotes):
- `02-kie-image-a.md` — GPT Image 2, Qwen 3.0/Pro, Ideogram V3, Imagen 4
- `03-kie-image-b.md` — Seedream 5.0 Pro/Lite/4.5, Nano Banana 2/2 Lite/Pro/legacy,
  Wan 2.7 Image, FLUX.2, Z-Image
- `01-kie-common.md` — generic Market API conventions

---

## 1. Matrix

| Family | Canonical model IDs | Prompt limit (status) | Max refs | Output notes |
|---|---|---|---|---|
| GPT Image 2 | `gpt-image-2-text-to-image`, `gpt-image-2-image-to-image` | **25,000 chars `OWNER_CONFIRMED`** (operator-confirmed 2026-08-27, authoritative; warn-only, never hard-fail) — docs page text also says "maximum 20,000 characters" but that figure is STALE | 16 @ 30 MB, JPEG/PNG/WEBP/JPG | 1K/2K/4K; 2K/4K exclude 5:4, 4:5, 3:1, 1:3, 9:21; auto→1K only; 1:1 cannot convert to 4K |
| Qwen Image 3.0 / Pro | `qwen3/text-to-image`, `qwen3-pro/text-to-image`, `qwen3/image-to-image`, `qwen3-pro/image-to-image` | 4.5K **tokens** advertised (marketing copy); docs schemas say maxLength 5000 chars. Token cap — NEVER converted to a fake char cap (spec rule D) | 3 @ 10 MB, JPEG/PNG/WEBP/BMP/GIF/TIFF | 1K/2K; ratios 1:1, 3:2, 2:3, 4:3, 3:4, 16:9, 9:16, 21:9 |
| Seedream 5.0 Pro | `seedream/5-pro-text-to-image`, `seedream/5-pro-image-to-image`, `seedream/5-pro-layer-decomposition` | NOT PUBLISHED | 10 @ 30 MB, JPEG/PNG/WEBP | Basic=1K / High=2K; 21:9 in enum |
| Seedream 5.0 Lite | `seedream/5-lite-text-to-image`, `seedream/5-lite-image-to-image` | NOT PUBLISHED | 14 @ 30 MB, JPEG/PNG/WEBP | Basic=2K / High=3K / Ultra=4K; 21:9 in enum |
| Seedream 4.5 | `seedream/4.5-text-to-image`, `seedream/4-5-edit` | NOT PUBLISHED | 14 @ 30 MB (playground editor) — README says "up to 10"; UNDETERMINED arbiter | Basic=2K / High=4K; NO output_format field |
| Nano Banana 2 | `nano-banana-2` | NOT PUBLISHED | 14 @ 30 MB, JPEG/PNG/WEBP | 1K/2K/4K; JPG/PNG; 15-value ratio enum incl 1:4, 4:1, 1:8, 8:1, 21:9, auto |
| Nano Banana 2 Lite | `nano-banana-2-lite` | NOT PUBLISHED | 10 @ 30 MB, JPEG/PNG/WEBP | 1K-focused (README); only 3 fields exposed: prompt, image_urls, aspect_ratio |
| Nano Banana Pro | `nano-banana-pro` | NOT PUBLISHED (context window 64K/32K is NOT a prompt cap) | 8 @ 30 MB, JPEG/PNG/WEBP | 1K/2K/4K; PNG/JPG; 11-value enum (NO 1:4/4:1/1:8/8:1) |
| Legacy Nano Banana | `google/nano-banana` | NOT PUBLISHED | edit path: 10 @ **10 MB** (NOT 30 MB), JPEG/PNG/WEBP | legacy/lightweight only; resolution param NOT exposed |
| Wan 2.7 Image | `wan/2-7-image`, `wan/2-7-image-pro` | **5,000 chars VERIFIED** (1–5,000, chars not tokens) | 9 @ 10 MB, JPEG/PNG/WEBP/JPG, min 240 px per side | standard 1K/2K; Pro up to 4K T2I only; bbox 2/image; n 1–4 (1–12 gallery); ratios incl 1:8, 8:1 |
| FLUX.2 | `flux-2/pro-text-to-image`, `flux-2/pro-image-to-image`, `flux-2/flex-text-to-image`, `flux-2/flex-image-to-image` | NOT PUBLISHED | NOT EXPOSED (no maxItems/MB published on docs routes) | request shape: prompt, aspect_ratio, resolution, nsfw_checker (+ input_urls I2I) |
| Z-Image | `z-image` | NOT PUBLISHED | none — playground exposes NO image field (T2I only, 3 fields: prompt, aspect_ratio, nsfw_checker) | ratios 1:1, 4:3, 3:4, 16:9, 9:16 (`auto` in help text only, NOT in enum) |
| Ideogram V3 | `ideogram/v3-text-to-image`, `ideogram/v3-edit`, `ideogram/v3-remix` | **5,000 chars VERIFIED** (prompt and negative_prompt) | mode-specific: v3-edit single image + mask (10.0 MB, jpeg/png/webp); v3-remix single image (10.0 MB) + strength 0.01–1 | rendering_speed TURBO/BALANCED/QUALITY; style AUTO/GENERAL/REALISTIC/DESIGN; named image_size enums; design/typography specialist |
| Imagen 4 family | `google/imagen4-fast`, `google/imagen4`, `google/imagen4-ultra` | **5,000 chars VERIFIED** (prompt and negative_prompt) | none — no reference/edit route found in sitemap (EN) | ratios 1:1, 16:9, 9:16, 3:4, 4:3, auto (fast default 16:9; standard/ultra default 1:1); seed string max 500 chars |

---

## 2. Per-family routing guidance

### GPT Image 2 — preferred default when compatible (spec 7.4, 7.5)
Owner's preferred KIE image model. Prefer for high-fidelity general generation,
editing, product/brand images, and detailed long-form creative instructions.
Prompt cap 25,000 chars, operator-confirmed 2026-08-27 (`OWNER_CONFIRMED`);
docs page "maximum 20,000 characters" is stale. House band 5,000–19,000 chars
is legal here (short prompts expanded, never rejected). Validators warn-only
above the house max — the confirmed cap is never hard-enforced.

### Qwen Image 3.0 / Pro
Use for information-dense layouts, multilingual content, typography, structured
UI/document visuals, and up to three references. Token-aware validation
(rule D): the 4.5K figure is TOKENS; never write it as a char cap. Docs char
limit (maxLength 5000) is the authoritative API validation surface.

### Seedream 5.0 Pro / Lite / 4.5
Strong premium controlled-generation/editing family, particularly multi-reference
and complex information-rich compositions. Pro: Basic=1K/High=2K. Lite:
Basic=2K/High=3K/Ultra=4K, cheaper lighter route. 4.5: keep (owner requested),
prefer 5.x when user did not ask for 4.5 and 5.x fits.

### Nano Banana family
- **Nano Banana 2**: strong general/multi-reference alternative; wide ratio
  support (1:4, 4:1, 1:8, 8:1, 21:9, auto) and 1K/2K/4K.
- **Nano Banana 2 Lite**: fast/low-cost route. Only 3 fields exposed — do not
  send resolution/output_format (route may ignore).
- **Nano Banana Pro**: strongest multi-turn edit; 8 refs; 1K/2K/4K; PNG/JPG.
- **Legacy Nano Banana**: compatibility only; prefer NB2/Pro unless explicitly
  pinned. Edit path caps at 10 MB per image (not 30 MB).

### Wan 2.7 Image
When its specific control/edit workflow fits and the 5K ceiling is acceptable.
Do NOT force 5,000 as a minimum — 5,000 is the hard ceiling; target 4,500–4,900
with headroom (spec rule B). 4K is text-to-image-only on Pro.

### FLUX.2
Creative/photorealistic alternate route. Limits NOT PUBLISHED — validators
treat cap_status NOT_PUBLISHED; no invented cap. Flux Kontext is a SEPARATE
API (`flux-kontext-api`, `/api/v1/flux/kontext/generate`) — not FLUX.2.

### Z-Image
Text-to-image ONLY with no exposed reference support. Own KIE family — NEVER
merged into Qwen, regardless of "Z Image by Quinn" phrasing (spec 13).

### Ideogram V3
Preferred specialist for typography/design/text-heavy visual assets.
v3-edit and v3-remix are endpoint-specific semantics — do NOT call them generic
multi-reference composition. Positive prompt takes precedence on conflict with
negative_prompt. `style_codes` is referenced but not documented (NOT EXPOSED).

### Imagen 4 family
Ratio-driven T2I. No reference/edit behavior on the verified T2I routes —
do not invent multi-reference support.

---

## 3. Registry invariants

- Every model carries `source_url` + `last_verified_at: 2026-08-26`.
- `vendor_hard_cap_chars` numeric only where a vendor page publishes it
  (Wan 2.7: 5000 VERIFIED; Ideogram V3: 5000 VERIFIED; Imagen 4: 5000 VERIFIED).
- Qwen caps live in `vendor_hard_cap_tokens: 4500` (rule D — never converted).
- GPT Image 2 sits in `owner_observed_cap_chars: 25000`, cap_status
  `OWNER_CONFIRMED` — operator-confirmed 2026-08-27 (vendor docs page's 20,000
  figure is stale); warn-only, never hard-failed upon.
- NOT_PUBLISHED families keep `null` caps; no invented numbers anywhere.
