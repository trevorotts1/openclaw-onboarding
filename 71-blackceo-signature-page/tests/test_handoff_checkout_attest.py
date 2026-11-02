"""CHK-28: a sales page's checkout is tied to the approved price.

A client-built checkout URL passes the handoff validator only with an
attestation (url, attested_by, product, price read-back) matching the approved
price; once a checkout_result exists the CTA must equal its read-back URL.
Synthetic fixtures only; no network, no browser.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATE = ROOT / "scripts" / "validate_handoff.py"

URL = "https://pay.example.com/checkout/elevate"
OLD = "https://pay.example.com/old-27-form"
PAGE = ('<!doctype html><html><body><a class="cta" href="%s">Claim Your Seat'
        '</a></body></html>')
APPROVED = {"amount": "97", "currency": "USD"}
ATTEST = {"url": URL, "attested_by": "client", "product": "Elevate",
          "price": {"amount": 97.00, "currency": "usd"}}
MISSING = {"status": "missing_input", "missing": "form_identity",
           "reason": "client checkout not sent yet",
           "behavior": "form_pop",
           "step_order": ["signature_page", "product_selection_page",
                          "order_form_page"],
           "approved_price": APPROVED}


def run_dir(td, handoff, href=URL):
    run = Path(td) / "run"
    (run / "copy").mkdir(parents=True)
    (run / "responsive-html").mkdir()
    (run / "intake.json").write_text(json.dumps(
        {"page_kind": "sales", "funnel_handoff": handoff}))
    (run / "copy" / "copy-manifest.json").write_text(json.dumps({"ctas": [
        {"label": "Claim Your Seat", "handoff_type": "external_link",
         "primary": True}]}))
    (run / "responsive-html" / "index.html").write_text(PAGE % href)
    return run


class CheckoutAttestTest(unittest.TestCase):
    def check(self, handoff, href=URL):
        with tempfile.TemporaryDirectory() as td:
            proc = subprocess.run(
                [sys.executable, str(VALIDATE), str(run_dir(td, handoff, href))],
                text=True, capture_output=True)
        return proc.returncode, proc.stdout

    def refused(self, handoff, text, href=URL):
        code, out = self.check(handoff, href)
        self.assertEqual(code, 1, out)
        self.assertIn(text, out)

    # --- row 1: client-built checkout needs the attested read-back ----------
    def test_arbitrary_client_url_without_attestation_is_refused(self):
        self.refused({"checkout_url": URL, "approved_price": APPROVED},
                     "no checkout_result and no checkout_attestation")

    def test_matching_attestation_passes(self):
        code, out = self.check({"checkout_url": URL, "approved_price": APPROVED,
                                "checkout_attestation": ATTEST})
        self.assertEqual(code, 0, out)
        self.assertIn("attested product/price read-back", out)

    def test_old_27_form_against_97_launch_is_refused(self):
        att = dict(ATTEST, price={"amount": "27", "currency": "USD"})
        self.refused({"approved_price": APPROVED, "checkout_attestation": att},
                     "does not match the approved price")

    def test_attestation_for_another_url_is_refused(self):
        att = dict(ATTEST, url=OLD)
        self.refused({"approved_price": APPROVED, "checkout_attestation": att},
                     "is not the CTA destination")

    def test_attestation_needs_attester_product_and_approved_price(self):
        att = {k: v for k, v in ATTEST.items()
               if k not in ("attested_by", "product")}
        self.refused({"approved_price": APPROVED, "checkout_attestation": att},
                     "no attested_by")
        self.refused({"checkout_attestation": ATTEST},
                     "no approved_price")

    def test_bump_read_back_must_match_the_approved_bump(self):
        approved = dict(APPROVED, bump={"amount": "37", "currency": "USD"})
        self.refused({"approved_price": approved,
                      "checkout_attestation": ATTEST},
                     "bump read-back")
        att = dict(ATTEST, bump={"amount": "37", "currency": "USD"})
        code, out = self.check({"approved_price": approved,
                                "checkout_attestation": att})
        self.assertEqual(code, 0, out)

    # --- rows 2 and 3: a checkout_result's native page URL wins -------------
    def test_cta_must_equal_the_checkout_result_url(self):
        result = {"read_back_url": URL}
        self.refused({"checkout_result": result}, "native page URL", href=OLD)
        code, out = self.check({"checkout_result": result})
        self.assertEqual(code, 0, out)
        self.assertIn("checkout_result's native page URL", out)

    def test_attestation_does_not_replace_the_checkout_result(self):
        self.refused({"checkout_result": {"native_page_url": URL},
                      "approved_price": APPROVED,
                      "checkout_attestation": dict(ATTEST, url=OLD)},
                     "native page URL", href=OLD)

    def test_checkout_result_without_a_url_is_refused(self):
        self.refused({"checkout_result": {"status": "installed"}},
                     "no read_back_url or native_page_url")

    def test_missing_input_flag_carries_only_a_placeholder(self):
        # QC2-D1: the old $27 form under the skill's own missing-input flag.
        self.refused(MISSING, "no checkout_result and no checkout_attestation",
                     href=OLD)
        code, out = self.check(MISSING, href="#checkout")
        self.assertEqual(code, 0, out)
        self.assertIn("recorded missing input", out)
        code, out = self.check(dict(MISSING, checkout_attestation=ATTEST))
        self.assertEqual(code, 0, out)
        self.assertIn("attested product/price read-back", out)


if __name__ == "__main__":
    unittest.main()
