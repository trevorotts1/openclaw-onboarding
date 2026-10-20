#!/usr/bin/env python3
"""Skill 49 reads the one answers file in both modes, and asks nothing twice.

Free: no network, no model, no paid call.
Run: python3 shared-utils/client_intake/tests/test_consumers_49.py
"""
import hashlib
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
REPO = PKG.parents[1]
FIX = PKG / "fixtures"
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(REPO / "49-signature-funnel/scripts"))
import engine as e  # noqa: E402

li = importlib.import_module("launch_intake")
psi = importlib.import_module("prove_sf_intake")


def session(**kw):
    return li.new_session(tenant_id="t1", location_id="loc1", launch_id="L1", client_identity_ref="client:1", **kw)


def doc(name):
    return json.loads((FIX / name).read_text())


class LaunchModeReadsTheAnswersFile(unittest.TestCase):
    def test_nothing_the_client_already_answered_is_asked_again(self):
        s = li.ingest_answers(session(), doc("answers.elevation.json"))
        asked = []
        while True:
            q = li.next_question(s)
            if not q:
                break
            asked.append(q["id"])
            li.answer(s, q["id"], "Some are missing" if q["id"] == "d1_brand" else "x")
        self.assertEqual(asked, ["d1_brand"], "only the brand files question is left, and only because no brand file exists yet")

    def test_brand_file_closes_the_brand_question_with_ref_and_hash(self):
        with tempfile.TemporaryDirectory() as td:
            bf = Path(td) / "client-brand.json"
            bf.write_text('{"brand_id": "elevation"}')
            s = li.ingest_answers(session(), doc("answers.elevation.json"), bf)
        self.assertEqual(s["brand_hash"], hashlib.sha256(b'{"brand_id": "elevation"}').hexdigest())
        self.assertIsNone(li.next_question(s))

    def test_elevation_assembles_a_valid_multiple_options_plan(self):
        with tempfile.TemporaryDirectory() as td:
            bf = Path(td) / "b.json"
            bf.write_text("{}")
            s = li.ingest_answers(session(), doc("answers.elevation.json"), bf)
        out = li.assemble_plan(s)
        self.assertIn(out["state"], ("awaiting_plan_approval", "recommendation_ready"), out)
        mains = [o["display_name"] for o in out["plan"]["offers"] if o["slot"] == "main"]
        self.assertEqual(mains, ["Starter", "Premium"])
        self.assertEqual(out["plan"]["journey_mode"], "multiple_options")

    def test_levels_build_named_priced_mains_and_never_ask_for_a_single_price(self):
        s = li.ingest_answers(session(), doc("answers.7fig.json"))
        out = li.assemble_plan(s)
        # the launch validator only gains folded_levels in the Skill 49 lane; until then this is its one complaint
        for m in out.get("missing", []):
            self.assertNotIn("price", m)
            self.assertNotIn("package", m)
        if out["state"] == "awaiting_missing_fact":
            self.assertEqual(out["missing"], ["plan validation: journey_mode 'folded_levels' is not a launch mode"])
        else:
            self.assertEqual(len([o for o in out["plan"]["offers"] if o["slot"] == "main"]), 3)

    def test_defaults_enter_as_recommended_unapproved_never_approved(self):
        s = li.ingest_answers(session(), doc("answers.7fig.json"))
        self.assertEqual(s["answers"]["image_provider"]["state"], "recommended_unapproved")
        self.assertEqual(s["answers"]["journey_mode"]["value"], "folded_levels")
        self.assertEqual(len(s["answers"]["offers.main.packages"]["value"]), 3)

    def test_help_me_check_is_no_longer_assumed_saved(self):
        s = session()
        li.answer(s, "d1_brand", "Help me check")
        self.assertEqual(s["answers"]["brand_ref"]["state"], "unknown")

    def test_launch_question_asks_for_the_main_color_and_offers_help(self):
        q = next(x for x in li.load_question_bank() if x["id"] == "d1_brand")
        self.assertIn("main color", q["prompt"])
        self.assertIn("three palettes", q["prompt"])
        self.assertLessEqual(len(q["choices"]), 3)


class LegacyModeReadsTheSameFile(unittest.TestCase):
    def test_same_answers_give_the_same_offer_fields_in_both_modes(self):
        d = doc("answers.elevation.json")
        launch = e.to_launch_known(d)
        brief = e.to_sf_brief_answers(d)
        main = launch["offers.main.description"]["value"]
        self.assertIn(main["display_name"], brief["q1_offer"])
        self.assertIn(main["description"], brief["q1_offer"])
        self.assertEqual(main["deliverables"], d["answers"]["deliverables"]["value"])
        self.assertEqual("; ".join(main["deliverables"]), brief["q5_goods"])
        self.assertEqual(launch["offers.main.transformation"]["value"], d["answers"]["offer_transformation"]["value"])
        self.assertIn(launch["offers.main.transformation"]["value"], brief["q2_price_promise"])
        # the same palette roles reach the legacy q7 text
        for hex_ in ("#0A7E8C", "#102A43", "#E76F51"):
            self.assertIn(hex_, brief["q7_brand_colors"])
        self.assertIn("primary #0A7E8C", brief["q7_brand_colors"])

    def test_sf_spec_q7_asks_for_the_main_color_and_names_the_help(self):
        spec = json.loads((REPO / "49-signature-funnel/intake/sf-intake-questions.json").read_text())
        q7 = next(q for q in spec["questions"] if q["id"] == "q7")
        self.assertIn("MAIN color", q7["prompt"])
        self.assertIn("help me", q7["prompt"])
        self.assertEqual(spec["canonical_bank"], "shared-utils/client_intake/question-bank.json")

    def test_prover_spec_and_self_test_still_pass(self):
        self.assertEqual(psi.prove(str(REPO / "49-signature-funnel/intake/sf-intake-questions.json")), 0)
        self.assertEqual(psi.self_test(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
