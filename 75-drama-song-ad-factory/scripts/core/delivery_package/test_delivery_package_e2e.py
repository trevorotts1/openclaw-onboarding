#!/usr/bin/env python3
"""DEL-13 end-to-end: one fixture run through the packaging entry point.

The whole run, for real: package_run discovers each package item's component
(the DEL unit that produces it), writes the 12 canonical numbered files into
one delivery folder, and the test then opens every one of them -- PDF header,
SRT cue structure, media non-empty -- exactly as the client would.

This test is deliberately NOT stubbed. When a sibling unit DEL-01..DEL-12 is
not in the branch base, its component is not wired, the packaging call raises
COMPONENT_MISSING and this test SKIPS with the full list of items still owed
-- the honest state of a delivery folder that cannot be built yet, never a
fabricated green. A producer that raises (COMPONENT_FAILED) or a folder that
does not verify (PACKAGE_INCOMPLETE) still FAILS here: only the not-yet-landed
sibling is skippable. Re-run it once the sibling PRs merge; nothing here needs
editing. The twelve-item gate itself stays hard meanwhile: delivery_checklist
Q12 PACKAGE_COMPLETE fails the run on any missing package item.

Run: python3 delivery_package/test_delivery_package_e2e.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parents[0]                       # .../scripts/core
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

import delivery_package.contract as C           # noqa: E402
import delivery_package.packaging as P          # noqa: E402


class DeliveryPackageEndToEnd(unittest.TestCase):
    """One fixture run -> packaging entry point -> 12 files that open."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="del13-e2e-"))
        cls.run_dir = cls.tmp / "run"
        cls.run_dir.mkdir()
        cls.out = cls.tmp / "delivery"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_01_fixture_run_packages_all_twelve_items_and_they_open(self):
        # the packaging call itself: every component discovered, every item
        # written under its canonical numbered name, folder verified.
        try:
            res = P.package_run(self.run_dir, self.out)
        except P.PackageError as exc:
            if exc.code == "COMPONENT_MISSING":
                # Sibling DEL-01..DEL-12 producers are not in this branch's
                # base yet. Stated, never green: the discovery path is
                # SKIPPED until they land, and the reason carries the full
                # list of items still owed. The twelve-item gate itself stays
                # hard meanwhile -- delivery_checklist Q12 PACKAGE_COMPLETE
                # fails the run on any missing item, and the contract suite
                # (including test_full_packaging_path_writes_a_verifying_folder)
                # still fail-closes on the same folder contract.
                self.skipTest(
                    "sibling delivery units still open -- %s. Re-run this "
                    "test after the sibling PRs merge; Q12 PACKAGE_COMPLETE "
                    "and the delivery_package contract tests stay hard."
                    % exc.message)
            self.fail(
                "packaging refused this run -- %s\n%s"
                % (exc.code, exc.message))

        self.assertEqual(len(res["items"]), 12)
        report = C.verify_folder(self.out)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["missing"], [])

        # every one of the 12 package items exists AND opens
        for item in C.PACKAGE_ITEMS:
            for name, kind in zip(item.files, item.kinds):
                path = self.out / name
                with self.subTest(item=item.key, file=name, kind=kind):
                    self.assertTrue(path.exists(), "%s missing" % name)
                    self._opens(path, kind)

    def _opens(self, path, kind):
        """Open one delivered file the way the contract defines 'opens'."""
        if kind.startswith("images"):
            self.assertTrue(path.is_dir(), "%s is not a directory" % path.name)
            images = [p for p in path.rglob("*")
                      if p.is_file()
                      and p.suffix.lower() in C.IMAGE_SUFFIXES]
            self.assertGreaterEqual(len(images), C.MIN_IMAGES, path.name)
            for image in images:
                self.assertGreater(image.stat().st_size, 0, image.name)
            return
        self.assertTrue(path.is_file(), "%s is not a file" % path.name)
        self.assertGreater(path.stat().st_size, 0, "%s is empty" % path.name)
        if kind == "pdf":
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(5), b"%PDF-",
                                 "%s has no PDF header" % path.name)
        elif kind == "srt":
            text = path.read_text(encoding="utf-8")
            self.assertRegex(
                text, r"\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}",
                "%s has no cue timing line" % path.name)
            self.assertRegex(text, r"(?m)^\d+\s*$",
                             "%s has no cue index line" % path.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
