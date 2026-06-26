#!/usr/bin/env python3
"""
test_cc_board.py — hermetic tests for the producer-side Command Center board
caller (cc_board.py). Stdlib unittest only; NO live network — every HTTP call is
intercepted so the suite is deterministic and offline.

Covers the contract that matters:
  * FAIL-SOFT: no MISSION_CONTROL_URL => clean no-op (None / False), never raises.
  * AUTH PARITY: Bearer MC_API_TOKEN + x-webhook-signature = HMAC-SHA256(
    WEBHOOK_SECRET, EXACT rawBody) hex — recomputed the way the route handler
    verifies it.
  * REQUEST CONTRACT: POST /api/ad-campaigns body shape; PATCH
    /api/ad-campaigns/{id} body shape incl. the blocked-move requirements.
  * LEGAL-PATH walk: backlog->done expands to in_progress->review->done.
  * FAIL-SOFT on transport errors (URLError / HTTPError / timeout) => None/False.
  * stamp_campaign_id merges into s7-deliver-receipt.json without clobbering.
"""

import hashlib
import hmac
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cc_board  # noqa: E402


# ---------------------------------------------------------------------------
# A fake HTTP layer: records the last request and returns a scripted response.
# ---------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, status, payload):
        self._status = status
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def getcode(self):
        return self._status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Recorder:
    """Stand-in for urllib.request.urlopen. Captures requests and replays a queue
    of (status, payload) responses; a response may be an Exception to raise."""

    def __init__(self):
        self.requests = []
        self.responses = []

    def queue(self, status, payload):
        self.responses.append((status, payload))

    def queue_raise(self, exc):
        self.responses.append(exc)

    def __call__(self, req, timeout=None):
        self.requests.append({
            "method": req.get_method(),
            "url": req.full_url,
            "headers": {k.lower(): v for k, v in req.header_items()},
            "body": req.data.decode("utf-8") if req.data else "",
            "timeout": timeout,
        })
        if not self.responses:
            raise AssertionError("no scripted response queued")
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        status, payload = nxt
        if status >= 400:
            raise urllib.error.HTTPError(
                req.full_url, status, "err", {}, io.BytesIO(json.dumps(payload).encode()))
        return _FakeResp(status, payload)


ENV = {
    "MISSION_CONTROL_URL": "https://cc.example.test/",
    "MC_API_TOKEN": "tok-abc",
    "WEBHOOK_SECRET": "shh-secret",
}


class FailSoftTest(unittest.TestCase):
    def test_no_url_create_is_noop(self):
        self.assertIsNone(cc_board.create_campaign("j1", "Show", env={}))

    def test_no_url_move_is_noop(self):
        self.assertFalse(cc_board.set_stage_status("j1", "s0-intake", "done", env={}))

    def test_config_none_without_url(self):
        self.assertIsNone(cc_board.board_config({"MC_API_TOKEN": "x"}))


class AuthAndContractTest(unittest.TestCase):
    def setUp(self):
        self.rec = _Recorder()
        self._orig = cc_board.urllib.request.urlopen
        cc_board.urllib.request.urlopen = self.rec

    def tearDown(self):
        cc_board.urllib.request.urlopen = self._orig

    def _verify_signature(self, request):
        """Recompute the signature exactly as the route handler does."""
        body = request["body"].encode("utf-8")
        expected = hmac.new(b"shh-secret", body, hashlib.sha256).hexdigest()
        self.assertEqual(request["headers"]["x-webhook-signature"], expected)

    def test_create_contract_and_auth(self):
        self.rec.queue(201, {"ok": True, "created": True, "campaign_id": "j1",
                             "parent_id": "p", "stages": [{"slug": "s0-intake"}]})
        cid = cc_board.create_campaign(
            "j1", "My Show", env=ENV,
            stages=[{"slug": "s0-intake", "title": "Intake"}, {"slug": "publish"}],
            owner="Trev", department="paid-advertisement",
            money_ceiling_usd=200, estimated_cost_usd=50, agent_id="agent-x")
        self.assertEqual(cid, "j1")
        req = self.rec.requests[-1]
        self.assertEqual(req["method"], "POST")
        self.assertEqual(req["url"], "https://cc.example.test/api/ad-campaigns")
        self.assertEqual(req["headers"]["authorization"], "Bearer tok-abc")
        self.assertEqual(req["headers"]["content-type"], "application/json")
        self._verify_signature(req)
        body = json.loads(req["body"])
        self.assertEqual(body["job_id"], "j1")
        self.assertEqual(body["show_name"], "My Show")
        self.assertEqual(body["owner"], "Trev")
        self.assertEqual(body["money_ceiling_usd"], 200)
        self.assertEqual(body["agent_id"], "agent-x")
        self.assertEqual(body["stages"][0], {"slug": "s0-intake", "title": "Intake"})
        self.assertEqual(body["stages"][1], {"slug": "publish"})  # no title key

    def test_no_secret_means_no_signature_header(self):
        self.rec.queue(200, {"ok": True, "created": False, "campaign_id": "j2",
                             "parent_id": None, "stages": []})
        env = {"MISSION_CONTROL_URL": "https://cc.example.test", "MC_API_TOKEN": "t"}
        cc_board.create_campaign("j2", "S", env=env)
        req = self.rec.requests[-1]
        self.assertNotIn("x-webhook-signature", req["headers"])
        self.assertEqual(req["headers"]["authorization"], "Bearer t")

    def test_move_blocked_contract(self):
        # GET current status, then a single direct blocked move.
        self.rec.queue(200, {"campaign": {}, "cards": [
            {"stage_slug": "s5-image-gen", "status": "in_progress"}]})
        self.rec.queue(200, {"task": {"status": "blocked"}})
        ok = cc_board.set_stage_status(
            "j1", "s5-image-gen", "blocked", env=ENV,
            blocked_reason="payment", ask="top up the Kie balance, then --resume")
        self.assertTrue(ok)
        patch = self.rec.requests[-1]
        self.assertEqual(patch["method"], "PATCH")
        self.assertEqual(patch["url"], "https://cc.example.test/api/ad-campaigns/j1")
        self._verify_signature(patch)
        body = json.loads(patch["body"])
        self.assertEqual(body["stage_slug"], "s5-image-gen")
        self.assertEqual(body["status"], "blocked")
        self.assertEqual(body["blocked_reason"], "payment")
        self.assertTrue(body["ask"])

    def test_blocked_without_reason_refused_locally(self):
        # No GET / PATCH should be issued — refused before any network call.
        ok = cc_board.set_stage_status("j1", "s5", "blocked", env=ENV, ask="x")
        self.assertFalse(ok)
        self.assertEqual(self.rec.requests, [])

    def test_legal_path_walk_backlog_to_done(self):
        # current=backlog -> walk in_progress, review, done (GET + 3 PATCH).
        self.rec.queue(200, {"campaign": {}, "cards": [
            {"stage_slug": "s0-intake", "status": "backlog"}]})
        self.rec.queue(200, {"task": {}})
        self.rec.queue(200, {"task": {}})
        self.rec.queue(200, {"task": {}})
        ok = cc_board.set_stage_status("j1", "s0-intake", "done", env=ENV)
        self.assertTrue(ok)
        patches = [r for r in self.rec.requests if r["method"] == "PATCH"]
        statuses = [json.loads(p["body"])["status"] for p in patches]
        self.assertEqual(statuses, ["in_progress", "review", "done"])

    def test_create_http_error_is_failsoft(self):
        self.rec.queue(500, {"error": "boom"})
        self.assertIsNone(cc_board.create_campaign("j1", "S", env=ENV))

    def test_create_urlerror_is_failsoft(self):
        self.rec.queue_raise(urllib.error.URLError("conn refused"))
        self.assertIsNone(cc_board.create_campaign("j1", "S", env=ENV))


class LegalPathUnitTest(unittest.TestCase):
    def test_paths(self):
        self.assertEqual(cc_board._legal_path("backlog", "done"),
                         ["in_progress", "review", "done"])
        self.assertEqual(cc_board._legal_path("in_progress", "done"),
                         ["review", "done"])
        self.assertEqual(cc_board._legal_path("review", "done"), ["done"])
        self.assertEqual(cc_board._legal_path("in_progress", "blocked"), ["blocked"])
        self.assertEqual(cc_board._legal_path("done", "done"), [])


class StampReceiptTest(unittest.TestCase):
    def test_stamp_merges_without_clobber(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            rp = rd / "working" / "checkpoints" / "s7-deliver-receipt.json"
            rp.parent.mkdir(parents=True)
            rp.write_text(json.dumps({"delivered": [{"idx": 0}], "counts": {"images": 10}}))
            self.assertTrue(cc_board.stamp_campaign_id(rd, "job-xyz"))
            got = json.loads(rp.read_text())
            self.assertEqual(got["campaign_id"], "job-xyz")
            self.assertEqual(got["delivered"], [{"idx": 0}])  # untouched
            self.assertEqual(got["counts"], {"images": 10})

    def test_stamp_creates_receipt_when_absent(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            self.assertTrue(cc_board.stamp_campaign_id(rd, "job-1"))
            got = json.loads((rd / "working" / "checkpoints"
                              / "s7-deliver-receipt.json").read_text())
            self.assertEqual(got["campaign_id"], "job-1")

    def test_stamp_empty_id_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(cc_board.stamp_campaign_id(Path(d), ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
