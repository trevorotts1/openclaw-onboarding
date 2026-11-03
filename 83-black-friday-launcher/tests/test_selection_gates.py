"""Skill 78's content, claim and catalog gates run in the product_selection adapter chain and in `check`.

Runs the real adapter command build_dispatch_config binds (build_selection_plan -> run_image_stages ->
emit_page_result) on the stub provider: no network, no spend. Each case fails on main (no gate in the
chain) and passes here.

  * a claim ("most popular", "only 50 left") in the page copy makes the adapter exit non-zero
  * a test_only offer in a live run fails with S78-TEST-ONLY-IN-PRODUCTION
  * emit_page_result --image-run-dir lists the image run's outputs as artifacts
  * check_rules/claims.py and check_rules/selection.py (the check_package seam)
  * an Elevation launch with levels supplied compares every deliverable; with none the page is refused
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = SKILL_ROOT / "fixtures"
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))

import adapters  # noqa: E402
import substrate  # noqa: E402
from launcher_core import image_plan, intake, launch_bridge, route  # noqa: E402

S78 = substrate.source("78-signature-product-selection")
S71 = substrate.source("71-blackceo-signature-page")
GOLDEN = S78 / "fixtures" / "golden-three-option"
RULES = SKILL_ROOT / "launcher_core" / "check_rules"
sys.path.insert(0, str(S78 / "scripts"))

import emit_section_manuscript as ems  # noqa: E402
from build_selection_plan import build_plan  # noqa: E402
from selection_core import Violation  # noqa: E402
from validate_selection_content import compare_rows, validate_manuscript  # noqa: E402

needs71 = unittest.skipUnless(S71.is_dir(), "Skill 71 is not beside this skill")


def load_rule(name: str):
    spec = importlib.util.spec_from_file_location(f"launcher_core.check_rules.{name}", RULES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Chain(unittest.TestCase):
    """A launch, request, route graph and brand file that agree, and the shipped adapter command for them."""

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
        self.launch = launch
        self.request = {"schema_version": "1.0", **ident, "request_id": "req-order-page", "page_id": "page-select-1",
                        "page_role": "product_selection", "assigned_skill": 78, "approval_ref": launch["plan_approval_ref"],
                        "input_hash": "in-hash-1", "brand_ref": launch["brand_ref"], "brand_hash": bhash,
                        "route_graph_ref": "route-graph.json", "route_graph_hash": ghash,
                        "offer_refs": [o["offer_id"] for o in launch["offers"] if o["slot"] == "main"],
                        "copy_profile": "standard", "allowed_write_target": "local_only", "test_only": True}
        self.inputs = {"route_graph": str(self.dir / "route-graph.json"), "brand_file": str(self.dir / "brand.json"),
                       "brand_owner": "blackceo", "image_cap": "40", "design_style": "B",
                       "model": "STUB-NO-MODEL", "test_run": True}
        (self.dir / "brand.json").write_bytes(brand)
        (self.dir / "route-graph.json").write_bytes(graph)
        self.work = self.dir / "work"
        self.work.mkdir()
        self.result = self.work / "result.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self):
        (self.dir / "launch.json").write_text(json.dumps(self.launch, indent=2))
        (self.dir / "page-request.json").write_text(json.dumps(self.request, indent=2))
        (self.dir / "inputs.json").write_text(json.dumps(self.inputs))

    def copy_json(self, doc):
        path = self.dir / "copy.json"
        path.write_text(json.dumps(doc))
        self.inputs["copy"] = str(path)

    def adapter(self):
        """Run the product_selection command build_dispatch_config binds, exactly as dispatch runs it."""
        self.write()
        files = {}
        for role in ("upsell_1", "upsell_2", "downsell_1"):
            for name in ("copy", "journey", "enrichment"):
                path = self.dir / f"{name}-{role}.json"
                path.write_text("{}")
                files.setdefault(name, {})[role] = path
        bridge = self.dir / "bridge.json"
        bridge.write_text("{}")
        config = adapters.build_dispatch_config(
            work_dir=self.work, launch_record=self.dir / "launch.json", bridge_config=bridge,
            author_session="session-test", image_inputs=self.dir / "inputs.json", **files)
        command = [part.replace("{request}", str(self.dir / "page-request.json"))
                   .replace("{result}", str(self.result)).replace("{work_dir}", str(self.work))
                   for part in config["adapters"]["product_selection"]["command"]]
        return subprocess.run(command, capture_output=True, text=True)

    def emit(self, *extra):
        out = self.dir / "emitted.json"
        proc = subprocess.run([sys.executable, str(S78 / "scripts" / "emit_page_result.py"),
                               str(self.work / "selection-plan.json"), "--output", str(out), "--author-session", "s",
                               "--request", str(self.dir / "page-request.json"), *extra],
                              capture_output=True, text=True)
        return proc, out


@needs71
class AdapterGateTests(Chain):
    def test_clean_copy_passes_the_whole_chain(self):
        proc = self.adapter()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(self.result.read_text())["page_id"], "page-select-1")

    def test_most_popular_in_the_copy_fails_the_adapter_before_anything_is_drawn(self):
        self.copy_json({"bridge_headline": "Our most popular packages"})
        proc = self.adapter()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("S78-UNPROVEN-CLAIM", proc.stdout + proc.stderr)
        self.assertFalse(self.result.exists())
        self.assertFalse((self.work / "order-page-images").exists())  # nothing drawn, nothing spent

    def test_a_scarcity_claim_in_the_copy_fails_the_adapter(self):
        self.copy_json({"how_to_choose": "Only 50 left, so pick now"})
        proc = self.adapter()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("only 50 left", proc.stdout + proc.stderr)
        self.assertFalse(self.result.exists())

    def test_a_claim_in_an_unused_copy_key_is_still_refused(self):
        self.copy_json({"bridge_headline": "Pick a package", "note": "Best value of the year"})
        proc = self.adapter()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("S78-UNPROVEN-CLAIM", proc.stdout + proc.stderr)

    def test_a_test_only_offer_in_a_live_run_fails_the_adapter(self):
        self.launch["test_only"] = False
        self.request["test_only"] = False
        proc = self.adapter()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("S78-TEST-ONLY-IN-PRODUCTION", proc.stdout + proc.stderr)
        self.assertFalse(self.result.exists())

    def test_the_image_step_refuses_a_live_request_over_a_test_launch(self):
        self.request["test_only"] = False  # the page request says live; the plan was built from a test launch
        self.write()
        (self.dir / "plan.json").write_text((GOLDEN / "plan.json").read_text())
        proc = subprocess.run([sys.executable, str(S78 / "scripts" / "run_image_stages.py"), "--plan", str(self.dir / "plan.json"),
                               "--request", str(self.dir / "page-request.json"), "--run-dir", str(self.dir / "run"),
                               "--launch-record", str(self.dir / "launch.json"), "--inputs", str(self.dir / "inputs.json"),
                               "--skill71-root", str(S71)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("S78-TEST-ONLY-IN-PRODUCTION", proc.stdout)
        self.assertFalse((self.dir / "run").exists())

    def test_a_bare_selection_page_is_refused(self):
        for offer in self.launch["offers"]:
            offer["deliverables"], offer["limited_deliverables"] = [], []
        proc = self.adapter()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("S78-OFFER-NO-DELIVERABLES", proc.stdout + proc.stderr)


@needs71
class ImageRunArtifactTests(Chain):
    def test_the_image_run_dir_is_listed_as_artifacts_and_runtime_scripts_are_not_claimed(self):
        self.assertEqual(self.adapter().returncode, 0)
        images = self.work / "order-page-images"
        proc, out = self.emit("--image-run-dir", str(images))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        artifacts = json.loads(out.read_text())["artifacts"]
        listed = {Path(a["path"]).relative_to(images).as_posix(): a["sha256"] for a in artifacts}
        for rel in ("copy/internal-manuscript.md", "desktop-wireframe/section-01.png", "visual-mockup/mobile/part-05.png"):
            self.assertEqual(listed[rel], hashlib.sha256((images / rel).read_bytes()).hexdigest())
        manifest = json.loads((S78 / "runtime-manifest.json").read_text())["done_claim"]
        self.assertIn("scripts/selection_runtime.py", manifest["not_counted"])
        self.assertIn("scripts/selection_session_store.py", manifest["not_counted"])
        self.assertFalse(set(manifest["counted"]) & set(manifest["not_counted"]))
        self.assertFalse([p for p in listed if "selection_runtime" in p or "session_store" in p])

    def test_a_manuscript_edited_after_the_run_is_refused_and_no_result_is_written(self):
        self.assertEqual(self.adapter().returncode, 0)
        images = self.work / "order-page-images"
        manuscript = images / "copy" / "internal-manuscript.md"
        manuscript.write_text(manuscript.read_text() + "\nMost popular choice.\n")
        proc, out = self.emit("--image-run-dir", str(images))
        self.assertEqual(proc.returncode, 3)
        self.assertIn("S78-UNPROVEN-CLAIM", proc.stderr)
        self.assertFalse(out.exists())

    def test_an_empty_run_dir_or_one_without_a_manuscript_is_refused(self):
        self.write()
        (self.work / "selection-plan.json").write_text((GOLDEN / "plan.json").read_text())
        (self.dir / "empty").mkdir()
        proc, out = self.emit("--image-run-dir", str(self.dir / "empty"))
        self.assertEqual(proc.returncode, 3)
        self.assertFalse(out.exists())


class ManuscriptGateTests(unittest.TestCase):
    def test_every_claim_phrase_is_refused_and_there_is_no_evidence_channel(self):
        text, _ = ems.build(json.loads((GOLDEN / "plan.json").read_text()))
        launch = json.loads((GOLDEN / "launch.json").read_text())
        self.assertTrue(validate_manuscript(text, launch))
        for claim in ("Most popular", "Best value", "You save 20", "40% off", "Limited time", "Only 50 left"):
            with self.assertRaises(Violation, msg=claim) as caught:
                validate_manuscript(text + f"\n{claim}.\n", launch)
            self.assertEqual(caught.exception.code, "S78-UNPROVEN-CLAIM")

    def test_a_manuscript_with_no_compare_rows_is_refused(self):
        plan = json.loads((GOLDEN / "plan.json").read_text())
        text, _ = ems.build(plan)
        launch = json.loads((GOLDEN / "launch.json").read_text())
        head, rest = text.split("## Section 4: Compare", 1)
        bare = head + "## Section 4: Compare\n\n## Section 5" + rest.split("## Section 5", 1)[1]
        self.assertEqual(compare_rows(bare), [])
        with self.assertRaises(Violation) as caught:
            validate_manuscript(bare, launch)
        self.assertEqual(caught.exception.code, "S78-COMPARE-EMPTY")
        plan["comparison_matrix"]["rows"] = []
        with self.assertRaises(ValueError):
            ems.build(plan)

    def test_a_wrong_price_and_a_hidden_exclusion_are_refused(self):
        text, _ = ems.build(json.loads((GOLDEN / "plan.json").read_text()))
        launch = json.loads((GOLDEN / "launch.json").read_text())
        with self.assertRaises(Violation) as caught:
            validate_manuscript(text.replace("$197.00", "$147.00"), launch)
        self.assertEqual(caught.exception.code, "S78-COPY-PRICE-MISMATCH")
        with self.assertRaises(Violation) as caught:
            validate_manuscript(text.replace("Not included: Private review sessions are not included", "Support"), launch)
        self.assertEqual(caught.exception.code, "S78-HIDDEN-EXCLUSION")


class CheckRuleTests(unittest.TestCase):
    """check_rules/claims.py and selection.py, called the way check_package calls a rule module."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def piece(self, role, name, text):
        path = self.root / "pieces" / role / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return {"role": role, "slot": role, "artifacts": [{"path": str(path.relative_to(self.root)), "sha256": "0" * 64}]}

    def test_claims_fails_every_discount_and_scarcity_claim_in_every_pieces_copy(self):
        claims = load_rule("claims")
        manifest = {"pieces": [self.piece("landing", "copy.md", "Black Friday: 40% off, only 50 left, ends Monday."),
                               self.piece("upsell_1", "internal-manuscript.md", "Limited time. Most popular add-on."),
                               self.piece("thank_you", "copy.md", "Thank you for your order.")]}
        fails = claims.violations(manifest, self.root, SKILL_ROOT)
        for phrase in ("40% off", "only 50 left", "ends monday", "limited time", "most popular"):
            self.assertTrue([f for f in fails if f"{phrase!r}" in f], (phrase, fails))
        self.assertTrue(all(f.startswith("AF-LAUNCH-CLAIM") for f in fails))
        self.assertFalse([f for f in fails if "thank_you" in f])

    def test_claims_passes_honest_copy_and_ignores_design_files(self):
        claims = load_rule("claims")
        manifest = {"pieces": [self.piece("landing", "copy.md", "Join the Elevation program. Choose your package."),
                               self.piece("checkout", "desktop-wireframes/checkout_desktop_wireframe_s01-of-02_hero.png",
                                          "limited time (not copy)")]}
        self.assertEqual(claims.violations(manifest, self.root, SKILL_ROOT), [])

    def test_selection_fails_a_compare_section_with_no_rows(self):
        selection = load_rule("selection")
        plan = json.loads((GOLDEN / "plan.json").read_text())
        text, _ = ems.build(plan)
        head, rest = text.split("## Section 4: Compare", 1)
        bare = head + "## Section 4: Compare\n\n## Section 5" + rest.split("## Section 5", 1)[1]
        good = {"test_only": True, "pieces": [self.piece("product_selection", "copy/internal-manuscript.md", text)]}
        self.assertEqual(selection.violations(good, self.root, SKILL_ROOT), [])
        bad = {"test_only": True, "pieces": [self.piece("product_selection", "copy/internal-manuscript.md", bare)]}
        fails = selection.violations(bad, self.root, SKILL_ROOT)
        self.assertEqual(len(fails), 1)
        self.assertIn("Compare section", fails[0])

    def test_selection_does_not_fail_a_piece_that_lists_no_manuscript(self):
        selection = load_rule("selection")
        piece = self.piece("product_selection", "desktop-wireframe/section-01.png", "png")
        self.assertEqual(selection.violations({"test_only": False, "pieces": [piece]}, self.root, SKILL_ROOT), [])

    def test_check_package_runs_both_rules_when_the_seam_is_present(self):
        seam = importlib.import_module("launcher_core.check_rules")
        if not hasattr(seam, "run"):
            self.skipTest("the check_rules seam (U-launcher-core-02) is not in this tree; QC re-runs this after it lands")
        manifest = {"test_only": True, "pieces": [self.piece("landing", "copy.md", "Only 50 left!")]}
        plan = json.loads((GOLDEN / "plan.json").read_text())
        text, _ = ems.build(plan)
        head, rest = text.split("## Section 4: Compare", 1)
        bare = head + "## Section 4: Compare\n\n## Section 5" + rest.split("## Section 5", 1)[1]
        manifest["pieces"].append(self.piece("product_selection", "copy/internal-manuscript.md", bare))
        fails = seam.run(manifest, self.root, SKILL_ROOT)
        self.assertTrue([f for f in fails if f.startswith("AF-LAUNCH-CLAIM")], fails)
        self.assertTrue([f for f in fails if f.startswith("AF-LAUNCH-SELECTION")], fails)


class LevelsTests(unittest.TestCase):
    """PRD-19: the Elevation launch with levels supplied compares every deliverable."""

    LEVELS = {"MAIN-ESS": ["Core course", "Community access"],
              "MAIN-PRO": ["Core course", "Community access", "Two private reviews"],
              "MAIN-ELITE": ["Core course", "Community access", "Two private reviews", "Private strategy day"]}

    def build_launch(self, with_levels):
        doc = json.loads((FIXTURES / "elevation" / "intake.json").read_text(encoding="utf-8"))
        doc["image_plan"] = {"brand_file": "/tmp/test-brand.json", "brand_owner": "TEST-ONLY Client"}
        if with_levels:
            for offer in doc["offers"]:
                if offer["offer_id"] in self.LEVELS:
                    offer["level"] = {"state": "supplied", "name": offer["name"],
                                      "deliverables": self.LEVELS[offer["offer_id"]]}
        normalized = intake.validate(doc)
        inputs, _ = image_plan.resolve(normalized.get("image_plan"), test_only=normalized["test_only"])
        return launch_bridge.to_launch_record(normalized, route.compile_route(normalized), inputs)

    def test_levels_supplied_gives_a_comparison_row_per_dimension(self):
        launch = self.build_launch(True)
        text, _ = ems.build(build_plan(launch))
        rows = compare_rows(text)
        dimensions = {d for items in self.LEVELS.values() for d in items}
        self.assertEqual(len(rows), len(dimensions))
        for dimension in dimensions:
            self.assertEqual(len([r for r in rows if r.startswith(f"- {dimension}:")]), 1, dimension)
        self.assertTrue(validate_manuscript(text, launch))

    def test_without_levels_the_selection_page_is_refused_not_padded(self):
        launch = self.build_launch(True)  # supplied levels, then every offer's deliverables emptied (as in the adapter test)
        for offer in launch["offers"]:
            offer["deliverables"], offer["limited_deliverables"] = [], []
        with self.assertRaises(Violation) as caught:
            build_plan(launch)
        self.assertEqual(caught.exception.code, "S78-OFFER-NO-DELIVERABLES")

    def test_without_levels_the_intake_is_refused(self):
        doc = json.loads((FIXTURES / "elevation" / "intake.json").read_text(encoding="utf-8"))
        mains = [i for i, o in enumerate(doc["offers"]) if o["role"] == "main"]
        if not any("level" in doc["offers"][i] for i in mains):
            self.skipTest("the fixture has no main-offer levels yet (U-products-01 supplies them); "
                          "QC re-runs this after it lands")
        for i in mains:
            doc["offers"][i].pop("level", None)
        with self.assertRaises(intake.IntakeError) as caught:
            intake.validate(doc)
        self.assertEqual(caught.exception.code, "AF-LAUNCH-INTAKE-LEVEL")
        self.assertEqual(caught.exception.field, f"offers[{mains[0]}].level")


if __name__ == "__main__":
    unittest.main()
