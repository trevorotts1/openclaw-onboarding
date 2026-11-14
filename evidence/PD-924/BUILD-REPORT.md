# PD-924 — retarget the five divergence fixtures PD-075 invalidated

Unit: PD-924 · lane FL17 · branch `pd/fl17-phase-checks`
Branch tip on arrival: `9255a8a2a885f0e2200267a0da46dd292858412a` (PD-075: build report)
Pre-existing on the branch, named as such: **PD-921**, **PD-088**, **PD-075**.

This was a **fixture retarget**. No product code was changed. No assertion was
deleted, no `assert` was flipped to a weaker form, no message was silenced, and
no divergence check was removed. Two files changed:

* `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/test_runfacts.py`
* `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_trust_boundary_observability.py`

---

## Why the five failed

PD-075 replaced the `P-TYPO-QC` legacy half — `_verify_json_artifact` (existence
only) — with `_verify_qc_report(..., "_chk_typography_qc", ...)`, build_deck's real
report-shape + AF-FONT-FLOOR teeth gate. The five assertions below used a
`pass:false` report as their DIVERGENCE FIXTURE. After PD-075 that report fails
the legacy half too, so it can no longer be the thing RunFacts diverges from.

### A second, separate cause: the room path has a space

`trust_boundary_observability._DIVERGENCE_RE` matches `run_dir=(\S+)` — one
whitespace-free token. This build room lives under
`<EXTERNAL-VOLUME>/swarm-contract/...`, so every real divergence line emitted
from a run_dir on this disk degrades to `UNRECOGNISED-SHAPE`.

Control (same line, two path spellings, instrument only):

```
'/tmp/nospace/run'            -> TRUST-BOUNDARY-DIVERGENCE
'<EXTERNAL-VOLUME>/x/run'  -> UNRECOGNISED-SHAPE
```

That is an instrument property, invisible on a space-free CI checkout. The
fixtures now hand the gate a **relative** run_dir (`run`) resolved from inside the
temp dir, so the emitted path is space-free on any host. Product code untouched;
no assertion relaxed. Assertions 3, 4 and 5 depend on this.

---

## The retarget per assertion

Two shapes are used. Both preserve "two systems disagree about the same report".

**Shape S (stale seal)** — admit the run while the artifact on disk is untrusted,
repair the artifact on disk, then gate. `runfacts.seal()` is documented to resolve
each run_dir ONCE (its front-door property), so RunFacts keeps the untrusted
verdict while the legacy gate reads the repaired file. Yields
`legacy=PASS / runfacts=FAIL` — the ORIGINAL direction.

**Shape T (font floor)** — a SHAPE-VALID PASSING report is written over
`working/typography/type_layout_system.md` with `min_body_pt: 12`. The legacy
teeth refuse it on the font floor; RunFacts seals only the report and passes it.

| # | Assertion | Change | Still fails? |
|---|---|---|---|
| 1 | `test_runfacts.py:186` `report-only mode must not change the legacy PASS result` | Fixture → **Shape S**. The assertion itself is byte-identical, same polarity. `get_or_seal` added as the admission step. | **RED** (mutation 1) |
| 2 | `test_runfacts.py:309` `report-only admission must pass the legacy result` | Fixture → **Shape S**. Assertion byte-identical, same polarity. | **RED** (mutation 2) |
| 3 | `test_trust_boundary_observability.py:191` `report-only mode must not change the legacy PASS result` | Fixture → **Shape S**. Assertion byte-identical. Capture count `2 → 1` and `total 2 → 1` because the seal-time SEAL-FINDING is now emitted at the admission step, outside the capture window; the DIVERGENCE half — the subject of the test — is unchanged. `would_have_blocked is True` kept. | **RED** (mutation 3) |
| 4 | `test_trust_boundary_observability.py:249` `assert obs.DIVERGENCE_PREFIX in captured_stderr` | Fixture → **Shape S**. Assertion byte-identical. Plus the space-free run_dir fix. | **RED** (mutation 4) |
| 5 | `test_trust_boundary_observability.py:305` `assert ok is False` | Fixture → **Shape S**. Assertion byte-identical. | **RED** (mutation 5) |

### Shape T is used only where the font floor is the subject

Assertion 1's test NAME is
`...still_returns_legacy_true_in_report_only`, so Shape S is the only correct
construction there — it keeps the legacy side TRUE, which Shape T cannot. Shape T
appears only in the new companion test
`test_the_font_floor_teeth_still_bite_a_shape_valid_report`, which pins that
`min_body_pt` is load-bearing in the retargeted fixture.

### One addition I did NOT make

`test_runfacts.py`'s `EnforcementModeSealedAtAdmissionTest` and the enforcing
test in the trust file were briefly rewritten to assert `ok is False`; both are
back to their original `assertTrue`/`assertFalse` polarity. PD-075's `and
legacy_ok` guard means enforcing cannot lift a legacy refusal, but the retarget
does not need to exercise that here, so the original polarity stands.

---

## Mutation proof — each retargeted assertion can still FAIL

Each mutation breaks the fixture property its assertion depends on, runs that one
node, and is reverted. Script: `scratchpads/PD-924/mutate3.py` (scratch, not in
the tree).

```
1 test_runfacts.py:186 legacy PASS survives report-only
   rc=1 RED (correct)
2 test_runfacts.py:309 report-only admission returns legacy PASS
   rc=1 RED (correct)
3 trust.py:191 legacy PASS survives report-only
   rc=1 RED (correct)
4 trust.py:249 DIVERGENCE reaches real stderr
   rc=1 RED (correct)
5 trust.py:305 enforcing refuses
   rc=1 RED (correct)
```

---

## Before / after — the two files on the branch tip

**BEFORE** (`9255a8a2a`, both files, `TMPDIR` on a space-free subdir):

```
.........FF............FF.FF.....                                        [100%]
FAILED test_runfacts.py::SealTypographyQcTest::test_proven_gap_pass_false_report_still_returns_legacy_true_in_report_only
FAILED test_runfacts.py::EnforcementModeSealedAtAdmissionTest::test_a_real_gate_verdict_does_not_flip_when_env_changes_mid_run
FAILED tests/test_trust_boundary_observability.py::TestEndToEndCapture::test_tampered_run_detected_recorded_and_still_proceeds
FAILED tests/test_trust_boundary_observability.py::TestEndToEndCapture::test_capture_is_a_true_pass_through_real_stderr_still_receives_the_line
FAILED tests/test_trust_boundary_observability.py::TestEnforcingIsOrthogonalToRecording::test_enforcing_on_still_gets_recorded_with_enforcing_true
FAILED tests/test_trust_boundary_observability.py::TestPreflightFamily::test_clean_run_summary_line_is_parsed
6 failed, 27 passed
```

**AFTER**:

```
............................F.....                                       [100%]
FAILED tests/test_trust_boundary_observability.py::TestPreflightFamily::test_clean_run_summary_line_is_parsed
1 failed, 33 passed
```

The one remaining failure is pre-existing and unrelated — see below. 33 passed
includes the two new companion tests.

---

## Pre-existing failures — by test ID, not by count

### The PD-075 builder's list: confirmed, and it is short

Measured on this branch tip AND on `c6d702160^` (pre-PD-075). Identical on both:

```
test_autofail_registry.py::test_a3_blind_spot_invariant_with_denominator
test_fix2_qc_unskippable.py::test_qc_phase_skip_record_refused_in_load_skip_approvals
test_fix2_qc_unskippable.py::test_real_report_attests_for_all_four_qc_phases
tests/test_fix112_missing_producers.py::test_infographic_checklist_phase_exists_with_role_file_and_verifier
```

The PD-075 list is confirmed exactly. (`test_fix112` lives under `tests/`, not the
scripts root — that is the only correction.)

### The same suite has three more, also pre-existing

The full top-level run (`python3 -m pytest test_*.py`) has **7** failures, not 4,
on BOTH trees — 275 passed at HEAD vs 274 pre-PD-075, the +1 being my new
companion test:

```
test_autofail_registry.py::test_a3_blind_spot_invariant_with_denominator
test_fix2_qc_unskippable.py::test_qc_phase_skip_record_refused_in_load_skip_approvals
test_fix2_qc_unskippable.py::test_real_report_attests_for_all_four_qc_phases
test_gate_read_audit.py::BeforeAfterCountTest::test_before_after_capability_counts
test_scan_roles.py::test_module_constants_exist
test_skip_approval_authenticity.py::ForgedApprovalTest::test_forged_owner_msg_id_fails_build_with_af_forged_approval
test_skip_approval_authenticity.py::ForgedApprovalTest::test_owner_action_only_record_fails_build
```

### The wider `tests/` tree

`python3 -m pytest tests/ -q` on HEAD: **220 failed, 3698 passed, 12 skipped**.
That tree is broadly red on this branch independent of this unit. The only
failure in it that belongs to either file I touched is:

```
tests/test_trust_boundary_observability.py::TestPreflightFamily::test_clean_run_summary_line_is_parsed
```

which asserts `entries=62` while the live `PREFLIGHT_REQUIRED` list has 63
entries. Proven pre-existing by running that exact node on the pre-PD-075 tree —
it fails there, identically, before any of my changes. Attributed to whichever
unit last added a preflight row; **not this one** (PD-924 touched no preflight
code, no product code at all).

### The `entries=62` failure, stated plainly

Not fixed here, because it is not this unit. It is a stale expected count against
a growing registry, and fixing it would mean editing an assertion PD-924 was not
asked to touch.

---

## Scope

Touched: the two test files above, plus this report. No product code, no
`build_deck.py`, no `phase_verifiers.py`, no `runfacts.py`, no
`trust_boundary_observability.py`. No merge, no push to main, no client box, no
live system, no paid model call. Temp files under
`<EXTERNAL-VOLUME>/swarm-contract/pd-fix/tmp`; scratch under
`<EXTERNAL-VOLUME>/swarm-contract/pd-fix/scratchpads/PD-924`.
