"""Negative fixture runner for Skill 81 (fixture gap lane, 2026-10-16).

The 20:10 fixture gap hunt (rooms/S81/lane-fixture-gap-2010.md) found
that the package carried no standalone negative fixtures: every defect
sentence the review chain recorded lived only as an inline string in a
test method. This file runs the standalone negative fixtures now in
fixtures/. Each one is a validly structured D1 page, result extension,
offer pair, or disclosure pair that violates exactly one named rule,
built with the exact probe construction its governing review used, and
carries its expected violation codes in its own expected_violations
field. The assertion is exact equality, not containment: a fixture
that starts failing with extra codes, or stops failing, fails here.

The three positive fixtures are re-run as controls so this file also
proves the negative set did not disturb them. An inventory test fails
if any invalid-*.json fixture exists that this runner does not cover,
so a future fixture cannot be added without a verdict here.

The escaping examples that are NOT in the negative set, and why, are
mapped in rooms/S81/negative-fixture-disposition.md: the caught ones
share a code with a fixture here and are pinned as test strings in the
cure test files; the D-3, D-8, and N-2 residual families are the
owner-accepted limitation under ruling S81-DEC-LEXRES-01 and are not
expected to be rejected.
Run: python3 -m unittest discover -s tests -v
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validators"))
import validate_downsell as vd  # noqa: E402

FX = ROOT / "fixtures"
CANON_U2 = "TEST-UPSELL_2"

# filename -> surface: which validator entry point judges the fixture.
NEGATIVE_FIXTURES = {
    "invalid-downsell-page-fake-scarcity.json": "page",
    "invalid-downsell-page-private-label.json": "page",
    "invalid-downsell-page-loss-of-purchase.json": "page",
    "invalid-downsell-page-decline-is-purchase.json": "page",
    "invalid-downsell-page-example-price-leak.json": "page",
    "invalid-downsell-result-decline-is-purchase.json": "result",
    "invalid-downsell-result-trial-disclosure.json": "result",
    "invalid-downsell-offer-identical-promise.json": "offer",
    "invalid-downsell-disclosure-missing-cancellation.json": "disclosure",
}


def load(name):
    return json.loads((FX / name).read_text())


def verdict(name, surface, fx):
    if surface == "page":
        return vd.validate_copy(fx["page"])
    if surface == "result":
        return vd.validate_result_extension(
            fx["downsell_result_extension"], CANON_U2)
    if surface == "offer":
        return vd.validate_offer_difference(fx["u1"], fx["d1"])
    if surface == "disclosure":
        return vd.validate_trial_disclosure(fx["d1"], fx["disclosure"])
    raise AssertionError(f"unknown surface {surface}")


class NegativeFixtureTests(unittest.TestCase):
    def check(self, name):
        fx = load(name)
        self.assertIs(fx.get("test_only"), True)
        expected = fx.get("expected_violations")
        self.assertTrue(expected, f"{name} names no expected violations")
        actual = verdict(name, NEGATIVE_FIXTURES[name], fx)
        self.assertEqual(actual, expected,
                         f"{name}: expected exactly {expected}, got {actual}")

    def test_fake_scarcity_page_rejected(self):
        self.check("invalid-downsell-page-fake-scarcity.json")

    def test_private_label_page_rejected(self):
        self.check("invalid-downsell-page-private-label.json")

    def test_loss_of_purchase_page_rejected(self):
        self.check("invalid-downsell-page-loss-of-purchase.json")

    def test_page_decline_is_purchase_rejected(self):
        self.check("invalid-downsell-page-decline-is-purchase.json")

    def test_example_price_leak_page_rejected(self):
        self.check("invalid-downsell-page-example-price-leak.json")

    def test_result_decline_is_purchase_rejected(self):
        self.check("invalid-downsell-result-decline-is-purchase.json")

    def test_result_trial_disclosure_rejected(self):
        self.check("invalid-downsell-result-trial-disclosure.json")

    def test_identical_promise_offer_rejected(self):
        self.check("invalid-downsell-offer-identical-promise.json")

    def test_disclosure_missing_cancellation_rejected(self):
        self.check("invalid-downsell-disclosure-missing-cancellation.json")

    def test_every_negative_fixture_file_is_covered(self):
        on_disk = {p.name for p in FX.glob("invalid-*.json")}
        self.assertEqual(on_disk, set(NEGATIVE_FIXTURES))


class PositiveFixtureControlTests(unittest.TestCase):
    def test_valid_page_fixture_clean(self):
        self.assertEqual(vd.validate_copy(load("valid-downsell-page.json")["page"]), [])

    def test_valid_result_fixture_clean(self):
        ext = load("valid-downsell-result.json")["downsell_result_extension"]
        self.assertEqual(vd.validate_result_extension(ext, CANON_U2), [])

    def test_valid_trial_matched_result_fixture_clean(self):
        ext = load("valid-downsell-result-trial-matched.json")["downsell_result_extension"]
        self.assertEqual(vd.validate_result_extension(ext, CANON_U2), [])


if __name__ == "__main__":
    unittest.main()
