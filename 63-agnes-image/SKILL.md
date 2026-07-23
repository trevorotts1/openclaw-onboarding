---
name: agnes-image
description: >
  Setup and API reference for Agnes Image 2.1 Flash, a synchronous
  text-to-image and image-to-image generation endpoint on the Agnes AI
  platform (apihub.agnes-ai.com). One API key, one POST, one JSON response
  with an image URL or Base64 — no task polling.
metadata:

  version: "1.0.0"
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
model (for example the KIE.ai / Nano Banana Pro default in Skill 07, or the
Presentations GPT-Image-2 pin). Only reach for Agnes Image when the request
names Agnes, or an upstream skill routes to it.

## Image-Prompt Character Band (MANDATORY -- 5,000-19,000)

Per decision GK-D2 (extended to Agnes skills 63/64), every image prompt authored
for GPT-image-2 OR Agnes Image 2.1 Flash must fall within the SACRED band:

- **FLOOR: 5,000 characters (stripped)** -- a prompt below 5,000 chars is a thin
  stub, NOT submitted, NOT rendered. 5,000 is the HARD MINIMUM.
- **CEILING: 19,000 characters (stripped)** -- the API accepts up to 25,000 chars;
  the 19,000 cap leaves ~6,000 chars of headroom to stay well clear of the
  endpoint's truncation boundary. Do NOT exceed 19,000.
- **Valid range: 5,000-19,000.**

Enforcement: `prove_agnes_image_prompt_floor.py` (shipped in this folder) is the
deterministic gate. It checks stripped character count (whitespace never counts),
rejects below 5,000 (`AF-AGNES-PROMPT-FLOOR`, exit 2), rejects above 19,000
(`AF-AGNES-PROMPT-CEILING`, exit 2), and exits 0 only when the prompt clears both
gates. Run it as a preflight before any paid API call:

```
python3 63-agnes-image/prove_agnes_image_prompt_floor.py --file working/prompts/<id>.txt
```

A QA version with self-tests (suitable for CI) runs with `--self-test`.

This band applies whenever the target endpoint is GPT-image-2 (T2I or I2I) or
Agnes Image 2.1 Flash. It does NOT apply to shorter-cap endpoints such as
Seedream 4.5 (3,000-char cap) or Ideogram V3 (5,000-char cap) -- those carry
their own bands in `45-design-intelligence-library/library/_system/prompt-bands.json`.

## Image-to-Image for Logos (MANDATORY)

When an image prompt involves the client's LOGO, wordmark, brand mark, monogram,
or any existing brand image, you MUST use IMAGE-TO-IMAGE generation -- provide the
logo as a reference image via `extra_body.image[]` (Agnes) or `input_urls`
(Kie.ai GPT-Image 2 I2I). Text-to-image generation of a logo is PROHIBITED: a
text-to-image model cannot render a specific client's logo accurately and will
invent a lookalike instead. The prove-agnes gate checks for this:

```
python3 63-agnes-image/prove_agnes_image_prompt_floor.py --file prompt.txt --logo
```

When a logo reference triggers an I2I call, the style-reference-only directive is
MANDATORY (MODEL-SPECS section 4): "Use the attached images only as style
reference for color grading, lighting, and composition -- do not copy their
subjects, faces, or text." The gate checks this with `--style-ref`.

## Style-Reference-Only Directive (MANDATORY when reference images attached)

Whenever ANY reference image is attached for style guidance (not just logos), the
prompt MUST carry the style-reference-only directive verbatim. Pass `--style-ref`
to the gate to enforce this check.

## Prerequisites

- Teach Yourself Protocol (TYP) must be learned first (Skill 01).
- Backup Protocol must be learned first (Skill 02).
- `AGNES_AI_API_KEY` present in the box's secrets. This is an EXISTING fleet
  credential — the same key the registered `agnes` / `agnes-2.0-flash` model on
  the boxes already uses against `apihub.agnes-ai.com/v1`. This skill REFERENCES
  that key; it does not mint a new one. Verify it is SET, never print its value.
- `curl` available for the verification calls.

## What This Skill Covers

1. **The synchronous request pattern** — one `POST /v1/images/generations`, one
   JSON response. No task id, no polling loop. This is the opposite of the
   asynchronous "create task then poll" pattern in Skill 07 (KIE.ai) and in the
   Agnes VIDEO endpoint.
2. **Required fields** — `model`, `prompt`, `size`.
3. **Size tiers and aspect ratios** — `size` is a TIER (`1K`, `2K`, `3K`, `4K`),
   combined with `ratio` (`1:1` default, plus `3:4`, `4:3`, `16:9`, `9:16`,
   `2:3`, `3:2`, `21:9`). Legacy exact sizes such as `1024x768` are accepted but
   may be normalized to the nearest tier.
4. **The output-dimension table** — every ratio × tier maps to exact pixels
   (for example `16:9` at `2K` = `2624x1472`). Full table in
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
   section in `agnes-image-full.md`.
8. **Pricing** — image generation is currently promotional `$0 / image`
   (standard reference rate `$0.003 / image`).

## Files in This Folder (Reading Order)

1. **SKILL.md** — you are here. Start with this file.
2. **agnes-image-full.md** — the complete reference: every parameter, the full
   output-dimension table, working curl examples for text-to-image and
   image-to-image, the response shape, error handling, and the tier/rate-limit
   section. Go here when you need exact API details.
3. **INSTRUCTIONS.md** — how to call the endpoint day to day.
4. **INSTALL.md** — how to confirm the `AGNES_AI_API_KEY` credential and verify
   the endpoint responds.
5. **EXAMPLES.md** — copy-paste curl examples for common tasks.
6. **CORE_UPDATES.md** — what to add to AGENTS.md, TOOLS.md, and MEMORY.md.
7. **prove_agnes_image_prompt_floor.py** — the deterministic prompt-band
   enforcement gate: checks every prompt against the 5,000–19,000-char band,
   enforces the image-to-image-for-logos rule, and verifies the mandatory
   style-reference-only directive. Run before any paid API call to Agnes Image or
   GPT-image-2. Self-tests with `--self-test` for CI.

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
  Treat a 429 as the authority and back off. The full tier table (with its
  confirmed and unverified cells) is in `agnes-image-full.md`.
- **Prompt length must be 5,000–19,000 characters (stripped).** Never submit a
  prompt below 5,000 chars (thin stub) or above 19,000 chars (stays clear of the
  API's 25,000-char max with ~6,000 chars of headroom). Run the deterministic
  gate before any paid call: `python3 63-agnes-image/prove_agnes_image_prompt_floor.py
  --file <prompt.txt>`. A prompt under 5,000 chars or over 19,000 chars is NOT
  submitted — re-author first.
- **Logo requests MUST use image-to-image.** When a prompt involves the client's
  logo, wordmark, or existing brand image, use I2I (pass the logo as a reference
  image via `extra_body.image[]`), never text-to-image. Add the mandatory
  style-reference-only directive whenever reference images are attached.
