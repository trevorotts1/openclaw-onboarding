#!/usr/bin/env python3
"""S75-033: the completion evidence a Skill 75 run owes the Command Center.

The board's own schema decides the shapes (Command Center src/lib/validation.ts):

  * SKILL75_REQUIRED_APPROVAL_KINDS — lines 449-456;
  * Skill75ApprovalEnvelopeSchema — lines 519-533;
  * Skill75ReviewEnvelopeSchema — lines 537-547;
  * UpdateAdCampaignStageSchema — lines 666-692 (one `approval` and one
    `review` per PATCH /api/ad-campaigns/[id]).

`assert_approval` / `assert_review` / `assert_patch_body` below MIRROR that
field list (required keys, types, lengths, enum values). They are deliberately
stricter than zod's default unknown-key strip, so a body accepted here is a
body the board's schema accepts.

What this suite proves:
  1. a fixture run that carries all six approval sources yields the six
     revision-bound approval records plus the independent review record;
  2. the PATCH body built from that result is accepted by the mirrored board
     schema;
  3. a run with no storyboard approval raises CompletionEvidenceMissing and
     names the missing record;
  4. a review whose reviewer is the recorded maker is refused (no self-review);
  5. cc_sync.enqueue_create sends the typed contract marker and the requester
     fields the create schema names;
  6. cc_sync.enqueue_move passes the approval and review envelopes through in
     the PATCH body, and refuses a malformed envelope before it is queued.

HTTP is stubbed at the transport seam only: zero sockets, zero spend.

Run: python3 test_cc_sync_completion_s75_033.py   (pytest-collectable) stdlib only.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parent                       # scripts/core
sys.path.insert(0, str(CORE))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CS = _load("cc_sync_completion_under_test", CORE / "cc_sync.py")
CC = _load("cc_completion_under_test", CORE / "cc_completion.py")

WS = "ws-completion-tests"
JOB = "run-s75-033"

APPROVAL_KINDS = ("script", "lyrics", "character_bible", "music", "storyboard", "final")
APPROVAL_REQUIRED = ("contract", "version", "kind", "artifact_kind", "revision",
                     "decision", "approver", "decided_at")
APPROVAL_OPTIONAL = ("sha256", "thread_id")
REVIEW_REQUIRED = ("contract", "version", "kind", "reviewer", "actor", "verdict")
REVIEW_OPTIONAL = ("scope", "revision")
BODY_REQUIRED = ("stage_slug", "status")
BODY_OPTIONAL = ("reason", "actor", "blocked_reason", "blocked_on_human", "ask",
                 "evidence", "reviewer", "approval", "review")
CARD_STATUSES = ("backlog", "in_progress", "review", "blocked", "done")


# --------------------------------------------------------------------------- #
# the mirrored board schema (validation.ts lines cited in the module docstring)
# --------------------------------------------------------------------------- #

def _object(value, allowed, required, where):
    if not isinstance(value, dict):
        raise AssertionError("%s must be an object" % where)
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise AssertionError("%s carries key(s) the schema does not accept: %s"
                             % (where, unknown))
    for key in required:
        if key not in value:
            raise AssertionError("%s is missing required key %r" % (where, key))


def _text(value, low, high, where):
    if not isinstance(value, str) or not (low <= len(value) <= high):
        raise AssertionError("%s must be a string of %d-%d characters" % (where, low, high))


def _positive_int(value, where):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AssertionError("%s must be a positive integer" % where)


def assert_approval(value):
    _object(value, APPROVAL_REQUIRED + APPROVAL_OPTIONAL, APPROVAL_REQUIRED, "approval")
    if value["contract"] != "skill75" or value["version"] != 1:
        raise AssertionError("approval contract must be skill75 version 1")
    if value["kind"] != "approval":
        raise AssertionError("approval kind must be 'approval'")
    if value["artifact_kind"] not in APPROVAL_KINDS:
        raise AssertionError("unknown artifact_kind %r" % (value["artifact_kind"],))
    _positive_int(value["revision"], "approval revision")
    if "sha256" in value:
        _text(value["sha256"], 64, 64, "approval sha256")
        if any(c not in "0123456789abcdefABCDEF" for c in value["sha256"]):
            raise AssertionError("approval sha256 must be hex")
    if value["decision"] not in ("approved", "revised"):
        raise AssertionError("approval decision must be approved or revised")
    _text(value["approver"], 1, 200, "approval approver")
    _text(value["decided_at"], 1, 64, "approval decided_at")
    if "thread_id" in value:
        _text(value["thread_id"], 1, 128, "approval thread_id")


def assert_review(value):
    _object(value, REVIEW_REQUIRED + REVIEW_OPTIONAL, REVIEW_REQUIRED, "review")
    if value["contract"] != "skill75" or value["version"] != 1:
        raise AssertionError("review contract must be skill75 version 1")
    if value["kind"] != "review":
        raise AssertionError("review kind must be 'review'")
    _text(value["reviewer"], 1, 200, "review reviewer")
    _text(value["actor"], 0, 200, "review actor")
    if value["verdict"] not in ("pass", "fail"):
        raise AssertionError("review verdict must be pass or fail")
    if "scope" in value:
        _text(value["scope"], 1, 64, "review scope")
    if "revision" in value:
        _positive_int(value["revision"], "review revision")


def assert_patch_body(body):
    _object(body, BODY_REQUIRED + BODY_OPTIONAL, BODY_REQUIRED, "PATCH body")
    _text(body["stage_slug"], 1, 64, "PATCH stage_slug")
    if body["status"] not in CARD_STATUSES:
        raise AssertionError("unknown status %r" % (body["status"],))
    for key, high in (("reason", 2000), ("actor", 200), ("evidence", 4000),
                      ("reviewer", 200), ("ask", 500)):
        if key in body and body[key] is not None:
            _text(body[key], 0, high, "PATCH %s" % key)
    if body.get("blocked_reason") is not None and \
            body["blocked_reason"] not in ("decision", "approval", "credential", "payment"):
        raise AssertionError("unknown blocked_reason")
    if body.get("blocked_on_human") is not None and \
            body["blocked_on_human"] not in ("owner", "operator"):
        raise AssertionError("unknown blocked_on_human")
    if "approval" in body:
        assert_approval(body["approval"])
    if "review" in body:
        assert_review(body["review"])


# --------------------------------------------------------------------------- #
# a run dir, written the way the run itself writes each record
# --------------------------------------------------------------------------- #

def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def fixture_run(root, with_storyboard=True, maker="builder-bot", reviewer="reviewer-bot"):
    run = Path(root)
    _write(run / "control" / "origin.json",
           {"schema": "blackceo.origin/v1", "channel": "telegram",
            "conversation_id": "9", "thread_id": "th-1"})
    _write(run / "creative" / "script-approval.json", {
        "schema_version": 2, "required": True, "status": "approved", "sent": True,
        "artifacts": {"script": {"revision": 2, "sha256": "a" * 64},
                      "lyrics": {"revision": 3, "sha256": "b" * 64}},
        "asks": [], "outbox": [],
        "approvals": [
            {"event_id": "e-script", "kind": "script", "decision": "approved",
             "revision": 2, "sha256": "a" * 64, "approved_by": "client-9",
             "timestamp": "2026-11-11T18:00:00Z", "thread_id": "th-1",
             "state": "active"},
            {"event_id": "e-old", "kind": "lyrics", "decision": "approved",
             "revision": 2, "sha256": "c" * 64, "approved_by": "client-9",
             "timestamp": "2026-11-11T17:00:00Z", "state": "invalidated"},
            {"event_id": "e-lyrics", "kind": "lyrics", "decision": "approved",
             "revision": 3, "sha256": "b" * 64, "approved_by": "client-9",
             "timestamp": "2026-11-11T18:05:00Z", "thread_id": "th-1",
             "state": "active"},
        ]})
    _write(run / "character" / "approval.json", {
        "schema": "blackceo.character-approval/v1", "status": "approved",
        "artifact_kind": "character_bible", "bible_revision": 2,
        "image_hashes": {"mara": {"front": "d" * 64}},
        "class_hashes": {"mara": {"image": {"appearance": "e" * 64}}},
        "origin": {"channel": "telegram", "conversation_id": "9", "thread_id": "th-1"},
        "approved_by": "client-9", "at": 1762884000.0})
    _write(run / "song-choices" / "state.json", {
        "required": True, "offered": {"2": {"label": "2 - Warm", "file": "x.mp3"}},
        "target": "9",
        "provenance": {"who": "client-9", "channel": "telegram",
                       "at": "2026-11-11T18:30:00Z"}})
    _write(run / "song-choices" / "pick.json",
           {"pick": 2, "label": "2 - Warm", "sha256": "f" * 64, "take": 1})
    if with_storyboard:
        _write(run / "storyboard" / "approval.json", {
            "state": "approved", "choice": "yes", "at": 1762887600.0,
            "shots": {"s1": {"status": "approved", "revision": "1" * 64,
                             "still_sha256": "2" * 64}},
            "invalidations": [],
            "decision": {"scope": "whole-package", "reply_text": "GO",
                         "at": 1762887600.0}})
    _write(run / "delivery" / "delivery-receipt.json", {
        "song_files": [{"kind": "song", "file": "01 - Full Song.mp3",
                        "sha256": "3" * 64}],
        "video_delivery": [{"file": "05 - Video Captioned.mp4", "sha256": "4" * 64}]})
    _write(run / "qc" / "records.json", [
        {"schema_version": "1.0.0", "check_id": "final_edit", "run_id": JOB,
         "stage": "final-qc", "check": "audio", "verdict": "PASS",
         "evidence": {"summary": "measured delivery audio"},
         "checker_version": "1.0.0",
         "reviewer": {"identity": reviewer, "session": "sess-1", "authority": "qc"}}])
    _write(run / "qc" / "makers.json", {"final_edit": maker})
    return run


def _last_payload(outbox):
    row = outbox.db.execute(
        "SELECT payload FROM outbox ORDER BY id DESC LIMIT 1").fetchone()
    return json.loads(row[0]) if row else None


class CompletionEvidence(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

    def test_all_six_approvals_and_the_review(self):
        result = CC.build(str(fixture_run(self.root)))
        kinds = [record["artifact_kind"] for record in result["approvals"]]
        self.assertEqual(kinds, list(APPROVAL_KINDS))
        for record in result["approvals"]:
            assert_approval(record)
            self.assertEqual(record["decision"], "approved")
        self.assertEqual(result["approval"]["artifact_kind"], "final")
        self.assertEqual(result["review"]["kind"], "review")
        self.assertEqual(result["review"]["verdict"], "pass")
        self.assertNotEqual(result["review"]["reviewer"], result["review"]["actor"])
        # the active decision is the current revision, never the invalidated one
        lyrics = next(r for r in result["approvals"] if r["artifact_kind"] == "lyrics")
        self.assertEqual(lyrics["revision"], 3)
        self.assertEqual(lyrics["sha256"], "b" * 64)

    def test_patch_body_is_accepted_by_the_board_schema(self):
        result = CC.build(str(fixture_run(self.root)))
        body = {"stage_slug": "epic", "status": "done", "actor": "builder-bot",
                "reviewer": "reviewer-bot", "evidence": "delivered package",
                "approval": result["approval"], "review": result["review"]}
        assert_patch_body(body)

    def test_missing_storyboard_approval_raises(self):
        run = fixture_run(self.root, with_storyboard=False)
        with self.assertRaises(CC.CompletionEvidenceMissing) as caught:
            CC.build(str(run))
        self.assertIn("storyboard", str(caught.exception))
        self.assertIn("storyboard", caught.exception.which)

    def test_self_review_is_refused(self):
        run = fixture_run(self.root, maker="reviewer-bot")
        with self.assertRaises(CC.CompletionEvidenceMissing) as caught:
            CC.build(str(run))
        self.assertIn("independent", str(caught.exception))


class SyncPayloads(unittest.TestCase):
    def setUp(self):
        self.outbox = CS.Outbox(db_path=":memory:", workspace=WS)
        self.addCleanup(self.outbox.db.close)

    def test_create_carries_contract_and_requester_fields(self):
        self.outbox.enqueue_create(
            JOB, "Drama Song Ad", [{"slug": "research"}], WS,
            requester_channel="telegram", requester_chat_id="9",
            requester_session_key="agent:bot:9")
        payload = _last_payload(self.outbox)
        self.assertEqual(payload["contract"], {"kind": "skill75", "version": 1})
        self.assertEqual(payload["requester_channel"], "telegram")
        self.assertEqual(payload["requester_chat_id"], "9")
        self.assertEqual(payload["requester_session_key"], "agent:bot:9")

    def test_move_carries_approval_and_review(self):
        with tempfile.TemporaryDirectory() as root:
            result = CC.build(str(fixture_run(root)))
        self.outbox.enqueue_stage_deliverable(
            JOB, "delivery", "https://example.test/05.mp4", "Video captioned", WS)
        self.outbox.enqueue_move(
            JOB, "delivery", "done", "builder-bot", WS, evidence="delivered package",
            reviewer="reviewer-bot", approval=result["approval"], review=result["review"])
        payload = _last_payload(self.outbox)
        self.assertEqual(payload["approval"], result["approval"])
        self.assertEqual(payload["review"], result["review"])
        assert_approval(payload["approval"])
        assert_review(payload["review"])

    def test_malformed_approval_is_refused_before_queueing(self):
        before = self.outbox.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
        bad = {"contract": "skill75", "version": 1, "kind": "approval",
               "artifact_kind": "music", "revision": 0, "decision": "approved",
               "approver": "client-9", "decided_at": "2026-11-11T18:30:00Z"}
        with self.assertRaises(CS.BoardSyncError):
            self.outbox.enqueue_move(JOB, "delivery", "review", "builder-bot", WS,
                                     evidence="x", approval=bad)
        with self.assertRaises(CS.BoardSyncError):
            self.outbox.enqueue_move(
                JOB, "delivery", "review", "builder-bot", WS, evidence="x",
                approval=dict(bad, revision=1, unknown_field="typo"))
        after = self.outbox.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
