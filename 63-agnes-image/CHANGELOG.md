# Changelog - agnes-image

All notable changes to this skill are documented here.

---

## [2.1.6] - 2026-10-15 - feat: Agnes Image 2.5 Flash becomes the default (Signature Launch S63)

### Why
The publisher catalog lists `agnes-image-2.5-flash` as the current image
generation/editing model, with the same endpoint, request/response contract,
size x ratio dimension table, and pricing as 2.1. The registry entry and the
SKILL.md default prose landed earlier (v2.1.5, AGN workstream), but the code
still hard-pinned 2.1: both validators rejected a well-formed 2.5 payload and
the alias normalizer resolved every generic alias to 2.1. This release makes
the default real in code and aligns every consumer-facing surface.

### What changed
- **Default resolution**: new `scripts/resolve_model.py` resolves unpinned and
  generic requests to `agnes-image-2.5-flash`; explicit `agnes-image-2.1-flash`
  pins are preserved as legacy behavior with provenance (default / explicit_pin
  / explicit_alias / ambiguous for stored configs without provenance). Text
  (`agnes-2.5-flash`) and video (`agnes-video-2.5-flash`) IDs are rejected by
  this image adapter.
- **Validators**: `scripts/validate_payload.py` and `scripts/validate_prompt.py`
  accept both image models (2.5 default), reject text/video IDs with a clear
  error, and gained self-test fixtures for both. `scripts/normalize_alias.py`
  maps generic aliases to 2.5 and keeps explicit 2.1 aliases on 2.1.
- **Registry**: `models.json` entries carry `launch_role` ("default" for 2.5,
  "legacy" for 2.1) so consumers never guess the default from list order.
- **New support modules**: `scripts/launch_prompt_policy.py` (named
  `signature_launch_completeness` launch policy plus the preserved
  `legacy_house_band` profile), `scripts/provider_receipt.py` (provider-neutral
  receipt; Agnes receipts carry no task ID and refuse KIE identifiers), and
  `scripts/response_persist.py` (synchronous response validation, real image
  sniffing/dimensions, atomic persistence).
- **Reference purposes (docs)**: SKILL.md and EXAMPLES.md now state the
  per-reference rule (preserve-the-mark for logo/identity references,
  style-only directive for style references), matching the corrected rule
  already coded in `validate_prompt.py` and `references/prompt-policy.md`.
- **Transport policy (S63-07)**: `scripts/transport.py` enforces credential
  presence (value never logged), approved-budget preflight with explicit
  unverified-cost handling, 401/403 stop, bounded 429 backoff and 5xx retry,
  and ambiguous-timeout handling that never resubmits a paid generation
  blindly.
- **Docs/version alignment**: agnes-image-full.md, references, INSTRUCTIONS,
  INSTALL, EXAMPLES, CORE_UPDATES, QC, wire.sh and qc-agnes-image.sh name 2.5
  as the default with 2.1 as the explicit legacy pin. `skill-version.txt` and
  the SKILL.md frontmatter version are both v2.1.6 (the frontmatter had been
  left at 2.1.2 when the registry bumped to v2.1.5).

### Not changed
Historical changelog entries below keep their original 2.1 wording. The
`agnes-image.skill` bundle is repacked at release time from this folder, not
in this change. No live provider call was made for this change; live smoke
(S63-10) remains a separately authorized step.

## [2.1.2] - 2026-09-17 - fix: valid YAML frontmatter version, repacked .skill bundle, backfilled changelog

### Why
`SKILL.md` frontmatter carried `version: ""2.1.0""` with doubled double quotes. That is invalid
YAML: a loader reading the block either errors or silently drops the field. The value was also
stale against `skill-version.txt` (v2.1.1), and the packaged `agnes-image.skill` bundle still
shipped an inner `SKILL.md` stamped `1.2.0`. Releases 2.1.0 and 2.1.1 shipped with no CHANGELOG
entry at all.

The repo-wide drift gate `scripts/qc-assert-skill-frontmatter-version.sh` could not catch any of
this. It reads only a TOP-LEVEL `version:` at column 0, and this skill keeps its version nested
under `metadata:`, so Skill 63 is reported as SKIPPED by that gate rather than checked.

### What changed
- **Valid frontmatter version**: `metadata.version` is now `"2.1.2"`, quoted in the same shape as
  the `64-agnes-video` control, and it agrees with `skill-version.txt`.
- **`skill-version.txt`**: v2.1.1 to v2.1.2.
- **Repacked `agnes-image.skill`**: rebuilt from the folder so every bundled file matches the
  folder byte for byte. The bundled `SKILL.md` now carries 2.1.2 instead of the stale 1.2.0, and
  three files that drifted across the 2.1.0 and 2.1.1 releases were resynced: `models.json`,
  `references/prompt-policy.md` and `scripts/validate_prompt.py`. Archive layout is unchanged:
  the same 19 files in the same order at the same flat paths, with `CHANGELOG.md` and the bundle
  itself excluded exactly as before.
- **Backfilled changelog**: entries for 2.1.0 and 2.1.1 added below.

### Not changed
No behavioral change. No script, reference, registry, or prompt-policy content was touched.

## [2.1.1] - 2026-09-10 - chore: prompt-policy reference follows the Kie GPT Image 2.5 migration

### Why
Backfilled. This release shipped with no CHANGELOG entry.

### What changed
- `references/prompt-policy.md`: the social-planner scoped override and the "no invented vendor
  cap" note were restated for the Kie GPT Image 2.5 default (operator ruling 2026-09-09), with
  legacy GPT Image 2 retained for aspect ratios 3:1, 1:3 and 9:21. The Agnes position is
  unchanged: no published Agnes cap exists, so the house band governs.
- `skill-version.txt`: v2.1.0 to v2.1.1, as part of the registry restamp for that migration.

Source commits: `5070ba221` (prompt-policy text), `fdf4e7cb1` (version restamp).

## [2.1.0] - 2026-09-08 - chore: version alignment for the W2 scoped prompt-policy batch

### Why
Backfilled. This release shipped with no CHANGELOG entry.

### What changed
- Version alignment only. The release commit records that the W2 scoped prompt-policy override
  touched this skill (`references/prompt-policy.md`, `models.json`,
  `scripts/validate_prompt.py`), but those content commits are not reachable in this repository's
  available history, which is shallow. The entry is therefore recorded at the level the release
  commits state and is not reconstructed further.
- `skill-version.txt`: v2.0.x to v2.1.0.
- `SKILL.md` frontmatter synced to the new version. That sync is what introduced the doubled
  double quotes corrected in 2.1.2.

Source commits: `956939292` (version bump), `abbf5fdab` (frontmatter sync).

## [2.0.0] - 2026-08-26 - fix: prompt policy alignment, remove invented 25K cap, add models.json registry and validators

### Why
First-party documentation for Agnes Image 2.1 Flash (`apihub.agnes-ai.com`) does NOT publish a hard prompt character limit. Earlier revisions of Skill 63 erroneously asserted that "the API accepts up to 25,000 chars" and enforced a mandatory hard rejection below 5,000 and above 19,000 characters. That 25K figure belongs to KIE GPT Image 2 (owner-observed), not Agnes. Furthermore, Spec §12 and §14 mandate machine-readable capability registries (`models.json`), structured references (`references/`), and deterministic testable validator scripts (`scripts/`).

### What changed
- **Removed Invented 25K Cap**: Clarified that vendor hard cap is `NOT_PUBLISHED`.
- **House Prompt Band Alignment (Spec §5 & §10.5)**: Reframed 5,000–19,000 chars (~9,000 target) as a house target band, not a vendor law. Short user prompts are expanded, not hard-rejected (§5.3). Prompts above 19,000 chars trigger non-fatal advisory, not hard rejection.
- **Machine-Readable Capability Registry**: Created `models.json` for `agnes-image-2.1-flash` with full dimension matrix (8 ratios × 4 tiers), endpoints, quotas, and sync execution flag.
- **Structured References**: Added `references/prompt-policy.md`, `references/api-patterns.md`, and `references/qc.md`.
- **Deterministic Validators & Selectors**:
  - Added `scripts/validate_prompt.py` (model-aware prompt validator with `--self-test`).
  - Added `scripts/validate_payload.py` (JSON request payload validator with `--self-test`).
  - Added `scripts/normalize_alias.py` (alias normalizer with `--self-test`).
  - Updated `prove_agnes_image_prompt_floor.py` to align with non-destructive prompt policy while preserving logo-I2I and style-reference quality gates.
- **Repackaged `.skill` bundle**: Built updated `agnes-image.skill` archive containing the modern skill structure.

## [v1.1.0] - 2026-08-03 - fix: the core-file updates are now EXECUTED by `wire.sh`, not pasted as a recipe

### Why
Skill 63 shipped no installer, so its `CORE_UPDATES.md` was consumed by the generic
merger in `update-skills.sh`, which copies a section body VERBATIM. What landed in every
box's `AGENTS.md` / `TOOLS.md` / `MEMORY.md` was the literal INSTRUCTION -- the word
`Add:`, a markdown code fence, the payload, the closing fence -- the recipe pasted instead
of executed. The pointer inside it was ALSO wrong: `63-agnes-image/agnes-image-full.md` is a ROOTLESS
relative path that resolves against whatever directory the agent happens to be in, so the
reference could never be opened reliably.

### What changed
- **New `wire.sh`** -- performs the add. It writes one compact pointer block per core file
  behind its version-free `<!-- BEGIN/END skill:63-agnes-image:<target> -->` marker,
  REPLACE-IN-PLACE, so a re-run is byte-identical and an already-pasted box is HEALED
  rather than appended to. The master-files path is RESOLVED to an absolute path on the box.
- It stamps `<!-- skill:63-agnes-image:core-update-applied -->`, which makes the generic merger
  short-circuit for this skill so the recipe can never be pasted again.
- It touches only its OWN `skill:63-agnes-image:*` markers -- the shared idempotency
  stamp bank ~44 other installers key on is never read, moved or removed.
- Backups are timestamped and taken ONLY when a file actually changes.
- `CORE_UPDATES.md` now documents that `wire.sh` performs these updates.

### Evidence (scratch only)
Seeded a fixture with the EXACT pasted junk carried on a live box: after `wire.sh` the
literal `Add:`, the code fences and the unfilled `[MASTER_FILES_FOLDER]` variable are all
gone, exactly one BEGIN/END pair per target remains, the pointer is an absolute path, and a
second run is byte-identical across AGENTS.md / TOOLS.md / MEMORY.md with no new backup.

## [v1.0.1] - August 1, 2026

### Changed
- Updated the referenced Agnes text/reasoning model from `agnes-2.0-flash` to
  `agnes-2.5-flash` in the shared-credential notes (SKILL.md, INSTALL.md,
  PREREQS.json, QC.md, CORE_UPDATES.md, agnes-image-full.md). The image model
  itself (`agnes-image-2.1-flash`) is unchanged.

## [v1.0.0] - July 21, 2026

### Added
- Initial release: Agnes Image 2.1 Flash endpoint reference (Skill 63).
- Synchronous text-to-image and image-to-image via
  `POST https://apihub.agnes-ai.com/v1/images/generations`
  (model `agnes-image-2.1-flash`) — one request returns the finished image
  (`data[0].url` or `data[0].b64_json`); no task polling.
- Documents required fields (`model`, `prompt`, `size`), the `1K`/`2K`/`3K`/`4K`
  size tiers crossed with aspect `ratio`, and the full ratio×tier
  output-dimension table (for example `16:9` `2K` = `2624x1472`).
- Calls out the two gotchas: `response_format` belongs in `extra_body` (not the
  top level), and image-to-image needs no `tags`.
- Rate-limit / tier awareness sourced from the vendor catalog (dated 2026-06-28)
  with confirmed and UNVERIFIED cells flagged; keys tier behavior off
  operator-set config and HTTP 429, never a hardcoded ceiling.
- References the EXISTING fleet credential `AGNES_AI_API_KEY` (SET/NOT-SET only;
  value never printed).
- Bundled `qc-agnes-image.sh` install QC that fails closed on a corrupted
  reference doc, plus `PREREQS.json` declaring Skills 01/02 and the credential.

## [v2.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
