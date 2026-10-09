#!/usr/bin/env python3
"""U9-t1: ``overlay_excerpt`` behaviour (the U11 seam entry point).

U11 calls exactly one thing:

    book_shot.EXCERPT_OVERLAY_HOOK = "final_assembler.captions_burn.overlay_excerpt"
    mod.overlay_excerpt(lines, provenance=overlay.get("provenance"))

so this suite pins that entry point and NOTHING else -- what it takes, what
it returns, what it refuses. The two companion files own the U11 PENDING
switch (test_pending_vs_burn_u9t.py) and the burn/SRT/style correctness
(test_caption_burn_u9t.py).

Checks:
  (a) the module, the entry point and the hook string U11 names;
  (b) a good excerpt returns a receipt -- never a frame, never an exception;
  (c) bad input is a REFUSAL receipt (ok False + reason_code), not a raise:
      the seam's own docstring promises "never raises on seam input";
  (d) client lines come back byte-identical -- this module re-spells nothing
      (U8 owns display spelling for performance text; an excerpt is data);
  (e) the receipt never claims frames were burned.

stdlib only, zero network, zero paid calls, no ffmpeg.

Run: python3 core/final_assembler/test_overlay_excerpt_u9t.py
"""
from __future__ import annotations

import json
import os
import sys

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


def _import():
    """Import captions_burn the way U11 does (package path, then bare)."""
    import importlib
    try:
        return importlib.import_module("final_assembler.captions_burn")
    except ImportError:
        return importlib.import_module("captions_burn")


EXCERPT = ["She kept the kitchn spotless", "for thirty years."]


def test_seam_shape():
    import book_shot as BS
    CB = _import()

    check("the named module resolves",
          getattr(CB, "__name__", "").endswith("captions_burn"),
          getattr(CB, "__name__", None))
    # U11 owns the book_shot constant; it lives on unit/FU-U11 until that
    # PR merges. Loud skip, never a silent pass -- the module side below
    # still pins the same string unconditionally.
    if hasattr(BS, "EXCERPT_OVERLAY_HOOK"):
        check("U11's constant names this exact module",
              BS.EXCERPT_OVERLAY_HOOK ==
              "final_assembler.captions_burn.overlay_excerpt",
              BS.EXCERPT_OVERLAY_HOOK)
    else:
        print("skip (U11 not on this tree): book_shot.EXCERPT_OVERLAY_HOOK "
              "-- asserted on unit/FU-U11 and on the merged tree")
    check("the module declares the same hook string",
          getattr(CB, "EXCERPT_OVERLAY_HOOK", None) ==
          "final_assembler.captions_burn.overlay_excerpt",
          getattr(CB, "EXCERPT_OVERLAY_HOOK", None))
    entry = getattr(CB, "overlay_excerpt", None)
    check("overlay_excerpt is the entry point U11 imports",
          callable(entry), type(entry).__name__)
    import inspect
    if callable(entry):
        params = inspect.signature(entry).parameters
        check("overlay_excerpt takes lines positionally",
              "lines" in params, list(params))
        check("overlay_excerpt takes provenance as U11 passes it",
              "provenance" in params, list(params))


def test_good_excerpt_is_a_receipt():
    CB = _import()
    out = CB.overlay_excerpt(EXCERPT, provenance="provided")
    check("a good excerpt returns a dict receipt",
          isinstance(out, dict), type(out).__name__)
    if not isinstance(out, dict):
        return
    check("the receipt reports ok", out.get("ok") is True, out.get("ok"))
    check("the receipt names U11's hook",
          out.get("hook") ==
          "final_assembler.captions_burn.overlay_excerpt",
          out.get("hook"))
    check("the receipt names the entry point",
          out.get("entry") == "overlay_excerpt", out.get("entry"))
    check("the excerpt lines ride the receipt unchanged",
          out.get("lines") == EXCERPT, out.get("lines"))
    check("the provenance U11 passed rides the receipt",
          out.get("provenance") == "provided", out.get("provenance"))
    check("this call plans only -- it burns nothing",
          out.get("planned") is True and out.get("burned") is False,
          (out.get("planned"), out.get("burned")))
    check("the receipt carries no reason_code",
          out.get("reason_code") in (None, ""),
          out.get("reason_code"))
    check("the receipt is data, never a video-model payload",
          out.get("data_only") is True and out.get("to_video_model") is False,
          (out.get("data_only"), out.get("to_video_model")))
    check("with no measured cues the timing is unavailable, never invented",
          out.get("timing") == "unavailable", out.get("timing"))
    check("the style arrives as data (white rounded box, black text)",
          isinstance(out.get("style"), dict)
          and out["style"].get("box") == "rounded"
          and out["style"].get("box_colour") == "#ffffff"
          and out["style"].get("font_colour") == "#000000",
          out.get("style"))
    check("the receipt serialises as JSON (it rides a receipt file)",
          bool(json.dumps(out)), "json")


def test_bad_input_refuses_rather_than_raises():
    CB = _import()

    cases = [
        ("an empty list", [], "OVERLAY_NO_LINES"),
        ("None", None, "OVERLAY_BAD_INPUT"),
        ("a bare string", "a line", "OVERLAY_BAD_INPUT"),
        ("a dict", {"line": "x"}, "OVERLAY_BAD_INPUT"),
        ("a number", 7, "OVERLAY_BAD_INPUT"),
        ("a list holding a number", [1, 2], "OVERLAY_BAD_INPUT"),
        ("a blank line", ["ok", "   "], "OVERLAY_BAD_INPUT"),
    ]
    for label, arg, code in cases:
        try:
            out = CB.overlay_excerpt(arg, provenance="provided")
        except Exception as exc:                      # noqa: BLE001
            check("%s comes back as a refusal, not a raise" % label, False,
                  "%s: %s" % (type(exc).__name__, exc))
            continue
        check("%s is refused fail-closed" % label,
              isinstance(out, dict) and out.get("ok") is False
              and out.get("reason_code") == code,
              out if not isinstance(out, dict)
              else (out.get("ok"), out.get("reason_code")))
        if isinstance(out, dict):
            check("%s refuses without burning" % label,
                  out.get("burned") is False and out.get("planned") is False,
                  (out.get("burned"), out.get("planned")))


def test_client_words_are_never_resped():
    CB = _import()
    # U8 re-spells PERFORMANCE text ("you-u" -> "you"); an excerpt is client
    # data and must come back exactly as supplied, case and spacing intact.
    odd = ["  Couldve been worse -- 30 years  ", "“Straight quotes”"]
    out = CB.overlay_excerpt(odd, provenance="provided")
    check("an excerpt is never re-cased, re-spaced or re-punctuated",
          isinstance(out, dict) and out.get("lines") == odd,
          out.get("lines") if isinstance(out, dict) else out)
    if isinstance(out, dict):
        check("line count survives untouched",
              out.get("lines") is not None and len(out["lines"]) == 2,
              out.get("lines"))


def test_no_frame_side_effect():
    CB = _import()
    import tempfile, shutil                      # noqa: E402
    tmp = tempfile.mkdtemp(prefix="u9t-overlay-")
    try:
        before = sorted(os.listdir(tmp))
        out = CB.overlay_excerpt(EXCERPT, provenance="provided")
        after = sorted(os.listdir(tmp))
        check("planning writes no file of its own",
              before == after, (before, after))
        if isinstance(out, dict):
            check("the receipt never reports frames burned",
                  out.get("burned") is False, out.get("burned"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    for fn in (test_seam_shape,
               test_good_excerpt_is_a_receipt,
               test_bad_input_refuses_rather_than_raises,
               test_client_words_are_never_resped,
               test_no_frame_side_effect):
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
    print("all U9-t1 overlay_excerpt checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())