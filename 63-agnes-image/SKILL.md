---
name: agnes-image
description: >
  Setup and API reference for Agnes Image 2.1 Flash, a synchronous
  text-to-image and image-to-image generation endpoint on the Agnes AI
  platform (apihub.agnes-ai.com). One API key, one POST, one JSON response
  with an image URL or Base64 — no task polling.
metadata:
  version: "1.2.0"
  priority: HIGH
---

# Agnes Image 2.1 Flash — Setup and API Reference

Agnes Image 2.1 Flash is a single image-generation model on the Agnes AI
platform (Sapiens AI). You send ONE POST request with a prompt and a size, and
the response comes back in the same call with a finished image — as a URL or as
Base64. There is no "create a task, then poll" step: the image endpoint is
SYNCHRONOUS.

Model name: `agnes-image-2.1-flash`. Endpoint:
`POST https://apihub.agnes-ai.com/v1/images/generations`.

## When to Use This Skill

- The user (or an upstream skill) says "use the Agnes image skill" or "generate
  this with Agnes."
- You need to generate an image from a text prompt (text-to-image).
- You need to transform, restyle, or edit an existing image while preserving its
  composition (image-to-image).
- You need predictable output dimensions from a size tier (`1K`/`2K`/`3K`/`4K`)
  crossed with an aspect ratio (`16:9`, `9:16`, `1:1`, and others).
- You need the image back as a hosted URL, or inline as Base64.

This skill is for the Agnes IMAGE endpoint specifically. It is NOT a general
image-model default: department pipelines and other skills pin their own image
model (for example the KIE Image registry in Skill 66, or specific department
pins). Only reach for Agnes Image when the request names Agnes, or an upstream
skill routes to it.

## Prompt Policy & House Operating Bands

Agnes vendor documentation does **NOT** publish a hard character or token limit
(`cap_status: "NOT_PUBLISHED"` in `models.json`). Do not invent a vendor cap.

Per BlackCEO prompt policy (Spec §5 & §10.5):
- **House Target Floor**: 5,000 characters (stripped) — prompts below 5,000 chars
  are thin stubs. Short user prompts are NOT an error (§5.3); the system expands
  them into rich production prompts rather than rejecting them.
- **House Normal Target**: ~9,000 characters (stripped) — high-information-density
  production target.
- **House Preferred Maximum**: 19,000 characters (stripped) — preferred headroom.
  Prompts above 19,000 characters trigger a non-fatal advisory but are NOT
  hard-rejected at the API boundary if intentional.
- **Status**: `PENDING_ACCEPTANCE_TEST` — house bands serve as targets, not
  invented vendor laws.

Enforcement & Validation:
- `scripts/validate_prompt.py`: model-aware prompt validator reporting band
  status (thin stub, target zone, upper band, above preferred max) and enforcing
  logo-I2I and style-reference rules.
- `prove_agnes_image_prompt_floor.py`: deterministic quality gate verifying
  prompt status, logo I2I intent, and style-reference directives.

```bash
python3 63-agnes-image/scripts/validate_prompt.py --file working/prompts/<id>.txt
```

## Image-to-Image for Logos (MANDATORY)

When an image prompt involves the client's LOGO, wordmark, brand mark, monogram,
or any existing brand image, you MUST use IMAGE-TO-IMAGE generation -- provide the
logo as a reference image via `extra_body.image[]`. Text-to-image generation of a
logo is PROHIBITED: a text-to-image model cannot render a specific client's logo
accurately and will invent a lookalike instead. The validation scripts check for
this:

```bash
python3 63-agnes-image/scripts/validate_prompt.py --file prompt.txt --logo
```

When a logo reference triggers an I2I call, the style-reference-only directive is
MANDATORY: "Use the attached images only as style reference for color grading,
lighting, and composition -- do not copy their subjects, faces, or text." Pass
`--style-ref` to enforce this.

## Style-Reference-Only Directive (MANDATORY when reference images attached)

Whenever ANY reference image is attached for style guidance (not just logos), the
prompt MUST carry the style-reference-only directive verbatim:
`Use the attached images only as style reference for color grading, lighting, and composition -- do not copy their subjects, faces, or text.`

## Prerequisites

- Teach Yourself Protocol (TYP) must be learned first (Skill 01).
- Backup Protocol must be learned first (Skill 02).
- `AGNES_AI_API_KEY` present in the box's secrets. This is an EXISTING fleet
  credential — the same key the registered `agnes` / `agnes-2.5-flash` model on
  the boxes already uses against `apihub.agnes-ai.com/v1`. This skill REFERENCES
  that key; it does not mint a new one. Verify it is SET, never print its value.
- `curl` available for the verification calls.

## What This Skill Covers

1. **The synchronous request pattern** — one `POST /v1/images/generations`, one
   JSON response. No task id, no polling loop. This is the opposite of the
   asynchronous "create task then poll" pattern in KIE.ai skills and the Agnes
   VIDEO endpoint.
2. **Required fields** — `model`, `prompt`, `size`.
3. **Size tiers and aspect ratios** — `size` is a TIER (`1K`, `2K`, `3K`, `4K`),
   combined with `ratio` (`1:1` default, plus `3:4`, `4:3`, `16:9`, `9:16`,
   `2:3`, `3:2`, `21:9`). Legacy exact sizes such as `1024x768` are accepted but
   may be normalized to the nearest tier.
4. **The output-dimension table** — every ratio × tier maps to exact pixels
   (for example `16:9` at `2K` = `2624x1472`). Full table in `models.json` and
   `agnes-image-full.md`.
5. **Image-to-image** — pass input image URL(s) or Data-URI Base64 in
   `extra_body.image[]`. Image-to-image does NOT require `tags: ["img2img"]`.
6. **URL vs Base64 output** — the response-format control lives in
   `extra_body.response_format` (`"url"` or `"b64_json"`), NOT at the top level.
   For text-to-image Base64, the top-level `return_base64: true` shortcut also
   works.
7. **Rate-limit / tier awareness** — Agnes meters requests-per-minute by ACCOUNT
   TIER and (on paid Token Plans) daily quotas. Treat HTTP 429 as the live
   source of truth and back off; never hardcode a ceiling. See the rate-limit
   section in `agnes-image-full.md` and `references/api-patterns.md`.
8. **Pricing** — image generation is currently promotional `$0 / image`
   (standard reference rate `$0.003 / image`). Reference images: first 3 free,
   4th+ `$0.003 / image` at list price.
9. **Machine-Readable Registry & Validators** — `models.json`, `scripts/validate_prompt.py`,
   `scripts/validate_payload.py`, and `scripts/normalize_alias.py`.

## Files in This Folder (Reading Order)

1. **SKILL.md** — you are here. Start with this file.
2. **models.json** — machine-readable capability registry for `agnes-image-2.1-flash`.
3. **references/prompt-policy.md** — prompt policy, house bands, and expansion guide.
4. **references/api-patterns.md** — request patterns, payload gotchas, and error handling.
5. **references/qc.md** — visual quality control checklist and retry ladder.
6. **agnes-image-full.md** — complete narrative reference and dimension tables.
7. **INSTRUCTIONS.md** — how to call the endpoint day to day.
8. **INSTALL.md** — how to confirm credentials and verify connectivity.
9. **EXAMPLES.md** — copy-paste curl examples for common tasks.
10. **CORE_UPDATES.md** — what to add to AGENTS.md, TOOLS.md, and MEMORY.md.
11. **scripts/validate_prompt.py** — model-aware prompt validation script.
12. **scripts/validate_payload.py** — JSON payload validation script.
13. **scripts/normalize_alias.py** — alias normalization script.
14. **prove_agnes_image_prompt_floor.py** — prompt band quality gate.

## Critical Things to Know

- **The image endpoint is SYNCHRONOUS.** A 200 response already contains the
  finished image at `data[0].url` (or `data[0].b64_json`). Do NOT write a
  polling loop for it. (The Agnes VIDEO endpoint is a separate, asynchronous
  create-then-poll service — do not confuse the two.)
- **`response_format` goes inside `extra_body`, not at the top level.** A
  top-level `response_format` is an error. Use
  `extra_body.response_format: "url"` (or `"b64_json"`).
- **Image-to-image needs NO tags.** Provide the input image array in
  `extra_body.image` and that is enough. Do not send `tags: ["img2img"]`.
- **`size` is a tier, `ratio` is the shape.** For predictable pixels, pair a
  tier (`2K`) with a ratio (`16:9`) and read the exact output size from the
  dimension table. Requesting an exact non-native size such as `1920x1080` may
  be normalized (for example to the `16:9` `1K` size `1312x736`).
- **The credential is the existing `AGNES_AI_API_KEY`.** It rides the
  `Authorization: Bearer <key>` header on every call. Confirm it is SET; never
  echo, cat, or log the value.
- **Rate limits are per account tier — read them live.** Do not bake a numeric
  request/day cap into any logic. If the account is on a paid Token Plan the
  daily quotas apply; on the free/default tier only requests-per-minute apply.
  Treat a 429 as the authority and back off. Full details in `references/api-patterns.md`.
- **Vendor prompt cap is NOT_PUBLISHED.** Do not invent a vendor cap.
  House operating policy targets 5,000–19,000 characters (~9,000 target). Short user
  prompts are expanded, not rejected. Run `scripts/validate_prompt.py` before calls.
- **Logo requests MUST use image-to-image.** When a prompt involves the client's
  logo, wordmark, or existing brand image, use I2I (pass the logo as a reference
  image via `extra_body.image[]`), never text-to-image. Add the mandatory
  style-reference-only directive whenever reference images are attached.
