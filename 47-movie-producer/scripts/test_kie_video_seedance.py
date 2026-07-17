#!/usr/bin/env python3
"""test_kie_video_seedance.py — proves the Skill 62 U5 extension of
kie_video.py: bytedance/seedance-1.5-pro + two-image `input_urls` frame
pinning (spec §10.1/§10.2, CINEMATIC-AND-WEB-FUNNEL-ENGINE-SPEC.md).

WHAT THIS TEST PROVES (no network, no KIE_API_KEY, AGPLv3-safe — tools.
base_tool is stubbed so the adapter imports standalone, same harness
pattern as test_kie_adapter_resultjson_decode.py):

  1. `_submit_seedance` posts to the SAME /api/v1/jobs/createTask endpoint
     used by gemini-omni-video (no new HTTP surface), with the exact body
     shape documented in 07-kie-setup/kie-setup-full.md § "Seedance 1.5 Pro"
     (model, input.prompt, input.aspect_ratio [required], input.resolution,
     input.duration [string], input.fixed_lens, input.generate_audio).
  2. Frame pinning: `input_urls` is included in the submitted body ONLY when
     non-empty, and 2 URLs are submitted in the EXACT order given — index 0
     = first frame, index 1 = last frame (order is never re-sorted or
     de-duplicated the way gemini-omni's multi-alias image merge is).
  3. Text-to-video (`input_urls` omitted entirely) never sends the
     `input_urls` key in the request body, matching kie-setup-full.md:
     "Text to video if input_urls is omitted".
  4. `_snap_duration`/`_snap_aspect`/`_snap_resolution` enforce Seedance's
     own valid sets (4/8/12s; 1:1/4:3/3:4/16:9/9:16/21:9; 480p/720p/1080p)
     — NOT gemini-omni-video's narrower 16:9/9:16-only aspect set, which
     would have wrongly clamped a valid Seedance aspect ratio before this
     fix (aspect snapping used to run before the model was known).
  5. `_resolve_input_urls` caps at 2 entries, drops non-http(s)/non-string
     entries, and preserves order.
  6. The real poll path (`_poll_seedance` -> shared `_poll_jobs_task`)
     extracts the result URL exactly like `_poll_gemini_omni` (both hit
     the identical /api/v1/jobs/recordInfo endpoint), and a failure is
     attributed to the Seedance model in the error text (not mislabeled
     "gemini-omni-video").
  7. `execute()` end-to-end: two-frame pinning submit+poll+download
     succeeds and echoes `input_urls` in the result; an out-of-range
     prompt length is refused before any HTTP call; a submit-time
     exception surfaces as a failed ToolResult, never a crash.
  8. No regression: `_poll_gemini_omni(task_id, api_key)` — the pre-U5
     external call signature — still works unchanged.

Run:  python3 47-movie-producer/scripts/test_kie_video_seedance.py
Exit: 0 = all pass; 1 = a failure.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from typing import Any

# execute() reads KIE_API_KEY from the environment before doing anything else.
# This is a FIXTURE placeholder value only (never a real credential) so the
# execute()-level tests below can reach the submit/poll/download path under
# test; every HTTP call in this file is faked, so the value is never sent
# anywhere real.
os.environ.setdefault("KIE_API_KEY", "FIXTURE-NOT-A-REAL-KEY")

REPO_ROOT = Path(__file__).resolve().parents[2]
VIDEO_PY = REPO_ROOT / "47-movie-producer" / "kie-adapters" / "tools" / "video" / "kie_video.py"

RESULT_URL = "https://tempfile.aiquickdraw.com/s/fixture-seedance-result-12345.mp4"
FIRST_FRAME_URL = "https://fixtures.example/scene-12-first-frame.png"
LAST_FRAME_URL = "https://fixtures.example/scene-13-first-frame.png"


# ---------------------------------------------------------------------------
# Stub tools.base_tool so the adapter imports without OpenMontage present.
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


# ---------------------------------------------------------------------------
# Fake requests transport
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


def _seedance_recordinfo_success() -> dict:
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": "fixture-task-seedance",
            "state": "success",
            "resultJson": json.dumps({"resultUrls": [RESULT_URL]}),
        },
    }


def _seedance_recordinfo_failed() -> dict:
    return {
        "code": 200,
        "msg": "ok",
        "data": {
            "taskId": "fixture-task-seedance-fail",
            "state": "fail",
            "failMsg": "content policy violation",
        },
    }


def main() -> int:
    _install_base_tool_stub()
    vid = _load_module(VIDEO_PY, "kie_video_seedance_under_test")
    KieVideo = vid.KieVideo
    instance = KieVideo()

    print("== module-level Seedance constants ==")
    check("_SEEDANCE_MODEL is the exact Kie wire slug",
          vid._SEEDANCE_MODEL == "bytedance/seedance-1.5-pro")
    check("_SEEDANCE_VALID_DURATIONS == {4,8,12}",
          vid._SEEDANCE_VALID_DURATIONS == {"4", "8", "12"})
    check("_SEEDANCE_VALID_RESOLUTIONS == {480p,720p,1080p}",
          vid._SEEDANCE_VALID_RESOLUTIONS == {"480p", "720p", "1080p"})
    check("_SEEDANCE_VALID_ASPECT_RATIOS == the 6-value Kie set",
          vid._SEEDANCE_VALID_ASPECT_RATIOS == {"1:1", "4:3", "3:4", "16:9", "9:16", "21:9"})
    check("model enum includes bytedance/seedance-1.5-pro",
          vid._SEEDANCE_MODEL in KieVideo.input_schema["properties"]["model"]["enum"])

    print("== _snap_duration (Seedance: 4/8/12, snapped to NEAREST not gemini/veo sets) ==")
    check("valid '4' passes through", instance._snap_duration("4", vid._SEEDANCE_MODEL) == "4")
    check("valid '8' passes through", instance._snap_duration("8", vid._SEEDANCE_MODEL) == "8")
    check("valid '12' passes through", instance._snap_duration("12", vid._SEEDANCE_MODEL) == "12")
    check("invalid '6' snaps to '8' (nearest)", instance._snap_duration("6", vid._SEEDANCE_MODEL) == "8")
    check("invalid '2' snaps to '4' (nearest)", instance._snap_duration("2", vid._SEEDANCE_MODEL) == "4")
    check("invalid '99' snaps to '12' (nearest)", instance._snap_duration("99", vid._SEEDANCE_MODEL) == "12")
    check("non-numeric snaps to default '8'", instance._snap_duration("bogus", vid._SEEDANCE_MODEL) == "8")
    check("gemini-omni-video path unaffected by Seedance branch",
          instance._snap_duration("6", "gemini-omni-video") == "6")

    print("== _snap_aspect (Seedance's WIDER set must not be clamped to 16:9/9:16) ==")
    for ratio in ("1:1", "4:3", "3:4", "16:9", "9:16", "21:9"):
        check(f"Seedance accepts '{ratio}' as-is",
              instance._snap_aspect(ratio, vid._SEEDANCE_MODEL) == ratio)
    check("Seedance invalid ratio snaps to 16:9",
          instance._snap_aspect("bogus", vid._SEEDANCE_MODEL) == "16:9")
    check("gemini-omni-video still rejects '21:9' (snaps to 16:9) — narrower set unaffected",
          instance._snap_aspect("21:9", "gemini-omni-video") == "16:9")
    check("gemini-omni-video still accepts '9:16' unaffected by Seedance change",
          instance._snap_aspect("9:16", "gemini-omni-video") == "9:16")

    print("== _snap_resolution ==")
    for res in ("480p", "720p", "1080p"):
        check(f"resolution '{res}' accepted as-is", instance._snap_resolution(res) == res)
    check("invalid resolution snaps to default 720p", instance._snap_resolution("4K") == "720p")

    print("== _resolve_input_urls (order-preserving, capped at 2, filters bad entries) ==")
    check("empty/missing input_urls -> []", instance._resolve_input_urls({}) == [])
    check("single valid URL preserved",
          instance._resolve_input_urls({"input_urls": [FIRST_FRAME_URL]}) == [FIRST_FRAME_URL])
    two = instance._resolve_input_urls({"input_urls": [FIRST_FRAME_URL, LAST_FRAME_URL]})
    check("two valid URLs preserved IN ORDER (first, then last)",
          two == [FIRST_FRAME_URL, LAST_FRAME_URL], detail=f"got {two!r}")
    capped = instance._resolve_input_urls({"input_urls": [FIRST_FRAME_URL, LAST_FRAME_URL, "https://extra.example/x.png"]})
    check("a 3rd URL is dropped (capped at 2)", capped == [FIRST_FRAME_URL, LAST_FRAME_URL])
    filtered = instance._resolve_input_urls({"input_urls": ["not-a-url", FIRST_FRAME_URL, 42, LAST_FRAME_URL]})
    check("non-http(s)/non-string entries are skipped, valid ones kept in relative order",
          filtered == [FIRST_FRAME_URL, LAST_FRAME_URL], detail=f"got {filtered!r}")

    print("== _submit_seedance request body shape ==")
    captured: dict[str, Any] = {}

    class _FakePostResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"taskId": "fixture-task-seedance"}}

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002 - matches requests kw
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json
        captured["timeout"] = timeout
        return _FakePostResp()

    fake_requests_mod = types.SimpleNamespace(post=fake_post)
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "requests":
            return fake_requests_mod
        return real_import(name, *a, **k)

    builtins.__import__ = fake_import
    try:
        task_id = instance._submit_seedance(
            "A serene beach at sunset with waves gently crashing on the shore",
            "8", "16:9", "720p", [FIRST_FRAME_URL, LAST_FRAME_URL],
            False, False, "FAKE_KEY",
        )
    finally:
        builtins.__import__ = real_import

    check("submit posts to the SHARED /api/v1/jobs/createTask endpoint (no new HTTP surface)",
          captured["url"] == vid._GEMINI_CREATE_URL, detail=captured.get("url"))
    check("submit returns the taskId from the response", task_id == "fixture-task-seedance")
    check("body.model is the exact wire slug", captured["body"]["model"] == "bytedance/seedance-1.5-pro")
    body_input = captured["body"]["input"]
    check("body.input.aspect_ratio is REQUIRED and present", body_input.get("aspect_ratio") == "16:9")
    check("body.input.resolution present", body_input.get("resolution") == "720p")
    check("body.input.duration is a STRING", body_input.get("duration") == "8" and isinstance(body_input.get("duration"), str))
    check("body.input.fixed_lens present (default false)", body_input.get("fixed_lens") is False)
    check("body.input.generate_audio present (default false)", body_input.get("generate_audio") is False)
    check("body.input.input_urls carries [first, last] IN ORDER — frame pinning",
          body_input.get("input_urls") == [FIRST_FRAME_URL, LAST_FRAME_URL])
    check("Authorization header carries Bearer + the key",
          captured["headers"]["Authorization"] == "Bearer FAKE_KEY")

    print("== text-to-video: input_urls key omitted entirely when no images given ==")
    captured2: dict[str, Any] = {}

    def fake_post2(url, headers=None, json=None, timeout=None):  # noqa: A002
        captured2["body"] = json
        return _FakePostResp()

    builtins.__import__ = lambda name, *a, **k: (
        types.SimpleNamespace(post=fake_post2) if name == "requests" else real_import(name, *a, **k)
    )
    try:
        instance._submit_seedance("A boy rides a bike at sunset", "8", "16:9", "720p", [], False, False, "FAKE_KEY")
    finally:
        builtins.__import__ = real_import
    check("input_urls key is ABSENT from the body for text-to-video (matches kie-setup-full.md)",
          "input_urls" not in captured2["body"]["input"], detail=str(captured2["body"]["input"]))

    print("== real poll path (_poll_seedance -> shared _poll_jobs_task) ==")

    def _patch_poll(mod, payload: dict):
        fake_requests = types.SimpleNamespace(get=lambda *a, **k: _FakeResp(payload))
        ri = builtins.__import__

        def fi(name, *a, **k):
            if name == "requests":
                return fake_requests
            return ri(name, *a, **k)
        mod.time.sleep = lambda *_a, **_k: None
        return fi

    fake_import_ok = _patch_poll(vid, _seedance_recordinfo_success())
    builtins.__import__ = fake_import_ok
    try:
        result = instance._poll_seedance("fixture-task-seedance", "FAKE_KEY")
    finally:
        builtins.__import__ = real_import
    check("poll extracts the result URL on success", result == RESULT_URL, detail=result)

    fake_import_fail = _patch_poll(vid, _seedance_recordinfo_failed())
    builtins.__import__ = fake_import_fail
    try:
        try:
            instance._poll_seedance("fixture-task-seedance-fail", "FAKE_KEY")
            poll_failed_correctly = False
            err_text = ""
        except RuntimeError as exc:
            poll_failed_correctly = True
            err_text = str(exc)
    finally:
        builtins.__import__ = real_import
    check("poll raises RuntimeError on a failed task", poll_failed_correctly)
    check("failure text attributes the model as Seedance, NOT 'gemini-omni-video'",
          "bytedance/seedance-1.5-pro" in err_text and "gemini-omni-video" not in err_text,
          detail=err_text)

    print("== _poll_gemini_omni: pre-U5 2-arg call signature unaffected (no regression) ==")
    fake_import_gemini = _patch_poll(vid, {
        "code": 200, "msg": "success",
        "data": {"taskId": "fixture-task-gemini", "state": "success",
                 "resultJson": json.dumps({"resultUrls": [RESULT_URL]})},
    })
    builtins.__import__ = fake_import_gemini
    try:
        gemini_result = instance._poll_gemini_omni("fixture-task-gemini", "FAKE_KEY")
    finally:
        builtins.__import__ = real_import
    check("_poll_gemini_omni(task_id, api_key) still works unchanged", gemini_result == RESULT_URL)

    print("== execute() end-to-end: frame-pinned Seedance clip ==")

    def fake_post3(url, headers=None, json=None, timeout=None):  # noqa: A002
        return _FakePostResp()

    downloaded: dict[str, Any] = {}

    class _FakeGetResp:
        def __init__(self, payload=None, content=b"FAKE-MP4-BYTES", status_code=200):
            self._payload = payload or _seedance_recordinfo_success()
            self.content = content
            self.status_code = status_code

        def json(self):
            return self._payload

        def raise_for_status(self):
            pass

    def fake_get(url, params=None, headers=None, timeout=None, allow_redirects=None):
        if "recordInfo" in url:
            return _FakeGetResp()
        downloaded["url"] = url
        return _FakeGetResp(content=b"FAKE-MP4-BYTES")

    fake_requests3 = types.SimpleNamespace(post=fake_post3, get=fake_get)
    builtins.__import__ = lambda name, *a, **k: (
        fake_requests3 if name == "requests" else real_import(name, *a, **k)
    )
    vid.time.sleep = lambda *_a, **_k: None
    tmp_out = REPO_ROOT / "62-cinematic-web-funnel-engine" / "tests" / "fixtures" / "kie" / "_tmp_seedance_output.mp4"
    tmp_out.parent.mkdir(parents=True, exist_ok=True)
    try:
        result_tool = instance.execute({
            "prompt": "A serene beach at sunset, waves crashing gently, palm trees swaying",
            "model": "bytedance/seedance-1.5-pro",
            "input_urls": [FIRST_FRAME_URL, LAST_FRAME_URL],
            "aspect_ratio": "21:9",
            "resolution": "1080p",
            "duration": "12",
            "generate_audio": True,
            "output_path": str(tmp_out),
        })
    finally:
        builtins.__import__ = real_import
        if tmp_out.exists():
            tmp_out.unlink()

    check("execute() reports success", getattr(result_tool, "success", False) is True,
          detail=getattr(result_tool, "error", None))
    check("execute() data.model is the Seedance slug", result_tool.data.get("model") == "bytedance/seedance-1.5-pro")
    check("execute() echoes the frame-pin input_urls IN ORDER",
          result_tool.data.get("input_urls") == [FIRST_FRAME_URL, LAST_FRAME_URL])
    check("execute() preserves the wide aspect ratio (not clamped to 16:9)",
          result_tool.data.get("aspect_ratio") == "21:9")
    check("execute() preserves the snapped duration", result_tool.data.get("duration") == "12")
    check("execute() carries the render-proof kie_task_id", result_tool.data.get("kie_task_id") == "fixture-task-seedance")

    print("== execute() refuses an out-of-range prompt BEFORE any HTTP call ==")
    call_count = {"n": 0}

    def counting_post(*a, **k):
        call_count["n"] += 1
        return _FakePostResp()

    builtins.__import__ = lambda name, *a, **k: (
        types.SimpleNamespace(post=counting_post, get=lambda *a2, **k2: _FakeGetResp())
        if name == "requests" else real_import(name, *a, **k)
    )
    try:
        result_short = instance.execute({
            "prompt": "hi",  # 2 chars, under the 3-char floor
            "model": "bytedance/seedance-1.5-pro",
        })
    finally:
        builtins.__import__ = real_import
    check("a 2-char prompt is refused", result_short.success is False)
    check("no HTTP call was made for the refused prompt", call_count["n"] == 0)

    print("== execute() surfaces a submit-time exception as a failed ToolResult (no crash) ==")

    def raising_post(*a, **k):
        raise RuntimeError("simulated network failure")

    builtins.__import__ = lambda name, *a, **k: (
        types.SimpleNamespace(post=raising_post) if name == "requests" else real_import(name, *a, **k)
    )
    try:
        result_err = instance.execute({
            "prompt": "A valid prompt long enough to pass the floor",
            "model": "bytedance/seedance-1.5-pro",
        })
    finally:
        builtins.__import__ = real_import
    check("submit failure surfaces as success=False", result_err.success is False)
    check("submit failure error text attributes the Seedance model",
          "bytedance/seedance-1.5-pro" in (result_err.error or ""), detail=result_err.error)

    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
