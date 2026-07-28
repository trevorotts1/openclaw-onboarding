#!/usr/bin/env python3
"""
test_retired_roles.py — proves the U048 legibility-role retirement.

Cases:
  1. The registry parses as JSON and the new pattern has the correct shape.
  2. Guard B is clean against the real tree AND actually scanned files.
  3. Positive control: the pattern has teeth — a live re-introduction is caught.
  4. Negative control: the history exemption works — a documented mention passes.
  5. Narrow scope holds — a live re-introduction under sops/ passes.
  6. The two sibling roles are NOT registered — no pattern id mentions
     image-grounding-steward or representation-casting-director.

The deliberate gap: this test places the offending file at sops/probe-role.md for
case 5 and asserts zero offenders. That is BY DESIGN: the pattern's scope is '*.md'
(top-level only) so the machine-only-doctrine rescue (U003) is not bricked when it
lands the 489-line how-to.md containing the slug.

Run:  python3 test_retired_roles.py
Exit: 0 = all assertions passed; 1 = a case failed.
"""

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent   # .../presentations
SCRIPTS = HERE / "scripts"


def load_registry():
    """Return the real registry dict."""
    reg_path = HERE / "retired-doctrine-patterns.json"
    with open(reg_path) as f:
        reg = json.load(f)
    return reg


def load_guard():
    """Import doctrine_residual_check by file location."""
    guard_path = SCRIPTS / "doctrine_residual_check.py"
    spec = importlib.util.spec_from_file_location("doctrine_residual_check", str(guard_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_fixture_root(md_lines, subdir=""):
    """Build a minimal presentations root with one .md file, return (root, pres_dir, guard_mod)."""
    root = tempfile.mkdtemp(prefix="u048test_")
    pres = os.path.join(root, "presentations")
    scripts_dir = os.path.join(pres, "scripts")
    os.makedirs(scripts_dir)

    # Copy the real registry so the guard can load it.
    shutil.copy(
        str(HERE / "retired-doctrine-patterns.json"),
        os.path.join(pres, "retired-doctrine-patterns.json"),
    )

    # The guard resolves its PRES_DIR = HERE.parent where HERE is its own script path.
    # We cannot just copy the guard script because it hardcodes PRES_DIR relative to
    # its location. Instead, we import and then monkey-patch PRES_DIR.
    return root, pres


class TestRetiredRoles(unittest.TestCase):
    """Unit tests for the U048 legibility-role retirement."""

    @classmethod
    def setUpClass(cls):
        cls.registry = load_registry()
        cls.guard = load_guard()

    # ------------------------------------------------------------------
    # Case 1 — registry shape
    # ------------------------------------------------------------------
    def test_1_pattern_registered_with_correct_shape(self):
        """The new pattern is in the registry with id, scope='*.md', no near, correct regex."""
        patterns = self.registry["patterns"]
        self.assertEqual(len(patterns), 5, "expected 5 patterns (was 4)")

        hits = [p for p in patterns if p["id"] == "role-assembled-slide-legibility-qc-retired"]
        self.assertTrue(hits, "new pattern not found by id")
        h = hits[0]

        self.assertEqual(h.get("scope"), "*.md",
                         f'scope must be "*.md", got {h.get("scope")!r}')
        self.assertIsNone(h.get("near"),
                          f"near must be None/absent, got {h.get('near')!r}")

        import re
        rx = re.compile(h["pattern"], re.IGNORECASE | re.MULTILINE)
        # Must match both separators.
        self.assertTrue(rx.search("assembled-slide-legibility-qc"),
                        "must match hyphen spelling")
        self.assertTrue(rx.search("assembled_slide_legibility_qc"),
                        "must match underscore spelling")
        # Must NOT match without the trailing qc segment.
        self.assertFalse(rx.search("assembled-slide-legibility"),
                         "must NOT match without trailing qc")

    # ------------------------------------------------------------------
    # Case 2 — Guard B is clean against the real tree
    # ------------------------------------------------------------------
    def test_2_guard_clean_and_scanned_files(self):
        """Guard B reports clean AND files_scanned > 0 on the real tree."""
        offenders, scanned = self.guard.run_check(self.registry)
        self.assertEqual(offenders, [], "Guard B must be clean on the real tree")
        self.assertGreater(scanned, 0, "files_scanned must be > 0 (else scan didn't run)")

    # ------------------------------------------------------------------
    # Case 3 — Positive control: live re-introduction is caught
    # ------------------------------------------------------------------
    def test_3_positive_control_live_caught(self):
        """A live re-introduction in a top-level .md is caught by the guard."""
        root, pres = build_fixture_root([])
        try:
            # Monkey-patch PRES_DIR to point at our fixture.
            orig_pres_dir = self.guard.PRES_DIR
            self.guard.PRES_DIR = Path(pres)

            try:
                # Write a probe role with the live slug.
                probe = Path(pres) / "probe-role.md"
                probe.write_text(
                    "# Probe role\n\n"
                    "Route assembled-slide-legibility-qc for the final QC pass.\n"
                )
                offenders, scanned = self.guard.run_check(self.registry)
                self.assertGreater(scanned, 0, "files_scanned must be > 0")
                self.assertEqual(len(offenders), 1,
                                 "positive control: exactly one offender expected")
                self.assertEqual(offenders[0]["id"],
                                 "role-assembled-slide-legibility-qc-retired")
                self.assertEqual(offenders[0]["file"], "probe-role.md")
            finally:
                self.guard.PRES_DIR = orig_pres_dir
        finally:
            shutil.rmtree(root, ignore_errors=True)

    # ------------------------------------------------------------------
    # Case 4 — Negative control: history exemption works
    # ------------------------------------------------------------------
    def test_4_history_exemption_works(self):
        """A documented retirement mention passes with a marker above it."""
        root, pres = build_fixture_root([])
        try:
            orig_pres_dir = self.guard.PRES_DIR
            self.guard.PRES_DIR = Path(pres)
            try:
                probe = Path(pres) / "probe-role.md"
                probe.write_text(
                    "# Probe role\n\n"
                    "This role is RETIRED (U048).\n"
                    "Route assembled-slide-legibility-qc for the final QC pass.\n"
                )
                offenders, scanned = self.guard.run_check(self.registry)
                self.assertGreater(scanned, 0, "files_scanned must be > 0")
                self.assertEqual(offenders, [],
                                 "negative control: zero offenders when marked as history")
            finally:
                self.guard.PRES_DIR = orig_pres_dir
        finally:
            shutil.rmtree(root, ignore_errors=True)

    # ------------------------------------------------------------------
    # Case 5 — Narrow scope: sops/ escapes
    # ------------------------------------------------------------------
    def test_5_narrow_scope_sops_escapes(self):
        """A live re-introduction under sops/ is NOT caught — scope is *.md only.
        This is deliberate so the machine-only-doctrine rescue (U003) is not bricked
        when it lands the 489-line how-to.md containing the slug."""
        root, pres = build_fixture_root([])
        try:
            orig_pres_dir = self.guard.PRES_DIR
            self.guard.PRES_DIR = Path(pres)
            try:
                sops_dir = Path(pres) / "sops"
                sops_dir.mkdir()
                probe = sops_dir / "probe-role.md"
                probe.write_text(
                    "# Probe role\n\n"
                    "Route assembled-slide-legibility-qc for the final QC pass.\n"
                )
                offenders, scanned = self.guard.run_check(self.registry)
                # files_scanned may be 0 if *.md glob resolves nothing at top level,
                # but the guard still passed — the job here is just to prove that
                # the sops/ file did NOT produce an offender.
                self.assertEqual(offenders, [],
                                 "sops/ re-introduction must NOT trigger — scope is *.md only")
            finally:
                self.guard.PRES_DIR = orig_pres_dir
        finally:
            shutil.rmtree(root, ignore_errors=True)

    # ------------------------------------------------------------------
    # Case 6 — Sibling roles NOT registered
    # ------------------------------------------------------------------
    def test_6_sibling_roles_not_registered(self):
        """image-grounding-steward and representation-casting-director are NOT registered."""
        pattern_ids = {p["id"] for p in self.registry["patterns"]}
        for slug in ("image-grounding-steward", "representation-casting-director"):
            for pid in pattern_ids:
                self.assertNotIn(
                    slug, pid,
                    f"pattern id '{pid}' mentions '{slug}' — sibling role must not be registered"
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
