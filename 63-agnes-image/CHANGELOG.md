# Changelog - agnes-image

All notable changes to this skill are documented here.

---

## [v1.2.0] - 2026-08-26 - fix: prompt policy alignment, remove invented 25K cap, add models.json registry and validators

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
