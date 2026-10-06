#!/usr/bin/env python3
"""test_kie_video_seedance.py — proves the Skill 62 U5 extension of
kie_video.py: bytedance/seedance-1.5-pro + two-image `input_urls` frame
pinning (spec §10.1/§10.2, CINEMATIC-AND-WEB-FUNNEL-ENGINE-SPEC.md).

WHAT THIS TEST PROVES (no network, no KIE_API_KEY, AGPLv3-safe — tools.
base_tool is stubbed so the adapter imports standalone, same harness
pattern as test_kie_adapter_resultjson_decode.py):

  1. execute() submits through Skill 74 to the SAME /api/v1/jobs/createTask
     endpoint used by gemini-omni-video (no new HTTP surface), with the exact
     body shape documented in 07-kie-setup/kie-setup-full.md § "Seedance 1.5 Pro"
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
  6. A failed Seedance task is attributed to the Seedance model in the error
     text (not mislabeled "gemini-omni-video").
  7. `execute()` end-to-end: two-frame pinning submit+wait+save succeeds and
     echoes `input_urls` in the result; the prompt length comes from Skill 74
     prompt-budget / the live schema (a too-long prompt is refused before
     createTask, a too-short one fails schema validation); a submit-time
     exception surfaces as a failed ToolResult, never a crash.
  8. gemini-omni-video: one retry on a transient image-fetch failure, a
     fallback to veo3_fast on any other failure, createTask never resent after
     a network error.

Run:  python3 47-movie-producer/scripts/test_kie_video_seedance.py
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
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_kie_adapter_resultjson_decode as base  # noqa: E402  (shared FakeKieTransport + fresh_tool)

# execute() reads KIE_API_KEY from the environment (a synthetic high-entropy fixture, never a real
# credential; set by fresh_tool). Every HTTP call in this file goes to the FakeKieTransport.

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

    print("== execute() through Skill 74: request body shape ==")
    ft = base.FakeKieTransport()
    tool = base.fresh_tool(vid, "KieVideo", ft)
    tmp = Path(tempfile.mkdtemp(prefix="kie47-seedance-"))
    result_tool = tool.execute({
        "prompt": "A serene beach at sunset, waves crashing gently, palm trees swaying",
        "model": "bytedance/seedance-1.5-pro",
        "input_urls": [FIRST_FRAME_URL, LAST_FRAME_URL],
        "aspect_ratio": "21:9",
        "resolution": "1080p",
        "duration": "12",
        "generate_audio": True,
        "output_path": str(tmp / "clip.mp4"),
    })
    check("execute() reports success (%s)" % getattr(result_tool, "error", None),
          getattr(result_tool, "success", False) is True)
    body = ft.create_calls[0] if ft.create_calls else {}
    body_input = body.get("input", {})
    check("submit goes to the SHARED createTask path (the only create route used)", len(ft.create_calls) == 1 and not ft.veo_calls)
    check("body.model is the exact wire slug", body.get("model") == "bytedance/seedance-1.5-pro")
    check("body.input.aspect_ratio is REQUIRED and present (wide ratio not clamped)", body_input.get("aspect_ratio") == "21:9")
    check("body.input.resolution present", body_input.get("resolution") == "1080p")
    check("body.input.duration is a STRING", body_input.get("duration") == "12" and isinstance(body_input.get("duration"), str))
    check("body.input.fixed_lens present (default false)", body_input.get("fixed_lens") is False)
    check("body.input.generate_audio present", body_input.get("generate_audio") is True)
    check("body.input.input_urls carries [first, last] IN ORDER — frame pinning",
          body_input.get("input_urls") == [FIRST_FRAME_URL, LAST_FRAME_URL])
    check("execute() data.model is the Seedance slug", result_tool.data.get("model") == "bytedance/seedance-1.5-pro")
    check("execute() echoes the frame-pin input_urls IN ORDER",
          result_tool.data.get("input_urls") == [FIRST_FRAME_URL, LAST_FRAME_URL])
    check("execute() preserves the wide aspect ratio (not clamped to 16:9)", result_tool.data.get("aspect_ratio") == "21:9")
    check("execute() preserves the snapped duration", result_tool.data.get("duration") == "12")
    check("execute() carries the render-proof kie_task_id", result_tool.data.get("kie_task_id") == "task-1")
    check("the MP4 was saved to output_path", (tmp / "clip.mp4").read_bytes() == b"FIXTURE-RESULT-BYTES")

    print("== text-to-video: input_urls key omitted entirely when no images given ==")
    ft = base.FakeKieTransport()
    base.fresh_tool(vid, "KieVideo", ft).execute({
        "prompt": "A boy rides a bike at sunset", "model": "bytedance/seedance-1.5-pro", "output_path": str(tmp / "t2v.mp4")})
    check("input_urls key is ABSENT from the body for text-to-video (matches kie-setup-full.md)",
          ft.create_calls and "input_urls" not in ft.create_calls[0]["input"], detail=str(ft.create_calls))

    print("== a failed Seedance task is attributed to Seedance ==")
    ft = base.FakeKieTransport()
    ft.record_queue = [{"code": 200, "msg": "ok", "data": {"taskId": "t", "state": "fail", "failMsg": "content policy violation"}}]
    res_fail = base.fresh_tool(vid, "KieVideo", ft).execute({
        "prompt": "A boy rides a bike at sunset", "model": "bytedance/seedance-1.5-pro", "output_path": str(tmp / "f.mp4")})
    err_text = res_fail.error or ""
    check("failed task -> success=False", res_fail.success is False)
    check("failure text attributes the model as Seedance, NOT 'gemini-omni-video'",
          "bytedance/seedance-1.5-pro" in err_text and "gemini-omni-video" not in err_text and "content policy violation" in err_text,
          detail=err_text)

    print("== prompt length comes from Skill 74 (live schema / prompt-budget), not a band in the adapter ==")
    ft = base.FakeKieTransport()
    ft.prompt_max = 60
    ft.input_props = {"bytedance/seedance-1.5-pro": {}}
    res_long = base.fresh_tool(vid, "KieVideo", ft).execute({
        "prompt": "x" * 90, "model": "bytedance/seedance-1.5-pro", "output_path": str(tmp / "l.mp4")})
    check("a prompt over the schema maximum is refused with the exact characters to CUT",
          res_long.success is False and "CUT exactly 30" in (res_long.error or ""), detail=res_long.error)
    check("no createTask was sent for the over-long prompt", ft.create_calls == [])
    ft = base.FakeKieTransport()
    ft.input_props = {"bytedance/seedance-1.5-pro": {}}
    ft._schema_orig = ft._schema

    def _schema_min(model, _o=ft._schema):
        sch = _o(model)
        sch["paths"]["/api/v1/jobs/createTask"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]["input"]["properties"]["prompt"]["minLength"] = 3
        return sch
    ft._schema = _schema_min
    res_short = base.fresh_tool(vid, "KieVideo", ft).execute({"prompt": "hi", "model": "bytedance/seedance-1.5-pro"})
    check("a 2-char prompt fails the live schema minLength before any createTask",
          res_short.success is False and ft.create_calls == [] and "validation_failed" in (res_short.error or ""), detail=res_short.error)

    print("== execute() surfaces a submit-time exception as a failed ToolResult (no crash), createTask not resent ==")
    ft = base.FakeKieTransport()
    err_tool = base.fresh_tool(vid, "KieVideo", ft)
    ft.create_error = vid._kie_client()[0].KieError("network", "simulated network failure")
    res_err = err_tool.execute({
        "prompt": "A valid prompt long enough to pass the floor", "model": "bytedance/seedance-1.5-pro"})
    check("submit failure surfaces as success=False", res_err.success is False)
    check("submit failure error text attributes the Seedance model",
          "bytedance/seedance-1.5-pro" in (res_err.error or ""), detail=res_err.error)
    check("createTask was sent exactly once (never retried after a network error)", len(ft.create_calls) == 1)

    print("== gemini-omni-video: transient image-fetch -> one retry; other failure -> veo3_fast fallback ==")
    ft = base.FakeKieTransport()
    ft.record_queue = [{"code": 200, "data": {"taskId": "a", "state": "fail", "failMsg": "image fetch failed"}}]
    res_retry = base.fresh_tool(vid, "KieVideo", ft).execute({"prompt": "a calm lake", "output_path": str(tmp / "g1.mp4")})
    check("transient image-fetch failure is retried once and then succeeds on gemini-omni-video",
          res_retry.success and res_retry.data["model"] == "gemini-omni-video" and len(ft.create_calls) == 2 and not ft.veo_calls,
          detail=str(getattr(res_retry, "error", "")))
    ft = base.FakeKieTransport()
    ft.record_queue = [{"code": 200, "data": {"taskId": "a", "state": "fail", "failMsg": "content policy violation"}}]
    res_fb = base.fresh_tool(vid, "KieVideo", ft).execute({"prompt": "a calm lake", "output_path": str(tmp / "g2.mp4")})
    check("a non-transient gemini failure is NOT resubmitted (one createTask) and falls back to veo3_fast",
          res_fb.success and res_fb.data["model"] == "veo3_fast" and len(ft.create_calls) == 1 and len(ft.veo_calls) == 1,
          detail=str(getattr(res_fb, "error", "")))

    print("== credit preflight: a real shortfall blocks before createTask ==")
    ft = base.FakeKieTransport()
    ft.catalog = [{"model": "bytedance/seedance-1.5-pro", "taskType": ["Text to Video"], "pricingDesc": "A 5-second video costs 160 credits"}]
    ft.balance = 100
    res_broke = base.fresh_tool(vid, "KieVideo", ft).execute({"prompt": "A boy rides a bike at sunset", "model": "bytedance/seedance-1.5-pro"})
    check("insufficient credits -> refused, no createTask", res_broke.success is False and ft.create_calls == []
          and "insufficient_credits" in (res_broke.error or ""), detail=res_broke.error)

    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
