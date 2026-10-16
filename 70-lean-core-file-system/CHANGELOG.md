# Changelog - lean-core-file-system (skill 70)

All notable changes to this skill are documented here.

---

## [1.0.4] - 2026-10-13 - model doctrine cleanup

- `scripts/install-weekly-cron.sh` model resolution is now functional client-choice resolution: `--primary` / `--fallback` remain the client's explicit choice (still validated against the box's configured model list; Anthropic/Claude still refused); with no override the primary is the box's configured default model and the fallback comes from the box's own `agents.defaults.model.fallbacks`. No named model is prescribed anywhere. Header, EXAMPLES.md, INSTALL.md, QC.md and the full skill doc updated to match. Exit codes and all non-model behavior unchanged.
- skill-version v1.0.3 -> v1.0.4.

## [1.0.3] - 2026-10-12 - D04

- `lib-paths.sh`: `pr_master_files` also honours `MASTER_FILES_DIR`; on Contabo (OpenClaw root is a mount, `$HOME` is not) `pr_master_files` and `pr_backup_root` are `<root>/openclaw-master-files` and `<root>/backups`, not the throwaway `$HOME/Downloads`. Mac and Hostinger unchanged.

## [1.0.2] - 2026-10-08 - INF002

- Weekly cron installer uses agent main when the box has one, otherwise the box's primary agent (default flag, else first listed); never fails for a missing main (INF002 B).

## [1.0.0] - 2026-09-28

### Added
- Initial release. Standalone skill (not part of skill 01) that keeps the core
  files (AGENTS.md, TOOLS.md, MEMORY.md, USER.md, IDENTITY.md, SOUL.md) under
  40,000 characters each: situational blocks move into one playbook per system
  in the master files `playbooks/` folder, a one-line pointer (WHAT, WHERE,
  WHEN) stays behind, always-on rules stay inline.
- `lean-core-file-system-full.md`: the playbook (doctrine verified against the
  installed OpenClaw 2026.9.4 code, pointer format with good and bad examples,
  earn-your-place rule, one system one playbook, master index, contradiction
  handling, safety, step-by-step and weekly procedures, test battery,
  landmines, sourced rationale).
- `scripts/pointer-audit.sh`: size report against 40,000, candidate blocks,
  broken pointers, orphans, duplicates, index consistency, playbook hygiene,
  `--backup`, `--prove-moved` content-preservation proof, `--dry-run`. Exit 0
  PASS, 1 FINDINGS, 2 tooling error. macOS bash 3.2 and Linux.
- `scripts/install-weekly-cron.sh`: idempotent weekly OpenClaw cron job
  `lean-core-file-system-weekly` (Sunday 05:30, isolated session, thinking high,
  no delivery). Primary DeepSeek V4.1 Flash on Ollama Cloud, fallback
  DeepSeek V4.1 Flash on OpenRouter, both discovered from the box's own model
  list; refuses (exit 4) rather than guess, and checks every flag against
  `--help` (exit 5).
- `wire.sh`: applies the AGENTS.md pointer and the MEMORY.md "core files"
  definition (backup first, replace-in-place, idempotent), installs the
  playbook copy and the master index, registers the cron job.
- `qc-70-lean-core-file-system.sh` plus three fixture batteries under `tests/`.

### Supersedes
- For core-file content only: the 10-to-25-line summary size and the four-part
  pointer block from skill 01 (Teach Yourself Protocol). Storage paths are
  unchanged and shared.
