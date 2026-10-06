# Changelog - kie-image

## [2.2.0] - 2026-10-06 - feat: dispatch runs through Skill 74 (validate, preflight, submit), registry is the curated policy

- `INSTRUCTIONS.md` Step 5 and `SKILL.md`: every dispatch path first runs `kie_live_adapter.py validate` (live schema, registry fallback) and `preflight` (balance must cover price x 1.30), then submits through Skill 74 (`submit --mode active`, production batches add `--callback-url` of the Skill 46 relay), then this skill's own QC. If submit returns `skipped` (adapter off or shadow) the curl path is used unchanged; if the adapter is absent steps 1 and 2 are skipped with a note.
- `models.json` and `SKILL.md` now describe the registry as the CURATED POLICY and verified-override registry, not the exhaustive catalog and not the live source of limits or prices (`registry_policy.role`). A model missing from it is DISCOVERED, never an automatic default; the only auto-follow stays GPT Image `latest-family` (owner order 2026-10-05).
- Merged PR #1510 (v2.0.5 line) and PR #1514 conflict-free except version markers; version roll to v2.2.0 (`SKILL.md`, `QC.md`, `skill-version.txt`, three script `VERSION` constants).
- Self-tests unchanged in count: select 38/38, `validate_prompt` 30/30, `validate_payload` 49/49, normalize PASS.
- Policy ownership did not move: no model choice, cap or ratio rule was changed.

---

## [2.1.0] - 2026-10-05 - feat: GPT Image auto-latest default and 80-100% prompt budget

- The GPT Image default follows the newest GPT Image generation in KIE's live catalog (owner order 2026-10-05), resolved through Skill 74 `latest-family` by `select_image_model.py`; falls back to the models.json default (GPT Image 2.5 Sunburst) when the adapter is absent or unreachable. Explicit model/alias pins ("gpt image 2.5", "sunburst", canonical ids) and department pins never move. Names that carry version 2 ("gpt image 2", "gpt-image-2", "gpt-img2", "gpt image 2.0") now route to the LEGACY gpt-image-2 family (owner correction 2026-10-06); only version-less names ("gpt image", "gpt-image", "openai image") follow latest-family. Legacy GPT Image 2 routing for 3:1, 1:3, 9:21 and the N43 ratio substitutions are unchanged. The result carries `default_source` and `fallback_default` (the previous default, for a retry when a newly promoted model fails dispatch or validation).
- `validate_prompt.py` now enforces the owner prompt budget through Skill 74 `prompt-budget` (models.json cap as fallback): below 80% of the max is rejected (exact chars to add), above the max is rejected (exact chars to cut), 80-95% warns. The old 5,000 / 9,000 / 19,000 house band is retired. Exit 1 now also covers below the floor; exit 2 is above the max.
- `validate_payload.py` validates a model that is not in models.json (a newly promoted generation) against Skill 74's live schema.
- New `scripts/adapter_bridge.py` (finds the sibling adapter; env KIE_LIVE_ADAPTER_PATH overrides, empty disables). Self-tests cover: newer generation becomes the default, pin unchanged, adapter unreachable falls back, under-80% and over-max rejected.

All notable changes to this skill are documented here.

---

## [v2.0.5] - 2026-10-05 - fix: Seedream 4.5 edit model id is seedream/4.5-edit

### Fixed
- The registry, selector, alias map, payload validator and docs recorded the Seedream 4.5 edit model as `seedream/4-5-edit`. KIE's own page (https://docs.kie.ai/market/seedream/4-5-edit.md, fetched 2026-10-05) declares the model enum and default as `seedream/4.5-edit` (the `4-5-edit` form is only the docs URL slug and the operationId). Corrected in `models.json`, `scripts/select_image_model.py` (registry and self-test), `scripts/normalize_alias.py`, `scripts/validate_payload.py` (reference-count warning and four self-test cases), `references/api-patterns.md` and `references/models.md`. The `source_url` keeps the real docs slug. A payload using the old id is now rejected as not in the registry, which is correct because KIE would not accept it.
- Version roll to v2.0.5 (`SKILL.md`, `QC.md`, three script `VERSION` constants).
- Self-tests unchanged in count: select 24/24, `validate_prompt` 21/21, `validate_payload` 49/49, normalize PASS.
- The prebuilt `66-kie-image-1.0.0.skill` archive is not rebuilt (no packaging script in `scripts/`, archive already stale, and its filename carries the 1.0.0 it shipped with).

---

## [v2.0.4] - 2026-10-05 - fix: version drift, registry and doc counts, validator CLI docs, retention prose

### Fixed
- Version drift: `SKILL.md` carried a nested `metadata.version` of 1.0.0 and `QC.md` asserted `skill-version.txt` reads v1.0.0 while `skill-version.txt` said v2.0.3. `SKILL.md` now has top-level `version: v2.0.4` (nested rolled), `QC.md` asserts v2.0.4, and the `VERSION` constants in `select_image_model.py`, `validate_payload.py` and `validate_prompt.py` follow.
- Registry count: `SKILL.md` (twice) and `references/models.md` said 30 entries; `models.json` has 32. Prose corrected to 32. (The 2.0.0 entry below records the count at first release.)
- Validator CLI docs follow the code: `INSTRUCTIONS.md` showed `validate_prompt.py <model-id> <prompt-file-or-text>` and `validate_payload.py <model-id> <payload.json> [--strict]`. The scripts take `validate_prompt.py "<prompt>" --model <id> [--prompt-file F] [--strict]` and `validate_payload.py <payload.json|-> [--model <id>]` (no `--strict`). `INSTALL.md` self-test counts corrected to the real 24/24 (selector), 21/21 (prompt) and 49/49 (payload).
- Result shape prose: `INSTRUCTIONS.md`, `EXAMPLES.md`, `references/qc.md` and `references/api-patterns.md` now say `data.resultJson` is a JSON string and `data.response.resultUrls` is the parsed copy (live shape, KIE contract), and Suno-style audio uses `response.data[].audio_url`.
- Retention: Result retention prose now reads: KIE documents 14 days for generated media but its task-detail page says result URLs typically expire after 24 hours; download/persist immediately. Edited in `SKILL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `QC.md`, `CORE_UPDATES.md`, `wire.sh`, `references/api-patterns.md`, `references/qc.md`.

### Investigated, not changed
- `select_image_model.py` maps the aliases `kling` and `cling` to `ideogram-v3` (introduced in the first release, commit 68d80c831, never revisited). Intent is not provable from history (the 2.0.0 notes say Cling->Kling, a video family), and the right behaviour (refuse with an alternative, or route elsewhere) is a design decision, so it is left for the owner.

### Migration Notes
- `CORE_UPDATES.md` and the `wire.sh` TOOLS block changed (retention line); re-run `bash wire.sh` on existing boxes (idempotent).
- The prebuilt `66-kie-image-1.0.0.skill` archive was not regenerated here.
- Risk level: LOW.

---

## [2.0.0] - 2026-08-26 - feat: new KIE Image skill (Skill 66) — model selection, validation, async dispatch, and real visual QC for KIE.ai Market API image families

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

## [v2.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
