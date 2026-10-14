# Changelog - 51 Signature Presentation (51-signature-presentation)

## [2.1.6] - 2026-10-13 - Intake-gate doctrine repair: the trace check IS the gate, and the golden fixture speaks one-at-a-time

Text and fixture repair only; no gate logic, prover check, or sacred methodology content changed. Resolves the verified contradictions where the skill's own documents taught two opposite behaviors at once:

- **The trace check gates.** `intake/sp-8-questions.json` (`delivery.rule`) and `scripts/intake_trace_check.py` (banner, SCOPE docstring, CLI description) no longer claim the AF-INTAKE-BATCH scanner "NEVER gates build_deck.py". They now state the truth SKILL.md and the spec's own AF-INTAKE-BATCH autofail entry already carried: this scanner is the check the engine runs as the required fail-closed preflight `P-SP-INTAKE-TRACE` (`build_deck._chk_sp_intake_trace`, phase order 0.16, absent transcript fails), and the QC/Healer scan runs the same scanner out-of-band as an additional post-hoc pass. Because `sp-8-questions.json` is a pinned sacred-structure file, its pin in `scripts/sacred-structure-hashes.json` is regenerated in this same commit, per the pin file's own rule.
- **Golden fixture language.** The golden Quest example no longer says the 8 Questions were "delivered as ONE block". The README, the declared plan's P-SP-INTAKE step name, and the captured P-SP-INTAKE prover outputs (`working/prover_results.json`, `working/checkpoints/process_manifest.json`) now carry the prover's current wording: asked one at a time, committed as ONE atomic record. The fixture intake records (`sp_intake.json`, `working/copy/sp_intake.json`, and broken variant C's copy) drop the deprecated `asked_all_at_once` / `question_block_msg_id` alias fields and keep the canonical `record_committed_atomically` / `record_commit_ids` the HMAC turn ledger signs (the signed payload does not cover the alias fields, so the ledger signature is unaffected).
- **Golden PROCESS-CERTIFICATE regenerated.** `working/checkpoints/client_reports.json` gains the P-SP-CLAIM and P-SP-INTAKE-TRACE start/done report pairs the 7-step declared plan requires (they were missing, so prove-deck.py failed the run with AF-PROCESS-INTEGRITY), and the certificate was re-issued by prove-deck.py against the 7-step plan: declared 2026-08-24, certified after declared_at. The previous certificate certified only 5 steps and was timestamped before its own declared_at.
- **Canonical driver flags.** The legacy signature-mode flags are removed from `prove_sp_intake.py`'s AF-SP-INTAKE-UNPACED remedy text and from the golden README: `deck-intake-driver.py --signature --sig-next/--sig-answer` is the canonical form (the department driver rejects `--signature` combined with `--next`/`--answer` as a caller error). The standard-mode `--next/--answer` flow for `presentation_type`/`signature_source` is unchanged and still canonical. `prove_sp_intake.py`'s CLI description now matches its own gate header (atomic-RECORD, not ONE-block).

## [2.1.5] - 2026-10-06 - KIE integration: the skill describes the deck image chain the department ships

Documentation only; no prover, gate, ledger or sacred file changed (`MASTERDOC.md`, the four frame templates, `intake/sp-8-questions.json` and `structure/sp_structure.json` are byte-identical, their pins in `scripts/sacred-structure-hashes.json` are untouched).

- **Prompt length.** `SKILL.md` no longer says the suggested-image seed expands to "the 9,000-char prompt floor". It now says the Prompt Author expands the seed to the rich image prompt sized to the pinned model's prompt budget (rule 12 of `07-kie-setup/references/kie-common-rules.md`, read with `kie_live_adapter.py prompt-budget --check`), and that the renderer's own 9,000 to 18,000 gate still stands, which is the range the frame templates quote.
- **Model.** "kie.ai gpt-image-2.5 only" becomes the department's image pin in `presentation_job/model_catalog.json`, changed only by an operator catalog bump.
- **Skill 74.** Added to the prerequisites as read-only tooling that is never copied into a run directory (the render guard blocks it).

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
