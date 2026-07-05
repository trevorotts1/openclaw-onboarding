#!/usr/bin/env python3
"""test_cc_contract.py — the board-contract test for the shared mc_board.py.

Proves the ONE invariant that the review-skip bug violated: a producer moves a
run's card to `review` and NEVER to `done`. review->done belongs exclusively to
the independent QC scorer (PASS >= 8.5). This test also proves the client-side
legal-transition walk and CC_STATUS_PATH_TEMPLATE route parity.

It is BYTE-IDENTICAL alongside mc_board.py in every productized skill that ships
the helper (49/50/53/55/56/57). Stdlib-only, zero network: mc_board._request is
monkeypatched to a recorder, so the test asserts the EXACT method/URL/payloads the
helper would put on the wire — never a live board.

Run:  python3 test_cc_contract.py            (verbose unittest)
Exit: 0 = contract holds; non-zero = a producer could skip the QC `review` column.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mc_board  # noqa: E402

# The CC TaskStatus enum this producer must stay in parity with (server truth:
# src/lib/validation.ts, mirrored in 48/scripts/cc_board.py). If the server adds a
# column, this list is the single place the contract test is updated.
CC_STATUS_ENUM = ("backlog", "in_progress", "review", "blocked", "done")

_ENABLED_ENV = {"COMMAND_CENTER_URL": "https://cc.example.test", "MC_API_TOKEN": "t"}


class _Recorder:
    """Stand-in for mc_board._request. Records every (method, url, payload) and
    replays a scripted (status_code, body) queue; GETs return the current status."""

    def __init__(self, current_status="backlog"):
        self.calls = []
        self.current_status = current_status
        self._task_id = "TASK-1"

    def __call__(self, method, url, payload, cfg):
        self.calls.append({"method": method, "url": url, "payload": payload})
        if method == "GET":
            return 200, {"task_id": self._task_id, "status": self.current_status}
        if url.endswith("/api/tasks/ingest"):
            return 201, {"task_id": self._task_id, "deduped": False}
        # A status write: reflect the new status so a subsequent GET sees it.
        if isinstance(payload, dict) and payload.get("status"):
            self.current_status = payload["status"]
        return 200, {"ok": True}

    def statuses_written(self):
        return [c["payload"]["status"] for c in self.calls
                if c["method"] != "GET" and isinstance(c["payload"], dict)
                and "status" in c["payload"] and not c["url"].endswith("/api/tasks/ingest")]


class BoardContractTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.run_dir = Path(self._tmp)
        self._orig_request = mc_board._request

    def tearDown(self):
        mc_board._request = self._orig_request

    def _patch(self, rec):
        mc_board._request = rec

    # ---- enum parity -------------------------------------------------------
    def test_status_enum_parity(self):
        self.assertEqual(tuple(mc_board.VALID_STATUSES), CC_STATUS_ENUM,
                         "mc_board.VALID_STATUSES drifted from the CC TaskStatus enum")
        self.assertIn("review", mc_board.VALID_STATUSES)
        self.assertIn("done", mc_board.VALID_STATUSES)

    # ---- THE contract: complete_run posts review, never done ---------------
    def test_complete_run_posts_review_never_done(self):
        rec = _Recorder(current_status="in_progress")
        self._patch(rec)
        ok = mc_board.complete_run(self.run_dir, "TASK-1", env=_ENABLED_ENV,
                                   deliverable_url="https://cc.example.test/deliverable")
        self.assertTrue(ok)
        written = rec.statuses_written()
        self.assertIn("review", written, "complete_run must post 'review'")
        self.assertNotIn("done", written,
                         "PRODUCER POSTED 'done' — the QC review column was skipped (THE bug)")
        # deliverable link is registered on the terminal (review) move
        review_calls = [c for c in rec.calls
                        if isinstance(c["payload"], dict) and c["payload"].get("status") == "review"]
        self.assertTrue(any(c["payload"].get("deliverable_url") for c in review_calls),
                        "the deliverable link must be registered on the review move")

    def test_card_advance_hard_blocks_done(self):
        rec = _Recorder(current_status="review")
        self._patch(rec)
        ok = mc_board.card_advance(self.run_dir, "TASK-1", phase_id="deliver",
                                   status="done", env=_ENABLED_ENV)
        self.assertFalse(ok, "card_advance(status='done') must be refused")
        self.assertNotIn("done", rec.statuses_written(),
                         "no 'done' write may ever leave a producer")
        # and it never even issued a write
        self.assertEqual([c for c in rec.calls if c["method"] != "GET"], [],
                         "a blocked 'done' must issue NO status write at all")

    def test_complete_run_coerces_done_to_review(self):
        rec = _Recorder(current_status="in_progress")
        self._patch(rec)
        ok = mc_board.complete_run(self.run_dir, "TASK-1", status="done", env=_ENABLED_ENV)
        self.assertTrue(ok)
        self.assertNotIn("done", rec.statuses_written())
        self.assertIn("review", rec.statuses_written())

    # ---- legal-path walking ------------------------------------------------
    def test_legal_path_walk_backlog_to_review(self):
        rec = _Recorder(current_status="backlog")
        self._patch(rec)
        ok = mc_board.card_advance(self.run_dir, "TASK-1", phase_id="run",
                                   status="review", env=_ENABLED_ENV)
        self.assertTrue(ok)
        self.assertEqual(rec.statuses_written(), ["in_progress", "review"],
                         "must walk backlog -> in_progress -> review, no illegal jump")

    def test_legal_path_helper(self):
        self.assertEqual(mc_board._legal_path("backlog", "review"),
                         ["in_progress", "review"])
        self.assertEqual(mc_board._legal_path("review", "review"), [])
        self.assertEqual(mc_board._legal_path("in_progress", "review"), ["review"])

    def test_same_status_is_noop(self):
        rec = _Recorder(current_status="in_progress")
        self._patch(rec)
        ok = mc_board.card_advance(self.run_dir, "TASK-1", phase_id="p",
                                   status="in_progress", env=_ENABLED_ENV)
        self.assertTrue(ok)
        self.assertEqual(rec.statuses_written(), [],
                         "already-at-target must issue no write")

    # ---- route parity ------------------------------------------------------
    def test_cc_status_path_template_honored(self):
        rec = _Recorder(current_status="in_progress")
        self._patch(rec)
        env = dict(_ENABLED_ENV, CC_STATUS_PATH_TEMPLATE="/api/tasks/{id}/status",
                   CC_STATUS_METHOD="POST")
        ok = mc_board.card_advance(self.run_dir, "TASK-9", phase_id="run",
                                   status="review", env=env)
        self.assertTrue(ok)
        writes = [c for c in rec.calls if c["method"] != "GET"]
        self.assertTrue(writes)
        self.assertTrue(all(c["url"].endswith("/api/tasks/TASK-9/status") for c in writes),
                        "CC_STATUS_PATH_TEMPLATE not honored on the status write URL")
        self.assertTrue(all(c["method"] == "POST" for c in writes),
                        "CC_STATUS_METHOD not honored")

    def test_malformed_template_falls_back(self):
        cfg = mc_board.board_config(dict(_ENABLED_ENV, CC_STATUS_PATH_TEMPLATE="/no-placeholder"))
        self.assertEqual(cfg["status_tmpl"], "/api/tasks/{id}")

    # ---- disabled board = clean no-op --------------------------------------
    def test_disabled_board_is_noop(self):
        rec = _Recorder()
        self._patch(rec)
        self.assertIsNone(mc_board.card_open(self.run_dir, slug="s", title="t",
                                             department="d", env={}))
        self.assertFalse(mc_board.card_advance(self.run_dir, "TASK-1", phase_id="p",
                                               status="review", env={}))
        self.assertFalse(mc_board.complete_run(self.run_dir, "TASK-1", env={}))
        self.assertEqual(rec.calls, [], "a disabled board must touch the network NEVER")
        self.assertFalse(mc_board._receipt_path(self.run_dir).exists(),
                         "a disabled board must write NOTHING into the run dir")

    # ---- full lifecycle never emits done -----------------------------------
    def test_full_cycle_never_emits_done(self):
        rec = _Recorder(current_status="backlog")
        self._patch(rec)
        env = _ENABLED_ENV
        tid = mc_board.card_open(self.run_dir, slug="run-1", title="Run 1",
                                 department="funnels", env=env)
        self.assertEqual(tid, "TASK-1")
        mc_board.card_advance(self.run_dir, tid, phase_id="run", status="in_progress",
                              note="run started", env=env)
        mc_board.card_advance(self.run_dir, tid, phase_id="P1", status="in_progress",
                              note="phase P1", env=env)
        mc_board.complete_run(self.run_dir, tid, env=env,
                              deliverable_url="https://cc.example.test/x")
        self.assertNotIn("done", rec.statuses_written(),
                         "no 'done' may ever be written across a full producer lifecycle")
        self.assertEqual(rec.statuses_written()[-1], "review",
                         "the terminal producer status must be 'review'")


if __name__ == "__main__":
    unittest.main(verbosity=2)
