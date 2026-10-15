---
name: agnes-video
description: >
  Endpoint reference and asynchronous workflow for the one approved Agnes
  video model, agnes-video-2.5-flash (string seconds 4-12, 720P only, modes
  text/keyframe/reference), on the Agnes AI API gateway. agnes-video-v2.0 was
  retired by the vendor on 2026-09-25 and is active:false in the registry; the
  router refuses it, refuses any request over 12 s with "split into clips of
  12 s or less", and refuses the V2.0-only request surface. Model choice is
  driven by the deterministic router
  scripts/select_agnes_video_model.py (single source of truth; explicit model
  wins; no silent switch), with the create-task / poll-result pattern, reading
  returned size/seconds/metadata as the source of truth.
metadata:

  version: "1.2.0"
  priority: HIGH
---

# Agnes Video — Router + Endpoint Reference (2.5 Flash; V2.0 retired)

Agnes Video is an asynchronous video-generation API reached through the Agnes
AI gateway (`apihub.agnes-ai.com`). One model is approved in this skill:

- **`agnes-video-2.5-flash`** — 720P only, `seconds` is a STRING `"4"`–`"12"`,
  modes `text` / `keyframe` / `reference`, images max 5, videos unsupported,
  n only 1.
- **`agnes-video-v2.0` — RETIRED** by the vendor on **2026-09-25 23:59:59
  (UTC+8)** ("Migrate to the Agnes Video 2.5 series",
  https://wiki.agnes-ai.com/en/docs/agnes-video-v20.md). Its surface
  (`480p`/`720p`/`1080p`, `width`/`height`, `num_frames <= 441` and `8n + 1`,
  `frame_rate` 1–60, `negative_prompt`, `inference_steps`, `extra_body.image[]`
  keyframes, frame-driven duration) is kept in `models.json` as
  `"active": false` only so the router can NAME and refuse it. Nothing routes to
  it and nothing selects it.

**Registry last verified 2026-10-15** (build date; the retirement above was
read from the vendor page on 2026-10-13 for the Agnes Drama Ad Factory build).

**Drama factory note:** the Agnes Drama Ad Factory
(`75-drama-song-ad-factory`) uses **fixed 10-second clips** — one segment is
one `seconds: "10"` Flash keyframe job — so factory runs never approach this
skill's 4–12 s edge.

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

Rules it enforces (spec 11.4, with v2.0 retired 2026-09-25):

- **Explicit model wins** — if the user names a model, validate THAT model.
  Incompatible → `valid: false` with the exact reason; the named model stays in
  the output. **Never silently switch** to a different model. Naming
  `agnes-video-v2.0` now returns `valid: false` with the retirement date and
  URL.
- **Semantic guard** — a 6-image reference request is NEVER reinterpreted as a
  keyframe job (reference vs keyframe are different semantics). It returns
  `valid: false` ("use at most 5 image refs, or use KIE Video"); the old
  fall-through to V2.0 keyframes is gone with V2.0.
- **Video references** — no Agnes video model supports them (vendor HTTP 400
  `videos is not supported`). Video refs are never silently converted to image
  refs; result is `unsupported`, with `handoff: {"provider":"kie"}` ONLY when
  `allow_kie_handoff: true` (KIE Video owns video-reference input).
- **Default** — no explicit model and nothing else said → Flash default (the
  only approved model).
- **Seed alone changes nothing** — seed never forces another model.
- **Over 12 s → refused** — Flash cannot go past 12 s and V2.0 is retired, so
  any `requested_seconds` above 12 returns `valid: false` with
  **"split into clips of 12 s or less"**.
- **The V2.0-only surface → refused** — `480p` / `1080p`, `width` / `height`,
  `num_frames`, `frame_rate`, `negative_prompt`, `inference_steps` are not
  Flash fields and their only model is retired → `valid: false`.
- **Never auto-select `agnes-video-2.5`** — full paid 2.5 is NOT in the token
  plan; `agnes-video-2.5-flash` is the only approved model and the only video
  model in the plan.

## When to Use This Skill

- The user asks to generate a video from a text prompt, an image, or keyframes.
- You need to know the exact create/retrieve endpoints, the Flash string-seconds
  enum, why a V2.0-only request is refused, or which model a request belongs on.
- You are told "use the Agnes video skill".

## Files in This Folder (Reading Order)

1. **SKILL.md** — You are here. Start with this file.
2. **agnes-video-full.md** — Complete endpoint reference: every parameter, all
   curl examples, error messages, normalization, pricing. Its V2.0 sections are
   historical only — that model is retired (see above).
3. **scripts/select_agnes_video_model.py** — Deterministic model router with
   `--self-test` (spec 11.4 / 14 / 18.5). Pure, offline, stdlib only.
4. **models.json** — Machine-readable capability registry (spec 12): endpoints,
   prompt-cap status (NOT_PUBLISHED — never invented), house band, reference
   limits, duration, resolutions, ratios, plan restriction.
5. **INSTRUCTIONS.md** — Operational instructions for running the async flow.
6. **EXAMPLES.md** — Copy-paste curl examples (the v2.0 examples are
   historical — that model is retired).
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
  `inference_steps` — those were V2.0 fields, and V2.0 is **retired** (see
  above), so a request carrying one of them returns `valid: false`.
- **V2.0 is gone, so its `num_frames` rules are history** (`<= 441` AND
  `8n + 1`; 81, 121, 241, 441 at frame_rate 24 ≈ 3/5/10/18s). Do not plan a
  clip on them; the router refuses them.
- **Trust the returned dimensions, not the request** — the service normalizes
  width/height/aspect. Read `size`, `seconds`, `metadata.size_mapping` from the
  response (this normalization was V2.0 behaviour and survives only as a
  reading rule for older results).
- **V2.0 keyframe mode used `extra_body`** (`extra_body.image` ARRAY +
  `extra_body.mode: "keyframes"`). Flash keyframes are `first_frame` /
  `last_frame` only.
- **Image inputs must be public URLs.**
- **The API key is referenced, never printed.** `AGNES_AI_API_KEY`; confirm
  SET, never echo/cat/log it.
- **Prompt caps are NOT published** for the model. No invented number; the
  house band (5,000/9,000/19,000) is `PENDING_ACCEPTANCE_TEST`.
- **Pricing is promotional** ($0/s for `agnes-video-2.5-flash` now). Full
  `agnes-video-2.5` is PAID and never auto-selected.

## Tier and Rate-Limit Awareness

Agnes meters usage on two axes at once — requests per minute (access type) and
daily/weekly quota (Token Plan tier) — and neither is a static skill constant.
For video the Token Plan caps **500 video-seconds per day** on every paid tier
(Starter/Plus/Pro identical), and `agnes-video-2.5-flash` is now the only video
model in the plan (v2.0 was retired 2026-09-25). Treat HTTP `429` as the live
source of truth and back off exponentially;
do not hardcode a ceiling. Which tier a box is on is an account property — read
it live from the Agnes console.

## Image-Prompt Band for Input Frames

When a video input frame image is itself generated (GPT-Image-2.5 or Agnes Image
2.1 Flash) it must obey the same 5,000–19,000 stripped-character band enforced
by Skill 63 (`63-agnes-image/prove_agnes_image_prompt_floor.py`). The band
applies to the IMAGE-generation prompt, not the video prompt. When input images
involve a client's LOGO or brand mark, use IMAGE-TO-IMAGE, never text-to-image.
