"""Lane 83: the picture choices, asked in plain English, with a safe path for "I don't know".

Free: nothing here calls a provider.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))

import substrate  # noqa: E402
from launcher_core import image_plan  # noqa: E402
from launcher_core.image_plan import ImagePlanError, resolve  # noqa: E402

BASE = {"brand_file": "/tmp/brand.json", "brand_owner": "TEST-ONLY Client"}


class QuestionTests(unittest.TestCase):
    def test_every_question_is_plain_short_and_has_a_way_out(self):
        for q in image_plan.QUESTIONS:
            self.assertLessEqual(len(q["choices"]), 3, q["id"])  # never a wall of options
            self.assertTrue(q["text"].endswith("?"), q["id"])
            self.assertLessEqual(len(q["text"]), 110, q["id"])
            self.assertTrue(q["why"], q["id"])
            self.assertEqual(q["help_label"], "I'm not sure, help me")
            self.assertTrue(q["help"], q["id"])
            self.assertTrue(q["target_fields"], q["id"])

    def test_the_style_question_shows_what_each_choice_looks_like(self):
        style = next(q for q in image_plan.QUESTIONS if q["id"] == "design_style")
        self.assertEqual([c["value"] for c in style["choices"]], ["A", "B", "C"])
        self.assertTrue(all(c["example"] for c in style["choices"]))

    def test_money_is_never_defaulted_in_the_question_data(self):
        cap = next(q for q in image_plan.QUESTIONS if q["id"] == "image_cap")
        self.assertIsNone(cap["safe_default"])
        self.assertEqual(cap["flag"], "never_default_when_paid")


class DontKnowTests(unittest.TestCase):
    def test_unknown_style_defaults_flagged_and_does_not_block(self):
        for answer in (None, "unknown", "I'm not sure", {"status": "unknown"}, "help me"):
            inputs, to_confirm = resolve({**BASE, "design_style": answer}, test_only=True)
            self.assertEqual(inputs["design_style"], "A")
            self.assertEqual(inputs["design_style_source"], "default_to_confirm")
            row = next(r for r in to_confirm if r["field"] == "image_plan.design_style")
            self.assertEqual(row["status"], "default_to_confirm")
            self.assertIn("weren't sure", row["reason"])
            self.assertIn("A, B or C", row["how_to_change"])

    def test_a_chosen_style_is_not_flagged(self):
        inputs, to_confirm = resolve({**BASE, "design_style": "B", "image_provider": "kie", "image_cap": 50},
                                     test_only=True)
        self.assertEqual(inputs["design_style"], "B")
        self.assertEqual(inputs["design_style_source"], "client_choice")
        self.assertEqual(to_confirm, [])

    def test_practice_run_defaults_cap_and_provider_flagged_and_stays_free(self):
        inputs, to_confirm = resolve(dict(BASE), test_only=True)
        self.assertEqual(inputs["executor_provider"], "stub")
        self.assertFalse(inputs["allow_paid"])
        self.assertEqual(inputs["image_cap"], image_plan.DEFAULT_STUB_IMAGE_CAP)
        flagged = {r["field"] for r in to_confirm}
        self.assertEqual(flagged, {"image_plan.design_style", "image_plan.image_provider",
                                   "image_plan.image_cap"})
        self.assertTrue(all("how_to_change" in r and r["reason"] for r in to_confirm))

    def test_unknown_brand_file_stops_with_help_not_a_dead_end(self):
        for raw in ({"brand_owner": "X"}, {"brand_owner": "X", "brand_file": "unknown"}):
            with self.assertRaises(ImagePlanError) as ctx:
                resolve(raw, test_only=True)
            self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-BRAND")
            self.assertIn("three palettes", ctx.exception.detail)
            self.assertIn("logo or website", ctx.exception.detail)

    def test_owner_is_required_so_no_page_wears_another_clients_look(self):
        with self.assertRaises(ImagePlanError) as ctx:
            resolve({"brand_file": "/tmp/b.json"}, test_only=True)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-OWNER")
        self.assertIn("another client", ctx.exception.detail)


class NeverDefaultedTests(unittest.TestCase):
    def test_a_real_run_never_picks_the_spend_cap(self):
        with self.assertRaises(ImagePlanError) as ctx:
            resolve(dict(BASE), test_only=False)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-CAP")
        self.assertIn("never pick this one for you", ctx.exception.detail)

    def test_a_real_run_never_assumes_the_written_approval(self):
        with self.assertRaises(ImagePlanError) as ctx:
            resolve({**BASE, "image_cap": 120}, test_only=False)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-APPROVAL")
        self.assertIn("nothing has been spent", ctx.exception.detail.lower())

    def test_a_real_run_with_cap_and_approval_may_spend_only_inside_them(self):
        inputs, _ = resolve({**BASE, "image_cap": 120, "paid_render_approval_ref": "APPR-9"}, test_only=False)
        self.assertEqual((inputs["executor_provider"], inputs["allow_paid"], inputs["image_cap"]),
                         ("kie", True, 120))

    def test_an_unbuilt_provider_is_refused_by_name_with_nothing_spent(self):
        for name in ("agnes", "other_explicit"):
            with self.assertRaises(ImagePlanError) as ctx:
                resolve({**BASE, "image_provider": name}, test_only=True)
            self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-PROVIDER")
            self.assertIn(name, ctx.exception.detail)
            self.assertIn("nothing was spent", ctx.exception.detail.lower())

    def test_bad_values_are_named(self):
        with self.assertRaises(ImagePlanError):
            resolve({**BASE, "design_style": "Z"}, test_only=True)
        with self.assertRaises(ImagePlanError):
            resolve({**BASE, "image_cap": 0, "image_provider": "kie"}, test_only=True)
        with self.assertRaises(ImagePlanError):
            resolve({**BASE, "surprise": 1}, test_only=True)


class FileTests(unittest.TestCase):
    def inputs(self):
        inputs, _ = resolve({**BASE, "design_style": "C", "image_cap": 10, "image_provider": "kie"},
                            test_only=True)
        return inputs

    def test_the_shared_file_holds_the_contract_keys_and_nothing_else(self):
        doc = image_plan.image_inputs_file(self.inputs())
        self.assertEqual(sorted(doc), sorted(image_plan.C3_KEYS))  # Skill 49 refuses any other key
        self.assertEqual(doc["image_provider"], "stub")            # the provider that really runs

    def test_skill_49_accepts_the_shared_file_it_is_handed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "image_inputs.json"
            path.write_text(json.dumps(image_plan.image_inputs_file(self.inputs())), encoding="utf-8")
            got = substrate.dispatch().pset.load_image_inputs(path)
        self.assertEqual((got["design_style"], got["image_provider"], got["allow_paid"]), ("C", "stub", False))

    def test_the_order_page_reader_gets_its_own_shape_of_the_same_values(self):
        doc = image_plan.order_page_inputs_file(self.inputs(), route_graph="/x/route-graph.json")
        self.assertEqual((doc["route_graph"], doc["provider"], doc["test_run"], doc["design_style"], doc["image_cap"]),
                         ("/x/route-graph.json", "stub", True, "C", 10))


if __name__ == "__main__":
    unittest.main(verbosity=2)
