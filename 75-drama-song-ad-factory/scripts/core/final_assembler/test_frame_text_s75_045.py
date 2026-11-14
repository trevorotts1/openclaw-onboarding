#!/usr/bin/env python3
"""S75-045 and S75-024: say what the on-screen text check did (assembler half).

Proves exactly the two findings and nothing looser:

  NO READER: with no real extractor (no tesseract, or a dry run) every row for
             a segment that plans on-screen words is UNAVAILABLE with reason
             OCR_UNAVAILABLE -- never PASS -- and the dry-run receipt carries
             that as a warning.
  WRONG TEXT: an extractor that runs and returns words other than the planned
             words gives a FAIL row and blocks the gate (TEXT_CHANGED).
  RIGHT TEXT: an extractor that returns the planned words gives PASS.
  SCOPE:     only segments that plan words get a row; the lip-sync rows keep
             their F9 shape (no status key).
  S75-024:   lane sizing is told the run's OWN bound builder (the runtime and
             route in model-bindings.json), not the old literals.

stdlib only, zero paid calls, no ffmpeg binary and no tesseract required.

Run: python3 -B scripts/core/final_assembler/test_frame_text_s75_045.py
"""
import json
import os
import shutil
import sys
import tempfile
import types
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import final_assembler.assembler as A            # noqa: E402
import final_assembler.frame_text as FT          # noqa: E402
from final_assembler.frame_text import (         # noqa: E402
    OCR_UNAVAILABLE, register_extractor,
)

FAILS = []


def check(name, cond, detail=""):
    detail = detail if isinstance(detail, str) else repr(detail)
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _seg(src="shot1.mp4", text=None, dur=5.0):
    seg = {"src": src, "dur": dur}
    if text is not None:
        seg["on_screen_text"] = text
    return seg


def _plan(segments):
    return A.plan_timeline({
        "schema_version": A.TIMELINE_SCHEMA, "fps": 30,
        "width": 1920, "height": 1080, "song_path": None,
        "transition": "none", "segments": segments,
    }, ".")


def _write_tl(tmp, segments):
    path = os.path.join(tmp, "tl.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
                   "width": 1920, "height": 1080, "song_path": None,
                   "transition": "none", "segments": segments}, fh)
    return path


# --------------------------------------------------------------- S75-045 ----


def test_no_reader_is_unavailable_never_pass():
    """No extractor configured -> UNAVAILABLE / OCR_UNAVAILABLE, never PASS."""
    rows = FT.text_check_rows(
        [_seg(text="GRAND OPENING"), _seg("b.mp4")], ffmpeg=None)
    check("one row per segment that plans words", len(rows) == 1, rows)
    check("segments with no planned words get no row",
          [r["clip"] for r in rows] == ["shot1.mp4"], rows)
    row = rows[0]
    check("no reader -> status UNAVAILABLE",
          row["status"] == FT.UNAVAILABLE, row.get("status"))
    check("no reader -> reason OCR_UNAVAILABLE",
          row["reason_code"] == OCR_UNAVAILABLE, row.get("reason_code"))
    check("the stub names itself as the extractor",
          row["extractor"] == FT.STUB_NAME, row.get("extractor"))
    check("no reader is never PASS", row["status"] != FT.PASS, row)


def test_planned_text_shapes():
    """The shot plan's own keys: a string, a list of strings, [{text}]."""
    check("a string",
          FT.planned_text({"on_screen_text": "OPEN"}) == "OPEN")
    check("a list of strings",
          FT.planned_text({"on_screen_text": ["OPEN", "TODAY"]}) == "OPEN TODAY")
    check("a list of text objects",
          FT.planned_text({"on_screen_text": [{"text": "OPEN"}]}) == "OPEN")
    check("the single-text key",
          FT.planned_text({"text": "OPEN"}) == "OPEN")
    check("no planned words -> None",
          FT.planned_text({"src": "a.mp4"}) is None)


def test_wrong_text_fails():
    """An extractor that runs and reads other words -> FAIL, and it blocks."""
    register_extractor("s75-045-wrong", lambda paths: ["GRAND OPEING"] * len(paths))
    rows = FT.text_check_rows([_seg(text="GRAND OPENING")], ffmpeg=None,
                              extractor="s75-045-wrong")
    check("wrong text -> status FAIL",
          rows and rows[0]["status"] == FT.FAIL, rows)
    check("wrong text -> reason TEXT_CHANGED",
          rows and rows[0]["reason_code"] == FT.TEXT_CHANGED, rows)

    plan = _plan([_seg(text="GRAND OPENING"), _seg("b.mp4", dur=6.0)])
    gate_rows, fail = A.frame_text_gate(plan, extractor="s75-045-wrong")
    check("the gate blocks on wrong on-screen words",
          fail is not None and fail["outcome"] == "error", fail)
    check("the gate names TEXT_CHANGED",
          fail is not None and fail["reason_code"] == FT.TEXT_CHANGED,
          fail and fail.get("reason_code"))
    check("the blocked receipt shows every text row",
          fail is not None
          and [r["clip"] for r in fail["evidence"]["frame_text"]]
          == ["shot1.mp4"], fail)
    check("the blocked receipt carries no PASS row",
          all(r.get("status") != FT.PASS for r in gate_rows), gate_rows)


def test_right_text_passes():
    """An extractor that reads exactly the planned words -> PASS, gate open."""
    register_extractor("s75-045-right",
                       lambda paths: ["GRAND OPENING"] * len(paths))
    rows = FT.text_check_rows([_seg(text="GRAND OPENING")], ffmpeg=None,
                              extractor="s75-045-right")
    check("right text -> status PASS",
          rows and rows[0]["status"] == FT.PASS, rows)
    check("right text -> no reason code",
          rows and rows[0]["reason_code"] is None, rows)
    plan = _plan([_seg(text="GRAND OPENING")])
    gate_rows, fail = A.frame_text_gate(plan, extractor="s75-045-right")
    check("correct on-screen words never block the gate",
          fail is None, fail)
    check("the PASS row keeps its readable frames without flagging",
          any(r.get("check") == "onscreen_text"
              and r.get("status") == FT.PASS and r.get("text_frames")
              for r in gate_rows), gate_rows)


def test_lipsync_rows_keep_the_f9_shape():
    """The F9 rows are unchanged: no status key, only the on-screen rows carry it."""
    plan = _plan([_seg(dur=5.0, text="OPEN")])
    plan["segments"][0]["lip_sync"] = True
    rows, fail = A.frame_text_gate(plan)
    check("no reader never blocks the gate", fail is None, fail)
    lip = [r for r in rows if r.get("check") != "onscreen_text"]
    text = [r for r in rows if r.get("check") == "onscreen_text"]
    check("one lip-sync row keeps its F9 shape",
          len(lip) == 1 and "status" not in lip[0], lip)
    check("one on-screen row is judged",
          len(text) == 1 and text[0]["status"] == FT.UNAVAILABLE, text)


@patch("lipsync_evidence.check_plan",
       new=lambda *_a, **_k: {"pass": True, "evidence": {}})
@patch.object(A, "lipsync_gate", new=lambda *_a, **_k: None)
def test_receipt_names_the_missing_reader(tmp):
    """The dry-run receipt carries the UNAVAILABLE row and its warning."""
    for name in ("shot1.mp4", "b.mp4"):
        open(os.path.join(tmp, name), "wb").close()
    tl = _write_tl(tmp, [{"src": "shot1.mp4", "dur": 5.0,
                          "on_screen_text": "GRAND OPENING"},
                         {"src": "b.mp4", "dur": 6.0}])
    rec = A.assemble(tl, os.path.join(tmp, "out.mp4"), dry_run=True)
    check("the dry run itself still passes the gate",
          rec["outcome"] == "ok" and rec["reason_code"] == "DRY_RUN",
          (rec.get("outcome"), rec.get("reason_code")))
    rows = [r for r in rec["evidence"].get("frame_text") or []
            if r.get("check") == "onscreen_text"]
    check("the receipt carries the on-screen row", len(rows) == 1, rows)
    check("the row says UNAVAILABLE, not PASS",
          rows and rows[0]["status"] == FT.UNAVAILABLE
          and rows[0]["reason_code"] == OCR_UNAVAILABLE, rows)
    warns = rec.get("warnings") or []
    check("the receipt warns about the missing reader",
          any(w.get("code") == OCR_UNAVAILABLE for w in warns), warns)
    check("the warning names the clip it could not read",
          any("shot1.mp4" in w.get("detail", "") for w in warns), warns)


# --------------------------------------------------------------- S75-024 ----


def test_lane_sizing_uses_the_runs_bound_builder(tmp):
    """lane_size.size() is told the bound builder's runtime and route."""
    try:
        from choice_card.intake_card import ai_models as AM
    except ImportError as exc:                      # pragma: no cover
        check("ai_models is importable", False, exc)
        return
    run_dir = os.path.join(tmp, "run")
    bound = AM.bind_roles(run_dir, "ollama/kimi-k2.6",
                          "openrouter/z-ai/glm-5.3")
    check("the run bound its builder", bound.get("ok") is True, bound)

    check("the assembler reads the run's bound builder",
          A._run_bound_builder(run_dir) == ("claude-nine", "ollama"),
          A._run_bound_builder(run_dir))
    check("a run with no binding invents no route",
          A._run_bound_builder(os.path.join(tmp, "unbound")) == (None, None),
          A._run_bound_builder(os.path.join(tmp, "unbound")))

    calls = []
    fake = types.ModuleType("lane_size")

    def _size(runtime, provider, ollama_plan=None, units=999, **_kw):
        calls.append((runtime, provider, units))
        return {"ffmpeg_threads": 3}

    fake.size = _size
    had = "lane_size" in sys.modules
    saved = sys.modules.get("lane_size")
    sys.modules["lane_size"] = fake
    try:
        threads, _nice, _timeout = A.size_ffmpeg(60, 1920, 1080,
                                                 run_dir=run_dir)
        check("lane_size's own threads value is used", threads == 3, threads)
        check("lane_size is called with the run's bound builder",
              calls == [("claude-nine", "ollama", 999)], calls)
        check("the old literals are gone",
              all("claude-code" not in " ".join(str(c)) for c in calls), calls)
        A.size_ffmpeg(60, 1920, 1080)
        check("an unbound run passes no invented route",
              calls[-1] == (None, None, 999), calls[-1])
    finally:
        if had:
            sys.modules["lane_size"] = saved
        else:
            sys.modules.pop("lane_size", None)


def main():
    tmp_root = tempfile.mkdtemp(prefix="s75-045-tests-")
    try:
        test_no_reader_is_unavailable_never_pass()
        test_planned_text_shapes()
        test_wrong_text_fails()
        test_right_text_passes()
        test_lipsync_rows_keep_the_f9_shape()
        test_receipt_names_the_missing_reader(tmp_root)
        test_lane_sizing_uses_the_runs_bound_builder(tmp_root)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    print("%s" % ("%d check(s) failed" % len(FAILS) if FAILS
                  else "all S75-045 / S75-024 checks passed"))
    return 1 if FAILS else 0


def test_suite_checks_pass():
    assert not FAILS, FAILS


if __name__ == "__main__":
    sys.exit(main())
