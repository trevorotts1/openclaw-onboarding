# Changelog - kie-video

All notable changes to this skill are documented here.

---

## [v1.0.0] - 2026-08-26 - feat: new KIE Video skill (Skill 67) — model selection, validation, async dispatch, and multi-frame visual QC for KIE.ai video families

### Added
- Initial release covering 37 video models across all major families on the KIE.ai API:
  - Wan 3.0 Video (`wan/3-0-video`, `wan/3-0-video-prime`)
  - Kling 3.0 Omni (`kling-3.0-omni/text-to-video`, `image-to-video`, `transformation`, `reference-to-video`)
  - Kling 3.0 Single/Multi (`kling-3.0/video`) & Motion Control (`kling-3.0/motion-control`)
  - Kling 2.6 Motion Control (`kling-2.6/motion-control`)
  - Kling 2.5 Turbo (`kling/v2-5-turbo-text-to-video-pro`, `image-to-video-pro`)
  - ByteDance Seedance (`bytedance/seedance-2-5`, `seedance-2-mini`)
  - PixVerse V6 (`pixverse-v6/text-to-video`, `image-to-video`, `transition`, `extend`, `reference-to-video`)
  - MiniMax H3 (`minimax-h3/text-to-video`, `image-to-video`, `reference-to-video`)
  - Wan 2.7 Video (`wan/2-7-r2v`, `wan/2-7-videoedit`, `wan/2-7-text-to-video`, `wan/2-7-image-to-video`)
  - HappyHorse 1.1 (`happyhorse-1-1/text-to-video`, `image-to-video`, `reference-to-video`)
  - HappyHorse 1.0 (`happyhorse/text-to-video`, `image-to-video`, `reference-to-video`, `video-edit`)
  - Gemini Omni Video (`gemini-omni-video`)
  - Runway Dedicated (`runway`)
  - Google Veo 3.1 Dedicated (`veo3`, `veo3_fast`, `veo3_lite`)
- `models.json` machine-readable registry: 37 entries with exact first-party endpoints (`createTask` vs dedicated `/api/v1/runway/generate` and `/api/v1/veo/generate`), duration windows, resolution enums, media reference caps, and verified prompt caps.
- Alias normalization (`scripts/normalize_alias.py`): Kling Omni variations, Wan 3.0/Prime variations, Seedance, PixVerse, MiniMax/Hailuo, HappyHorse, Gemini Omni, Runway, and Veo aliases.
- Model selector (`scripts/select_video_model.py`): natural-language video request to canonical model ID and task mode; capability hierarchy routing (long-form >15s -> Wan 3.0/Seedance 2.5; multi-shot -> Kling Omni; 2K -> MiniMax H3; character slots -> Gemini Omni; puppet -> Kling Motion Control; video edit -> Wan 2.7; short+cheap -> Kling 2.5 Turbo); deterministic `--self-test` covering >30 test cases.
- Prompt validator (`scripts/validate_prompt.py`): spec 5 rules A–E adapted for video — verified ≥20K (Rule A, Wan 3.0/Gemini Omni/Seedance 2.5), verified 5K–19,999 (Rule B, MiniMax/PixVerse/Wan 2.7/HappyHorse), verified <5K (Rule C, Kling Omni 3072, Kling 2.5/motion 2500), NOT_PUBLISHED/LIVE_PROBE_REQUIRED (Rule E). Exit code 0/1/2 semantics.
- Payload validator (`scripts/validate_payload.py`): endpoint matching (createTask vs dedicated), duration window checks, resolution enums, media reference limits, Runway 1080p 5s constraint, and auth_env validation.
- References: `models.md` (golden limits matrix and routing guide), `prompt-policy.md` (17-part video prompt structure and compression examples), `api-patterns.md` (generic createTask/recordInfo, dedicated Runway/Veo APIs, webhook HMAC verification, and polling backoff), `qc.md` (multi-frame sampling: Frame 0, Midpoint, Final Frame, and 5-step controlled retry ladder).
- Core documentation: `SKILL.md`, `INSTRUCTIONS.md`, `INSTALL.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, `QC.md`, `PREREQS.json`, `skill-version.txt`, and idempotent `wire.sh`.
