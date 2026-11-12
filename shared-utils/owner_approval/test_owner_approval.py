"""Tests for owner_approval.py against a fake Command Center on loopback."""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import owner_approval as oa  # noqa: E402

STATE = {"posts": 0, "status": "pending", "auth": [], "bodies": []}


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        STATE["auth"].append(self.headers.get("Authorization"))
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path != "/api/approval-requests":
            return self._send(404, {})
        STATE["posts"] += 1
        STATE["bodies"].append(json.loads(raw or b"{}"))
        self._send(201, {"request_id": "req_abc123", "status": "pending", "path": "/approvals/req_abc123", "approval_url": None})

    def do_GET(self):
        STATE["auth"].append(self.headers.get("Authorization"))
        if self.path != "/api/approval-requests/req_abc123":
            return self._send(404, {})
        out = {"status": STATE["status"]}
        if STATE["status"] == "approved":
            out["approval_id"] = "apr_12345678"
        self._send(200, out)


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ.update(MISSION_CONTROL_URL=f"http://127.0.0.1:{self.srv.server_port}",
                          MC_API_TOKEN="tok_test", OWNER_APPROVAL_STATE_DIR=self.tmp)
        STATE.update(posts=0, status="pending", auth=[], bodies=[])

    def req(self, **kw):
        base = dict(kind="publish", location_id="LOC1", action="social_publish", object_key="wk-46",
                    plan_sha256="a" * 64, summary="Nine posts go out Nov 9-15.", preview_text="Post 1: hello")
        base.update(kw)
        return oa.request_approval(**base)

    def test_request_returns_absolute_link_and_bearer(self):
        rec = self.req()
        self.assertTrue(rec["approval_url"].startswith("http://127.0.0.1:"))
        self.assertTrue(rec["approval_url"].endswith("/approvals/req_abc123"))
        self.assertEqual(STATE["auth"][0], "Bearer tok_test")

    def test_same_plan_is_not_requested_twice(self):
        self.req()
        again = self.req()
        self.assertTrue(again["reused"])
        self.assertEqual(STATE["posts"], 1)

    def test_body_matches_final_contract(self):
        self.req(preview_url="https://x.test/p")
        b = STATE["bodies"][0]
        self.assertEqual(b["kind"], "publish")
        self.assertEqual(b["preview"]["text"], "Post 1: hello")
        self.assertEqual(b["preview"]["links"][0]["url"], "https://x.test/p")
        for k in ("location_id", "action", "object_key", "plan_sha256", "title", "summary"):
            self.assertIn(k, b)
        self.assertNotIn("preview_text", b)

    def test_shell_export_binds_gate_env(self):
        import io, contextlib
        rec = self.req()
        STATE["status"] = "approved"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            oa.main(["status", "--request-id", rec["request_id"], "--shell"])
        out = buf.getvalue()
        for line in ("export CAF_APPROVAL_ID=apr_12345678", "export CAF_WRITE_ACTION=social_publish",
                     "export CAF_OBJECT_KEY=wk-46", "export CAF_PLAN_SHA256=" + "a" * 64):
            self.assertIn(line, out)

    def test_changed_plan_makes_a_new_request(self):
        self.req()
        self.req(plan_sha256="b" * 64)
        self.assertEqual(STATE["posts"], 2)

    def test_pending_has_no_approval_id(self):
        rec = self.req()
        out = oa.check_status(rec["request_id"])
        self.assertEqual(out["status"], "pending")
        self.assertIsNone(out["approval_id"])

    def test_approved_returns_id_and_shell_export(self):
        rec = self.req()
        STATE["status"] = "approved"
        out = oa.check_status(rec["request_id"])
        self.assertEqual(out["approval_id"], "apr_12345678")

    def test_approved_without_id_is_refused(self):
        rec = self.req()
        STATE["status"] = "approved"
        orig = Fake.do_GET

        def bad(self):
            self._send(200, {"status": "approved"})
        Fake.do_GET = bad
        try:
            with self.assertRaises(oa.ApprovalError):
                oa.check_status(rec["request_id"])
        finally:
            Fake.do_GET = orig

    def test_unknown_status_is_not_approval(self):
        rec = self.req()
        STATE["status"] = "maybe"
        with self.assertRaises(oa.ApprovalError):
            oa.check_status(rec["request_id"])

    def test_message_always_has_link_and_preview(self):
        rec = self.req()
        for kw in ({}, {"reminder": True}, {"chat_said_approved": True}):
            msg = oa.owner_message(rec, **kw)
            self.assertIn(rec["approval_url"], msg)
            self.assertIn("Post 1: hello", msg)
            self.assertNotIn("awaiting your approval", msg.lower())

    def test_chat_approved_answer_gives_link_not_proceed(self):
        rec = self.req()
        msg = oa.owner_message(rec, chat_said_approved=True)
        self.assertIn("tap this one link", msg)

    def test_unreachable_fails_closed(self):
        os.environ["MISSION_CONTROL_URL"] = "http://127.0.0.1:1"
        with self.assertRaises(oa.ApprovalError):
            self.req()

    def test_plain_http_non_loopback_refused(self):
        os.environ["MISSION_CONTROL_URL"] = "http://example.com"
        with self.assertRaises(oa.ApprovalError):
            self.req()

    def test_cli_exit_codes(self):
        rec = self.req()
        self.assertEqual(oa.main(["status", "--request-id", rec["request_id"]]), oa.EXIT_PENDING)
        STATE["status"] = "approved"
        self.assertEqual(oa.main(["status", "--request-id", rec["request_id"], "--shell"]), oa.EXIT_OK)

    def test_token_never_printed(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            oa.main(["request", "--kind", "publish", "--action", "x", "--plan-sha256", "c" * 64,
                     "--summary", "s", "--location-id", "L"])
        self.assertNotIn("tok_test", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
