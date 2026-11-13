#!/usr/bin/env python3
"""PD-081 acceptance gate: a web "Signature" choice starts NO build until the
8 questions have been answered in chat.

Run: python3 test/test_pd081_signature_block.py

Rows (01-BUILD-SPEC.md, PD-081):
  A1  signature intake, no working/copy/sp_intake.json -> rc 8, no board call,
      no launcher call; the ledger is blocked_actionable with the spec reason.
  A2  the same signature intake WITH sp_intake.json -> proceeds to the board.
  A3  a from-scratch intake is unaffected (proceeds to the board).
  A4  pages/index.html and deployed-r2/public/index.html are byte-identical.

The durable-state machine (launch_ledger.py) is the REAL production module.
The run-dir writer, board, launcher and notifier are stubs that record calls,
so "no board call / no launcher call" is observed, not inferred.
"""
from __future__ import annotations

import contextlib
import io
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
APP = HERE.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "bridge"))

import intake_bridge as ib  # noqa: E402
import launch_ledger as _ll  # noqa: E402

FAST_POLICY = {
    "backoff_base_s": 0.0,
    "backoff_cap_s": 0.0,
    "max_attempts": 10,
    "notify_thresholds": (3, 7),
    "claim_ttl_s": 120.0,
}


def _intake(presentation_type: str) -> dict:
    return {
        "intake_session_id": "sess-pd081",
        "deck_type": "signature_presentation",
        "presentation_type": presentation_type,
        "requester_chat_id": "12345",
        "answers": {"presentation_type": presentation_type},
        "deck_brief": {},
        "pre_presentation_capture": {},
    }


class _Recorder:
    """Stubs that record every call the bridge would make to the outside."""

    def __init__(self):
        self.record_calls = 0
        self.board_calls: list[dict] = []
        self.launch_calls: list[dict] = []
        self.notifications: list[tuple] = []

    def record(self, run_dir, intake, verbose):
        self.record_calls += 1
        return True

    def board(self, run_dir, intake, session_id, doc, policy):
        self.board_calls.append({"slug": str(run_dir)})
        return "registered", "CC-STUB-1"

    def launch(self, run_dir, intake, session_id, doc, policy, verbose):
        self.launch_calls.append({"slug": str(run_dir)})
        return "acknowledged", "stub worker acknowledged"

    def notifier(self):
        rec = self

        def _notify(kind, submission_id, message):
            rec.notifications.append((kind, submission_id, message))

        return _notify


class Pd081SignatureBlockTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = pathlib.Path(self._tmp.name) / "pres-runs" / "run-pd081"
        self.run_dir.mkdir(parents=True)
        self.session_id = "sess-pd081"
        self.rec = _Recorder()
        self._patches = [
            mock.patch.object(ib, "_record_run_dir_files", self.rec.record),
            mock.patch.object(ib, "_ensure_board_card", self.rec.board),
            mock.patch.object(ib, "_dispatch_launch", self.rec.launch),
            mock.patch.object(ib, "_make_notifier", self.rec.notifier),
        ]
        for p in self._patches:
            p.start()
        self.doc = _ll.acquire_new(self.run_dir, self.session_id, holder={})

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        self._tmp.cleanup()

    def _drive(self, presentation_type: str) -> dict:
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return ib._drive_submission_claimed(
                self.run_dir, _intake(presentation_type), self.session_id,
                FAST_POLICY, verbose=False, doc=self.doc)

    # A1 -----------------------------------------------------------------
    def test_a1_signature_without_sp_intake_blocks_before_the_board(self):
        report = self._drive("signature")
        self.assertEqual(report.get("_rc"), 8, report)
        self.assertEqual(report.get("verdict"), "blocked", report)
        self.assertEqual(self.rec.record_calls, 1,
                         "the run-dir record must be written before the gate")
        self.assertEqual(self.rec.board_calls, [],
                         "no board card may be created while the interview is open")
        self.assertEqual(self.rec.launch_calls, [],
                         "no launcher may be called while the interview is open")
        doc = _ll.load(self.run_dir, self.session_id)
        self.assertEqual(doc.get("state"), _ll.BLOCKED_ACTIONABLE, doc)
        self.assertEqual(
            doc["blocked"]["reason"],
            "signature interview not done: the 8 questions have not been asked")
        self.assertIn("deck-intake-driver.py", doc["blocked"]["remediation"])
        self.assertIn("--signature --sig-next", doc["blocked"]["remediation"])
        self.assertEqual(len(self.rec.notifications), 1,
                         "the operator is told exactly once")
        # Re-polling stays blocked: no retry cost, still no board card.
        report2 = self._drive("signature")
        self.assertEqual(report2.get("_rc"), 8, report2)
        self.assertEqual(self.rec.board_calls, [])

    # A2 -----------------------------------------------------------------
    def test_a2_signature_with_sp_intake_proceeds_to_the_board(self):
        sp = self.run_dir / "working" / "copy" / "sp_intake.json"
        sp.parent.mkdir(parents=True)
        sp.write_text('{"answers": {}}', encoding="utf-8")
        report = self._drive("signature")
        self.assertEqual(len(self.rec.board_calls), 1,
                         "sp_intake.json present must reach the board step")
        self.assertNotEqual(report.get("verdict"), "blocked", report)

    # A3 -----------------------------------------------------------------
    def test_a3_from_scratch_intake_is_unaffected(self):
        report = self._drive("from_scratch")
        self.assertEqual(len(self.rec.board_calls), 1,
                         "a from-scratch intake must reach the board step")
        self.assertNotEqual(report.get("verdict"), "blocked", report)
        self.assertFalse((self.run_dir / "working" / "copy" / "sp_intake.json").exists())

    # A4 -----------------------------------------------------------------
    def test_a4_the_two_page_copies_are_byte_identical(self):
        pages = APP / "pages" / "index.html"
        deployed = APP / "deployed-r2" / "public" / "index.html"
        self.assertEqual(pages.read_bytes(), deployed.read_bytes())
        self.assertIn(
            b"The full Signature Presentation (100+ slides). You will answer 8 "
            b"more questions in chat after this form.",
            pages.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
