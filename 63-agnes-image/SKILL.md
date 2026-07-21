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
