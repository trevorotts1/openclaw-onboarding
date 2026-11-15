"""U2 approvals bridge against a local fake service; no network calls.

Proves, per SPEC.md §4 / BUILD-PLAN W1-box-bridge-U2:

  1  publish() POSTs exactly the documented JSON (every file with its
     sha256), PUTs every file (bytes and content type as declared), calls the
     finalize route with the publish reply's presentation digest, and returns
     the service's ready item
  2  answer() is None while unanswered, then the value; another stage's
     version is never mistaken for this one
  3  a wrong key is refused by the service (control: the key really travels)
     and an absent key is refused locally, before any request
  4  the key never reaches stdout/stderr, with a positive control proving the
     detector can see the sentinel when it is present
  5  the User-Agent is studio_bridge's own constant, and the server saw it
  6  the box-side publish gate is image/* and audio/* -- the service's own
     allow-list -- while a video, a pdf, a .json/.log/.py or an unknown
     extension is refused LOCALLY: zero requests made, and the refusal names
     the file and its content type

Run: python3 checks/test_approvals_bridge.py
"""
import contextlib
import hashlib
import io
import json
import mimetypes
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
DIGEST = r"^[0-9a-f]{64}$"


def _presentation_digest(body):
    """The service's own digest: stage, version, text, choices and each file
    declaration, in the order the producer wrote them (approvals-api.js)."""
    canonical = json.dumps({
        "stage": body["stage"], "version": body["version"], "text": body["text"],
        "choices": [[c["n"], c["label"]] for c in body.get("choices") or []],
        "files": [[f["name"], f["content_type"], f["bytes"], f["sha256"]]
                  for f in body.get("files") or []],
    }, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Fake:
    """The service contract of SPEC §4 / approvals-api.js, enforced -- a real
    server, not a mock. Only a FINALIZED version is listed."""

    def __init__(self):
        self.key = KEY
        self.items = {}          # (stage, version) -> ready item (listed)
        self.intents = {}        # (stage, version) -> published body (staged)
        self.digests = {}        # (stage, version) -> presentation digest
        self.published = []      # bodies as received
        self.puts = {}           # name -> (content_type, body)
        self.calls = []          # ("publish"|"put"|"finalize"|"list", ...)
        self.finalized = []      # presentation_digest values finalize received
        self.seen_ua = set()
        self.base_url = ""

    def item(self, body, digest, ready):
        return {"stage": body["stage"], "version": body["version"],
                "text": body["text"], "choices": body.get("choices") or [],
                "presentation_digest": digest, "ready": ready,
                "files": [{"name": f["name"],
                           "url": None,
                           "content_type": f["content_type"],
                           "bytes": f["bytes"], "sha256": f["sha256"]}
                          for f in body.get("files") or []],
                "answer": None}


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
        path = urllib.parse.urlsplit(self.path).path
        base = "/api/studio/orders/%s/approvals" % ORDER
        if path.startswith(base + "/") and path.endswith("/finalize"):
            return self._finalize(path[len(base):])
        if path != base:
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
            if not isinstance(f.get("sha256"), str) or not re.fullmatch(DIGEST, f["sha256"]):
                return self._send(400, {"ok": False, "code": "BAD_DIGEST",
                                        "message": "every file needs its sha256"})
        st.published.append(body)
        st.calls.append(("publish", body["stage"], body["version"]))
        key = (body["stage"], body["version"])
        digest = _presentation_digest(body)
        if key in st.items:        # already ready: nothing to upload
            return self._send(200, {"ok": True, "item": st.items[key],
                                    "created": False, "ready": True, "uploads": []})
        if key in st.intents and st.digests[key] != digest:
            return self._send(409, {"ok": False, "code": "AF-APPROVAL-REVISION",
                                    "message": "that version is published with different content"})
        st.intents[key] = body
        st.digests[key] = digest
        uploads = [{"name": f["name"], "method": "PUT",
                    "url": st.base_url + "/presigned/" + f["name"]} for f in files]
        return self._send(201, {"ok": True, "item": st.item(body, digest, False),
                                "created": True, "ready": not files, "uploads": uploads})

    def _finalize(self, rest):
        st = self.server.state
        parts = [p for p in rest.split("/") if p]
        if len(parts) != 3:
            return self._send(404, {"ok": False, "code": "NOT_FOUND", "message": "no route"})
        stage, version, _ = parts
        try:
            version = int(version)
        except ValueError:
            return self._send(400, {"ok": False, "code": "BAD_VERSION", "message": "version"})
        key = (stage, version)
        body = self._body()
        st.calls.append(("finalize", stage, version))
        if key in st.items:
            return self._send(200, {"ok": True, "item": st.items[key],
                                    "ready": True, "created": False})
        if key not in st.intents:
            return self._send(404, {"ok": False, "code": "AF-APPROVAL-UNKNOWN",
                                    "message": "no such approval to finalize"})
        if body.get("presentation_digest") is not None:
            st.finalized.append(body["presentation_digest"])
            if body["presentation_digest"] != st.digests[key]:
                return self._send(409, {"ok": False, "code": "AF-APPROVAL-REVISION",
                                        "message": "that finalize names a different presentation"})
        intent = st.intents[key]
        for f in intent.get("files") or []:
            put = st.puts.get(f["name"])
            if not put:
                return self._send(409, {"ok": False, "code": "AF-APPROVAL-UPLOAD",
                                        "message": "%s has not finished uploading" % f["name"]})
            if hashlib.sha256(put[1]).hexdigest() != f["sha256"]:
                return self._send(409, {"ok": False, "code": "AF-APPROVAL-BYTES",
                                        "message": "%s does not match its digest" % f["name"]})
        ready = st.item(intent, st.digests[key], True)
        st.items[key] = ready
        return self._send(201, {"ok": True, "item": ready, "ready": True, "created": True})

    def do_GET(self):
        st = self.server.state
        if not self._auth():
            return self._send(403, {"ok": False, "code": "AF-DS-KEY", "message": "key refused"})
        if urllib.parse.urlsplit(self.path).path != "/api/studio/orders/%s/approvals" % ORDER:
            return self._send(404, {"ok": False, "code": "NOT_FOUND", "message": "no route"})
        st.calls.append(("list",))
        items = [dict(i) for i in st.items.values()]   # FINALIZED only
        return self._send(200, {"ok": True, "items": items})

    def do_PUT(self):
        st = self.server.state
        name = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path.rsplit("/", 1)[-1])
        body = self.rfile.read(int(self.headers.get("content-length") or 0))
        st.puts[name] = (self.headers.get("Content-Type"), body)
        st.calls.append(("put", name))
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
        self.st.intents.clear()
        self.st.digests.clear()
        self.st.published.clear()
        self.st.puts.clear()
        self.st.calls.clear()
        self.st.finalized.clear()
        self.song = pathlib.Path(self.tmp.name) / "pick1.mp3"
        self.song.write_bytes(b"ID3\x03\x00\x00\x00song-bytes")
        self.still = pathlib.Path(self.tmp.name) / "shot-1.png"
        self.still.write_bytes(b"\x89PNG\r\n\x1a\nstill-bytes")

    def publish(self, files=None, key=KEY, stage="song", version=1):
        return AB.publish(self.st.base_url, key, ORDER, stage, version,
                          "Which cut?", [{"n": 1, "label": "Cut A"},
                                         {"n": 2, "label": "Cut B"}],
                          [self.song, self.still] if files is None else files)

    # 1 ------------------------------------------------------------------
    def test_publish_posts_the_spec_json_and_puts_every_file(self):
        item = self.publish()
        self.assertEqual(len(self.st.published), 1)
        body = self.st.published[0]
        self.assertEqual(body, {
            "stage": "song", "version": 1, "text": "Which cut?",
            "choices": [{"n": 1, "label": "Cut A"}, {"n": 2, "label": "Cut B"}],
            "files": [{"name": "pick1.mp3",
                       "content_type": body["files"][0]["content_type"],
                       "bytes": self.song.stat().st_size,
                       "sha256": hashlib.sha256(self.song.read_bytes()).hexdigest()},
                      {"name": "shot-1.png",
                       "content_type": body["files"][1]["content_type"],
                       "bytes": self.still.stat().st_size,
                       "sha256": hashlib.sha256(self.still.read_bytes()).hexdigest()}],
        })
        self.assertTrue(body["files"][0]["content_type"].startswith("audio/"))
        self.assertTrue(body["files"][1]["content_type"].startswith("image/"))
        self.assertEqual(set(self.st.puts), {"pick1.mp3", "shot-1.png"})
        self.assertEqual(self.st.puts["pick1.mp3"], (body["files"][0]["content_type"],
                                                     self.song.read_bytes()))
        self.assertEqual(self.st.puts["shot-1.png"], (body["files"][1]["content_type"],
                                                      self.still.read_bytes()))
        # upload, then finalize, with the digest the publish reply carried
        kinds = [c[0] for c in self.st.calls]
        self.assertLess(kinds.index("publish"), kinds.index("put"))
        self.assertLess(max(i for i, k in enumerate(kinds) if k == "put"),
                        kinds.index("finalize"))
        self.assertEqual(self.st.finalized, [self.st.digests[("song", 1)]])
        self.assertTrue(item["ready"])
        self.assertEqual([f["name"] for f in item["files"]], ["pick1.mp3", "shot-1.png"])
        self.assertEqual(item["stage"], "song")
        self.assertIsNone(item["answer"])
        # and the version is now listed for the client
        self.assertEqual(list(self.st.items), [("song", 1)])

    def test_publish_twice_same_version_returns_the_existing_item(self):
        first, second = self.publish(), self.publish()
        self.assertEqual(len(self.st.published), 2)  # the service dedups
        self.assertEqual(first["stage"], second["stage"])
        self.assertTrue(first["ready"] and second["ready"])
        # the second publish was told the version is ready: nothing re-uploaded
        self.assertEqual([c[0] for c in self.st.calls].count("finalize"), 1)

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

    def test_a_finalize_refusal_is_named(self):
        # the service refuses a finalize whose digest names other content
        real_http = AB._http
        calls = []

        def fake_http(method, url, *, key=None, body=None, timeout=20):
            calls.append((method, url, body))
            if url.endswith("/finalize"):
                return 409, {"ok": False, "code": "AF-APPROVAL-REVISION",
                             "message": "that finalize names a different presentation"}
            return 201, {"ok": True, "ready": False,
                         "item": {"presentation_digest": "0" * 64},
                         "uploads": [{"name": "pick1.mp3",
                                      "url": self.st.base_url + "/presigned/pick1.mp3"},
                                     {"name": "shot-1.png",
                                      "url": self.st.base_url + "/presigned/shot-1.png"}]}

        AB._http = fake_http
        self.addCleanup(setattr, AB, "_http", real_http)
        with self.assertRaises(LedgerError) as caught:
            self.publish()
        self.assertEqual(caught.exception.code, "APPROVAL_FINALIZE_REFUSED")
        self.assertTrue(calls[-1][1].endswith("/approvals/song/1/finalize"))

    def test_a_finalize_transport_error_is_unknown_not_failed(self):
        real_http = AB._http

        def fake_http(method, url, *, key=None, body=None, timeout=20):
            if url.endswith("/finalize"):
                return 0, {"code": "TRANSPORT_UNKNOWN", "message": "timed out"}
            return 201, {"ok": True, "ready": False, "item": {},
                         "uploads": [{"name": "pick1.mp3",
                                      "url": self.st.base_url + "/presigned/pick1.mp3"},
                                     {"name": "shot-1.png",
                                      "url": self.st.base_url + "/presigned/shot-1.png"}]}

        AB._http = fake_http
        self.addCleanup(setattr, AB, "_http", real_http)
        with self.assertRaises(LedgerError) as caught:
            self.publish()
        self.assertEqual(caught.exception.code, "TRANSPORT_UNKNOWN")

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

    # 6 ------------------------------------------------------------------
    def test_image_and_audio_pass_the_local_gate(self):
        for name, data in {"pick1.mp3": b"ID3\x03\x00\x00\x00song-bytes",
                           "shot-1.png": b"\x89PNG\r\n\x1a\nstill-bytes",
                           "take.wav": b"RIFF\x00\x00\x00\x00WAVEwave-bytes"}.items():
            f = pathlib.Path(self.tmp.name) / name
            f.write_bytes(data)
            spec = AB._file_spec(f)
            self.assertEqual(spec["name"], name)
            self.assertEqual(spec["content_type"], mimetypes.guess_type(name)[0])
            self.assertEqual(spec["bytes"], len(data))
            self.assertEqual(spec["sha256"], hashlib.sha256(data).hexdigest())
        # png and mp3 also survive the WHOLE publish, file and all
        item = self.publish()
        self.assertEqual([f["name"] for f in item["files"]], ["pick1.mp3", "shot-1.png"])
        self.assertEqual(set(self.st.puts), {"pick1.mp3", "shot-1.png"})

    def test_video_and_pdf_are_refused_locally_with_zero_requests(self):
        # the service accepts audio/image only; the video is now refused HERE
        # instead of after a request and a key use.
        for name, data in {"clip.mp4": b"\x00\x00\x00\x18ftypmp42vid-bytes",
                           "score.pdf": b"%PDF-1.4\npdf-bytes"}.items():
            f = pathlib.Path(self.tmp.name) / name
            f.write_bytes(data)
            with self.assertRaises(LedgerError) as caught:
                self.publish(files=[f])
            self.assertEqual(caught.exception.code, "BAD_FILE_TYPE", name)
            self.assertIn(name, str(caught.exception))
        self.assertEqual(self.st.published, [])      # zero requests made
        self.assertEqual(self.st.puts, {})
        self.assertEqual(self.st.calls, [])

    def test_non_media_files_are_refused_locally_with_zero_requests(self):
        for name, data in {"config.json": b"{}", "run.log": b"one\n",
                           "tool.py": b"print(1)\n", "mystery.zzz": b"\x00"}.items():
            f = pathlib.Path(self.tmp.name) / name
            f.write_bytes(data)
            with self.assertRaises(LedgerError) as caught:
                self.publish(files=[f])
            err = caught.exception
            # a typed file hits the allow-list; an unknown extension has no
            # type to check and stops one step earlier -- both are LOCAL
            self.assertIn(err.code, ("BAD_FILE_TYPE", "UNSUPPORTED_FILE"), name)
            self.assertIn(name, str(err))            # the refusal names the file
            if err.code == "BAD_FILE_TYPE":
                self.assertIn(mimetypes.guess_type(name)[0], str(err))
        self.assertEqual(self.st.published, [])      # zero requests made
        self.assertEqual(self.st.puts, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
