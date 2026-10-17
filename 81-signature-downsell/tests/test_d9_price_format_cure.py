"""D-9 cure tests: example price formats restored by the price-scan fix.

The independent re-review of the v0.3 validator found defect D-9 PARTIAL
with a regression: the digit pattern's negative lookahead excluded a
following dot, so the exact example amount in cents form ("$27.00"),
which lane 5 had verified as caught before the fix, passed clean. Two
sibling escapes in the same family also passed: the suffixed cents form
("27.00 USD") and the hyphenated form ("27-dollar").

These tests pin, for every example amount the scan covers (1, 27, and
997 dollars, not only 27):
- each cured format is rejected with D1-COPY-EXAMPLE-PRICE-LEAK,
- each lane 5 verified format stays rejected,
- genuinely different amounts ("$279", "$27.50") stay unflagged, so the
  lookahead's intended protection is preserved,
- an approved amount in cents form stays unflagged, and both valid
  fixtures still validate clean.
Nothing here edits or weakens any pre-existing test.
Run: python3 -m unittest discover -s tests -v
"""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validators"))
import validate_downsell as vd  # noqa: E402

PAGE = json.loads((ROOT / "fixtures" / "valid-downsell-page.json").read_text())["page"]
EXT = json.loads(
    (ROOT / "fixtures" / "valid-downsell-result.json").read_text()
)["downsell_result_extension"]
LEAK = "D1-COPY-EXAMPLE-PRICE-LEAK"


def scrubbed_page():
    """Valid page with every example amount scrubbed and none approved, so
    a price-leak verdict can only come from the text a test adds. Same
    construction as the defect-fix test file."""
    p = copy.deepcopy(PAGE)
    p["approved_amounts_minor"] = []
    for s in p["sections"]:
        s["body"] = s["body"].replace("$1", "").replace("$27", "")
        s["cta"]["label"] = s["cta"]["label"].replace("$1", "")
    return p


def with_cta(label):
    p = scrubbed_page()
    p["sections"][0]["cta"]["label"] = label
    return p


def with_body(text):
    p = scrubbed_page()
    p["sections"][0]["body"] += " " + text
    return p


class D9CuredFormatTests(unittest.TestCase):
    """The three escaping formats from the re-review, per example amount."""

    def test_d9_cents_form_dollar_sign_caught(self):
        self.assertIn(LEAK, vd.validate_copy(with_cta("Join for $27.00 now")))

    def test_d9_suffixed_cents_form_caught(self):
        self.assertIn(LEAK, vd.validate_copy(with_body("Pay 27.00 USD monthly.")))

    def test_d9_hyphenated_form_caught(self):
        self.assertIn(LEAK, vd.validate_copy(
            with_body("A 27-dollar trial starts today.")))

    def test_d9_cents_form_one_dollar_caught(self):
        self.assertIn(LEAK, vd.validate_copy(with_cta("Join for $1.00 now")))

    def test_d9_suffixed_cents_form_one_dollar_caught(self):
        self.assertIn(LEAK, vd.validate_copy(with_body("Pay 1.00 USD monthly.")))

    def test_d9_hyphenated_form_one_dollar_caught(self):
        self.assertIn(LEAK, vd.validate_copy(
            with_body("A 1-dollar trial starts today.")))

    def test_d9_cents_form_997_caught(self):
        self.assertIn(LEAK, vd.validate_copy(with_cta("Join for $997.00 now")))

    def test_d9_suffixed_cents_form_997_caught(self):
        self.assertIn(LEAK, vd.validate_copy(with_body("Pay 997.00 USD monthly.")))

    def test_d9_hyphenated_form_997_caught(self):
        self.assertIn(LEAK, vd.validate_copy(
            with_body("A 997-dollar plan starts today.")))


class D9Lane5ControlFormatTests(unittest.TestCase):
    """Formats lane 5 verified as caught; the cure must not lose any."""

    def test_d9_words_form_stays_caught(self):
        self.assertIn(LEAK, vd.validate_copy(
            with_body("That is twenty-seven dollars a month.")))

    def test_d9_spaced_dollar_sign_stays_caught(self):
        self.assertIn(LEAK, vd.validate_copy(with_cta("Join for $ 27 now")))

    def test_d9_usd_suffix_stays_caught(self):
        self.assertIn(LEAK, vd.validate_copy(
            with_body("Yours for 27 USD monthly.")))

    def test_d9_plain_dollar_digits_stay_caught(self):
        self.assertIn(LEAK, vd.validate_copy(with_cta("Join for $27 now")))

    def test_d9_digit_dollar_word_stays_caught(self):
        self.assertIn(LEAK, vd.validate_copy(
            with_body("That is 27 dollars a month.")))

    def test_d9_one_dollar_words_stay_caught(self):
        self.assertIn(LEAK, vd.validate_copy(
            with_body("A one dollar trial starts today.")))

    def test_d9_997_dollar_form_stays_caught(self):
        self.assertIn(LEAK, vd.validate_copy(with_cta("Join for $997 now")))

    def test_d9_997_usd_form_stays_caught(self):
        self.assertIn(LEAK, vd.validate_copy(
            with_body("Yours for 997 USD monthly.")))


class D9UnflaggedControlTests(unittest.TestCase):
    """Genuinely different amounts keep the lookahead's protection."""

    def test_d9_scrubbed_control_page_still_clean(self):
        self.assertEqual(vd.validate_copy(scrubbed_page()), [])

    def test_d9_longer_amount_279_not_flagged(self):
        self.assertEqual(vd.validate_copy(with_cta("Join for $279 now")), [])

    def test_d9_nonzero_cents_2750_not_flagged(self):
        self.assertEqual(vd.validate_copy(with_cta("Join for $27.50 now")), [])

    def test_d9_usd_longer_amount_279_not_flagged(self):
        self.assertEqual(vd.validate_copy(
            with_body("Yours for 279 USD monthly.")), [])

    def test_d9_usd_nonzero_cents_not_flagged(self):
        self.assertEqual(vd.validate_copy(
            with_body("Pay 27.50 USD monthly.")), [])

    def test_d9_997_nonzero_cents_not_flagged(self):
        self.assertEqual(vd.validate_copy(with_cta("Join for $997.50 now")), [])

    def test_d9_approved_amount_in_cents_form_not_flagged(self):
        p = copy.deepcopy(PAGE)
        p["sections"][0]["cta"]["label"] = "Join for $27.00 now"
        self.assertEqual(vd.validate_copy(p), [])

    def test_d9_valid_page_fixture_still_clean(self):
        self.assertEqual(vd.validate_copy(copy.deepcopy(PAGE)), [])

    def test_d9_valid_result_fixture_still_clean(self):
        self.assertEqual(vd.validate_result_extension(copy.deepcopy(EXT)), [])


if __name__ == "__main__":
    unittest.main()
