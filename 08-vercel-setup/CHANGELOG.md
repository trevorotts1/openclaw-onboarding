# Changelog - vercel-setup

All notable changes to this skill wrapper are documented here.

---

## [v6.5.9] - July 21, 2026

> Version note: `skill-version.txt` is this skill's authoritative marker (now
> `v6.5.9`).

### Fixed
- **The install gate hard-required the Vercel CLI that this skill's own sovereign
  lock forbids.** `SKILL.md`'s API-ONLY EXECUTION LOCK states "do NOT use the
  Vercel CLI for setup/auth. Use browser-based account/token creation and
  API-token verification only", and `QC.md` opens by describing the skill as
  working "without relying on the Vercel CLI for auth" — but
  `qc-vercel-setup.sh` still ran `assert "vercel CLI installed" "command -v vercel"`.
  A box installed exactly as documented has no vercel binary, so this gate failed
  permanently on every correct install. The assertion is removed and replaced with
  one explicit `SKIPPED BY DESIGN` line that counts as neither a pass nor a
  warning. The live token probe stays warn-only; promoting it is a separate,
  measured change.

### Proof
Regression suite `tests/unit/qc-sovereign-lock-forbidden-cli.test.sh` — hermetic,
`vercel` absent by construction. Before the fix a correct install failed; after,
it exits 0, and the gate still exits 1 naming `VERCEL_TOKEN set` and
`jq installed` on real defects.

---

## [v1.5.1] - March 10, 2026

### Fixed
- Locked onboarding to browser + API token flow and removed Vercel CLI as a setup requirement.
- Updated verification and capability notes to use API-based checks during onboarding.

---

## [v1.5.0] - March 7, 2026

### Changed
- Converted INSTALL.md to agent-executable, autonomous execution format.
- Ensured TYP guardrails are present: MANDATORY TYP CHECK, CONFLICT RULE, and TYP file storage instructions.

