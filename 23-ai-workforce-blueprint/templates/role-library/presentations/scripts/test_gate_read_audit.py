#!/usr/bin/env python3
"""
test_gate_read_audit.py — unit tests for presentation_job/gate_read_audit.py,
the fix for the PREFLIGHT_REQUIRED "83% blind spot": 50 of 60 gates in
build_deck.PREFLIGHT_REQUIRED carry rel=None (run-dir-scoped: no single
declared file), so any snapshot mechanism keyed off that static `rel` has
NO file to snapshot for those 50 and is mathematically incapable of ever
registering a divergence for them. This module observes what each gate
ACTUALLY reads (sys.addaudithook) instead of trusting the declared tuple.

Hermetic: no network, no subprocess. Every fixture lives under
tempfile.mkdtemp() and reuses the SAME real gate-fixture builders
test_preflight.py already ships (_coverage_run_dir et al.) rather than
hand-authoring parallel ones — these tests exercise the real
build_deck._chk_* functions via the real PREFLIGHT_REQUIRED list, not a
substitute.

Run:  python3 test_gate_read_audit.py
      python3 -m pytest test_gate_read_audit.py -q
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from presentation_job import gate_read_audit as gra  # noqa: E402
import build_deck as bd  # noqa: E402
import test_preflight as tp  # noqa: E402


class ReadTracingPrimitiveTest(unittest.TestCase):
    def test_trace_reads_observes_a_path_read_via_pathlib(self):
        d = Path(tempfile.mkdtemp())
        f = d / "a.json"
        f.write_text("{}")
        _result, paths = gra.trace_reads(lambda: f.read_text())
        self.assertIn(str(f), paths)

    def test_trace_reads_does_not_leak_across_calls(self):
        """A file opened OUTSIDE trace_reads() must never appear in a LATER
        trace_reads() call's result — recording must be call-scoped, not
        cumulative/global."""
        d = Path(tempfile.mkdtemp())
        f1 = d / "before.json"
        f1.write_text("{}")
        f1.read_text()  # opened before any recording is active

        f2 = d / "during.json"
        f2.write_text("{}")
        _result, paths = gra.trace_reads(lambda: f2.read_text())
        self.assertIn(str(f2), paths)
        self.assertNotIn(str(f1), paths)

    def test_paths_under_filters_to_run_dir_only(self):
        run_dir = Path(tempfile.mkdtemp())
        inside = run_dir / "working" / "x.json"
        inside.parent.mkdir(parents=True)
        inside.write_text("{}")
        outside = Path(tempfile.mkdtemp()) / "y.json"
        outside.write_text("{}")

        def _do():
            inside.read_text()
            outside.read_text()

        _result, raw = gra.trace_reads(_do)
        filtered = gra._paths_under(run_dir, raw)
        self.assertIn(str(inside.resolve()), filtered)
        self.assertNotIn(str(outside.resolve()), filtered)


class SealAndVerifyGateReadsTest(unittest.TestCase):
    """The acceptance-shaped test: seal a real rel=None gate's read set
    against a real fixture, prove a legitimate re-verify is silent, then
    prove tampering with the exact file the gate read is DETECTED (recorded,
    never blocked — seal_gate_reads/verify_gate_reads never raise, never
    change what any check() returns)."""

    def _fixture(self):
        # Real repo fixture (test_preflight.py, not authored here):
        # source_slide_count=120, output=120 -> _chk_coverage PASSES.
        run_dir = tp._coverage_run_dir(120, 120)
        gates = [
            (rel, label, phase, check)
            for rel, label, phase, check in bd.PREFLIGHT_REQUIRED
            if check is bd._chk_coverage
        ]
        self.assertEqual(len(gates), 1, "expected exactly one PREFLIGHT_REQUIRED "
                          "entry for _chk_coverage")
        self.assertIsNone(gates[0][0], "_chk_coverage must be rel=None (the exact "
                          "'previously blind' shape this module fixes) or this test "
                          "no longer exercises the bug")
        return run_dir, gates

    def test_gate_confirmed_rel_none_and_passes_on_the_real_fixture(self):
        run_dir, gates = self._fixture()
        reason = bd._chk_coverage(run_dir)
        self.assertEqual(reason, "", f"fixture is broken, gate did not pass: {reason!r}")

    def test_seal_observes_a_real_file_for_a_previously_blind_gate(self):
        run_dir, gates = self._fixture()
        sealed_path = gra.seal_gate_reads(run_dir, gates, None)
        self.assertIsNotNone(sealed_path)
        sealed = json.loads(sealed_path.read_text())
        self.assertEqual(sealed["blind_gate_count"], 1)
        rec = next(iter(sealed["gates"].values()))
        self.assertTrue(rec["was_blind"])
        self.assertTrue(rec["observed_paths"], "seal observed zero files for a gate "
                         "that demonstrably reads mission_prd.json + slides.json")
        self.assertTrue(any(p.endswith("mission_prd.json") for p in rec["observed_paths"]))

    def test_legitimate_reverify_is_silent(self):
        run_dir, gates = self._fixture()
        gra.seal_gate_reads(run_dir, gates, None)
        lines = gra.verify_gate_reads(run_dir, gates, None)
        self.assertEqual(lines, [], f"untampered re-verify must be clean, got: {lines}")

    def test_tampering_the_observed_file_is_detected(self):
        run_dir, gates = self._fixture()
        sealed_path = gra.seal_gate_reads(run_dir, gates, None)
        sealed = json.loads(sealed_path.read_text())
        rec = next(iter(sealed["gates"].values()))
        mission_prd = next(p for p in rec["observed_paths"] if p.endswith("mission_prd.json"))

        # Tamper with EXACTLY the file the gate's own seal proved it reads —
        # not a guess, the seal's own observed_paths names it.
        original = Path(mission_prd).read_text()
        Path(mission_prd).write_text(json.dumps({"source_slide_count": 1}))
        try:
            lines = gra.verify_gate_reads(run_dir, gates, None)
        finally:
            Path(mission_prd).write_text(original)

        self.assertEqual(len(lines), 1, f"expected exactly one divergence, got: {lines}")
        self.assertIn(gra.DIVERGENCE_PREFIX, lines[0])
        self.assertIn(mission_prd, lines[0])
        self.assertIn("was_blind=True", lines[0])

    def test_tampering_never_raises_and_never_blocks(self):
        """The whole point is REPORT-ONLY: verify_gate_reads must never raise,
        and calling it (or seal_gate_reads) must have zero effect on what
        _chk_coverage itself returns."""
        run_dir, gates = self._fixture()
        gra.seal_gate_reads(run_dir, gates, None)
        mission_prd = run_dir / "working" / "copy" / "mission_prd.json"
        original = mission_prd.read_text()
        mission_prd.write_text(json.dumps({"source_slide_count": 999999}))
        try:
            lines = gra.verify_gate_reads(run_dir, gates, None)  # must not raise
            self.assertTrue(lines)
            # The gate's own return value is untouched by the shadow audit —
            # it still evaluates the (now-tampered) file on its own terms.
            reason = bd._chk_coverage(run_dir)
            self.assertIn("AF-COVERAGE-1", reason)
        finally:
            mission_prd.write_text(original)


class BeforeAfterCountTest(unittest.TestCase):
    """Reproduces the defect count named in the fix task and proves the
    before/after capability shift on the real PREFLIGHT_REQUIRED list."""

    def test_before_after_capability_counts(self):
        total = len(bd.PREFLIGHT_REQUIRED)
        self.assertEqual(total, 60)
        before_capable = sum(1 for rel, *_ in bd.PREFLIGHT_REQUIRED if rel is not None)
        before_blind = total - before_capable
        self.assertEqual(before_capable, 10)
        self.assertEqual(before_blind, 50)

        run_dir = tp.make_workdir(True)
        try:
            bd.run_preflight(run_dir)
        except SystemExit:
            pass  # pass/fail of preflight itself is irrelevant to this test
        sealed_path = run_dir / "working" / "checkpoints" / ".gate-reads.sealed.json"
        sealed = json.loads(sealed_path.read_text())
        after_capable = sum(1 for g in sealed["gates"].values() if g.get("observed_paths"))
        after_capable_of_previously_blind = sum(
            1 for g in sealed["gates"].values()
            if g.get("was_blind") and g.get("observed_paths")
        )
        self.assertGreater(after_capable, before_capable,
                            "the audit must strictly increase the number of gates "
                            "capable of registering a divergence")
        self.assertGreater(after_capable_of_previously_blind, 0,
                            "at least one previously-blind (rel=None) gate must now "
                            "have an empirically observed, hashable file")


if __name__ == "__main__":
    unittest.main()
