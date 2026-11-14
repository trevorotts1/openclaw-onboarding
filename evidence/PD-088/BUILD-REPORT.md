# PD-088 — the typography step proves typography work

- Unit: PD-088
- Lane: FL17
- Severity: Severe
- Branch: `pd/fl17-phase-checks` (confirmed with `git branch --show-current` before any work)
- Worktree: `<EXTERNAL-VOLUME>/swarm-contract/pd-fix/worktrees/onboarding/FL17`
- Fix commit: `1e697fdda9b756798353c693f9ca38b77c6833e4`
- Pre-fix branch head: `13d00426b`
- Remote proof: `git ls-remote origin refs/heads/pd/fl17-phase-checks` →
  `1e697fdda9b756798353c693f9ca38b77c6833e4` = local `git rev-parse HEAD`
- Acceptance row: A1
- Ledger note / defect list: the PD-088 ledger row carries `note: null` and
  `spec_defect: null` — no defect list and no correction to address.

## Branch attribution (`git log --oneline -8` before the commit)

Already on the branch before this unit (NOT mine):

    cb8028e04 PD-921: an unbound provenance binding refuses instead of passing
    10cedc4ec PD-062v: the deck is resolved where the render writes it
    76703417c PD-915: build report
    2d85e9d1b PD-915: the phase-level bundle check is asserted at its new gate
    021f74e24 PD-910: build report
    08a6cdcd7 PD-910: the unbound sentinel is not a placeholder and a note is not a failure
    200fa8630 PD-064: the audio step is checked for the audio

Mine:

    1e697fdda PD-088: the typography step proves typography work

No other unit's hunk is touched by this commit; the diff is one registry entry,
one new function, and one new test file.

## The defect

`phase_verifiers.py` registered the typography step as

    "PF-DESIGN": _verify_text_artifact("working/research/design-brief-*.md", 50),

so fifty characters of art direction flipped Phase 4.5 to `done` with no type
system, no declared weights and no design system behind it. Proven, not assumed:
the new test's brief-alone row FAILED against the pre-fix code with
`AssertionError: a research brief alone must not pass the typography step`.

## The change

`23-ai-workforce-blueprint/templates/role-library/presentations/scripts/phase_verifiers.py`
(+70 −1): new `_verify_design_phase`, registered as `PF-DESIGN`. It passes only
when all three artifacts exist and are valid, each miss returning its own reason:

1. `working/research/design-brief-*.md` with 200 characters of text;
2. `working/typography/type_layout_system.md` present and
   `build_deck.check_font_floor(run_dir)` returning `""` (an unavailable
   measurer fails closed — F03);
3. `working/typography/design_system.json` parsing as a JSON object with a
   non-empty `weight_ladder` and a non-empty `archetype_plan`.

The entry keeps `artifact_pattern = "working/research/design-brief-*.md"` — the
path the manifest's `produces_artifact` declares — so the PD-061 all-registry
parity walk still classifies it and `test_pd061_verifier_paths.py` is neither
edited nor weakened.

New file
`.../scripts/tests/test_pd088_design_phase.py` (118 lines): the registry entry
is the new function; A1 rows — brief alone fails naming `type_layout_system.md`
(and `design_system.json`), all three valid passes, `min_body_pt: 12` fails.

## Commands run and results

All from `.../role-library/presentations/scripts`, `TMPDIR` set to
`<EXTERNAL-VOLUME>/swarm-contract/pd-fix/tmp`.

1. BEFORE the fix — `python3 -m pytest tests/test_pd088_design_phase.py -q`
   → **3 failed, 1 passed**. The substantive failure:
   `AssertionError: a research brief alone must not pass the typography step /
   assert not True` — the old verifier passed on the brief alone.
2. AFTER the fix — `python3 -m pytest tests/test_pd088_design_phase.py -q`
   → **4 passed**.
3. `python3 -m pytest tests/test_pd061_verifier_paths.py -q` → **4 passed**
   (registry parity unbroken, test untouched).
4. `python3 phase_verifiers.py --selftest` → **PASS — all self-tests passed.**
5. Whole-registry neighbourhood:
   `python3 -m pytest tests/test_fix36_registry_parity_cand27.py
   tests/test_verifier_registry.py tests/test_gates.py
   tests/test_pd_phase_checks_audio.py tests/test_pd062v_deck_assembly_path.py
   tests/test_defect3_presence_is_not_substance.py test_autofail_registry.py -q`
   → **80 passed, 1 failed**. The one failure
   (`test_autofail_registry.py::test_a3_blind_spot_invariant_with_denominator`)
   fails identically with the pre-fix `phase_verifiers.py`, measured in step 7.
6. Every test file importing `phase_verifiers` (41 files, one per run, 90 s cap
   each, results in `tmp/pd088-perfile.txt`): **32 files pass, 8 fail, 1 times
   out**. The 9 non-passing files and their counts:

       tests/test_f16_agent_phase_wait_race.py          rc=1  2 failed,  6 passed
       tests/test_fault17_resume_false_block.py         rc=1  1 failed,  1 passed
       tests/test_fix112_missing_producers.py           rc=1  1 failed,  5 passed
       tests/test_fix17_verifier_import_failclosed.py   rc=1  5 failed,  2 passed
       tests/test_negative_fixtures.py                  rc=1  1 failed, 26 passed
       tests/test_pres002_ready_gate.py                 rc=124 (hang; "FF." captured)
       tests/test_pres036_ready_queue.py                rc=1  1 failed,  8 passed
       tests/test_trust_boundary_observability.py       rc=1  3 failed, 14 passed
       tests/test_upsell_verifiers.py                   rc=1  3 failed, 48 passed

7. TRUE BASELINE for those 9 files: the worktree's `phase_verifiers.py` was
   replaced by `git show HEAD~1:<path>` (pre-fix bytes, `grep -c
   _verify_design_phase` = 0) and the same 9 runs repeated. Result
   (`tmp/pd088-true-baseline9.txt`): **identical rc and identical
   failed/passed counts on all 9**. None of them is caused by PD-088; they are
   pre-existing on this branch. The file was then restored from
   `tmp/pd088-mine.py` and `git status --porcelain` is clean against HEAD.
   The `test_fix112` failure in particular is a role-file path assert
   (`presentations/infographic-checklist.md` ships only under
   `presentations/roles/` in HEAD) reached before that test imports
   `phase_verifiers`.

## Files changed

- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/phase_verifiers.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd088_design_phase.py` (new)
- `evidence/PD-088/BUILD-REPORT.md` (this file)
