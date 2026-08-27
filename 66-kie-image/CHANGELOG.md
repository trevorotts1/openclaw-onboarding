# Changelog - kie-image

All notable changes to this skill are documented here.

---

## [v1.0.0] - 2026-08-26 - feat: new KIE Image skill (Skill 66) — model selection, validation, async dispatch, and real visual QC for KIE.ai Market API image families

### Added
- Initial release covering all 14 spec 7.2 image families on the KIE.ai Market
  API: GPT Image 2 (t2i + i2i), Qwen Image 3.0 / Pro (4 routes), Seedream 5.0
  Pro / Lite / 4.5, Nano Banana 2 / 2 Lite / Pro / legacy, Wan 2.7 Image
  (standard + pro), FLUX.2 (4 routes), Z-Image, Ideogram V3 (t2i/edit/remix),
  Imagen 4 (fast/standard/ultra) — 30 registry entries.
- `models.json` machine-readable registry: per-entry provider,
  canonical_model_id, aliases, modality, tasks, api_family `kie-market`,
  create/query endpoints, vendor_hard_cap_chars/tokens, owner_observed_cap_chars,
  cap_status (`VERIFIED | OWNER_OBSERVED | NOT_PUBLISHED | LIVE_PROBE_REQUIRED`),
  house band fields, reference_images_max, resolutions, aspect_ratios,
  source_url, last_verified_at (every entry, 2026-08-26).
- Alias normalization (`scripts/normalize_alias.py`): Cling->Kling,
  Quinn->Qwen, C Dream/Seed Dream->Seedream, Idiogram->Ideogram,
  Imagine 4->Imagen 4, GPT-img2 / GPT-image 2.0->GPT Image 2,
  Nano Banana Light->Nano Banana 2 Lite. Z-Image is its own family and is
  NEVER merged into Qwen.
- Model selector (`scripts/select_image_model.py`): natural-language request to
  canonical model id; explicit user pick wins; GPT Image 2 preferred default;
  capability fallbacks; deterministic --self-test.
- Prompt validator (`scripts/validate_prompt.py`): spec 5 rules A-E —
  verified >=20K (rule A), verified 5K-19,999 with safe ceiling (rule B),
  verified <5K (rule C), token caps never converted to fake char caps
  (rule D, Qwen 4.5K tokens), NOT_PUBLISHED never invented (rule E). Exit 0/
  1/2 semantics; --strict.
- Payload validator (`scripts/validate_payload.py`): reference counts, MB/
  format, ratio/resolution enums, per-family rules (GPT Image 2 per-resolution
  exclusions + auto/1:1 rules; Wan n/bbox/min-240px; Qwen 3 refs; legacy NB
  10MB; Z-Image T2I-only; Ideogram strength; Seedream 4.5 output_format gap).
- References: `models.md` (human golden matrix + routing guidance),
  `prompt-policy.md` (rules A-E + 15-dimension expansion structure),
  `api-patterns.md` (createTask/recordInfo conventions + per-family schemas),
  `qc.md` (real visual QC + 5-step retry ladder).
- `INSTRUCTIONS.md` (route -> normalize -> select -> validate -> dispatch ->
  poll/callback -> QC), `INSTALL.md` (KIE_API_KEY SET/NOT-SET check,
  credit-free connectivity probe, no autonomous gateway restart),
  `EXAMPLES.md` (GPT Image 2 t2i + i2i, Wan bbox, Seedream i2i, NB2 i2i),
  `CORE_UPDATES.md` + idempotent `wire.sh`, `QC.md`, `PREREQS.json`,
  `CHANGELOG.md`, `skill-version.txt`.
- Every numeric limit carries a quoted first-party source
  (01-kie-common.md / 02-kie-image-a.md / 03-kie-image-b.md fetched 2026-08-26)
  plus source_url; no invented caps. Known inconsistency recorded: GPT Image 2
  docs page text "maximum 20,000 characters" vs spec 7.4 owner-observed ~25K —
  stored per spec 7.4 as OWNER_OBSERVED 25000, LIVE_PROBE_REQUIRED to resolve.
- Packaged `66-kie-image-1.0.0.skill` bundle (SKILL.md, INSTALL.md,
  INSTRUCTIONS.md, EXAMPLES.md, CORE_UPDATES.md, CHANGELOG.md, QC.md,
  PREREQS.json, models.json, references/, scripts/, skill-version.txt).
