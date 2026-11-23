#!/usr/bin/env python3
"""RFX-006: the fixes a client box carried locally, now upstream. One test per ported behaviour.

Each test fails on the code before the port: the prompt brace escape, the non-landing route
read, the preflight button rule, the numeric slot ids, the QC-report cross-check, the mockup
slot identity, the deterministic validation log, the US spelling, the executor's empty
reference list and keyword guard, and the gate's tightening-only close checks.
"""
import importlib.util
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name):
    spec = importlib.util.spec_from_file_location(f"rfx006_{name}", SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PromptBraces(unittest.TestCase):
    def test_a_brace_in_any_prose_block_survives_str_format(self):
        bpr = load("build_production_request")
        blocks = {"rules_md": 'font map {"h1": "Serif"}', "notes": "keep {this} literal"}
        tpl = bpr.template_for("desktop-wireframe", blocks)
        out = tpl.format(section_number=1, section_total=2, section_name="Hero", width=1440,
                         layout="L", copy="C", slots="S")
        self.assertIn('font map {"h1": "Serif"}', out)
        self.assertIn("keep {this} literal", out)


class PageResultRoute(unittest.TestCase):
    def test_a_checkout_node_is_not_judged_by_the_landing_next_role_rule(self):
        pr = load("page_result")
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            graph = {"nodes": [{"page_id": "p-checkout", "role": "checkout"},
                               {"page_id": "p-thanks", "role": "thank_you"}],
                     "edges": [{"from": "p-checkout", "to": "p-thanks",
                                "event": "payment_succeeded"}]}
            (run / "route.json").write_text(json.dumps(graph), encoding="utf-8")
            req = {"route_graph_ref": "route.json", "page_id": "p-checkout",
                   "page_role": "checkout"}
            _info, errors = pr.resolve_route(run, req)
        self.assertEqual(errors, [])


class SlotIdentity(unittest.TestCase):
    def test_grade_ids_compare_numerically(self):
        vig = load("validate_image_grade")
        self.assertEqual(vig.normalize_id("IMG-001"), vig.normalize_id("Image-01"))
        self.assertEqual(vig.normalize_id("IMG-01"), vig.normalize_id("image-1"))
        self.assertNotEqual(vig.normalize_id("IMG-001"), vig.normalize_id("IMG-002"))

    def test_mockup_slots_share_one_identity_across_namespaces(self):
        vms = load("validate_mockup_slots")
        self.assertEqual(vms.slot_key("IMG-001"), vms.slot_key("Image-01"))
        _index, fails = vms.keyed(["IMG-001", "PKG-1"], [1, 2], "where")
        self.assertTrue(fails and "share the identity" in fails[0], fails)


class ManifestQcCrossCheck(unittest.TestCase):
    def entries(self):
        return [("images[0]", {"asset_file": "a.png", "filename": "Image-01.png",
                               "qc_status": "passed"}, "IMG-001", None)]

    def test_a_passed_claim_needs_a_passing_qc_report(self):
        vim = load("validate_image_manifest")
        fails = vim.qc_report_problems(self.entries(), {"verdict": "FAIL", "assets": []}, "qc")
        self.assertTrue(any("not PASS" in f for f in fails), fails)
        self.assertTrue(any("graded no asset" in f for f in fails), fails)
        ok = {"verdict": "PASS", "assets": [{"asset_id": "IMG-001", "pass": True}]}
        self.assertEqual(vim.qc_report_problems(self.entries(), ok, "qc"), [])
        self.assertTrue(vim.qc_report_problems(self.entries(), None, "qc"))


class CopyPrimaryHandoff(unittest.TestCase):
    def test_a_sales_page_primary_cta_is_its_checkout_link(self):
        vcs = load("validate_copy_structure")
        src = inspect.getsource(vcs.validate)
        self.assertIn("primary_type", inspect.signature(vcs.validate).parameters)
        self.assertIn("external_link", src)


class DeterministicValidationLog(unittest.TestCase):
    def test_the_pinned_log_carries_no_wall_clock(self):
        text = (SCRIPTS / "validate_page.py").read_text(encoding="utf-8")
        self.assertNotIn('"generated_at": datetime.now', text)
        self.assertIn("composition_cues(brand, style_id)", text)


class WireframeSpelling(unittest.TestCase):
    def test_the_behavior_note_uses_us_spelling(self):
        spec = json.loads((ROOT / "references" / "wireframe-build-spec.json").read_text("utf-8"))
        line = json.dumps(spec)
        self.assertIn("BEHAVIOR NOTE:", line)


class PreflightButtons(unittest.TestCase):
    def test_the_self_test_manuscript_honours_a_forbidden_standalone_cta(self):
        text = (SCRIPTS / "preflight_installed.py").read_text(encoding="utf-8")
        self.assertIn('cta_rule.get("standalone") == "forbidden"', text)


class ExecutorReferences(unittest.TestCase):
    def setUp(self):
        self.se = load("stage_executor")

    def test_ceiling_only_is_passed_only_to_a_callable_that_takes_it(self):
        def old(text, *, model=None):
            return None

        def new(text, *, model=None, ceiling_only=False):
            return None
        self.assertEqual(self.se._ceiling_kw(old, True), {})
        self.assertEqual(self.se._ceiling_kw(new, True), {"ceiling_only": True})
        self.assertEqual(self.se._ceiling_kw(new, False), {})

    def test_submit_carries_the_flag_once_and_only_when_accepted(self):
        calls = []

        class Old:
            def submit(self, req_path):
                calls.append(("old", req_path))
                return {}

        class New:
            def submit(self, req_path, ceiling_only=False):
                calls.append(("new", ceiling_only))
                return {}
        self.se._transport_submit(Old(), "r", ceiling_only=True)
        self.se._transport_submit(New(), "r", ceiling_only=True)
        self.assertEqual(calls, [("old", "r"), ("new", True)])

    def test_only_the_design_board_is_a_verbatim_sheet(self):
        self.assertTrue(self.se.job_is_verbatim_sheet({"stage": self.se.BOARD_STAGE}))
        self.assertFalse(self.se.job_is_verbatim_sheet({"stage": "desktop-wireframe"}))


class GateTightening(unittest.TestCase):
    def setUp(self):
        self.sg = load("stage_gate")

    def test_a_vision_pass_must_name_the_delivered_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "image-generation-qc").mkdir()
            png = run / "image-generation-qc" / "Image-01.png"
            png.write_bytes(b"\x89PNG fake")
            self.assertTrue(self.sg.vision_log_problems(run))
            (run / "qc").mkdir()
            log = [{"artifact_sha256": self.sg.sha256_file(png), "vision_api_response": {"ok": 1}}]
            (run / "qc" / "vision_qc_log.json").write_text(json.dumps(log), encoding="utf-8")
            self.assertEqual(self.sg.vision_log_problems(run), [])


if __name__ == "__main__":
    unittest.main()
