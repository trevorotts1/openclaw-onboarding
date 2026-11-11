"""INT-T-6: validate_copy_request is validate_request minus the three Skill 06 read-back keys, nothing else.

The copy emitter (WP-09b) calls it so a request built from the intake alone (Skill 83 launch_bridge, which
cannot know the read-back facts) can become copy. The production gate validate_request keeps requiring them.
"""
import copy
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "scripts"))
sys.path.insert(0, str(HERE.parent))

import validate_checkout  # noqa: E402
from validate_checkout import (CheckoutValidationError, READBACK_FACTS, validate_copy_request,  # noqa: E402
                               validate_request)
from test_validate_checkout_production import BASE, NOW  # noqa: E402


def without_readback():
    request = copy.deepcopy(BASE)
    for key in READBACK_FACTS:
        request.pop(key)
    return request


class CopyRequest(unittest.TestCase):
    def test_the_readback_keys_are_exactly_the_three_skill_06_facts(self):
        self.assertEqual(set(READBACK_FACTS), {
            "native_capability_evidence_ref", "fulfillment_mapping_ref", "failed_pending_requirements"})

    def test_a_missing_readback_passes_copy_but_fails_the_production_gate(self):
        request = without_readback()
        validate_copy_request(request, now=NOW)
        for key in READBACK_FACTS:
            only = copy.deepcopy(BASE)
            only.pop(key)
            validate_copy_request(only, now=NOW)
            with self.assertRaises(CheckoutValidationError, msg=key):
                validate_request(only, now=NOW)
        with self.assertRaises(CheckoutValidationError):
            validate_request(request, now=NOW)

    def test_a_full_request_passes_both(self):
        validate_copy_request(copy.deepcopy(BASE), now=NOW)
        validate_request(copy.deepcopy(BASE), now=NOW)

    def test_an_unapproved_price_is_still_refused(self):
        request = without_readback()
        request["main_price"]["approval_status"] = "recommended_unapproved"
        with self.assertRaises(CheckoutValidationError):
            validate_copy_request(request, now=NOW)

    def test_a_test_only_request_is_still_refused_where_the_gate_refuses_it(self):
        request = without_readback()
        request["main_price"]["approval_status"] = "test_only"
        with self.assertRaises(CheckoutValidationError):
            validate_copy_request(request, now=NOW)

    def test_every_other_required_key_is_still_required(self):
        for key in ("tenant_id", "main_price", "terms_ref", "consent_ref", "brand_ref"):
            request = without_readback()
            request.pop(key)
            with self.assertRaises(CheckoutValidationError, msg=key):
                validate_copy_request(request, now=NOW)

    def test_a_readback_key_that_is_present_is_still_validated(self):
        request = without_readback()
        request["native_capability_evidence_ref"] = 17
        with self.assertRaises(CheckoutValidationError):
            validate_copy_request(request, now=NOW)

    def test_an_expired_mapping_is_still_refused(self):
        request = without_readback()
        request["main_price"]["price_mapping_expires_at"] = "2000-01-01T00:00:00Z"
        with self.assertRaises(CheckoutValidationError):
            validate_copy_request(request, now=NOW)

    def test_the_schema_file_itself_is_not_loosened(self):
        required = validate_checkout._schema()["$defs"]["checkout_request"]["required"]
        for key in READBACK_FACTS:
            self.assertIn(key, required)


if __name__ == "__main__":
    unittest.main(verbosity=2)
