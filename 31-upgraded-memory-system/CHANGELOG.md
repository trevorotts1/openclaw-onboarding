# Changelog - Skill 31: Upgraded Memory System

All notable changes to this skill will be documented in this file.

## [v7.3.0] - 2026-07-21 - SK1-31: the activator applies what the skill declares mandatory, writes atomically, and verifies instead of announcing

- **T2-27 — the required Layer-8 settings were never applied.** SKILL.md:14
  states "ACTIVE MEMORY IS REQUIRED - Layer 8 (Active Memory) requires
  memory-core with `autoCapture: true` and `autoRecall: true`. This is NOT
  optional", and INSTALL.md names `scripts/activate-memory-stack.sh` as the only
  supported activation path. The configuration that script applied contained the
  plugin entry, the dreaming setting and the backend — and neither required
  setting, nor the documented `activeMemory` block. The layer reported active and
  captured nothing. Both are now in the canonical block, and the script asserts
  them as postconditions on the staged file before installing it.

- **T2-28 — the live configuration was rewritten twice, non-atomically, before
  validation, with no backup.** Two separate in-place writes to `openclaw.json`
  ran before `openclaw config validate`; an interruption between them, or a
  validation failure after them, left the box holding a configuration that was
  never validated and could not be restored. This is the file the gateway reads
  at start. Both mutations now apply to a staging file in the configuration
  directory; the staged file is validated, a timestamped backup of the original
  is written, and the install is a single atomic same-directory rename. A
  rejection from `openclaw config validate` restores the backup and exits
  non-zero.

- **T0-45 — the verification command's failure was discarded, and the completion
  banner named the wrong provider.** `openclaw memory status || true` meant the
  script could not distinguish a healthy memory stack from one that cannot start,
  and it then printed DONE with success criteria naming Gemini even on the branch
  (step 1b) that resolved no provider at all — telling the operator to confirm
  output the run could never produce. The status call now captures its output and
  exit code, a non-zero exit is fatal, `Provider: none` is a failure, the status
  output must name the provider this box actually resolved, and the printed
  criteria are generated from that provider. A box with no embedding-capable key
  is a failure rather than a DONE, because Layer 4 cannot run without one.

Tests: `tests/unit/memory-activator-correct-atomic.test.sh` (22 assertions,
including an interruption test and the `|| true` mutation proof).
CI: `.github/workflows/memory-activator-guard.yml`.

## [v7.1.0] - 2026-04-14

### Changed
- **BREAKING**: Active Memory (Layer 8) is now REQUIRED, not optional
- Updated Layer 8 description to reflect Active Memory as mandatory component
- Added complete Active Memory configuration documentation with all parameters
- Added 10-point Active Memory verification checklist to QC.md

### Added
- Active Memory Configuration section in SKILL.md with full config block
- "Activate Active Memory (Layer 8)" as final activation step in INSTALL.md
- Config parameter table documenting all Active Memory settings
- Active Memory entries to CORE_UPDATES.md for AGENTS.md, TOOLS.md, and MEMORY.md
- Section 7: Active Memory Verification Checklist (10-Point) in QC.md
- CHANGELOG.md file for version tracking

### Technical Details
- Active Memory requires `memory.backend: "builtin"`
- Active Memory requires `agents.defaults.memory.autoCapture: true`
- Active Memory requires `agents.defaults.memory.autoRecall: true`
- Active Memory supports optional `agents.defaults.activeMemory.enabled: true`
- Wiki System remains as Layer 8 component alongside Active Memory

## [v6.5.7] - Previous Version

### Features
- 8-layer memory architecture
- Markdown files (Layer 1) for source of truth
- Memory flush (Layer 2) with 8-category capture
- Session indexing (Layer 3) for searchable past conversations
- Gemini Embedding 2 (Layer 4) for semantic search
- memory-core (Layer 5) for native auto-capture and auto-recall
- Cognee (Layer 6) for graph-based knowledge relationships
- Obsidian Vault (Layer 7) for structured knowledge base
- Wiki System (Layer 8) for collaborative documentation
