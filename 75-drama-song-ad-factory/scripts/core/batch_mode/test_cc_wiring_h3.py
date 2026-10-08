#!/usr/bin/env python3
"""H3 steps 2/3 wiring: department, title prefix, batch-in-show_name,
no separate parent board, and the deliverables POST on the epic.

Manual 02 H3 (drama song ads show as "FB Ad Run" under Marketing, with no
deliverable and no batch link). This suite proves the shared-core half:

  1. every enqueue_create carries department="video",
     title_prefix="Drama Song Ad" and agent_id
     ="vsl-video-sales-letter-specialist" (provenance only);
  2. batch children carry the parent job id in the show_name text
     ("Book 2 of 5 — <title> (batch <id>)");
  3. materialize enqueues NO separate 12-stage parent board (exactly one
     create per book, nothing titled "Batch of N books");
  4. Outbox.enqueue_deliverable POSTs to /api/tasks/<epic id>/deliverables
     with {deliverable_type: "file", path, title} -- the create response's
     parent_id is recorded and reused;
  5. the HTTP layer is stubbed at the ``sender`` seam: zero sockets, zero
     network, zero spend. A wrong-enough stub fails the suite.

Run: python3 core/batch_mode/test_cc_wiring_h3.py   (pytest-collectable)
stdlib only.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent          # scripts/core
HERE = Path(__file__).resolve().parent                 # core/batch_mode
sys.path.insert(0, str(CORE))                          # core/ on path: batch.py's flat imports resolve


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


CS = _load("cc_sync_under_test", CORE / "cc_sync.py")
BM = _load("batch_under_test", HERE / "batch.py")


class RecordingOutbox(CS.Outbox):
    """The real outbox rows + a stubbed transport that records every call."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls = []

    def _stub_sender(self, status_by_path):
        def sender(method, path, payload):
            self.calls.append({"method": method, "path": path,
                               "payload": payload})
            for prefix, (status, body) in status_by_path.items():
                if path.startswith(prefix):
                    return status, body
            return 500, {"code": "NO_ROUTE"}
        return sender


WORKSPACE = "ws-batch-mode"


def priced_card(titles=(("Hope of the Highlands", "A. Highlander"),
                        ("Rust and Rain", "M. Storm"))):
    card = BM.make_card({"style": "lifelike-3d", "music": "soul-ballad"})
    card = BM.set_books(card, [{"title": t, "author": a} for t, a in titles])
    return BM.price_batch(card, price_fn=lambda book, fields: 2.50)


def materialized(card, tmp):
    outbox = RecordingOutbox(db_path=":memory:", workspace=WORKSPACE)
    manifest = BM.materialize(card, tmp, price_fn=None, outbox=outbox,
                              workspace=WORKSPACE, check=False)
    return manifest, outbox


class H3Wiring(unittest.TestCase):
    def test_create_payload_carries_department_prefix_agent(self):
        """H3 step 2: department=video, title_prefix='Drama Song Ad', agent
        id as provenance -- on every book create."""
        _, outbox = materialized(priced_card(), SelfTmp(self).dir())
        creates = [json.loads(r[4]) for r in outbox_rows(outbox)
                   if r[1] == "create"]
        self.assertTrue(creates, "expected at least one create row")
        for payload in creates:
            self.assertEqual(payload.get("department"), "video")
            self.assertEqual(payload.get("title_prefix"), "Drama Song Ad")
            self.assertEqual(payload.get("agent_id"),
                             "vsl-video-sales-letter-specialist")

    def test_batch_child_show_name_carries_parent_job_id(self):
        """H3 step 2: 'Book 2 of 5 — <title> (batch <id>)'."""
        card = priced_card()
        _, outbox = materialized(card, SelfTmp(self).dir())
        creates = [json.loads(r[4]) for r in outbox_rows(outbox)
                   if r[1] == "create"]
        by_job = {}
        for book in card["books"]:
            match = [p for p in creates if p["job_id"] == book["cc_job_id"]]
            self.assertEqual(len(match), 1, book["cc_job_id"])
            by_job[book["cc_job_id"]] = match[0]
            self.assertIn("batch %s" % card["batch_id"],
                          by_job[book["cc_job_id"]]["show_name"])
            self.assertIn(book["title"], by_job[book["cc_job_id"]]["show_name"])
            self.assertRegex(by_job[book["cc_job_id"]]["show_name"],
                             r"^Book \d+ of \d+ — .+ \(batch .+\)$")

    def test_no_separate_parent_board(self):
        """H3 step 2: one create per book, zero titled 'Batch of N books'."""
        card = priced_card()
        _, outbox = materialized(card, SelfTmp(self).dir())
        creates = [json.loads(r[4]) for r in outbox_rows(outbox)
                   if r[1] == "create"]
        self.assertEqual(len(creates), 2)
        self.assertFalse([p for p in creates
                          if p["show_name"].startswith("Batch of")])

    def test_deliverable_method_posts_documented_body(self):
        """H3 step 3: POST /api/tasks/<epic id>/deliverables with
        {deliverable_type: 'file', path, title}. The epic id comes from the
        create response's parent_id."""
        outbox = RecordingOutbox(db_path=":memory:", workspace=WORKSPACE)
        epic_id = "epic-1234"
        outbox.sender = outbox._stub_sender({
            "/api/ad-campaigns": (201, {"ok": True, "created": True,
                                        "campaign_id": "job-1",
                                        "parent_id": epic_id, "stages": []}),
            "/api/tasks/": (201, {"id": "d1"}),
        })
        rid = outbox.enqueue_create("job-1", "Hope of the Highlands",
                                    [{"slug": "delivery", "title": "Delivery"}],
                                    workspace=WORKSPACE)
        outbox.flush()
        self.assertTrue(outbox.epic_id("job-1"), "parent_id must be recorded")
        # H3 acceptance: the deliverable rides the recorded epic id.
        did = outbox.enqueue_deliverable(outbox.epic_id("job-1"), WORKSPACE,
                                         path="/runs/campaign/delivery/final.mp4",
                                         title="Hope of the Highlands")
        report = outbox.flush()
        self.assertIn(rid, [row[0] for row in outbox_rows(outbox)
                            if row[5] == "acked"])
        self.assertIn(did, report["acked"])
        posts = [c for c in outbox.calls
                 if c["method"] == "POST" and "/deliverables" in c["path"]]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["path"],
                         "/api/tasks/%s/deliverables" % epic_id)
        self.assertEqual(posts[0]["payload"],
                         {"deliverable_type": "file",
                          "path": "/runs/campaign/delivery/final.mp4",
                          "title": "Hope of the Highlands"})

    def test_deliverable_unknown_type_fails_closed(self):
        outbox = RecordingOutbox(db_path=":memory:", workspace=WORKSPACE)
        for bad in ("", "link", "VIDEO"):
            with self.assertRaises(CS.BoardSyncError):
                outbox.enqueue_deliverable("epic-1", WORKSPACE,
                                           path="final.mp4", title="t",
                                           deliverable_type=bad)


# --- helpers --------------------------------------------------------------
def outbox_rows(outbox):
    return outbox.db.execute(
        "SELECT id,kind,job_id,stage_slug,payload,state FROM outbox "
        "ORDER BY id").fetchall()


class SelfTmp:
    """A TemporaryDirectory owned by the calling unittest case."""
    def __init__(self, case):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory(prefix="h3-wiring-")
        case.addCleanup(self.tmp.cleanup)

    def dir(self):
        return self.tmp.name


if __name__ == "__main__":
    unittest.main(verbosity=2)