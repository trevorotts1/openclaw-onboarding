"""FIX-4 — authenticated image download (Authorization: Bearer + browser User-Agent).

Proves `build_deck.download_image(url, dest, api_key)` against a local HTTP server
that mimics the KIE CDN result-URL contract (tempfile.aiquickdraw.com):

  * An unauthenticated GET (no `Authorization: Bearer <key>`, no browser UA) returns
    HTTP 403 — the exact failure D22 root cause A observed in the live E2E run, where
    plain `urllib.urlretrieve` / a generic-UA GET left renders/ empty.
  * A GET carrying `Authorization: Bearer <key>` AND the browser User-Agent
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)" returns HTTP 200 with the PNG
    bytes — the exact contract the FIX-4 doc specifies.

Assertions (each maps to the FIX-4 QC gate):
  1. status 200 (the gate's "HTTP 200").
  2. file starts with PNG magic bytes + verify_png() accepts it (the gate's "PNG").
  3. download_image returns the on-disk byte size (>0).
  4. the helper sent both required headers — the server REFUSES with 403 if either
     header is missing, so a green test proves auth is what unblocked the download.
  5. the C1 SSRF scheme guard still rejects a non-http(s) URL (no regression).
  6. a missing api_key (empty bearer) is still refused by the server (403) — proof
     the Bearer header is load-bearing, not decorative.

Run:  python3 -m pytest tests/test_fix4_authenticated_download.py -v
(no network needed; live-kie re-verification is the pre-push step per the QC row.)
"""
from __future__ import annotations

import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import build_deck  # noqa: E402

BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
KEY = "kie-test-key-0001"


# Minimal 1x1 transparent PNG (magic bytes + IHDR/IDAT/IEND).
def _png_bytes() -> bytes:
    import struct
    import zlib

    def _chunk(tag: bytes, data: bytes) -> bytes:
        c = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", c)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00\x00\x00")
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


class _KieCDNHandler(BaseHTTPRequestHandler):
    """Mimics the KIE result-CDN auth contract:

    - without `Authorization: Bearer <key>` -> 403
    - without the browser User-Agent        -> 403
    - with both                             -> 200 + PNG bytes
    """

    seen_headers: list[dict] = []

    def do_GET(self):  # noqa: N802
        self.seen_headers.append(dict(self.headers))
        auth = self.headers.get("Authorization", "")
        ua = self.headers.get("User-Agent", "")
        if auth != f"Bearer {KEY}":
            self.send_error(403, "missing/incorrect Authorization header")
            return
        if ua != BROWSER_UA:
            self.send_error(403, "missing/incorrect browser User-Agent")
            return
        data = _png_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # silence request logging
        pass


@pytest.fixture()
def cdn():
    server = HTTPServer(("127.0.0.1", 0), _KieCDNHandler)
    _KieCDNHandler.seen_headers = []
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{server.server_port}/tempfile.aiquickdraw.com/result.png"
    server.shutdown()
    t.join(timeout=5)


def test_download_image_returns_200_and_valid_png(cdn, tmp_path):
    dest = tmp_path / "slide-01.png"
    size = build_deck.download_image(cdn, dest, KEY)
    assert dest.exists()
    assert size == dest.stat().st_size > 0
    # PNG magic bytes.
    assert dest.read_bytes()[:4] == b"\x89PNG"
    # The engine's own PNG verifier accepts it.
    build_deck.verify_png(dest)


def test_download_image_sent_bearer_and_browser_ua(cdn, tmp_path):
    dest = tmp_path / "slide-02.png"
    build_deck.download_image(cdn, dest, KEY)
    assert _KieCDNHandler.seen_headers, "server saw no request"
    auth = _KieCDNHandler.seen_headers[-1].get("Authorization", "")
    ua = _KieCDNHandler.seen_headers[-1].get("User-Agent", "")
    assert auth == f"Bearer {KEY}"
    assert ua == BROWSER_UA


def test_missing_api_key_is_refused_403(cdn, tmp_path):
    """An empty bearer still 403s — proves the Bearer header is load-bearing."""
    dest = tmp_path / "slide-03.png"
    with pytest.raises(Exception) as exc:
        build_deck.download_image(cdn, dest, "")
    assert "403" in str(exc.value) or "HTTP Error 403" in str(exc.value)
    assert not dest.exists() or dest.stat().st_size == 0


def test_bad_api_key_is_refused_403(cdn, tmp_path):
    dest = tmp_path / "slide-04.png"
    with pytest.raises(Exception):
        build_deck.download_image(cdn, dest, "wrong-key")
    assert not dest.exists() or dest.stat().st_size == 0


def test_scheme_guard_still_blocks_non_http(tmp_path):
    """C1 SSRF guard: file:// result URLs are refused before any network."""
    dest = tmp_path / "slide-05.png"
    with pytest.raises(ValueError, match="REFUSED"):
        build_deck.download_image("file:///etc/passwd", dest, KEY)
    assert not dest.exists()


def test_verify_png_rejects_non_png(tmp_path):
    dest = tmp_path / "bad.bin"
    dest.write_bytes(b"GIF89a" + b"\x00" * 64)  # not PNG magic
    with pytest.raises(RuntimeError, match="not a PNG"):
        build_deck.verify_png(dest)


def test_download_image_exists_in_module():
    assert callable(getattr(build_deck, "download_image", None))
