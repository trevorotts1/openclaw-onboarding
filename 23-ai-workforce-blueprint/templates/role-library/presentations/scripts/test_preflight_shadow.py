#!/usr/bin/env python3
"""
test_preflight_shadow.py — TRUST BOUNDARY, SURFACE A: unit tests + acceptance
proof for presentation_job/preflight_shadow.py (the "core" builder's
deliverable — the admission validator).

Hermetic: no network, no subprocess spawn of build_deck.py's CLI. Every
fixture lives under a tempfile.mkdtemp(). Deliberately reuses the EXISTING
run-dir fixture builder from this repo's own test_preflight.py
(`make_workdir(with_artifacts=True)`) rather than authoring a new one — that
fixture already produces a run dir that clears all 60 PREFLIGHT_REQUIRED
gates for real, so "legitimate run" in these tests means what it says. The
only fixture content this file writes itself is the TAMPER step (an action
taken on an already-legitimate fixture, not a fixture invented to make a
check pass), which is exactly what "a tampered run" needs to mean for the
acceptance bar to be honest.

Run:  python3 test_preflight_shadow.py
      python3 -m pytest test_preflight_shadow.py -q
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_deck as bd  # noqa: E402  (real gate functions, read-only import)
from presentation_job import preflight_shadow as ps  # noqa: E402
from presentation_job import runfacts as rf  # noqa: E402
from test_preflight import make_workdir  # noqa: E402  (existing repo fixture, not authored here)


def _read_ledger(root: Path) -> list:
    p = root / ps.SHADOW_LEDGER_REL
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


class LegitimateRunUnaffectedTest(unittest.TestCase):
    """ACCEPTANCE #1: a legitimate run is unaffected."""

    def setUp(self):
        rf.reset_cache_for_tests()
        ps.reset_cache_for_tests()
        self.root = make_workdir(with_artifacts=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        rf.reset_cache_for_tests()
        ps.reset_cache_for_tests()

    def test_wrapped_result_identical_to_unwrapped_for_artifact_scoped_gate(self):
        manifest = ps.admit(self.root)
        found = self.root / "working" / "copy" / "intake.json"
        self.assertTrue(found.is_file())

        direct = bd._chk_intake(found)
        wrapped = ps.shadow_check(
            bd._chk_intake, found,
            rel="working/copy/intake.json", label="intake.json",
            run_dir=self.root, manifest=manifest,
        )
        self.assertEqual(direct, wrapped, "shadow_check must return EXACTLY what "
                          "the legacy gate returns on a legitimate run")
        self.assertEqual(wrapped, "", "the reused fixture must actually pass "
                          "_chk_intake — otherwise this isn't proving a "
                          "legitimate-run scenario")

    def test_no_divergence_recorded_for_unchanged_file(self):
        manifest = ps.admit(self.root)
        found = self.root / "working" / "copy" / "intake.json"
        ps.shadow_check(
            bd._chk_intake, found,
            rel="working/copy/intake.json", label="intake.json",
            run_dir=self.root, manifest=manifest,
        )
        lines = _read_ledger(self.root)
        self.assertEqual(len(lines), 1)
        rec = lines[0]
        self.assertEqual(rec["divergence_kind"], "unchanged")
        self.assertFalse(rec["would_have_blocked"])
        self.assertEqual(rec["legacy_result"], "PASS")

    def test_run_dir_scoped_gate_also_unaffected_and_recorded(self):
        manifest = ps.admit(self.root)
        direct = bd._chk_research_map(self.root, None)
        wrapped = ps.shadow_check(
            bd._chk_research_map, self.root, None,
            rel=None, label="research_map", run_dir=self.root, manifest=manifest,
        )
        self.assertEqual(direct, wrapped)
        lines = _read_ledger(self.root)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["divergence_kind"], "run_dir_scoped")
        self.assertFalse(lines[0]["would_have_blocked"])

    def test_ledger_file_is_0600(self):
        manifest = ps.admit(self.root)
        found = self.root / "working" / "copy" / "intake.json"
        ps.shadow_check(bd._chk_intake, found, rel="working/copy/intake.json",
                         label="intake.json", run_dir=self.root, manifest=manifest)
        p = self.root / ps.SHADOW_LEDGER_REL
        mode = p.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)


class TamperedRunDetectedButProceedsTest(unittest.TestCase):
    """ACCEPTANCE #2/#3/#4: a tampered run is DETECTED and RECORDED, but still
    PROCEEDS (report-only — nothing here can block). The record names the
    specific fact (which path, which gate) and where it came from (resolved
    path + run_dir + label)."""

    def setUp(self):
        rf.reset_cache_for_tests()
        ps.reset_cache_for_tests()
        self.root = make_workdir(with_artifacts=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        rf.reset_cache_for_tests()
        ps.reset_cache_for_tests()

    def test_content_tampered_after_admission_is_detected_run_still_proceeds(self):
        manifest = ps.admit(self.root)
        found = self.root / "working" / "copy" / "intake.json"

        # TAMPER: mutate a real field AFTER admission, in a way that does NOT
        # flip _chk_intake's own verdict (target_talk_minutes just needs to be
        # a positive number) — this is the exact silent-drift scenario the
        # trust boundary exists to catch: the legacy gate is blind to it.
        before = json.loads(found.read_text())
        self.assertEqual(before["target_talk_minutes"], 30)
        after = dict(before)
        after["target_talk_minutes"] = 5
        found.write_text(json.dumps(after))

        legacy_direct = bd._chk_intake(found)
        self.assertEqual(legacy_direct, "", "sanity: the legacy gate really is "
                          "blind to this specific tamper")

        wrapped = ps.shadow_check(
            bd._chk_intake, found,
            rel="working/copy/intake.json", label="intake.json",
            run_dir=self.root, manifest=manifest,
        )

        # REPORT-ONLY: the run gets EXACTLY the legacy result — it proceeds.
        self.assertEqual(wrapped, "", "tampering must not change what the "
                          "gate returns in this pass — report-only")
        self.assertEqual(wrapped, legacy_direct)

        # DETECTED + RECORDED: the ledger independently caught it.
        lines = _read_ledger(self.root)
        self.assertEqual(len(lines), 1)
        rec = lines[0]
        self.assertEqual(rec["divergence_kind"], "content_changed_since_admission")
        self.assertTrue(rec["would_have_blocked"])
        self.assertEqual(rec["legacy_result"], "PASS")
        # Names the specific fact and where it came from.
        self.assertEqual(rec["resolved_relkey"], "working/copy/intake.json")
        self.assertEqual(rec["label"], "intake.json")
        self.assertEqual(rec["run_dir"], str(self.root))
        self.assertEqual(rec["check_fn"], "_chk_intake")
        self.assertIsNotNone(rec["admission_sha256"])
        self.assertIsNotNone(rec["check_sha256"])
        self.assertNotEqual(rec["admission_sha256"], rec["check_sha256"])

    def test_artifact_deleted_after_admission_is_detected_legacy_failure_unchanged(self):
        manifest = ps.admit(self.root)
        found = self.root / "working" / "copy" / "arc_allocation.json"
        self.assertTrue(found.is_file())

        # TAMPER: delete the artifact after admission (the run_preflight loop
        # will resolve found=None for this gate, exactly like a normal
        # never-produced-it absence — but this one HAD a sealed history).
        found.unlink()

        legacy_direct = bd._chk_arc(None)
        self.assertNotEqual(legacy_direct, "", "sanity: _chk_arc really does "
                             "fail on a missing artifact")

        wrapped = ps.shadow_check(
            bd._chk_arc, None,
            rel="working/copy/arc_allocation.json", label="arc allocation",
            run_dir=self.root, manifest=manifest,
        )
        self.assertEqual(wrapped, legacy_direct, "the wrapper must not change "
                          "the legacy failure message")

        lines = _read_ledger(self.root)
        self.assertEqual(len(lines), 1)
        rec = lines[0]
        self.assertEqual(rec["divergence_kind"], "path_vanished_since_admission")
        self.assertTrue(rec["would_have_blocked"])
        self.assertEqual(rec["resolved_relkey"], "working/copy/arc_allocation.json")
        self.assertIsNotNone(rec["admission_sha256"])

    def test_shadow_check_never_raises_even_if_manifest_is_none(self):
        """A caller that forgot to admit() first (or hit a wiring gap) must still
        get the legacy result — never a crash, never a block."""
        found = self.root / "working" / "copy" / "intake.json"
        wrapped = ps.shadow_check(
            bd._chk_intake, found,
            rel="working/copy/intake.json", label="intake.json",
            run_dir=self.root, manifest=None,
        )
        self.assertEqual(wrapped, "")
        lines = _read_ledger(self.root)
        self.assertEqual(lines[0]["divergence_kind"], "no_baseline_available")
        self.assertFalse(lines[0]["would_have_blocked"])

    def test_shadow_check_never_raises_when_check_fn_itself_raises(self):
        """If the LEGACY check_fn raises, shadow_check must not swallow that
        (the legacy contract is untouched) but the shadow bookkeeping around
        it must never be what breaks the caller with a DIFFERENT exception."""
        def _boom(_path):
            raise RuntimeError("legacy gate exploded")
        manifest = ps.admit(self.root)
        with self.assertRaises(RuntimeError):
            ps.shadow_check(_boom, self.root / "nope.json", rel="nope.json",
                             label="boom", run_dir=self.root, manifest=manifest)


class GlobResolvedGateTest(unittest.TestCase):
    """A PREFLIGHT_REQUIRED entry whose rel contains '*' (e.g. research
    briefs) must still be classified correctly when the file vanishes."""

    def setUp(self):
        rf.reset_cache_for_tests()
        ps.reset_cache_for_tests()
        self.root = make_workdir(with_artifacts=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        rf.reset_cache_for_tests()
        ps.reset_cache_for_tests()

    def test_glob_pattern_vanish_detected(self):
        manifest = ps.admit(self.root)
        briefs = sorted(self.root.glob("working/research/brief-*.md"))
        self.assertTrue(briefs, "fixture must have produced a research brief")
        briefs[0].unlink()

        wrapped = ps.shadow_check(
            lambda p: "" if p else "file absent", None,
            rel="working/research/brief-*.md", label="research brief",
            run_dir=self.root, manifest=manifest,
        )
        self.assertEqual(wrapped, "file absent")
        lines = _read_ledger(self.root)
        self.assertEqual(lines[0]["divergence_kind"], "path_vanished_since_admission")
        self.assertTrue(lines[0]["would_have_blocked"])


class SnapshotBoundsTest(unittest.TestCase):
    """admit() must never be able to raise or hang, and must degrade honestly
    (never silently report "unchanged") when its own bounds are hit."""

    def setUp(self):
        rf.reset_cache_for_tests()
        ps.reset_cache_for_tests()
        self.root = Path(tempfile.mkdtemp(prefix="ps_bounds_test_"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        rf.reset_cache_for_tests()
        ps.reset_cache_for_tests()

    def test_oversized_file_skipped_not_asserted_unchanged(self):
        big = self.root / "working" / "big.bin"
        big.parent.mkdir(parents=True, exist_ok=True)
        big.write_bytes(b"x" * 2048)
        manifest = ps.admit(self.root, max_file_bytes=1024, force=True)
        snap = manifest.paths.get("working/big.bin")
        self.assertIsNotNone(snap)
        self.assertIsNone(snap.sha256)
        self.assertIn("exceeds", snap.skipped_reason)

    def test_symlink_never_treated_as_a_baseline(self):
        target = self.root / "real.txt"
        target.write_text("hello")
        link = self.root / "link.txt"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unsupported in this environment")
        manifest = ps.admit(self.root, force=True)
        snap = manifest.paths.get("link.txt")
        self.assertIsNotNone(snap)
        self.assertIsNone(snap.sha256)
        self.assertIn("symlink", snap.skipped_reason)

    def test_admit_on_nonexistent_dir_never_raises(self):
        ghost = self.root / "does-not-exist"
        manifest = ps.admit(ghost, force=True)  # must not raise
        # NOTE: runfacts.get_or_seal()'s own _best_effort_save() creates
        # <ghost>/working/checkpoints/.runfacts.sealed.json as a side effect
        # (existing, unmodified behavior of presentation_job.runfacts — not
        # this module's doing), so the walk that runs immediately after can
        # legitimately see that one freshly-written file. What matters here
        # is that admit() never raises and never hangs on a dir that didn't
        # exist a moment ago.
        self.assertGreaterEqual(manifest.file_count, 0)
        self.assertTrue(ghost.exists(), "sanity: confirms the side effect above")

    def test_file_count_cap_truncates_not_crashes(self):
        d = self.root / "many"
        d.mkdir()
        for i in range(12):
            (d / f"f{i}.txt").write_text(str(i))
        manifest = ps.admit(self.root, max_files=5, force=True)
        self.assertTrue(manifest.truncated)
        self.assertLessEqual(manifest.file_count, 5)


class AdmissionCachingTest(unittest.TestCase):
    def setUp(self):
        rf.reset_cache_for_tests()
        ps.reset_cache_for_tests()
        self.root = make_workdir(with_artifacts=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        rf.reset_cache_for_tests()
        ps.reset_cache_for_tests()

    def test_admit_is_cached_per_run_dir_unless_forced(self):
        m1 = ps.admit(self.root)
        (self.root / "working" / "copy" / "intake.json").write_text("{}")
        m2 = ps.admit(self.root)  # cached — must NOT reflect the mutation above
        self.assertIs(m1, m2)
        m3 = ps.admit(self.root, force=True)
        self.assertIsNot(m1, m3)


def main() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (LegitimateRunUnaffectedTest, TamperedRunDetectedButProceedsTest,
                GlobResolvedGateTest, SnapshotBoundsTest, AdmissionCachingTest):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
