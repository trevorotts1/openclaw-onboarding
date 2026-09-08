#!/usr/bin/env python3
"""F13 — Make spreadsheet completion depend on real writeback.

QC-F13 matrix (unittest, NO network):
  1. A locally fabricated 20-cell row (the OLD accepted shape) FAILS — the
     receipt must carry company-bound spreadsheet_id, schema_version, stable
     row_key, ACTUAL updatedRange and a content hash.
  2. A nominal "appended" response without a real updatedRange fails.
  3. A real append whose RESPONSE was lost reconciles by readback of the
     stable row — one row, never a second append.
  4. A Sheets outage preserves already-published posts (delivery rows
     independent) and exposes a separate planner-sync task.

Run:  python3 -m unittest tests.social-planner.test_f13_writeback_proof -v
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


rsm = _load("run_social_media_f13", _RUNNER_PATH)


def _good_row():
    row = ["rk-co1-cy1-r3"] + ["w%d" % i for i in range(1, 20)]
    assert len(row) == 20
    return row


def _run_dir(tmp, receipt=None, plan_sheet="sheet-1"):
    rd = Path(tmp) / "run"
    for d in ("working/copy", "working/plan", "working/publish", "delivery"):
        (rd / d).mkdir(parents=True, exist_ok=True)
    cfg = {"brandName": "Brand One", "locationId": "loc-1", "userId": "u-1",
           "timezone": "America/New_York", "status": "Paid"}
    (rd / "working" / "copy" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    (rd / "working" / "execution_mode.json").write_text(
        json.dumps({"mode": "production", "set_by": "trusted-entry", "simulated": False}),
        encoding="utf-8")
    plan = {"weekOf": "2026-09-07", "themeOfWeek": "Theme", "plannerSheetId": plan_sheet,
            "companyId": "co-1", "cycleId": "cy-1", "contentRevision": 3,
            "platforms": ["facebook"],
            "accounts": [{"account_id": "fb-1", "platform": "facebook", "account_name": "FB"}]}
    (rd / "working" / "plan" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    if receipt is not None:
        (rd / "working" / "plan" / "row_appended.json").write_text(
            json.dumps(receipt), encoding="utf-8")
    return rd


def _good_receipt(row=None, **overrides):
    row = row if row is not None else _good_row()
    rec = {
        "row": row,
        "spreadsheet_id": "sheet-1",
        "schema_version": rsm.PLANNER_SCHEMA_VERSION,
        "row_key": "rk-co1-cy1-r3",
        "updatedRange": "Planner!A42:T42",
        "content_hash": rsm._row_content_hash(row),
    }
    rec.update(overrides)
    return rec


class TestFabricatedRowFails(unittest.TestCase):
    """QC-F13: the old accepted shape (a local 20-cell array) fails."""

    def test_local_row_without_receipt_fields_fails(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, receipt={"row": [""] * 20})  # the OLD fixture
            ok, msg = rsm._chk_writeback(rd)
            self.assertFalse(ok)
            self.assertIn("AF-SM-WRITEBACK-PROOF", msg)
            self.assertIn("spreadsheet_id", msg)

    def test_nominal_appended_response_fails(self):
        with tempfile.TemporaryDirectory() as td:
            row = _good_row()
            rec = _good_receipt(row=row)
            rec.pop("updatedRange")
            rec["result"] = "appended"  # the nominal word the API fell back to
            rd = _run_dir(td, receipt=rec)
            ok, msg = rsm._chk_writeback(rd)
            self.assertFalse(ok)
            self.assertIn("updatedRange", msg)

    def test_non_a1_range_fails(self):
        with tempfile.TemporaryDirectory() as td:
            row = _good_row()
            rec = _good_receipt(row=row, updatedRange="appended")
            rd = _run_dir(td, receipt=rec)
            ok, msg = rsm._chk_writeback(rd)
            self.assertFalse(ok)
            self.assertIn("A1 range", msg)

    def test_missing_row_key_fails(self):
        with tempfile.TemporaryDirectory() as td:
            rec = _good_receipt()
            rec.pop("row_key")
            rd = _run_dir(td, receipt=rec)
            ok, msg = rsm._chk_writeback(rd)
            self.assertFalse(ok)
            self.assertIn("row_key", msg)

    def test_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            rec = _good_receipt()
            rec["content_hash"] = "0" * 64
            rd = _run_dir(td, receipt=rec)
            ok, msg = rsm._chk_writeback(rd)
            self.assertFalse(ok)
            self.assertIn("hash", msg.lower())

    def test_unbound_spreadsheet_fails(self):
        with tempfile.TemporaryDirectory() as td:
            rec = _good_receipt(spreadsheet_id="1-other-brand-sheet")
            rd = _run_dir(td, receipt=rec, plan_sheet="sheet-1")
            ok, msg = rsm._chk_writeback(rd)
            self.assertFalse(ok)
            self.assertIn("company-bound", msg)

    def test_wrong_schema_version_fails(self):
        with tempfile.TemporaryDirectory() as td:
            rec = _good_receipt(schema_version="planner-2024-old")
            rd = _run_dir(td, receipt=rec)
            ok, msg = rsm._chk_writeback(rd)
            self.assertFalse(ok)
            self.assertIn("schema_version", msg)


class TestReconcileLostResponse(unittest.TestCase):
    """QC-F13: real append + lost response -> read back, ONE row, no second."""

    def test_readback_completes_writeback(self):
        with tempfile.TemporaryDirectory() as td:
            row = _good_row()
            rd = _run_dir(td, receipt=_good_receipt(row=row))
            readback = {"found": True, "row_key": "rk-co1-cy1-r3",
                        "values": row}
            ok, msg = rsm._reconcile_writeback_readback(rd, readback)
            self.assertTrue(ok, msg)
            rec = json.loads((rd / "working" / "plan" / "row_appended.json").read_text())
            self.assertTrue(rec.get("reconciled") is True)

    def test_readback_marker_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            row = _good_row()
            rd = _run_dir(td, receipt=_good_receipt(row=row))
            readback = {"found": True, "row_key": "rk-co1-cy1-r3",
                        "values": ["rk-some-other-row"] + row[1:]}
            ok, msg = rsm._reconcile_writeback_readback(rd, readback)
            self.assertFalse(ok)
            self.assertIn("row-key marker", msg)

    def test_row_not_found_by_readback_fails(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, receipt=_good_receipt())
            ok, msg = rsm._reconcile_writeback_readback(rd, {"found": False})
            self.assertFalse(ok)
            self.assertIn("NOT complete", msg)

    def test_idempotent_no_second_row(self):
        """Reconciling twice (a retried run) must not duplicate: the receipt is
        marked reconciled once; the row key pins the single row."""
        with tempfile.TemporaryDirectory() as td:
            row = _good_row()
            rd = _run_dir(td, receipt=_good_receipt(row=row))
            readback = {"found": True, "row_key": "rk-co1-cy1-r3", "values": row}
            for _ in range(3):  # retry reconcile any number of times
                ok, _m = rsm._reconcile_writeback_readback(rd, readback)
                self.assertTrue(ok)
            ok, msg = rsm._chk_writeback(rd)
            self.assertTrue(ok, msg)
            self.assertIn("row_key", msg)


class TestSheetsOutagePreservesPublished(unittest.TestCase):
    def test_outage_exposes_planner_sync_task(self):
        with tempfile.TemporaryDirectory() as td:
            rd = Path(td) / "run"
            (rd / "working" / "plan").mkdir(parents=True)
            (rd / "working" / "delivery").mkdir(parents=True)
            # published delivery rows already on record
            rsm._upsert_delivery_row(rd, "co-1", "cy-1", 3, "fb-1",
                                     remote_post_id="post-1", provider_state="published")
            preserved, task = rsm._sheets_outage_recovery(rd)
            self.assertTrue(preserved)
            self.assertIsInstance(task, dict)
            self.assertEqual(task.get("kind"), "planner-sync")
            self.assertEqual(task.get("state"), "open")
            on_disk = json.loads((rd / "working" / "plan" /
                                  "planner_sync_task.json").read_text())
            self.assertEqual(on_disk["task_id"], task["task_id"])
            # the delivery row is UNCHANGED (no repost, no state regression)
            rows = {r["account_id"]: r for r in rsm._delivery_rows(rd)}
            self.assertEqual(rows["fb-1"]["provider_state"], "published")

    def test_no_published_rows_no_task(self):
        with tempfile.TemporaryDirectory() as td:
            rd = Path(td) / "run"
            (rd / "working" / "plan").mkdir(parents=True)
            preserved, task = rsm._sheets_outage_recovery(rd)
            self.assertTrue(preserved)
            self.assertIsNone(task)

    def test_full_checker_requires_readback(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, receipt=_good_receipt())
            ok, msg = rsm._chk_writeback(rd)
            self.assertFalse(ok)  # receipt OK but no readback staged yet
            self.assertIn("NOT complete", msg)
            # stage the readback -> writeback completes
            row = _good_row()
            (rd / "working" / "plan" / "row_readback.json").write_text(
                json.dumps({"found": True, "row_key": "rk-co1-cy1-r3", "values": row}),
                encoding="utf-8")
            ok, msg = rsm._chk_writeback(rd)
            self.assertTrue(ok, msg)


if __name__ == "__main__":
    unittest.main()