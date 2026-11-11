"""Issue 12 at Skill 83: the order form's copy is Skill 79's emitter output, run before the checkout design lane.

`launch_bridge` writes the checkout request, runs `adapters.emit_checkout_manuscript` (Skill 79's emitter) and hands
the stamped file to `build_dispatch_config`, which refuses any manuscript that is not that emitter's output for that
request. A hand-staged copy-checkout.md never reaches the lane (and Skill 49's wrapper re-checks the same stamp).
"""

from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))
sys.path.insert(0, str(SKILL_ROOT / "fixtures"))

import adapters  # noqa: E402
from launcher_core import launch_bridge  # noqa: E402
from launcher_core import checkout_instances  # noqa: E402
from test_checkout_instances import prepared  # noqa: E402

TERMS_TEXT = {"guarantee_text": "Try it for 30 days.", "terms_text": "You agree to the terms of sale.",
              "consent_text": "I agree to the terms of sale."}


def price(amount):
    return {"price_choice_id": "x", "amount_minor": amount, "currency": "USD", "billing_type": "one_time"}


class EmittedCheckoutCopyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.td = Path(tmp.name)
        # The request the bridge itself builds from an intake (Skill 79 emitter input), not a stub: the emitter
        # validates it (validate_copy_request, INT-T-6), so every required fact but the Skill 06 read-back is real.
        normalized, graph, launch = prepared("multiple_options")
        request = checkout_instances.record(normalized, graph, launch=launch)["instances"][0]["request"]
        self.request, self.launch = request, launch
        terms = dict(TERMS_TEXT, guarantee_ref="g", terms_ref=request["terms_ref"], consent_ref=request["consent_ref"])
        files = {"request.json": request, "launch.json": launch, "checkout-terms.json": {"checkout_terms": terms}}
        for name, doc in files.items():
            (self.td / name).write_text(json.dumps(doc), encoding="utf-8")

    def emit(self):
        return adapters.emit_checkout_manuscript(
            request=self.td / "request.json", launch=self.td / "launch.json",
            terms=self.td / "checkout-terms.json", out=self.td / "copy-checkout.md")

    def test_the_emitter_runs_and_its_output_is_accepted_for_its_own_request(self):
        manuscript = self.emit()
        main = next(o for o in self.launch["offers"] if o["offer_id"] == self.request["main_offer_id"])
        self.assertIn(main["display_name"], manuscript.read_text(encoding="utf-8"))
        adapters._require_stamped(manuscript, self.td / "request.json")  # does not raise

    def test_a_hand_staged_copy_is_refused_before_any_page_is_built(self):
        staged = self.td / "staged.md"
        staged.write_text("## Section 1: Offer\n\nThe Studio, one payment of $97.\n", encoding="utf-8")
        with self.assertRaises(adapters.AdapterError) as ctx:
            adapters._require_stamped(staged, self.td / "request.json")
        self.assertIn("never staged by hand", str(ctx.exception))

    def test_copy_for_an_older_request_is_refused(self):
        manuscript = self.emit()
        (self.td / "request.json").write_text(json.dumps({"main_offer_id": "MAIN-A", "main_price": price(1)}),
                                              encoding="utf-8")
        with self.assertRaises(adapters.AdapterError):
            adapters._require_stamped(manuscript, self.td / "request.json")

    def test_a_refused_emission_names_the_cause_and_leaves_no_file(self):
        (self.td / "checkout-terms.json").write_text(json.dumps({"checkout_terms": {"terms_text": "t"}}),
                                                     encoding="utf-8")
        with self.assertRaises(adapters.AdapterError) as ctx:
            self.emit()
        self.assertIn("guarantee_text", str(ctx.exception))
        self.assertFalse((self.td / "copy-checkout.md").exists())

    def test_the_bridge_runs_the_emitter_and_no_longer_takes_a_staged_manuscript(self):
        source = (SKILL_ROOT / "launcher_core" / "launch_bridge.py").read_text(encoding="utf-8")
        self.assertIn("adapters.emit_checkout_manuscript(", source)
        self.assertNotIn('adapter_inputs["checkout_manuscript"]', source)
        self.assertTrue(hasattr(launch_bridge, "_checkout_request_file"))


class BridgeHandoffTests(unittest.TestCase):
    """The bridge writes ONE checkout request, has the emitter write the copy from it, and hands the design lane
    that same request and that same copy: the pair `build_dispatch_config` then checks by stamp."""

    def test_the_request_the_copy_was_written_from_is_the_request_handed_to_the_design_lane(self):
        normalized, _, launch = prepared("multiple_options")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / launch_bridge.INTAKE_SNAPSHOT).write_text(json.dumps(normalized), encoding="utf-8")
            launch_path = out / "launch.json"
            launch_path.write_text(json.dumps(launch), encoding="utf-8")
            seen = {}

            def emit(**kw):
                seen["emit"] = kw
                Path(kw["out"]).parent.mkdir(parents=True, exist_ok=True)
                Path(kw["out"]).write_text("copy", encoding="utf-8")
                return Path(kw["out"])

            def build(**kw):
                seen["build"] = kw
                return {"adapters": {}}

            fake = types.SimpleNamespace(emit_checkout_manuscript=emit, build_dispatch_config=build)
            inputs = {"brand_file": "b.md", "brand_owner": "o", "image_cap": 1, "design_style": "A",
                      "executor_provider": "stub", "allow_paid": False}
            adapter_inputs = {"bridge_config": "bridge.json", "author_session": "s", "copy": {}, "journey": {},
                              "enrichment": {}}
            launch_bridge._bind_adapters(fake, adapter_inputs, out, launch_path, inputs, out / "i.json", out / "o.json")
            design = seen["build"]["checkout_design"]
            request = out / "checkout-request.json"
            self.assertEqual(design["checkout_request"], str(request))
            written = json.loads(request.read_text(encoding="utf-8"))  # the Skill 79 request itself, not its instance
            self.assertEqual((written["main_offer_id"], written["main_price"]["billing_type"]), ("MAIN-A", "one_time"))
            self.assertEqual(seen["emit"]["request"], request)
            self.assertEqual(seen["emit"]["launch"], launch_path)
            self.assertEqual(seen["emit"]["terms"], out / "checkout-terms.json")
            self.assertEqual(design["manuscript"], str(seen["emit"]["out"]))


if __name__ == "__main__":
    unittest.main()
