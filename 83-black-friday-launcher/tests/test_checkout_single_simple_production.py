"""Issue 13: a live single_simple launch supplies approval_status, so the top-level checkout probe can pass.

Before: `_price_choice` set approval_status only for a test_only launch, so a production single_simple intake
left it in `unknown`, the Skill 79 probe was rejected, and `AF-LAUNCH-CHECKOUT-INCOMPLETE` blocked delivery for a
launch whose price the client had stated. Now the canonical offer the intake resolved in the client's answers file
decides, by the rule checkout_instances uses.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "fixtures"))

from launcher_core import checkout, intake, route  # noqa: E402
from launcher_core.check_rules import checkout as rule  # noqa: E402
from test_checkout_mapping import READBACK, raw_intake  # noqa: E402


def live(mode="single_simple", bump=False):
    payload = raw_intake(mode, bump=bump)
    payload["test_only"] = False
    return intake.validate(payload)


# TEST-ONLY Skill 06 read-back for a live launch: the native ids a production request must carry (C5)
LIVE_READBACK = dict(READBACK, native={"main-1": {"native_product_id": "TEST-ONLY-PROD",
                                                  "native_price_id": "TEST-ONLY-PRICE", "currency_exponent": 2}})


def mapping_of(normalized, readback=LIVE_READBACK):
    return checkout.order_form_mapping(normalized, route.compile_route(normalized), readback=readback)


class SingleSimpleProductionTests(unittest.TestCase):
    def test_a_live_single_offer_supplies_approval_status_and_leaves_it_out_of_unknown(self):
        mapping = mapping_of(live())
        price = mapping["supplied"]["main_price"]
        self.assertEqual(price["approval_status"], "approved")  # the client's own price, not a defaulted one
        self.assertNotIn("approval_status", price.get("unknown", []))
        self.assertNotIn("main_price.approval_status", mapping["missing_facts"])

    def test_the_live_top_level_probe_passes_and_incomplete_is_not_raised(self):
        mapping = mapping_of(live())
        self.assertEqual(mapping["validator"]["probe"], {"result": "accepted"}, mapping["missing_facts"])
        manifest = {"test_only": False, "checkout": mapping}
        self.assertEqual(rule.incomplete_violations(manifest, mapping), [])

    def test_a_live_bump_price_carries_its_status_too(self):
        mapping = mapping_of(live(bump=True))
        self.assertEqual(mapping["supplied"]["bump"]["price"]["approval_status"], "approved")

    def test_without_the_status_the_same_launch_is_incomplete(self):
        """Fail-before: take approval_status away and the live probe is rejected, by name."""
        mapping = mapping_of(live())
        broken = copy.deepcopy(mapping)
        del broken["supplied"]["main_price"]["approval_status"]
        fails = rule.incomplete_violations({"test_only": False, "checkout": broken}, broken)
        self.assertEqual([f.split(":")[0] for f in fails], ["AF-LAUNCH-CHECKOUT-INCOMPLETE"])
        self.assertIn("main_price.approval_status", fails[0])

    def test_a_practice_launch_still_says_test_only(self):
        payload = raw_intake("single_simple")
        normalized = intake.validate(payload)  # raw_intake says test_only true out loud (issue 36)
        self.assertEqual(mapping_of(normalized)["supplied"]["main_price"]["approval_status"], "test_only")

    def test_the_rule_is_the_one_checkout_instances_uses(self):
        def offer(status):
            return {"canonical": {"prices": [{"approval_status": status}]}}
        self.assertEqual(checkout.production_approval_status(offer("provided")), "approved")
        self.assertEqual(checkout.production_approval_status(offer("approved")), "approved")
        self.assertEqual(checkout.production_approval_status(offer("recommended_unapproved")),
                         "recommended_unapproved")  # Skill 79's validator then judges it
        self.assertIsNone(checkout.production_approval_status(offer("unknown")))
        self.assertIsNone(checkout.production_approval_status({}))  # unresolved stays unknown, never "approved"

    def test_an_unresolved_price_is_never_defaulted_to_approved(self):
        bare = {"offer_id": "main-1", "price": {"amount_minor": 5000, "currency": "USD"}}
        price = checkout._price_choice(bare, {}, None)
        self.assertNotIn("approval_status", price)
        self.assertIn("approval_status", price["unknown"])


class ValidationClockTests(unittest.TestCase):
    """Skill 79's validator is given the time only for a LIVE request (test_only is exactly False)."""

    def test_the_clock_rides_only_a_request_that_says_it_is_live(self):
        self.assertIsInstance(checkout.validation_clock({"test_only": False}), str)
        self.assertIsNone(checkout.validation_clock({"test_only": True}))
        self.assertIsNone(checkout.validation_clock({}))  # silence is not "live"
        self.assertIsNone(checkout.validation_clock({"test_only": None}))

    def test_replay_hands_the_validator_the_clock_only_for_a_live_request(self):
        calls = []
        fake = mock.Mock(validate_request=lambda *args: calls.append(args))
        with mock.patch.object(checkout, "_load_validator", return_value=fake):
            self.assertEqual(checkout.replay({"test_only": False}), ("accepted", ""))
            self.assertEqual(checkout.replay({"test_only": True}), ("accepted", ""))
        live_call, practice_call = calls
        self.assertEqual((len(live_call), len(practice_call)), (2, 1))
        self.assertIsInstance(live_call[1], str)


if __name__ == "__main__":
    unittest.main()
