#!/usr/bin/env python3
"""Acceptance tests for Item 20 (item-level gates), run against a stage_gate.py
that has stage-gate-item-commands.patch applied (the S7 stream ships the patch;
these tests assemble S1's tree + the patch in a scratch dir; see
references/item-gate-spec.md).

Covered:
- check-item / close-item / block-item on the two itemized stages.
- The weld cut: a generation item opens when ITS prompt item closes, while
  stage-level `check` for image-generation-qc still refuses (unchanged).
- close-item verifies the item's validators, v2 review file (per-artifact
  scoring), and, for generation items, the item's Skill 74 transport entry.
- Stage close fan-in: an itemized stage refuses to close while any item is
  open or blocked, naming the item.
- Item transitions append to private/run-events.jsonl.
- Non-itemized stages reject item commands.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "stage_gate.py"
WRITE_REVIEW = ROOT / "scripts" / "write_review.py"
PY = sys.executable
sys.path.insert(0, str(ROOT / "scripts"))
import stage_gate  # noqa: E402  (direct transport-slice calls below)

LONG_NOTE = "Checked against the artifact bytes and the stage rubric line by line."
PNG_1PX = __import__("base64").b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def write(path: Path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")


def fixture_contract(td: Path) -> Path:
    contract = json.loads((ROOT / "references" / "stage-contract.json").read_text())
    for stage in contract["stages"].values():
        stage["validators"] = ["gate:noop"]
    path = td / "contract-fixture.json"
    path.write_text(json.dumps(contract, indent=2), encoding="utf-8")
    return path


def scores_json(**criteria):
    return json.dumps({name: {"score": score, "note": LONG_NOTE}
                       for name, score in criteria.items()})


def run_gate(contract, *args):
    env = {**os.environ, "STAGE_GATE_CONTRACT": str(contract)}
    return subprocess.run([PY, str(GATE), *args], text=True, capture_output=True, env=env)


def run_write_review(contract, run, stage, item, reviewer_session, scores,
                     author_session="sess-author-1"):
    env = {k: v for k, v in os.environ.items()
           if k not in ("OPENCLAW_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID")}
    env["OPENCLAW_SESSION_ID"] = reviewer_session
    env["STAGE_GATE_CONTRACT"] = str(contract)
    return subprocess.run([PY, str(WRITE_REVIEW), str(run), stage, item,
                           "--scores", scores, "--verdict", "pass",
                           "--author-session", author_session,
                           "--performed-check",
                           "Read the artifact end to end and scored each "
                           "rubric criterion against what is on disk.",
                           "--next-current-artifact",
                           "the artifact named in this review"],
                          text=True, capture_output=True, env=env)


def put_receipt(run, stage, **kw):
    receipt = {"stage": stage, "status": "pass", "author_agent": "builder-agent",
               "author_session": "sess-author-1",
               "started_at": "2026-10-13T10:00:00+00:00",
               "finished_at": "2026-10-13T10:30:00+00:00", "artifacts": []}
    receipt.update(kw)
    write(run / "private" / "receipts" / f"{stage}.json", json.dumps(receipt))


class ItemGateTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="item-gate-"))
        self.contract = fixture_contract(self.td)
        self.run = self.td / "run"
        # Assembly fix (S8): the Item 13 layout gate (S3 Request 2,
        # applied at assembly) refuses layout-stage closes without the
        # owner-supplied reference files or a recorded waiver; this
        # fixture predates the gate, so it records the waiver.
        write(self.run / "intake.json", json.dumps({"layout_waivers": [
            {"gate": "layout-references",
             "reason": "test fixture: owner-supplied Item 13 reference files absent"}]}))
        write(self.run / "private" / "brand.json",
              json.dumps({"fonts": {"display": "Test", "body": "Test", "accent": "Test"}}))
        proc = run_gate(self.contract, "init", str(self.run))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # Close mobile-tablet directly (close does not consult upstream deps).
        # Update Plan Item 11: the stage delivers the spec image set
        # (section slices, stitched full-page PNG, combined PDF); the
        # retired part-*.png export no longer satisfies the contract.
        write(self.run / "mobile-tablet" / "section-01.png", "stub")
        write(self.run / "mobile-tablet" / "wireframe-full.png", "stub")
        write(self.run / "mobile-tablet" / "wireframe.pdf", "stub")
        write(self.run / "mobile-tablet" / "tablet-rules.md", "rules")
        write(self.run / "mobile-tablet" / "section-plan.json", "{}")
        put_receipt(self.run, "mobile-tablet")
        proc = run_write_review(self.contract, self.run, "mobile-tablet", "stage",
                                "sess-rev-mt", scores_json(reflow=9))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = run_gate(self.contract, "close", str(self.run), "mobile-tablet")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # Inventory + bible: the prompt items' own dependencies.
        write(self.run / "desktop-wireframe" / "image-inventory.json",
              json.dumps({"images": [{"id": "IMG-001"}, {"id": "IMG-002"}]}))
        write(self.run / "visual-mockup" / "page-visual-bible.json",
              json.dumps({"selection_mode": "SECRET_SAUCE_ONLY"}))
        # Assembly fix (S8): GCR-S2-4 (Item 10) requires a governing
        # style selection record before the prompts stage can close;
        # this fixture predates the requirement.
        write(self.run / "image-inventory-prompts" / "style-selection.json",
              json.dumps({"schema_version": 1, "selections": [
                  {"applies_to": "all", "source_library": "image-guide-sauce-only",
                   "style_id": "signature-grade", "branded_name": "Signature Grade"}]}))
        put_receipt(self.run, "image-inventory-prompts")

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def close_prompt_item(self, item="IMG-001"):
        write(self.run / "image-inventory-prompts" / f"{item}.txt", "prompt body")
        write(self.run / "image-inventory-prompts" / "prompt-manifest.json", "{}")
        proc = run_write_review(self.contract, self.run, "image-inventory-prompts",
                                item, "sess-rev-prompt",
                                scores_json(fidelity=9, craft=9))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return run_gate(self.contract, "close-item", str(self.run),
                        "image-inventory-prompts", item)

    def test_check_item_prompt_ok_and_unknown_item_named(self):
        proc = run_gate(self.contract, "check-item", str(self.run),
                        "image-inventory-prompts", "IMG-001")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = run_gate(self.contract, "check-item", str(self.run),
                        "image-inventory-prompts", "IMG-099")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("unknown item", proc.stdout + proc.stderr)

    def test_generation_item_blocked_until_its_prompt_closes(self):
        proc = run_gate(self.contract, "check-item", str(self.run),
                        "image-generation-qc", "IMG-001")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("is not closed", proc.stdout + proc.stderr)

    def test_weld_cut_and_stage_check_unchanged(self):
        proc = self.close_prompt_item("IMG-001")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # The generation item for image 1 opens NOW...
        proc = run_gate(self.contract, "check-item", str(self.run),
                        "image-generation-qc", "IMG-001")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # ...while image 2's generation item still waits for its own prompt.
        proc = run_gate(self.contract, "check-item", str(self.run),
                        "image-generation-qc", "IMG-002")
        self.assertEqual(proc.returncode, 1)
        # Stage-level check for image-generation-qc still refuses: the whole
        # dependency chain (prompts stage closed) is required there.
        proc = run_gate(self.contract, "check", str(self.run), "image-generation-qc")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("image-inventory-prompts", proc.stdout + proc.stderr)

    def test_close_item_records_state_and_event(self):
        proc = self.close_prompt_item("IMG-001")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        state = json.loads((self.run / "private" / "state.json").read_text())
        entry = state["items"]["image-inventory-prompts"]["IMG-001"]
        self.assertEqual(entry["status"], "closed")
        self.assertIn("image-inventory-prompts/IMG-001.txt", entry["artifact_hashes"])
        self.assertEqual(entry["review"],
                         "private/reviews/image-inventory-prompts/IMG-001.review.json")
        events = [json.loads(l) for l in
                  (self.run / "private" / "run-events.jsonl").read_text().splitlines()]
        # S8 assembly: event lines carry the frozen Item 24 envelope
        # (event_type / item_id), not the pre-freeze shorthand keys.
        self.assertTrue(any(e["event_type"] == "item_closed" and e["item_id"] == "IMG-001"
                            for e in events))
        # Idempotent: closing again with unchanged bytes passes.
        proc = run_gate(self.contract, "close-item", str(self.run),
                        "image-inventory-prompts", "IMG-001")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("already closed", proc.stdout)

    def test_close_item_records_prompt_budget(self):
        # Decision 1: the prompt stage gate records the validator's
        # budget block on the item's close entry. The fixture prompt
        # ("prompt body", 11 characters) sits below the floor, so the
        # record carries the BELOW_FLOOR verdict and budget exit 3;
        # recording is best-effort and never blocks the close.
        proc = self.close_prompt_item("IMG-001")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        state = json.loads((self.run / "private" / "state.json").read_text())
        entry = state["items"]["image-inventory-prompts"]["IMG-001"]
        record = entry["prompt_budget"]
        self.assertEqual(record["characters"], 11)
        self.assertEqual(record["budget"]["status"], "BELOW_FLOOR")
        self.assertEqual(record["budget"]["budget_exit"], 3)

    def test_close_item_review_per_artifact_average(self):
        # One strong and one weak criterion: mean 8.0 < 8.5 average floor.
        write(self.run / "image-inventory-prompts" / "IMG-001.txt", "prompt body")
        write(self.run / "image-inventory-prompts" / "prompt-manifest.json", "{}")
        proc = run_write_review(self.contract, self.run, "image-inventory-prompts",
                                "IMG-001", "sess-rev-prompt",
                                scores_json(fidelity=9, craft=7))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = run_gate(self.contract, "close-item", str(self.run),
                        "image-inventory-prompts", "IMG-001")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("below minimum", proc.stdout + proc.stderr)

    def test_close_generation_item_with_transport(self):
        proc = self.close_prompt_item("IMG-001")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        write(self.run / "image-generation-qc" / "Image-001.png", PNG_1PX)
        write(self.run / "image-generation-qc" / "image-qc.json", "{}")
        write(self.run / "receipts" / "kie74" / "task-001.json", json.dumps({
            "provider": "kie", "adapter": "74-kie-live-adapter",
            "adapter_mode": "active", "backend": "native-live",
            "model_id": "gpt-image-2", "task_id": "task-001", "state": "success",
            "saved_paths": ["image-generation-qc/Image-001.png"],
            "warnings": [], "data": {}}))
        put_receipt(self.run, "image-generation-qc",
                    cost={"provider": "kie", "credits_before": 100.0,
                          "credits_after": 96.0},
                    transport={"skill": "74-kie-live-adapter",
                               "policy": "66-kie-image", "mode": "active",
                               "tasks": [{"file": "image-generation-qc/Image-001.png",
                                          "task_id": "task-001",
                                          "preflight_ok": True, "budget_exit": 0,
                                          "model_id": "gpt-image-2",
                                          "model_source": "latest-family",
                                          "requested_ratio": "16:9",
                                          "generated_ratio": "16:9"}]})
        proc = run_write_review(self.contract, self.run, "image-generation-qc",
                                "Image-001", "sess-rev-img",
                                scores_json(fidelity=9, craft=9))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = run_gate(self.contract, "close-item", str(self.run),
                        "image-generation-qc", "IMG-001")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        state = json.loads((self.run / "private" / "state.json").read_text())
        entry = state["items"]["image-generation-qc"]["IMG-001"]
        self.assertEqual(entry["status"], "closed")
        self.assertEqual(entry["review_item"], "Image-001")

    def test_close_generation_item_missing_transport_entry_fails(self):
        proc = self.close_prompt_item("IMG-001")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        write(self.run / "image-generation-qc" / "Image-001.png", PNG_1PX)
        write(self.run / "image-generation-qc" / "image-qc.json", "{}")
        put_receipt(self.run, "image-generation-qc",
                    cost={"provider": "kie", "credits_before": 100.0,
                          "credits_after": 96.0})
        proc = run_gate(self.contract, "close-item", str(self.run),
                        "image-generation-qc", "IMG-001")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("transport", proc.stdout + proc.stderr)

    def test_stage_close_fan_in_names_open_and_blocked_items(self):
        proc = self.close_prompt_item("IMG-001")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = run_gate(self.contract, "block-item", str(self.run),
                        "image-inventory-prompts", "IMG-002",
                        "--reason", "prompt author failed twice: validation")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = run_gate(self.contract, "close", str(self.run),
                        "image-inventory-prompts")
        self.assertEqual(proc.returncode, 1)
        out = proc.stdout + proc.stderr
        self.assertIn("fan-in", out)
        self.assertIn("IMG-002", out)
        self.assertIn("blocked", out)

    def test_item_commands_reject_non_itemized_stage(self):
        proc = run_gate(self.contract, "check-item", str(self.run), "copy", "IMG-001")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not itemized", proc.stdout + proc.stderr)


PNG_1PX_SHA = hashlib.sha256(PNG_1PX).hexdigest()
GENERATED_TASK = {"file": "image-generation-qc/Image-001.png",
                  "task_id": "task-001",
                  "preflight_ok": True, "budget_exit": 0,
                  "model_id": "gpt-image-2",
                  "model_source": "latest-family",
                  "requested_ratio": "16:9",
                  "generated_ratio": "16:9"}


class SuppliedAssetGateTest(unittest.TestCase):
    """Item 3 supplied-asset machinery in stage_gate.py: supplied
    inventory entries (source begins with "supplied") are exempt from
    style-selection governance, and their transport slice is a
    supplied-asset entry verified against the filed bytes."""

    def build_run(self, td_name, supplied=True):
        td = self.td / td_name
        td.mkdir(parents=True, exist_ok=True)
        contract = fixture_contract(td)
        run = td / "run"
        write(run / "intake.json", json.dumps({"layout_waivers": [
            {"gate": "layout-references",
             "reason": "test fixture: owner-supplied Item 13 reference files absent"}]}))
        write(run / "private" / "brand.json",
              json.dumps({"fonts": {"display": "Test", "body": "Test", "accent": "Test"}}))
        proc = run_gate(contract, "init", str(run))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # Update Plan Item 11: the stage delivers the spec image set
        # (section slices, stitched full-page PNG, combined PDF); the
        # retired part-*.png export no longer satisfies the contract.
        write(run / "mobile-tablet" / "section-01.png", "stub")
        write(run / "mobile-tablet" / "wireframe-full.png", "stub")
        write(run / "mobile-tablet" / "wireframe.pdf", "stub")
        write(run / "mobile-tablet" / "tablet-rules.md", "rules")
        write(run / "mobile-tablet" / "section-plan.json", "{}")
        put_receipt(run, "mobile-tablet")
        proc = run_write_review(contract, run, "mobile-tablet", "stage",
                                "sess-rev-mt", scores_json(reflow=9))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = run_gate(contract, "close", str(run), "mobile-tablet")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        img2 = {"id": "IMG-002"}
        if supplied:
            img2.update({"source": "supplied-founder-photo",
                         "sha256": PNG_1PX_SHA, "requested_ratio": "4:5"})
        write(run / "desktop-wireframe" / "image-inventory.json",
              json.dumps({"images": [{"id": "IMG-001"}, img2]}))
        write(run / "visual-mockup" / "page-visual-bible.json",
              json.dumps({"selection_mode": "SECRET_SAUCE_ONLY"}))
        # The selection governs ONLY IMG-001; IMG-002 is governed only
        # if it is a generated entry.
        write(run / "image-inventory-prompts" / "style-selection.json",
              json.dumps({"schema_version": 1, "selections": [
                  {"applies_to": ["IMG-001"],
                   "source_library": "photographers",
                   "style_id": "some-style", "branded_name": "Some Style"}]}))
        put_receipt(run, "image-inventory-prompts")
        return contract, run

    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="supplied-gate-"))
        self.contract, self.run = self.build_run("main", supplied=True)

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def close_prompt_item(self, contract, run, item):
        write(run / "image-inventory-prompts" / f"{item}.txt", "prompt body")
        write(run / "image-inventory-prompts" / "prompt-manifest.json", "{}")
        proc = run_write_review(contract, run, "image-inventory-prompts",
                                item, "sess-rev-prompt",
                                scores_json(fidelity=9, craft=9))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return run_gate(contract, "close-item", str(run),
                        "image-inventory-prompts", item)

    def put_generation_receipt(self, run, supplied_entry):
        write(run / "receipts" / "kie74" / "task-001.json", json.dumps({
            "provider": "kie", "adapter": "74-kie-live-adapter",
            "adapter_mode": "active", "backend": "native-live",
            "model_id": "gpt-image-2", "task_id": "task-001", "state": "success",
            "saved_paths": ["image-generation-qc/Image-001.png"],
            "warnings": [], "data": {}}))
        put_receipt(run, "image-generation-qc",
                    cost={"provider": "kie", "credits_before": 100.0,
                          "credits_after": 96.0},
                    transport={"skill": "74-kie-live-adapter",
                               "policy": "66-kie-image", "mode": "active",
                               "tasks": [GENERATED_TASK, supplied_entry]})

    def close_generation_item(self, contract, run, item, stem):
        proc = run_write_review(contract, run, "image-generation-qc",
                                stem, "sess-rev-img",
                                scores_json(fidelity=9, craft=9))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return run_gate(contract, "close-item", str(run),
                        "image-generation-qc", item)

    def stage_supplied_files(self, run, supplied_sha=PNG_1PX_SHA):
        write(run / "image-generation-qc" / "Image-001.png", PNG_1PX)
        write(run / "image-generation-qc" / "Image-002.png", PNG_1PX)
        write(run / "image-generation-qc" / "image-qc.json", "{}")
        return {"file": "image-generation-qc/Image-002.png",
                "supplied_asset": True, "sha256": supplied_sha}

    def test_prompts_stage_closes_with_supplied_item_ungoverned(self):
        for item in ("IMG-001", "IMG-002"):
            proc = self.close_prompt_item(self.contract, self.run, item)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = run_gate(self.contract, "close", str(self.run),
                        "image-inventory-prompts")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_prompts_stage_close_names_ungoverned_generated_item(self):
        # Control: the same fixture with IMG-002 NOT supplied must
        # fail the stage close, naming IMG-002's missing governance.
        contract, run = self.build_run("control", supplied=False)
        for item in ("IMG-001", "IMG-002"):
            proc = self.close_prompt_item(contract, run, item)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = run_gate(contract, "close", str(run), "image-inventory-prompts")
        self.assertEqual(proc.returncode, 1)
        out = proc.stdout + proc.stderr
        self.assertIn("IMG-002", out)
        self.assertIn("no governing style selection", out)

    def test_close_supplied_generation_item_with_supplied_entry(self):
        proc = self.close_prompt_item(self.contract, self.run, "IMG-002")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        entry = self.stage_supplied_files(self.run)
        self.put_generation_receipt(self.run, entry)
        proc = self.close_generation_item(self.contract, self.run,
                                          "IMG-002", "Image-002")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        state = json.loads((self.run / "private" / "state.json").read_text())
        self.assertEqual(
            state["items"]["image-generation-qc"]["IMG-002"]["status"],
            "closed")

    def test_supplied_transport_sha_mismatch_fails_by_name(self):
        proc = self.close_prompt_item(self.contract, self.run, "IMG-002")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        entry = self.stage_supplied_files(self.run, supplied_sha="0" * 64)
        self.put_generation_receipt(self.run, entry)
        proc = run_gate(self.contract, "close-item", str(self.run),
                        "image-generation-qc", "IMG-002")
        self.assertEqual(proc.returncode, 1)
        out = proc.stdout + proc.stderr
        self.assertIn("IMG-002", out)
        self.assertIn("supplied-asset sha256 mismatch", out)

    def missing_supplied_file_receipt(self, run):
        """A generation receipt whose supplied entry (IMG-002) names
        image-generation-qc/Image-002.png, while that file is
        deliberately NOT written to disk (Item 3 review defect D1)."""
        write(run / "image-generation-qc" / "Image-001.png", PNG_1PX)
        write(run / "image-generation-qc" / "image-qc.json", "{}")
        entry = {"file": "image-generation-qc/Image-002.png",
                 "supplied_asset": True, "sha256": PNG_1PX_SHA}
        self.put_generation_receipt(run, entry)
        return json.loads(
            (run / "private" / "receipts" / "image-generation-qc.json"
             ).read_text(encoding="utf-8"))

    def test_supplied_missing_file_fails_by_name_at_item_level(self):
        # D1 pin, item level (the review's probe C8 path):
        # check_item_transport must reach the designed supplied-asset
        # failure naming the missing file, not "transport.tasks has no
        # entry for None", and must still fail (the problems list is
        # exactly the designed line).
        receipt = self.missing_supplied_file_receipt(self.run)
        problems = stage_gate.check_item_transport(
            self.run, "image-generation-qc", "IMG-002", receipt)
        self.assertEqual(problems, [
            "stage image-generation-qc item IMG-002 "
            "(image-generation-qc/Image-002.png): supplied asset file "
            "image-generation-qc/Image-002.png is not on disk"])

    def test_supplied_missing_file_fails_by_name_at_stage_level(self):
        # D1 pin, stage level (the review's probe S3 path):
        # check_transport must divert the supplied entry to the
        # supplied-asset slice, producing the designed not-on-disk line
        # naming the file (after the pre-existing cover line, which
        # also names it), with no generic generation-task problems
        # sprayed for the supplied entry, and must still fail.
        receipt = self.missing_supplied_file_receipt(self.run)
        problems = stage_gate.check_transport(
            self.run, "image-generation-qc", receipt)
        self.assertEqual(problems, [
            "stage image-generation-qc: transport.tasks cover "
            "['image-generation-qc/Image-001.png', "
            "'image-generation-qc/Image-002.png'] but the stage has "
            "['image-generation-qc/Image-001.png']",
            "stage image-generation-qc item IMG-002 "
            "(image-generation-qc/Image-002.png): supplied asset file "
            "image-generation-qc/Image-002.png is not on disk"])
        self.assertFalse(any("transport.tasks[1]" in p for p in problems))

    def test_supplied_item_with_generation_task_entry_fails(self):
        proc = self.close_prompt_item(self.contract, self.run, "IMG-002")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.stage_supplied_files(self.run)
        task_entry = dict(GENERATED_TASK)
        task_entry["file"] = "image-generation-qc/Image-002.png"
        task_entry["task_id"] = "task-002"
        self.put_generation_receipt(self.run, task_entry)
        proc = run_gate(self.contract, "close-item", str(self.run),
                        "image-generation-qc", "IMG-002")
        self.assertEqual(proc.returncode, 1)
        out = proc.stdout + proc.stderr
        self.assertIn("supplied_asset: true", out)

    def test_generation_stage_closes_with_mixed_transport(self):
        for item in ("IMG-001", "IMG-002"):
            proc = self.close_prompt_item(self.contract, self.run, item)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # The prompts stage closes first (generation depends on it).
        proc = run_gate(self.contract, "close", str(self.run),
                        "image-inventory-prompts")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        entry = self.stage_supplied_files(self.run)
        self.put_generation_receipt(self.run, entry)
        proc = self.close_generation_item(self.contract, self.run,
                                          "IMG-001", "Image-001")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.close_generation_item(self.contract, self.run,
                                          "IMG-002", "Image-002")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = run_gate(self.contract, "close", str(self.run),
                        "image-generation-qc")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        state = json.loads((self.run / "private" / "state.json").read_text())
        self.assertEqual(state["stages"]["image-generation-qc"]["status"],
                         "closed")


if __name__ == "__main__":
    unittest.main()
