# Changelog - pointer-references (skill 70)

All notable changes to this skill are documented here.

---

## [1.0.0] - 2026-09-28

### Added
- Initial release. Standalone skill (not part of skill 01) that keeps the core
  files (AGENTS.md, TOOLS.md, MEMORY.md, USER.md, IDENTITY.md, SOUL.md) under
  40,000 characters each: situational blocks move into one playbook per system
  in the master files `playbooks/` folder, a one-line pointer (WHAT, WHERE,
  WHEN) stays behind, always-on rules stay inline.
- `pointer-references-full.md`: the playbook (doctrine verified against the
  installed OpenClaw 2026.9.6 code, pointer format with good and bad examples,
  earn-your-place rule, one system one playbook, master index, contradiction
  handling, safety, step-by-step and weekly procedures, test battery,
  landmines, sourced rationale).
- `scripts/pointer-audit.sh`: size report against 40,000, candidate blocks,
  broken pointers, orphans, duplicates, index consistency, playbook hygiene,
  `--backup`, `--prove-moved` content-preservation proof, `--dry-run`. Exit 0
  PASS, 1 FINDINGS, 2 tooling error. macOS bash 3.2 and Linux.
- `scripts/install-weekly-cron.sh`: idempotent weekly OpenClaw cron job
  `pointer-references-weekly` (Sunday 05:30, isolated session, thinking high,
  no delivery). Primary DeepSeek V4.1 Flash on Ollama Cloud, fallback
  DeepSeek V4.1 Flash on OpenRouter, both discovered from the box's own model
  list; refuses (exit 4) rather than guess, and checks every flag against
  `--help` (exit 5).
- `wire.sh`: applies the AGENTS.md pointer and the MEMORY.md "core files"
  definition (backup first, replace-in-place, idempotent), installs the
  playbook copy and the master index, registers the cron job.
- `qc-70-pointer-references.sh` plus three fixture batteries under `tests/`.

### Supersedes
- For core-file content only: the 10-to-25-line summary size and the four-part
  pointer block from skill 01 (Teach Yourself Protocol). Storage paths are
  unchanged and shared.
