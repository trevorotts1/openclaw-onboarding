#!/usr/bin/env python3
"""Issue 96: every purchase-sensitive Skill 50 flow stops sending on a verified purchase.

Skill 44's launch gate refuses any promotional build whose lifecycle lacks the
stop rule `stop_on_verified_purchase` and the suppression rule
`suppress_promotion_after_verified_purchase`.  The registry rows for the main
launch and doors-closing flows already carry both; this test pins the same
mechanism on every other purchase-sensitive flow.  The gate side is proved in
44-convert-and-flow-operator/tools/engine/tests/test_registry_stop_on_purchase.py.

Run: python3 -m pytest 50-email-engine/tests/test_stop_on_purchase.py -q
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "50-email-engine" / "profiles" / "launch-email-families.json"

FAMILIES = {f["kind"]: f for f in json.loads(REGISTRY.read_text(encoding="utf-8"))["families"]}
# welcome_access is the post-purchase delivery email: a purchase triggers it, so
# it has nothing to stop.  Any other family, present or future, must stop.
NOT_PURCHASE_SENSITIVE = {"welcome_access"}
SENSITIVE = sorted(set(FAMILIES) - NOT_PURCHASE_SENSITIVE)
STOP = "stop_on_verified_purchase"
SUPPRESS = "suppress_promotion_after_verified_purchase"


def _names(lifecycle: dict, key: str) -> list:
    return [r["rule"] for r in lifecycle[key]]


class StopOnVerifiedPurchase(unittest.TestCase):
    def test_the_purchase_sensitive_set_is_every_family_but_welcome_access(self) -> None:
        self.assertEqual(len(SENSITIVE), 6)
        self.assertNotIn("welcome_access", SENSITIVE)

    def test_every_purchase_sensitive_flow_stops_and_suppresses_on_verified_purchase(self) -> None:
        for kind in SENSITIVE:
            lc = FAMILIES[kind]["lifecycle"]
            self.assertIn(STOP, _names(lc, "stop_rules"), kind)
            self.assertIn(SUPPRESS, _names(lc, "suppression_rules"), kind)
            recheck = [r for r in lc["suppression_rules"]
                       if r["rule"] == "recheck_eligibility_immediately_before_send"]
            self.assertEqual(len(recheck), 1, kind)
            self.assertIn("verified_purchase", recheck[0]["checks"], kind)

    def test_stop_rule_is_scoped_to_this_campaign_like_the_main_launch_row(self) -> None:
        for kind in SENSITIVE:
            rule = next(r for r in FAMILIES[kind]["lifecycle"]["stop_rules"] if r["rule"] == STOP)
            self.assertEqual(rule["scope"], "this_campaign_only", kind)


if __name__ == "__main__":
    unittest.main()
