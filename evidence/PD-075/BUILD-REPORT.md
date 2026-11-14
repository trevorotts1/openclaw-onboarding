# PD-075 — the typography report is read at its own step

- Unit: PD-075
- Lane: FL17
- Severity: Moderate
- Branch: `pd/fl17-phase-checks` (`git branch --show-current` = `pd/fl17-phase-checks`, exact match to the ledger row, no `--hold-dNN` suffix)
- Worktree: `/Volumes/mac mini m4/swarm-contract/pd-fix/worktrees/onboarding/FL17`
- Base head at start: `5288f07a903d048458157dcba93d6e78c0669822` (`git rev-parse HEAD`)
- Fix commit: `c6d702160b063ef4b441bf53d3b758d7d2034aed`
- Remote proof: `git ls-remote origin refs/heads/pd/fl17-phase-checks` →
  `c6d702160b063ef4b441bf53d3b758d7d2034aed` = local `git rev-parse HEAD`
- Acceptance row: A1
- Verdict: **BUILT, with a named BLOCKED item for five assertions in two files PD-075 does not own** (see the last section)

## Pre-existing commits on the branch (NOT mine)

Named in the dispatch as already ACCEPTED, both left intact:

```
5288f07a9 PD-088: build report                          (PD-088, build report)
1e697fdda PD-088: the typography step proves typography work
13d00426b PD-921: build report                          (PD-921, build report)
cb8028e04 PD-921: an unbound provenance binding refuses instead of passing
10cedc4ec PD-062v: the deck is resolved where the render writes it
```

Mine, on top:

```
c6d702160 PD-075: the typography report is read at its own step
```

## The change

Spec (01-BUILD-SPEC.md, section PD-075): register `P-TYPO-QC` with
`_verify_qc_report("working/qc/typography_qc_report.json", "_chk_typography_qc", "AF-TYPOGRAPHY-QC")`,
keeping the shadow wrapper around it.

Before, in `phase_verifiers.py`:

```python
"P-TYPO-QC": _shadow_qc_verifier(
    "typography", _verify_json_artifact("working/qc/typography_qc_report.json")),
```

The legacy half only proved the file existed, was non-empty and parsed, so a
report carrying `pass: false` flipped the step to done. After:

```python
"P-TYPO-QC": _shadow_qc_verifier(
    "typography", _verify_qc_report(
        "working/qc/typography_qc_report.json", "_chk_typography_qc",
        "AF-TYPOGRAPHY-QC",
        artifact_pattern="working/qc/typography_qc_report.json")),
```

Files changed (exactly two, both inside the unit's owned paths):

| File | Change |
|---|---|
| `…/presentations/scripts/phase_verifiers.py` | the registry entry; `_verify_qc_report` gains an optional `artifact_pattern`; `_shadow_qc_verifier` enforcing branch no longer lifts a legacy FAIL; `_chk_typography_qc` added to `_VERIFIER_SYMBOL_CONTRACT`; comments updated |
| `…/presentations/scripts/tests/test_pd_phase_checks_typography.py` | NEW — A1a `pass:false` → fail, A1b valid passing report → pass, plus a registration assertion |

`git show --name-only --format="" HEAD` prints only those two paths.

### Two supporting edits inside `phase_verifiers.py`, and why

1. **`artifact_pattern` parameter.** `test_pd061_verifier_paths.py` walks the
   whole registry and requires every entry built by a path factory to expose
   `artifact_pattern`, and pins the covered set in BOTH directions
   (`EXPECTED_FACTORY_PHASES` includes `P-TYPO-QC`). The old
   `_verify_json_artifact` factory set that attribute and `_shadow_qc_verifier`
   copies it; `_verify_qc_report` did not. Without this the PD-061 parity walk
   would raise. The attribute is now carried by the wrapped verifier, so the
   covered set is unchanged — `test_pd061_verifier_paths.py` passes unmodified.

2. **Enforcing mode could LIFT a FAIL — proved, then fixed.** With teeth in the
   legacy half, the report-only RunFacts read (which sees only the report, not
   the on-disk type tokens) can PASS where the legacy gate FAILS. The old
   `if facts.enforcing: if verdict is PASS: return True` therefore *weakened*
   the gate, contradicting `_shadow_qc_verifier`'s own docstring ("can only
   ever make the gate STRICTER"). The enforcing branch now returns True only
   when `verdict is PASS and legacy_ok`. Measured both ways with
   `PRES_TRUST_BOUNDARY_ENFORCE=1`, a shape-valid passing report and
   `min_body_pt: 12` on disk:

   - before the fix: `RESULT enforcing=1 sub-floor tokens: True` (a weakening)
   - after the fix:  `RESULT enforcing=1 sub-floor tokens: False`

## Commands and results (verbatim)

### A1 — PD-075's own rows

```
$ python3 -m pytest tests/test_pd_phase_checks_typography.py -q
...                                                                      [100%]
3 passed in 0.08s
```

### PD-921's fail-closed null binding SURVIVED (required by the dispatch)

In-process probe on the committed tree: bind `pv._rf109 = None`, then ask for a
refusal on a consumer phase, a producer phase and the typography phase.

```
PD921 unbound P-CONSUMER: refusal=True
PD921 unbound P0A-INTAKE: refusal=True
PD921 unbound P-TYPO-QC: refusal=True
PD921 bound restored: True
```

Plus the accepted unit's own test file:

```
$ python3 -m pytest tests/test_intake_provenance.py -q
......                                                                   [100%]
6 passed in 0.15s
```

### Owned neighbours still green

```
$ python3 -m pytest tests/test_pd061_verifier_paths.py tests/test_pd088_design_phase.py -q
........                                                                 [100%]
8 passed in 0.08s

$ python3 -c "import phase_verifiers as pv; print(len(pv.assert_bound()))"
assert_bound ok: 44 symbols
```

### Before/after pair, same ten-file set

Before the change (working tree stashed back to `5288f07a9`):

```
$ python3 -m pytest tests/test_pd061_verifier_paths.py tests/test_pd088_design_phase.py \
    tests/test_fix112_missing_producers.py tests/test_pd_phase_checks_audio.py \
    tests/test_pd_phase_checks_human_review.py tests/test_pd_phase_checks_typography.py \
    test_runfacts.py test_fix2_qc_unskippable.py test_autofail_registry.py \
    tests/test_intake_provenance.py -q
FAILED tests/test_fix112_missing_producers.py::test_infographic_checklist_phase_exists_with_role_file_and_verifier
FAILED test_fix2_qc_unskippable.py::test_qc_phase_skip_record_refused_in_load_skip_approvals
FAILED test_fix2_qc_unskippable.py::test_real_report_attests_for_all_four_qc_phases
FAILED test_autofail_registry.py::test_a3_blind_spot_invariant_with_denominator
4 failed, 64 passed in 3.35s
```

After (`HEAD` = `c6d702160`):

```
FAILED tests/test_fix112_missing_producers.py::test_infographic_checklist_phase_exists_with_role_file_and_verifier
FAILED test_runfacts.py::SealTypographyQcTest::test_proven_gap_pass_false_report_still_returns_legacy_true_in_report_only
FAILED test_runfacts.py::EnforcementModeSealedAtAdmissionTest::test_a_real_gate_verdict_does_not_flip_when_env_changes_mid_run
FAILED test_fix2_qc_unskippable.py::test_qc_phase_skip_record_refused_in_load_skip_approvals
FAILED test_fix2_qc_unskippable.py::test_real_report_attests_for_all_four_qc_phases
FAILED test_autofail_registry.py::test_a3_blind_spot_invariant_with_denominator
6 failed, 65 passed in 2.81s
```

The four failures present before are untouched pre-existing failures on this
branch (three `test_fix2_qc_unskippable`/`test_fix112` failures and the
`test_autofail_registry` blind-spot denominator), unrelated to this unit. Two
`test_runfacts.py` failures are NEW and are mine — see BLOCKED below.

### Trust-boundary observability suite, before and after

Pristine `5288f07a9`:

```
$ python3 -m pytest tests/test_trust_boundary_observability.py test_runfacts.py -q
FAILED tests/test_trust_boundary_observability.py::TestPreflightFamily::test_clean_run_summary_line_is_parsed
1 failed, 32 passed in 3.37s
```

At `HEAD`:

```
FAILED tests/test_trust_boundary_observability.py::TestEndToEndCapture::test_tampered_run_detected_recorded_and_still_proceeds
FAILED tests/test_trust_boundary_observability.py::TestEndToEndCapture::test_capture_is_a_true_pass_through_real_stderr_still_receives_the_line
FAILED tests/test_trust_boundary_observability.py::TestEnforcingIsOrthogonalToRecording::test_enforcing_on_still_gets_recorded_with_enforcing_true
FAILED tests/test_trust_boundary_observability.py::TestPreflightFamily::test_clean_run_summary_line_is_parsed
FAILED test_runfacts.py::SealTypographyQcTest::test_proven_gap_pass_false_report_still_returns_legacy_true_in_report_only
FAILED test_runfacts.py::EnforcementModeSealedAtAdmissionTest::test_a_real_gate_verdict_does_not_flip_when_env_changes_mid_run
6 failed, 27 passed in 3.35s
```

## BLOCKED: spec-versus-test (five assertions, two unowned files)

PD-075's owned paths are `phase_verifiers.py`, `tests/test_pd_phase_checks_*.py`,
`tests/test_pd061_verifier_paths.py`, `tests/test_pd088_design_phase.py`,
`tests/test_fix112_missing_producers.py`. `test_runfacts.py` and
`tests/test_trust_boundary_observability.py` are **not** in that list, so I did
not edit them. Five assertions in them are falsified by this unit's own specified
change, each for the same true reason: they assert the OLD defect (a
`pass: false` typography report is accepted as a legacy PASS) as a fixture for
proving the trust-boundary machinery records a divergence. PD-075 exists to
remove exactly that defect, so these fixtures must be repointed; their assertions
cannot hold while the spec holds.

Exact assertions, verbatim:

1. `test_runfacts.py:186`
   `self.assertTrue(ok, "report-only mode must not change the legacy PASS result")`
2. `test_runfacts.py:309`
   `self.assertTrue(ok_before, "report-only admission must pass the legacy result")`
3. `tests/test_trust_boundary_observability.py:191`
   `assert ok is True, "report-only mode must not change the legacy PASS result"`
4. `tests/test_trust_boundary_observability.py:249`
   `assert obs.DIVERGENCE_PREFIX in captured_stderr, (` — the `pass:false`
   fixture no longer diverges, so `shadow_compare` prints nothing to tee.
5. `tests/test_trust_boundary_observability.py:305`
   `assert ok is False` (enforcing case) — reaches this line only after the
   earlier divergence expectations.

What a follow-up unit must do: keep each test's INTENT (a tampered run is
detected, recorded, and the legacy result stands) but build the divergence from
a fixture RunFacts can disagree with, e.g. a shape-valid passing report over
sub-floor `type_layout_system.md` tokens (`min_body_pt: 12`) — the asymmetry
proved above, where the deterministic teeth FAIL and RunFacts PASSes. A working
edit was written and reverted, not committed; the branch carries no change to
either file.

Until that unit lands, the two files are red at `c6d702160` for the reason
above; every other file this unit touches is green.
