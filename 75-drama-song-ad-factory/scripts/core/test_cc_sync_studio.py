#!/usr/bin/env python3
"""cc_sync cards the Command Center actually accepts (SPEC section 6 board rules).

A studio run walks a stage card backlog -> in_progress -> review -> done. The
Command Center refuses review/done until a deliverable is registered on THAT
card (task-lifecycle.ts PRECONDITION_EVIDENCE, FIX 25) and answers an illegal
jump with 409 ILLEGAL_TRANSITION (transition()).

The board here is a fake server that enforces exactly those two rules, so this
suite proves cc_sync against the contract instead of against itself:

  1. create -> in_progress -> deliverable -> review -> done all ack;
  2. review/done with no deliverable on the card is refused BEFORE it queues;
  3. the stage deliverable POSTs to the stage card's TASK id (stages[].id from
     the create response), not to the campaign;
  4. a deliverable row left "sent" by a timeout reconciles against the card's
     deliverable list instead of being rejected -- the campaign route 404s on a
     task id and used to mark landed work rejected;
  5. a row whose bytes never landed reconciles to rejected (no false ack) and
     is never re-sent;
  6. an illegal jump is rejected once and never re-sent;
  7. base URL order: CC_BASE_URL -> COMMAND_CENTER_URL -> MISSION_CONTROL_URL
     -> http://127.0.0.1:${CC_PORT|4000}.

HTTP is stubbed at the ``sender`` seam: zero sockets, zero network, zero spend.

Run: python3 -m pytest -q test_cc_sync_studio.py   (also unittest-collectable)
"""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parent                 # scripts/core
HERE = CORE / "batch_mode"
sys.path.insert(0, str(CORE))                          # batch.py's flat imports resolve


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


CS = _load("cc_sync_studio_under_test", CORE / "cc_sync.py")
BM = _load("batch_stages_under_test", HERE / "batch.py")   # the real 12 stage slugs

WS = "ws-studio"

# src/lib/task-lifecycle.ts LEGAL_TRANSITIONS, restricted to the five ad
# statuses cc_sync may send. Written out from the server source on purpose:
# the fake must not import the client's own mirror and agree with it by construction.
SERVER_LEGAL = {
    "backlog": {"in_progress", "review", "blocked"},
    "in_progress": {"review", "blocked", "backlog"},
    "review": {"done", "in_progress", "blocked", "backlog"},
    "blocked": {"backlog", "in_progress"},
    "done": {"backlog"},
}


class FakeBoard:
    """Minimal Command Center contract: idempotent create returning
    stages[].id, transition() with 409 ILLEGAL_TRANSITION, and 422
    PRECONDITION_EVIDENCE when review/done has no registered deliverable."""

    def __init__(self):
        self.campaigns = {}      # job id -> {slug: {"id", "status"}}
        self.deliverables = {}   # task id -> [row, ...]
        self.calls = []
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

    # -- route -----------------------------------------------------------
    def sender(self, method, path, payload):
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
                return 200, {"campaign": {"id": job}, "cards": cards}
        if parts[:2] == ["api", "tasks"] and len(parts) == 4 and parts[3] == "deliverables":
            task_id = parts[2]
            if self._card(task_id)[1] is None:
                return 404, {"code": "NOT_FOUND"}
            if method == "GET":
                return 200, self.deliverables.get(task_id, [])
            if method == "POST":
                return self._register(task_id, payload)
        return 404, {"code": "NO_ROUTE"}

    # -- handlers --------------------------------------------------------
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

    def _register(self, task_id, payload):
        # FIX 27: a url row must be a syntactically valid http(s) URL.
        if (payload or {}).get("deliverable_type") == "url":
            p = (payload or {}).get("path") or ""
            if not (p.startswith("http://") or p.startswith("https://")):
                return 422, {"error": "A 'url' deliverable requires a valid http(s) URL in path."}
        row = {"id": "d%d" % (len(self.deliverables.get(task_id, [])) + 1), **(payload or {})}
        self.deliverables.setdefault(task_id, []).append(row)
        return 201, row

    def _move(self, job, body):
        if job not in self.campaigns:
            return 404, {"code": "CARD_NOT_FOUND"}
        slug = (body or {}).get("stage_slug")
        card = self.campaigns[job].get(slug)
        if card is None:
            return 404, {"code": "CARD_NOT_FOUND"}
        status = (body or {}).get("status")
        if status not in SERVER_LEGAL:
            return 400, {"code": "INVALID_STATUS"}
        if status == card["status"]:            # transition() is same-state idempotent
            return 200, {"task": {"id": card["id"], "stage_slug": slug, "status": status}}
        if status not in SERVER_LEGAL[card["status"]]:
            return 409, {"code": "ILLEGAL_TRANSITION"}
        if status in ("review", "done") and not self.deliverables.get(card["id"]):
            return 422, {"code": "PRECONDITION_EVIDENCE"}
        card["status"] = status
        return 200, {"task": {"id": card["id"], "stage_slug": slug, "status": status}}


class LossySender:
    """The reply never comes back for ``path_fragment`` (timeout/5xx), so the
    row stays sent (UNKNOWN, dispatched=True) and the next flush must
    reconcile it. ``landed`` says whether the board applied the bytes first."""

    def __init__(self, board, path_fragment, landed):
        self.board, self.fragment, self.landed = board, path_fragment, landed

    def __call__(self, method, path, payload):
        if self.fragment in path:
            if self.landed:
                self.board.sender(method, path, payload)
            raise CS.TransportOutage("timeout", dispatched=True)
        return self.board.sender(method, path, payload)


class StudioBoard(unittest.TestCase):
    def setUp(self):
        self.board = FakeBoard()
        self.outbox = CS.Outbox(db_path=":memory:", workspace=WS, sender=self.board.sender)

    # -- helpers ----------------------------------------------------------
    def new_campaign(self, job="job-studio-1"):
        self.outbox.enqueue_create(job, "Studio Show",
                                   [{"slug": s, "title": t} for s, t in BM.STAGES],
                                   workspace=WS, department="video",
                                   title_prefix="Drama Song Ad")
        self.assertAcks(self.outbox.flush())
        return job

    def acked(self, report):
        return [r for r in report["acked"]]

    def assertAcks(self, report, ids=()):
        self.assertEqual(report["rejected"], [], report)
        for i in ids:
            self.assertIn(i, report["acked"])

    def stage_task_id(self, job, slug):
        return self.board.campaigns[job][slug]["id"]

    def deliverable(self, job, slug, url="https://cc.example.test/runs/r1/stage"):
        did = self.outbox.enqueue_stage_deliverable(job, slug, url, "Stage work", WS)
        self.assertAcks(self.outbox.flush(), [did])
        return did

    def to_status(self, job, slug, status, **kw):
        kw.setdefault("actor", "studio")
        mid = self.outbox.enqueue_move(job, slug, status, workspace=WS, **kw)
        self.assertAcks(self.outbox.flush(), [mid])
        return mid

    # -- 1: the happy path ------------------------------------------------
    def test_create_move_deliverable_review_done_all_ack(self):
        job = self.new_campaign()
        slug = BM.STAGES[0][0]                       # research
        self.assertEqual(len(self.board.campaigns[job]) - 1, 12)   # epic + 12 stages

        self.to_status(job, slug, "in_progress", reason="picked up")
        self.deliverable(job, slug, "https://cc.example.test/runs/r1/research")

        # the POST went to the stage card's TASK id, never to the campaign
        posts = [c for c in self.board.calls
                 if c["method"] == "POST" and c["path"].endswith("/deliverables")]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["path"],
                         "/api/tasks/%s/deliverables" % self.stage_task_id(job, slug))
        self.assertEqual(posts[0]["payload"],
                         {"deliverable_type": "url",
                          "path": "https://cc.example.test/runs/r1/research",
                          "title": "Stage work"})

        self.to_status(job, slug, "review", evidence="url deliverable registered")
        self.to_status(job, slug, "done", evidence="final qc pass", reviewer="qc-agent")
        self.assertEqual(self.board.campaigns[job][slug]["status"], "done")

    # -- 2: the gate ------------------------------------------------------
    def test_review_with_no_deliverable_is_refused_before_it_queues(self):
        job = self.new_campaign()
        slug = BM.STAGES[0][0]
        self.to_status(job, slug, "in_progress", reason="picked up")

        rows_before = self.outbox.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
        with self.assertRaises(CS.EvidenceError) as caught:
            self.outbox.enqueue_move(job, slug, "review", actor="studio", workspace=WS,
                                     evidence="says so")
        self.assertIn("enqueue_stage_deliverable", str(caught.exception))
        rows_after = self.outbox.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
        self.assertEqual(rows_before, rows_after, "a refused move must queue nothing")

    # -- 4: a sent-but-unacked deliverable reconciles ---------------------
    def test_timed_out_deliverable_reconciles_instead_of_rejecting(self):
        job = self.new_campaign()
        slug = BM.STAGES[1][0]                       # creative-strategy
        self.to_status(job, slug, "in_progress", reason="picked up")
        task_id = self.stage_task_id(job, slug)
        url = "https://cc.example.test/runs/r1/strategy"

        self.outbox.sender = LossySender(self.board, "/deliverables", landed=True)
        did = self.outbox.enqueue_stage_deliverable(job, slug, url, "Strategy", WS)
        report = self.outbox.flush()
        self.assertIn(did, report["pending"], "timeout leaves the row sent (UNKNOWN)")
        self.assertEqual(self.board.deliverables[task_id][0]["path"], url)  # it landed

        self.outbox.sender = self.board.sender
        campaign_gets = [c for c in self.board.calls
                         if c["method"] == "GET" and c["path"].startswith("/api/ad-campaigns/")]
        report = self.outbox.flush()
        self.assertAcks(report, [did])
        # the bug: GET /api/ad-campaigns/<task id> 404s and marks landed work rejected
        self.assertFalse([c for c in self.board.calls
                          if c["method"] == "GET" and c["path"] == "/api/ad-campaigns/" + task_id])
        self.assertEqual([c for c in self.board.calls
                          if c["method"] == "GET" and c["path"].startswith("/api/ad-campaigns/")],
                         campaign_gets)
        # review now clears the server gate
        self.to_status(job, slug, "review", evidence="registered")

    # -- 5: no false ack --------------------------------------------------
    def test_deliverable_that_never_landed_reconciles_to_rejected(self):
        job = self.new_campaign()
        slug = BM.STAGES[2][0]                       # script-lyrics
        self.to_status(job, slug, "in_progress", reason="picked up")
        task_id = self.stage_task_id(job, slug)

        self.outbox.sender = LossySender(self.board, "/deliverables", landed=False)
        did = self.outbox.enqueue_stage_deliverable(job, slug,
                                                    "https://cc.example.test/r1/script", "Script", WS)
        report = self.outbox.flush()
        self.assertIn(did, report["pending"], "dispatched-but-unknown stays sent")
        self.assertEqual(self.board.deliverables.get(task_id, []), [])

        self.outbox.sender = self.board.sender
        report = self.outbox.flush()                 # reconcile: not there -> rejected
        self.assertIn(did, report["rejected"])
        self.assertEqual(self.board.deliverables.get(task_id, []), [])

        state = self.outbox.db.execute("SELECT state FROM outbox WHERE id=?", (did,)).fetchone()[0]
        self.assertEqual(state, "rejected")
        calls = len(self.board.calls)
        report = self.outbox.flush()                 # rejected is terminal: never re-sent
        self.assertEqual(len(self.board.calls), calls)
        self.assertEqual(report["acked"] + report["rejected"] + report["pending"], [])

    # -- 6: stale transitions --------------------------------------------
    def test_illegal_jump_is_rejected_once_and_never_resent(self):
        job = self.new_campaign()
        slug = BM.STAGES[0][0]
        self.to_status(job, slug, "in_progress", reason="picked up")
        self.deliverable(job, slug)
        self.to_status(job, slug, "review", evidence="registered")
        self.to_status(job, slug, "done", evidence="qc pass", reviewer="qc-agent")

        # done -> review is illegal; a distinct reason keeps this a NEW intent
        # (identical payloads dedupe onto the earlier acked row by design).
        mid = self.outbox.enqueue_move(job, slug, "review", actor="studio", workspace=WS,
                                       reason="reopen after done", evidence="reopen")
        report = self.outbox.flush()
        self.assertIn(mid, report["rejected"])
        result = self.outbox.db.execute("SELECT result FROM outbox WHERE id=?", (mid,)).fetchone()[0]
        self.assertIn("ILLEGAL_TRANSITION", result)

        calls = len(self.board.calls)
        report = self.outbox.flush()
        self.assertEqual(len(self.board.calls), calls)
        self.assertEqual(report["acked"] + report["rejected"] + report["pending"], [])
        self.assertEqual(self.board.campaigns[job][slug]["status"], "done")

    # -- 7: base URL ------------------------------------------------------
    def test_base_url_env_fallback_order(self):
        saved = dict(os.environ)

        def base(env, **explicit):
            for k in ("CC_BASE_URL", "COMMAND_CENTER_URL", "MISSION_CONTROL_URL", "CC_PORT"):
                os.environ.pop(k, None)
            os.environ.update(env)
            try:
                return CS.Outbox(db_path=":memory:", workspace=WS, **explicit).base_url
            finally:
                os.environ.clear()
                os.environ.update(saved)

        both = {"CC_BASE_URL": "http://cc-base.example", "COMMAND_CENTER_URL": "http://cc-env.example",
                "MISSION_CONTROL_URL": "http://mc.example"}
        self.assertEqual(base(both), "http://cc-base.example")
        self.assertEqual(base({k: v for k, v in both.items() if k != "CC_BASE_URL"}),
                         "http://cc-env.example")
        self.assertEqual(base({"MISSION_CONTROL_URL": "http://mc.example"}),
                         "http://mc.example")
        self.assertEqual(base({}), "http://127.0.0.1:4000")
        self.assertEqual(base({"CC_PORT": "4100"}), "http://127.0.0.1:4100")
        # an explicit argument still wins
        self.assertEqual(base(both, base_url="http://explicit.example/"),
                         "http://explicit.example")


if __name__ == "__main__":
    unittest.main(verbosity=2)
