"""S82-07 access validation tests.

Covers scripts/validate_access.py against the TEST ONLY fixtures:
the honest manifest passes; insecure destinations, identity/entitlement
claims in URLs, missing independent authorization, mailto-as-access,
and access for an entitlement that is not in the view all fail with
named codes. Claim keys are also tested in evasion forms (homoglyph,
double-encoded, null-byte — F-02), and benign parameter keys pass.
"""

import copy
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from validate_access import validate_access  # noqa: E402


def _load(name):
    with open(os.path.join(ROOT, "fixtures", name), encoding="utf-8") as fh:
        return json.load(fh)


def _codes(errors):
    return {e.split(":", 1)[0] for e in errors}


class ValidateAccessTests(unittest.TestCase):
    def setUp(self):
        self.view = _load("test-only-order-view.json")
        self.manifest = _load("test-only-links.json")

    def test_honest_manifest_passes(self):
        # Includes a mailto: support link, which is not an access block
        # and must not trip the https / authorization-flag rules.
        self.assertEqual(validate_access(self.view, self.manifest), [])

    def test_http_access_destination_fails(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["links"][0]["url"] = "http://example.test/access/base-a"
        errors = validate_access(self.view, manifest)
        self.assertIn("insecure_destination", _codes(errors))

    def test_email_claim_in_url_fails(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["links"][0]["url"] = (
            "https://example.test/access/base-a?email=buyer@example.test")
        errors = validate_access(self.view, manifest)
        self.assertIn("claim_in_url", _codes(errors))

    def test_vip_claim_in_url_fails(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["links"][1]["url"] = (
            "https://example.test/access/workbook?vip=true")
        errors = validate_access(self.view, manifest)
        self.assertIn("claim_in_url", _codes(errors))

    # --- F-02 regressions: claim keys must not evade by encoding -----

    def test_homoglyph_claim_key_in_url_fails(self):
        # "em" + CYRILLIC SMALL LETTER A (U+0430) + "il" reads as
        # "email" but is not the ASCII key; normalization folds it.
        homoglyph_key = "em" + chr(0x430) + "il"
        manifest = copy.deepcopy(self.manifest)
        manifest["links"][0]["url"] = (
            "https://example.test/access/base-a"
            f"?{homoglyph_key}=buyer@example.test")
        errors = validate_access(self.view, manifest)
        self.assertIn("claim_in_url", _codes(errors))

    def test_double_encoded_claim_key_in_url_fails(self):
        # %2565mail decodes once to "%65mail" and only a second decode
        # reveals "email"; the normalizer decodes repeatedly.
        manifest = copy.deepcopy(self.manifest)
        manifest["links"][0]["url"] = (
            "https://example.test/access/base-a"
            "?%2565mail=buyer@example.test")
        errors = validate_access(self.view, manifest)
        self.assertIn("claim_in_url", _codes(errors))

    def test_null_byte_claim_key_in_url_fails(self):
        # email%00 decodes to "email" + NUL; a downstream parser that
        # ignores the null byte would see the claim key.
        manifest = copy.deepcopy(self.manifest)
        manifest["links"][0]["url"] = (
            "https://example.test/access/base-a"
            "?email%00=buyer@example.test")
        errors = validate_access(self.view, manifest)
        self.assertIn("claim_in_url", _codes(errors))

    def test_benign_param_keys_pass(self):
        # Only key names on the claim list are claims. Benign keys —
        # and arbitrary parameter values, which are never inspected —
        # must not be flagged.
        manifest = copy.deepcopy(self.manifest)
        manifest["links"][0]["url"] = (
            "https://example.test/access/base-a"
            "?ref=receipt&page=2&lang=en&utm_source=email-footer")
        self.assertEqual(validate_access(self.view, manifest), [])

    def test_missing_independent_authorization_fails(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["links"][2]["destination_independently_authorizes"] = False
        errors = validate_access(self.view, manifest)
        self.assertIn("missing_independent_authorization", _codes(errors))

    def test_access_for_unviewed_entitlement_fails(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["links"].append({
            "entitlement_id": "premium-not-purchased",
            "kind": "access",
            "url": "https://example.test/access/premium-not-purchased",
            "destination_independently_authorizes": True,
        })
        errors = validate_access(self.view, manifest)
        self.assertIn("access_for_unviewed_entitlement", _codes(errors))

    def test_mailto_as_access_block_fails(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["links"].append({
            "entitlement_id": "base-a",
            "kind": "access",
            "url": "mailto:support@example.test",
            "destination_independently_authorizes": True,
        })
        errors = validate_access(self.view, manifest)
        self.assertIn("invalid_destination", _codes(errors))

    def test_cli_exit_codes(self):
        import subprocess
        script = os.path.join(ROOT, "scripts", "validate_access.py")
        view = os.path.join(ROOT, "fixtures", "test-only-order-view.json")
        links = os.path.join(ROOT, "fixtures", "test-only-links.json")
        ok = subprocess.run([sys.executable, script, "--view", view,
                             "--links", links],
                            capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertIn("PASS", ok.stdout)


if __name__ == "__main__":
    unittest.main()
