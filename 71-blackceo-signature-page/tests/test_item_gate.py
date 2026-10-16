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
        write(self.run / "mobile-tablet" / "part-01.png", "stub")
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


if __name__ == "__main__":
    unittest.main()
