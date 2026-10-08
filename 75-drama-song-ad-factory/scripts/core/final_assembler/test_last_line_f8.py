#!/usr/bin/env python3
"""F8 tests: the last line lands before the end card (manual Part F F8).

Proves EXACTLY the manual's done-when and the unit contract:
  * a sung/spoken line whose END lands after the end card's start time
    on the timeline fails: ["LAST_LINE_OVER_ENDCARD"]; assemble() itself
    refuses the render (LAST_LINE_OVER_ENDCARD receipt, before spend);
  * a line ending before (or exactly at) the card start passes: [];
  * NO "endcard_start_s" key on the timeline passes: [] — absence means
    the card is not checked and old timelines assemble unchanged;
  * load_timeline validates the optional keys fail-closed when present
    (bad endcard_start_s / bad lines windows), and accepts both absent;
  * endcard_start_s present with no lines is fail-closed UNKNOWN.

stdlib only, zero paid calls, no ffmpeg (dry_run receipts), $0.

Run: python3 core/final_assembler/test_last_line_f8.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import final_assembler.assembler as A   # noqa: E402

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _tl(lines=None, endcard=True):
    # 4 segments (3 marked lip_sync so the E6 coverage gate passes on the
    # fixture; 12% of 19.5 s = 2.34 s < 7.5 s marked, 3 lines minimum);
    # the end card starts at 15 s inside the closing clip.
    tl = {"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
          "width": 640, "height": 360, "song_path": None,
          "transition": "none",
          "segments": [{"src": "a.mp4", "dur": 12.0},
                       {"src": "b.mp4", "dur": 2.5, "lip_sync": True},
                       {"src": "c.mp4", "dur": 2.5, "lip_sync": True},
                       {"src": "d.mp4", "dur": 2.5, "lip_sync": True}]}
    if endcard:
        tl["endcard_start_s"] = 15.0        # card starts at 15 s
    if lines is not None:
        tl["lines"] = lines
    return tl


def _plan(lines=None, endcard=True):
    return A.plan_timeline(_tl(lines, endcard), ".")


LINE_BEFORE = [{"line_id": "l1", "start_s": 10.0, "end_s": 14.0}]
LINE_AT = [{"line_id": "l1", "start_s": 10.0, "end_s": 15.0}]
LINE_OVER = [{"line_id": "l1", "start_s": 10.0, "end_s": 16.5},
             {"line_id": "l2", "start_s": 5.0, "end_s": 9.0}]


def test_over_line_fails():
    reasons = A.check_last_line_before_endcard(_plan(LINE_OVER))
    check("line ending after endcard_start_s fails",
          reasons == ["LAST_LINE_OVER_ENDCARD"], "got %r" % (reasons,))

def test_before_line_passes():
    check("line ending before endcard_start_s passes",
          A.check_last_line_before_endcard(_plan(LINE_BEFORE)) == [])
    # exact boundary: end AT the card start is before, not over
    check("line ending exactly at endcard_start_s passes",
          A.check_last_line_before_endcard(_plan(LINE_AT)) == [])

def test_no_endcard_key_not_checked():
    reasons = A.check_last_line_before_endcard(_plan(LINE_OVER,
                                                     endcard=False))
    check("no endcard key = not checked (absence passes)",
          reasons == [], "got %r" % (reasons,))

def test_loader_validates_optional_keys():
    # key present: valid values are kept
    tl = _tl(LINE_BEFORE)
    check("load_timeline keeps a valid endcard_start_s",
          A.load_timeline(_write(tl))["endcard_start_s"] == 15.0)
    # key present: bad values are refused, fail closed
    for bad in (0, -1, "15", True, float("nan")):
        tl["endcard_start_s"] = bad
        try:
            A.load_timeline(_write(tl))
            check("bad endcard_start_s %r rejected" % (bad,), False)
        except ValueError as exc:
            check("bad endcard_start_s %r rejected" % (bad,),
                  str(exc).startswith("TIMELINE_BAD_ENDCARD"),
                  str(exc))
        tl["endcard_start_s"] = 15.0
    # no key: loads fine (old timelines unchanged)
    check("load_timeline accepts a timeline without the key",
          A.load_timeline(_write(_tl(endcard=False)))
          .get("endcard_start_s") is None)
    # lines validated: unordered window refused, good window kept
    try:
        A.load_timeline(_write(_tl([{"line_id": "x", "start_s": 5.0,
                                     "end_s": 3.0}])))
        check("bad line window rejected", False)
    except ValueError as exc:
        check("bad line window rejected",
              str(exc).startswith("TIMELINE_BAD_LINES"), str(exc))
    check("good lines kept",
          A.load_timeline(_write(_tl(LINE_BEFORE)))["lines"]
          == LINE_BEFORE)

def test_endcard_without_lines_fail_closed():
    try:
        A.check_last_line_before_endcard(_plan(lines=None))
        check("endcard without lines raises LAST_LINE_WINDOW_UNKNOWN",
              False)
    except ValueError as exc:
        check("endcard without lines raises LAST_LINE_WINDOW_UNKNOWN",
              str(exc).startswith("LAST_LINE_WINDOW_UNKNOWN"), str(exc))

def _write(tl):
    if not hasattr(_write, "dir"):
        _write.dir = tempfile.mkdtemp(prefix="last_line_f8_")
        for name in "abcd":
            open(os.path.join(_write.dir, "%s.mp4" % name), "wb").close()
    p = os.path.join(_write.dir, "tl.json")
    import json
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(tl, fh)
    return p


def _assemble_receipt(tl_path, output_name):
    out = os.path.join(os.path.dirname(tl_path), output_name)
    return A.assemble(tl_path, out, dry_run=True), out


def test_assemble_wiring_dry_run():
    d = tempfile.mkdtemp(prefix="last_line_f8_asm_")
    for name in "abcd":
        open(os.path.join(d, "%s.mp4" % name), "wb").close()
    # over: assemble refuses before render spend
    tl = _tl(LINE_OVER)
    p = os.path.join(d, "tl_over.json")
    import json
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(tl, fh)
    rec, _ = _assemble_receipt(p, "out_over.mp4")
    check("assemble refuses an over last line",
          rec.get("outcome") == "error"
          and rec.get("reason_code") == "LAST_LINE_OVER_ENDCARD",
          "%r/%r" % (rec.get("outcome"), rec.get("reason_code")))
    check("receipt names the offending lines",
          rec.get("evidence", {}).get("over")
          and rec["evidence"]["over"][0]["line_id"] == "l1"
          and rec["evidence"]["over"][0]["end_s"] == 16.5,
          "%r" % (rec.get("evidence", {}).get("over"),))
    # before: dry run proceeds (DRY_RUN receipt, plan carries keys)
    tl["lines"] = LINE_BEFORE
    p = os.path.join(d, "tl_before.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(tl, fh)
    rec, _ = _assemble_receipt(p, "out_ok.mp4")
    check("assemble proceeds when the last line clears the card",
          rec.get("outcome") == "ok"
          and rec.get("reason_code") == "DRY_RUN",
          "%r/%r" % (rec.get("outcome"), rec.get("reason_code")))
    check("plan carries endcard_start_s + lines",
          rec.get("evidence", {}).get("plan", {}).get("endcard_start_s")
          == 15.0
          and rec["evidence"]["plan"]["lines"] == LINE_BEFORE)
    # no key: assemble proceeds, gate not checked
    del tl["endcard_start_s"]
    p = os.path.join(d, "tl_none.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(tl, fh)
    rec, _ = _assemble_receipt(p, "out_none.mp4")
    check("assemble without the key proceeds (not checked)",
          rec.get("outcome") == "ok"
          and rec.get("reason_code") == "DRY_RUN",
          "%r/%r" % (rec.get("outcome"), rec.get("reason_code")))


def main():
    for fn in (test_over_line_fails,
               test_before_line_passes,
               test_no_endcard_key_not_checked,
               test_loader_validates_optional_keys,
               test_endcard_without_lines_fail_closed,
               test_assemble_wiring_dry_run):
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
    print("all F8 checks passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())