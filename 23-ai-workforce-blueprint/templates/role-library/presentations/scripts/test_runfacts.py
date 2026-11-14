#!/usr/bin/env python3
"""
test_runfacts.py — TRUST BOUNDARY, INCREMENT 1: unit tests for
presentation_job/runfacts.py and its two shadow-wired consumers
(build_deck._owner_skip_approved, phase_verifiers PHASE_VERIFIERS["P-TYPO-QC"]).

Hermetic: no network, no subprocess spawn of build_deck.py's CLI (these
exercise the module functions directly, matching the existing convention in
test_fix2_qc_unskippable.py: `import build_deck as bd`). Every fixture lives
under a tempfile.TemporaryDirectory().

Run:  python3 test_runfacts.py
      python3 -m pytest test_runfacts.py -q
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from presentation_job import runfacts as rf  # noqa: E402
import build_deck as bd  # noqa: E402
import phase_verifiers as pv  # noqa: E402


def _write(p: Path, obj_or_text) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj_or_text, str):
        p.write_text(obj_or_text)
    else:
        p.write_text(json.dumps(obj_or_text))


# --- PD-924 retarget helpers (module level: two test classes need them) ----
def _pd924_tokens(run_dir: Path, min_body_pt="12") -> None:
    """PD-924: the design tokens AF-FONT-FLOOR re-measures. A sub-floor
    min_body_pt makes the LEGACY teeth refuse a report whose SHAPE is a clean
    pass — which is the divergence these tests construct."""
    _write(run_dir / "working" / "typography" / "type_layout_system.md",
           f"min_body_pt: {min_body_pt}\ntype_scale_steps: 4\n"
           f"min_contrast_ratio: 7.0\n")


def _pd924_clean_report() -> dict:
    return {
        "gate": "Phase Typography-QC", "average": 9.1, "pass": True,
        "triggered_autofails": [],
        "qc_independence": {"graded_by": "typography-qc-specialist",
                            "independent": True},
    }


class FactAndVerdictPrimitivesTest(unittest.TestCase):
    def test_verdict_has_no_truthiness(self):
        for v in (rf.Verdict.PASS, rf.Verdict.FAIL, rf.Verdict.UNDETERMINED):
            with self.assertRaises(TypeError):
                bool(v)
            with self.assertRaises(TypeError):
                if v:  # pragma: no cover - the assertRaises above already proves it
                    pass

    def test_fact_value_raises_unless_known(self):
        for f in (rf.Fact.absent("x"), rf.Fact.unparseable("x"),
                  rf.Fact.conflicted("x"), rf.Fact.untrusted("x")):
            with self.assertRaises(rf.RunFactsError):
                _ = f.value
            self.assertEqual(f.get("fallback"), "fallback")

    def test_fact_value_ok_when_known(self):
        f = rf.Fact.known(42, "because")
        self.assertEqual(f.value, 42)
        self.assertEqual(f.get("fallback"), 42)
        self.assertTrue(f.is_known())


class SealOwnerSkipTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._td.name)
        rf.reset_cache_for_tests()

    def tearDown(self):
        self._td.cleanup()
        rf.reset_cache_for_tests()

    def test_absent_manifest_is_absent_fact_and_fails_closed(self):
        facts = rf.seal(self.run_dir)
        self.assertIs(facts.owner_skip_records.state, rf.Epistemic.ABSENT)
        verdict, detail = rf.verify_owner_skip(facts, "AF-MODE-UNSET")
        self.assertIs(verdict, rf.Verdict.FAIL)
        self.assertIn("AF-MODE-UNSET", detail)
        # findings() must stay QUIET for the common "nothing has happened yet"
        # case — ABSENT-because-not-yet-produced is not a "finding".
        self.assertEqual(facts.findings(), [])

    def test_valid_record_passes_both_legacy_and_runfacts(self):
        pm = self.run_dir / "working" / "checkpoints" / "process_manifest.json"
        _write(pm, {"owner_skip_approval": {
            "owner_approved": True, "af_code": "AF-MODE-UNSET",
            "approved_by": "trevor", "reason": "client requested general mode",
            "timestamp": "2026-08-13T00:00:00Z",
        }})
        legacy = bd._owner_skip_approved_legacy(self.run_dir, "AF-MODE-UNSET")
        self.assertIsNotNone(legacy)
        facts = rf.seal(self.run_dir, force=True)
        verdict, _detail = rf.verify_owner_skip(facts, "AF-MODE-UNSET")
        self.assertIs(verdict, rf.Verdict.PASS)
        self.assertEqual(facts.findings(), [])
        # And the public wrapper (report-only, default env) must return the
        # SAME thing the legacy function returns — behavior unchanged.
        self.assertEqual(bd._owner_skip_approved(self.run_dir, "AF-MODE-UNSET"),
                          legacy)

    def test_incomplete_record_is_surfaced_even_though_legacy_silently_drops_it(self):
        pm = self.run_dir / "working" / "checkpoints" / "process_manifest.json"
        _write(pm, {"owner_skip_approval": [
            {"owner_approved": True, "af_code": "AF-CANONICAL-RENDER-BYPASS",
             "approved_by": "", "reason": "", "timestamp": ""},
        ]})
        legacy = bd._owner_skip_approved_legacy(self.run_dir, "AF-CANONICAL-RENDER-BYPASS")
        self.assertIsNone(legacy)  # legacy already correctly denies this (safe)
        facts = rf.seal(self.run_dir, force=True)
        verdict, _d = rf.verify_owner_skip(facts, "AF-CANONICAL-RENDER-BYPASS")
        self.assertIs(verdict, rf.Verdict.FAIL)
        findings = facts.findings()
        self.assertEqual(len(findings), 1)
        self.assertIn("AF-CANONICAL-RENDER-BYPASS", findings[0])
        self.assertIn("NOT structurally valid", findings[0])

    def test_conflicting_records_are_conflicted_not_silently_resolved(self):
        pm = self.run_dir / "working" / "checkpoints" / "process_manifest.json"
        _write(pm, {"owner_skip_approval": [
            {"owner_approved": False, "af_code": "AF-MODE-UNSET",
             "approved_by": "qc-specialist", "reason": "denied on review",
             "timestamp": "2026-08-12T00:00:00Z"},
            {"owner_approved": True, "af_code": "AF-MODE-UNSET",
             "approved_by": "trevor", "reason": "override",
             "timestamp": "2026-08-13T00:00:00Z"},
        ]})
        legacy = bd._owner_skip_approved_legacy(self.run_dir, "AF-MODE-UNSET")
        self.assertIsNotNone(legacy)  # legacy silently picks the valid one -> "approved"
        facts = rf.seal(self.run_dir, force=True)
        verdict, detail = rf.verify_owner_skip(facts, "AF-MODE-UNSET")
        self.assertIs(verdict, rf.Verdict.UNDETERMINED)
        self.assertIn("CONFLICTED", detail)
        # Report-only: the public wrapper still returns the legacy (permissive)
        # result — divergence is LOGGED, never silently enforced, by default.
        os.environ.pop(rf.ENFORCE_ENV, None)
        wrapped = bd._owner_skip_approved(self.run_dir, "AF-MODE-UNSET")
        self.assertEqual(wrapped, legacy)


class SealTypographyQcTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._td.name)
        rf.reset_cache_for_tests()

    def tearDown(self):
        self._td.cleanup()
        os.environ.pop(rf.ENFORCE_ENV, None)
        rf.reset_cache_for_tests()

    def _report(self, obj_or_text):
        p = self.run_dir / "working" / "qc" / "typography_qc_report.json"
        _write(p, obj_or_text)

    def test_legit_report_passes_legacy_and_runfacts_and_wired_gate(self):
        self._report({
            "gate": "Phase Typography-QC", "average": 9.1, "pass": True,
            "triggered_autofails": [],
            "qc_independence": {"graded_by": "typography-qc-specialist", "independent": True},
        })
        legacy_ok, legacy_reasons = pv.PHASE_VERIFIERS["P-TYPO-QC"].__wrapped__(self.run_dir) \
            if hasattr(pv.PHASE_VERIFIERS["P-TYPO-QC"], "__wrapped__") \
            else pv._verify_json_artifact("working/qc/typography_qc_report.json")(self.run_dir)
        self.assertTrue(legacy_ok)
        facts = rf.seal(self.run_dir, force=True)
        verdict, _d = rf.verify_qc(facts, "typography")
        self.assertIs(verdict, rf.Verdict.PASS)
        self.assertEqual(facts.findings(), [])
        wired_ok, wired_reasons = pv.verify("P-TYPO-QC", self.run_dir)
        self.assertTrue(wired_ok)
        self.assertEqual(wired_reasons, [])

    def test_proven_gap_pass_false_report_still_returns_legacy_true_in_report_only(self):
        """DIVERGENCE, retargeted by PD-924.

        PD-075 closed the old acceptance gap: a pass:false report no longer
        sails through the legacy gate, so a STATIC pass:false fixture can no
        longer produce the divergence this test is named for. The fixture is
        now the stale-seal shape, which reproduces the same disagreement
        without asserting the defect:

          1. admit the run while the report on disk is untrusted (the seal
             RunFacts holds from here on);
          2. repair the artifact on disk into a SHAPE-VALID PASSING report over
             tokens at min_body_pt 18 (the legacy teeth then PASS it);
          3. run the wired gate: legacy PASS, RunFacts FAIL on the sealed bytes.

        Every assertion below is the ORIGINAL one, unchanged in polarity and in
        what it names — this test's name is about the legacy TRUE surviving
        report-only mode, so that is exactly what it still pins."""
        self._report('{"gate":"typography","pass":false,"average":2.1,'
                     '"failures":["everything is broken"]}')
        rf.reset_cache_for_tests()
        rf.get_or_seal(self.run_dir)          # (1) the seal of record
        self._report(_pd924_clean_report())   # (2) repaired on disk
        _pd924_tokens(self.run_dir, min_body_pt="18")
        os.environ.pop(rf.ENFORCE_ENV, None)

        ok, reasons = pv.verify("P-TYPO-QC", self.run_dir)
        self.assertTrue(ok, "report-only mode must not change the legacy PASS result")
        self.assertEqual(reasons, [])

        facts = rf.get_or_seal(self.run_dir)
        verdict, detail = rf.verify_qc(facts, "typography")
        self.assertIs(verdict, rf.Verdict.FAIL)
        for needle in ("expected 'Phase Typography-QC'", "below the 8.5",
                       "does not affirmatively mark pass:true", "AF-QC-INDEPENDENCE"):
            self.assertIn(needle, detail)
        findings = facts.findings()
        self.assertEqual(len(findings), 1)
        self.assertIn("qc[typography]", findings[0])

    def test_the_font_floor_teeth_still_bite_a_shape_valid_report(self):
        """PD-924 control for the fixture above: the repaired report is a
        genuine PASS for the legacy SHAPE gate and is refused ONLY because the
        design tokens sit under the font floor. Drop min_body_pt to 12 and the
        legacy gate flips to REFUSE — so the token value is load-bearing in
        the retargeted fixture, not decoration."""
        self._report(_pd924_clean_report())
        _pd924_tokens(self.run_dir, min_body_pt="18")
        path = self.run_dir / "working" / "qc" / "typography_qc_report.json"
        self.assertEqual(bd._chk_typography_qc(path), "",
                         "tokens at the floor must pass the legacy teeth")
        _pd924_tokens(self.run_dir, min_body_pt="12")
        self.assertIn("below the 18pt body floor", bd._chk_typography_qc(path))

    def test_enforcing_flag_flips_the_gate_and_never_regresses_a_legit_report(self):
        os.environ[rf.ENFORCE_ENV] = "1"
        try:
            self._report('{"gate":"typography","pass":false,"average":2.1}')
            rf.reset_cache_for_tests()
            ok, reasons = pv.verify("P-TYPO-QC", self.run_dir)
            self.assertFalse(ok, "enforcing mode must reject the proven-tampered report")
            self.assertTrue(reasons and reasons[0])

            self._report({
                "gate": "Phase Typography-QC", "average": 9.4, "pass": True,
                "triggered_autofails": [],
                "qc_independence": {"graded_by": "typography-qc-specialist",
                                    "independent": True},
            })
            rf.reset_cache_for_tests()
            ok2, reasons2 = pv.verify("P-TYPO-QC", self.run_dir)
            self.assertTrue(ok2, "enforcing mode must still pass a legitimate report")
            self.assertEqual(reasons2, [])
        finally:
            os.environ.pop(rf.ENFORCE_ENV, None)


class EnforcementModeSealedAtAdmissionTest(unittest.TestCase):
    """FIX: enforcing() used to be read from os.environ AT CALL TIME by every
    consumer, so a single run's enforcement mode could change mid-run purely
    because the environment changed after the run was already admitted. A
    prior version of this fix sealed the mode into RunFacts.enforcing once at
    seal() time -- but only protected the NOT-forced (cached) path: every
    force=True reseal (verifier_registry.VerifierSpec.seal_into's
    "transactional" seal, used by the MAJORITY of registered gates —
    qc_report_verifier, priority_shift_verifier, final_qc_verifier,
    artifact_verifier, and all six slice-3 composite_verifier specs) still
    called the live enforcing() primitive fresh on every single call, so the
    SAME bug reappeared one layer deeper. This class proves the CURRENT fix
    closes both: (1)+(2) the front-door (cached) path, matching the earlier
    fix's own proof; (3) the force=True registry reseal path the verifier
    used to break it; (4) the default (unset env) is still inert/report-only,
    unchanged by this fix."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._td.name)
        rf.reset_cache_for_tests()
        os.environ.pop(rf.ENFORCE_ENV, None)

    def tearDown(self):
        self._td.cleanup()
        os.environ.pop(rf.ENFORCE_ENV, None)
        rf.reset_cache_for_tests()

    def test_runfacts_carries_a_sealed_enforcing_field(self):
        facts = rf.seal(self.run_dir, force=True)
        self.assertIn("enforcing", facts.__dataclass_fields__)
        self.assertIs(facts.enforcing, False)

    def test_default_unset_env_is_still_inert_report_only(self):
        """Confirms still inert by default: with the env var unset (the real
        production default -- nothing sets it today), a freshly sealed run's
        mode is False, matching the module's documented default."""
        self.assertNotIn(rf.ENFORCE_ENV, os.environ)
        facts = rf.seal(self.run_dir, force=True)
        self.assertIs(facts.enforcing, False)
        self.assertIs(rf.enforcing(), False)

    def test_sealed_mode_survives_env_mutated_after_admission(self):
        """The front-door acceptance proof: admit a run with the flag OFF,
        THEN set the env var mid-run (no re-admission), and confirm the
        ALREADY SEALED record's mode did not move -- including through a
        LATER force=True reseal of the SAME run_dir, which is exactly the
        path the rejected fix left open."""
        facts = rf.seal(self.run_dir, force=True)
        self.assertIs(facts.enforcing, False)
        os.environ[rf.ENFORCE_ENV] = "1"
        try:
            # rf.enforcing() itself is the raw, unsealed, live primitive --
            # it correctly reflects the new environment (that is its job).
            self.assertIs(rf.enforcing(), True)
            # But the RECORD ALREADY SEALED for this run must be untouched.
            self.assertIs(facts.enforcing, False)
            cached_again = rf.get_or_seal(self.run_dir)
            self.assertIs(cached_again is facts, True,
                          "get_or_seal must return the SAME cached record, "
                          "not re-admit / re-read the environment")
            self.assertIs(cached_again.enforcing, False)
            # THE PART THE REJECTED FIX GOT WRONG: a force=True reseal of the
            # SAME run_dir, after the env changed, must STILL carry the
            # run's original mode -- not a fresh live read.
            reforced = rf.seal(self.run_dir, force=True)
            self.assertIs(reforced.enforcing, False,
                          "force=True re-measures artifact facts; it must "
                          "NOT re-poll the enforcement policy for a run_dir "
                          "that has already been touched in this process")
        finally:
            os.environ.pop(rf.ENFORCE_ENV, None)

    def test_a_real_gate_verdict_does_not_flip_when_env_changes_mid_run(self):
        """End-to-end via the front-door (get_or_seal) path, retargeted by
        PD-924. PD-075 gave the legacy half real teeth, so a pass:false report
        is no longer the gap; the fixture is now a SHAPE-VALID PASSING report
        over sub-floor design tokens — legacy FAIL, RunFacts PASS.

        The property is unchanged: admit the run with the flag OFF, then flip
        it ON without re-admitting, and the wired gate must return the SAME
        result both times. It now bites HARDER than before, because the two
        halves disagree: pre-fix the enforcing branch returned RunFacts' PASS
        and LIFTED the legacy FAIL (True after, False before — the equality
        assertion goes red). PD-075's `and legacy_ok` guard is what keeps the
        legacy refusal standing, so this test now pins that guard too."""
        p = self.run_dir / "working" / "qc" / "typography_qc_report.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        # PD-924 fixture: seal the run while the artifact is untrusted, then
        # repair it on disk. The sealed mode is what this test pins, and it is
        # resolved on the FIRST touch — which is the admission below.
        p.write_text('{"gate": "typography", "pass": false, "average": 2.1}')
        rf.reset_cache_for_tests()
        rf.get_or_seal(self.run_dir)
        p.write_text(json.dumps(_pd924_clean_report()))
        _pd924_tokens(self.run_dir, min_body_pt="18")

        self.assertNotIn(rf.ENFORCE_ENV, os.environ)
        ok_before, reasons_before = pv.verify("P-TYPO-QC", self.run_dir)
        self.assertTrue(ok_before, "report-only admission must pass the legacy result")

        os.environ[rf.ENFORCE_ENV] = "1"
        try:
            # deliberately NOT calling rf.reset_cache_for_tests() -- the run
            # was already admitted above; nothing should re-seal it just
            # because the environment changed.
            ok_after, reasons_after = pv.verify("P-TYPO-QC", self.run_dir)
            self.assertEqual(
                ok_before, ok_after,
                "the SAME sealed run's gate verdict must not change just "
                "because the environment changed after admission",
            )
            self.assertTrue(ok_after)
            self.assertEqual(reasons_after, [])
        finally:
            os.environ.pop(rf.ENFORCE_ENV, None)

    def test_registry_force_reseal_does_not_drift_mid_run(self):
        """THE DEFECT THE VERIFIER FOUND, reproduced as a regression test:
        every VerifierSpec.seal_into() (verifier_registry.py, the base for
        every T1/T2/slice-3 gate) unconditionally calls
        presentation_job.runfacts.seal(..., force=True) -- the "transactional
        seal" that re-measures artifact facts on every single gate check.
        The rejected fix sealed the mode only inside the not-forced cached
        branch, so THIS force=True path kept calling the live enforcing()
        primitive fresh on every call -- meaning two checks of the SAME
        registry gate, on the SAME already-admitted run, could see two
        DIFFERENT modes if the environment changed between them.

        This reproduces exactly that shape: admit the run (front door, flag
        OFF), run a registered qc_report_verifier gate through the registry
        ONCE, flip the env var with NO re-admission, then run the SAME gate
        through the registry AGAIN. Both calls must agree -- the second call
        must NOT pick up the live env change, because this run_dir was
        already touched (this is a force=True reseal of an EXISTING
        admission, not a new one)."""
        import verifier_registry as vr

        p = self.run_dir / "working" / "qc" / "typography_qc_report.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"gate": "typography", "pass": False, "average": 2.1}))

        def _legacy_always_pass(_run_dir):
            return True, []

        base_spec = vr.qc_report_verifier("typography")
        spec = vr.VerifierSpec(gate=base_spec.gate, verifier=base_spec.verifier,
                               verdict=base_spec.verdict, artifacts=base_spec.artifacts,
                               legacy=_legacy_always_pass, config=None)

        # --- front-door admission, flag OFF ---
        self.assertNotIn(rf.ENFORCE_ENV, os.environ)
        front_door = rf.get_or_seal(self.run_dir)
        self.assertIs(front_door.enforcing, False)

        # --- registry gate check #1 (force=True inside seal_into), flag OFF ---
        ok1, _reasons1 = spec.run_verifier(self.run_dir)
        self.assertTrue(ok1, "report-only: the always-pass legacy result wins")

        # --- mid-run drift: env flips, NO re-admission ---
        os.environ[rf.ENFORCE_ENV] = "1"
        try:
            # the front-door record for THIS run_dir is still cached False
            still_cached = rf._SEAL_CACHE.get(str(self.run_dir.resolve()))
            self.assertIsNotNone(still_cached)
            self.assertIs(still_cached.enforcing, False)

            # --- registry gate check #2, SAME run_dir, SAME (unforced) admission ---
            ok2, reasons2 = spec.run_verifier(self.run_dir)
            self.assertEqual(
                ok1, ok2,
                "a force=True registry reseal of an ALREADY-admitted run_dir "
                "must not pick up a live environment change mid-run -- this "
                "is the exact defect the verifier found in the prior fix",
            )
            self.assertTrue(ok2)
            self.assertEqual(reasons2, [])
        finally:
            os.environ.pop(rf.ENFORCE_ENV, None)


class GateIntegrityPurityTest(unittest.TestCase):
    """Confirms gate_integrity_check.py --purity (Guard B) actually parses
    runfacts.py and finds the two migrated verdict functions clean — a light
    in-process re-check of the same AST logic (the full CLI invocation is
    exercised separately as part of the acceptance run)."""

    def test_verify_owner_skip_and_verify_qc_are_ast_clean(self):
        sys.path.insert(0, str(HERE))
        import gate_integrity_check as gic
        problems = gic.run_purity_check()
        self.assertEqual(problems, [])


def main() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (FactAndVerdictPrimitivesTest, SealOwnerSkipTest,
                SealTypographyQcTest, EnforcementModeSealedAtAdmissionTest,
                GateIntegrityPurityTest):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
