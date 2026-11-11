"""Issue 96: Skill 44's launch gate accepts Skill 50's registry lifecycle settings for every
purchase-sensitive flow, and still refuses a flow that keeps sending after a verified purchase.

Run: python3 -m pytest 44-convert-and-flow-operator/tools/engine/tests/test_registry_stop_on_purchase.py -q
"""
import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))
from cli_anything.gohighlevel.utils import launch_step_compiler as lsc  # noqa: E402

REGISTRY = HERE.parents[4] / "50-email-engine" / "profiles" / "launch-email-families.json"
FAMILIES = {f["kind"]: f for f in json.loads(REGISTRY.read_text(encoding="utf-8"))["families"]}
# welcome_access is the post-purchase delivery email; every other family must stop.
SENSITIVE = sorted(set(FAMILIES) - {"welcome_access"})
STOP = "stop_on_verified_purchase"
SUPPRESS = "suppress_promotion_after_verified_purchase"
RECHECK = "recheck_eligibility_immediately_before_send"
FOLLOW_UPS = ("upsell_followup", "downsell_followup")


def _gate(kind, lifecycle):
    return lsc._lifecycle_blockers(
        {"id": "email_%s" % kind, "family": kind, "lifecycle": lifecycle,
         "lifecycle_source": "build_plan"})


def _follow_gate(lifecycle):
    """The registry row as Skill 44 meets it in production: family upsell_downsell and the
    followed offer a Skill 49 launch plan declares."""
    return lsc._lifecycle_blockers(
        {"id": "auto_up1", "family": lsc.FOLLOW_UP_FAMILY, "followed_offer_id": "off-up1",
         "lifecycle": lifecycle, "lifecycle_source": "build_plan"})


class RegistryStopOnPurchase(unittest.TestCase):
    def test_six_purchase_sensitive_families_are_checked(self):
        self.assertEqual(len(SENSITIVE), 6)

    def test_gate_accepts_the_registry_settings(self) -> None:
        for kind in SENSITIVE:
            self.assertEqual(_gate(kind, FAMILIES[kind]["lifecycle"]), [], kind)

    def test_gate_refuses_a_flow_that_keeps_sending(self) -> None:
        for kind in SENSITIVE:
            lc = copy.deepcopy(FAMILIES[kind]["lifecycle"])
            lc["stop_rules"] = [r for r in lc["stop_rules"] if r["rule"] != STOP]
            blocked = _gate(kind, lc)
            self.assertEqual(len(blocked), 1, kind)
            self.assertIn(STOP, blocked[0], kind)
            lc = copy.deepcopy(FAMILIES[kind]["lifecycle"])
            lc["suppression_rules"] = [r for r in lc["suppression_rules"] if r["rule"] != SUPPRESS]
            blocked = _gate(kind, lc)
            self.assertEqual(len(blocked), 1, kind)
            self.assertIn(SUPPRESS, blocked[0], kind)

    def test_follow_up_rows_pass_the_gate_as_the_production_family(self) -> None:
        # Deleting purchase_of from a follow-up row in the registry makes Skill 44 refuse every
        # real upsell/downsell build, so the registry row itself must carry it.
        for kind in FOLLOW_UPS:
            self.assertEqual(_follow_gate(FAMILIES[kind]["lifecycle"]), [], kind)
            lc = copy.deepcopy(FAMILIES[kind]["lifecycle"])
            for rule in lc["stop_rules"]:
                if rule["rule"] == STOP:
                    del rule["purchase_of"]
            self.assertEqual(_follow_gate(lc), ["guards:auto_up1:%s.purchase_of" % STOP], kind)

    def test_gate_refuses_a_flow_that_skips_the_send_time_recheck(self) -> None:
        for kind in SENSITIVE:
            lc = copy.deepcopy(FAMILIES[kind]["lifecycle"])
            lc["suppression_rules"] = [r for r in lc["suppression_rules"] if r["rule"] != RECHECK]
            self.assertEqual(_gate(kind, lc), ["guards:email_%s:%s" % (kind, RECHECK)], kind)


if __name__ == "__main__":
    unittest.main()
