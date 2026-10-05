# Runtime Adapters - Phase 1

The BlackCEO methodology is runtime-independent. Installation/discovery mechanics are runtime-specific.

## Canonical-core principle

Prefer one real complete skill folder and safe symlinks into local runtimes when the runtime supports them. Link the entire `blackceo-signature-page` folder, not only `SKILL.md`, because references, scripts, tests, adapters, and assets must travel together.

Do not create separately maintained methodology copies for Claude Code, Claude-Nine, and Codex unless a runtime requires it.

## Safe install helper

Use `python3 scripts/install_local.py --dry-run` before creating any link.

Known Phase-1 helper defaults in this package:

- Claude Code target root: `~/.claude/skills`
- Codex target roots: `~/.agents/skills` and `~/.codex/skills` (both linked when present)
- Claude-Nine: no hard-coded target. Supply its verified skills root with `--target-root`.

Runtime paths and discovery behavior can change. The receiving agent must verify its current environment before using a default and must not claim compatibility solely because a path exists.

The installer refuses to overwrite an existing nonmatching file/directory/symlink. A conflict must be inspected and reconciled intentionally.

## Claude Code adapter

See `adapters/claude-code/README.md`.

## Codex adapter

See `adapters/codex/README.md`.

## Claude-Nine adapter

See `adapters/claude-nine/README.md`. Claude-Nine's exact skill directory is intentionally not guessed; verify the active harness/install and then use the safe installer with the confirmed target root.

## External tools

This skill does not bundle secrets or connectors. Detect available tools at runtime.

Potential live dependencies include:

- Kie.ai or another image engine;
- Agnes when selected;
- GHL;
- browser/computer control;
- GitHub;
- Vercel or another hosting target.

If a tool is absent, keep the local artifacts complete and mark the live integration stage BLOCKED with the exact missing capability.

## Phase 2 boundary

Do not modify the user's OpenClaw GitHub distribution in Phase 1. The vetted core is adapted to the OpenClaw repository/install/update workflow only after Phase-1 evaluation and reconciliation.
