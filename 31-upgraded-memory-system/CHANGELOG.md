# Changelog - Skill 31: Upgraded Memory System

All notable changes to this skill will be documented in this file.

## [8.1.1] - 2026-10-06 - keep the Skill 76 local embedder

- `scripts/activate-memory-stack.sh` no longer re-pins memory search to Gemini, OpenAI or OpenRouter on a
  box whose memory search runs on the local Ollama embedder (provider `ollama` with `remote.baseUrl` on
  127.0.0.1, localhost or ::1, read from `memory.search`, else the legacy `agents.defaults.memorySearch`).
  It takes the existing "leave the provider alone" path.
- The post-activation check reads the provider and model from `memory.search` first, then the legacy key,
  so it matches what `openclaw memory status` reports on OpenClaw 2026.9.x.

## [8.1.0] - 2026-09-28 - nightly memory maintenance: prune dead embedding-cache rows, report index drift

- **Nothing ever deleted an embedding-cache row.** `memory_embedding_cache` keeps
  one vector per chunk hash, and the vectors add up fast (about 66 KB each as JSON
  before 2026.9.6, 24 KB each as binary after). Rows under an old provider key,
  and rows whose chunk was edited or deleted, stayed forever. One box held 7,133
  such rows (0.47 GB) across 5 agents. New `scripts/memory-cache-prune.sh` deletes
  both kinds. It judges each agent against its OWN index stamp and keeps orphans
  younger than 7 days. It also compacts any agent DB holding 256 MB or more of
  free pages: the 2026.9.6 schema migration left 2.6 GB of free pages on one box.
  It uses python3 stdlib only, because the Docker image ships no sqlite3 CLI.
- **Paused vector search was invisible.** New `scripts/memory-index-check.sh`
  reports agents whose index stamp drifted from the live embedding identity. It
  is READ-ONLY: it never reindexes, because the repair re-embeds through the paid
  provider.
- **Scheduled on every box.** New `install.sh` registers both as silent
  `openclaw cron --command` jobs (`memory-index-check` 02:00,
  `memory-cache-prune` 02:40, `--no-deliver`). It is idempotent by name and
  honors a tombstone. install.sh calls it on a fresh install, and
  update-skills.sh runs it through the per-skill wiring loop, on Mac and in
  Docker alike.
- Guarded by `tests/unit/memory-cache-prune.test.sh` and
  `.github/workflows/memory-cache-prune-guard.yml`.

## [8.0.0] - 2026-07-21 - SK1-31: the activator applies what the skill declares mandatory, writes atomically, and verifies instead of announcing

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

## [v8.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
