# Changelog - 51 Signature Presentation (51-signature-presentation)

## [2.1.0] - 2026-09-09 - PRES-051: supported plugin hook registration + bounded scripts

Adds the hosted lifecycle hook package: `.claude-plugin/plugin.json`, `hooks/hooks.json`
(supported events SessionStart / PreToolUse / PostToolUse / Stop, `${CLAUDE_PLUGIN_ROOT}`
install-relative paths), and bounded handlers in `scripts/hooks/` — session readiness with
explicit company/presentation/run binding, read-only engine delegation (never a gate waiver),
observed-operation recording, bounded Stop feedback with `stop_hook_active` + persisted reentry
budget and resumable blocked state, plus `sp_doctor.py` install/uninstall/registration/doctor
(`--handshake` classifies files-present / registered / event-observed / engine-gate-tested
separately). Hook handlers never invoke a Claude binary, never start paid work, and never print
secrets; enforcement stays in engine transactions. 27 hermetic checks in
`scripts/tests/test_pres051_hooks.py`. SKILL.md documents the contract.

## [2.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
