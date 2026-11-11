#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_page_set.py - every page type in every funnel shape, with its designs, and the shared image
inputs. Run: python3 test_page_set.py (from scripts/). No network, no provider, no paid call.
"""
import copy
import fnmatch
import itertools
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compile_launch_route as clr  # noqa: E402
import page_set as ps  # noqa: E402
import page_swarm as sw  # noqa: E402
import validate_launch_plan as vlp  # noqa: E402

REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "71-blackceo-signature-page" / "scripts"))
import deliverable_labels as labels  # noqa: E402
import copy_forms  # noqa: E402
import page_kinds  # noqa: E402
import role_spec  # noqa: E402
sys.path.insert(0, str(REPO / "83-black-friday-launcher"))
from launcher_core import page_designs  # noqa: E402

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
    approval = {"schema_version": "1.0", "approval_id": "APPR-1", "kind": "launch_plan_build",
                "plan_hash": vlp.plan_document_hash(launch), "client_identity": "client-1",
                "source_message_ref": "m-1", "scope": ["launch_plan_build"],
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "revoked": False,
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
            self.assertEqual(labels.pdf_name(role, "mobile", "final-mockups"),
                             ps.slug_of(key) + "_MOBILE_MOCKUPS-FINAL.pdf")
            self.assertEqual(labels.board_name(role, "combined", "visual-mockup"),
                             ps.slug_of(key) + "_DESKTOP-and-MOBILE_MOCKUP-VISUAL-BOARD")

    def test_labeled_globs_match_the_file_names_skill_71_writes_and_the_launcher_classifies(self):
        """U-designs-seam: each section-image deliverable names the labeled client copy (FINAL for mockups)."""
        stage_of = {"wireframe": None, "mockup": "final-mockups"}
        for key, page in ps.page_types()["pages"].items():
            for d in ps.deliverables_for(key):
                if "labeled_glob" not in d:
                    continue
                stage = stage_of[d["kind"]] or d["stage"]
                name = labels.image_name(page["label_role"], d["device"], stage, 3, 8, "Offer and price")
                with self.subTest(page=key, deliverable=d["id"]):
                    self.assertTrue(fnmatch.fnmatchcase(f"{labels.folder(d['device'], stage)}/{name}",
                                                        d["labeled_glob"].split("/", 1)[1]), (name, d["labeled_glob"]))
                    self.assertTrue(d["labeled_glob"].startswith("review-pdfs/"))
                    self.assertTrue(page_designs.classify(name), name)
        for key in ps.page_types()["pages"]:  # the render deliverables are the FINAL PDFs and the boards
            pdfs = {d["id"]: d["glob"] for d in ps.deliverables_for(key) if d["id"].endswith("_pdf")}
            self.assertEqual(pdfs["desktop_mockup_pdf"], f"review-pdfs/{ps.slug_of(key)}_DESKTOP_MOCKUPS-FINAL.pdf")
            for glob in pdfs.values():
                self.assertTrue(page_designs.classify(glob.rsplit("/", 1)[1]), glob)

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
    def make_run(self, page_key, skip=(), render=True, counts=None, provider=None):
        """A run folder with one image per section in every image kind (counts overrides a kind's
        number) and one file per render kind; provider writes a stage record per stage folder."""
        run = Path(tempfile.mkdtemp())
        for d in ps.deliverables_for(page_key):
            if d["id"] in skip or (d["needs"] == "render" and not render):
                continue
            n = (counts or {}).get(d["id"], ps.section_counts(page_key)[0]) if d["needs"] == "images" else 1
            for key in ("glob", "labeled_glob"):  # the raw proof, and the labeled client copy a paid run adds
                if key not in d or (key == "labeled_glob" and not render):
                    continue
                for i in range(1, n + 1):
                    target = run / d[key].replace("*", f"{i:02d}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(d["id"].encode())
        for stage in ((provider or {}).get("stages") or ()):
            (run / stage).mkdir(exist_ok=True)
            (run / stage / "stage-executor-record.json").write_text(
                json.dumps({"provider": provider["provider"]}), encoding="utf-8")
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

    def test_a_paid_run_before_final_mockups_closed_lacks_the_labeled_final_copies_and_is_not_complete(self):
        run = self.make_run("upsell_1")
        for path in (run / "review-pdfs").rglob("*_mockup-final_*.png"):  # final-mockups has not closed yet
            path.unlink()
        got = ps.check_deliverables("upsell_1", run, rendered=True)
        self.assertEqual(got["labeled_missing"], ["desktop_mockup_sections", "mobile_mockup_sections"])
        self.assertEqual(got["missing"], [])
        self.assertFalse(got["complete"])
        names = {Path(f).name for f in got["files"]}
        self.assertTrue(any("_desktop_wireframe_s01-of-" in n for n in names))
        self.assertFalse(any("mockup-final" in n for n in names))
        self.assertEqual(ps.check_deliverables("upsell_1", run, rendered=False)["labeled_missing"], [])

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
        self.assertEqual(len(arts), sum(1 for f in run.rglob("*") if f.is_file()))
        self.assertTrue(all(len(a["sha256"]) == 64 and not a["path"].startswith("/") for a in arts))
        self.assertEqual([a["path"] for a in arts], sorted(a["path"] for a in arts))


class SectionCountsPerKind(unittest.TestCase):  # STR-15
    make_run = Deliverables.make_run

    def test_one_of_fifteen_landing_section_images_fails_the_check(self):
        run = self.make_run("landing", counts={"desktop_wireframe_sections": 1})
        got = ps.check_deliverables("landing", run, rendered=True)
        self.assertEqual(got["wrong_count"], ["desktop_wireframe_sections"])
        self.assertEqual(got["section_counts"]["desktop_wireframe_sections"], 1)
        self.assertIn("desktop_wireframe_sections", got["missing"])
        self.assertFalse(got["images_complete"])
        self.assertFalse(got["complete"])

    def test_a_full_set_of_the_pages_own_form_passes(self):
        for key in ps.page_types()["pages"]:
            with self.subTest(page=key):
                got = ps.check_deliverables(key, self.make_run(key), rendered=True)
                self.assertTrue(got["complete"], got)
                self.assertEqual(set(got["section_counts"].values()), {ps.section_counts(key)[0]})

    def test_a_set_from_the_other_copy_form_or_a_mixed_set_fails(self):
        every = {i: 12 for i in ("desktop_wireframe_sections", "mobile_wireframe_sections",
                                 "desktop_mockup_sections", "mobile_mockup_sections")}
        landing = ps.check_deliverables("landing", self.make_run("landing", counts=every), rendered=True)
        self.assertEqual(len(landing["wrong_count"]), 4, "the opt-in page has only the 15 section form")
        sales_long = {i: 15 for i in every}
        self.assertTrue(ps.check_deliverables("sales", self.make_run("sales", counts=sales_long),
                                              rendered=True)["complete"], "the sales page has both forms")
        mixed = dict(sales_long, mobile_mockup_sections=12)
        got = ps.check_deliverables("sales", self.make_run("sales", counts=mixed), rendered=True)
        self.assertEqual(got["wrong_count"], ["mobile_mockup_sections"])
        strict = ps.check_deliverables("sales", self.make_run("sales", counts=sales_long), rendered=True,
                                       long_form=False)
        self.assertEqual(len(strict["wrong_count"]), 4)

    def test_page_types_counts_equal_the_skill_71_spec_sequence_lengths(self):  # drift test
        pages = ps.page_types()["pages"]
        structures = json.loads((REPO / "71-blackceo-signature-page" / "references" /
                                 "page-structures.json").read_text(encoding="utf-8"))["roles"]
        expect = {
            "landing": (len(page_kinds.sequence("opt_in", "long-form")), None),
            "sales": (len(page_kinds.sequence("sales", "standard")), len(page_kinds.sequence("sales", "long-form"))),
            "downsell_1": (len(structures["downsell_1"]["sequence"]), None),
            "downsell_2": (len(structures["downsell_1"]["sequence"]), None),
        }
        for key, role in (("product_selection", "product_selection"), ("checkout", "checkout"),
                          ("upsell_1", "upsell_1"), ("upsell_2", "upsell_2"), ("thank_you", "thank_you")):
            spec = role_spec.load(role)
            if spec is None:
                spec = copy_forms.load_spec(copy_forms.form_for_role(role))
            expect[key] = (len(spec["sequence"]), None)
        self.assertEqual(set(expect), set(pages), "every page type has a 71 sequence to compare with")
        for key, (short, long_) in expect.items():
            self.assertEqual(pages[key]["sections"], short, key)
            self.assertEqual(pages[key].get("long_form_sections"), long_, key)


class OfferedCeilingAndDryRun(unittest.TestCase):  # IMG-04
    def nine_page_launch(self):
        launch = route_launch("multiple_options", EXTRAS[-1])
        return ps.build_page_set(launch, landing_pages=["landing", "sales"], extra_pages=["downsell_2"])

    def requests(self, page_set):
        return [{"page_role": r} for r in dict.fromkeys(p["request_role"] for p in page_set["pages"])]

    def test_the_offered_ceiling_is_the_sum_of_the_pages_image_estimates(self):
        got = self.nine_page_launch()
        offered = ps.offered_image_ceilings(got)
        self.assertEqual(len(got["pages"]), 9)
        self.assertEqual(offered["total"], sum(p["image_estimate"] for p in got["pages"]))
        self.assertEqual([x["page_key"] for x in offered["per_page"]], [p["page_key"] for p in got["pages"]])
        self.assertEqual(offered["options"][-1]["image_cap"], offered["total"])
        self.assertEqual(offered["options"][0]["builds"], ["landing"])
        self.assertGreater(offered["options"][0]["image_cap"], 36, "the old largest guided cap (12/24/36) never fit")
        caps = [x["image_cap"] for x in offered["options"]]
        self.assertEqual(caps, sorted(caps))

    def test_the_estimate_is_the_image_stages_per_section_not_a_typed_number(self):
        self.assertEqual(ps.images_per_section(), 4)
        self.assertEqual(ps.image_estimate("landing"), 4 * 15)
        self.assertEqual(ps.image_estimate("sales", long_form=True), 4 * 15)

    def test_a_dry_run_reports_the_lanes_a_guided_cap_would_skip_with_nothing_started(self):
        lanes = ps.lane_plan(self.nine_page_launch())["parallel"]
        report = sw.dry_run_cap(lanes, 36)
        self.assertFalse(report["fits"])
        skipped = [x["lane"] for x in report["would_skip"]]
        self.assertEqual(skipped[0], "landing", "the landing and sales pages go first today")
        self.assertIn("upsell_1", skipped)
        self.assertLessEqual(report["reserved"], 36)
        total = ps.offered_image_ceilings(self.nine_page_launch())["total"]
        self.assertTrue(sw.dry_run_cap(lanes, total)["fits"])
        self.assertFalse(sw.dry_run_cap(lanes, total - 1)["fits"])

    def run_execute(self, provider, cap, strict):
        got, started = self.nine_page_launch(), []
        inputs = {"design_style": "B", "brand_file": "/x/b.json", "brand_owner": "Acme", "image_cap": cap,
                  "image_provider": provider, "allow_paid": False}

        def executor(request, lane=None):
            started.append(lane or request["page_role"])
            return {}
        out = sw.execute(self.requests(got), executor, page_set=got, out_dir=None, launch_id="L-1",
                         image_inputs=inputs, strict_cap=strict)
        return out, started

    def test_a_cap_too_small_for_the_page_set_refuses_before_any_lane_starts_stub_or_paid(self):
        for provider in ("stub", "kie"):
            started = []
            got = self.nine_page_launch()
            inputs = {"design_style": "B", "brand_file": "/x/b.json", "brand_owner": "Acme", "image_cap": 36,
                      "image_provider": provider, "allow_paid": False}
            with self.subTest(provider=provider), self.assertRaises(sw.SwarmError) as cm:
                sw.execute(self.requests(got), lambda r, lane=None: started.append(r) or {}, page_set=got,
                           out_dir=None, launch_id="L-1", image_inputs=inputs, strict_cap=True)
            self.assertIn("landing", str(cm.exception))
            self.assertIn("Nothing was started", str(cm.exception))
            self.assertEqual(started, [])

    def test_the_stub_run_report_names_the_lanes_the_paid_run_would_skip(self):
        out, started = self.run_execute("stub", 36, strict=False)
        preview = out["swarm"]["cap_preview"]
        self.assertFalse(preview["fits"])
        self.assertEqual(preview["would_skip"][0]["lane"], "landing")
        self.assertEqual(set(out["swarm"]["statuses"].values()), {"ok"}, "the free stub still builds every lane")
        total = ps.offered_image_ceilings(self.nine_page_launch())["total"]
        out, _ = self.run_execute("kie", total, strict=True)
        self.assertTrue(out["swarm"]["cap_preview"]["fits"])


class UpsellLanesDoNotWaitForTheLanding(unittest.TestCase):  # UPS-18
    def test_parallel_upsell_lanes_run_with_no_file_from_the_landing_lane(self):
        got = ps.build_page_set(route_launch("multiple_options", EXTRAS[-1]), landing_pages=["landing", "sales"])
        out, seen = Path(tempfile.mkdtemp()), []
        landing_file = out / "result-landing.json"

        def executor(request, lane=None):
            seen.append(request["page_role"])
            self.assertFalse(landing_file.exists(), "no lane reads or waits for a landing result file")
            return {}
        requests = [{"page_role": r} for r in dict.fromkeys(p["request_role"] for p in got["pages"])]
        result = sw.execute(requests, executor, page_set=got, out_dir=out, launch_id="L-1", workers=4)
        self.assertEqual(set(result["swarm"]["statuses"].values()), {"ok"})
        self.assertIn("upsell_1", seen)
        self.assertIn("upsell_2", seen)
        self.assertFalse(landing_file.exists())
        self.assertEqual(list(ps.lane_plan(got)), ["parallel"], "one parallel group, no landing-first stage")


class ProviderOnEveryArtifact(unittest.TestCase):  # UPS-23
    make_run = Deliverables.make_run

    def test_every_artifact_names_the_provider_that_drew_the_run(self):
        stages = ("desktop-wireframe", "mobile-tablet", "visual-mockup")
        for provider in ("stub", "kie"):
            run = self.make_run("upsell_1", provider={"provider": provider, "stages": stages})
            arts = ps.design_artifacts("upsell_1", run, relative=True, with_provider=True)
            with self.subTest(provider=provider):
                self.assertTrue(arts)
                self.assertEqual({a["provider"] for a in arts}, {provider}, "PDFs and boards take the run's")

    def test_one_stub_stage_marks_the_files_outside_the_stages_as_stub(self):
        run = self.make_run("upsell_1", provider={"provider": "kie", "stages": ("desktop-wireframe",)})
        (run / "visual-mockup" / "stage-executor-record.json").write_text(
            json.dumps({"provider": "stub"}), encoding="utf-8")
        by_path = {a["path"]: a["provider"] for a in ps.design_artifacts("upsell_1", run, relative=True,
                                                                       with_provider=True)}
        self.assertEqual(by_path["desktop-wireframe/section-01.png"], "kie")
        self.assertEqual(by_path["visual-mockup/desktop/part-01.png"], "stub")
        self.assertEqual(by_path["review-pdfs/upsell-1_DESKTOP_WIREFRAMES.pdf"], "stub")

    def test_a_run_with_no_stage_record_names_no_provider_rather_than_guessing(self):
        arts = ps.design_artifacts("upsell_1", self.make_run("upsell_1"), relative=True, with_provider=True)
        self.assertEqual({a["provider"] for a in arts}, {None})

    def test_the_default_form_stays_path_and_hash_only_for_the_page_result_schema(self):
        run = self.make_run("upsell_1", provider={"provider": "stub", "stages": ("desktop-wireframe",)})
        self.assertEqual({tuple(sorted(a)) for a in ps.design_artifacts("upsell_1", run)}, {("path", "sha256")})

    def test_a_non_test_package_with_a_stub_upsell_run_fails_the_design_gate(self):
        run = self.make_run("upsell_1", provider={"provider": "stub", "stages": ("desktop-wireframe",)})
        root = Path(tempfile.mkdtemp())
        name = "upsell-1_desktop_wireframe_s01-of-08_x.png"
        (root / name).write_bytes(b"x")
        art = next(a for a in ps.design_artifacts("upsell_1", run, relative=True, with_provider=True)
                   if a["path"] == "desktop-wireframe/section-01.png")
        piece = {"role": "upsell_1", "artifacts": [{"path": name, "provider": art["provider"]}]}
        fails = page_designs.design_violations({"pieces": [piece], "test_only": False}, root, spec={})
        self.assertTrue(any("stub provider" in f and f.startswith("AF-LAUNCH-PAGE-DESIGNS") for f in fails), fails)
        fails = page_designs.design_violations({"pieces": [piece], "test_only": True}, root, spec={})
        self.assertFalse(any("stub provider" in f for f in fails))


# 40 pictures at 8 cents each is 320 cents (issue 76: the count travels with the money that justifies it).
MONEY = {"image_cap_minor": 320, "image_currency": "USD", "image_price_minor": 8}


class ImageInputs(unittest.TestCase):
    def write(self, **over):
        doc = {"design_style": "B", "brand_file": "/x/brand.json", "brand_owner": "Acme", "image_cap": 40,
               "image_provider": "stub", "test_only": True}
        doc.update(over)
        path = Path(tempfile.mkdtemp()) / "image_inputs.json"
        path.write_text(json.dumps({k: v for k, v in doc.items() if v != "__drop__"}), encoding="utf-8")
        return path

    def test_a_valid_stub_file_loads_and_never_allows_paid(self):
        got = ps.load_image_inputs(self.write())
        self.assertEqual((got["image_provider"], got["allow_paid"]), ("stub", False))

    def test_the_paid_provider_needs_the_clients_recorded_approval(self):
        with self.assertRaises(ps.PageSetError) as cm:
            ps.load_image_inputs(self.write(image_provider="kie", test_only=False))
        self.assertIn("paid_render_approval_ref", str(cm.exception))
        got = ps.load_image_inputs(self.write(image_provider="kie", paid_render_approval_ref="APPR-PAID-9",
                                             test_only=False, **MONEY))
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

    # ---- issue 76: the money keys travel with the count ---------------------------------------
    def test_the_three_money_keys_are_accepted_and_returned(self):
        got = ps.load_image_inputs(self.write(image_provider="kie", paid_render_approval_ref="APPR-PAID-9", **MONEY))
        self.assertEqual({k: got[k] for k in MONEY}, MONEY)
        for key in MONEY:
            self.assertIn(key, ps.IMAGE_INPUT_KEYS)

    def test_a_count_that_costs_more_than_the_money_is_refused(self):
        for over in ({"image_cap": 41}, {"image_price_minor": 9}, {"image_cap_minor": 319}):
            with self.subTest(over=over), self.assertRaises(ps.PageSetError) as cm:
                ps.load_image_inputs(self.write(**dict(MONEY, **over)))
            self.assertIn("AF-FUN-IMAGE-CAP-MONEY", str(cm.exception))
        self.assertEqual(ps.load_image_inputs(self.write(**MONEY))["image_cap"], 40)  # exactly the money is fine

    def test_a_real_run_with_a_count_and_missing_money_keys_is_refused(self):
        for drop in MONEY:
            with self.subTest(drop=drop), self.assertRaises(ps.PageSetError) as cm:
                ps.load_image_inputs(self.write(**dict(MONEY, test_only=False, **{drop: "__drop__"})))
            self.assertIn("AF-FUN-IMAGE-CAP-MONEY", str(cm.exception))
            self.assertIn(drop, str(cm.exception))
        with self.assertRaises(ps.PageSetError) as cm:  # null is not money either; no test_only key counts as real
            ps.load_image_inputs(self.write(**dict(MONEY, test_only=False, image_price_minor=None)))
        self.assertIn("AF-FUN-IMAGE-CAP-MONEY", str(cm.exception))

    def test_a_file_with_no_test_only_key_is_a_real_run(self):
        doc = {"design_style": "B", "brand_file": "/x/b.json", "brand_owner": "Acme", "image_cap": 4, "image_provider": "stub"}
        path = Path(tempfile.mkdtemp()) / "image_inputs.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(ps.PageSetError) as cm:
            ps.load_image_inputs(path)
        self.assertIn("AF-FUN-IMAGE-CAP-MONEY", str(cm.exception))

    def test_a_practice_run_needs_no_money_keys_and_null_money_is_allowed(self):
        self.assertEqual(ps.load_image_inputs(self.write(test_only=True))["image_cap"], 40)
        got = ps.load_image_inputs(self.write(test_only=True, image_cap_minor=None, image_currency=None,
                                              image_price_minor=None))
        self.assertIsNone(got["image_cap_minor"])

    def test_bad_money_values_are_refused_plainly(self):
        for over in ({"image_cap_minor": True}, {"image_cap_minor": 0}, {"image_cap_minor": "320"},
                     {"image_currency": "usd"}, {"image_price_minor": 0}, {"image_price_minor": 8.5}):
            with self.subTest(over=over), self.assertRaises(ps.PageSetError) as cm:
                ps.load_image_inputs(self.write(**dict(MONEY, **over)))
            self.assertIn("AF-FUN-IMAGE-CAP-MONEY", str(cm.exception))

    def test_a_boolean_is_never_a_whole_number_of_minor_units(self):
        # True is 1 in Python. Each case below would otherwise pass the count-versus-money comparison,
        # so only the boolean check itself refuses it (an image_cap of 0 makes the comparison pass).
        for over in ({"image_cap_minor": True, "image_cap": 0}, {"image_price_minor": True}):
            with self.subTest(over=over), self.assertRaises(ps.PageSetError) as cm:
                ps.load_image_inputs(self.write(**dict(MONEY, **over)))
            self.assertIn("AF-FUN-IMAGE-CAP-MONEY", str(cm.exception))
            self.assertIn("whole number", str(cm.exception))

    def test_the_currency_is_exactly_three_uppercase_letters_and_money_edges_hold(self):
        for cur in ("USDX", "US", "U$D", "US1", 5, ""):
            with self.subTest(cur=cur), self.assertRaises(ps.PageSetError) as cm:
                ps.load_image_inputs(self.write(**dict(MONEY, image_currency=cur)))
            self.assertIn("AF-FUN-IMAGE-CAP-MONEY", str(cm.exception))
        # one minor unit is a real amount, and a count that costs exactly the money is allowed
        self.assertEqual(ps.load_image_inputs(self.write(**dict(MONEY, image_price_minor=1, image_cap=320)))["image_price_minor"], 1)
        # a practice run with only one of the two amounts compares nothing
        for part in ({"image_cap_minor": None}, {"image_price_minor": None}):
            got = ps.load_image_inputs(self.write(**dict(MONEY, test_only=True, **part)))
            self.assertEqual(got["image_cap"], 40)

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
