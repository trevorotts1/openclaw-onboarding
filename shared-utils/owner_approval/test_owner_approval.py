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

STATE = {"posts": 0, "status": "pending", "auth": [], "bodies": [], "chat": [], "chat_reply": None}


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
        if self.path.endswith("/chat-decision"):
            body = json.loads(raw or b"{}")
            STATE["chat"].append((self.path, body))
            code, out = STATE["chat_reply"] or (200, {"status": "approved", "approval_id": "apr_12345678"})
            if code == 200:
                STATE["status"] = "approved" if out.get("status") == "approved" else "changes_requested"
            return self._send(code, out)
        if self.path != "/api/approval-requests":
            return self._send(404, {})
        STATE["posts"] += 1
        STATE["bodies"].append(json.loads(raw or b"{}"))
        self._send(201, {"request_id": "req_abc123", "status": "pending", "path": "/approvals/req_abc123", "approval_url": None})

    def do_GET(self):
        STATE["auth"].append(self.headers.get("Authorization"))
        if self.path != "/api/approval-requests/req_abc123":
            return self._send(404, {})
        out = {"status": STATE["status"], "short_code": "req_ab", "approve_by": "2026-11-19T00:00:00Z"}
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
        STATE.update(posts=0, status="pending", auth=[], bodies=[], chat=[], chat_reply=None)

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

    def test_chat_approved_fallback_gives_link_and_does_not_proceed(self):
        rec = self.req()
        msg = oa.owner_message(rec, chat_said_approved=True)
        self.assertIn(rec["approval_url"], msg)
        self.assertIn("Command Center to confirm", msg)

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

REF = "telegram:555:9001"


class ChatApprovals(T):
    """The owner answers in chat, by button, or in Command Center: every kind, one path."""

    def test_every_kind_message_has_inline_preview_code_link_and_three_ways(self):
        for kind in oa.KINDS:
            rec = self.req(kind=kind, object_key="k-" + kind, plan_sha256=kind.encode().hex().ljust(64, "0")[:64],
                           preview_text=f"Headline for {kind}")
            msg = oa.owner_message(rec)
            self.assertIn(f"Headline for {kind}", msg, kind)                 # inline, not behind a link
            self.assertIn("Code: " + rec["request_id"][:6], msg, kind)
            self.assertIn(rec["approval_url"], msg, kind)
            self.assertIn("Reply right here", msg, kind)
            self.assertIn("button", msg, kind)
            self.assertIn("Command Center", msg, kind)
            self.assertNotIn("awaiting your approval", msg.lower(), kind)

    def test_unknown_kind_refused_before_any_request(self):
        with self.assertRaises(oa.ApprovalError):
            self.req(kind="made_up")
        self.assertEqual(STATE["posts"], 0)

    def test_preview_files_text_inline_images_attached(self):
        d = Path(tempfile.mkdtemp())
        (d / "copy.md").write_text("HERO: Grow your business this Black Friday")
        (d / "wire.png").write_bytes(b"\x89PNG")
        (d / "mock.pdf").write_bytes(b"%PDF")
        text, atts = oa.collect_preview([str(d / "copy.md"), str(d / "wire.png"), str(d / "mock.pdf")])
        self.assertIn("HERO: Grow your business", text)
        self.assertEqual([Path(a).name for a in atts], ["wire.png", "mock.pdf"])
        rec = self.req(preview_text=text, attachments=atts, kind="design_board")
        msg = oa.owner_message(rec)
        self.assertIn("HERO: Grow your business", msg)
        self.assertIn("wire.png", msg)
        self.assertIn("mock.pdf", msg)
        with self.assertRaises(oa.ApprovalError):
            oa.collect_preview([str(d / "nope.png")])
        (d / "x.zip").write_bytes(b"PK")
        with self.assertRaises(oa.ApprovalError):
            oa.collect_preview([str(d / "x.zip")])

    def test_chat_decision_approve_sends_contract_body_and_returns_cc_id(self):
        rec = self.req()
        out = oa.chat_decision(rec["request_id"], decision="approve", channel="telegram", source_message_ref=REF)
        path, body = STATE["chat"][0]
        self.assertEqual(path, "/api/approval-requests/req_abc123/chat-decision")
        self.assertEqual(body, {"decision": "approve", "channel": "telegram", "source_message_ref": REF})
        self.assertEqual(STATE["auth"][-1], "Bearer tok_test")
        self.assertEqual(out["status"], "approved")
        self.assertEqual(out["approval_id"], "apr_12345678")           # read back from Command Center
        self.assertEqual(oa.main(["status", "--request-id", rec["request_id"]]), oa.EXIT_OK)

    def test_chat_decision_cli_approve_exit_and_shell_exports(self):
        import io, contextlib
        rec = self.req()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = oa.main(["chat-decision", "--request-id", rec["request_id"], "--decision", "approve",
                          "--channel", "telegram", "--source-message-ref", REF, "--shell"])
        self.assertEqual(rc, oa.EXIT_OK)
        self.assertIn("export CAF_APPROVAL_ID=apr_12345678", buf.getvalue())

    def test_chat_decision_changes_carries_note_and_exit_4(self):
        import io, contextlib
        rec = self.req()
        STATE["chat_reply"] = (200, {"status": "changes_requested", "approval_id": None})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = oa.main(["chat-decision", "--request-id", rec["request_id"], "--decision", "changes",
                          "--channel", "webchat", "--source-message-ref", "webchat:sess1:77",
                          "--note", "shorter headline"])
        self.assertEqual(rc, oa.EXIT_CHANGES)
        self.assertEqual(STATE["chat"][0][1]["note"], "shorter headline")
        self.assertEqual(STATE["chat"][0][1]["decision"], "changes")
        self.assertNotIn("apr_", buf.getvalue())
        self.assertIsNone(oa.check_status(rec["request_id"]).get("approval_id"))

    def test_refusal_reason_is_relayed_with_link_and_nothing_is_approved(self):
        import io, contextlib
        for code in (403, 409):
            STATE.update(chat=[], chat_reply=(code, {"reason": "That message did not come from the account owner."}))
            rec = self.req(object_key=f"obj-{code}")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = oa.main(["chat-decision", "--request-id", rec["request_id"], "--decision", "approve",
                              "--channel", "telegram", "--source-message-ref", REF])
            self.assertEqual(rc, oa.EXIT_REFUSED)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["status"], "refused")
            self.assertIn("did not come from the account owner", out["reason"])
            self.assertIn("did not come from the account owner", out["owner_message"])
            self.assertIn(rec["approval_url"], out["owner_message"])
            self.assertIn("Code: ", out["owner_message"])
            self.assertIsNone(oa._load(rec["request_id"]).get("approval_id"))

    def test_approve_answer_that_is_not_approved_is_not_trusted(self):
        rec = self.req()
        STATE["chat_reply"] = (200, {"status": "pending"})
        with self.assertRaises(oa.ApprovalError):
            oa.chat_decision(rec["request_id"], decision="approve", channel="telegram", source_message_ref=REF)

    def test_approved_but_readback_not_approved_fails_closed(self):
        rec = self.req()
        orig = Fake.do_GET

        def pending(self):
            self._send(200, {"status": "pending"})
        Fake.do_GET = pending
        try:
            with self.assertRaises(oa.ApprovalError):
                oa.chat_decision(rec["request_id"], decision="approve", channel="telegram", source_message_ref=REF)
        finally:
            Fake.do_GET = orig

    def test_already_approved_is_never_asked_or_posted_again(self):
        rec = self.req()
        oa.chat_decision(rec["request_id"], decision="approve", channel="telegram", source_message_ref=REF)
        n = len(STATE["chat"])
        again = oa.chat_decision(rec["request_id"], decision="approve", channel="telegram", source_message_ref="telegram:555:9002")
        self.assertEqual(len(STATE["chat"]), n)
        self.assertTrue(again["already_approved"])
        self.assertEqual(again["approval_id"], "apr_12345678")
        again2 = self.req()                                  # same plan, already approved: reused, no new POST
        self.assertTrue(again2["reused"])
        self.assertEqual(STATE["posts"], 1)

    def test_made_up_or_mismatched_message_reference_refused_locally(self):
        rec = self.req()
        for ref in ("", "just yes", "telegram:555", "webchat:s:1"):
            with self.assertRaises(oa.ApprovalError):
                oa.chat_decision(rec["request_id"], decision="approve", channel="telegram", source_message_ref=ref)
        self.assertEqual(STATE["chat"], [])

    def test_agent_text_is_never_a_decision_field(self):
        # the only things sent are decision, channel, source_message_ref, note: no approval id, no actor
        rec = self.req()
        oa.chat_decision(rec["request_id"], decision="approve", channel="telegram", source_message_ref=REF)
        self.assertEqual(set(STATE["chat"][0][1]), {"decision", "channel", "source_message_ref"})

    def test_status_keeps_short_code_and_deadline(self):
        rec = self.req()
        out = oa.check_status(rec["request_id"])
        self.assertEqual(out["short_code"], "req_ab")
        self.assertEqual(out["approve_by"], "2026-11-19T00:00:00Z")

    def _fake_gateway(self):
        d = Path(tempfile.mkdtemp())
        log = d / "calls.jsonl"
        exe = d / "fakeclaw"
        exe.write_text("#!/usr/bin/env python3\nimport sys, json\n"
                       f"open({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
                       "sys.exit(1 if '--presentation' in sys.argv and %s else 0)\n" % "FAIL_BUTTONS")
        return d, exe, log

    def test_deliver_telegram_sends_text_media_and_buttons_through_gateway(self):
        d, exe, log = self._fake_gateway()
        exe.write_text(exe.read_text().replace("FAIL_BUTTONS", "False"))
        exe.chmod(0o755)
        os.environ["OWNER_APPROVAL_SEND_CMD"] = str(exe)
        try:
            (d / "wire.png").write_bytes(b"\x89PNG")
            rec = self.req(kind="design_board", preview_text="HERO copy", attachments=[str(d / "wire.png")])
            res = oa.deliver(rec, channel="telegram", target="555")
        finally:
            os.environ.pop("OWNER_APPROVAL_SEND_CMD")
        self.assertTrue(res["delivered"])
        argv = json.loads(log.read_text().splitlines()[0])
        self.assertEqual(argv[:6], ["message", "send", "--channel", "telegram", "--target", "555"])
        msg = argv[argv.index("--message") + 1]
        self.assertIn("HERO copy", msg)
        self.assertIn("Code: " + rec["request_id"][:6], msg)
        self.assertIn(rec["approval_url"], msg)
        self.assertEqual(argv[argv.index("--media") + 1], str(d / "wire.png"))
        self.assertIn("--presentation", argv)

    def test_deliver_retries_without_buttons_when_gateway_rejects_them(self):
        d, exe, log = self._fake_gateway()
        exe.write_text(exe.read_text().replace("FAIL_BUTTONS", "True"))
        exe.chmod(0o755)
        os.environ["OWNER_APPROVAL_SEND_CMD"] = str(exe)
        try:
            rec = self.req()
            res = oa.deliver(rec, channel="telegram", target="555")
        finally:
            os.environ.pop("OWNER_APPROVAL_SEND_CMD")
        calls = [json.loads(x) for x in log.read_text().splitlines()]
        self.assertEqual(len(calls), 2)
        self.assertIn("--presentation", calls[0])
        self.assertNotIn("--presentation", calls[1])
        self.assertTrue(res["delivered"])
        self.assertFalse(res["buttons"])

    def test_deliver_gateway_failure_is_reported_not_swallowed(self):
        d = Path(tempfile.mkdtemp())
        exe = d / "bad"
        exe.write_text("#!/bin/sh\nexit 1\n")
        exe.chmod(0o755)
        os.environ["OWNER_APPROVAL_SEND_CMD"] = str(exe)
        try:
            with self.assertRaises(oa.ApprovalError):
                oa.deliver(self.req(), channel="telegram", target="555")
        finally:
            os.environ.pop("OWNER_APPROVAL_SEND_CMD")

    def test_deliver_webchat_returns_text_and_files_for_the_agents_own_reply(self):
        rec = self.req(attachments=["/tmp/x.png"])
        res = oa.deliver(rec, channel="webchat")
        self.assertFalse(res["delivered"])
        self.assertIn("Code: ", res["text"])
        self.assertEqual(res["attachments"], ["/tmp/x.png"])

    def test_deliver_cli_refuses_when_already_approved(self):
        rec = self.req()
        oa.chat_decision(rec["request_id"], decision="approve", channel="telegram", source_message_ref=REF)
        self.assertEqual(oa.main(["deliver", "--request-id", rec["request_id"], "--channel", "webchat"]), oa.EXIT_USAGE)

    def test_pending_lists_only_waiting_requests(self):
        a = self.req(object_key="one")
        rows = oa.list_pending()
        self.assertEqual([r["request_id"] for r in rows], [a["request_id"]])
        oa.chat_decision(a["request_id"], decision="approve", channel="telegram", source_message_ref=REF)
        self.assertEqual(oa.list_pending(), [])


if __name__ == "__main__":
    unittest.main()
