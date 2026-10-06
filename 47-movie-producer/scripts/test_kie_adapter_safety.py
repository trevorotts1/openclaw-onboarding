#!/usr/bin/env python3
"""test_kie_adapter_safety.py - the money and key safety rules of the Skill 47 adapters (fake Skill 74 transport,
no network, no real key):

  1. NO FALLBACK ON AN UNKNOWN OUTCOME. When gemini-omni-video times out (the task may still finish) or its
     createTask answer is lost to a network error, execute() does NOT start a second paid job on veo3_fast and does
     NOT resubmit: it fails with data.needs_repoll and the task id for the Dispatcher to re-poll. A definite
     failure (KIE reported the task failed) still falls back, and a prompt refusal never falls back.
  2. THE KEY GATE WORKS IN A BARE CLONE. With an empty HOME and no shared-utils anywhere (the Docker image and a
     clone), a well-formed key is AVAILABLE, a placeholder is UNAVAILABLE.
  3. OWNER RULE 12, THE PROMPT FLOOR. A descriptive prompt below 80 percent of the model maximum is a HARD REJECT
     with the characters to add; 95 percent passes; 101 percent is refused with the characters to cut (image and video).

Run:  python3 47-movie-producer/scripts/test_kie_adapter_safety.py      Exit: 0 = all pass.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_kie_adapter_resultjson_decode as base  # noqa: E402

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
    base._install_base_tool_stub()
    vid = base._load_module(base.VIDEO_PY, "kie_video_safety")
    img = base._load_module(base.IMAGE_PY, "kie_image_safety")
    tmp = Path(tempfile.mkdtemp(prefix="kie47-safety-"))
    GEM = {"prompt": "a calm lake", "output_path": str(tmp / "o.mp4")}
    RUNNING = {"code": 200, "data": {"taskId": "t", "state": "generating"}}

    print("== 1. no fallback and no resubmit when the outcome is unknown ==")
    ft = base.FakeKieTransport()
    ft.record_queue = [RUNNING] * 400   # the task never finishes inside the 30-minute deadline
    tool = base.fresh_tool(vid, "KieVideo", ft)
    res = tool.execute(dict(GEM))
    check("gemini timeout: success=False", res.success is False)
    check("gemini timeout: NO veo3_fast fallback job was started", ft.veo_calls == [])
    check("gemini timeout: createTask was sent exactly once (no resubmit)", len(ft.create_calls) == 1)
    check("gemini timeout: the task id is recorded for the Dispatcher to re-poll",
          res.data.get("kie_task_id") == "task-1" and res.data.get("needs_repoll") is True and res.data.get("kie_task_state") == "unresolved",
          detail=str(res.data))
    check("gemini timeout: the error says to re-poll and not to resubmit or switch model",
          "re-poll task task-1" in (res.error or "") and "do not resubmit or switch model" in (res.error or ""), detail=res.error)

    ft = base.FakeKieTransport()
    tool = base.fresh_tool(vid, "KieVideo", ft)
    ft.create_error = vid._kie_client()[0].KieError("network", "connection reset after send")
    res = tool.execute(dict(GEM))
    check("gemini createTask network error: no fallback job, createTask not resent",
          res.success is False and ft.veo_calls == [] and len(ft.create_calls) == 1)
    check("gemini createTask network error: flagged as an unknown createTask outcome (no task id exists)",
          res.data.get("kie_task_state") == "createTask_outcome_unknown" and res.data.get("needs_repoll") is True
          and res.data.get("kie_task_id") is None, detail=str(res.data))

    ft = base.FakeKieTransport()
    ft.record_queue = [{"code": 200, "data": {"taskId": "a", "state": "fail", "failMsg": "content policy violation"}}]
    res = base.fresh_tool(vid, "KieVideo", ft).execute(dict(GEM))
    check("a DEFINITE failure (KIE reported the task failed) still falls back to veo3_fast",
          res.success and res.data["model"] == "veo3_fast" and len(ft.create_calls) == 1 and len(ft.veo_calls) == 1, detail=str(getattr(res, "error", "")))

    ft = base.FakeKieTransport()
    ft.record_queue = [{"code": 200, "data": {"taskId": "a", "state": "fail", "failMsg": "content policy violation"}}]
    ft.veo_record = {"code": 200, "data": {"successFlag": 0}}   # the fallback itself never finishes
    res = base.fresh_tool(vid, "KieVideo", ft).execute(dict(GEM))
    check("a fallback that times out is also unresolved: task id recorded, nothing resubmitted",
          res.success is False and res.data.get("kie_task_id") == "veo-task-1" and res.data.get("needs_repoll") is True
          and len(ft.veo_calls) == 1, detail=str(res.data))

    ft = base.FakeKieTransport()
    ft.veo_record = {"code": 200, "data": {"successFlag": 0}}
    res = base.fresh_tool(vid, "KieVideo", ft).execute({"prompt": "a calm lake", "model": "veo3_fast", "output_path": str(tmp / "v.mp4")})
    check("direct veo3_fast timeout: unresolved with the task id (no resubmit)",
          res.success is False and res.data.get("kie_task_id") == "veo-task-1" and len(ft.veo_calls) == 1, detail=str(res.data))

    ft = base.FakeKieTransport()
    ft.record_queue = [RUNNING] * 400
    res = base.fresh_tool(vid, "KieVideo", ft).execute({"prompt": "a calm lake", "model": "bytedance/seedance-1.5-pro", "output_path": str(tmp / "s.mp4")})
    check("seedance timeout: unresolved with the task id, no second job",
          res.success is False and res.data.get("kie_task_id") == "task-1" and len(ft.create_calls) == 1, detail=str(res.data))

    print("== 2. the key gate in a bare clone: empty HOME, no shared-utils ==")
    clone = Path(tempfile.mkdtemp(prefix="kie47-bareclone-"))
    (clone / "tools" / "graphics").mkdir(parents=True)
    (clone / "tools" / "video").mkdir(parents=True)
    (clone / "tools" / "graphics" / "kie_image.py").write_text(base.IMAGE_PY.read_text(encoding="utf-8"), encoding="utf-8")
    (clone / "tools" / "video" / "kie_video.py").write_text(base.VIDEO_PY.read_text(encoding="utf-8"), encoding="utf-8")
    empty_home = tempfile.mkdtemp(prefix="kie47-emptyhome-")
    saved = {k: os.environ.get(k) for k in ("HOME", "OPENCLAW_SHARED_UTILS", "KIE_API_KEY")}
    try:
        os.environ["HOME"] = empty_home
        os.environ.pop("OPENCLAW_SHARED_UTILS", None)
        cimg = base._load_module(clone / "tools" / "graphics" / "kie_image.py", "bare_kie_image")
        cvid = base._load_module(clone / "tools" / "video" / "kie_video.py", "bare_kie_video")
        os.environ["KIE_API_KEY"] = base.FIXTURE_KEY
        check("bare clone: a well-formed key makes kie_image AVAILABLE", cimg.KieImage().get_status() == "AVAILABLE")
        check("bare clone: a well-formed key makes kie_video AVAILABLE", cvid.KieVideo().get_status() == "AVAILABLE")
        os.environ["KIE_API_KEY"] = "YOUR_CLIENT_KIE_API_KEY_HERE"
        check("bare clone: the installer placeholder is UNAVAILABLE (image)", cimg.KieImage().get_status() == "UNAVAILABLE")
        check("bare clone: the installer placeholder is UNAVAILABLE (video)", cvid.KieVideo().get_status() == "UNAVAILABLE")
        os.environ["KIE_API_KEY"] = "short"
        check("bare clone: a short key is UNAVAILABLE", cimg.KieImage().get_status() == "UNAVAILABLE")
        os.environ.pop("KIE_API_KEY", None)
        check("bare clone: no key is UNAVAILABLE", cvid.KieVideo().get_status() == "UNAVAILABLE")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    print("== 3. owner rule 12: the 80 percent prompt floor is a hard reject (79 refused, 95 passes, 101 refused) ==")
    for name, mod, cls, extra in (("image", img, "KieImage", {}), ("video gemini", vid, "KieVideo", {}),
                                  ("video seedance", vid, "KieVideo", {"model": "bytedance/seedance-1.5-pro"})):
        def run(n):
            ft = base.FakeKieTransport()
            ft.prompt_max = 1000   # floor 800, target 950
            res = base.fresh_tool(mod, cls, ft).execute(dict({"prompt": "x" * n, "output_path": str(tmp / f"{name}{n}.out")}, **extra))
            return res, ft
        res, ft = run(790)
        check(f"{name}: 79 percent is refused with the characters to add and nothing is sent",
              res.success is False and "below the 80 percent floor" in (res.error or "") and "ADD at least 10" in (res.error or "")
              and ft.create_calls == [] and ft.veo_calls == [], detail=res.error)
        res, ft = run(800)
        check(f"{name}: exactly 80 percent passes", res.success is True, detail=str(getattr(res, "error", "")))
        res, ft = run(950)
        check(f"{name}: 95 percent passes and is submitted", res.success is True and len(ft.create_calls) == 1, detail=str(getattr(res, "error", "")))
        res, ft = run(1010)
        check(f"{name}: 101 percent is refused with the characters to cut", res.success is False and "CUT exactly 10" in (res.error or "") and ft.create_calls == [])
    ft = base.FakeKieTransport()
    ft.prompt_max = 1000
    res = base.fresh_tool(vid, "KieVideo", ft).execute({"prompt": "x" * 100, "output_path": str(tmp / "gf.mp4")})
    check("a gemini prompt refused for the floor does NOT fall back to veo3_fast (no way around the rule)",
          res.success is False and ft.veo_calls == [] and ft.create_calls == [], detail=str(ft.veo_calls))

    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
