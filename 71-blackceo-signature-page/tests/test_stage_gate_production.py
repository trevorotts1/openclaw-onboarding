#!/usr/bin/env python3
"""U-images-03: the 71 stage gate cannot be talked past on generated-image QC.

IMG-11  an UNKNOWN reviewer cannot close a production stage; the contract wires the
        OCR read-back (AF-G1) into the four section-image stages, and the logo (AF-G2)
        is checked against the client's own logo file.
IMG-14  prompts are judged against the model the run's request names (a 19,000-char
        prompt fails a 5,000-char model maximum).
IMG-15  'stock' is not a free pass: supplied-* and stock assets need a supplied-asset
        record, and stock a licence reference; the transport gate recognises stock.

Each failing case has a passing control run through the same instrument.
"""
import hashlib
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
stage_gate = importlib.import_module("stage_gate")
validate_prompt = importlib.import_module("validate_prompt")
validate_image_manifest = importlib.import_module("validate_image_manifest")
validate_production_record = importlib.import_module("validate_production_record")

CONTRACT = json.loads((ROOT / "references" / "stage-contract.json").read_text(encoding="utf-8"))
NOTE = "Checked the artifact bytes against the stage rubric, line by line, in a fresh session."
SHA = "a" * 64


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = Path(self._tmp.name)


class UnknownReviewerBlocksProductionClose(Tmp):
    def review(self, reviewer):
        art = self.run_dir / "copy" / "public-copy.md"
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_bytes(b"the page copy")
        write_json(self.run_dir / "private" / "reviews" / "copy" / "stage.review.json", {
            "item": "stage", "artifact": "copy/public-copy.md", "artifact_sha256": sha(b"the page copy"),
            "author_session": "author-session-1", "reviewer_session": reviewer,
            "verdict": "pass", "automatic_failures": [], "specific_defects": [], "repair_attempt": 0,
            "performed_check": "opened the copy", "next_current_artifact": "the copy receipt",
            "independent_review": reviewer != "UNKNOWN",
            "criteria": {"clarity": {"score": 9, "note": NOTE}},
        })

    def close_failures(self):
        receipt = {"author_agent": "copy-agent", "author_session": "author-session-1"}
        return stage_gate.check_review_scores(self.run_dir, "copy", receipt)

    def test_unknown_reviewer_fails_a_production_close(self):
        self.review("UNKNOWN")
        write_json(self.run_dir / "intake.json", {"brand_owner": "Acme"})
        lines = [l for l in self.close_failures() if "UNKNOWN" in l]
        self.assertTrue(lines, "an UNKNOWN reviewer closed a production stage")
        self.assertIn("test_run", lines[0])

    def test_unknown_reviewer_is_allowed_only_for_a_test_run(self):
        self.review("UNKNOWN")
        write_json(self.run_dir / "intake.json", {"brand_owner": "Acme", "test_run": True})
        self.assertEqual([l for l in self.close_failures() if "UNKNOWN" in l], [])

    def test_control_named_reviewer_closes_in_production(self):
        self.review("reviewer-session-2")
        write_json(self.run_dir / "intake.json", {"brand_owner": "Acme"})
        self.assertEqual(self.close_failures(), [])


class ContractWiring(unittest.TestCase):
    def test_section_image_stages_read_the_pixels_and_name_the_model(self):
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup", "final-mockups"):
            cmds = [v for v in CONTRACT["stages"][stage]["validators"]
                    if "validate_production_record.py" in v]
            self.assertEqual(len(cmds), 1, stage)
            argv = cmds[0].split()
            self.assertIn("--ocr", argv, stage)
            self.assertIn("--model", argv, stage)
            self.assertIn(f"visual-mockup/production-record.json" if stage == "visual-mockup"
                          else f"{stage}/production-record.json", cmds[0])
        # visual-mockup never carried a production record; --if-present reads it back when one exists
        (vm,) = [v for v in CONTRACT["stages"]["visual-mockup"]["validators"] if "validate_production_record" in v]
        self.assertIn("--if-present", vm.split())
        for stage in ("desktop-wireframe", "mobile-tablet", "final-mockups"):
            (cmd,) = [v for v in CONTRACT["stages"][stage]["validators"] if "validate_production_record" in v]
            self.assertNotIn("--if-present", cmd.split(), stage)

    def test_prompt_validator_names_the_model_and_its_maximum(self):
        (cmd,) = CONTRACT["stages"]["image-inventory-prompts"]["validators"]
        argv = cmd.split()
        self.assertIn("--model", argv)
        self.assertIn("--max-chars", argv)

    def test_flag_and_value_drop_together_when_the_run_declares_no_model(self):
        tpl = "python3 x.py {file} {sauce} --model {model} --max-chars {max_chars}"
        argv = stage_gate.substitute_argv(tpl, {"{file}": "a b.txt", "{sauce}": "", "{model}": "", "{max_chars}": ""})
        self.assertEqual(argv, ["python3", "x.py", "a b.txt"])
        argv = stage_gate.substitute_argv(tpl, {"{file}": "f", "{sauce}": "", "{model}": "m-1", "{max_chars}": "5000"})
        self.assertEqual(argv[-4:], ["--model", "m-1", "--max-chars", "5000"])


class PromptJudgedAgainstTheRunModel(Tmp):
    PROMPT = ("A photograph of a founder at a desk. " * 600)[:19000]

    def test_19000_chars_fails_a_5000_char_model_maximum(self):
        res = validate_prompt.inspect(self.PROMPT, model="gpt-image-2-5-sunburst-text-to-image", max_chars=5000)
        self.assertTrue([e for e in res["errors"] if "of max 5000" in e], res["errors"])
        self.assertEqual(res["telemetry"]["budget"]["status"], "ABOVE_MAX")

    def test_control_without_the_request_maximum_the_policy_band_passes_it(self):
        res = validate_prompt.inspect(self.PROMPT, model="gpt-image-2-5-sunburst-text-to-image")
        self.assertEqual(res["telemetry"]["budget"]["status"], "OK")
        self.assertEqual([e for e in res["errors"] if "max is" in e], [])

    def test_request_maximum_cannot_loosen_the_policy_maximum(self):
        res = validate_prompt.inspect(self.PROMPT, model="gpt-image-2-5-sunburst-text-to-image", max_chars=90000)
        self.assertEqual(res["telemetry"]["model_max_chars"], 20000)

    def test_gate_reads_the_model_from_the_run_request(self):
        self.assertEqual(stage_gate.run_model_request(self.run_dir), (None, None))
        write_json(self.run_dir / "production-request.json",
                   {"model": "gpt-image-2-5-sunburst-text-to-image", "model_max_chars": 5000, "sections": []})
        self.assertEqual(stage_gate.run_model_request(self.run_dir, "image-inventory-prompts"),
                         ("gpt-image-2-5-sunburst-text-to-image", 5000))

    def item_failures(self):
        prompt = self.run_dir / "image-inventory-prompts" / "IMG-001.txt"
        prompt.parent.mkdir(parents=True, exist_ok=True)
        prompt.write_text(self.PROMPT, encoding="utf-8")
        return "\n".join(stage_gate.run_item_validators(
            self.run_dir, "image-inventory-prompts", "image-inventory-prompts/IMG-001.txt"))

    def test_stage_validator_fails_the_prompt_against_the_request_model(self):
        write_json(self.run_dir / "production-request.json",
                   {"model": "gpt-image-2-5-sunburst-text-to-image", "model_max_chars": 5000, "sections": []})
        self.assertIn("of max 5000", self.item_failures())

    def test_control_no_request_model_leaves_the_default_judgement(self):
        self.assertNotIn("of max 5000", self.item_failures())

    def test_close_records_the_budget_against_the_run_model(self):
        write_json(self.run_dir / "production-request.json",
                   {"model": "gpt-image-2-5-sunburst-text-to-image", "model_max_chars": 5000, "sections": []})
        prompt = self.run_dir / "image-inventory-prompts" / "IMG-001.txt"
        prompt.parent.mkdir(parents=True, exist_ok=True)
        prompt.write_text(self.PROMPT, encoding="utf-8")
        record = stage_gate._prompt_budget_record(prompt, self.run_dir)
        self.assertEqual(record["model"], "gpt-image-2-5-sunburst-text-to-image")
        self.assertEqual(record["budget"]["max"], 5000)
        self.assertEqual(record["percent_of_max"], 380.0)


class GeneratedImageTextAndLogo(Tmp):
    """AF-G1 (OCR read-back) and AF-G2 (logo) on a mockup production record."""

    def build(self, readback="Welcome to Acme Coaching", logo=None):
        from PIL import Image
        stage = self.run_dir / "final-mockups"
        (stage / "desktop").mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (40, 20), "white").save(stage / "desktop" / "part-01.png")
        Image.new("RGB", (40, 20), "white").save(self.run_dir / "wire.png")
        section = {
            "section_id": "hero", "slice": "desktop/part-01.png", "width": 40, "height": 20,
            "generation": {"route": "kie-gpt-image", "model_id": "model-a", "model_source": "explicit-request",
                           "layout_reference": "wire.png", "style_input": "visual-bible",
                           "native_aspect": "40x20"},
            "text_qc": {"checked_at_native_resolution": True, "expected_text": "Welcome to Acme Coaching",
                        "readback_text": readback, "garbled_words": [], "attempts": 1, "verdict": "pass"},
        }
        if logo is not None:
            section["logo_expected"] = True
            section["logo_check"] = logo
        return {"artifact": "mockup", "stage": "final-mockups", "sections": [section]}, stage

    def test_a_mockup_whose_ocr_text_diverges_from_the_copy_fails(self):
        record, stage = self.build()
        fails = validate_production_record.check_record(
            record, base_dir=stage, ocr=lambda path: "Frree gift inside click here now")
        self.assertTrue([f for f in fails if "AF-G1" in f], fails)

    def test_control_matching_ocr_text_passes(self):
        record, stage = self.build()
        self.assertEqual(validate_production_record.check_record(
            record, base_dir=stage, ocr=lambda path: "Welcome to Acme Coaching"), [])

    def test_if_present_skips_an_absent_record_but_validates_one_that_exists(self):
        import subprocess
        cmd = [sys.executable, str(ROOT / "scripts" / "validate_production_record.py"),
               str(self.run_dir / "final-mockups" / "production-record.json"), "--if-present"]
        self.assertEqual(subprocess.run(cmd, capture_output=True, text=True).returncode, 0)
        self.assertEqual(subprocess.run(cmd[:-1], capture_output=True, text=True).returncode, 2)
        write_json(self.run_dir / "final-mockups" / "production-record.json", {"artifact": "mockup", "sections": []})
        self.assertEqual(subprocess.run(cmd, capture_output=True, text=True).returncode, 1)

    def test_a_record_naming_another_model_than_the_run_fails(self):
        record, stage = self.build()
        self.assertTrue(validate_production_record.check_record(record, base_dir=stage, model="model-b"))
        self.assertEqual(validate_production_record.check_record(record, base_dir=stage, model="model-a"), [])

    def client_logo(self):
        logo = b"client-logo-bytes"
        (self.run_dir / "logo.png").write_bytes(logo)
        write_json(self.run_dir / "brand.json", {"brand_id": "Acme", "palette": {"primary": "#112233"},
                                                 "logo": {"files": "logo.png"}})
        write_json(self.run_dir / "intake.json", {"brand_owner": "Acme", "brand_file": "brand.json"})
        return sha(logo)

    def test_a_record_that_never_expects_the_clients_logo_fails(self):
        self.client_logo()
        record, stage = self.build()
        fails = validate_production_record.check_record(record, base_dir=stage)
        self.assertTrue([f for f in fails if "AF-G2" in f and "no section expects" in f], fails)

    def test_a_logo_check_against_another_file_fails_and_the_right_hash_passes(self):
        good = self.client_logo()
        check = {"logo_ref": "logo.png", "method": "side-by-side", "verdict": "pass", "logo_sha256": "0" * 64}
        record, stage = self.build(logo=check)
        fails = validate_production_record.check_record(record, base_dir=stage)
        self.assertTrue([f for f in fails if "logo_sha256" in f], fails)
        record, stage = self.build(logo=dict(check, logo_sha256=good))
        self.assertEqual(validate_production_record.check_record(record, base_dir=stage), [])

    def test_a_stated_waiver_is_the_only_way_to_omit_the_logo(self):
        self.client_logo()
        record, stage = self.build()
        record["logo_waived"] = "the page carries no logo by the client's direction"
        self.assertEqual(validate_production_record.check_record(record, base_dir=stage), [])


class StockAndSuppliedAssets(Tmp):
    def inventory(self, **entry):
        return {"images": [dict({"id": "IMG-001", "source": "stock"}, **entry)]}

    def record(self, **extra):
        return dict({"supplied_by": "Acme Coaching (the client)", "client_record": "intake.json founder-photo",
                     "supplied_at": "2026-11-02T09:30:00Z", "sha256": SHA}, **extra)

    def errors(self, inventory):
        return validate_image_manifest.validate({"images": []}, inventory_data=inventory)

    def test_stock_without_a_licence_record_fails_image_map_upload(self):
        errs = self.errors(self.inventory())
        self.assertTrue([e for e in errs if "supplied_asset record" in e], errs)
        self.assertTrue([e for e in errs if "no licence record" in e], errs)

    def test_stock_with_a_supplied_record_but_no_licence_still_fails(self):
        errs = self.errors(self.inventory(supplied_asset=self.record()))
        self.assertEqual([e for e in errs if "licence" not in e], [], errs)
        self.assertTrue([e for e in errs if "no licence record" in e])

    def test_control_stock_the_client_supplied_with_its_licence_passes(self):
        inv = self.inventory(supplied_asset=self.record(), licence={"licence_ref": "LIC-2026-114"})
        self.assertEqual(self.errors(inv), [])

    def test_a_supplied_asset_must_name_who_which_record_and_when(self):
        inv = {"images": [{"id": "IMG-001", "source": "supplied-founder-photo",
                           "supplied_asset": {"supplied_by": "Acme", "supplied_at": "yesterday"}}]}
        errs = self.errors(inv)
        for needle in ("client_record", "ISO 8601", "sha256"):
            self.assertTrue([e for e in errs if needle in e], (needle, errs))

    def test_cli_image_map_upload_command_refuses_stock_and_passes_the_control(self):
        import subprocess
        manifest = self.run_dir / "image-map.json"
        write_json(manifest, {"images": []})
        inv = self.run_dir / "inventory.json"

        def run():
            return subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_image_manifest.py"),
                                   str(manifest), "--inventory", str(inv)], capture_output=True, text=True)
        write_json(inv, self.inventory())
        bad = run()
        self.assertEqual(bad.returncode, 1, bad.stdout)
        write_json(inv, self.inventory(supplied_asset=self.record(), licence_ref="LIC-1"))
        good = run()
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)

    def transport(self, entry_extra):
        data = b"filed photo bytes"
        (self.run_dir / "image-generation-qc").mkdir(parents=True, exist_ok=True)
        (self.run_dir / "image-generation-qc" / "Image-01.png").write_bytes(data)
        write_json(self.run_dir / "desktop-wireframe" / "image-inventory.json",
                   self.inventory(**entry_extra(sha(data))))
        task = {"file": "image-generation-qc/Image-01.png", "supplied_asset": True, "sha256": sha(data)}
        return stage_gate._supplied_transport_problems(
            self.run_dir, "image-generation-qc", "IMG-001", "image-generation-qc/Image-01.png", task)

    def test_the_transport_gate_recognises_stock_and_demands_its_records(self):
        problems = self.transport(lambda h: {})
        self.assertTrue([p for p in problems if "supplied_asset record" in p], problems)
        self.assertTrue([p for p in problems if "licence" in p], problems)

    def test_a_hash_taken_from_the_filed_file_alone_does_not_vouch_for_it(self):
        problems = self.transport(lambda h: {"supplied_asset": {
            "supplied_by": "Acme", "client_record": "intake.json", "supplied_at": "2026-11-02T09:30:00Z"},
            "licence_ref": "LIC-1"})
        self.assertTrue([p for p in problems if "recorded when the client supplied" in p], problems)

    def test_control_independent_hash_and_records_pass(self):
        self.assertEqual(self.transport(lambda h: {
            "supplied_asset": self.record(sha256=h), "licence_ref": "LIC-1"}), [])

    def test_a_swapped_file_fails_against_the_hash_the_client_handed_over(self):
        problems = self.transport(lambda h: {"supplied_asset": self.record(sha256=SHA), "licence_ref": "LIC-1"})
        self.assertTrue([p for p in problems if "inventory entry records sha256" in p], problems)


if __name__ == "__main__":
    unittest.main()
