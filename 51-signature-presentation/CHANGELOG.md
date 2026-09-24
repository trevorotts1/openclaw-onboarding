# Changelog - 51 Signature Presentation (51-signature-presentation)

## [2.1.2] - 2026-09-16 - PD-TEST-147 / PD-TEST-140: refresh the intake self-test's stale fixtures

`prove_sp_intake.py --self-test` went red on every PR once the content-provenance
migration window legitimately closed on 2026-09-15: FIVE must-PASS cases were
still built from the *pre-provenance driver* record shape (no `answer_provenance`)
-- `GK-23-fixtureA-driver-paced` plus four `fix29-*` cases (`fix29-current-key-envelope`,
`fix29-previous-key-within-window`, `fix29-legacy-envelope-within-window`,
`fix29-current-key-still-passes-after-cutoff`) -- and each failed with the SINGLE
`AF-SP-PROVENANCE` code, which masked the turn-ledger rotation / pacing property
that case actually tests. The gate was correct; the fixtures were stale. Those five
cases now build `_valid_runtime_fixture_provenanced()`, which is the shape a record
the engine must ACCEPT today actually has, so each case isolates its own property
again. Separately, the `fix29-*` VIOLATION cases no longer carry a spurious second
code: they now report exactly the one code they mean to test (two codes -> one),
which makes them strictly stronger assertions than they were.
`_valid_runtime_fixture_paced()` keeps its provenance-less shape DELIBERATELY -- it
is the fixture for the migration boundary itself -- and its docstring now says so,
so this time bomb cannot be silently re-armed HERE. (It is still armed in a sibling
copy of the driver, `23-ai-workforce-blueprint/scripts/deck-intake-driver.py`, which
has no `answer_provenance` support at all and whose `--signature --selftest` fails
Tests 2 and 5 on a provisioned box while self-skipping in CI; recorded separately as
PD-TEST-150 and deliberately NOT fixed here.) The grandfathering branch stays covered
on both sides of the cutoff by cases 21/22, which inject `today=`.

Also fixes PD-TEST-140 in the same self-test: case 20 ("missing current key fails
closed") cleared the six key env vars but not the operator's DEFAULT record file
(`~/.openclaw/state/presentation/sp-turn-ledger-keys.json`), which exists on every
box that has run the department. There the real record wins, its
`rotation_started_at` (2026-09-01) is later than the case's synthetic in-window
clock (2026-07-20), and the earlier clock-backward guard fired first -- so the
assertion could never pass on the operator's own box while passing on a clean CI
runner. Case 20 now neutralises the default-file step for its duration and
restores it, making the check hermetic on both an unprovisioned runner and a live
box. No engine, gate, verifier or contract behaviour changed.

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
