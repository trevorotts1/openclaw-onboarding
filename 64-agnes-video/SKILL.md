---
name: agnes-video
description: >
  Endpoint reference and asynchronous workflow for the two approved Agnes video
  models — agnes-video-2.5-flash (string seconds 4-12, 720P only, modes
  text/keyframe/reference) and agnes-video-v2.0 (frame-driven duration,
  num_frames 8n+1 <= 441, 480p/720p/1080p) — on the Agnes AI API gateway.
  Model choice is driven by the deterministic router
  scripts/select_agnes_video_model.py (single source of truth; explicit model
  wins; no silent switch), with the create-task / poll-result pattern, reading
  returned size/seconds/metadata as the source of truth.
metadata:

  version: "1.2.0"
  priority: HIGH
---

# Agnes Video — Router + Endpoint Reference (2.5 Flash & V2.0)

Agnes Video is an asynchronous video-generation API reached through the Agnes
AI gateway (`apihub.agnes-ai.com`). Two models are approved in this skill:

- **`agnes-video-2.5-flash`** — 720P only, `seconds` is a STRING `"4"`–`"12"`,
  modes `text` / `keyframe` / `reference`, images max 5, videos unsupported,
  n only 1.
- **`agnes-video-v2.0`** — frame-driven duration (`seconds = num_frames /
  frame_rate`), `num_frames <= 441` and `8n + 1`, `frame_rate` 1–60,
  `480p`/`720p`/`1080p`, top-level `image` for i2v, `extra_body.image[]` +
  `extra_body.mode: "keyframes"`.

This skill is a REFERENCE, not an installer for a new account. The fleet already
carries the `AGNES_AI_API_KEY` credential.

## The Router Is the Single Source of Truth

**Model choice is NOT manual.** Run the deterministic, offline router before any
dispatch:

```bash
echo '{"requested_seconds":"5","size":"720P","intent":"text"}' \
  | python3 64-agnes-video/scripts/select_agnes_video_model.py
python3 64-agnes-video/scripts/select_agnes_video_model.py --self-test
```

The router emits one JSON verdict:
`{"model": ..., "valid": true|false, "mode": ..., "reason": ..., "warnings": [],
"handoff": null | {"provider":"kie",...}}`.

Rules it enforces (spec 11.4):

- **Explicit model wins** — if the user names a model, validate THAT model.
  Incompatible → `valid: false` with the exact reason; the named model stays in
  the output. **Never silently switch** Flash to V2.0 or vice versa.
- **Semantic guard** — a 6-image reference request is NOT reinterpreted as a
  V2.0 keyframe job (reference vs keyframe are different semantics). It returns
  `valid: false` ("re-ask or use KIE Video") unless the request explicitly says
  mode keyframes and fits V2.0.
- **Video references** — neither Agnes model supports them (vendor HTTP 400
  `videos is not supported`). Video refs are never silently converted to image
  refs; result is `unsupported`, with `handoff: {"provider":"kie"}` ONLY when
  `allow_kie_handoff: true` (KIE Video owns video-reference input).
- **Tiebreak** — both models valid and no explicit model → Flash default.
- **Seed alone never forces V2.0** — both models accept seed.
- **>12s** — Flash cannot go past 12s; the router derives V2.0 `num_frames`
  (8n+1 ceiling, default frame_rate 24) and only when `frames <= 441`; otherwise
  it explains the tradeoff (split clips or lower frame_rate).
- **Never auto-select `agnes-video-2.5`** — full paid 2.5 is NOT in the token
  plan; only flash and v2.0 are approved.

## When to Use This Skill

- The user asks to generate a video from a text prompt, an image, or keyframes.
- You need to know the exact create/retrieve endpoints, the Flash string-seconds
  enum, the V2.0 `num_frames` rule, or which model a request belongs on.
- You are told "use the Agnes video skill".

## Files in This Folder (Reading Order)

1. **SKILL.md** — You are here. Start with this file.
2. **agnes-video-full.md** — Complete endpoint reference: every parameter, all
   curl examples, both models, error messages, normalization, pricing.
3. **scripts/select_agnes_video_model.py** — Deterministic model router with
   `--self-test` (spec 11.4 / 14 / 18.5). Pure, offline, stdlib only.
4. **models.json** — Machine-readable capability registry (spec 12): endpoints,
   prompt-cap status (NOT_PUBLISHED — never invented), house band, reference
   limits, duration, resolutions, ratios, plan restriction.
5. **INSTRUCTIONS.md** — Operational instructions for running the async flow.
6. **EXAMPLES.md** — Copy-paste curl examples for both models.
7. **INSTALL.md** — Steps to verify the reference is installed.
8. **CORE_UPDATES.md** — What wire.sh writes to AGENTS.md/TOOLS.md/MEMORY.md.
9. **QC.md** — Install-time + media QC checklist.

## Critical Things to Know

- **Video is ASYNCHRONOUS.** Agnes *image* generation is synchronous. Create-
  then-poll; a `200` on `POST /v1/videos` only means the task was queued.
- **The endpoint is NOT the OpenAI shape.** Create is `POST /v1/videos`; the
  recommended result read is `GET /agnesapi?video_id=<ID>`. For Flash, the
  safe form ALWAYS includes `&model_name=agnes-video-2.5-flash` (required for
  keyframe/reference modes; `video_id`-only works only for text).
- **Flash `seconds` is a STRING** `"4"`–`"12"` (default `"5"`); **Flash `size`
  is ONLY `"720P"`** — anything else is HTTP 400 `size must be 720P`.
- **Flash `images` max 5** — HTTP 400 `images length must not exceed 5`;
  **Flash `videos` NEVER** — HTTP 400 `videos is not supported`; Flash `n` only 1.
- **Flash has no** `width`/`height`/`num_frames`/`frame_rate`/`negative_prompt`/
  `inference_steps` — those are V2.0 fields.
- **V2.0 `num_frames` two hard rules:** `<= 441` AND `8n + 1` (81, 121, 241,
  441 at frame_rate 24 ≈ 3/5/10/18s).
- **Trust the returned dimensions, not the request** — V2.0 normalizes
  width/height/aspect to the nearest `480p`/`720p`/`1080p` preset. Read `size`,
  `seconds`, `metadata.size_mapping` from the response.
- **V2.0 keyframe mode uses `extra_body`.** `extra_body.image` ARRAY +
  `extra_body.mode: "keyframes"`; plain i2v uses the top-level `image` string.
- **Image inputs must be public URLs.**
- **The API key is referenced, never printed.** `AGNES_AI_API_KEY`; confirm
  SET, never echo/cat/log it.
- **Prompt caps are NOT published** for both models. No invented number; the
  house band (5,000/9,000/19,000) is `PENDING_ACCEPTANCE_TEST`.
- **Pricing is promotional** ($0/s both approved models now). Full
  `agnes-video-2.5` is PAID and never auto-selected.

## Tier and Rate-Limit Awareness

Agnes meters usage on two axes at once — requests per minute (access type) and
daily/weekly quota (Token Plan tier) — and neither is a static skill constant.
For video the Token Plan caps **500 video-seconds per day** on every paid tier
(Starter/Plus/Pro identical), and flash + v2.0 are the only video models in the
plan. Treat HTTP `429` as the live source of truth and back off exponentially;
do not hardcode a ceiling. Which tier a box is on is an account property — read
it live from the Agnes console.

## Image-Prompt Band for Input Frames

When a video input frame image is itself generated (GPT-image-2 or Agnes Image
2.1 Flash) it must obey the same 5,000–19,000 stripped-character band enforced
by Skill 63 (`63-agnes-image/prove_agnes_image_prompt_floor.py`). The band
applies to the IMAGE-generation prompt, not the video prompt. When input images
involve a client's LOGO or brand mark, use IMAGE-TO-IMAGE, never text-to-image.
