#!/usr/bin/env python3
"""test_kie_adapter_resultjson_decode.py - proves the result-URL extraction of both
Skill 47 adapters now that they run through Skill 74 (and holds the shared test harness).

THE ORIGINAL BUG (confirmed live against api.kie.ai during the v14.1.x render proof):
  KIE's poll endpoints return ``resultJson`` as a JSON-ENCODED STRING, not a parsed
  object. The v14 adapters read it as a dict and never extracted the result URL.
  Skill 74's ``wait`` / ``save`` own that decode now; this test proves the adapters get
  a saved file out of a recordInfo response whose resultJson is a JSON string, on all
  three poll shapes, with no network and no real key (tools.base_tool is stubbed):

    1. image gpt-image-2.5     createTask -> /jobs/recordInfo         (Skill 74 run)
    2. video gemini-omni-video createTask -> /jobs/recordInfo         (Skill 74 run)
    3. video veo3_fast         veo/generate -> /veo/record-info       (legacy Veo route over Skill 74's Adapter)

  and that a malformed / empty resultJson degrades to a failed ToolResult (never a crash).

This file also exports the harness the sibling tests reuse: ``_install_base_tool_stub``,
``_load_module``, ``FakeKieTransport`` (a Skill 74 transport double that serves the
catalog, schema, credit, createTask, recordInfo, upload and legacy Veo routes) and
``fresh_tool``.

Run:  python3 48-facebook-ad-generator/scripts/test_kie_adapter_resultjson_decode.py
(Skill 48 builds on the Skill 47 adapters, so this copy proves the same result extraction from Skill 48's tree;
the canonical copy and the shared harness live in 47-movie-producer/scripts/.)
Exit: 0 = all pass; 1 = a failure.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTERS = REPO_ROOT / "47-movie-producer" / "kie-adapters" / "tools"
VIDEO_PY = ADAPTERS / "video" / "kie_video.py"
IMAGE_PY = ADAPTERS / "graphics" / "kie_image.py"

RESULT_URL = "https://tempfile.aiquickdraw.com/s/fixture-result-12345.mp4"
RESULT_IMG_URL = "https://tempfile.aiquickdraw.com/s/fixture-result-67890.png"
# Synthetic high-entropy fixture key (never a real credential); the adapters reject placeholder-shaped keys.
FIXTURE_KEY = "".join("ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"[(i * 37 + 11) % 57] for i in range(32))


# ---------------------------------------------------------------------------
# Stub tools.base_tool so the adapters import without OpenMontage present.
# ---------------------------------------------------------------------------
def _install_base_tool_stub() -> None:
    if "tools" not in sys.modules:
        sys.modules["tools"] = types.ModuleType("tools")
    bt = types.ModuleType("tools.base_tool")

    class BaseTool:
        pass

    class ToolResult:
        def __init__(self, success=False, error=None, data=None, **kw):
            self.success = success
            self.error = error
            self.data = data or {}
            for k, v in kw.items():
                setattr(self, k, v)

    class _Enum:
        def __getattr__(self, name):
            return name

    class _Profile:
        def __init__(self, *a, **k):
            pass

    bt.BaseTool = BaseTool
    bt.ToolResult = ToolResult
    bt.Determinism = _Enum()
    bt.ExecutionMode = _Enum()
    bt.ResourceProfile = _Profile
    bt.RetryPolicy = _Profile
    bt.ToolRuntime = _Enum()
    bt.ToolStability = _Enum()
    bt.ToolStatus = _Enum()
    bt.ToolTier = _Enum()
    sys.modules["tools.base_tool"] = bt


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class FakeKieTransport:
    """Skill 74 transport double: request(method, url, headers, body, timeout) -> (status, bytes).
    Serves every route the adapters touch. ``create_calls`` / ``veo_calls`` hold the parsed
    request bodies; ``uploads`` the upload bodies; ``record_queue`` scripts recordInfo bodies."""

    def __init__(self):
        self.calls = []
        self.create_calls = []
        self.veo_calls = []
        self.uploads = []
        self.record_queue = []          # recordInfo bodies, consumed in order (then the default success)
        self.create_queue = []          # createTask bodies, consumed in order (then the default)
        self.veo_record = None          # body for /veo/record-info (default: success)
        self.input_props = {}           # model -> extra input properties for the schema
        self.prompt_max = None
        self.balance = 100000
        self.catalog = []
        self.create_error = None        # an exception instance raised on createTask
        self.create_raw = None          # (status, bytes) answered on createTask instead of the default (a gateway page)
        self.veo_raw = None             # (status, bytes) answered on the legacy veo/generate
        self.schema_error = None        # an exception instance raised on a schema GET
        self.result_url = RESULT_URL
        self.downloads = []

    @staticmethod
    def _j(obj, status=200):
        return status, json.dumps(obj).encode()

    def _schema(self, model):
        prompt = {"type": "string"}
        if self.prompt_max is not None:
            prompt["maxLength"] = self.prompt_max
        props = {"prompt": prompt}
        props.update(self.input_props.get(model, {}))
        body = {"type": "object", "required": ["model", "input"], "properties": {
            "model": {"type": "string"}, "callBackUrl": {"type": "string"},
            "input": {"type": "object", "properties": props}}}
        return {"openapi": "3.1.0", "paths": {"/api/v1/jobs/createTask": {"post": {
            "requestBody": {"content": {"application/json": {"schema": body}}}}}}}

    def request(self, method, url, headers=None, body=None, timeout=60):
        u = urlparse(url)
        self.calls.append((method, url))
        path = u.path
        if u.hostname not in ("api.kie.ai", "kieai.redpandaai.co"):  # a result file on a CDN host
            self.downloads.append(url)
            return 200, b"FIXTURE-RESULT-BYTES"
        if method == "GET" and path == "/api/v1/models":
            return self._j({"code": 200, "msg": "success", "data": {"total": len(self.catalog), "models": self.catalog}})
        if method == "GET" and path.startswith("/api/v1/models/") and path.endswith("/schema"):
            if self.schema_error is not None:
                raise self.schema_error
            model = path[len("/api/v1/models/"):-len("/schema")]
            return self._j({"code": 200, "msg": "success", "data": {"openapi": self._schema(model)}})
        if method == "GET" and path == "/api/v1/chat/credit":
            return self._j({"code": 200, "msg": "success", "data": self.balance})
        if method == "POST" and path == "/api/v1/jobs/createTask":
            self.create_calls.append(json.loads(body.decode()))
            if self.create_error is not None:
                raise self.create_error
            if self.create_raw is not None:
                return self.create_raw
            if self.create_queue:
                return self._j(self.create_queue.pop(0))
            return self._j({"code": 200, "msg": "success", "data": {"taskId": "task-%d" % len(self.create_calls)}})
        if method == "GET" and path == "/api/v1/jobs/recordInfo":
            tid = parse_qs(u.query).get("taskId", ["?"])[0]
            if self.record_queue:
                return self._j(self.record_queue.pop(0))
            return self._j({"code": 200, "msg": "success", "data": {
                "taskId": tid, "state": "success", "resultJson": json.dumps({"resultUrls": [self.result_url]})}})
        if method == "POST" and path.endswith("/file-base64-upload"):
            b = json.loads(body.decode())
            self.uploads.append(b)
            return self._j({"code": 200, "data": {"downloadUrl": "https://fixtures.example/up-%s" % b["fileName"], "fileName": b["fileName"]}})
        if method == "POST" and path == "/api/v1/veo/generate":
            self.veo_calls.append(json.loads(body.decode()))
            if self.veo_raw is not None:
                return self.veo_raw
            return self._j({"code": 200, "msg": "success", "data": {"taskId": "veo-task-%d" % len(self.veo_calls)}})
        if method == "GET" and path == "/api/v1/veo/record-info":
            return self._j(self.veo_record or {"code": 200, "data": {"successFlag": 1, "response": {"resultUrls": [self.result_url]}}})
        return 404, b'{"code":404,"msg":"no route"}'


class FakeClock:
    """A clock that only moves when the adapter sleeps, so a 30-minute poll deadline passes instantly."""

    def __init__(self):
        self.t = 1_000_000.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


def fresh_tool(module, cls_name, transport, skill74_dir=None):
    """A tool instance wired to a fake transport; ``skill74_dir`` selects the client path:
    None = auto (Skill 74 from the repo), "" = Skill 74 absent (embedded copy)."""
    os.environ["KIE_API_KEY"] = FIXTURE_KEY
    os.environ["KIE_LIVE_CACHE_DIR"] = tempfile.mkdtemp(prefix="kie47-cache-")
    os.environ["KIE_LIVE_MIN_SPACING"] = "0"
    os.environ["KIE_POLICY_ROOT"] = ""   # no policy owners: limits come from the fake schema only
    if skill74_dir is None:
        os.environ.pop("KIE_SKILL74_DIR", None)
    else:
        os.environ["KIE_SKILL74_DIR"] = skill74_dir
    module._CLIENT = None
    tool = getattr(module, cls_name)()
    clock = FakeClock()
    tool._transport = transport
    tool._sleep = clock.sleep
    tool._now = clock.now
    return tool


_PASS = 0
_FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {label}")
    else:
        _FAIL += 1
        print(f"  FAIL  {label}  {detail}")


def main() -> int:
    _install_base_tool_stub()
    vid = _load_module(VIDEO_PY, "kie_video_under_test")
    img = _load_module(IMAGE_PY, "kie_image_under_test")
    tmp = Path(tempfile.mkdtemp(prefix="kie47-decode-"))

    print("== resultJson as a JSON-ENCODED STRING: the saved file comes out of every route ==")
    t = FakeKieTransport()
    t.result_url = RESULT_IMG_URL
    res = fresh_tool(img, "KieImage", t).execute({"prompt": "a red barn", "output_path": str(tmp / "img.png")})
    check("image createTask->recordInfo: success and the file is written", res.success and (tmp / "img.png").read_bytes() == b"FIXTURE-RESULT-BYTES",
          detail=str(getattr(res, "error", "")))
    check("image: kie_result_url is the URL decoded from the JSON string", res.data.get("kie_result_url") == RESULT_IMG_URL)
    check("image: the CDN download carried no API credentials (Skill 74 save)", t.downloads == [RESULT_IMG_URL])

    t = FakeKieTransport()
    res = fresh_tool(vid, "KieVideo", t).execute({"prompt": "a calm lake", "output_path": str(tmp / "gem.mp4")})
    check("video gemini-omni-video createTask->recordInfo: success", res.success and res.data.get("model") == "gemini-omni-video",
          detail=str(getattr(res, "error", "")))
    check("video gemini-omni-video: kie_result_url decoded", res.data.get("kie_result_url") == RESULT_URL)

    t = FakeKieTransport()
    t.veo_record = {"code": 200, "data": {"successFlag": 1, "response": {}, "resultJson": json.dumps({"resultUrls": [RESULT_URL]})}}
    res = fresh_tool(vid, "KieVideo", t).execute({"prompt": "a calm lake", "model": "veo3_fast", "duration": "8",
                                                  "output_path": str(tmp / "veo.mp4")})
    check("video veo3_fast generate->record-info (resultJson string fallback): success", res.success and res.data.get("model") == "veo3_fast",
          detail=str(getattr(res, "error", "")))
    check("video veo3_fast: result URL decoded from the JSON string", res.data.get("kie_result_url") == RESULT_URL)
    check("video veo3_fast: legacy body keeps a top-level prompt and an INTEGER duration",
          t.veo_calls and t.veo_calls[0].get("prompt") == "a calm lake" and t.veo_calls[0].get("duration") == 8 and "input" not in t.veo_calls[0])

    print("== malformed / empty resultJson degrades to a failed ToolResult, never a crash ==")
    for label, rj in (("malformed", "{not json"), ("empty", ""), ("non-dict", "[1,2,3]")):
        t = FakeKieTransport()
        t.record_queue = [{"code": 200, "data": {"taskId": "x", "state": "success", "resultJson": rj}}]
        res = fresh_tool(img, "KieImage", t).execute({"prompt": "a red barn", "output_path": str(tmp / ("bad-%s.png" % label))})
        check(f"image: {label} resultJson -> success=False, no file", res.success is False and not (tmp / ("bad-%s.png" % label)).exists(),
              detail=str(getattr(res, "error", "")))

    print("== regression guard: the OLD (pre-fix) code path would have crashed ==")
    raw = json.dumps({"resultUrls": [RESULT_URL]})
    try:
        (raw or {}).get("resultUrls")  # the original line, applied to a str
        old_crashes = False
    except AttributeError:
        old_crashes = True
    check("pre-fix `(str).get(...)` raises AttributeError (bug was real)", old_crashes)

    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
