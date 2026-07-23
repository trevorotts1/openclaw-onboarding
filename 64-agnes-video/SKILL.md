---
name: agnes-video
description: >
  Endpoint reference and asynchronous workflow for Agnes Video V2.0
  (agnes-video-v2.0), a production video-generation model on the Agnes AI API
  gateway. Covers text-to-video, image-to-video, and keyframe animation via the
  create-task / poll-result pattern, the num_frames 8n+1 rule, resolution tiers,
  and reading the returned size/seconds/metadata as the source of truth.
metadata:

  version: "1.0.0"
  priority: HIGH
---

# Agnes Video V2.0 — Endpoint Reference

Agnes Video V2.0 is an asynchronous video-generation model reached through the
Agnes AI API gateway (`apihub.agnes-ai.com`). You give it a text prompt (and
optionally an image, or a set of keyframes) and it returns a rendered `.mp4`.

This skill is a REFERENCE, not an installer for a new account. The fleet already
carries the `AGNES_AI_API_KEY` credential (the same key that backs the registered
`agnes/agnes-2.0-flash` model on the boxes, endpoint `apihub.agnes-ai.com/v1`).
This skill teaches an agent the exact request/response shape so that when it is
told "use the Agnes video skill", it knows the two-step async flow cold.

Think of it as the operating manual for one endpoint family — like Skill 30
(Fish Audio) is for text-to-speech, this is for text-to-video.

## When to Use This Skill

- The user asks you to generate a video from a text prompt (text-to-video).
- The user asks you to animate a still image into a moving clip (image-to-video).
- The user asks you to tween between two or more keyframes (keyframe animation).
- You are told to "use the Agnes video skill" or to render with `agnes-video-v2.0`.
- You need to know the exact create-task parameters, the poll endpoint, the
  `num_frames` rule, the resolution tiers, or how to read the true output size.

## Image-Prompt Character Band for Image-to-Video Inputs

When generating images that will be fed as inputs to Agnes Video (image-to-video
or keyframe animation), the image-generation prompt that produces those input
images must obey the same band as the Agnes Image skill: **5,000–19,000 stripped
characters** (per decision GK-D2, extended to skills 63/64). The deterministic
gate is `63-agnes-image/prove_agnes_image_prompt_floor.py`.

When those input images involve the client's LOGO or existing brand image, use
IMAGE-TO-IMAGE generation (provide the logo as reference), never text-to-image.
The same style-reference-only directive is MANDATORY whenever reference images
are attached for style (MODEL-SPECS section 4).

Agnes Video itself has a separate prompt for the video generation (focused on
animation/motion, typically much shorter). The 5,000–19,000 band applies to the
IMAGE-generation prompt that produces the input frame(s), not to the video
prompt itself.

## Prerequisites

- Teach Yourself Protocol (TYP) must be learned first (Skill 01).
- Backup Protocol must be learned first (Skill 02).
- The `AGNES_AI_API_KEY` credential must be present on the box (it is already
  configured fleet-wide — this skill REFERENCES it, it does not create it).
- `curl` available for the request examples.
- For image-to-video and keyframe workflows: publicly reachable image URLs.

## What This Skill Covers

1. **The async pattern** — Video generation is a TWO-STEP flow, unlike Agnes
   *image* generation which is synchronous. Step 1: `POST /v1/videos` to CREATE
   a task (a `200` means the task was accepted, NOT that a video exists yet).
   Step 2: POLL `GET /agnesapi?video_id=<id>` until `status` is `completed`,
   then read `metadata.url`.
2. **Retrieval ids** — The create response returns BOTH a `task_id` and a
   `video_id`. `video_id` is the RECOMMENDED id for new integrations. A
   legacy-compatible path (`GET /v1/videos/<task_id>`) still works.
3. **Three generation modes** — text-to-video (prompt only), image-to-video
   (`image` URL), and keyframe animation (`extra_body.image[]` +
   `extra_body.mode: "keyframes"`).
4. **Duration control** — `seconds = num_frames / frame_rate`. `num_frames` must
   be `<= 441` and must satisfy the `8n + 1` rule (81, 121, 241, 441, ...).
   `frame_rate` is 1-60.
5. **Resolution tiers** — `480p` / `720p` / `1080p`, aspect ratios
   `16:9`, `9:16`, `1:1`, `4:3`, `3:4`. Requested `width`/`height` are NORMALIZED
   to the nearest supported preset.
6. **Source of truth after normalization** — the request dimensions may not
   match the render. ALWAYS trust the RETURNED `size`, `seconds`, and
   `metadata.size_mapping` fields, never the values you submitted.
7. **Task status + error codes** — `queued` / `in_progress` / `completed` /
   `failed`, and what `400` / `401` / `404` / `500` / `503` mean.
8. **Rate-limit / tier awareness** — Agnes meters on TWO axes at once (requests
   per minute AND daily/weekly quota) and the limit depends on the account's
   access tier. Treat HTTP `429` as the live truth; do not hardcode a ceiling.
   See "Tier and Rate-Limit Awareness" below.

## Files in This Folder (Reading Order)

1. **SKILL.md** — You are here. Start with this file.
2. **agnes-video-full.md** — The complete endpoint reference: every parameter,
   every response field, all curl examples, the duration table, the resolution
   normalization rules, error codes, and pricing. Your go-to for exact details.
3. **INSTRUCTIONS.md** — Operational instructions for running the async flow.
4. **INSTALL.md** — Steps to verify the reference is installed and the existing
   `AGNES_AI_API_KEY` is visible on the box.
5. **EXAMPLES.md** — Copy-paste curl examples for every mode.
6. **CORE_UPDATES.md** — What to add to AGENTS.md, TOOLS.md, and MEMORY.md.
7. **QC.md** — Install-time QC checklist and rubric.

## Critical Things to Know

- **Video is ASYNCHRONOUS. Agnes *image* generation is synchronous.** Do not
  reuse the image flow. For video you MUST create-then-poll; a `200` on
  `POST /v1/videos` only means the task was queued.
- **The endpoint is NOT the OpenAI shape.** Create is `POST /v1/videos`. The
  recommended result read is `GET /agnesapi?video_id=<VIDEO_ID>` — note the
  `agnesapi` path, not `/v1/videos/...` (that legacy form takes a `task_id`).
- **`num_frames` has two hard rules:** `<= 441` AND `8n + 1`. A value that
  breaks either rule is invalid. Valid examples: 81 (~3s), 121 (~5s), 241
  (~10s), 441 (~18s) at `frame_rate: 24`.
- **Trust the returned dimensions, not the request.** The model normalizes
  `width`/`height`/aspect to the nearest `480p`/`720p`/`1080p` preset. Read
  `size`, `seconds`, and `metadata.size_mapping` from the response when you
  compute duration, cost, or display resolution.
- **Keyframe mode uses `extra_body`.** Pass `extra_body.image` as an ARRAY of
  image URLs and `extra_body.mode: "keyframes"`. Plain image-to-video uses the
  top-level `image` string instead.
- **Image inputs must be public URLs**, not local files or raw bytes.
- **The API key is referenced, never printed.** It lives as `AGNES_AI_API_KEY`
  and is sent as `Authorization: Bearer <key>`. Confirm it is SET; never echo,
  cat, or log its value.
- **Pricing is currently promotional.** Video duration is billed at `$0 / second`
  right now (standard reference rate `$0.005 / second`). Do not assume it stays
  free — the vendor labels prices as non-contractual reference values.

## Tier and Rate-Limit Awareness

Agnes AI meters usage on **two axes simultaneously**, and both depend on the
account's access tier:

- **Requests per minute (RPM)** — set by the ACCESS TYPE
  (Free/default, Enterprise-verified, or a paid Token Plan). For video, the
  free/default tier is roughly **1 generation task per minute** (2 public /
  1 actual RPM); Token-Plan raises this to ~5 actual RPM.
- **Daily / weekly quota** — set by the Token Plan tier. Video has a documented
  **500 video-seconds per day** cap on every paid tier (Starter / Plus / Pro are
  IDENTICAL for video). Free/default has NO published daily video-seconds quota —
  it is RPM-throttled only.

Practical guidance (respecting research confidence — every number below traces to
`AgnesAI-Labs/AgnesAI-Models` `MODEL_CATALOG.md` + `docs/TOKEN_PLAN_FAQ.md`,
dated 2026-06-28, which the vendor explicitly calls non-contractual reference
values):

- **Do NOT hardcode a rate ceiling.** Treat HTTP `429` as the live source of
  truth and back off exponentially. A static number cannot capture both axes.
- **Which tier a box is on is an ACCOUNT property** you cannot know statically —
  read it live from the Agnes console (Usage / Billing). If the fleet keys off a
  per-box tier config, source the limits from a DATED, SOURCED table, not
  constants baked into skill logic.
- **For a pure video/image workload, paying up buys NOTHING extra.** All three
  paid tiers (Starter $4 / Plus $10 / Pro $50) grant the SAME 500 sec/day and
  share one Token-Plan RPM pool. Only the text-model request quota scales with
  tier. Flag this so the operator does not overpay for video throughput that
  does not exist.

## Credential Note

The credential is `AGNES_AI_API_KEY`. It is ALREADY provisioned on the fleet
(the same key backs `agnes/agnes-2.0-flash`). This skill only REFERENCES it.

- Verify presence with SET / NOT-SET only, e.g.
  `openclaw config get AGNES_AI_API_KEY` (check that it is set) — NEVER print,
  `cat`, `echo`, or log the value.
- It is sent as `Authorization: Bearer <AGNES_AI_API_KEY>` on every request.
