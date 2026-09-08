#!/usr/bin/env python3
"""F19 — capability/dependency-graph preflight tests (unittest, no network).

Contract (QC-F19): build plans independently for text-only, image, video and
optional podcast; remove every unused dependency and the requested outputs
still execute; remove one required dependency and ONLY the dependent nodes
wait with a repair action; never require all media providers for a single
chosen provider; cost is estimated from planned assets vs available balance;
unsupported/deferred modes are never presented as delivered.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent.parent / "57-social-media-in-a-box" / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / ("%s.py" % name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pg = _load("preflight_gate")


def _base(**extra):
    cfg = {
        "brandName": "Brand One", "pit": "pit-set", "locationId": "loc123", "userId": "user123",
        "openrouterKey": "set", "openrouterModel": "google/gemini-2.0-flash-001",
        "openrouterFallbacks": ["meta-llama/llama-3.1-70b", "mistralai/mistral-large"],
        "kieKey": "set", "geminiKey": "set", "platforms": ["facebook"], "postTypes": ["post"],
        "timezone": "America/New_York", "status": "Paid",
        "probes": {"kieCredits": 500, "openrouterBalance": 25.0, "ghlTokenValid": True,
                   "connectedAccounts": [{"account_id": "fb-1", "platform": "facebook",
                                          "account_name": "Brand One FB"}]},
    }
    cfg.update(extra)
    return cfg


class TestPlanResolution(unittest.TestCase):
    def test_text_only_plan(self):
        plan = pg.resolve_output_plan(_base())
        self.assertTrue(plan["ghl_delivery"])
        self.assertFalse(plan["images"])
        self.assertFalse(plan["video"])
        self.assertFalse(plan["podcast"])

    def test_image_plan_via_carousel_post_type(self):
        plan = pg.resolve_output_plan(_base(postTypes=["post", "carousel"]))
        self.assertTrue(plan["images"])
        self.assertFalse(plan["video"])

    def test_video_plan(self):
        plan = pg.resolve_output_plan(_base(postTypes=["video"]))
        self.assertTrue(plan["video"])

    def test_podcast_only_when_fold_on(self):
        self.assertFalse(pg.resolve_output_plan(_base())["podcast"])
        self.assertTrue(pg.resolve_output_plan(_base(podcast=True))["podcast"])


class TestTextOnlyRunsOnEveryUnusedDependencyRemoved(unittest.TestCase):
    """QC-F19: remove every unused dependency; the requested outputs still run."""

    def test_text_only_without_kie_gemini_fishaudio_podbean(self):
        cfg = _base()
        del cfg["kieKey"]
        del cfg["geminiKey"]
        cfg["probes"].pop("kieCredits", None)
        fails = pg.evaluate(cfg, live=False)
        self.assertEqual(fails, [])  # text-only Facebook work continues

    def test_text_only_without_media_probes_at_all(self):
        cfg = _base()
        del cfg["kieKey"]
        del cfg["geminiKey"]
        cfg["probes"] = {"openrouterBalance": 25.0, "ghlTokenValid": True,
                         "connectedAccounts": [{"account_id": "fb-1", "platform": "facebook",
                                                "account_name": "Brand One FB"}]}
        self.assertEqual(pg.evaluate(cfg, live=False), [])

    def test_image_plan_does_not_require_podcast_credentials(self):
        cfg = _base(postTypes=["carousel"])  # images requested
        self.assertNotIn("fishAudioKey", pg.required_secrets_for_plan(cfg, pg.resolve_output_plan(cfg)))
        fails = pg.evaluate(cfg, live=False)
        self.assertEqual(fails, [])  # never require ALL media providers for the chosen one

    def test_podcast_off_means_fishaudio_absent_is_fine(self):
        cfg = _base()
        fails = pg.evaluate(cfg, live=False)
        self.assertEqual(fails, [])


class TestRequiredDependencyRemovedWaitsWithRepair(unittest.TestCase):
    """QC-F19: remove ONE required dependency -> only dependent nodes fail,
    each with a SPECIFIC repair action."""

    def test_image_plan_without_kie_blocks_image_branch_only(self):
        cfg = _base(postTypes=["carousel"])
        del cfg["kieKey"]
        fails = pg.evaluate(cfg, live=False)
        codes = [c for c, _m in fails]
        self.assertIn(pg.AF_CONFIG, codes)  # the image branch's key is required
        # the text/social branch is NOT what failed: no balance/token complaints
        self.assertNotIn(pg.AF_BALANCE, codes)
        self.assertNotIn(pg.AF_TOKEN, codes)
        # the message names the plan-scoped secret, never a global wall
        self.assertTrue(any("kieKey" in m for _c, m in fails))

    def test_kie_credits_below_plan_estimate_blocks_images_only(self):
        cfg = _base(postTypes=["carousel"])
        cfg["probes"]["kieCredits"] = 10
        fails = pg.evaluate(cfg, live=False)
        codes = [c for c, _m in fails]
        self.assertIn(pg.AF_CREDITS, codes)
        self.assertNotIn(pg.AF_BALANCE, codes)

    def test_podcast_requested_without_credentials_specific_repair(self):
        cfg = _base(podcast=True)
        fails = pg.evaluate(cfg, live=False)
        codes = [c for c, _m in fails]
        self.assertIn(pg.AF_CAPABILITY, codes)
        msg = " ".join(m for c, m in fails if c == pg.AF_CAPABILITY)
        self.assertIn("fishAudioKey", msg)
        self.assertIn("podcast", msg.lower())

    def test_ghl_token_removed_blocks_only_ghl_node(self):
        cfg = _base()
        cfg["probes"]["ghlTokenValid"] = False
        fails = pg.evaluate(cfg, live=False)
        codes = [c for c, _m in fails]
        self.assertIn(pg.AF_TOKEN, codes)
        self.assertNotIn(pg.AF_CREDITS, codes)  # the image branch was never consulted


class TestCostEstimateFromPlan(unittest.TestCase):
    def test_client_exact_estimate_wins(self):
        cfg = _base(postTypes=["carousel"], creditEstimates={"images": 300})
        cfg["probes"]["kieCredits"] = 250  # above the default band 200, below the plan estimate
        fails = pg.evaluate(cfg, live=False)
        self.assertTrue(any(c == pg.AF_CREDITS for c, _m in fails))
        self.assertTrue(any("300" in m for c, m in fails if c == pg.AF_CREDITS))

    def test_balance_estimate_text_branch(self):
        cfg = _base(creditEstimates={"text": 50})
        cfg["probes"]["openrouterBalance"] = 40
        fails = pg.evaluate(cfg, live=False)
        self.assertTrue(any(c == pg.AF_BALANCE for c, _m in fails))
        self.assertTrue(any("50" in m for c, m in fails if c == pg.AF_BALANCE))


class TestProviderPolicyNotGlobal(unittest.TestCase):
    """openrouterModel/fallbacks are provider-POLICY contract fields, not the
    global hard floor: a text plan without them still passes the dependency
    graph (policy validation lives in the provider-policy contract)."""

    def test_missing_model_fields_pass_dependency_graph(self):
        cfg = _base()
        del cfg["openrouterModel"]
        del cfg["openrouterFallbacks"]
        self.assertEqual(pg.evaluate(cfg, live=False), [])

    def test_required_fields_floor_is_minimal(self):
        self.assertEqual(set(pg.REQUIRED_FIELDS),
                         {"brandName", "locationId", "userId", "timezone", "status"})


class TestUnsupportedModesNotDelivered(unittest.TestCase):
    def test_deferred_mode_reported_unavailable_before_selection(self):
        plan = pg.resolve_output_plan(_base(narratedVideo=True))
        # narrated-video is DEFERRED to v0.3.0: it must NOT appear as a planned,
        # deliverable capability in the dependency graph.
        self.assertNotIn("narrated_video", plan)
        self.assertFalse(plan.get("narrated", False))

    def test_syndicate_stub_not_a_delivered_capability(self):
        plan = pg.resolve_output_plan(_base(syndicate=True))
        self.assertNotIn("syndicate", plan)  # v0.4.0 deferred stub stays out of the graph


if __name__ == "__main__":
    unittest.main()