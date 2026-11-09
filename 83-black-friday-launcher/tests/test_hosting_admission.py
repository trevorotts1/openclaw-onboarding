"""F17: the hosted URL is checked as a REAL image, never as "HTTP 200 and some bytes".

The pre-fix behaviour, reproduced below: a Cloudflare/GHL login page at the hosted URL returned
``<!doctype html>…Sign in to continue``, route liveness recorded ``{"live": true, "http": 200,
"bytes": 60}`` with no content type at all, and the launcher ADMITTED it as a live image. The
consumer's ``text/html`` guard could never fire because the route never wrote a content type.

Now the hosting route records what it observed (the real Content-Type header and decoded image
evidence: magic header + dimensions) and admission refuses anything that is not a demonstrably
real image: an HTML page, a type that is not an image, bytes that do not decode, a type that
contradicts the bytes, and a missing type (a null is honestly refused, never assumed to be
``image/png``).

Merged (LND-002): main's port and the branch's binding are ONE implementation now. The route
evidence and ``remote_image_problems`` are the ported form; ``hosted_admission`` is the branch's
stricter binding-aware gate; main's ``_hosted_urls`` — the map path — delegates to it, so this
file keeps BOTH main's asset-map refusal test and the branch's ``write_hosting_binding`` cases.

Free and offline beyond a loopback HTTP server in this process. The GHL REST calls are the
module's own documented mock seam.
"""

from __future__ import annotations

import hashlib
import http.server
import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parent
PUSH_SCRIPT = REPO_ROOT / "45-design-intelligence-library" / "scripts" / "graphics_ghl_push.py"
RULE_FILE = SKILL_ROOT / "launcher_core" / "check_rules" / "image_qc.py"

sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import image_stages  # noqa: E402

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f"
       b"\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00"
       b"\x00\x00IEND\xaeB`\x82")
JPEG_HEADER = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
HTML = b"<!doctype html><html><body>Sign in to continue</body></html>"

_PUSH = {}


def push_module():
    """Skill 45's real hosting route, loaded once (it loads the shared GHL media module at import)."""
    if "module" not in _PUSH:
        spec = importlib.util.spec_from_file_location("f17_graphics_ghl_push", PUSH_SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        _PUSH["module"] = module
    return _PUSH["module"]


class _Handler(http.server.BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):  # noqa: N802
        body, ctype = self.routes.get(self.path, (b"", "text/plain"))
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep the test output clean
        pass


class LoopbackMedia:
    """A loopback stand-in for the GHL media host: an image, a login page, and a lying URL."""

    @classmethod
    def setUpClass(cls):
        cls.routes = {"/image.png": (PNG, "image/png"),
                      "/login": (HTML, "text/html; charset=utf-8"),
                      "/fake.png": (HTML, "image/png")}
        handler = type("H", (_Handler,), {"routes": cls.routes})
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    @classmethod
    def url(cls, path: str) -> str:
        return cls.base + path


class HostingCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        LoopbackMedia.setUpClass()

    @classmethod
    def tearDownClass(cls):
        LoopbackMedia.tearDownClass()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        push_module()

    def tearDown(self):
        self.tmp.cleanup()

    def observe(self, path: str) -> dict:
        """Exactly what the route's liveness step records for a URL."""
        return push_module()._url_live(LoopbackMedia.url(path))

    def page(self, liveness: dict, *, content_type=..., asset_id: str = "IMG-001") -> Path:
        """One page run whose route ledger row carries the given liveness evidence."""
        run = self.root / "dispatch" / "landing"
        image = run / "image-generation-qc" / "Image-01.png"
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(PNG)
        (run / "private").mkdir(parents=True, exist_ok=True)
        (run / "intake.json").write_text(json.dumps({"page_role": "landing", "location_id": "loc-fixture"}))
        row = {"local_path": str(image), "asset_id": asset_id, "file_id": "m1", "ghl_media_id": "m1",
               "ghl_folder_id": "fld_1", "ghl_upload_status": "complete",
               "public_url": LoopbackMedia.url("/image.png"), "liveness": liveness}
        if content_type is ...:  # the route's own record: the Content-Type it observed
            row["content_type"] = liveness.get("content_type")
        elif content_type is not None:
            row["content_type"] = content_type
        (run / "media_library.json").write_text(json.dumps({"ghl_folder_id": "fld_1", "uploaded": [row]}))
        return run

    def decide(self, run: Path, *, bind: bool = True) -> dict:
        if bind:  # the branch's path: the binding is what admission consumes
            image_stages.write_hosting_binding(self.root, run)
        return image_stages.hosted_admission(self.root, run)

    def problems(self, decision: dict) -> list:
        return [p for entry in decision.get("refused") or [] for p in entry.get("problems") or []]


class RouteEvidenceTests(HostingCase):
    """The route records what the transport returned, never a made-up "image/png"."""

    def test_a_real_png_records_its_content_type_and_decoded_dimensions(self):
        live = self.observe("/image.png")
        self.assertEqual(live["content_type"], "image/png")
        self.assertIs(live["image"]["decodes"], True)
        self.assertEqual((live["image"]["format"], live["image"]["width"], live["image"]["height"]),
                         ("png", 1, 1))

    def test_an_html_login_page_is_live_but_records_html_and_no_image(self):
        live = self.observe("/login")
        self.assertIs(live["live"], True)  # a 200 with bytes: the old code stopped here
        self.assertEqual(live["content_type"], "text/html; charset=utf-8")
        self.assertIs(live["image"]["decodes"], False)
        self.assertIsNone(live["image"]["format"])

    def test_a_transport_that_exposes_no_header_records_null_not_an_invented_type(self):
        class _Resp:
            headers = {}

            def getcode(self):
                return 200

            def read(self):
                return PNG

        live = push_module()._url_live("https://host.test/a.png", opener=lambda u, t: _Resp())
        self.assertIsNone(live["content_type"])
        self.assertIs(live["image"]["decodes"], True)  # the bytes are still evidence

    def test_image_evidence_decodes_jpeg_and_webp_dimensions(self):
        push = push_module()
        jpeg = JPEG_HEADER + b"\xff\xc0\x00\x11\x08\x00\x02\x00\x03\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01" + b"\xff\xd9"
        self.assertEqual((jpeg[:3], push.image_evidence(jpeg)["decodes"]), (b"\xff\xd8\xff", True))
        self.assertEqual((push.image_evidence(jpeg)["width"], push.image_evidence(jpeg)["height"]), (3, 2))
        webp = (b"RIFF" + (30).to_bytes(4, "little") + b"WEBP" + b"VP8X" + b"\x00" * 8
                + (2).to_bytes(3, "little") + (3).to_bytes(3, "little") + b"\x00" * 4)
        webp = webp[:24] + (2).to_bytes(3, "little") + (3).to_bytes(3, "little") + webp[30:]
        evidence = push.image_evidence(webp)
        self.assertEqual((evidence["format"], evidence["decodes"], evidence["width"], evidence["height"]),
                         ("webp", True, 3, 4))
        self.assertIs(push.image_evidence(b"GIF89a" + b"\x00" * 20)["decodes"], False)

    def test_the_ledger_row_the_push_writes_carries_the_observed_evidence(self):
        push = push_module()

        def opener(req, timeout):
            class _R:
                def getcode(self):
                    return 200

                def read(self):
                    return json.dumps({"id": "fld_x", "folderId": "fld_x", "fileId": "file_x",
                                       "url": LoopbackMedia.url("/image.png")}).encode()
            return _R()

        with tempfile.TemporaryDirectory() as t:
            job = Path(t)
            (job / "renders").mkdir()
            (job / "renders" / "ad-01.png").write_bytes(PNG)
            (job / "qc").mkdir()
            (job / "qc" / "image_qc_report.json").write_text(json.dumps({"assets": [
                {"local_path": "renders/ad-01.png", "asset_id": "ad-01", "pass": True, "triggered_autofails": []}]}))
            (job / "job.json").write_text(json.dumps({"has_ghl": True}))
            # F19 (merged): the hosting route now refuses bytes that carry no independent
            # current-file review. This case is about the F17 route evidence, so it supplies a
            # valid review record instead of weakening the authority.
            (job / "qc" / "review_records.json").write_text(json.dumps({"records": [{
                "schema": "signature-launch-review-record/v1",
                "reviewer_session": "rev-1", "reviewer_model": "m-review",
                "verdict": "pass", "independent_review": True, "scope": "item",
                "attempt_id": "attempt-1", "revision": "r1",
                "reviewed_artifacts": [{"path": "renders/ad-01.png",
                                        "sha256": hashlib.sha256(PNG).hexdigest()}],
            }]}))
            (job / "qc" / "dispatch_ledger.json").write_text(json.dumps({"sessions": [
                {"session_id": "rev-1", "model": "m-review"}]}))
            store = job / "approval-store"
            store.mkdir()
            (store / "APPR-LIVE.json").write_text(json.dumps({
                "approval_ref": "APPR-LIVE", "allowed_write_target": "approved_live_publication",
                "test_only": False, "location_id": "loc-fixture", "page_ids": []}))
            env = {"GHL_API_KEY": "pit-0f3a9c1e-7b2d-4e65-9a18-c4d2b6e8f0a1", "GHL_LOCATION_ID": "loc-fixture"}
            with mock.patch.dict(os.environ, env):
                push.push_graphics_media(job, opener=opener, approval_ref="APPR-LIVE",
                                         approval_store=str(store))
            push_ledger = json.loads((job / "media_library.json").read_text())
        row = push_ledger["uploaded"][0]
        self.assertEqual(row["content_type"], "image/png")
        self.assertIs(row["liveness"]["image"]["decodes"], True)
        self.assertEqual((row["liveness"]["image"]["width"], row["liveness"]["image"]["height"]), (1, 1))


class AdmissionTests(HostingCase):
    """(a) admit a real image; (b)(c)(d) refuse every non-image by name."""

    def test_a_real_png_with_its_real_content_type_is_admitted(self):
        decision = self.decide(self.page(self.observe("/image.png")))
        self.assertEqual(decision["state"], "pass")
        self.assertEqual(len(decision["admitted"]), 1)
        self.assertEqual(decision["refused"], [])
        self.assertEqual(decision["admitted"][0]["ghl_media_id"], "m1")

    def test_the_html_login_page_is_refused_by_name(self):
        decision = self.decide(self.page(self.observe("/login")))
        self.assertEqual(decision["state"], "refused")
        self.assertEqual(decision["admitted"], [])
        problems = self.problems(decision)
        self.assertIn("the URL returned text/html, which is a page, not a picture", problems)
        self.assertIn("the fetched bytes do not decode as an image (no readable image header/dimensions)",
                      problems)

    def test_an_image_typed_url_whose_bytes_do_not_decode_is_refused(self):
        decision = self.decide(self.page(self.observe("/fake.png")))
        self.assertEqual(decision["state"], "refused")
        problems = self.problems(decision)
        self.assertIn("the fetched bytes do not decode as an image (no readable image header/dimensions)",
                      problems)
        self.assertFalse(any("which is a page" in p for p in problems))  # the type claimed image/png

    def test_a_missing_content_type_is_refused_never_assumed(self):
        live = self.observe("/image.png")
        live = dict(live, content_type=None)
        decision = self.decide(self.page(live, content_type=None))
        self.assertEqual(decision["state"], "refused")
        self.assertIn("records no remote content type, so a login page cannot be told from a picture",
                      self.problems(decision))

    def test_a_type_that_contradicts_the_bytes_is_refused(self):
        decision = self.decide(self.page(self.observe("/image.png"), content_type="image/jpeg"))
        self.assertEqual(decision["state"], "refused")
        self.assertIn("the URL returned image/jpeg but its bytes decode as png", self.problems(decision))

    def test_a_generic_octet_stream_is_admitted_only_with_decoded_image_bytes(self):
        live = self.observe("/image.png")
        self.assertEqual(self.decide(self.page(live, content_type="application/octet-stream"))["state"], "pass")

    def test_json_is_refused_as_not_an_image(self):
        live = dict(self.observe("/image.png"), content_type="application/json")
        decision = self.decide(self.page(live, content_type="application/json"))
        self.assertEqual(decision["state"], "refused")
        self.assertIn("the URL returned application/json, not an image", self.problems(decision))

    def test_a_type_the_check_never_accepted_is_still_refused(self):
        decision = self.decide(self.page(self.observe("/image.png"), content_type="image/gif"))
        self.assertEqual(decision["state"], "refused")
        self.assertIn("the URL returned image/gif, not an image", self.problems(decision))

    def test_a_stale_local_artifact_is_still_refused(self):
        """main's raw-route-ledger path: a file changed after the route recorded its hash is refused."""
        run = self.page(self.observe("/image.png"))
        (run / "image-generation-qc" / "Image-01.png").write_bytes(PNG + b"tampered")
        ledger = json.loads((run / "media_library.json").read_text())
        ledger["uploaded"][0]["sha256"] = hashlib.sha256(PNG).hexdigest()
        (run / "media_library.json").write_text(json.dumps(ledger))
        decision = self.decide(run, bind=False)  # no binding: the route's own row is what is read
        self.assertEqual(decision["state"], "refused")
        self.assertIn("is not the current artifact (the ledger's hash is stale)", self.problems(decision))

    def _https_row(self, run: Path, live: dict) -> None:
        """The same row with a public https URL (what a real upload records), the hash the route
        records for the bytes it sent, and this evidence."""
        image = run / "image-generation-qc" / "Image-01.png"
        ledger = json.loads((run / "media_library.json").read_text())
        ledger["uploaded"][0].update(public_url="https://host.test/image.png", liveness=live,
                                     sha256=hashlib.sha256(image.read_bytes()).hexdigest())
        (run / "media_library.json").write_text(json.dumps(ledger))

    def test_the_asset_map_path_refuses_the_html_page_too(self):
        """main's own map path (_hosted_urls) applies the same F17 evidence, so a page cannot
        be rewritten to a login page's URL. LND-002: that path now DELEGATES to the one
        admission implementation, so the two can never disagree."""
        run = self.page(self.observe("/login"))
        self._https_row(run, self.observe("/login"))
        self.assertEqual(image_stages._hosted_urls(run), {})
        good = self.page(self.observe("/image.png"))
        self._https_row(good, self.observe("/image.png"))
        self.assertEqual(len(image_stages._hosted_urls(good)), 1)

    def test_the_binding_hash_binding_still_refuses_a_changed_artifact(self):
        run = self.page(self.observe("/image.png"))
        self.decide(run)  # writes hosting-binding.json
        (run / "image-generation-qc" / "Image-01.png").write_bytes(PNG + b"tampered")
        decision = image_stages.hosted_admission(self.root, run)
        self.assertEqual(decision["state"], "refused")
        self.assertIn("is not the current artifact (the ledger's hash is stale)", self.problems(decision))

    def test_the_binding_is_still_preferred_over_a_tampered_route_ledger(self):
        run = self.page(self.observe("/image.png"))
        self.assertEqual(self.decide(run)["state"], "pass")
        ledger = json.loads((run / "media_library.json").read_text())
        ledger["uploaded"][0].update(ghl_upload_status="failed", content_type="text/html")
        (run / "media_library.json").write_text(json.dumps(ledger))
        decision = image_stages.hosted_admission(self.root, run)  # reads the binding, not the row
        self.assertEqual(decision["state"], "pass")

    def test_the_binding_keeps_its_required_keys_and_the_local_hash(self):
        run = self.page(self.observe("/image.png"))
        path = image_stages.write_hosting_binding(self.root, run)
        doc = json.loads(Path(path).read_text())
        self.assertEqual(doc["schema"], image_stages.HOSTING_BINDING_SCHEMA)
        self.assertEqual(doc["required_keys"], list(image_stages.BINDING_KEYS))
        row = doc["uploads"][0]
        self.assertEqual(row["sha256"], hashlib.sha256(PNG).hexdigest())
        self.assertEqual(row["hash_source"], "admission")
        self.assertEqual(row["content_type"], "image/png")
        for key in image_stages.BINDING_KEYS:
            self.assertIn(key, row, key)

    def test_the_package_check_rule_names_the_html_refusal(self):
        run = self.page(self.observe("/login"))
        image_stages.write_hosting_binding(self.root, run)
        spec = importlib.util.spec_from_file_location("bwx011_image_qc_rule", RULE_FILE)
        rule = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rule)  # type: ignore[union-attr]
        fails = rule._hosting_binding_violations({"pieces": [{"role": "landing"}]}, self.root)
        self.assertEqual(len(fails), 1, fails)
        self.assertTrue(fails[0].startswith("AF-LAUNCH-HOSTING-BINDING: page landing"), fails[0])
        self.assertIn("text/html, which is a page, not a picture", fails[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
