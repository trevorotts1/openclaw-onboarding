#!/usr/bin/env python3
"""test_cover_render_kie74.py -- cover_render.py runs every KIE call through Skill 74 (one KIE path).

A local mock stands in for KIE and for the result CDN, and the REAL Skill 74 CLI (the sibling
74-kie-live-adapter) talks to it through its localhost-only hooks. The CDN answers the default urllib
User-Agent with 403 exactly like the real one (W0.6), so a green run proves Skill 74's `save` carries the
browser User-Agent this adapter passes. No network, no real key, no credits.

Run: python3 -m pytest 59-anthology-engine/tests/test_cover_render_kie74.py -q
"""
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
REPO = SKILL_DIR.parent
ADAPTER = REPO / "74-kie-live-adapter" / "scripts" / "kie_live_adapter.py"


def _load():
    spec = importlib.util.spec_from_file_location("cover_render_under_test", SKILL_DIR / "scripts" / "cover_render.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _png(w, h):
    return (b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR" + w.to_bytes(4, "big")
            + h.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00" + b"X" * 64)


class Mock:
    def __init__(self, png, mode="success"):
        self.png, self.mode = png, mode
        self.creates, self.agents = [], []
        mock = self

        class H(BaseHTTPRequestHandler):
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
                n = int(self.headers.get("Content-Length", 0) or 0)
                body = json.loads(self.rfile.read(n).decode() or "{}")
                if self.path.split("?")[0] == "/api/v1/jobs/createTask":
                    mock.creates.append(body)
                    if mock.mode == "credits":
                        return self._send(200, {"code": 402, "msg": "insufficient credits"})
                    return self._send(200, {"code": 200, "data": {"taskId": "cv-1"}})
                return self._send(404, {"code": 404})

            def do_GET(self):
                p = self.path.split("?")[0]
                host = self.headers["Host"]
                if p.startswith("/api/v1/models/") and p.endswith("/schema"):
                    return self._send(200, {"code": 200, "data": {"openapi": {"paths": {"/api/v1/jobs/createTask": {"post": {
                        "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {
                            "model": {"type": "string"}, "input": {"type": "object"}}}}}}}}}}}})
                if p == "/api/v1/jobs/recordInfo":
                    url = "http://%s/cdn/cover.png" % (host if mock.mode != "offlist" else "evil.invalid")
                    return self._send(200, {"code": 200, "data": {"state": "success", "resultJson": json.dumps(
                        {"resultUrls": [url]})}})
                if p == "/cdn/cover.png":
                    ua = self.headers.get("User-Agent", "")
                    mock.agents.append(ua)
                    if ua.startswith("Python-urllib"):  # the real result CDN 403s urllib's default agent
                        self.send_response(403)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(mock.png)))
                    self.end_headers()
                    self.wfile.write(mock.png)
                    return
                return self._send(404, {"code": 404})

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.base = "http://127.0.0.1:%d" % self.srv.server_port
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()


@pytest.fixture
def env(monkeypatch, tmp_path):
    if not ADAPTER.is_file():
        pytest.skip("Skill 74 is not a sibling of this checkout")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AE_COVER_TEST_KEY", "cover-test-key-0123456789")
    monkeypatch.setenv("KIE_LIVE_MIN_SPACING", "0")
    mod = _load()
    monkeypatch.setattr(mod, "KIE_RESULT_HOSTS", ("127.0.0.1",))  # the mock stands in for the Kie CDN

    class E:
        pass
    e = E()
    e.mod, e.tmp, e.mocks = mod, tmp_path, []

    def start(png, mode="success"):
        m = Mock(png, mode)
        e.mocks.append(m)
        return m
    e.start = start
    yield e
    for m in e.mocks:
        m.close()


def _render(e, mock, name="cover.png"):
    return e.mod.render("a portrait cover", e.tmp / name, base_url=mock.base, key_labels=("AE_COVER_TEST_KEY",),
                        poll_interval_s=0.1, poll_ceiling_s=30)


def test_real_skill_74_renders_a_portrait_cover_with_the_browser_user_agent(env):
    mock = env.start(_png(1024, 1536))
    code, man = _render(env, mock)
    assert code == env.mod.EX_OK, man
    assert man["status"] == "rendered" and man["task_id"] == "cv-1"
    assert man["dimensions"] == {"width": 1024, "height": 1536, "portrait": True}
    assert (env.tmp / "cover.png").read_bytes() == mock.png
    assert mock.agents == [env.mod.MOZILLA_UA]  # Skill 74 sent the adapter's browser agent, not urllib's
    body = mock.creates[0]
    assert body["model"] == env.mod.COVER_MODEL and body["input"]["aspect_ratio"] == "2:3"


def test_landscape_result_holds_and_lands_nothing(env):
    mock = env.start(_png(1536, 1024))
    code, man = _render(env, mock)
    assert code == env.mod.EX_HELD and man["held_reason"] == env.mod.HELD_RENDER_NOT_PORTRAIT
    assert not (env.tmp / "cover.png").exists()


def test_result_host_outside_the_allowlist_is_never_fetched(env):
    mock = env.start(_png(1024, 1536), mode="offlist")
    code, man = _render(env, mock)
    assert code == env.mod.EX_HELD and man["held_reason"] == env.mod.HELD_DOWNLOAD_FAILED
    assert mock.agents == []


def test_insufficient_credits_hold_through_the_real_transport(env):
    mock = env.start(_png(1024, 1536), mode="credits")
    code, man = _render(env, mock)
    assert code == env.mod.EX_HELD and man["held_reason"] == env.mod.HELD_CREDIT_OUT
    assert len(mock.creates) == 1


def test_missing_skill_74_holds_with_a_clear_reason_and_no_http(env, monkeypatch):
    mock = env.start(_png(1024, 1536))
    monkeypatch.setattr(env.mod, "_find_kie_adapter", lambda: None)
    code, man = _render(env, mock)
    assert code == env.mod.EX_HELD and man["held_reason"] == env.mod.HELD_TRANSPORT_MISSING
    assert mock.creates == [] and mock.agents == []


def test_module_has_no_kie_http_client_of_its_own():
    source = (SKILL_DIR / "scripts" / "cover_render.py").read_text(encoding="utf-8")
    for forbidden in ("urllib.request", "api.kie.ai", "/api/v1/jobs/createTask", "/api/v1/jobs/recordInfo",
                      "urlopen", "Content-Type"):
        assert forbidden not in source, forbidden
    mod = _load()
    for gone in ("_request", "_Resp", "_kie_headers", "_poll_record_info", "_extract_result_urls",
                 "CREATE_TASK_PATH", "RECORD_INFO_PATH", "DEFAULT_KIE_BASE_URL"):
        assert not hasattr(mod, gone), gone


def test_self_test_still_passes():
    assert _load().self_test() == 0
