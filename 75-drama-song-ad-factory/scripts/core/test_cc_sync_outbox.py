#!/usr/bin/env python3
"""cc_sync durable outbox + ACTUAL factory-to-outbox call path (W08-U1; D13, D32).

What this suite proves:
  1. the outbox default state is a durable FILE bound to tenant/run
     (spec 13: `:memory:` is only acceptable for explicit tests) and its
     acknowledgement state survives a process restart;
  2. the ACTUAL factory-to-outbox call path -- shared-bridge/studio_bridge.py
     _board_epic(), the initialization the studio poll runs at claim time --
     registers exactly one campaign with the canonical 12-stage mapping
     through the durable outbox, and replays idempotently across retries and
     board outages without re-ingesting the request into a second campaign
     and without manual database edits (D32: not inferred from an adapter's
     existence -- the real factory function is called here);
  3. the run event taxonomy (state, approval_request, approval_decision,
     failure, recovery, deliverable) projects from the same durable rows;
  4. pending-synchronization state stays visible during an outage;
  5. stage deliverable registration fulfils the acknowledged-outbox contract
     the stage-move guard reads (file paths included), receipts persist.

HTTP is stubbed at the transport seam only: zero sockets, zero spend.

Run: python3 test_cc_sync_outbox.py   (pytest-collectable) stdlib only.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parent                       # scripts/core
SKILL_ROOT = CORE.parent.parent                             # 75-drama-song-ad-factory
sys.path.insert(0, str(CORE))                               # batch.py's flat imports


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


CS = _load("cc_sync_outbox_under_test", CORE / "cc_sync.py")
WS = "ws-outbox-tests"

CANONICAL_SLUGS = ("research", "creative-strategy", "script-lyrics", "music",
                   "continuity-bible", "storyboard", "image-keyframes",
                   "video-generation", "qc-retakes", "assembly", "final-qc",
                   "delivery")


class FakeBoard:
    """Command Center contract, reduced: idempotent create on job_id, stage
    transitions with 409 ILLEGAL_TRANSITION, 422 PRECONDITION_EVIDENCE for
    review/done without a deliverable. `down` models a transport outage.
    `outage` must be the TransportOutage class of the cc_sync module under
    test (module identity, not name)."""

    def __init__(self, outage=None):
        self.campaigns = {}
        self.deliverables = {}
        self.calls = []
        self.down = False
        self.outage = outage or CS.TransportOutage
        self._n = 0

    def _next_id(self):
        self._n += 1
        return "task-%d" % self._n

    def _card(self, task_id):
        for cards in self.campaigns.values():
            for slug, card in cards.items():
                if card["id"] == task_id:
                    return slug, card
        return None, None

    def sender(self, method, path, payload):
        if self.down:
            raise self.outage("board unreachable (dispatched=False)",
                              dispatched=False)
        self.calls.append({"method": method, "path": path, "payload": payload})
        parts = path.strip("/").split("/")
        if parts[:2] == ["api", "ad-campaigns"]:
            if method == "POST" and len(parts) == 2:
                return self._create(payload)
            if len(parts) == 3 and method == "PATCH":
                return self._move(parts[2], payload)
            if len(parts) == 3 and method == "GET":
                job = parts[2]
                if job not in self.campaigns:
                    return 404, {"code": "NOT_FOUND"}
                cards = [{"id": c["id"], "stage_slug": slug, "status": c["status"]}
                         for slug, c in self.campaigns[job].items()]
                return 200, {"campaign": {"id": job, "status": "active"}, "cards": cards}
        if parts[:2] == ["api", "tasks"] and len(parts) == 4 and parts[3] == "deliverables":
            task_id = parts[2]
            if self._card(task_id)[1] is None:
                return 404, {"code": "NOT_FOUND"}
            if method == "GET":
                return 200, self.deliverables.get(task_id, [])
            if method == "POST":
                row = {"id": "d%d" % (len(self.deliverables.get(task_id, [])) + 1),
                       **(payload or {})}
                self.deliverables.setdefault(task_id, []).append(row)
                return 201, row
        return 404, {"code": "NO_ROUTE"}

    def _create(self, payload):
        job = (payload or {}).get("job_id")
        if job in self.campaigns:
            return 200, self._create_result(job, created=False)
        cards = {"epic": {"id": self._next_id(), "status": "backlog"}}
        for s in (payload or {}).get("stages") or []:
            cards[s["slug"]] = {"id": self._next_id(), "status": "backlog"}
        self.campaigns[job] = cards
        return 201, self._create_result(job, created=True)

    def _create_result(self, job, created):
        cards = self.campaigns[job]
        return {"ok": True, "created": created, "campaign_id": job,
                "parent_id": cards["epic"]["id"],
                "stages": [{"slug": slug, "id": c["id"], "status": c["status"]}
                           for slug, c in cards.items() if slug != "epic"]}

    def _move(self, job, body):
        if job not in self.campaigns:
            return 404, {"code": "CARD_NOT_FOUND"}
        slug = (body or {}).get("stage_slug")
        card = self.campaigns[job].get(slug)
        if card is None:
            return 404, {"code": "CARD_NOT_FOUND"}
        status = (body or {}).get("status")
        legal = {"backlog": {"in_progress", "review", "blocked"},
                 "in_progress": {"review", "blocked", "backlog"},
                 "review": {"done", "in_progress", "blocked", "backlog"},
                 "blocked": {"backlog", "in_progress"},
                 "done": {"backlog"}}
        if status == card["status"]:
            return 200, {"task": {"id": card["id"], "stage_slug": slug, "status": status}}
        if status not in legal.get(card["status"], set()):
            return 409, {"code": "ILLEGAL_TRANSITION"}
        if status in ("review", "done") and not self.deliverables.get(card["id"]):
            return 422, {"code": "PRECONDITION_EVIDENCE"}
        card["status"] = status
        return 200, {"task": {"id": card["id"], "stage_slug": slug, "status": status}}


class TmpDir:
    def __init__(self, case, prefix="s75w08u1-ccsync-"):
        self.tmp = tempfile.TemporaryDirectory(prefix=prefix)
        case.addCleanup(self.tmp.cleanup)

    def dir(self):
        return self.tmp.name


class DurableDefault(unittest.TestCase):
    def test_default_path_binds_tenant_and_run_and_memory_is_explicit(self):
        tmp = TmpDir(self).dir()
        os.environ["CC_OUTBOX_DIR"] = tmp
        self.addCleanup(os.environ.pop, "CC_OUTBOX_DIR", None)
        ob = CS.Outbox(workspace="ws-a", run_id="job-7", sender=lambda m, p, b: (200, {}))
        self.assertNotEqual(ob.db_path, ":memory:")
        self.assertEqual(ob.db_path,
                         os.path.join(tmp, "ws-a", "job-7.sqlite3"))
        mem = CS.Outbox(db_path=":memory:", workspace="ws-a",
                        sender=lambda m, p, b: (200, {}))
        self.assertEqual(mem.db_path, ":memory:", ":memory: is the explicit test seam")
        self.assertTrue(CS.default_outbox_path("ws/a b", "run 1").endswith(".sqlite3"))
        self.assertNotIn(" ", os.path.basename(
            os.path.dirname(CS.default_outbox_path("ws/a b", "run 1"))))

    def test_acknowledgement_state_survives_process_restart(self):
        tmp = TmpDir(self).dir()
        os.environ["CC_OUTBOX_DIR"] = tmp
        self.addCleanup(os.environ.pop, "CC_OUTBOX_DIR", None)
        board = FakeBoard()
        ob = CS.Outbox(workspace=WS, run_id="job-restart", sender=board.sender)
        ob.enqueue_create("job-restart", "Restart Show",
                          [{"slug": s} for s in CANONICAL_SLUGS], workspace=WS)
        ob.flush()
        path = ob.db_path
        ob.db.close()
        # a fresh process = a fresh connection on the same durable file
        ob2 = CS.Outbox(db_path=path, workspace=WS, sender=board.sender)
        self.assertEqual(ob2.counts().get("acked"), 1)
        self.assertEqual(ob2.acknowledged_status("job-restart", "research"), "backlog")
        self.assertEqual(ob2.pending_sync(), [])


class FactoryToOutbox(unittest.TestCase):
    """D32: the actual factory-to-outbox call path, traced and tested --
    shared-bridge/studio_bridge.py::_board_epic is the factory initialization
    the studio poll runs at claim time. Only HTTP is faked."""

    def _bridge(self):
        import cc_sync as real_cc_sync  # the factory's own import name
        sb = _load("studio_bridge_under_test",
                   SKILL_ROOT / "shared-bridge" / "studio_bridge.py")
        return sb, real_cc_sync

    def _patched_sender(self, real_cc_sync, board):
        original = real_cc_sync.Outbox._http_sender
        self.addCleanup(setattr, real_cc_sync.Outbox, "_http_sender", original)
        real_cc_sync.Outbox._http_sender = board.sender

    def _init_board(self, case):
        tmp = TmpDir(case).dir()
        os.environ["CC_OUTBOX_DIR"] = tmp
        case.addCleanup(os.environ.pop, "CC_OUTBOX_DIR", None)
        os.environ["CC_WORKSPACE"] = WS
        case.addCleanup(os.environ.pop, "CC_WORKSPACE", None)
        return tmp

    def test_board_epic_registers_exactly_one_campaign_with_canonical_mapping(self):
        tmp = self._init_board(self)
        sb, real_cc_sync = self._bridge()
        board = FakeBoard(real_cc_sync.TransportOutage)
        self._patched_sender(real_cc_sync, board)
        sb._board_epic(str(SKILL_ROOT), "order-77", "Order Seventy-Seven")
        # exactly one durable create row, acked, carrying the canonical mapping
        db = real_cc_sync.Outbox(db_path=os.path.join(tmp, WS, "default.sqlite3"),
                                 workspace=WS, sender=board.sender)
        creates = db.db.execute(
            "SELECT state, payload FROM outbox WHERE kind='create'").fetchall()
        self.assertEqual(len(creates), 1)
        self.assertEqual(creates[0][0], "acked")
        self.assertEqual([s["slug"] for s in json.loads(creates[0][1])["stages"]],
                         list(CANONICAL_SLUGS))
        self.assertEqual(len(board.campaigns), 1)
        # retry the factory call: the same request is not re-ingested
        sb._board_epic(str(SKILL_ROOT), "order-77", "Order Seventy-Seven")
        creates = db.db.execute(
            "SELECT state, payload FROM outbox WHERE kind='create'").fetchall()
        self.assertEqual(len(creates), 1, "same key: same row, never a second create")
        self.assertEqual(len(board.campaigns), 1, "exactly one campaign per tenant/run")

    def test_board_epic_survives_board_outage_without_duplicate_intake(self):
        tmp = self._init_board(self)
        sb, real_cc_sync = self._bridge()
        board = FakeBoard(real_cc_sync.TransportOutage)
        board.down = True                       # Command Center is down
        self._patched_sender(real_cc_sync, board)
        sb._board_epic(str(SKILL_ROOT), "order-88", "Order Eighty-Eight")
        path = os.path.join(tmp, WS, "default.sqlite3")
        db = real_cc_sync.Outbox(db_path=path, workspace=WS, sender=board.sender)
        # the factory call is fail-soft, but the intent is durably queued and
        # the pending synchronization state is visible -- no manual DB edits
        pending = db.pending_sync()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["kind"], "create")
        self.assertEqual(pending[0]["state"], "pending")
        # board comes back; the factory replays the same request idempotently
        board.down = False
        sb._board_epic(str(SKILL_ROOT), "order-88", "Order Eighty-Eight")
        db2 = real_cc_sync.Outbox(db_path=path, workspace=WS, sender=board.sender)
        self.assertEqual(db2.pending_sync(), [])
        self.assertEqual(len(board.campaigns), 1, "one campaign across the outage")
        creates = db2.db.execute(
            "SELECT id, state FROM outbox WHERE kind='create'").fetchall()
        self.assertEqual(len(creates), 1, "the request was never re-ingested")
        self.assertEqual(creates[0][1], "acked")


class EventsAndReceipts(unittest.TestCase):
    def _outbox(self, case, board):
        tmp = TmpDir(case).dir()
        os.environ["CC_OUTBOX_DIR"] = tmp
        case.addCleanup(os.environ.pop, "CC_OUTBOX_DIR", None)
        return CS.Outbox(workspace=WS, run_id="job-events", sender=board.sender)

    def test_event_taxonomy_state_approval_failure_recovery_deliverable(self):
        board = FakeBoard()
        ob = self._outbox(self, board)
        ob.enqueue_create("job-events", "Events Show",
                          [{"slug": s} for s in CANONICAL_SLUGS], workspace=WS)
        ob.flush()                                            # -> state
        ob.enqueue_move("job-events", "music", "blocked", "media-runner",
                        workspace=WS, reason="need the client",
                        blocked_reason="approval", blocked_on_human="owner",
                        ask="approve the hook?")              # -> approval_request
        ob.flush()
        ob.enqueue_move("job-events", "music", "in_progress", "media-runner",
                        workspace=WS, reason="client said go")  # -> approval_decision
        ob.flush()
        ob.enqueue_stage_deliverable("job-events", "music",
                                     "https://cc.example.test/take-1",
                                     "Take 1", WS)             # -> deliverable
        ob.flush()
        # a stale write the server rejects -> failure
        ob.enqueue_move("job-events", "music", "done", "media-runner",
                        workspace=WS, reason="jump", evidence="x",
                        reviewer="qc-lead")
        ob.flush()
        # a row that only acks after an outage -> recovery
        board.down = True
        ob.enqueue_stage_deliverable("job-events", "music",
                                     "https://cc.example.test/take-2",
                                     "Take 2", WS)
        ob.flush()
        board.down = False
        ob.flush()
        types = [e["type"] for e in ob.events(job_id="job-events")]
        for expected in CS.EVENT_TYPES:
            self.assertIn(expected, types, expected)
        self.assertEqual(types[0], "state", "events arrive in run order")

    def test_pending_sync_visible_and_same_request_never_reingested(self):
        board = FakeBoard()
        ob = self._outbox(self, board)
        board.down = True
        rid1 = ob.enqueue_create("job-events", "Events Show",
                                 [{"slug": s} for s in CANONICAL_SLUGS], workspace=WS)
        ob.flush()
        self.assertEqual(len(ob.pending_sync(job_id="job-events")), 1)
        rid2 = ob.enqueue_create("job-events", "Events Show",
                                 [{"slug": s} for s in CANONICAL_SLUGS], workspace=WS)
        self.assertEqual(rid1, rid2, "identical request dedupes onto the same row")
        board.down = False
        ob.flush()
        self.assertEqual(ob.pending_sync(), [])
        self.assertEqual(len(board.campaigns), 1)

    def test_stage_deliverable_file_registration_feeds_the_move_guard(self):
        board = FakeBoard()
        ob = self._outbox(self, board)
        ob.enqueue_create("job-events", "Events Show",
                          [{"slug": s} for s in CANONICAL_SLUGS], workspace=WS)
        ob.flush()
        card_id = board.campaigns["job-events"]["script-lyrics"]["id"]
        ob.db.execute("DELETE FROM card_ids")        # prove the hint re-seeds
        ob.db.commit()
        rid = ob.enqueue_stage_deliverable(
            "job-events", "script-lyrics", "/runs/r1/script.md", "Script", WS,
            deliverable_type="file", task_id=card_id)
        self.assertEqual(ob._stage_task_id("job-events", "script-lyrics"), card_id,
                         "explicit task id seeds card_ids")
        self.assertEqual(ob.flush()["acked"], [rid])
        self.assertTrue(ob.stage_deliverable_queued("job-events", "script-lyrics"),
                        "the stage-move guard reads the acknowledged outbox row")
        mid = ob.enqueue_move("job-events", "script-lyrics", "review",
                              "media-runner", workspace=WS, evidence="/runs/r1/script.md")
        self.assertEqual(ob.flush()["acked"], [mid], "review admission passes")
        with self.assertRaises(CS.BoardSyncError):
            ob.enqueue_stage_deliverable("job-events", "music", "ftp://nope",
                                         "bad", WS)  # FIX 27 url check preserved
        with self.assertRaises(CS.BoardSyncError):
            ob.enqueue_stage_deliverable("job-events", "music", "  ",
                                         "bad", WS, deliverable_type="file")

    def test_stage_receipts_persist_and_compare_evidence(self):
        tmp = TmpDir(self).dir()
        os.environ["CC_OUTBOX_DIR"] = tmp
        self.addCleanup(os.environ.pop, "CC_OUTBOX_DIR", None)
        board = FakeBoard()
        ob = CS.Outbox(workspace=WS, run_id="job-r", sender=board.sender)
        receipt = {"stage_slug": "music", "flow": ["in_progress", "review", "done"]}
        ob.record_stage_receipt("job-r", "music", "done", "/runs/r1/take.wav",
                                "qc-lead", "media-runner", receipt)
        rec = ob.stage_receipt("job-r", "music", "done")
        self.assertEqual(rec["evidence"], "/runs/r1/take.wav")
        self.assertEqual(rec["receipt"], receipt)
        ob.db.close()
        ob2 = CS.Outbox(db_path=os.path.join(tmp, WS, "job-r.sqlite3"),
                        workspace=WS, sender=board.sender)
        self.assertEqual(ob2.stage_receipt("job-r", "music", "done")["receipt"],
                         receipt, "receipts survive restart")
        self.assertIsNone(ob2.stage_receipt("job-r", "music", "review"))
        with self.assertRaises(CS.BoardSyncError):
            ob2.record_stage_receipt("job-r", "music", "nope", "e", "r", "a", {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
