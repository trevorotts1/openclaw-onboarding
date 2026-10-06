#!/usr/bin/env python3
"""F11 — Require complete and independent QC evidence.

QC-F11 matrix (unittest, offline):
  * zero contracts -> FAIL
  * one missing contract -> FAIL
  * an unrelated QC JSON (not keyed to a planned artifact) -> FAIL
  * a same-producer approval -> FAIL
  * an altered-artifact-hash approval -> FAIL (approval invalidated)
  * a self-asserted reviewer (no orchestrator roster entry) -> FAIL
  * a complete, independent, exact-revision matrix -> PASS
  * editing an approved asset AFTER approval invalidates the approval
  * build_manifest describes plain SHA-256 (no "signed" claims)

Run:  python3 -m unittest tests.social-planner.test_f11_qc_matrix -v
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_SKILL_DIR = _REPO_ROOT / "57-social-media-in-a-box"
_RUNNER_PATH = _SKILL_DIR / "run_social_media.py"
assert _RUNNER_PATH.is_file()


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rsm = _load("run_social_media_f11", _RUNNER_PATH)


def _sha_of(run_dir, rel):
    import hashlib
    return rsm._artifact_sha256(run_dir, rel)


def _run_dir(tmp, planned=("caption_mon", "image_mon"), complete=True):
    """A run whose plan declares `planned` artifacts; when `complete`, the
    contracts + independent PASS receipts are staged for every item."""
    rd = Path(tmp) / "run"
    for d in ("working/copy", "working/plan", "working/content/bands",
              "working/content/contracts", "working/qc", "working/media"):
        (rd / d).mkdir(parents=True, exist_ok=True)
    items = [{"artifact_id": a, "revision": 2, "path": "working/content/artifacts/%s.txt" % a}
             for a in planned]
    plan = {"weekOf": "2026-09-07", "themeOfWeek": "Theme", "plannerSheetId": "sheet-1",
            "producerId": "producer-ops-1", "plannedItems": items}
    (rd / "working" / "plan" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    # a bands input that passes prove_bands (evaluate_post: >=300 body words)
    (rd / "working" / "content" / "bands" / "b.json").write_text(
        json.dumps({"body": "word " * 300}), encoding="utf-8")
    for it in items:
        p = rd / it["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(("ARTIFACT %s rev2" % it["artifact_id"]).encode("utf-8"))
    if complete:
        receipts, roster = [], []
        for it in items:
            aid = it["artifact_id"]
            c = rd / "working" / "content" / "contracts" / ("%s.json" % aid)
            # a carousel-shaped contract that passes validate_contract
            c.write_text(json.dumps({
                "kind": "carousel", "platform": "instagram",
                "carouselCaption": "caption text for " + aid,
                "slides": [{"textOnImage": "t", "prompt": "p"}]}), encoding="utf-8")
            receipts.append({
                "artifact_id": aid, "company_id": "co-1", "cycle_id": "cy-1",
                "revision": 2, "sha256": _sha_of(rd, it["path"]),
                "producer_id": "producer-ops-1", "qc_reviewer_id": "reviewer-qc-7",
                "qc_result": "pass", "rubric_scores": {"accuracy": 5, "brand": 5},
                "reviewed_at": "2026-09-08T12:00:00Z"})
            roster.append({"artifact_id": aid, "reviewer_id": "reviewer-qc-7"})
        (rd / "working" / "q c" if False else rd / "working" / "qc").mkdir(exist_ok=True)
        (rd / "working" / "qc" / "qc_receipts.json").write_text(
            json.dumps(receipts), encoding="utf-8")
        (rd / "working" / "qc" / "reviewer_roster.json").write_text(
            json.dumps(roster), encoding="utf-8")
    return rd


class TestMatrixFailures(unittest.TestCase):
    """Each defective matrix MUST fail with AF-SM-QC-MATRIX."""

    def test_zero_contracts_fail(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, complete=False)  # no contracts, no receipts
            ok, msg = rsm._chk_contract_and_bands(rd)
            self.assertFalse(ok)
            self.assertIn("ZERO content contracts", msg)

    def test_one_missing_contract_fails(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, planned=("a1", "a2"), complete=False)
            # stage a complete set for a1 only
            c = rd / "working" / "content" / "contracts" / "a1.json"
            c.write_text(json.dumps({
                "kind": "carousel", "platform": "instagram",
                "carouselCaption": "caption text for a1",
                "slides": [{"textOnImage": "t", "prompt": "p"}]}), encoding="utf-8")
            (rd / "working" / "content" / "artifacts").mkdir(parents=True, exist_ok=True)
            (rd / "working" / "content" / "artifacts" / "a1.txt").write_bytes(b"A1 rev2")
            ok, _msg, failures = rsm._verify_qc_matrix(rd)
            self.assertFalse(ok)
            self.assertTrue(any("a2" in f for f in failures), failures)

    def test_unrelated_qc_json_fails(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, planned=("a1",), complete=True)
            # overwrite the receipts with a file keyed to NOTHING planned
            (rd / "working" / "qc" / "qc_receipts.json").write_text(
                json.dumps([{"artifact_id": "some-other-project-asset",
                             "qc_result": "pass", "revision": 2,
                             "sha256": "0" * 64}]), encoding="utf-8")
            ok, msg = rsm._chk_contract_and_bands(rd)
            self.assertFalse(ok)
            self.assertIn("no QC receipt for planned item", msg)

    def test_same_producer_approval_fails(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, planned=("a1",), complete=True)
            receipts = json.loads((rd / "working" / "qc" / "qc_receipts.json").read_text())
            receipts[0]["qc_reviewer_id"] = "producer-ops-1"  # approved ITSELF
            (rd / "working" / "qc" / "qc_receipts.json").write_text(
                json.dumps(receipts), encoding="utf-8")
            ok, _msg, failures = rsm._verify_qc_matrix(rd)
            self.assertFalse(ok)
            self.assertTrue(any("own producer" in f for f in failures), failures)

    def test_self_asserted_reviewer_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, planned=("a1",), complete=True)
            # a receipt that claims a DIFFERENT reviewer than the orchestrator assigned
            receipts = json.loads((rd / "working" / "qc" / "qc_receipts.json").read_text())
            receipts[0]["qc_reviewer_id"] = "whoever-signed-this"
            (rd / "working" / "qc" / "qc_receipts.json").write_text(
                json.dumps(receipts), encoding="utf-8")
            ok, _msg, failures = rsm._verify_qc_matrix(rd)
            self.assertFalse(ok)
            self.assertTrue(any("self-asserted identity rejected" in f for f in failures),
                            failures)

    def test_missing_roster_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, planned=("a1",), complete=True)
            (rd / "working" / "qc" / "reviewer_roster.json").unlink()
            ok, _msg, failures = rsm._verify_qc_matrix(rd)
            self.assertFalse(ok)
            self.assertTrue(any("orchestrator-assigned reviewer" in f for f in failures),
                            failures)

    def test_altered_hash_approval_fails(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, planned=("a1",), complete=True)
            # EDIT the approved artifact after QC — the approval must invalidate
            (rd / "working" / "content" / "artifacts" / "a1.txt").write_bytes(b"EDITED rev2")
            ok, _msg, failures = rsm._verify_qc_matrix(rd)
            self.assertFalse(ok)
            self.assertTrue(any("INVALIDATED" in f for f in failures), failures)

    def test_wrong_revision_receipt_fails(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, planned=("a1",), complete=True)
            receipts = json.loads((rd / "working" / "qc" / "qc_receipts.json").read_text())
            receipts[0]["revision"] = 1
            (rd / "working" / "qc" / "qc_receipts.json").write_text(
                json.dumps(receipts), encoding="utf-8")
            ok, _msg, failures = rsm._verify_qc_matrix(rd)
            self.assertFalse(ok)
            self.assertTrue(any("revision" in f for f in failures), failures)

    def test_no_planned_items_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, planned=(), complete=False)
            ok, _msg, failures = rsm._verify_qc_matrix(rd)
            self.assertFalse(ok)
            self.assertTrue(any("NO planned artifacts" in f for f in failures), failures)

    def test_missing_receipt_fails(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, planned=("a1",), complete=True)
            (rd / "working" / "qc" / "qc_receipts.json").unlink()
            ok, _msg, failures = rsm._verify_qc_matrix(rd)
            self.assertFalse(ok)


class TestMatrixPass(unittest.TestCase):
    def test_complete_independent_matrix_passes(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, planned=("a1", "a2"), complete=True)
            # a bands input that passes evaluate_post (>=300 body words)
            (rd / "working" / "content" / "bands" / "b.json").write_text(
                json.dumps({"body": "word " * 300}), encoding="utf-8")
            ok, msg = rsm._chk_contract_and_bands(rd)
            self.assertTrue(ok, msg)
            self.assertIn("complete QC matrix", msg)

    def test_edit_after_approval_invalidates(self):
        """The negative→positive cycle: approve, edit, FAIL, re-approve new
        bytes, PASS."""
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, planned=("a1",), complete=True)
            (rd / "working" / "content" / "artifacts" / "a1.txt").write_bytes(b"TAMPERED")
            ok, _m, failures = rsm._verify_qc_matrix(rd)
            self.assertFalse(ok)  # the edit invalidated the approval
            # re-approve: a fresh receipt against the NEW bytes
            receipts = json.loads((rd / "working" / "qc" / "qc_receipts.json").read_text())
            receipts[0]["sha256"] = _sha_of(rd, "working/content/artifacts/a1.txt")
            receipts[0]["revision"] = 3
            plan = json.loads((rd / "working" / "plan" / "plan.json").read_text())
            plan["plannedItems"][0]["revision"] = 3
            (rd / "working" / "qc" / "qc_receipts.json").write_text(
                json.dumps(receipts), encoding="utf-8")
            (rd / "working" / "plan" / "plan.json").write_text(
                json.dumps(plan), encoding="utf-8")
            ok, _m, failures = rsm._verify_qc_matrix(rd)
            self.assertTrue(ok, failures)


class TestTruthfulDescription(unittest.TestCase):
    def test_no_signed_claims_in_certificate_paths(self):
        """build_manifest.py + run_social_media.py describe receipts as plain
        SHA-256 — a hash is tamper-EVIDENT, never 'signed'."""
        manifest_src = (_SKILL_DIR / "scripts" / "build_manifest.py").read_text()
        runner_src = _RUNNER_PATH.read_text()
        self.assertNotIn("signed certificate", manifest_src.lower())
        self.assertNotIn("signed certificate", runner_src.lower())
        self.assertIn("certificate_sha", manifest_src)  # the plain-SHA field stays

    def test_receipt_record_describes_sha256(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, planned=("a1",), complete=True)
            receipts = json.loads((rd / "working" / "qc" / "qc_receipts.json").read_text())
            self.assertEqual(len(receipts[0]["sha256"]), 64)  # a bare SHA-256 hex digest


if __name__ == "__main__":
    unittest.main()