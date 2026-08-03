# Changelog - agnes-image

All notable changes to this skill are documented here.

---

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
