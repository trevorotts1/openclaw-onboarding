# Changelog - github-setup

All notable changes to this skill wrapper are documented here.

---

## [v6.5.8] - July 21, 2026

> Version note: `skill-version.txt` is this skill's authoritative marker (now
> `v6.5.8`). The `v1.x` headings below are the historical wrapper series and are
> kept for provenance; new entries use the authoritative marker.

### Fixed
- **The install gate hard-required the GitHub CLI that this skill's own sovereign
  lock forbids.** `SKILL.md`'s API-ONLY EXECUTION LOCK states "do NOT use GitHub
  CLI (gh) for setup/auth", and v1.5.1 below already removed gh as an onboarding
  requirement — but `qc-github-setup.sh` still ran
  `assert "gh CLI installed" "command -v gh"` and
  `assert "gh authenticated" "gh auth status ..."`. A box installed exactly as
  documented has no gh, so this gate failed permanently on every correct install
  and fed a non-zero quality-control exit into the wave gate. Both assertions are
  removed and replaced with one explicit `SKIPPED BY DESIGN` line that counts as
  neither a pass nor a warning. Credential validation is unchanged.
- `QC.md`'s expected-version pin said `v6.5.6` against a `skill-version.txt` of
  `v6.5.7`, making its stated pass rule unsatisfiable. Both now read `v6.5.8`.

### Proof
Regression suite `tests/unit/qc-sovereign-lock-forbidden-cli.test.sh` — hermetic,
`gh` absent by construction. Before the fix: 4 passed, 4 failed (a correct install
failed). After: 8 passed, 0 failed, and the gate still exits 1 naming
`Skill 10 folder present` and `git user.email configured` on real defects.

---

## [v1.5.1] - March 10, 2026

### Fixed
- Locked onboarding to browser + PAT/API setup with local git config only.
- Removed GitHub CLI as an onboarding requirement and cleaned up conflicting examples.

---

## [v1.5.0] - March 7, 2026

### Changed
- Converted INSTALL.md to agent-executable, autonomous execution format.
- Ensured TYP guardrails are present: MANDATORY TYP CHECK, CONFLICT RULE, and TYP file storage instructions.

