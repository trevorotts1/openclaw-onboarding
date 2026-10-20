#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_page_set.py - every page type in every funnel shape, with its designs, and the shared image
inputs. Run: python3 test_page_set.py (from scripts/). No network, no provider, no paid call.
"""
import copy
import itertools
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compile_launch_route as clr  # noqa: E402
import page_set as ps  # noqa: E402
import validate_launch_plan as vlp  # noqa: E402

REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "71-blackceo-signature-page" / "scripts"))
import deliverable_labels as labels  # noqa: E402

LAUNCH_EXAMPLE = json.loads((HERE / "fixtures" / "launch-example.json").read_text(encoding="utf-8"))
MODES = ("single_simple", "multiple_options", "free_entry", "folded_levels")
EXTRAS = ({"upsell_1": False, "downsell_1": False, "upsell_2": False},
          {"upsell_1": True, "downsell_1": False, "upsell_2": False},
          {"upsell_1": True, "downsell_1": True, "upsell_2": False},
          {"upsell_1": True, "downsell_1": False, "upsell_2": True},
          {"upsell_1": True, "downsell_1": True, "upsell_2": True})


def route_launch(mode, extras):
    """A launch record of this shape (route only; offers are the example's)."""
    launch = copy.deepcopy(LAUNCH_EXAMPLE)
    launch["journey_mode"], launch["extras"] = mode, dict(extras)
    return launch


def approved_launch(mode="multiple_options"):
    """A fully valid, approved launch of this shape plus its approval, as dispatch needs them."""
    launch = copy.deepcopy(LAUNCH_EXAMPLE)
    launch["journey_mode"] = mode
    launch["bump_enabled"] = True
    graph = clr.compile_route(launch)
    launch["route_graph_ref"] = f"route-graph:{launch['launch_id']}:rev{launch['revision']}"
    launch["route_graph_hash"] = clr.graph_hash(graph)
    launch["status"], launch["plan_approval_ref"] = "approved", "APPR-1"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    approval = {"schema_version": "1.0", "approval_id": "APPR-1", "subject_type": "launch_plan_build",
                "subject_hash": vlp.plan_document_hash(launch), "owner_identity_ref": "client-1",
                "source_message_ref": "m-1", "recorded_at": now, "scope": ["launch_plan_build"],
                "revoked": False,
                "verification_class": "recorded_consent_not_cryptographically_sealed"}
    return launch, approval


class EveryShapeEveryPage(unittest.TestCase):
    def test_every_route_node_of_every_shape_is_a_page_with_full_deliverables(self):
        ids = [d["id"] for d in ps.page_types()["deliverables"]]
        for mode, extras in itertools.product(MODES, EXTRAS):
            for chosen in (None, ["landing"], ["sales"], ["landing", "sales"]):
                launch = route_launch(mode, extras)
                got = ps.build_page_set(launch, landing_pages=chosen)
                with self.subTest(mode=mode, extras=extras, landing=chosen):
                    keys = [p["page_key"] for p in got["pages"]]
                    self.assertEqual(len(keys), len(set(keys)))
                    identities = {(p["role"], p["page_kind"], p["role_instance"]) for p in got["pages"]}
                    self.assertEqual(len(identities), len(got["pages"]), "role+page_kind+role_instance is unique")
                    for role in clr.expected_roles(launch):  # every route node has at least one page
                        self.assertTrue(any(p["request_role"] == role for p in got["pages"]), role)
                    for p in got["pages"]:
                        self.assertEqual(p["deliverables"], ids)
                        self.assertTrue(p["label"])
                    self.assertEqual(keys == sorted(keys, key=lambda k: ps.page_types()["pages"][k]["order"]), True)
                    self.assertEqual("product_selection" in keys, mode == "multiple_options")
                    self.assertEqual(got["to_confirm"] == ["landing_pages"], chosen is None)

    def test_landing_pages_the_client_chose_are_exactly_what_is_built(self):
        launch = route_launch("multiple_options", EXTRAS[-1])
        for chosen in (["landing"], ["sales"], ["landing", "sales"]):
            keys = [p["page_key"] for p in ps.build_page_set(launch, landing_pages=chosen)["pages"]]
            self.assertEqual([k for k in keys if k in ps.LANDING_PAGE_KEYS], chosen)

    def test_recommended_landing_pages_when_the_client_did_not_choose(self):
        self.assertEqual(ps.recommended_landing_pages(route_launch("free_entry", EXTRAS[0])), ["landing"])
        self.assertEqual(ps.recommended_landing_pages(route_launch("single_simple", EXTRAS[0])), ["sales"])
        self.assertEqual(ps.recommended_landing_pages(route_launch("single_simple", EXTRAS[-1])), ["landing", "sales"])
        self.assertEqual(ps.recommended_landing_pages(route_launch("folded_levels", EXTRAS[0])), ["landing", "sales"])

    def test_a_full_funnel_does_not_force_both_landing_pages(self):  # D1
        keys = [p["page_key"] for p in ps.build_page_set(
            route_launch("multiple_options", EXTRAS[-1]), landing_pages=["sales"])["pages"]]
        self.assertIn("sales", keys)
        self.assertNotIn("landing", keys)

    def test_folded_levels_has_no_selection_page_and_multiple_options_has_one(self):
        folded = [p["page_key"] for p in ps.build_page_set(route_launch("folded_levels", EXTRAS[-1]))["pages"]]
        multi = [p["page_key"] for p in ps.build_page_set(route_launch("multiple_options", EXTRAS[-1]))["pages"]]
        self.assertNotIn("product_selection", folded)
        self.assertIn("product_selection", multi)
        self.assertEqual(folded, ["landing", "sales", "checkout", "upsell_1", "upsell_2", "downsell_1", "thank_you"])

    def test_a_second_downsell_is_an_opt_in_design_page_on_the_downsell_request(self):
        launch = route_launch("multiple_options", EXTRAS[-1])
        got = ps.build_page_set(launch, landing_pages=["sales"], extra_pages=["downsell_2"])
        d2 = next(p for p in got["pages"] if p["page_key"] == "downsell_2")
        self.assertEqual((d2["role"], d2["role_instance"], d2["request_role"], d2["design_only"]),
                         ("downsell_1", "downsell_2", "downsell_1", True))
        self.assertEqual([p["page_key"] for p in got["pages"]][-2:], ["downsell_2", "thank_you"])
        with self.assertRaises(ps.PageSetError):  # no downsell_1 to follow
            ps.build_page_set(route_launch("single_simple", EXTRAS[1]), extra_pages=["downsell_2"])
        with self.assertRaises(ps.PageSetError):
            ps.build_page_set(launch, extra_pages=["upsell_3"])
        with self.assertRaises(ps.PageSetError):
            ps.build_page_set(launch, landing_pages=["opt_in"])

    def test_labels_match_the_ones_skill_71_prints_on_every_file(self):
        for key, page in ps.page_types()["pages"].items():
            role = page["label_role"]
            self.assertEqual(labels.page_type(role), page["label"], key)
            self.assertEqual(labels.pdf_name(role, "desktop", "desktop-wireframe"),
                             ps.slug_of(key) + "_DESKTOP_WIREFRAMES.pdf")
            self.assertEqual(labels.pdf_name(role, "mobile", "visual-mockup"),
                             ps.slug_of(key) + "_MOBILE_MOCKUPS-VISUAL.pdf")
            self.assertEqual(labels.board_name(role, "combined", "visual-mockup"),
                             ps.slug_of(key) + "_DESKTOP-and-MOBILE_MOCKUP-VISUAL-BOARD")

    def test_legacy_three_five_seven_step_funnels_are_the_same_page_entries(self):
        legacy = {n: [p["page_key"] for p in ps.legacy_page_set(n)["pages"]] for n in (3, 5, 7)}
        self.assertEqual(legacy[3], ["sales", "upsell_1", "thank_you"])
        self.assertEqual(legacy[5], ["sales", "upsell_1", "upsell_2", "downsell_1", "thank_you"])
        self.assertEqual(legacy[7], ["sales", "checkout", "upsell_1", "upsell_2", "downsell_1", "downsell_2",
                                     "thank_you"])
        with self.assertRaises(ps.PageSetError):
            ps.legacy_page_set(4)

    def test_the_client_reads_their_pages_in_plain_english_with_what_we_chose_marked(self):
        launch = route_launch("folded_levels", EXTRAS[-1])
        text = ps.plain_summary(ps.build_page_set(launch))
        self.assertIn("Your funnel has 7 pages", text)
        self.assertIn("  3. Order Form / Checkout (design only; the real order form is installed separately)", text)
        self.assertIn("To confirm with you:", text)
        self.assertIn("we suggested Signature Landing Page and Signature Sales Page", text)
        self.assertNotIn("To confirm", ps.plain_summary(ps.build_page_set(launch, landing_pages=["sales"])))
        d2 = ps.plain_summary(ps.build_page_set(route_launch("multiple_options", EXTRAS[-1]),
                                                landing_pages=["sales"], extra_pages=["downsell_2"]))
        self.assertIn("Downsell 2 (design only)", d2)

    def test_lane_plan_runs_every_lane_side_by_side_the_landing_lane_included(self):
        got = ps.build_page_set(route_launch("multiple_options", EXTRAS[-1]), landing_pages=["landing", "sales"],
                                extra_pages=["downsell_2"])
        plan = ps.lane_plan(got)
        self.assertEqual(list(plan), ["parallel"])
        self.assertEqual([l["lane"] for l in plan["parallel"]],
                         ["landing", "product_selection", "checkout", "upsell_1", "upsell_2", "downsell_1",
                          "downsell_2", "thank_you"])
        landing = plan["parallel"][0]
        self.assertEqual(landing["pages"], ["landing", "sales"])
        self.assertEqual(landing["image_estimate"], 4 * 15 + 4 * 12)


class Deliverables(unittest.TestCase):
    def make_run(self, page_key, skip=(), render=True):
        run = Path(tempfile.mkdtemp())
        slug = ps.slug_of(page_key)
        for d in ps.deliverables_for(page_key):
            if d["id"] in skip or (d["needs"] == "render" and not render):
                continue
            target = run / d["glob"].replace("*", "01")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(d["id"].encode())
        return run

    def test_a_complete_run_has_every_deliverable(self):
        run = self.make_run("upsell_1")
        got = ps.check_deliverables("upsell_1", run, rendered=True)
        self.assertTrue(got["complete"], got)
        self.assertEqual(len(got["present"]), len(ps.page_types()["deliverables"]))

    def test_a_stub_run_has_the_images_but_is_never_called_complete(self):
        run = self.make_run("checkout", render=False)
        got = ps.check_deliverables("checkout", run, rendered=False)
        self.assertTrue(got["images_complete"])
        self.assertFalse(got["complete"])
        self.assertEqual(got["missing"], [])
        self.assertEqual(len(got["render_pending"]), 5)

    def test_a_missing_mobile_mockup_is_named(self):
        run = self.make_run("sales", skip=("mobile_mockup_sections",))
        got = ps.check_deliverables("sales", run, rendered=True)
        self.assertEqual(got["missing"], ["mobile_mockup_sections"])
        self.assertFalse(got["images_complete"])
        self.assertFalse(got["complete"])

    def test_a_paid_run_that_lost_its_pdfs_is_missing_them_not_pending(self):
        run = self.make_run("thank_you", render=False)
        got = ps.check_deliverables("thank_you", run, rendered=True)
        self.assertEqual(len(got["missing"]), 5)

    def test_design_artifacts_lists_every_file_with_a_hash(self):
        run = self.make_run("downsell_2")
        (run / "visual-mockup").mkdir(exist_ok=True)
        (run / "visual-mockup" / "stage-executor-record.json").write_text("{}", encoding="utf-8")
        arts = ps.design_artifacts("downsell_2", run, relative=True)
        self.assertEqual(len(arts), len(ps.page_types()["deliverables"]) + 1)
        self.assertTrue(all(len(a["sha256"]) == 64 and not a["path"].startswith("/") for a in arts))
        self.assertEqual([a["path"] for a in arts], sorted(a["path"] for a in arts))


class ImageInputs(unittest.TestCase):
    def write(self, **over):
        doc = {"design_style": "B", "brand_file": "/x/brand.json", "brand_owner": "Acme", "image_cap": 40,
               "image_provider": "stub"}
        doc.update(over)
        path = Path(tempfile.mkdtemp()) / "image_inputs.json"
        path.write_text(json.dumps({k: v for k, v in doc.items() if v != "__drop__"}), encoding="utf-8")
        return path

    def test_a_valid_stub_file_loads_and_never_allows_paid(self):
        got = ps.load_image_inputs(self.write())
        self.assertEqual((got["image_provider"], got["allow_paid"]), ("stub", False))

    def test_the_paid_provider_needs_the_clients_recorded_approval(self):
        with self.assertRaises(ps.PageSetError) as cm:
            ps.load_image_inputs(self.write(image_provider="kie"))
        self.assertIn("paid_render_approval_ref", str(cm.exception))
        got = ps.load_image_inputs(self.write(image_provider="kie", paid_render_approval_ref="APPR-PAID-9"))
        self.assertTrue(got["allow_paid"])
        got = ps.load_image_inputs(self.write(image_provider="kie", test_only=True))
        self.assertFalse(got["allow_paid"])

    def test_agnes_is_refused_by_name(self):
        with self.assertRaises(ps.PageSetError) as cm:
            ps.load_image_inputs(self.write(image_provider="agnes"))
        self.assertIn("agnes", str(cm.exception))

    def test_bad_values_are_refused_plainly(self):
        for over, needle in (({"design_style": "D"}, "design_style"), ({"image_cap": -1}, "image_cap"),
                             ({"image_cap": True}, "image_cap"), ({"brand_owner": "__drop__"}, "brand_owner"),
                             ({"brand_file": ""}, "brand_file"), ({"surprise": 1}, "unknown key")):
            with self.subTest(over=over), self.assertRaises(ps.PageSetError) as cm:
                ps.load_image_inputs(self.write(**over))
            self.assertIn(needle, str(cm.exception))

    def test_a_missing_design_style_is_allowed_it_means_ask_the_client(self):
        self.assertIsNone(ps.load_image_inputs(self.write(design_style=None))["design_style"])

    def test_fill_args_never_overrides_a_flag_the_caller_typed(self):
        class A:
            brand_owner, image_cap, design_style = "Typed", None, None
        a = A()
        ps.fill_args(a, {"brand_owner": "FromFile", "image_cap": 0, "design_style": "C"},
                     {"brand_owner": "brand_owner", "image_cap": "image_cap", "design_style": "design_style"})
        self.assertEqual((a.brand_owner, a.image_cap, a.design_style), ("Typed", 0, "C"))

    def test_selection_inputs_match_what_skill_78_requires(self):
        got = ps.selection_inputs(ps.load_image_inputs(self.write()), "/x/route-graph.json")
        for key in ("route_graph", "brand_file", "brand_owner", "image_cap"):
            self.assertTrue(got[key] not in (None, ""), key)


class FoldedLevelsAreALaunchShape(unittest.TestCase):
    def test_the_validator_accepts_folded_levels_with_two_or_more_mains(self):
        launch = copy.deepcopy(LAUNCH_EXAMPLE)
        launch["journey_mode"] = "folded_levels"
        self.assertEqual(vlp.validate_launch(launch), [])

    def test_folded_levels_with_one_main_is_refused(self):
        launch = copy.deepcopy(LAUNCH_EXAMPLE)
        launch["journey_mode"] = "folded_levels"
        launch["offers"] = [o for o in launch["offers"] if o["offer_id"] != "MAIN-B" and o["offer_id"] != "MAIN-C"]
        self.assertTrue(any("folded_levels requires at least two" in f for f in vlp.validate_launch(launch)))

    def test_all_three_schema_copies_name_folded_levels(self):
        for rel in ("49-signature-funnel/schema/launch.schema.json",
                    "shared-utils/signature_launch/domain/launch.schema.json",
                    "71-blackceo-signature-page/references/launch.schema.json"):
            doc = json.loads((REPO / rel).read_text(encoding="utf-8"))
            self.assertIn("folded_levels", doc["properties"]["journey_mode"]["enum"], rel)

    def test_the_route_compiler_gives_folded_levels_no_selection_node(self):
        launch = copy.deepcopy(LAUNCH_EXAMPLE)
        launch["journey_mode"] = "folded_levels"
        self.assertNotIn("product_selection", [n["role"] for n in clr.compile_route(launch)["nodes"]])


if __name__ == "__main__":
    unittest.main()
