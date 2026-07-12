# Changelog - Agent Browser (Vercel)

All notable changes to this skill wrapper are documented here.

---

## [v6.5.9] - July 12, 2026 (P3-06)

### Fixed
- **Stale bundled archive, regenerated + made impossible to drift again.** `agent-browser.skill` was hand-packaged with no regeneration step and no drift check, so it silently shipped a STALE copy of `INSTALL.md` (missing the N24 TYP citation, the mandatory `--headed false` requirement, the guaranteed-close `trap ... EXIT` subshell, the "Lifecycle hygiene" section, and the entire "GATEWAY RESTART PROTOCOL" block) and a STALE `CORE_UPDATES.md`, right next to current loose files. Added `scripts/pack-agent-browser-skill.sh` — the ONLY sanctioned way to produce/update the archive from now on (deterministic, `--check` mode, wired into CI). Regenerated the archive from the current on-disk source.
- **`qc-agent-browser.sh` drift gate.** Now unzips `agent-browser.skill` and diffs `INSTALL.md`/`SKILL.md`/`CHANGELOG.md`/`CORE_UPDATES.md` inside it against the on-disk copies — ANY mismatch is a hard QC FAIL naming the differing file (`scripts/lib-archive-diff.sh`, shared by the packer's `--check` and the QC gate).
- **Step-4 smoke test is now ASSERTED, not implied.** `qc-agent-browser.sh` re-extracts the exact fenced Step-4 code block live from `INSTALL.md` (the guaranteed-close trap, `--headed false`) and prints the command + flags it actually ran as evidence. An ambient `AGENT_BROWSER_HEADED` signal that would force a visible window is refused (exit-75 class, matching Skill 06's D6 convention) before the smoke test ever runs.
- **Post-smoke-test session state upgraded from `warn_only` to `assert`.** A Chromium process this run's own smoke test spawned and left alive after `agent-browser close` ran now FAILS QC (was: no check at all). A scoped session that predates the QC run stays `warn_only` (not this skill's fault). QC.md gained explicit line items for all three.

---

## [v1.5.0] - March 7, 2026

### Changed
- Converted INSTALL.md to agent-executable, autonomous execution format.
- Ensured TYP guardrails are present: MANDATORY TYP CHECK, CONFLICT RULE, and TYP file storage instructions.
- Added wrapper skill to ensure agent-browser is installed and available as the preferred browser automation tool.
