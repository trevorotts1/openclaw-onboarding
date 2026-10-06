"""Skill 06 copy of kie_generate.py: result download must be authenticated, like
build_deck.download_image (FIX-4). Mirrors the role-library tests/test_fix4_authenticated_download.py
against a local server that returns 403 unless Bearer + browser User-Agent are present.
Run: python3 -m pytest test_kie_generate_authenticated_download.py -v
"""
import importlib.util
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("kie_generate_twin", HERE / "kie_generate.py")
twin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(twin)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
KEY = "kie-test-key-0001"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class _H(BaseHTTPRequestHandler):
    seen = []

    def do_GET(self):  # noqa: N802
        self.seen.append(dict(self.headers))
        if self.headers.get("Authorization", "") != f"Bearer {KEY}" or self.headers.get("User-Agent", "") != UA:
            self.send_error(403, "unauthenticated")
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(PNG)))
        self.end_headers()
        self.wfile.write(PNG)

    def log_message(self, *a):
        pass


@pytest.fixture()
def cdn():
    srv = HTTPServer(("127.0.0.1", 0), _H)
    _H.seen = []
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}/result.png"
    srv.shutdown()
    t.join(timeout=5)


def test_download_sends_bearer_and_browser_ua(cdn, tmp_path):
    dest = tmp_path / "a.png"
    twin._download(cdn, dest, KEY)
    assert dest.read_bytes()[:4] == b"\x89PNG"
    assert _H.seen[-1]["Authorization"] == f"Bearer {KEY}"
    assert _H.seen[-1]["User-Agent"] == UA


def test_empty_or_wrong_key_is_refused(cdn, tmp_path):
    for k in ("", "wrong"):
        with pytest.raises(RuntimeError, match="403"):
            twin._download(cdn, tmp_path / "b.png", k)


def test_non_http_scheme_refused(tmp_path):
    with pytest.raises(ValueError, match="REFUSED"):
        twin._download("file:///etc/passwd", tmp_path / "c.png", KEY)
    assert not (tmp_path / "c.png").exists()
