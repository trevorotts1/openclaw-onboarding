# Changelog - google-workspace-integration

All notable changes to this skill wrapper are documented here.

---

## [7.0.1] - 2026-10-12

### Fixed - GMAIL SEND PATH IN TOOLS.md (RRS001)

- The `CORE_UPDATES.md` TOOLS.md block taught only `gws auth login`, so an agent that found no gws OAuth said the box had no way to send email. It now also names the Google service-account + domain-wide-delegation path (`GOOGLE_APPLICATION_CREDENTIALS`, `GCP_IMPERSONATE_USER`) and a send-readiness check that passes when EITHER path is ready, without running a bare headless `gws auth status`.
- `INSTALL.md` troubleshooting no longer claims the path "is documented in TOOLS.md" when the shipped block did not contain it.
- `qc-google-workspace-integration.sh`: Gmail send-path-ready check. Test: `tests/unit/skill14-send-readiness.test.sh`. Existing users should re-run core updates.

---

## [7.0.0] - March 19, 2026

### Changed
- Replaced google-api.js and gog with Google Workspace CLI (gws).
- Reduced from 10 files to 8 files.
- All 81 scopes preserved.
- Simplified authentication: one tool for both Gmail and Workspace accounts.
- Updated all documentation to reference gws commands.

---

## [v1.5.0] - March 7, 2026

### Changed
- Converted INSTALL.md to agent-executable, autonomous execution format.
- Ensured TYP guardrails are present: MANDATORY TYP CHECK, CONFLICT RULE, and TYP file storage instructions.

## [v7.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
