#!/usr/bin/env python3
"""U9-t3: caption burn correctness (owner decision D16 / plan section 6.5).

What the owner ordered, as checks on ``final_assembler/captions_burn.py``:

  * ON BY DEFAULT, one line at a time, white rounded box, black text;
  * 9:16 sits ABOVE the bottom 20% of the frame (platform buttons), 16:9
    uses the lower third;
  * timing comes from MEASURED cues only -- without them the plan says
    "unavailable" and no clock is invented (F18's rule);
  * a measured cue set produces a valid SRT (D16 delivers an SRT);
  * the plan is DATA: a render pass burns it, this call never claims it did;
  * every refusal is fail-closed with a reason_code, never a silent pass.

Checks:
  (a) style geometry on both orientations, defaults and pins;
  (b) SRT shape: numbering, HH:MM:SS,mmm, comma decimal, cue text verbatim;
  (c) build_plan: lines verbatim, one_line_at_a_time, timing/srt state;
  (d) bad cues refuse instead of half-planning;
  (e) the CLI prints a receipt and exits 0/1 honestly.

stdlib only, zero network, zero paid calls, no ffmpeg.

Run: python3 core/final_assembler/test_caption_burn_u9t.py
"""
from __future__ import annotations

import importlib
import io
import json
import os
import re
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

FAILS = []


def check(name, cond, detail=""):
    detail = detail if isinstance(detail, str) else repr(detail)
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        " (%s)" % detail if not cond else ""))
    if not cond:
        FAILS.append(name)
        # Under pytest a printed FAIL would be a silent green: fail there too.
        if "pytest" in sys.modules:
            import pytest
            pytest.fail("%s (%s)" % (name, detail), pytrace=False)


def _cb():
    try:
        return importlib.import_module("final_assembler.captions_burn")
    except ImportError:
        return importlib.import_module("captions_burn")


EXCERPT = ["She kept the kitchn spotless", "for thirty years."]
CUES = [{"text": EXCERPT[0], "start": 0.0, "end": 2.4},
        {"text": EXCERPT[1], "start": 2.5, "end": 4.75}]


def test_style_look_and_safe_area():
    CB = _cb()

    # 9:16: cleared ABOVE the bottom 20% + the edge margin.
    portrait = CB.caption_style(1080, 1920)
    check("9:16 geometry is chosen from the frame",
          portrait.get("orientation") == "9:16", portrait.get("orientation"))
    check("9:16 clears the bottom 20% (platform buttons)",
          portrait.get("bottom_margin_px") == 1920 * 0.20 + 24,
          portrait.get("bottom_margin_px"))
    check("16:9 uses the lower third",
          CB.caption_style(1920, 1080).get("bottom_margin_px") == 1080 * 0.10
          + 24, CB.caption_style(1920, 1080).get("bottom_margin_px"))
    check("an explicit 9:16 pin beats the auto-orientation",
          CB.caption_style(1920, 1080, orientation="9:16")
          .get("orientation") == "9:16",
          CB.caption_style(1920, 1080, orientation="9:16"))
    check("an unknown orientation falls back to geometry, never crashes",
          CB.caption_style(1080, 1920, orientation="4:5")
          .get("orientation") == "9:16",
          CB.caption_style(1080, 1920, orientation="4:5"))

    for label, st in (("portrait", portrait),
                      ("landscape", CB.caption_style(1920, 1080))):
        check("%s: white rounded box, black text (D16)" % label,
              st.get("box") == "rounded"
              and st.get("box_colour") == "#ffffff"
              and st.get("font_colour") == "#000000", st)
        check("%s: one line at a time" % label,
              st.get("one_line_at_a_time") is True, st)
        check("%s: captions ON by default" % label,
              st.get("enabled") is True, st)
    check("enabled can be turned off (a caption-free master)",
          CB.caption_style(1080, 1920, enabled=False).get("enabled") is False,
          CB.caption_style(1080, 1920, enabled=False))


def test_srt_is_valid_from_measured_cues():
    CB = _cb()
    srt = CB.build_srt(CUES)
    check("SRT ends with exactly one trailing newline",
          srt.endswith("\n") and not srt.endswith("\n\n"), repr(srt[-4:]))
    blocks = [b for b in srt.split("\n\n") if b.strip()]
    check("one SRT block per cue", len(blocks) == len(CUES), len(blocks))
    stamp = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}$")
    for i, (cue, block) in enumerate(zip(CUES, blocks), 1):
        lines = block.split("\n")
        check("block %d is numbered in order" % i,
              lines[0] == str(i), lines[0])
        check("block %d uses the SRT clock (comma decimal)" % i,
              bool(stamp.match(lines[1])), lines[1])
        check("block %d carries the cue text verbatim" % i,
              [l for l in lines[2:] if l != ""] == [cue["text"]],
              lines[2:])
    expected = ("00:00:00,000 --> 00:00:02,400" in srt
                and "00:00:02,500 --> 00:00:04,750" in srt)
    check("the cue milliseconds are exact (2.400s and 4.750s)",
          expected, srt)

    # A zero window and an unsorted set are not measured windows.
    for label, cues in (("a cue that ends before it starts",
                         [{"text": "x", "start": 5.0, "end": 1.0}]),
                        ("a cue with no window",
                         [{"text": "x"}]),
                        ("cues out of time order",
                         [{"text": "a", "start": 3.0, "end": 4.0},
                          {"text": "b", "start": 1.0, "end": 2.0}]),
                        ("no cues at all", [])):
        try:
            CB.build_srt(cues)
            check("%s is refused" % label, False, "no raise")
        except ValueError as exc:
            check("%s is refused fail-closed" % label,
                  "CAPTION_CUES_INVALID" in str(exc), str(exc))


def test_plan_is_data_not_a_claim():
    CB = _cb()
    tmp = tempfile.mkdtemp(prefix="u9t-burn-")
    try:
        srt_path = os.path.join(tmp, "excerpt.srt")
        plan, why = CB.build_plan(EXCERPT, provenance="provided",
                                  cues=CUES, srt_path=srt_path)
        check("measured cues plan cleanly", why is None, why)
        check("the plan carries the lines verbatim",
              plan.get("lines") == EXCERPT, plan.get("lines"))
        check("the plan is one line at a time",
              plan.get("one_line_at_a_time") is True, plan)
        check("the plan says measured, not invented",
              plan.get("timing") == "measured"
              and plan.get("cue_count") == len(CUES),
              (plan.get("timing"), plan.get("cue_count")))
        check("the SRT rides the plan",
              isinstance(plan.get("srt"), str) and "-->" in plan["srt"],
              repr(plan.get("srt"))[:60])
        check("the SRT file is written only because srt_path was given",
              os.path.isfile(srt_path)
              and open(srt_path, encoding="utf-8").read() == plan["srt"],
              srt_path)
        check("the plan is data-only: never a video-model payload",
              plan.get("data_only") is True
              and plan.get("to_video_model") is False,
              (plan.get("data_only"), plan.get("to_video_model")))
        check("the plan carries the hook U11 names",
              plan.get("hook") ==
              "final_assembler.captions_burn.overlay_excerpt",
              plan.get("hook"))

        # No cues -> no timing, no SRT, no invented clock.
        plan2, why2 = CB.build_plan(EXCERPT, provenance="provided")
        check("without cues the plan times nothing",
              why2 is None and plan2.get("timing") == "unavailable"
              and plan2.get("srt") is None
              and plan2.get("cue_count") == 0,
              (why2, plan2.get("timing"), plan2.get("srt")))
        check("the receipt with no cues still carries the lines",
              plan2.get("lines") == EXCERPT, plan2.get("lines"))

        # Bad lines are refused before anything is planned.
        for label, arg in (("an empty line list", []),
                           ("a list with a blank", ["ok", "  "]),
                           ("a non-list", "nope")):
            try:
                CB.build_plan(arg)
                check("%s is refused by build_plan" % label, False,
                      "no raise")
            except ValueError as exc:
                check("%s is refused by build_plan" % label,
                      "OVERLAY_NO_LINES" in str(exc), str(exc))

        # Bad cues half-plan NOTHING: refused with the cue reason.
        plan3, why3 = CB.build_plan(EXCERPT, cues=[{"text": "x", "start": 9.0,
                                                    "end": 1.0}])
        check("bad cues refuse without writing an SRT",
              why3 is not None and "CAPTION_CUES_INVALID" in why3
              and plan3.get("srt") is None,
              (why3, plan3.get("srt")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_overlay_receipt_never_claims_a_burn():
    CB = _cb()
    out = CB.overlay_excerpt(EXCERPT, provenance="provided", cues=CUES)
    check("measured cues give a measured receipt",
          out.get("ok") is True and out.get("timing") == "measured",
          (out.get("ok"), out.get("timing")))
    check("even with cues this call only plans",
          out.get("planned") is True and out.get("burned") is False,
          (out.get("planned"), out.get("burned")))
    check("the receipt embeds the same plan a render pass reads",
          isinstance(out.get("plan"), dict)
          and out["plan"].get("lines") == EXCERPT,
          type(out.get("plan")).__name__)
    check("the receipt is JSON-serialisable",
          bool(json.dumps(out)), "json")


def test_cli_receipt_is_honest():
    CB = _cb()
    buf = io.StringIO()
    saved = sys.stdout
    sys.stdout = buf
    try:
        rc_ok = CB.main(["--lines", json.dumps(EXCERPT),
                         "--provenance", "provided"])
        rc_bad = CB.main(["--lines", '"not a list"'])
    finally:
        sys.stdout = saved
    out = buf.getvalue()
    # Parse each printed JSON object robustly (two receipts, two objects).
    objs, depth, start = [], 0, None
    for i, ch in enumerate(out):
        if ch == "{" and depth == 0:
            start = i
            depth = 1
        elif ch == "{" and depth:
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0:
                objs.append(json.loads(out[start:i + 1]))
    check("the CLI exits 0 on a good excerpt", rc_ok == 0, rc_ok)
    check("the CLI exits 1 on a refused excerpt", rc_bad == 1, rc_bad)
    check("the CLI prints a JSON receipt", len(objs) == 2, len(objs))
    if len(objs) == 2:
        check("the good receipt reports ok and no burn",
              objs[0].get("ok") is True and objs[0].get("burned") is False,
              objs[0])
        check("the refused receipt names OVERLAY_BAD_INPUT",
              objs[1].get("ok") is False
              and objs[1].get("reason_code") == "OVERLAY_BAD_INPUT",
              objs[1])


def main():
    for fn in (test_style_look_and_safe_area,
               test_srt_is_valid_from_measured_cues,
               test_plan_is_data_not_a_claim,
               test_overlay_receipt_never_claims_a_burn,
               test_cli_receipt_is_honest):
        try:
            fn()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % getattr(fn, "__name__", "test"), False,
                  "%s: %s" % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all U9-t3 caption burn checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())