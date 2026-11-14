"""S75-037: a file-carrying approval is publishable only through the
service's own three rules, enforced here by a local stub:

  1  every file carries its lowercase SHA-256, and the stored copy must match
     it (the service sizes the file and reads the digest)
  2  a publish that carries files replies `ready: false` plus one presigned
     PUT per file; the bytes go up after the publish, never inside it
  3  the version is listed for the client ONLY after the finalize route has
     verified every staged file, and the finalize names the presentation
     digest the publish reply carried

The case this fixes (S75-037): a storyboard or song approval carrying image
or audio files used to publish and upload, and then never became answerable,
because nothing called finalize.

Run: python3 checks/test_s75_037_publish_finalize.py
"""
import hashlib
import json
import pathlib
import re
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import approvals_bridge as AB  # noqa: E402
from studio_claim import LedgerError  # noqa: E402

KEY = "k-" + "feedface" * 4
ORDER = "o_fedcba9876543210fedcba98"
NAME = r"^[A-Za-z0-9._-]{1,80}$"
DIGEST = r"^[0-9a-f]{64}$"
MAX_APPROVAL_FILES = 40          # approvals-api.js
MAX_APPROVAL_FILE_BYTES = 25 * 1024 * 1024


def _presentation_digest(body):
    canonical = json.dumps({
        "stage": body["stage"], "version": body["version"], "text": body["text"],
        "choices": [[c["n"], c["label"]] for c in body.get("choices") or []],
        "files": [[f["name"], f["content_type"], f["bytes"], f["sha256"]]
                  for f in body.get("files") or []],
    }, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Stub:
    """The service's publish / upload / finalize / list rules, in one place."""

    def __init__(self):
        self.items = {}        # (stage, version) -> ready item
        self.intents = {}      # (stage, version) -> published body
        self.digests = {}      # (stage, version) -> presentation digest
        self.staged = {}       # name -> bytes as PUT
        self.calls = []        # what the producer did, in order
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

    def _key(self):
        return self.headers.get("x-ds-key") or ""

    def _refuse(self):
        return self._send(403, {"ok": False, "code": "AF-DS-KEY", "message": "key refused"})

    def do_POST(self):
        st = self.server.state
        if self._key() != KEY:
            return self._refuse()
        path = urllib.parse.urlsplit(self.path).path
        base = "/api/studio/orders/%s/approvals" % ORDER
        if path.startswith(base + "/") and path.endswith("/finalize"):
            return self._finalize(path[len(base):])
        if path != base:
            return self._send(404, {"ok": False, "code": "NOT_FOUND", "message": "no route"})
        body = self._body()
        st.calls.append(("publish", body.get("stage"), body.get("version")))
        if body.get("stage") not in AB.STAGES or not isinstance(body.get("version"), int):
            return self._send(400, {"ok": False, "code": "AF-APPROVAL-BAD",
                                    "message": "stage and version are required"})
        files = body.get("files") or []
        if not isinstance(files, list) or len(files) > MAX_APPROVAL_FILES:
            return self._send(400, {"ok": False, "code": "AF-APPROVAL-BAD",
                                    "message": "at most %d files" % MAX_APPROVAL_FILES})
        for f in files:
            if not isinstance(f.get("name"), str) or not re.fullmatch(NAME, f["name"]):
                return self._send(400, {"ok": False, "code": "AF-APPROVAL-BAD",
                                        "message": "bad file name"})
            if not re.match(r"^(audio|image)/", str(f.get("content_type") or "")):
                return self._send(400, {"ok": False, "code": "AF-APPROVAL-BAD",
                                        "message": "approval files must be audio or image"})
            if not isinstance(f.get("bytes"), int) or not (0 < f["bytes"] <= MAX_APPROVAL_FILE_BYTES):
                return self._send(400, {"ok": False, "code": "AF-APPROVAL-BAD",
                                        "message": "bad file length"})
            # RULE 1: the digest is required, and must be a lowercase SHA-256
            if not isinstance(f.get("sha256"), str) or not re.fullmatch(DIGEST, f["sha256"]):
                return self._send(400, {"ok": False, "code": "AF-APPROVAL-BAD",
                                        "message": "every file needs its lowercase SHA-256 digest"})
        key = (body["stage"], body["version"])
        digest = _presentation_digest(body)
        st.intents[key] = body
        st.digests[key] = digest
        # RULE 2: files are staged after the publish, never inside it
        uploads = [{"name": f["name"], "method": "PUT",
                    "url": st.base_url + "/presigned/" + f["name"]} for f in files]
        return self._send(201, {"ok": True,
                                "item": {"stage": body["stage"], "version": body["version"],
                                         "text": body["text"],
                                         "presentation_digest": digest},
                                "ready": not files, "uploads": uploads})

    def _finalize(self, rest):
        st = self.server.state
        parts = [p for p in rest.split("/") if p]
        if len(parts) != 3:
            return self._send(404, {"ok": False, "code": "NOT_FOUND", "message": "no route"})
        stage, version, _ = parts
        try:
            version = int(version)
        except ValueError:
            return self._send(400, {"ok": False, "code": "AF-APPROVAL-BAD",
                                    "message": "bad version"})
        body = self._body()
        st.calls.append(("finalize", stage, version))
        key = (stage, version)
        if key in st.items:
            return self._send(200, {"ok": True, "item": st.items[key], "ready": True})
        if key not in st.intents:
            return self._send(404, {"ok": False, "code": "AF-APPROVAL-UNKNOWN",
                                    "message": "no such approval to finalize"})
        if body.get("presentation_digest") != st.digests[key]:
            return self._send(409, {"ok": False, "code": "AF-APPROVAL-REVISION",
                                    "message": "that finalize names a different presentation"})
        for f in st.intents[key].get("files") or []:
            got = st.staged.get(f["name"])
            if got is None:
                return self._send(409, {"ok": False, "code": "AF-APPROVAL-UPLOAD",
                                        "message": "%s has not finished uploading" % f["name"]})
            # RULE 1 again: the stored copy must match the declared digest
            if hashlib.sha256(got).hexdigest() != f["sha256"]:
                return self._send(409, {"ok": False, "code": "AF-APPROVAL-BYTES",
                                        "message": "%s does not match its digest" % f["name"]})
        intent = st.intents[key]
        ready = {"stage": stage, "version": version, "text": intent["text"],
                 "choices": intent.get("choices") or [],
                 "presentation_digest": st.digests[key], "ready": True,
                 "files": [{"name": f["name"], "content_type": f["content_type"],
                            "bytes": f["bytes"], "sha256": f["sha256"]}
                           for f in intent.get("files") or []],
                 "answer": None}
        st.items[key] = ready
        return self._send(201, {"ok": True, "item": ready, "ready": True})

    def do_GET(self):
        st = self.server.state
        if self._key() != KEY:
            return self._refuse()
        if urllib.parse.urlsplit(self.path).path != "/api/studio/orders/%s/approvals" % ORDER:
            return self._send(404, {"ok": False, "code": "NOT_FOUND", "message": "no route"})
        st.calls.append(("list",))
        # RULE 3: only finalized versions are listed and answerable
        return self._send(200, {"ok": True, "items": list(st.items.values())})

    def do_PUT(self):
        st = self.server.state
        name = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path.rsplit("/", 1)[-1])
        data = self.rfile.read(int(self.headers.get("content-length") or 0))
        st.staged[name] = data
        st.calls.append(("put", name))
        return self._send(200, {"ok": True})


class PublishFinalizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = Stub()
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
        self.st.staged.clear()
        self.st.calls.clear()
        self.still = pathlib.Path(self.tmp.name) / "shot-1.png"
        self.still.write_bytes(b"\x89PNG\r\n\x1a\n" + b"still-bytes" * 8)

    def publish(self, files):
        return AB.publish(self.st.base_url, KEY, ORDER, "storyboard", 1,
                          "Storyboard: approve these shots?",
                          [{"n": 1, "label": "GO"}], files)

    def _raw(self, method, path, body=None):
        req = urllib.request.Request(
            self.st.base_url + path, method=method,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers={"content-type": "application/json", "x-ds-key": KEY})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    # 1 ------------------------------------------------------------------
    def test_one_image_file_is_ready_after_upload_and_finalize(self):
        item = self.publish([self.still])
        kinds = [c[0] for c in self.st.calls]
        self.assertEqual(kinds, ["publish", "put", "finalize"])
        self.assertTrue(item["ready"])
        self.assertEqual([f["name"] for f in item["files"]], ["shot-1.png"])
        self.assertEqual(self.st.staged["shot-1.png"], self.still.read_bytes())
        self.assertEqual(self.st.digests[("storyboard", 1)], item["presentation_digest"])
        # and the client's list shows it, now that it is finalized
        status, listing = self._raw("GET", "/api/studio/orders/%s/approvals" % ORDER)
        self.assertEqual(status, 200)
        self.assertEqual([(i["stage"], i["version"]) for i in listing["items"]],
                         [("storyboard", 1)])

    def test_the_published_sha256_is_the_whole_file(self):
        big = pathlib.Path(self.tmp.name) / "sheet.png"
        data = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 9000   # > 2 MB, several blocks
        big.write_bytes(data)
        item = self.publish([big])
        self.assertGreater(len(data), 2 * 1024 * 1024)
        body = self.st.intents[("storyboard", 1)]
        self.assertEqual(body["files"][0]["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(body["files"][0]["bytes"], len(data))
        self.assertTrue(item["ready"])

    # 2 ------------------------------------------------------------------
    def test_no_finalize_means_the_item_is_never_listed(self):
        # Rule 3 proved directly: publish + upload with NO finalize leaves the
        # version unlisted, and the finalize is what lists it. If publish()
        # ever stops calling finalize, this fails.
        body = {"stage": "storyboard", "version": 1, "text": "Approve?",
                "choices": [{"n": 1, "label": "GO"}],
                "files": [{"name": "shot-1.png", "content_type": "image/png",
                           "bytes": self.still.stat().st_size,
                           "sha256": hashlib.sha256(self.still.read_bytes()).hexdigest()}]}
        status, reply = self._raw("POST", "/api/studio/orders/%s/approvals" % ORDER, body)
        self.assertEqual(status, 201)
        self.assertFalse(reply["ready"])
        self.assertEqual([u["name"] for u in reply["uploads"]], ["shot-1.png"])
        req = urllib.request.Request(
            self.st.base_url + "/presigned/shot-1.png", method="PUT",
            data=self.still.read_bytes(),
            headers={"Content-Type": "image/png",
                     "Content-Length": str(self.still.stat().st_size)})
        with urllib.request.urlopen(req, timeout=10):
            pass
        status, listing = self._raw("GET", "/api/studio/orders/%s/approvals" % ORDER)
        self.assertEqual(status, 200)
        self.assertEqual(listing["items"], [])       # uploaded, still not listed
        status, _ = self._raw(
            "POST", "/api/studio/orders/%s/approvals/storyboard/1/finalize" % ORDER,
            {"presentation_digest": reply["item"]["presentation_digest"]})
        self.assertEqual(status, 201)
        status, listing = self._raw("GET", "/api/studio/orders/%s/approvals" % ORDER)
        self.assertEqual([(i["stage"], i["version"]) for i in listing["items"]],
                         [("storyboard", 1)])
        # the shipped path calls finalize, which is what makes the test above
        # the "missing finalize" case the acceptance names
        self.st.calls.clear()
        self.st.items.clear()
        self.st.intents.clear()
        self.st.digests.clear()
        self.st.staged.clear()
        self.publish([self.still])
        self.assertIn("finalize", [c[0] for c in self.st.calls])

    def test_the_stub_refuses_a_file_with_no_sha256(self):
        # control for the instrument: rule 1 really is enforced here
        body = {"stage": "storyboard", "version": 2, "text": "Approve?",
                "files": [{"name": "shot-1.png", "content_type": "image/png",
                           "bytes": self.still.stat().st_size}]}
        status, reply = self._raw("POST", "/api/studio/orders/%s/approvals" % ORDER, body)
        self.assertEqual(status, 400)
        self.assertIn("SHA-256", reply["message"])

    # 3 ------------------------------------------------------------------
    def test_video_is_refused_locally_with_no_request_made(self):
        clip = pathlib.Path(self.tmp.name) / "clip.mp4"
        clip.write_bytes(b"\x00\x00\x00\x18ftypmp42vid-bytes")
        with self.assertRaises(LedgerError) as caught:
            self.publish([clip])
        self.assertEqual(caught.exception.code, "BAD_FILE_TYPE")
        self.assertIn("clip.mp4", str(caught.exception))
        self.assertEqual(self.st.calls, [])
        self.assertEqual(self.st.intents, {})
        self.assertEqual(self.st.items, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
