"""Static checks for the S79 component drafts (S79-03/S79-05/S79-09 fixture
level): no homemade payment fields anywhere, bump and consent start
unchecked, native slot present, accessibility hooks present. L1 only;
rendered proof is L2 and still owed."""
import re
import unittest
from pathlib import Path

COMPONENTS = Path(__file__).resolve().parents[1] / "references" / "components"


def read(name):
    return (COMPONENTS / name).read_text()


class ComponentStaticTests(unittest.TestCase):
    def test_no_homemade_payment_fields_anywhere(self):
        # The rule bans homemade payment FIELD constructs (inputs named or
        # autocompleted as card data). Prose that prohibits such fields,
        # including the word CVC in a warning comment, is not a field.
        field_patterns = (r'<input[^>]+(card|cvc|cvv|cc-)', r'name="(card|cvc|cvv)',
                          r'id="(card|cvc|cvv)', r'autocomplete="cc-')
        for path in COMPONENTS.glob("*.html"):
            text = path.read_text().lower()
            for pattern in field_patterns:
                self.assertIsNone(re.search(pattern, text),
                                  f"{path.name} matches field pattern {pattern}")

    def test_bump_checkbox_starts_unchecked(self):
        bump = read("order-bump.html")
        offered = bump.split('data-state="offered_unchecked"')[1].split("</section>")[0]
        self.assertIn('type="checkbox"', offered)
        self.assertNotIn("checked", offered)

    def test_suppressed_and_unavailable_states_have_no_checkbox(self):
        bump = read("order-bump.html")
        for state in ("suppressed_included", "suppressed_previously_purchased",
                      "disabled_unavailable"):
            section = bump.split(f'data-state="{state}"')[1].split("</section>")[0]
            self.assertNotIn('type="checkbox"', section, state)
            self.assertNotIn('type="radio"', section, state)

    def test_consent_starts_unchecked(self):
        terms = read("guarantee-terms.html")
        self.assertIn('name="consent"', terms)
        self.assertNotIn("checked", terms)

    def test_both_modes_have_native_slot_and_status_region(self):
        for name in ("combined-checkout.html", "post-selection-checkout.html"):
            text = read(name)
            self.assertIn('data-native-slot="checkout-form"', text, name)
            self.assertIn('aria-live="polite"', text, name)
            self.assertIn('name="viewport"', text, name)

    def test_post_selection_has_change_package_and_recovery(self):
        text = read("post-selection-checkout.html")
        self.assertIn("Change package", text)
        self.assertIn('data-state="recovery"', text)
        self.assertIn('data-state="reconfirm"', text)
        self.assertIn("not substituted a different package", text)

    def test_css_has_focus_visible_and_mobile_rules(self):
        css = read("components.css")
        self.assertIn(".sig-checkout :focus-visible", css)
        self.assertIn("@media (max-width: 640px)", css)
        self.assertRegex(css, r"--sig-color-")

    def test_selection_summary_confirms_billing_schedule(self):
        self.assertIn("Billing schedule:", read("post-selection-checkout.html"))

    def test_combined_explanation_has_all_four_slots(self):
        text = read("combined-checkout.html")
        for slot in ("What is included", "Who this is for", "Access and delivery",
                     "Important exclusions"):
            self.assertIn(slot, text)

    def test_status_component_states(self):
        text = read("checkout-status.html")
        for state in ("pending", "failed", "requires_action", "paid"):
            self.assertIn(f'data-state="{state}"', text)
        failed = text.split('data-state="failed"')[1].split("</section>")[0]
        self.assertIn("not been charged", failed)
        self.assertIn("never charged twice", text)
        # No onward paid-route link may exist in any non-paid state block.
        for state in ("pending", "failed", "requires_action"):
            block = text.split(f'data-state="{state}"')[1].split("</section>")[0]
            self.assertNotIn("<a ", block, state)

    def test_no_em_dashes_in_component_copy(self):
        for path in list(COMPONENTS.glob("*.html")) + [COMPONENTS / "README.md"]:
            self.assertNotIn("—", path.read_text(), path.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
