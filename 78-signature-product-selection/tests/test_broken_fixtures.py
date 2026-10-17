import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from selection_core import Violation, build_selection, check_invocation, validate_catalog  # noqa: E402

BROKEN = ROOT / "fixtures" / "broken"


class BrokenFixtureTests(unittest.TestCase):
    """On-disk broken fixtures (S78 hardening): every negative case that
    used to live only inside script self-tests now ships as an inspectable
    file with its expected outcome pinned. Adding a fixture file without
    updating its expectation fails here, and weakening an expectation
    shows up as a diff in this test."""

    def _cases(self):
        files = sorted(BROKEN.glob("*.json"))
        self.assertGreaterEqual(len(files), 10, "broken fixture set shrank")
        return [(f.name, json.loads(f.read_text())) for f in files]

    def test_every_broken_fixture_behaves_as_pinned(self):
        for name, doc in self._cases():
            with self.subTest(fixture=name):
                launch = doc["launch"]
                expect = doc["expect"]
                if expect.get("decline_single_offer"):
                    self.assertEqual(check_invocation(launch), "decline_single_offer")
                    continue
                code = expect["violation_code"]
                if doc["via"] == "selection":
                    offer = launch["offers"][0]
                    with self.assertRaises(Violation) as ctx:
                        build_selection(
                            launch, offer_id=offer["offer_id"],
                            price_choice_id=offer["prices"][0]["price_choice_id"],
                            selected_at="2026-10-15T20:00:00Z",
                            source_page_id="TEST", session_ref="opaque",
                        )
                    self.assertEqual(ctx.exception.code, code)
                else:
                    with self.assertRaises(Violation) as ctx:
                        validate_catalog(launch)
                    self.assertEqual(ctx.exception.code, code)


if __name__ == "__main__":
    unittest.main()
