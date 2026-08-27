---
name: kie-video
description: >
  KIE Video generation via the KIE.ai API. Owns model selection across
  37 video models across all major families (Wan 3.0/2.7, Kling 3.0 Omni/3.0/2.6/2.5 Turbo,
  ByteDance Seedance 2.5/2.0 Mini, PixVerse V6, MiniMax H3, HappyHorse 1.1/1.0,
  Gemini Omni Video, Runway Dedicated, Veo 3.1 Dedicated), payload validation
  against a machine-readable registry, prompt sizing against published limits,
  asynchronous task dispatch with callbacks or polling, and mandatory real visual QC.
metadata:
  version: "1.0.0"
  priority: HIGH
---

# KIE Video — Model Selection, Validation, Dispatch, and QC

The KIE.ai API serves 37 video models across two primary integration tiers:
1. **Unified Market API** (`POST https://api.kie.ai/api/v1/jobs/createTask`) for Wan, Kling, ByteDance Seedance, PixVerse, MiniMax, HappyHorse, and Gemini Omni.
2. **Dedicated APIs** (`POST /api/v1/runway/generate` and `POST /api/v1/veo/generate`) for Runway and Google Veo 3.1.

All video tasks are asynchronous: HTTP 200 from createTask or dedicated endpoints means the task was CREATED/QUEUED, never completed. This skill owns the entire lifecycle: pick the model, size the prompt, validate the payload, dispatch, wait (callback or poll), and visually QC the multi-frame video result.

## Routing Architecture & Policy

- **Generic Video Routing:** Generic video requests route through the provider router to either **Agnes Video (Skill 64)** or **KIE Video (Skill 67)**.
- **Explicit Model Wins:** When a specific model, family, or dedicated provider is named by the user or department manifest, that selection is strictly honored. Never override an explicit pick.
- **Autonomous Capability Hierarchy (when unspecified):**
  1. **Long-Form Narrative / Multi-Reference (>15s to 30s):** `wan/3-0-video` (or `wan/3-0-video-prime` for high throughput). Supports up to 20K char prompts, 10 images, 5 video clips, 5 audio tracks. Alternative: `bytedance/seedance-2-5` (up to 30s, 50 combined assets, 30K prompt cap).
  2. **Multi-Shot Storyboards & Sequence Control:** `kling-3.0-omni/text-to-video` (up to 6 shots, 512 chars/shot, 3,072 total cap) or `kling-3.0/video` (up to 5 shots).
  3. **High-Resolution 2K Native:** `minimax-h3/text-to-video` or `minimax-h3/reference-to-video` (7,000 char cap, default 2K resolution).
  4. **Slot-Governed Subject & Character Consistency:** `gemini-omni-video` (up to 3 character IDs, 7 reference slots, 20K prompt cap).
  5. **Video Editing & Repainting:** `wan/2-7-videoedit` (1 source video ≤100MB, 2–10s, optional reference image).
  6. **Puppet Motion Transfer:** `kling-3.0/motion-control` (1 driving video + 1 character portrait).
  7. **Short + Cheap / Fast Turnaround:** `kling/v2-5-turbo-text-to-video-pro` or `bytedance/seedance-2-mini`.
  8. **Dedicated Providers:** `runway` (`POST /api/v1/runway/generate`) and `veo3`/`veo3_fast`/`veo3_lite` (`POST /api/v1/veo/generate`).
  9. **Targets above 30s:** multi-clip plan per references/models.md "Clip Planning for Long Targets" (N = ceil(target/max)); no single continuous clip exceeds 30s on any KIE model.

## Mandatory Sequence: route -> select -> validate -> dispatch

1. **Normalize the alias** (`scripts/normalize_alias.py`) — Transcription errors and abbreviations ("Kling O3", "Wan 3 Prime", "Seed Dance", "Mini Max", "Runway Gen3", "Veo 3.1") resolve to canonical family names.
2. **Select** (`scripts/select_video_model.py`) — Maps natural-language video request to canonical model ID and task mode, or returns alternatives.
3. **Validate the prompt** (`scripts/validate_prompt.py`) — Model-aware character band check against registry hard caps (Rules A–E). Verified caps hard-fail (exit code 2); NOT_PUBLISHED/LIVE_PROBE_REQUIRED warn with proposed bands.
4. **Validate the payload** (`scripts/validate_payload.py`) — Endpoint matching, durations, resolutions, media reference counts/sizes, and per-family constraints validated before dispatch to prevent wasted credits.
5. **Dispatch & Monitor** — POST to createTask or dedicated endpoint. Wait via Skill 46 Webhook Callback (`callBackUrl`) or stepped recordInfo polling (3s -> 5s -> 10s -> 15s; max 15 min).
6. **QC** — Perform multi-frame visual QC on downloaded asset (Frame 0, Midpoint, Final Frame; references/qc.md). Retry along the 5-step controlled retry ladder.

## Registry & Prompt Doctrine

- `models.json` contains all 37 verified entries with exact first-party endpoints, caps, and parameters.
- Standard house band: desired min 5,000 chars, target ~9,000 chars, preferred max 19,000 chars (for models with cap ≥20,000). For smaller cap models, enforce high-density compression without losing control domains.

## Prerequisites & Auth

- TYP (Skill 01), BYUP (Skill 02), and KIE Setup (Skill 07) required.
- Credential: `KIE_API_KEY` (Authorization: Bearer $KIE_API_KEY). Check SET without printing.
- Retention: Generated media retained for 14 days on KIE; download URLs expire in ~24h. Persist media immediately.

## Files in This Folder

1. **SKILL.md** — You are here.
2. **models.json** — 37-model machine-readable registry.
3. **references/models.md** — Golden limits matrix and routing guide.
4. **references/prompt-policy.md** — Character prompt policy and 17-part prompt structure.
5. **references/api-patterns.md** — API endpoints, callback HMAC verification, and polling.
6. **references/qc.md** — Multi-stage video QC and 5-step retry ladder.
7. **INSTRUCTIONS.md** — Daily operational walkthrough.
8. **INSTALL.md** — Credential and connectivity installation checks.
9. **EXAMPLES.md** — Worked examples (Wan 3.0, Kling Omni, Veo 3.1, Runway, PixVerse).
10. **CORE_UPDATES.md** — Core file configuration blocks.
11. **QC.md** — Verification checklist.
12. **wire.sh** — Idempotent core wiring script.
13. **scripts/** — `select_video_model.py`, `validate_prompt.py`, `validate_payload.py`, `normalize_alias.py`.
