# Changelog - Skill 31: Upgraded Memory System

All notable changes to this skill will be documented in this file.

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
