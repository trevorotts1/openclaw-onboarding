"""Static checks for the S79 component drafts (S79-03/S79-05/S79-09 fixture
level): no homemade payment fields anywhere, bump and consent start
unchecked, native slot present, accessibility hooks present. L1 only;
rendered proof is L2 and still owed."""
import re
import unittest
from pathlib import Path

COMPONENTS = Path(__file__).resolve().parents[1] / "references" / "components"
REPO = Path(__file__).resolve().parents[2]
SKILL = COMPONENTS.parents[1]
# Every html/css draft is review-only (CHK-18/CHK-24); globbed so new drafts are covered.
REVIEW_ONLY_DRAFTS = tuple(sorted(p.name for p in COMPONENTS.glob("*.html"))) + ("components.css",)
# Docs scanned for stale strings and unresolvable paths. checkout.schema.json is
# excluded: its title belongs to U-checkout-commerce-06 (carried).
DOC_FILES = ([SKILL / "SKILL.md"] + sorted((SKILL / "references").glob("*.md"))
             + sorted(p for p in COMPONENTS.iterdir() if p.is_file()))


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

    def test_every_draft_carries_review_only_marker(self):
        for name in REVIEW_ONLY_DRAFTS + ("README.md",):
            self.assertIn("REVIEW-ONLY", read(name), name)

    def test_no_stale_work_paths_or_draft_title(self):
        for path in DOC_FILES:
            text = path.read_text()
            for needle in ("work/", "DRAFT v0.1", "0.1.5"):
                self.assertNotIn(needle, text, f"{path.name}: {needle}")
        for name in ("combined-checkout.html", "post-selection-checkout.html"):
            title = re.search(r"<title>(.*?)</title>", read(name)).group(1)
            self.assertNotIn("TEST", title, name)

    def test_paths_named_in_docs_resolve(self):
        # Backticked tokens shaped like dir/file.ext must exist under the 79
        # root or the repo root. The schema id skill6-environment-capabilities/1
        # has no extension and is not a path.
        for path in DOC_FILES:
            for rel in re.findall(r"`([^`\s]+/[^`\s]+\.(?:py|md|json|html|css))`", path.read_text()):
                self.assertTrue((SKILL / rel).exists() or (REPO / rel).exists(),
                                f"{path.name}: {rel}")

    def test_skill_md_marks_components_review_only(self):
        self.assertIn("REVIEW-ONLY", (SKILL / "SKILL.md").read_text())

    def test_shared_utils_bump_copy_is_deprecated_and_points_to_79(self):
        copy = REPO / "shared-utils" / "signature_launch" / "components" / "order-bump" / "order-bump.html"
        head = copy.read_text()[:600]
        self.assertIn("DEPRECATED", head)
        self.assertIn("79-signature-order-form/references/components/order-bump.html", head)
        self.assertTrue((REPO / "79-signature-order-form/references/components/order-bump.html").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
