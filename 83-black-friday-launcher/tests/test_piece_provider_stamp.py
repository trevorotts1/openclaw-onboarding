"""Issue 16: every written piece names the provider that drew its pictures.

The package check refuses a client delivery whose design files name no provider (a placeholder cannot be
told from a real render). A page-result 1.0 carries no provider field, so launch_bridge records the run's
approved image provider on each piece; an artifact that names its own provider keeps it.

Run: python3 -m unittest tests.test_piece_provider_stamp   (from the skill folder)
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))

from launcher_core import launch_bridge  # noqa: E402


class PieceProviderStampTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def piece(self, slot, **extra):
        (self.dir / f"{slot}.json").write_text(json.dumps({"page_id": slot, "artifacts": [], **extra}))

    def read(self, slot):
        return json.loads((self.dir / f"{slot}.json").read_text())

    def test_a_piece_with_no_provider_gets_the_run_provider(self):
        self.piece("upsell_1")
        self.piece("downsell_1")
        launch_bridge._stamp_image_provider(self.dir, ["upsell_1", "downsell_1"], "kie")
        self.assertEqual(self.read("upsell_1")["image_provider"], "kie")
        self.assertEqual(self.read("downsell_1")["image_provider"], "kie")

    def test_a_piece_that_names_its_own_provider_keeps_it(self):
        self.piece("landing", image_provider="stub")
        launch_bridge._stamp_image_provider(self.dir, ["landing"], "kie")
        self.assertEqual(self.read("landing")["image_provider"], "stub")

    def test_a_blank_or_non_string_provider_is_no_provider(self):
        self.piece("a", image_provider="   ")
        self.piece("b", image_provider="")
        self.piece("c", image_provider=7)
        launch_bridge._stamp_image_provider(self.dir, ["a", "b", "c"], "kie")
        self.assertEqual([self.read(x)["image_provider"] for x in "abc"], ["kie", "kie", "kie"])

    def test_only_the_named_slots_are_touched(self):
        self.piece("upsell_1")
        self.piece("thank_you")
        launch_bridge._stamp_image_provider(self.dir, ["upsell_1"], "stub")
        self.assertNotIn("image_provider", self.read("thank_you"))


if __name__ == "__main__":
    unittest.main()
