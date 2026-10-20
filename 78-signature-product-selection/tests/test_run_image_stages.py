#!/usr/bin/env python3
"""The order page's wireframes and mockups: manuscript, slots, and the call into Skill 71.

Free: the provider is always the stub (or a preflight), so no network and no spend. The Skill 71
tree and the Skill 49 example config are siblings of this skill in the repository; where they are
absent (a lone install of Skill 78) the cases that need them skip.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parent
S71 = REPO / "71-blackceo-signature-page"
S49_CONFIG = REPO / "49-signature-funnel" / "launch-adapters.example.json"
GOLDEN = ROOT / "fixtures" / "golden-three-option"
PY = sys.executable
sys.path.insert(0, str(ROOT / "scripts"))

import emit_section_manuscript as ems  # noqa: E402
import run_image_stages as ris  # noqa: E402
from build_selection_plan import SELF_TEST_LAUNCH, build_plan  # noqa: E402

needs71 = unittest.skipUnless(S71.is_dir(), "Skill 71 is not beside this skill")
PLAN = json.loads((GOLDEN / "plan.json").read_text())


class ManuscriptTests(unittest.TestCase):
    def test_five_sections_one_button_per_package_and_only_plan_facts(self):
        text, manifest = ems.build(PLAN)
        heads = [l for l in text.splitlines() if l.startswith("## Section")]
        self.assertEqual(heads, [f"## Section {i}: {n}" for i, n in ems.SECTION_NAMES.items()])
        self.assertEqual(text.count("[CTA BUTTON:"), 3)
        for offer in PLAN["offers_in_order"]:
            self.assertIn(f"[CTA BUTTON: {offer['cta']}]", text)
            self.assertIn(offer["display_name"], text)
        for fact in ("$97.00, one time.", "$197.00, one time.", "$497.00 total, paid as: $248.50 today, $248.50 in 30 days.",
                     "Not included: Private review sessions are not included",
                     "Recommended for founders who need individual feedback.",
                     "TEST ONLY: Can I change packages later?", "TEST ONLY: This page collects no payment details."):
            self.assertIn(fact, text)
        self.assertEqual(manifest["authored"], {"bridge_headline": False, "how_to_choose": False})
        self.assertEqual(manifest["sections"], ["1", "2", "3", "4", "5"])

    def test_authored_sentences_win_and_are_recorded(self):
        text, manifest = ems.build(PLAN, {"bridge_headline": "Pick your plan", "how_to_choose": "Start small or go deep"})
        self.assertIn("Pick your plan.", text)
        self.assertIn("Start small or go deep.", text)
        self.assertEqual(manifest["authored"], {"bridge_headline": True, "how_to_choose": True})

    def test_a_declined_single_offer_plan_makes_no_page(self):
        single = build_plan(dict(SELF_TEST_LAUNCH, journey_mode="single_simple", offers=SELF_TEST_LAUNCH["offers"][:1]))
        with self.assertRaises(ValueError):
            ems.build(single)

    @needs71
    def test_it_matches_skill_71s_fixture_and_passes_71s_spec(self):
        text, _ = ems.build(PLAN)
        fixture = S71 / "tests" / "fixtures" / "copy_examples" / "product-selection-path-b.md"
        self.assertEqual(text, fixture.read_text(encoding="utf-8"), "regenerate the 71 fixture from this emitter")
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            ems.write(GOLDEN / "plan.json", run)
            proc = subprocess.run([PY, str(S71 / "scripts" / "validate_copy_structure.py"), str(run), "--spec",
                                   str(S71 / "references" / "copy-specs" / "product-selection-v1.json")],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("RESULT: PASS", proc.stdout)


class SlotTests(unittest.TestCase):
    def test_one_plate_per_package_in_card_order_by_design_style(self):
        a = ris.package_slots(PLAN, "A")["3"]
        b = ris.package_slots(PLAN, "B")["3"]
        c = ris.package_slots(PLAN, "C")["3"]
        self.assertEqual([s["slot_id"] for s in a], ["PKG-1", "PKG-2", "PKG-3"])
        self.assertTrue(all(s["aspect_ratio"] == "4:3" and "mask" not in s for s in a))
        self.assertTrue(all(s["aspect_ratio"] == "1:1" and s["mask"] == "circle" for s in b))
        self.assertEqual([s.get("mask") for s in c], ["circle", None, None])  # style C: at most one circle in three
        self.assertIn("TEST ONLY Essential", a[0]["art_direction"])


class Fixture(unittest.TestCase):
    """A launch, request, route graph and brand file that agree with each other, on the bundled test brand."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        brand = (S71 / "assets" / "brand" / "blackceo-brand.json").read_bytes()
        launch = json.loads((GOLDEN / "launch.json").read_text())
        ident = {k: launch[k] for k in ("tenant_id", "location_id", "launch_id", "revision")}
        graph = (json.dumps({
            "schema_version": "1.0", **ident,
            "nodes": [{"page_id": "page-landing-1", "role": "landing"},
                      {"page_id": "page-select-1", "role": "product_selection"},
                      {"page_id": "page-thanks-1", "role": "thank_you"}],
            "edges": [{"from": "page-landing-1", "event": "interest_submitted", "to": "page-select-1",
                       "guard": "verified_native_contact_submit"},
                      {"from": "page-select-1", "event": "selection_validated", "to": "page-thanks-1",
                       "guard": "selection_complete"}],
            "pending_failed_payment_behavior": "retain_current_purchase_state_until_resolved_or_explicit_decline",
            "test_only": True}, indent=2) + "\n").encode()
        ghash, bhash = hashlib.sha256(graph).hexdigest(), hashlib.sha256(brand).hexdigest()
        launch.update(brand_ref="assets/brand/blackceo-brand.json", brand_hash=bhash,
                      route_graph_ref="route-graph.json", route_graph_hash=ghash)
        request = {"schema_version": "1.0", **ident, "request_id": "req-order-page", "page_id": "page-select-1",
                   "page_role": "product_selection", "assigned_skill": 78, "approval_ref": launch["plan_approval_ref"],
                   "input_hash": "in-hash-1", "brand_ref": launch["brand_ref"], "brand_hash": bhash,
                   "route_graph_ref": "route-graph.json", "route_graph_hash": ghash,
                   "offer_refs": [o["offer_id"] for o in launch["offers"] if o["slot"] == "main"],
                   "copy_profile": "standard", "allowed_write_target": "local_only", "test_only": True}
        (self.dir / "brand.json").write_bytes(brand)
        (self.dir / "route-graph.json").write_bytes(graph)
        (self.dir / "launch.json").write_text(json.dumps(launch, indent=2))
        (self.dir / "page-request.json").write_text(json.dumps(request, indent=2))
        (self.dir / "plan.json").write_text((GOLDEN / "plan.json").read_text())
        self.inputs = {"route_graph": str(self.dir / "route-graph.json"), "brand_file": str(self.dir / "brand.json"),
                       "brand_owner": "blackceo", "image_cap": "40", "design_style": "B",
                       "model": "STUB-NO-MODEL", "test_run": True}
        self.write_inputs()

    def write_inputs(self):
        (self.dir / "inputs.json").write_text(json.dumps(self.inputs))

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, *extra, inputs="inputs.json"):
        return subprocess.run(
            [PY, str(ROOT / "scripts" / "run_image_stages.py"), "--plan", str(self.dir / "plan.json"),
             "--request", str(self.dir / "page-request.json"), "--run-dir", str(self.dir / "run"),
             "--launch-record", str(self.dir / "launch.json"), "--inputs",
             inputs if inputs == "none" else str(self.dir / inputs), "--skill71-root", str(S71), *extra],
            capture_output=True, text=True)


@needs71
class RunTests(Fixture):
    def test_preflight_admits_the_page_and_checks_every_stage_with_no_provider_call(self):
        proc = self.call("--preflight")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):
            self.assertIn(f"PREFLIGHT_CTA {stage} 3 -> Choose TEST ONLY Essential", proc.stdout)
        self.assertIn("PREFLIGHT_SECTIONS copy_version=product-selection sections=5", proc.stdout)
        run = self.dir / "run"
        intake = json.loads((run / "intake.json").read_text())
        self.assertEqual((intake["copy_version"], intake["page_version"], intake["design_style"]),
                         ("product-selection", "product-selection", "B"))
        self.assertEqual(intake["launch"]["page_role"], "product_selection")
        self.assertEqual(intake["launch"]["assigned_skill"], 78)
        self.assertFalse((run / "desktop-wireframe" / "section-01.png").exists())  # nothing was generated

    def test_stub_run_makes_the_stage_folders_and_the_board_role_is_product_selection(self):
        proc = self.call()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        run = self.dir / "run"
        for n in range(1, 6):
            self.assertTrue((run / "desktop-wireframe" / f"section-{n:02d}.png").is_file())
            self.assertTrue((run / "mobile-tablet" / f"section-{n:02d}.png").is_file())
            self.assertTrue((run / "visual-mockup" / "desktop" / f"part-{n:02d}.png").is_file())
            self.assertTrue((run / "visual-mockup" / "mobile" / f"part-{n:02d}.png").is_file())
        record = json.loads((run / "visual-mockup" / "stage-executor-record.json").read_text())
        self.assertEqual(record["provider"], "stub")
        slots = json.loads((run / "slots.json").read_text())["3"]
        self.assertEqual([s["slot_id"] for s in slots], ["PKG-1", "PKG-2", "PKG-3"])
        sys.path.insert(0, str(S71 / "scripts"))
        import design_board
        self.assertEqual(design_board.declared_role(run), "product_selection")

    def test_inputs_none_is_refused_and_makes_no_images(self):
        proc = self.call(inputs="none")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("REFUSED", proc.stdout)
        self.assertFalse((self.dir / "run").exists())

    def test_refusals(self):
        self.inputs.pop("brand_owner")
        self.write_inputs()
        proc = self.call()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("missing brand_owner", proc.stdout)
        self.inputs["brand_owner"] = "blackceo"
        self.write_inputs()
        (self.dir / "plan.json").write_text(json.dumps({"outcome": "declined_single_offer"}))
        proc = self.call()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("no order page is built", proc.stdout)
        self.assertFalse((self.dir / "run").exists())

    def test_a_stale_route_graph_is_refused_before_anything_is_written(self):
        (self.dir / "route-graph.json").write_text("{}\n")
        proc = self.call()
        self.assertEqual(proc.returncode, 2)
        self.assertFalse((self.dir / "run" / "production-request-desktop-wireframe.json").exists())

    def test_the_stage_executor_refuses_final_mockups_without_the_design_board_approval(self):
        self.inputs["stages"] = ["final-mockups"]
        self.write_inputs()
        proc = self.call()
        self.assertEqual(proc.returncode, 2)
        self.assertFalse((self.dir / "run" / "final-mockups").exists())

    def test_the_wrong_page_version_for_the_role_is_refused_by_the_service(self):
        proc = subprocess.run([PY, str(S71 / "scripts" / "shared_page_service.py"),
                               "--request", str(self.dir / "page-request.json"), "--run-dir", str(self.dir / "r2"),
                               "--page-version", "standard", "--brand-owner", "blackceo", "--image-cap", "40",
                               "--brand-file", str(self.dir / "brand.json"), "--launch-record", str(self.dir / "launch.json"),
                               "--route-graph", str(self.dir / "route-graph.json"), "--validation-only"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("does not fit page_role", proc.stdout)


@unittest.skipUnless(S71.is_dir() and S49_CONFIG.is_file(), "Skill 71 and the Skill 49 example config are not beside this skill")
class ShippedAdapterTests(Fixture):
    """The product_selection command Skill 49 ships, run exactly as dispatch runs it."""

    def command(self, inputs):
        spec = json.loads(S49_CONFIG.read_text())["adapters"]["product_selection"]
        work = self.dir / "work"
        work.mkdir(exist_ok=True)
        self.result = work / "result.json"
        return [part.replace("/path/to", str(REPO))
                .replace("<per-launch: approved launch record JSON>", str(self.dir / "launch.json"))
                .replace("<per-launch: order page image inputs JSON>", inputs)
                .replace("{request}", str(self.dir / "page-request.json")).replace("{result}", str(self.result))
                .replace("{work_dir}", str(work)) for part in spec["command"]]

    def test_dispatch_makes_the_order_page_images_before_it_writes_the_page_result(self):
        proc = subprocess.run(self.command(str(self.dir / "inputs.json")), capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        images = self.dir / "work" / "order-page-images"
        self.assertTrue((images / "visual-mockup" / "mobile" / "part-05.png").is_file())
        result = json.loads(self.result.read_text())
        self.assertEqual((result["page_id"], result["status"]), ("page-select-1", "locally_verified"))
        self.assertNotIn("--allow-paid", " ".join(self.command("x")))  # dispatch never spends
        self.assertLessEqual((images / "intake.json").stat().st_mtime, self.result.stat().st_mtime)

    def test_failing_images_leave_no_page_result(self):
        self.inputs["brand_owner"] = ""
        self.write_inputs()
        proc = subprocess.run(self.command(str(self.dir / "inputs.json")), capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(self.result.exists())

    def test_inputs_none_leaves_no_page_result(self):
        proc = subprocess.run(self.command("none"), capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(self.result.exists())
        self.assertFalse((self.dir / "work" / "order-page-images").exists())


if __name__ == "__main__":
    unittest.main()
