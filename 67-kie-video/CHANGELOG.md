# Changelog - kie-video

All notable changes to this skill are documented here.

---

## [2.1.2] - 2026-10-06 - feat: `validate_prompt.py` uses the rule 12 length band (merged with the capability fix)

- KIE prompt rule 12 (owner order 2026-10-05): prompt length is 95 to 100 percent of the model maxLength, hard floor 80 percent, hard ceiling 100 percent, measured by the one shared enforcer `shared-utils/kie_prompt_enforcer.py` (wraps Skill 74 `prompt-budget --check`); the gate keeps no band of its own and its rejection names the exact characters to add or cut. Models with no limit anywhere (NOT_PUBLISHED, LIVE_PROBE_REQUIRED) are UNKNOWN with no floor; the policy-owner cap in models.json applies when the adapter has none. Exit 1 below the 80 percent floor, exit 2 above the max. Self-test: 23 of 23.

## [v2.1.1] - 2026-10-06 - fix: an explicitly named unknown model must be a video model

- `validate_payload.py`: a model not in `models.json` that Skill 74 validates is accepted only when its capability matches "to video" (text, image, video or speech to video); a non-video or unknown capability is refused. Two new self-test cases (image model, unknown capability); self-test 32/32 became 34/34. Version roll to v2.1.1 (`SKILL.md`, `QC.md`, `skill-version.txt`).

---

## [v2.1.0] - 2026-10-06 - feat: dispatch runs through Skill 74 (validate, preflight, submit), registry is the curated policy

- `INSTRUCTIONS.md` Step 5 and `SKILL.md`: Market dispatch first runs `kie_live_adapter.py validate` (live schema, registry fallback) and `preflight --units <seconds>` (balance must cover price x 1.30), then `submit --mode active` (production batches add `--callback-url` of the Skill 46 relay), then multi-frame QC. `skipped` (adapter off or shadow) falls back to the curl path; adapter absent skips the first two steps with a note.
- `validate_payload.py` (same wiring Skill 66 got in v1.1): a Market model that is NOT in `models.json` is validated by Skill 74 against its live schema (registry snapshot fallback) instead of being rejected outright, with a warning that it is an explicit pick only. Adapter absent or silent: the old "not present in registry" rejection. Dedicated Runway and Veo payloads are never routed this way. New `scripts/adapter_bridge.py`. Self-test 29/29 became 32/32.
- No auto-latest for video: a new live model is DISCOVERED (`discover --modality video`), never selected or made a default.
- `models.json` is described as the CURATED POLICY and verified-override registry (`registry_policy.role`).

### Open item (owner decision, not changed here)
- KIE's live catalog (Skill 74 registry snapshot, 2026-10-06) lists `runway`, `veo-3-1` and `veo/*` whose schema declares `/api/v1/jobs/createTask`, while this skill's curated route is the dedicated `/api/v1/runway/generate` and `/api/v1/veo/generate` routes. This change keeps the curated route as the dispatch route and only adds `price` and `preflight` for the matching catalog id. Which route is authoritative is the owner's call.
- Version roll to v2.1.0 (`SKILL.md`, `QC.md`, `skill-version.txt`, three script `VERSION` constants). Select 43/43, `validate_prompt` 17/17, normalize PASS.

---

## [v2.0.4] - 2026-10-05 - docs: wording fix in the v2.0.3 entry

- The v2.0.3 entry said the `sync` change was listed as investigate-only in the "release notes"; it was the PR #1492 text. Corrected. Version roll to v2.0.4 (`SKILL.md`, `QC.md`, three script `VERSION` constants). Self-tests unchanged: select 43/43, `validate_prompt` 17/17, `validate_payload` 29/29, normalize PASS.
- Archive decision (applies to 07, 46, 66, 67, 68): the `NN-*.skill` zips are not rebuilt. See the PR for the evidence: `install.sh` Step 5 (lines 3772-3802) copies every file in each skill folder as a plain file and `update-skills.sh` (line 6148) runs `cp -r` on the whole folder; neither unzips a `.skill`.

---

## [v2.0.3] - 2026-10-05 - docs: record the sync flag change truthfully

### Corrected record
- v2.0.2 flipped `sync` from `true` to `false` on all 37 `models.json` entries, but PR #1492 text listed it under "investigated, not changed". It WAS changed. This entry is the accurate record.
- How `sync` is consumed: none of the four scripts in this skill (`select_video_model.py`, `validate_payload.py`, `validate_prompt.py`, `normalize_alias.py`) reads the field, and no 67 document depends on it, so the flip changes registry data only and no behaviour here. Consumers elsewhere in the repo could not be searched, so they are undetermined.
- Why `false` is correct: every KIE video route in this registry (Market `createTask`, Runway `generate`, Veo `generate`) is asynchronous (create, then poll or callback), which `SKILL.md`, `INSTRUCTIONS.md` and `references/api-patterns.md` all state. The sibling registries use `false` for asynchronous work (66: 32 of 32; Agnes Video: 2 of 2). `true` would mean "result in the create response", which none of these models does. Verified: 37 of 37 entries are `false`.
- Version roll to v2.0.3 (`SKILL.md`, `QC.md`, three script `VERSION` constants). Self-tests unchanged: select 43/43, `validate_prompt` 17/17, `validate_payload` 29/29, normalize PASS.
- The prebuilt `67-kie-video-1.0.0.skill` archive is not rebuilt (no packaging script in `scripts/`, archive already stale).

---

## [v2.0.2] - 2026-10-05 - fix: version drift, registry sync flag, api_family spelling, retention prose

### Fixed
- Version drift: `SKILL.md` carried a nested `metadata.version` of 1.0.0 and `QC.md` asserted v1.1.1 while `skill-version.txt` said v2.0.1. `SKILL.md` now has top-level `version: v2.0.2` (nested rolled), `QC.md` asserts v2.0.2, and the `VERSION` constants in the three validator scripts follow.
- Registry data defect: all 37 `models.json` entries had `sync: true`, yet every KIE video task is asynchronous (SKILL.md, INSTRUCTIONS.md, api-patterns.md) and the sibling registries use `sync: false` for asynchronous work (66: 32 of 32; Agnes Video 64: 2 of 2). No script in this skill reads the field, so the change is data only; all 37 are now `sync: false`.
- Docs said `api_family: "veo-dedicated"` (`INSTRUCTIONS.md`, `references/api-patterns.md`); the registry and validator use `veo3-dedicated`. Docs corrected.
- `references/api-patterns.md` success example used a result host (`file.aiquick.net`) that is not a documented KIE result host; it now uses `tempfile.aiquickdraw.com` and shows the parsed `response.resultUrls` copy next to the `resultJson` string.
- Retention: Result retention prose now reads: KIE documents 14 days for generated media but its task-detail page says result URLs typically expire after 24 hours; download/persist immediately. Edited in `SKILL.md`, `INSTRUCTIONS.md`, `QC.md`, `CORE_UPDATES.md`, `wire.sh`, `references/api-patterns.md`.

### Migration Notes
- `CORE_UPDATES.md` and the `wire.sh` TOOLS block changed (retention line); re-run `bash wire.sh` on existing boxes (idempotent).
- The prebuilt `67-kie-video-1.0.0.skill` archive was not regenerated here.
- Risk level: LOW.

---

## [2.0.0] - 2026-08-31 - fix: QC.md version expectation matches skill-version.txt after media-limits repack

- `QC.md` checklist no longer asserts `skill-version.txt` reads `v1.0.0` (it
  has been `v1.1.0` since the media-limits repack); the expectation is now
  `v1.1.1`, matching the current `skill-version.txt`.

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

## [v2.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
