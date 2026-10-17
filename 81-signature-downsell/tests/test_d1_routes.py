"""S81-06 local route fixtures for D1, run against the packet reference
contracts (imported read-only from the packet; the packet is never modified).
Covers the D1 branches of doc 18 section 2 at L1. Installed L3/L4 route
proof remains pending S49 graph + S80 canonical U2 + S06 test location.
Run with the rest of the suite: python3 -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

PACKET_REF = Path("/home/hatch/workspace/signature-launch/packet/reference")
sys.path.insert(0, str(PACKET_REF))
from reference_contracts import Extras, resolve_after  # noqa: E402

BASE = frozenset(["MAIN-A"])


class D1RouteTests(unittest.TestCase):
    def test_d1_paid_reaches_same_u2_as_u1(self):
        f = Extras()
        via_u1 = resolve_after("upsell_1", "payment_succeeded", BASE, f, True)[0]
        stage, bought = resolve_after("upsell_1", "explicit_decline", BASE, f)
        self.assertEqual(stage, "downsell_1")
        via_d1, bought = resolve_after(stage, "payment_succeeded", bought, f, True)
        self.assertEqual(via_d1, via_u1)
        self.assertEqual(via_d1, "upsell_2")
        self.assertEqual(bought, frozenset(["MAIN-A", "D1"]))

    def test_d1_paid_u2_disabled_goes_to_thank_you(self):
        f = Extras(upsell_2=False)
        stage, bought = resolve_after("upsell_1", "explicit_decline", BASE, f)
        stage, bought = resolve_after(stage, "payment_succeeded", bought, f, True)
        self.assertEqual(stage, "thank_you")
        self.assertEqual(bought, frozenset(["MAIN-A", "D1"]))

    def test_d1_declined_goes_to_thank_you_base_preserved(self):
        f = Extras()
        stage, bought = resolve_after("upsell_1", "explicit_decline", BASE, f)
        stage, bought = resolve_after(stage, "explicit_decline", bought, f)
        self.assertEqual(stage, "thank_you")
        self.assertEqual(bought, BASE)

    def test_d1_with_bump_preserves_bump_on_decline(self):
        f = Extras()
        start = frozenset(["MAIN-A", "BUMP"])
        stage, bought = resolve_after("upsell_1", "explicit_decline", start, f)
        stage, bought = resolve_after(stage, "explicit_decline", bought, f)
        self.assertEqual(bought, start)

    def test_d1_failed_or_pending_payment_stays_on_d1(self):
        f = Extras()
        for event in ("payment_failed", "payment_pending", "requires_customer_action"):
            stage, bought = resolve_after("downsell_1", event, BASE, f)
            self.assertEqual(stage, "downsell_1")
            self.assertEqual(bought, BASE)

    def test_decline_both_never_reaches_u2(self):
        f = Extras()
        stage, bought = resolve_after("upsell_1", "explicit_decline", BASE, f)
        stage, bought = resolve_after(stage, "explicit_decline", bought, f)
        self.assertEqual(stage, "thank_you")
        self.assertNotIn("U2", bought)

    def test_d1_unreachable_when_disabled(self):
        f = Extras(downsell_1=False)
        stage, _ = resolve_after("upsell_1", "explicit_decline", BASE, f)
        self.assertEqual(stage, "thank_you")


if __name__ == "__main__":
    unittest.main()
