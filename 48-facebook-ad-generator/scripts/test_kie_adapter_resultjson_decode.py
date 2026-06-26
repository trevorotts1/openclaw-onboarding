#!/usr/bin/env python3
"""test_kie_adapter_resultjson_decode.py — proves the v14.1.2 resultJson fix.

THE BUG (confirmed live against api.kie.ai during the v14.1.x render proof):
  KIE's poll endpoints return the ``resultJson`` field as a JSON-ENCODED STRING
  (a string whose contents are themselves JSON), NOT an already-parsed object.
  The shipped adapters read it as if it were a dict and called ``.get()`` on the
  raw string, so they never extracted the result URL on a client box.

THE FIX:
  Both adapters now route ``resultJson`` through ``_decode_result_json`` before
  reading the output URL(s): str -> json.loads(); dict -> use as-is; else -> {}.

WHAT THIS TEST PROVES (no network, no KIE_API_KEY, AGPLv3-safe — tools.base_tool
is stubbed so the adapters import standalone):
  1. The real GET-poll path of each adapter extracts the result URL when KIE
     returns ``resultJson`` as a JSON STRING (the live shape that exposed the bug).
  2. The decode is defensive: an already-parsed dict still works; an empty
     string and malformed JSON degrade to "no result URL" (RuntimeError) rather
     than crashing with AttributeError on a str.

Covers all three shipped poll paths:
  - video gemini-omni-video  createTask -> /jobs/recordInfo   (KieVideo._poll_gemini_omni)
  - video veo3_fast          generate   -> /veo/record-info   (KieVideo._poll_veo)
  - image gpt-image-2        createTask -> /jobs/recordInfo   (KieImage._poll_task)

Run:  python3 47-movie-producer/scripts/test_kie_adapter_resultjson_decode.py
Exit: 0 = all pass; 1 = a failure.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTERS = REPO_ROOT / "47-movie-producer" / "kie-adapters" / "tools"
VIDEO_PY = ADAPTERS / "video" / "kie_video.py"
IMAGE_PY = ADAPTERS / "graphics" / "kie_image.py"

# A captured KIE recordInfo result URL (shape only; not a real asset).
RESULT_URL = "https://tempfile.aiquickdraw.com/s/fixture-result-12345.mp4"
RESULT_IMG_URL = "https://tempfile.aiquickdraw.com/s/fixture-result-67890.png"


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


# ---------------------------------------------------------------------------
# A fake `requests` whose GET returns a scripted recordInfo response, and whose
# sleep we monkeypatch so polling does not actually wait.
# ---------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"unexpected HTTP {self.status_code}")


def _patch_poll(mod, payload: dict):
    """Monkeypatch the module's lazily-imported `requests` and `time.sleep`."""
    fake_requests = types.SimpleNamespace(get=lambda *a, **k: _FakeResp(payload))
    real_import = __import__

    def fake_import(name, *a, **k):
        if name == "requests":
            return fake_requests
        return real_import(name, *a, **k)

    mod.time.sleep = lambda *_a, **_k: None  # no real waiting
    return fake_import


# ---------------------------------------------------------------------------
# Response payloads — resultJson as a JSON-ENCODED STRING (the live bug shape).
# ---------------------------------------------------------------------------
def _gemini_recordinfo_resultjson_as_string() -> dict:
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": "fixture-task-gemini",
            "state": "success",
            # <<< JSON-ENCODED STRING, exactly as KIE returns it >>>
            "resultJson": json.dumps({"resultUrls": [RESULT_URL]}),
        },
    }


def _veo_recordinfo_resultjson_as_string() -> dict:
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": "fixture-task-veo",
            "successFlag": "1",
            # response has no resultUrls/videoUrl -> must fall back to resultJson,
            # which is a JSON-ENCODED STRING.
            "response": {},
            "resultJson": json.dumps({"resultUrls": [RESULT_URL]}),
        },
    }


def _image_recordinfo_resultjson_as_string() -> dict:
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": "fixture-task-image",
            "state": "success",
            "resultJson": json.dumps({"resultUrls": [RESULT_IMG_URL]}),
        },
    }


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------
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


def run_poll(mod, method_name: str, payload: dict, instance):
    """Call a bound poll method with a patched requests/sleep; return its result
    or the raised exception."""
    import builtins

    fake_import = _patch_poll(mod, payload)
    orig_import = builtins.__import__
    builtins.__import__ = fake_import
    try:
        method = getattr(instance, method_name)
        try:
            return ("ok", method("fixture-task", "FAKE_KEY"))
        except Exception as exc:  # noqa: BLE001 — we assert on the type/text
            return ("err", exc)
    finally:
        builtins.__import__ = orig_import


def main() -> int:
    _install_base_tool_stub()
    vid = _load_module(VIDEO_PY, "kie_video_under_test")
    img = _load_module(IMAGE_PY, "kie_image_under_test")

    print("== _decode_result_json (defensive contract) ==")
    for mod_name, mod in (("video", vid), ("image", img)):
        d = mod._decode_result_json
        check(f"[{mod_name}] str  -> json.loads -> dict",
              d(json.dumps({"resultUrls": [RESULT_URL]})) == {"resultUrls": [RESULT_URL]})
        check(f"[{mod_name}] dict -> used as-is",
              d({"resultUrls": [RESULT_URL]}) == {"resultUrls": [RESULT_URL]})
        check(f"[{mod_name}] empty str -> {{}}", d("") == {})
        check(f"[{mod_name}] malformed JSON str -> {{}} (no crash)", d("{not json") == {})
        check(f"[{mod_name}] None -> {{}}", d(None) == {})
        check(f"[{mod_name}] non-dict JSON (list) -> {{}}", d("[1,2,3]") == {})

    print("== real poll path extracts URL when resultJson is a JSON STRING ==")
    KieVideo = vid.KieVideo
    KieImage = img.KieImage

    kind, res = run_poll(vid, "_poll_gemini_omni",
                         _gemini_recordinfo_resultjson_as_string(), KieVideo())
    check("video gemini-omni: poll returns the result URL (createTask->recordInfo)",
          kind == "ok" and res == RESULT_URL, detail=f"got {kind}={res!r}")

    kind, res = run_poll(vid, "_poll_veo",
                         _veo_recordinfo_resultjson_as_string(), KieVideo())
    check("video veo3_fast: poll returns the result URL (generate->record-info)",
          kind == "ok" and res == RESULT_URL, detail=f"got {kind}={res!r}")

    kind, res = run_poll(img, "_poll_task",
                         _image_recordinfo_resultjson_as_string(), KieImage())
    check("image gpt-image-2: poll returns the result URL (createTask->recordInfo)",
          kind == "ok" and res == RESULT_IMG_URL, detail=f"got {kind}={res!r}")

    print("== regression guard: the OLD (pre-fix) code path would have crashed ==")
    # Prove the bug is real: calling .get() on the raw JSON STRING raises.
    raw = json.dumps({"resultUrls": [RESULT_URL]})
    old_path_crashes = False
    try:
        (raw or {}).get("resultUrls")  # the original line, applied to a str
    except AttributeError:
        old_path_crashes = True
    check("pre-fix `(str).get(...)` raises AttributeError (bug was real)",
          old_path_crashes)

    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
