#!/usr/bin/env python3
"""cc_owner_questions: list, match and answer against a fake Command Center.

Run: python3 tests/unit/test_cc_owner_questions.py
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "shared-utils" / "cc_owner_questions" / "cc_owner_questions.py"
TOKEN = "tok-SECRET-9f8e7d"

QUESTIONS = [{"id": "uuid-1", "task_id": "t1", "task_title": "Landing page", "kind": "audience",
              "short_code": "Q-ABC123", "question": "Is this for new clients?",
              "recommendation": "Yes, target new clients.", "asked_at": "x", "pushed_at": "y"}]


class Handler(BaseHTTPRequestHandler):
    mode = {"questions": QUESTIONS, "answer_status": 200, "route": True}
    seen = []

    def log_message(self, *a):
        pass

    def _send(self, status, body=None, raw=None):
        data = raw if raw is not None else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        Handler.seen.append(("GET", self.path, self.headers.get("Authorization"), None))
        if not Handler.mode["route"]:
            return self._send(404, raw=b"<html>not found</html>")
        self._send(200, {"questions": Handler.mode["questions"]})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        Handler.seen.append(("POST", self.path, self.headers.get("Authorization"), body))
        if not Handler.mode["route"]:
            return self._send(404, raw=b"<html>not found</html>")
        st = Handler.mode["answer_status"]
        if st == "text":
            return self._send(200, raw=b"ok")
        if st == "nosuccess":
            return self._send(200, {"applied": True})
        if st == 200:
            return self._send(200, {"success": True, "applied": True, "question": QUESTIONS[0]})
        self._send(st, {"error": "nope"})


class CCQ(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.home = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.home.cleanup()

    def setUp(self):
        Handler.mode = {"questions": QUESTIONS, "answer_status": 200, "route": True}
        Handler.seen = []

    def run_h(self, *args, token=TOKEN):
        env = {"PATH": os.environ["PATH"], "HOME": self.home.name,
               "MC_ROUTE_INGEST_URL": "http://127.0.0.1:%d/api/tasks/ingest" % self.port}
        if token:
            env["MC_API_TOKEN"] = token
        p = subprocess.run([sys.executable, "-I", str(HELPER), *args], env=env,
                           capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr

    def test_open_lists(self):
        rc, out, err = self.run_h("open")
        self.assertEqual(rc, 0)
        self.assertIn("Q-ABC123", out)
        self.assertIn("Is this for new clients?", out)
        self.assertIn("Yes, target new clients.", out)
        rc, out, _ = self.run_h("open", "--json")
        self.assertEqual(json.loads(out)["questions"][0]["short_code"], "Q-ABC123")
        self.assertEqual(Handler.seen[0][1], "/api/owner-questions?status=open")

    def test_answer_posts_path_body_bearer(self):
        rc, out, err = self.run_h("answer", "--ref", "q-abc123", "--text", "YES please",
                                  "--source-message-ref", "msg-77")
        self.assertEqual(rc, 0, err)
        method, path, auth, body = Handler.seen[0]
        self.assertEqual((method, path), ("POST", "/api/owner-questions/Q-ABC123/chat-answer"))
        self.assertEqual(auth, "Bearer " + TOKEN)
        self.assertEqual(body, {"answer": "YES please", "channel": "telegram",
                                "source_message_ref": "msg-77"})

    def test_answer_by_id_and_webchat(self):
        rc, _, err = self.run_h("answer", "--ref", "uuid-1", "--text", "no, do X",
                                "--source-message-ref", "m1", "--channel", "webchat")
        self.assertEqual(rc, 0, err)
        self.assertEqual(Handler.seen[0][1], "/api/owner-questions/uuid-1/chat-answer")
        self.assertEqual(Handler.seen[0][3]["channel"], "webchat")

    def test_match_short_code_needs_no_server_call(self):
        rc, out, _ = self.run_h("match", "--text", "yes (ref q-abc123) go")
        self.assertEqual((rc, out.strip()), (0, "Q-ABC123"))
        self.assertEqual(Handler.seen, [])

    def test_match_single_open(self):
        rc, out, _ = self.run_h("match", "--text", "yes")
        self.assertEqual(rc, 0)
        self.assertIn("single-open", out)
        self.assertIn("Q-ABC123", out)

    def test_match_none_and_ambiguous(self):
        Handler.mode["questions"] = []
        rc, out, _ = self.run_h("match", "--text", "yes")
        self.assertEqual((rc, out.strip()), (1, "none"))
        Handler.mode["questions"] = QUESTIONS + [dict(QUESTIONS[0], id="u2", short_code="Q-ZZZ999")]
        rc, out, _ = self.run_h("match", "--text", "yes")
        self.assertEqual(rc, 1)
        self.assertIn("ambiguous", out)

    def test_old_cc_404_says_needs_update(self):
        Handler.mode["route"] = False
        for args in (("open",), ("answer", "--ref", "Q-ABC123", "--text", "yes",
                                 "--source-message-ref", "m")):
            rc, out, err = self.run_h(*args)
            self.assertEqual(rc, 4)
            self.assertIn("needs updating", err)
            self.assertNotIn("Traceback", err)

    def test_status_mapping(self):
        for status, code in ((404, 5), (409, 6), (422, 7), (500, 8)):
            Handler.mode["answer_status"] = status
            rc, _, err = self.run_h("answer", "--ref", "Q-ABC123", "--text", "yes",
                                    "--source-message-ref", "m")
            self.assertEqual(rc, code, (status, err))

    def test_200_must_confirm_success(self):
        for mode in ("text", "nosuccess"):
            Handler.mode["answer_status"] = mode
            rc, out, err = self.run_h("answer", "--ref", "Q-ABC123", "--text", "yes",
                                      "--source-message-ref", "m")
            self.assertEqual(rc, 8, mode)
            self.assertIn("did not confirm", err)

    def test_bad_ref_rejected(self):
        for ref in ("../x", "a/b", "Q-AB", "x", "Q-ABC123/../.."):
            rc, _, _ = self.run_h("answer", "--ref", ref, "--text", "yes",
                                  "--source-message-ref", "m")
            self.assertEqual(rc, 2, ref)
        self.assertEqual(Handler.seen, [])

    def test_token_never_printed(self):
        outs = []
        for st in (200, 409, 500):
            Handler.mode["answer_status"] = st
            outs.append(self.run_h("answer", "--ref", "Q-ABC123", "--text", "yes",
                                   "--source-message-ref", "m", "--json"))
        outs.append(self.run_h("open", "--json"))
        for rc, out, err in outs:
            self.assertNotIn(TOKEN, out + err)

    def test_no_token_and_unreachable_exit_3(self):
        rc, _, err = self.run_h("open", token="")
        self.assertEqual(rc, 3)
        self.assertIn("MC_API_TOKEN", err)

    def test_usage_errors_exit_2(self):
        self.assertEqual(self.run_h("answer", "--ref", "Q-ABC123")[0], 2)
        self.assertEqual(self.run_h("answer", "--ref", "Q-ABC123", "--text", "  ",
                                    "--source-message-ref", "m")[0], 2)


class Redirect(unittest.TestCase):
    def test_redirect_refused_and_token_not_forwarded(self):
        got = []

        class Sink(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _h(self):
                got.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")
            do_GET = do_POST = _h

        sink = HTTPServer(("127.0.0.1", 0), Sink)
        threading.Thread(target=sink.serve_forever, daemon=True).start()
        target = "http://127.0.0.1:%d/stolen" % sink.server_address[1]

        class Redir(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _h(self):
                n = int(self.headers.get("Content-Length", 0))
                self.rfile.read(n)
                self.send_response(302)
                self.send_header("Location", target)
                self.send_header("Content-Length", "0")
                self.end_headers()
            do_GET = do_POST = _h

        redir = HTTPServer(("127.0.0.1", 0), Redir)
        threading.Thread(target=redir.serve_forever, daemon=True).start()
        env = {"PATH": os.environ["PATH"], "HOME": tempfile.gettempdir(), "MC_API_TOKEN": TOKEN,
               "CC_OWNER_QUESTIONS_URL": "http://127.0.0.1:%d" % redir.server_address[1]}
        try:
            for args in (["open"], ["answer", "--ref", "Q-ABC123", "--text", "yes",
                                    "--source-message-ref", "m"]):
                p = subprocess.run([sys.executable, "-I", str(HELPER), *args], env=env,
                                   capture_output=True, text=True)
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("redirect", p.stderr)
                self.assertNotIn(TOKEN, p.stdout + p.stderr)
            self.assertEqual(got, [])
        finally:
            sink.shutdown()
            redir.shutdown()


class Doctrine(unittest.TestCase):
    def test_block_in_agents_md_and_stamper_idempotent(self):
        text = (ROOT / "AGENTS.md").read_text()
        self.assertEqual(text.count("<!-- CC_OWNER_QUESTIONS_V1 -->"), 1)
        self.assertEqual(text.count("<!-- END CC_OWNER_QUESTIONS_V1 -->"), 1)
        stamper = ROOT / "shared-utils" / "agents-doctrine-blocks.sh"
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "AGENTS.md"
            f.write_text("# Owner\nkeep\n")
            script = '. "$1"; stamp_cc_owner_questions "$2"; stamp_cc_owner_questions "$2"'
            subprocess.run(["bash", "-c", script, "bash", str(stamper), str(f)], check=True,
                           capture_output=True)
            got = f.read_text()
            self.assertTrue(got.startswith("# Owner\nkeep\n"))
            self.assertEqual(got.count("<!-- CC_OWNER_QUESTIONS_V1 -->"), 1)
            self.assertIn("cc_owner_questions.py", got)


if __name__ == "__main__":
    unittest.main()
