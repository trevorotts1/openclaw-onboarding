#!/usr/bin/env python3
"""Acceptance proof for the interactive-owner fulfillment commands (PBB-698 T-25).

The BUILD commit that added ``record-basis`` and ``fulfill`` to
``interactive_owner.py`` shipped 163 production lines that no test reached: the
FAIL receipt (PBB-1024, defect D1) measured 0 references to ``interactive_owner``
in ``test_direct_fulfillment.py`` and 0 references to ``fulfill`` or
``record-basis`` in ``test_interactive_owner.py``, while the branch's own CI
comment claimed a sibling suite covered the call site. This file is that
sibling suite, and it drives the CLI surface the claim named:

* a stale tap and an unknown control are refused BEFORE any outbox row, ledger
  file, journal line or transport call exists (resolution runs first);
* an accepted step with no recorded basis refuses rather than minting one;
* the promised item's purpose is pinned to ORIGINAL_GIFT and the basis must
  name the same item/version;
* the once-only path: one send, then ``already_satisfied`` with the journal
  still holding exactly one line.

Run: python3 38-conversational-ai-system/tools/tests/test_interactive_owner_fulfillment.py
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import interactive_owner as owner  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "interactive-owner"

ITEM_ID = "gift_001"
ITEM_VERSION = "1"
CONTENT = b"original gift content, v1"
CONTENT_SHA = hashlib.sha256(CONTENT).hexdigest()


def accepted_event():
    """A tap the canonical fixture contract accepts (step pick_time, gen 3)."""
    return {
        "kind": "control",
        "step_id": "pick_time",
        "control_id": "tue_10am",
        "generation": 3,
    }


def promised_item(**overrides):
    doc = {
        "item_id": ITEM_ID,
        "version": ITEM_VERSION,
        "content_sha256": CONTENT_SHA,
        "approved": True,
        "purpose": owner.PURPOSE_ORIGINAL_GIFT,
        "content_uri": "https://example.invalid/gift.pdf",
    }
    doc.update(overrides)
    return doc


def delivery_basis(**overrides):
    doc = {
        "tenant_id": "tenant-alpha",
        "canonical_contact_id": "c_001",
        "item_id": ITEM_ID,
        "version": ITEM_VERSION,
        "basis": "requested_in_conversation",
        "actor": "owner",
        "evidence": "thread-1",
        "channel": "SMS",
        "address": "+15550100698",
    }
    doc.update(overrides)
    return doc


class FulfillmentCommandsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="interactive-owner-fulfill-"))
        self.outbox = self.tmp / "outbox.sqlite3"
        self.ledger = self.tmp / "ledger.sqlite3"
        self.journal = self.tmp / "journal.jsonl"
        self.contract = FIXTURES / "valid.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── helpers ────────────────────────────────────────────────────────────
    def write(self, name, doc):
        path = self.tmp / name
        path.write_text(json.dumps(doc), encoding="utf-8")
        return str(path)

    def run_cli(self, *argv):
        buffer = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(err):
            code = owner.main(list(argv))
        return code, buffer.getvalue(), err.getvalue()

    def fulfill_argv(self, contract, event, item, basis):
        return (
            "fulfill",
            "--contract", str(contract),
            "--event", json.dumps(event),
            "--outbox", str(self.outbox),
            "--ledger", str(self.ledger),
            "--journal", str(self.journal),
            "--item", item,
            "--basis", basis,
        )

    def journal_rows(self):
        if not self.journal.exists():
            return []
        text = self.journal.read_text(encoding="utf-8")
        return [line for line in text.splitlines() if line.strip()]

    def outbox_rows(self, sql):
        if not self.outbox.exists():
            return []
        conn = sqlite3.connect(str(self.outbox))
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    # ── D1: refused before any effect exists ───────────────────────────────
    def test_stale_tap_is_refused_before_any_outbox_ledger_or_journal_exists(self):
        stale = dict(accepted_event(), generation=2)
        code, out, _ = self.run_cli(*self.fulfill_argv(
            self.contract, stale,
            self.write("item.json", promised_item()),
            self.write("basis.json", delivery_basis()),
        ))
        payload = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(payload["code"], owner.STALE_TAP)
        self.assertFalse(self.outbox.exists(), "a refused tap created the outbox")
        self.assertFalse(self.ledger.exists(), "a refused tap created the basis ledger")
        self.assertEqual(self.journal_rows(), [])

    def test_unknown_control_is_refused_before_any_outbox_row(self):
        code, out, _ = self.run_cli(*self.fulfill_argv(
            self.contract, dict(accepted_event(), control_id="never_rendered"),
            self.write("item.json", promised_item()),
            self.write("basis.json", delivery_basis()),
        ))
        payload = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(payload["code"], owner.UNKNOWN_CONTROL)
        self.assertFalse(self.outbox.exists())
        self.assertFalse(self.ledger.exists())
        self.assertEqual(self.journal_rows(), [])

    def test_unknown_step_is_refused_before_any_outbox_row(self):
        code, out, _ = self.run_cli(*self.fulfill_argv(
            self.contract, dict(accepted_event(), step_id="no_such_step"),
            self.write("item.json", promised_item()),
            self.write("basis.json", delivery_basis()),
        ))
        payload = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(payload["code"], owner.UNKNOWN_STEP)
        self.assertFalse(self.outbox.exists())
        self.assertEqual(self.journal_rows(), [])

    # ── D1: no basis, no send; the basis is never minted by fulfill ────────
    def test_accepted_step_without_a_recorded_basis_refuses_and_sends_nothing(self):
        code, out, _ = self.run_cli(*self.fulfill_argv(
            self.contract, accepted_event(),
            self.write("item.json", promised_item()),
            self.write("basis.json", delivery_basis()),
        ))
        payload = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(payload["reason"], "no_delivery_basis")
        self.assertEqual(self.outbox_rows("SELECT COUNT(*) FROM outbox_actions")[0][0], 0)
        self.assertEqual(self.journal_rows(), [])

    # ── D1: ORIGINAL_GIFT purpose pin ──────────────────────────────────────
    def test_promised_item_purpose_must_be_original_gift(self):
        code, out, err = self.run_cli(*self.fulfill_argv(
            self.contract, accepted_event(),
            self.write("item.json", promised_item(purpose="UPSELL")),
            self.write("basis.json", delivery_basis()),
        ))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("purpose", err)
        self.assertFalse(self.outbox.exists())
        self.assertFalse(self.ledger.exists())

    def test_basis_naming_a_different_item_is_a_usage_error(self):
        code, out, err = self.run_cli(*self.fulfill_argv(
            self.contract, accepted_event(),
            self.write("item.json", promised_item()),
            self.write("basis.json", delivery_basis(version="2")),
        ))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("different promised item", err)

    # ── D1: the once-only path ─────────────────────────────────────────────
    def test_record_basis_then_fulfill_sends_once_and_never_twice(self):
        code, out, _ = self.run_cli(
            "record-basis",
            "--ledger", str(self.ledger),
            "--basis", self.write("basis.json", delivery_basis()),
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["command"], "record-basis")

        item = self.write("item.json", promised_item())
        basis = self.write("basis.json", delivery_basis())
        code, out, _ = self.run_cli(
            *self.fulfill_argv(self.contract, accepted_event(), item, basis))
        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "sent")
        self.assertEqual(payload["delivery_status"], "accepted")
        self.assertEqual(payload["item_id"], ITEM_ID)
        self.assertEqual(payload["step"]["step_id"], "pick_time")
        self.assertEqual(payload["step"]["input"], "control")
        self.assertIsNotNone(payload["action_id"])

        purposes = self.outbox_rows("SELECT purpose FROM outbox_actions")
        self.assertEqual(len(purposes), 1, purposes)
        self.assertEqual(purposes[0][0], "original_gift")

        rows = self.journal_rows()
        self.assertEqual(len(rows), 1)
        receipt = json.loads(rows[0])
        self.assertEqual(receipt["destination"]["address"], "+15550100698")
        self.assertEqual(receipt["item_id"], ITEM_ID)
        self.assertEqual(receipt["content_sha256"], CONTENT_SHA)

        code, out, _ = self.run_cli(
            *self.fulfill_argv(self.contract, accepted_event(), item, basis))
        second = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(second["status"], "already_satisfied")
        self.assertEqual(second["action_id"], payload["action_id"])
        self.assertEqual(len(self.journal_rows()), 1, "a second send reached the transport")
        self.assertEqual(
            self.outbox_rows("SELECT COUNT(*) FROM outbox_actions")[0][0], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
