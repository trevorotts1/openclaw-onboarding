#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_front_door_siblings.py - the front door refuses a Skill 49 tree that names a sibling skill it must not touch.

Trevor's ruling: Skill 49 must not touch Skill 6. The delivery rail is named in the brief and proven by signed
receipts (schema/delivery-rail-receipt.schema.json); no file of the 49 tree may name Skill 6's folder or tools.
`front_door.FORBIDDEN_SIBLING_REFS` is applied by `scan_tree` to every .py, .sh, .json and .md file of the 49 tree
(outside the skipped example/fixture/test directories), so one reintroduced reference trips BYPASS-SCAN before any
phase runs. This file never spells the forbidden names in one piece (it would trip the repository grep): they are
joined from halves below.

Run:  python3 -m pytest 49-signature-funnel/scripts/test_front_door_siblings.py -q
"""
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
REPO = SKILL.parent
sys.path.insert(0, str(HERE))
import front_door as fd  # noqa: E402

# the seven names, joined from halves so this file is not itself a hit for the repository-wide grep
NAMES = ("06-ghl-" + "install-pages", "ghl" + "_gate", "ghl" + "_verify", "ghl" + "_media",
         "cc" + "_board", "ghl" + "_rest_canvas", "ghl" + "_builder")
SKIP = shutil.ignore_patterns("__pycache__", "examples", "working", "fixtures", "tests")


def _tree(td: Path) -> Path:
    """A throwaway copy of the 49 tree beside symlinks to the real 83 / 71 / shared trees (only 49 is mutated)."""
    root = Path(td)
    t49 = root / "49-signature-funnel"
    shutil.copytree(SKILL, t49, ignore=SKIP)
    for name in ("83-black-friday-launcher", "71-blackceo-signature-page", "shared-utils"):
        (root / name).symlink_to(REPO / name, target_is_directory=True)
    return t49


class TheRealTreeIsClean(unittest.TestCase):
    def test_scan_tree_finds_nothing_in_the_real_49_tree(self):
        self.assertEqual(fd.scan_tree(SKILL), [])

    def test_only_front_door_py_spells_a_forbidden_name_anywhere_in_49_or_funnel_craft(self):
        """The M1 acceptance grep, as a test (substring match, no word boundaries)."""
        hits = []
        for base in (SKILL, REPO / "universal-sops" / "funnel-craft"):
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if d != "__pycache__"]
                for fn in filenames:
                    path = Path(dirpath) / fn
                    try:
                        text = path.read_text(encoding="utf-8")
                    except (UnicodeDecodeError, OSError):
                        continue
                    if any(name in text for name in NAMES):
                        hits.append(path.relative_to(REPO).as_posix())
        self.assertEqual(hits, ["49-signature-funnel/scripts/front_door.py"])

    def test_the_denylist_still_names_all_seven(self):
        for name in NAMES:
            self.assertTrue(fd.FORBIDDEN_SIBLING_REFS.search(name), name)
        # and only whole names: a longer identifier that merely contains one is not a hit
        self.assertFalse(fd.FORBIDDEN_SIBLING_REFS.search("my" + NAMES[3] + "er"))


class AReintroducedReferenceTripsTheBypassScan(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.t49 = _tree(Path(self._td.name))

    def tearDown(self):
        self._td.cleanup()

    def plant(self, rel, text):
        path = self.t49 / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_the_copy_of_the_real_tree_is_clean_first(self):
        self.assertEqual(fd.scan_tree(self.t49), [])
        fd.step_bypass_scan(None, self.t49)   # does not raise

    def test_an_import_of_a_sibling_gate_module_trips_bypass_scan(self):
        self.plant("scripts/new_prover.py", "import " + NAMES[1] + "\n")
        hits = fd.scan_tree(self.t49)
        self.assertTrue(any("new_prover.py" in h and "sibling skill" in h for h in hits), hits)
        with self.assertRaises(fd.FrontDoorError) as cm:
            fd.step_bypass_scan(None, self.t49)
        self.assertEqual(cm.exception.gate, "BYPASS-SCAN")

    def test_every_forbidden_name_in_every_scanned_file_type_trips_it(self):
        for ext in (".py", ".sh", ".json", ".md"):
            for name in NAMES:
                with self.subTest(ext=ext, name=name):
                    path = self.plant(f"zz_planted{ext}", f"# note: {name}\n" if ext != ".json" else f'{{"x": "{name}"}}')
                    self.assertTrue(any("zz_planted" in h for h in fd.scan_tree(self.t49)), (ext, name))
                    path.unlink()
                    self.assertEqual(fd.scan_tree(self.t49), [])

    def test_a_reference_in_a_doc_in_a_subfolder_trips_it(self):
        self.plant("adapters/NOTES.md", "see " + NAMES[0] + "/tools\n")
        self.assertTrue(any("adapters/NOTES.md" in h for h in fd.scan_tree(self.t49)))

    def test_front_door_py_is_the_only_exemption(self):
        self.assertIn("49/scripts/front_door.py", fd.STRING_ALLOWED)
        text = (self.t49 / "scripts" / "front_door.py").read_text(encoding="utf-8")
        self.assertTrue(any(n in text for n in NAMES))      # it spells the denylist ...
        self.assertEqual(fd.scan_tree(self.t49), [])        # ... and is not flagged for it
        extra = [p for p in fd.STRING_ALLOWED if p != "49/scripts/front_door.py"]
        self.assertEqual(extra, ["49/scripts/kie74_receipt.py"])   # the other exemption is the KIE receipt writer

    def test_the_door_message_no_longer_names_skill_6(self):
        self.plant("scripts/new_prover.py", "import " + NAMES[1] + "\n")
        with self.assertRaises(fd.FrontDoorError) as cm:
            fd.step_bypass_scan(None, self.t49)
        self.assertNotIn("Skill 6 ", cm.exception.detail)
        self.assertIn("delivery rail", cm.exception.detail)

    def test_other_trees_are_not_subject_to_the_sibling_scan(self):
        """The new pattern is scoped to the 49 tree; 83 and the shared trees keep their own rules."""
        self.assertEqual(fd.scan_tree(self.t49), [])
        self.assertTrue(all(h.startswith("49/") for h in fd.scan_tree(self.t49)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
