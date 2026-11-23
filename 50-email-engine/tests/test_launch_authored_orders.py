#!/usr/bin/env python3
"""SWB-022: registered authored framework orders for launch count variants.

A client launch plan approved a 10-email welcome_access sequence and a 2-email
upsell_followup sequence whose framework labels follow the client's own
approved order, not the single map each count variant registered:

  welcome_access 10:  six-ws, before-after-bridge, three-b-plan, pas,
                      three-b-plan, six-ws, three-b-plan x4 (3-B slots are
                      short notes under 150 words)
  upsell_followup 2:  features-to-benefit (follows upsell page 1),
                      before-after-bridge (follows upsell page 2)

The prover refused both with AF-EMAIL-SEQUENCE-MAP. Relabelling would falsify
the labels and the short 3-B notes would then fail AF-EMAIL-WORDBAND, and
copy is never padded. The fix registers each order as a named pattern map of
its count variant (`authored_order_patterns`), matched slot for slot. This
proves:

  (a) both approved orders now prove with the locked brief, and the emitter
      carries the matched pattern (and, for upsell, each slot's page);
  (b) an order the registry does not register is still refused, the declared
      ledger pattern still wins, the pattern's word bands still bind, and the
      default maps are unchanged;
  (c) the registry refuses a malformed authored order.

Hermetic: fictional fixtures, temp dirs only, no network.
Run: python3 50-email-engine/tests/test_launch_authored_orders.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cv = _load("swb022_count_variants", HERE / "test_launch_count_variants.py")
launch_profiles = cv.launch_profiles
emitter = cv.emitter

WELCOME_ORDER = {1: "six-ws", 2: "before-after-bridge", 3: "three-b-plan", 4: "pas",
                 5: "three-b-plan", 6: "six-ws", 7: "three-b-plan", 8: "three-b-plan",
                 9: "three-b-plan", 10: "three-b-plan"}
UPSELL_ORDER = {1: "features-to-benefit", 2: "before-after-bridge"}
PLAN = {"main_launch": 3, "doors_closing": 1, "welcome_access": 10, "upsell_followup": 2}


def _authored(brief, order, short_slots=()):
    """A sequence authored in `order` WITHOUT a declared pattern: the labels
    are the author's own, the 3-B (or listed) slots are short notes."""
    doc = cv._emails(brief)
    for e in doc["emails"]:
        slot = e["e_slot"]
        e["framework"] = order[slot]
        words = 90 if (order[slot] == "three-b-plan" or slot in short_slots) else 200
        e["body"] = cv._body(words, e["ctas"], False)
    doc.pop("pattern", None)
    return doc


class _Base(cv._Tmp):
    def setUp(self):
        super().setUp()
        self.briefs = cv._adapt(cv._plan(PLAN))

    def prove_doc(self, kind, doc):
        bpath = self.write("brief-%s.json" % kind, self.briefs[kind])
        return self.prove(self.write("emails-%s.json" % kind, doc), bpath)

    @staticmethod
    def codes(out):
        return [f["code"] for f in out.get("failures", [])]


class ApprovedOrdersProve(_Base):
    def test_welcome_short_form_order_proves(self):
        rc, out = self.prove_doc("welcome_access",
                                 _authored(self.briefs["welcome_access"], WELCOME_ORDER))
        self.assertEqual(rc, 0, out)

    def test_upsell_one_email_per_page_order_proves(self):
        rc, out = self.prove_doc("upsell_followup",
                                 _authored(self.briefs["upsell_followup"], UPSELL_ORDER))
        self.assertEqual(rc, 0, out)

    def test_emitter_carries_the_matched_pattern(self):
        for kind, order, name, pages in (
                ("welcome_access", WELCOME_ORDER, "event_nurture_short_form", None),
                ("upsell_followup", UPSELL_ORDER, "one_email_per_upsell_page",
                 {"1": "upsell_1", "2": "upsell_2"})):
            plan = emitter.build_plan(self.briefs[kind], _authored(self.briefs[kind], order))
            self.assertEqual(emitter.validate_plan(plan), [], kind)
            meta = plan["_meta"]
            self.assertEqual(meta["framework_pattern"], name, kind)
            self.assertTrue(meta["framework_pattern_purpose"], kind)
            self.assertEqual(meta["framework_pattern_slot_pages"], pages, kind)
            self.assertEqual(meta["framework_map"], {str(k): v for k, v in order.items()}, kind)
            self.assertIs(meta["draft_only"], True)
            wf = plan[[k for k in plan if k not in ("folder", "_meta")][0]]
            self.assertEqual(wf["status"], "draft")

    def test_emitter_refuses_an_unregistered_pattern_name(self):
        plan = emitter.build_plan(self.briefs["upsell_followup"],
                                  _authored(self.briefs["upsell_followup"], UPSELL_ORDER))
        plan["_meta"]["framework_pattern"] = "made_up_order"
        self.assertTrue(any("framework_pattern" in e for e in emitter.validate_plan(plan)))


class EverythingElseIsStillRefused(_Base):
    def test_an_unregistered_order_is_still_refused(self):
        order = {**WELCOME_ORDER, 3: "pas"}
        rc, out = self.prove_doc("welcome_access",
                                 _authored(self.briefs["welcome_access"], order))
        self.assertEqual(rc, 2)
        self.assertIn("AF-EMAIL-SEQUENCE-MAP", self.codes(out))
        order = {**UPSELL_ORDER, 2: "acca"}
        rc, out = self.prove_doc("upsell_followup",
                                 _authored(self.briefs["upsell_followup"], order))
        self.assertEqual(rc, 2)
        self.assertIn("AF-EMAIL-SEQUENCE-MAP", self.codes(out))

    def test_the_pattern_word_bands_bind(self):
        doc = _authored(self.briefs["welcome_access"], WELCOME_ORDER)
        doc["emails"][2]["body"] = cv._body(200, doc["emails"][2]["ctas"], False)  # 3-B slot 3
        rc, out = self.prove_doc("welcome_access", doc)
        self.assertEqual(rc, 2)
        self.assertIn("AF-EMAIL-WORDBAND", self.codes(out))
        self.assertNotIn("AF-EMAIL-SEQUENCE-MAP", self.codes(out))

    def test_a_declared_pattern_still_wins(self):
        doc = _authored(self.briefs["upsell_followup"], UPSELL_ORDER)
        doc["pattern"] = "upsell_1"
        rc, out = self.prove_doc("upsell_followup", doc)
        self.assertEqual(rc, 2)
        self.assertIn("AF-EMAIL-SEQUENCE-MAP", self.codes(out))

    def test_the_order_needs_the_locked_count(self):
        doc = _authored(self.briefs["welcome_access"], WELCOME_ORDER)
        rc, out = self.prove(self.write("no-brief.json", doc))  # default count 2 applies
        self.assertEqual(rc, 2)
        self.assertIn("AF-EMAIL-SEQUENCE-LENGTH", self.codes(out))

    def test_default_and_registered_maps_are_unchanged(self):
        fams = launch_profiles.families()
        wa = launch_profiles.resolve(fams["welcome_access"], 10)
        self.assertEqual(launch_profiles.framework_map(wa)[3], "star-story-solution")
        up = launch_profiles.resolve(fams["upsell_followup"], 2)
        self.assertEqual(launch_profiles.framework_map(up), {1: "features-to-benefit", 2: "pas"})
        self.assertEqual(launch_profiles.framework_map(up, "upsell_2"),
                         {1: "acca", 2: "three-b-plan"})
        self.assertNotIn("authored_order_patterns", launch_profiles.resolve(fams["welcome_access"]))
        # the registered default 10-email order still proves (no regression)
        default = {k: v for k, v in launch_profiles.framework_map(wa).items()}
        rc, out = self.prove_doc("welcome_access", _authored(
            self.briefs["welcome_access"], default, short_slots=(10,)))
        self.assertEqual(rc, 0, out)


class RegistryRefusesMalformedOrders(cv._Tmp):
    def _reg_with(self, mutate):
        reg = json.loads(launch_profiles.REGISTRY_PATH.read_text(encoding="utf-8"))
        fam = next(f for f in reg["families"] if f["kind"] == "upsell_followup")
        mutate(fam["count_variants"]["2"])
        return self.write("reg.json", reg)

    def test_malformed_orders_are_refused(self):
        cases = (
            lambda v: v.__setitem__("authored_order_patterns", ["not_a_pattern"]),
            lambda v: v["pattern_purposes"].pop("one_email_per_upsell_page"),
            lambda v: v["pattern_maps"].__setitem__("one_email_per_upsell_page",
                                                   dict(v["framework_map"])),
            lambda v: v.__setitem__("authored_order_patterns", []),
        )
        for i, mutate in enumerate(cases):
            with self.assertRaises(launch_profiles.RegistryError, msg=i):
                launch_profiles.load_registry(self._reg_with(mutate))


if __name__ == "__main__":
    unittest.main(verbosity=2)
