# Changelog - Google Workspace Setup

All notable changes to this skill wrapper are documented here.

---

## [v1.5.1] - March 10, 2026

### Fixed
- Added existing-setup detection for Gmail / Google Workspace so onboarding can ask add-account-or-skip before reconfiguring.

---

## [v1.5.0] - March 7, 2026

### Changed
- Converted INSTALL.md to agent-executable, autonomous execution format.
- Ensured TYP guardrails are present: MANDATORY TYP CHECK, CONFLICT RULE, and TYP file storage instructions.
- Major expansion: added Gmail-only OAuth path, browser automation hierarchy (agent-browser then Playwright), policy-error recovery for JSON key creation, and automatic GOG setup after successful test.
