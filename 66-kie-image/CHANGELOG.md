## [2.2.12] - 2026-11-09 - Ratio coherence: GPT Image 2.6 now matches the vendor 16-member enum (merge of main's 2.2.11 entry)

- `models.json`: both `gpt-image-2-6/sunburst` rows' `aspect_ratios` set to the vendor live schema
  (`auto, 1:1, 3:2, 2:3, 4:3, 3:4, 5:4, 4:5, 16:9, 9:16, 2:1, 1:2, 21:9, 9:21, 3:1, 1:3` -- 16 members,
  verified against `74-kie-live-adapter/references/kie-model-registry.json` ->
  `gpt-image-2-6/sunburst-text-to-image` `input_fields.aspect_ratio.enum`) and
  `ratio_resolution_exclusions` set to `[]`. The old 27:16/16:27/9:8/8:9 entries were 2.5-era and are
  not in the 2.6 schema. The superseded Ruling 6 ratio prose in both rows now records that it does not
  apply to 2.6. (Owner cap 20,000 from main carried unchanged on both rows.)
- `scripts/validate_payload.py`: the 2.5 per-resolution exclusion branch no longer matches 2-6 ids;
  2.6 is validated by enum membership alone. Self-test cases added for 2.6 (3:1, 1:3, 5:4, 2:1 and
  9:21-at-4K accepted; 27:16 rejected; legacy-2 and 2.5 rules not applied to 2.6).
- `scripts/select_image_model.py`: the 2.5-only ratio constants (`GPT_2_5_LEGACY_ONLY_RATIOS`,
  `GPT_2_5_RATIO_SUBSTITUTIONS`) are gated to the 2.5 family, so 3:1/1:3/9:21 stay on 2.6 and
  5:4/4:5/2:1/1:2 are passed through unsubstituted. Self-test cases updated; 2.5 behaviour re-tested
  under an explicit 2.5 pin.

## [2.2.11] - 2026-11-09 - fix: restore the PENDING_ACCEPTANCE_TEST status clause dropped from models.json notes (INST-001 #23)

- `models.json` notes: the `hard-enforcement status PENDING_ACCEPTANCE_TEST, validators warn only` clause the gapfill dropped is restored on the legacy GPT Image 2 entries (with the owner-confirmed 25,000 cap band restated) and on the 2.5 entries. No cap, band, id, alias, ratio or ordering changed.

## [2.2.10] - 2026-11-09 - GPT Image 2.6 owner cap 20,000 recorded in models.json

- `models.json`: `owner_prompt_cap_chars: 20000` on both 2.6 sunburst entries (t2i + i2i). The existing `policy_owner_cap` precedence in the 74 adapter and 66 validator now resolves max 20000 with `limit_source` owner-ruling.

## [2.2.9] - 2026-11-09 - 2.6 named as the ratio-rule default; remaining 2.5 default claims corrected

- `models.json` `owner_preferred_default` / `_note`: 2.6 Sunburst is the current default since #2860; Ruling 6 is retained as history and 2.5 is retained by operator ruling 2026-09-09. `SKILL.md`: the `(default)` ratio-rule label moved to 2.6, with the 2.5 ratio facts kept attached to 2.5. Two stale comments in `normalize_alias.py` and `select_image_model.py` corrected. No executable logic changed; both self-tests pass.
- Second pass (same version): the legacy GPT Image 2 `status_note`/`notes` rows no longer call 2.5 the default, and five more comments (`normalize_alias.py:64`, `:144-145`, `select_image_model.py:41`, `:204-208`, `validate_payload.py:335`) no longer describe 2.5 as the default. Comments and JSON prose only; no executable line, mapping, assertion, ratio table or test changed; a third pass relabelled the two 2.5 rows' own `status_note`/`notes` as RETAINED and no longer the default.
- Fourth pass (same version): the two 2.5 rows are marked `status: legacy` in data as well as prose; the 2.6 rows keep `status: default`. No key, id, alias, cap, ratio, note or ordering changed.

# Changelog - kie-image
## [2.2.8] - 2026-11-09 - G3 lockstep roll for the batch fold (no behaviour change)

- Version bumped so the folded content carries the version G3 requires above main. No functional change.

## [2.2.6] - 2026-11-08 - G3 lockstep roll (PR 2868)

- `SKILL.md` frontmatter and `skill-version.txt` rolled 2.2.5 -> 2.2.6 so this skill's changelog entry carries the version bump G3 requires above main. No behavior change; main's one prompt-band rule (owner rule 12) is carried unchanged.

## [2.2.5] - 2026-11-08 - G3 lockstep roll (PR 2868)

- `SKILL.md` frontmatter and `skill-version.txt` rolled 2.2.4 -> 2.2.5 so the changelog entries added to this skill carry the required version bump. No behavior change; the prompt gate is unchanged.

## [2.2.4] - 2026-11-08 - G3 lockstep rolls (F18 touch, CI clear)

- `SKILL.md` frontmatter and `skill-version.txt` rolled 2.2.2 -> 2.2.4 by the F18 version bump (2026-11-07) and the PR 2864 CI-clear roll (2026-11-08): prompt-gate prompt-budget enforcement carries forward, no new behavior in this entry. Entry added so the Skill 07 docs-port changelog gate pins the shipped version.

## [2.2.3] - 2026-11-07 - G3 lockstep roll (F18 touch)

- `SKILL.md` frontmatter and `skill-version.txt` rolled 2.2.2 -> 2.2.3 by the F18 version bump: prompt-gate prompt-budget enforcement carries forward, no new behavior in this entry. Entry added so the Skill 07 docs-port changelog gate pins the shipped version.


- `scripts/validate_prompt.py` carries the merged rule-12 band arithmetic beside the GPT Image 2.6
  slash ids and the owner cap of 20,000 characters (`owner_prompt_cap_chars` outranks the vendor
  schema at limit resolution).
- Version bumped to v2.2.6: main's W19 fold already reached v2.2.5.
- Risk: LOW. Band arithmetic and model ids only; no route or credential changed.


- Every 2.5 reference in this skill now names `gpt-image-2-6/sunburst-text-to-image` (T2I) and
  `gpt-image-2-6/sunburst-image-to-image` (I2I). Skill 88 explicitly calls models.json for
  capability data, the adapter for dispatch.
- `models.json` 2.6 rows carry the real 16-value `aspect_ratio` enum and the owner prompt cap.
- No credential, endpoint or payload shape changed.


## [2.2.2] - 2026-10-09 - fix: key-variable sentence names KIE_API_KEY from the official docs

- `SKILL.md` prerequisites: the sentence "KIE docs use the literal `YOUR_API_KEY` placeholder — nothing documents the env var" was wrong as of 2026-10-09. KIE's own overview page names the variable `KIE_API_KEY` (`export KIE_API_KEY=your_key`). The sentence now says so and cites docs.kie.ai/ai-agent/overview with the date.
- No behavior change. Version roll to v2.2.2 (`SKILL.md`, `skill-version.txt`).

## [2.2.1] - 2026-10-06 - fix: `validate_prompt.py` calls the shared rule 12 enforcer

- `validate_prompt.py` no longer carries its own band math or Skill 74 bridge call: KIE prompt rule 12 (owner order 2026-10-05): prompt length is 95 to 100 percent of the model maxLength, hard floor 80 percent, hard ceiling 100 percent, enforced by the one shared enforcer `shared-utils/kie_prompt_enforcer.py` (wraps Skill 74 `prompt-budget --check`). The gate keeps no band of its own. The models.json cap (live_schema_cap_chars, vendor_hard_cap_chars, owner_observed_cap_chars) is the policy-owner fallback. `adapter_bridge.prompt_budget` is removed (`latest_family` and `validate` stay). Self-test: 30 of 30.
- `validate_payload.py` prompt ceiling now reads `live_schema_cap_chars` first (20,000 for legacy `gpt-image-2`, superseding the N43 25,000 per the KIE live schema of 2026-10-05); before, the legacy route had no ceiling check at all.

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


No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
