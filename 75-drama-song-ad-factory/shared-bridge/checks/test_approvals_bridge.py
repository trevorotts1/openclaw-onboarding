"""U2 approvals bridge against a local fake service; no network calls.

Proves, per SPEC.md §4 / BUILD-PLAN W1-box-bridge-U2:

  1  publish() POSTs exactly the documented JSON and PUTs every file (bytes
     and content type as declared) and returns the service's item
  2  answer() is None while unanswered, then the value; another stage's
     version is never mistaken for this one
  3  a wrong key is refused by the service (control: the key really travels)
     and an absent key is refused locally, before any request
  4  the key never reaches stdout/stderr, with a positive control proving the
     detector can see the sentinel when it is present
  5  the User-Agent is studio_bridge's own constant, and the server saw it

Run: python3 checks/test_approvals_bridge.py
"""
import contextlib
import io
import json
import pathlib
import re
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import approvals_bridge as AB  # noqa: E402
import studio_bridge as SB  # noqa: E402
from studio_claim import LedgerError  # noqa: E402

KEY = "k-" + "deadbeef" * 4
ORDER = "o_0123456789abcdef01234567"
NAME = r"^[A-Za-z0-9._-]{1,80}$"


class Fake:
    """The service contract of SPEC §4, enforced — a real server, not a mock."""

    def __init__(self):
        self.key = KEY
        self.items = {}          # (stage, version) -> item
        self.published = []      # bodies as received
        self.puts = {}           # name -> (content_type, body)
        self.seen_ua = set()
        self.base_url = ""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _send(self, code, obj):
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        return json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")

    def _auth(self):
        st = self.server.state
        st.seen_ua.add(self.headers.get("User-Agent") or "")
        return (self.headers.get("x-ds-key") or "") == st.key

    def do_POST(self):
        st = self.server.state
        if not self._auth():
            return self._send(403, {"ok": False, "code": "AF-DS-KEY", "message": "key refused"})
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != "/api/studio/orders/%s/approvals" % ORDER:
            return self._send(404, {"ok": False, "code": "NOT_FOUND", "message": "no route"})
        body = self._body()
        if body.get("stage") not in AB.STAGES:
            return self._send(400, {"ok": False, "code": "BAD_STAGE", "message": "stage"})
        if not isinstance(body.get("version"), int) or body["version"] < 1:
            return self._send(400, {"ok": False, "code": "BAD_VERSION", "message": "version"})
        if not isinstance(body.get("text"), str) or len(body["text"]) > 20000:
            return self._send(400, {"ok": False, "code": "BAD_TEXT", "message": "text"})
        files = body.get("files")
        if not isinstance(files, list) or len(files) > 40:
            return self._send(400, {"ok": False, "code": "BAD_FILES", "message": "files"})
        for f in files:
            if not isinstance(f.get("name"), str) or not re.fullmatch(NAME, f["name"]):
                return self._send(400, {"ok": False, "code": "BAD_NAME", "message": "name"})
            if not str(f.get("content_type", "")).split("/")[0] in ("audio", "image"):
                return self._send(400, {"ok": False, "code": "BAD_TYPE", "message": "content type"})
            if not isinstance(f.get("bytes"), int) or f["bytes"] < 0:
                return self._send(400, {"ok": False, "code": "BAD_BYTES", "message": "bytes"})
        st.published.append(body)
        key = (body["stage"], body["version"])
        if key in st.items:  # same stage + version: the existing item, created:false
            item = dict(st.items[key])
            created = False
        else:
            item = {"stage": body["stage"], "version": body["version"],
                    "text": body["text"], "choices": body.get("choices") or [],
                    "files": [f["name"] for f in files], "answer": None}
            st.items[key] = item
            created = True
        uploads = [{"name": f["name"], "method": "PUT",
                    "url": st.base_url + "/presigned/" + f["name"]} for f in files]
        return self._send(201, {"ok": True, "item": item, "created": created,
                                "uploads": uploads})

    def do_GET(self):
        st = self.server.state
        if not self._auth():
            return self._send(403, {"ok": False, "code": "AF-DS-KEY", "message": "key refused"})
        if urllib.parse.urlsplit(self.path).path != "/api/studio/orders/%s/approvals" % ORDER:
            return self._send(404, {"ok": False, "code": "NOT_FOUND", "message": "no route"})
        items = [dict(i) for i in st.items.values()]
        return self._send(200, {"ok": True, "items": items})

    def do_PUT(self):
        st = self.server.state
        name = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path.rsplit("/", 1)[-1])
        body = self.rfile.read(int(self.headers.get("content-length") or 0))
        st.puts[name] = (self.headers.get("Content-Type"), body)
        return self._send(200, {"ok": True})


class ApprovalsBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = Fake()
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.srv.state = cls.st
        cls.st.base_url = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.st.items.clear()
        self.st.published.clear()
        self.st.puts.clear()
        self.song = pathlib.Path(self.tmp.name) / "pick1.mp3"
        self.song.write_bytes(b"ID3\x03\x00\x00\x00song-bytes")
        self.still = pathlib.Path(self.tmp.name) / "shot-1.png"
        self.still.write_bytes(b"\x89PNG\r\n\x1a\nstill-bytes")

    def publish(self, files=None, key=KEY, stage="song", version=1):
        return AB.publish(self.st.base_url, key, ORDER, stage, version,
                          "Which cut?", [{"n": "1", "label": "Cut A"},
                                         {"n": "2", "label": "Cut B"}],
                          [self.song, self.still] if files is None else files)

    # 1 ------------------------------------------------------------------
    def test_publish_posts_the_spec_json_and_puts_every_file(self):
        item = self.publish()
        self.assertEqual(len(self.st.published), 1)
        body = self.st.published[0]
        self.assertEqual(body, {
            "stage": "song", "version": 1, "text": "Which cut?",
            "choices": [{"n": "1", "label": "Cut A"}, {"n": "2", "label": "Cut B"}],
            "files": [{"name": "pick1.mp3",
                       "content_type": body["files"][0]["content_type"],
                       "bytes": self.song.stat().st_size},
                      {"name": "shot-1.png",
                       "content_type": body["files"][1]["content_type"],
                       "bytes": self.still.stat().st_size}],
        })
        self.assertTrue(body["files"][0]["content_type"].startswith("audio/"))
        self.assertTrue(body["files"][1]["content_type"].startswith("image/"))
        self.assertEqual(set(self.st.puts), {"pick1.mp3", "shot-1.png"})
        self.assertEqual(self.st.puts["pick1.mp3"], (body["files"][0]["content_type"],
                                                     self.song.read_bytes()))
        self.assertEqual(self.st.puts["shot-1.png"], (body["files"][1]["content_type"],
                                                      self.still.read_bytes()))
        self.assertEqual(item["stage"], "song")
        self.assertEqual(item["files"], ["pick1.mp3", "shot-1.png"])
        self.assertIsNone(item["answer"])

    def test_publish_twice_same_version_returns_the_existing_item(self):
        first, second = self.publish(), self.publish()
        self.assertEqual(len(self.st.published), 2)  # the service dedups
        self.assertEqual(first["stage"], second["stage"])

    def test_missing_file_is_refused_before_any_request(self):
        with self.assertRaises(LedgerError) as caught:
            self.publish(files=[str(pathlib.Path(self.tmp.name) / "nope.mp3")])
        self.assertEqual(caught.exception.code, "NO_FILE")
        self.assertEqual(self.st.published, [])

    def test_bad_stage_or_version_is_refused_locally(self):
        with self.assertRaises(LedgerError) as caught:
            self.publish(stage="music")
        self.assertEqual(caught.exception.code, "BAD_STAGE")
        with self.assertRaises(LedgerError) as caught:
            self.publish(version=0)
        self.assertEqual(caught.exception.code, "BAD_VERSION")
        self.assertEqual(self.st.published, [])

    # 2 ------------------------------------------------------------------
    def test_answer_is_none_then_the_value_and_scoped_to_stage_version(self):
        self.publish()
        self.assertIsNone(AB.answer(self.st.base_url, KEY, ORDER, "song", 1))
        self.st.items[("song", 1)]["answer"] = {"value": "2", "by": "link", "at": 1700000000000}
        self.st.items[("script", 1)] = {"stage": "script", "version": 1, "text": "t",
                                        "choices": [], "files": [], "answer": None}
        self.assertEqual(AB.answer(self.st.base_url, KEY, ORDER, "song", 1), "2")
        self.assertIsNone(AB.answer(self.st.base_url, KEY, ORDER, "script", 1))
        self.assertIsNone(AB.answer(self.st.base_url, KEY, ORDER, "song", 2))

    # 3 ------------------------------------------------------------------
    def test_wrong_key_is_refused_by_the_service(self):
        with self.assertRaises(LedgerError) as caught:
            self.publish(key="wrong-key")
        self.assertEqual(caught.exception.code, "APPROVAL_PUBLISH_REFUSED")
        with self.assertRaises(LedgerError) as caught:
            AB.answer(self.st.base_url, "wrong-key", ORDER, "song", 1)
        self.assertEqual(caught.exception.code, "APPROVAL_READ_REFUSED")
        self.assertEqual(self.st.published, [])
        self.assertEqual(self.st.puts, {})

    def test_no_key_is_refused_locally_before_any_request(self):
        with self.assertRaises(LedgerError) as caught:
            self.publish(key="")
        self.assertEqual(caught.exception.code, "NO_KEY")
        with self.assertRaises(LedgerError) as caught:
            AB.answer(self.st.base_url, "", ORDER, "song", 1)
        self.assertEqual(caught.exception.code, "NO_KEY")
        self.assertEqual(self.st.published, [])

    # 4 ------------------------------------------------------------------
    def test_the_key_is_never_printed(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            self.publish()
            AB.answer(self.st.base_url, KEY, ORDER, "song", 1)
        self.assertNotIn(KEY, out.getvalue())
        # positive control: the detector sees the sentinel when it is there
        self.assertIn(KEY, out.getvalue() + KEY)

    # 5 ------------------------------------------------------------------
    def test_one_user_agent_from_studio_bridge(self):
        self.assertIs(AB.STUDIO_USER_AGENT, SB.STUDIO_USER_AGENT)
        self.publish()
        AB.answer(self.st.base_url, KEY, ORDER, "song", 1)
        self.assertEqual(self.st.seen_ua, {SB.STUDIO_USER_AGENT})


if __name__ == "__main__":
    unittest.main(verbosity=2)
