#!/usr/bin/env python3
"""Lane 83 graphics hooks in Skill 71 (SOP-GIP-02): free, no provider, no network.

  1. write_review.py: a reviewer model must differ from the prompt author's model; an unnamed model
     counts as not independent; a pass verdict cannot cite an AF-G automatic failure; with no model
     flags the record is exactly what it was before.
  2. validate_production_record.py: logo accuracy (AF-G2) and the text read-back (AF-G1) against the
     image itself (reader injected here, so no OCR engine is needed).
  3. stage_executor.py: a model that cannot render text is refused, and so is a file that is not a PNG.
  4. The AF-G1..AF-G8 list exists as data in stage-contract.json and as a table in qc-contract.md.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(SCRIPTS))

import test_item13_production_method as item13  # noqa: E402  (its make_stage builds a valid record)
import validate_production_record as vpr  # noqa: E402

PY = sys.executable
NOTE = "Checked against the artifact bytes and the stage rubric line by line."


def load(name):
    spec = importlib.util.spec_from_file_location(f"lane83_{name}", SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ContractDataTests(unittest.TestCase):
    def test_the_eight_codes_are_data_in_the_stage_contract_and_a_table_in_the_qc_contract(self):
        contract = json.loads((ROOT / "references" / "stage-contract.json").read_text(encoding="utf-8"))
        rows = contract["graphics_autofails"]
        self.assertEqual([r["code"] for r in rows], [f"AF-G{i}" for i in range(1, 9)])
        self.assertTrue(all(r["name"] and r["summary"] and r["effect"] for r in rows))
        qc = (ROOT / "references" / "qc-contract.md").read_text(encoding="utf-8")
        for r in rows:
            self.assertIn(f"| {r['code']} |", qc)
        self.assertEqual(set(contract["stage_order"]), set(contract["stages"]))  # the stage list is untouched


class ModelIndependenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "run"
        (self.run_dir / "image-generation-qc").mkdir(parents=True)
        (self.run_dir / "image-generation-qc" / "Image-01.png").write_bytes(b"\x89PNG\r\n\x1a\nx")
        self.wr = load("write_review")

    def tearDown(self):
        self.tmp.cleanup()

    def review(self, *flags, verdict="pass", reviewer="sess-reviewer", author="sess-author", item="Image-01",
               failures="[]", defects="[]"):
        env = {k: v for k, v in os.environ.items()
               if k not in ("OPENCLAW_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID",
                            "SKILL71_REVIEWER_MODEL")}
        env["OPENCLAW_SESSION_ID"] = reviewer
        cmd = [PY, str(SCRIPTS / "write_review.py"), str(self.run_dir), "image-generation-qc", item,
               "--artifact", "image-generation-qc/Image-01.png",
               "--scores", json.dumps({"brief_fidelity": {"score": 9, "note": NOTE}}),
               "--verdict", verdict, "--performed-check", "Opened the image and read every word on it.",
               "--next-current-artifact", "the image-generation-qc stage receipt",
               "--author-session", author, "--automatic-failures", failures, "--specific-defects", defects,
               *flags]
        proc = subprocess.run(cmd, text=True, capture_output=True, env=env)
        path = self.run_dir / "private" / "reviews" / "image-generation-qc" / f"{item}.review.json"
        return proc, (json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None)

    def test_the_pure_rule(self):
        mi = self.wr.model_independence
        self.assertEqual(mi("model-a", "model-b"), "independent")
        self.assertEqual(mi("Model-A", " model-a "), "same_model")
        self.assertEqual(mi(None, "model-b"), "unknown")
        self.assertEqual(mi("model-a", ""), "unknown")

    def test_a_different_model_in_a_different_session_is_independent(self):
        proc, rec = self.review("--author-model", "gpt-image-2", "--reviewer-model", "qwen3-vl")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(rec["independent_review"])
        self.assertEqual((rec["author_model"], rec["reviewer_model"], rec["model_independence"]),
                         ("gpt-image-2", "qwen3-vl", "independent"))

    def test_the_same_model_is_not_independent_even_in_another_session(self):
        proc, rec = self.review("--author-model", "qwen3-vl", "--reviewer-model", "qwen3-vl")
        self.assertEqual(proc.returncode, 0)
        self.assertFalse(rec["independent_review"])
        self.assertEqual(rec["model_independence"], "same_model")
        self.assertIn("independent_review false", proc.stderr)

    def test_an_unnamed_model_counts_as_not_independent(self):
        _, rec = self.review("--author-model", "gpt-image-2")
        self.assertFalse(rec["independent_review"])
        self.assertEqual((rec["reviewer_model"], rec["model_independence"]), ("UNKNOWN", "unknown"))
        _, rec = self.review("--require-model-independence", item="Image-02")
        self.assertFalse(rec["independent_review"])
        self.assertEqual((rec["author_model"], rec["reviewer_model"]), ("UNKNOWN", "UNKNOWN"))

    def test_the_reviewer_model_can_come_from_the_environment(self):
        env_flag = {"SKILL71_REVIEWER_MODEL": "qwen3-vl"}
        old = dict(os.environ)
        os.environ.update(env_flag)
        try:
            proc = subprocess.run(
                [PY, str(SCRIPTS / "write_review.py"), str(self.run_dir), "image-generation-qc", "Image-03",
                 "--artifact", "image-generation-qc/Image-01.png",
                 "--scores", json.dumps({"brief_fidelity": {"score": 9, "note": NOTE}}),
                 "--verdict", "pass", "--performed-check", "Opened the image and read it.",
                 "--next-current-artifact", "the stage receipt", "--author-session", "sess-author",
                 "--author-model", "gpt-image-2"],
                text=True, capture_output=True, env={**os.environ, "OPENCLAW_SESSION_ID": "sess-r"})
        finally:
            os.environ.clear()
            os.environ.update(old)
        rec = json.loads((self.run_dir / "private/reviews/image-generation-qc/Image-03.review.json").read_text())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(rec["independent_review"])

    def test_with_no_model_flags_the_record_is_what_it_was_before(self):
        proc, rec = self.review()
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(rec["independent_review"])
        for key in ("author_model", "reviewer_model", "model_independence"):
            self.assertNotIn(key, rec)

    def test_a_pass_cannot_cite_a_graphics_automatic_failure(self):
        for code in ("AF-G1", "AF-G2: logo recolored", "AF-G8"):
            proc, rec = self.review(failures=json.dumps([code]), item="Image-09")
            self.assertEqual(proc.returncode, 1, code)
            self.assertIn("graphics automatic failure", proc.stdout)
            self.assertIsNone(rec)

    def test_a_fail_may_cite_one_and_an_unrelated_note_does_not_trip_the_rule(self):
        proc, rec = self.review(failures='["AF-G1"]', defects='["garbled headline"]',
                                item="Image-10", verdict="fail")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(rec["automatic_failures"], ["AF-G1"])
        proc, rec = self.review(failures='["slightly soft shadow"]', item="Image-11")
        self.assertEqual(proc.returncode, 0)


class ProductionRecordHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stage = item13.make_stage(self.tmp.name)
        self.record = json.loads((self.stage / "production-record.json").read_text(encoding="utf-8"))

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, record=None, ocr=None):
        return vpr.check_record(record or self.record, base_dir=self.stage, ocr=ocr)

    def test_the_baseline_record_still_passes(self):
        self.assertEqual(self.check(), [])

    def test_logo_expected_without_a_logo_check_fails_af_g2(self):
        self.record["sections"][0]["logo_expected"] = True
        fails = self.check()
        self.assertTrue(any("AF-G2" in f and "no logo_check record" in f for f in fails), fails)

    def test_a_failed_or_incomplete_logo_check_fails(self):
        section = self.record["sections"][0]
        section["logo_expected"] = True
        section["logo_check"] = {"logo_ref": "brand/logo.png", "method": "side-by-side with the logo file",
                                 "verdict": "fail"}
        self.assertTrue(any("mutated, recolored or invented" in f for f in self.check()))
        section["logo_check"] = {"verdict": "pass"}
        fails = self.check()
        self.assertTrue(any("logo_check.logo_ref is required" in f for f in fails), fails)
        self.assertTrue(any("logo_check.method is required" in f for f in fails), fails)
        section["logo_check"] = {"logo_ref": "brand/logo.png", "method": "side-by-side", "verdict": "maybe"}
        self.assertTrue(any("verdict must be one of" in f for f in self.check()))

    def test_a_passing_logo_check_passes(self):
        section = self.record["sections"][0]
        section["logo_expected"] = True
        section["logo_check"] = {"logo_ref": "brand/logo.png", "method": "side-by-side", "verdict": "pass"}
        self.assertEqual(self.check(), [])

    def test_a_section_that_does_not_expect_a_logo_is_not_asked_for_one(self):
        self.record["sections"][0]["logo_expected"] = False
        self.assertEqual(self.check(), [])

    def test_the_read_back_must_be_supported_by_the_image_itself(self):
        seen = {}

        def faithful(path):  # the "image" really does say what the section's copy says
            seen[path.name] = True
            return " ".join(s["text_qc"]["expected_text"] for s in self.record["sections"])

        self.assertEqual(self.check(ocr=faithful), [])
        self.assertEqual(sorted(seen), ["section-01.png", "section-02.png", "section-03.png"])

    def test_an_image_that_does_not_show_its_copy_fails_af_g1(self):
        fails = self.check(ocr=lambda path: "completely unrelated pixels about something else")
        self.assertTrue(any("AF-G1" in f and "does not show its copy" in f for f in fails), fails)
        self.assertTrue(any("AF-G1" in f and "not supported by the image" in f for f in fails), fails)

    def test_the_cli_reader_is_the_design_boards_own(self):
        board = vpr._design_board()
        self.assertTrue(callable(board.ocr_text))
        self.assertTrue(callable(board.support))

    def test_without_the_ocr_flag_nothing_reads_pixels(self):
        proc = subprocess.run([PY, str(SCRIPTS / "validate_production_record.py"),
                               str(self.stage / "production-record.json")], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stdout)


class StageExecutorHookTests(unittest.TestCase):
    def setUp(self):
        self.se = load("stage_executor")

    def test_text_blind_model_classes_are_refused_before_any_call(self):
        for model in ("nano-banana-2", "google/nano-banana-pro", "bytedance/seedream-4"):
            with self.assertRaises(self.se.ExecutorError) as ctx:
                self.se.require_text_capable(model)
            self.assertIn("cannot render readable text", str(ctx.exception))
            self.assertIn("no API call was made", str(ctx.exception))

    def test_text_capable_models_pass(self):
        for model in ("gpt-image-2-5-sunburst-text-to-image", "gpt-image-2-text-to-image", "stub-model"):
            self.se.require_text_capable(model)

    def test_the_paid_route_refuses_a_text_blind_model_without_touching_the_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = self.se.KieProvider(Path(tmp) / "never-run.py", Path(tmp))
            job = {"stage": "desktop-wireframe", "index": 1, "out": Path(tmp) / "out.png"}
            with self.assertRaises(self.se.ExecutorError):
                provider.generate(job, {"model": "nano-banana-2"})

    def test_a_saved_file_that_is_not_a_png_is_refused_not_renamed(self):
        with tempfile.TemporaryDirectory() as tmp:
            good, bad = Path(tmp) / "g.png", Path(tmp) / "b.png"
            good.write_bytes(self.se.PNG_MAGIC + b"rest")
            bad.write_bytes(b"\xff\xd8\xffJPEG")
            self.se.require_png(good)
            with self.assertRaises(self.se.ExecutorError) as ctx:
                self.se.require_png(bad)
            self.assertIn("is not a PNG", str(ctx.exception))

    def test_the_stub_provider_still_makes_real_pngs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "s.png"
            self.se.StubProvider().generate({"out": out, "width": 390, "height": 600, "label": "x"}, {})
            self.se.require_png(out)


if __name__ == "__main__":
    unittest.main()
