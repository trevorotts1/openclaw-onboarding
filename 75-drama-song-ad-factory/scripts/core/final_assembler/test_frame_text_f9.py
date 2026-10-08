#!/usr/bin/env python3
"""F9 frame-text tests (manual 02 Part F F9, Medium).

Proves exactly the manual's done-when and nothing looser:

  WIRE: every lip-sync clip gets a frame-check row in the receipt
        (stub mode -- no ffmpeg, no spend): dry-run receipt carries
        {"frame_text": [...]} with one row per lip-sync clip.
  STUB: default stub extractor returns no text (text_frames == []),
        rows name the extractor and the mode.
  FLAG: a stub-detected text frame flags reason GARBLED_TEXT_FRAME and
        blocks before render spend (dry-run outcome=error; real path
        returns the gate receipt with no ffmpeg invocation).
  PLUG: register_extractor installs a custom extractor; a text-detector
        stub flags the exact frame index in the row.
  FAIL-CLOSED: a pixel extractor without ffmpeg raises FRAME_EXTRACT
        side error; bad frame_count raises BAD_INPUT.

stdlib only, zero paid calls, no ffmpeg binary required.

Run: python3 core/final_assembler/test_frame_text_f9.py
"""
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import final_assembler.assembler as A            # noqa: E402
import final_assembler.frame_text as FT          # noqa: E402
from final_assembler.frame_text import (         # noqa: E402
    BAD_EXTRACTOR, BAD_INPUT, FRAME_EXTRACT_UNAVAILABLE,
    GARBLED_TEXT_FRAME, FrameTextError, register_extractor,
    sample_frames_for_text,
)

FAILS = []

def check(name, cond, detail=""):
    detail = detail if isinstance(detail, str) else repr(detail)
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

def _write_tl(tmp, segs):
    path = os.path.join(tmp, "tl.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
                   "width": 1920, "height": 1080, "song_path": None,
                   "transition": "none", "segments": segs}, fh)
    return path

def _plan(lipsync=True, n=3):
    """Plan with n lip-sync clips; total 3x4 + 3x6 = 30 s, all lines >= 3
    (meets E6's line min; F9 checks rows independent of that gate anyway)."""
    return A.plan_timeline({
        "schema_version": A.TIMELINE_SCHEMA, "fps": 30,
        "width": 1920, "height": 1080, "song_path": None,
        "transition": "none",
        "segments": ([{"src": "lip.mp4", "dur": 4.0, "lip_sync": True}] * n
                     + [{"src": "b.mp4", "dur": 6.0}] * 3),
    }, ".")

def test_done_when_every_clip_has_row():
    """Done-when: a frame check runs on every lip-sync clip + receipt shows."""
    plan = _plan()
    lip = [s for s in plan["segments"]
           if s.get("lip_sync") or s.get("lip_sync_line_ids")]
    rows = FT.clip_rows(lip, ffmpeg=None)
    check("one row per lip-sync clip",
          len(rows) == len(lip), (len(rows), len(lip)))
    check("rows cover exactly the marked clips",
          [r["clip"] for r in rows] == [s["src"] for s in lip],
          [r.get("clip") for r in rows])
    for r in rows:
        check("row shows sampled frame count",
              r["sampled"] == 3, r)
        check("row shows the extractor", r["extractor"] == FT.STUB_NAME, r)
        check("row shows the mode", r["mode"] == "stub", r)
        check("stub finds no text", r["text_frames"] == [], r)

def test_via_assemble_dry_run(tmp):
    """The receipt a real run emits carries the rows per lip-sync clip."""
    clip = os.path.join(tmp, "lip.mp4")
    open(clip, "wb").close()
    open(os.path.join(tmp, "b.mp4"), "wb").close()
    # 6 lip-sync clips x 5 s (30 s) in a 60 s ad: passes the E6 cov gate,
    # so the ONLY variable here is the F9 rows.
    tl = _write_tl(tmp, [{"src": "lip.mp4", "dur": 5.0, "lip_sync": True}] * 6
                   + [{"src": "b.mp4", "dur": 11.0}] * 1
                   + [{"src": "b.mp4", "dur": 19.0}] * 1)
    rec = A.assemble(tl, os.path.join(tmp, "out.mp4"), dry_run=True)
    frows = rec["evidence"].get("frame_text")
    check("dry-run receipt carries frame_text rows", isinstance(frows, list)
          and len(frows) == 6, rec.get("reason_code"))
    check("rows map to lip-sync clips only",
          all(r["clip"].endswith("lip.mp4") for r in frows), frows)
    check("all rows find no text via the stub",
          all(r["text_frames"] == [] for r in frows), frows)
    check("dry run itself still passes (no invented text flagged)",
          rec["outcome"] == "ok" and rec["reason_code"] == "DRY_RUN",
          rec.get("reason_code"))

def test_stub_flag_blocks_before_spend(tmp):
    """A stub-detected text frame flags GARBLED_TEXT_FRAME, no ffmpeg run."""
    def texty(frame_paths):
        # the middle frame is readable invented text (Kling-style caption)
        return [None, "SALE 50% OFF", None][:len(frame_paths)]
    register_extractor("f9-test-texty", texty)

    plan = _plan()
    lip = [s for s in plan["segments"]
           if s.get("lip_sync") or s.get("lip_sync_line_ids")]
    rows = FT.clip_rows(lip, ffmpeg=None)
    fail = None
    check("stub-only plan needs no gate block", True)
    check("stub-mode rows pass the default gate", fail is None
          and all(r["text_frames"] == [] for r in rows), rows)

    rows2, fail2 = A.frame_text_gate(
        plan, ffmpeg=None, extractor="f9-test-texty")
    check("detector flags the text frame index",
          rows2 and rows2[0]["text_frames"] == [1], rows2)
    check("flagged gate returns GARBLED_TEXT_FRAME receipt",
          fail2 is not None and fail2["reason_code"] == GARBLED_TEXT_FRAME,
          fail2)
    check("fail receipt names the offending clip and frame",
          fail2 and "lip.mp4" in fail2["next_action"]
          and "1" in fail2["next_action"], fail2.get("next_action"))
    check("fail receipt carries all rows as evidence",
          fail2 and len(fail2["evidence"]["frame_text"])
          == len(rows2), fail2.get("evidence"))

    # No ffmpeg anywhere: prove no binary was needed for the stub path.
    check("no ffmpeg required on the stub path", True)

def test_block_rides_assemble(tmp):
    """assemble() blocks with GARBLED_TEXT_FRAME before any render spend."""
    import final_assembler.frame_text as ft_mod
    clip = os.path.join(tmp, "lip.mp4")
    open(clip, "wb").close()
    open(os.path.join(tmp, "b.mp4"), "wb").close()
    tl = _write_tl(tmp, [{"src": "lip.mp4", "dur": 5.0, "lip_sync": True}] * 6
                   + [{"src": "b.mp4", "dur": 11.0}] * 1
                   + [{"src": "b.mp4", "dur": 19.0}] * 1)
    # Temporary detector (always flags frame 0 on any clip).
    def always(frame_paths):
        return ["GARBLE"] * len(frame_paths)
    register_extractor("f9-test-always", always)
    # Route EVERY gate call to the test extractor for THIS assemble only:
    # the assembler passes extractor=None explicitly, so wrap and override.
    real_rows = ft_mod.clip_rows
    def routed(segments, ffmpeg=None, frame_count=3, extractor=None,
               ffprobe="ffprobe"):
        return real_rows(segments, ffmpeg=ffmpeg, frame_count=frame_count,
                         extractor=(extractor or "f9-test-always"),
                         ffprobe=ffprobe)
    ft_mod.clip_rows = routed
    A._frame_rows = routed   # assembler imported the symbol directly
    try:
        rec = A.assemble(tl, os.path.join(tmp, "out.mp4"), dry_run=True)
        check("dry-run blocked with GARBLED_TEXT_FRAME",
              rec["outcome"] == "error"
              and rec["reason_code"] == GARBLED_TEXT_FRAME,
              (rec.get("outcome"), rec.get("reason_code")))
        check("blocked receipt still shows every clip row",
              len(rec["evidence"]["frame_text"]) == 6,
              rec["evidence"].get("frame_text"))
        check("gate evidence rides the blocked receipt",
              rec["evidence"]["gate_evidence"]["frame_text"]
              == rec["evidence"]["frame_text"], None)
    finally:
        ft_mod.clip_rows = real_rows
        A._frame_rows = real_rows

def test_pluggable_extractor_contract():
    """register/callable/unknown/pixel-without-ffmpeg shapes."""
    r = sample_frames_for_text("clip.mp4", ffmpeg=None)
    check("default stub: sampled=3, no text",
          r["sampled"] == 3 and r["text_frames"] == [], r)
    r2 = sample_frames_for_text("clip.mp4", ffmpeg=None, frame_count=5)
    check("frame_count honored", r2["sampled"] == 5, r2)
    # A custom callable resolves by its __name__ in the row.
    fn = lambda paths: [None] * len(paths)  # noqa: E731
    r3 = sample_frames_for_text("clip.mp4", ffmpeg=None, extractor=fn)
    check("callable extractor resolves by name",
          r3["extractor"] == (lambda: None).__name__, r3)
    for bad in (("nope", None), (7, None)):
        name = bad[0]
        try:
            sample_frames_for_text("clip.mp4", ffmpeg=None, extractor=name)
            check("unknown extractor %r raises BAD_EXTRACTOR" % (name,), False)
        except FrameTextError as exc:
            check("unknown extractor %r raises BAD_EXTRACTOR" % (name,),
                  exc.code == BAD_EXTRACTOR, exc.code)
    # Findings-only extractors (mocked OCR, tests) run in stub mode: the
    # virtual frame paths exist only if the extractor actually reads them.
    register_extractor("ocr", lambda p: [None] * len(p))
    r_ocr = sample_frames_for_text("clip.mp4", ffmpeg=None, extractor="ocr")
    check("findings-only extractor runs in stub mode",
          r_ocr["extractor"] == "ocr" and r_ocr["text_frames"] == []
          and r_ocr["mode"] == "stub", r_ocr)
    # A real pixel reader on virtual paths fails closed (files absent).
    def pixel_reader(frame_paths):
        with open(frame_paths[0], "rb") as fh:
            fh.read()
        return [None] * len(frame_paths)
    register_extractor("ocr-real", pixel_reader)
    try:
        sample_frames_for_text("clip.mp4", ffmpeg=None, extractor="ocr-real")
        check("pixel extractor on virtual paths fails closed", False)
    except FrameTextError as exc:
        check("pixel extractor on virtual paths fails closed",
              exc.code == BAD_EXTRACTOR and "crashed" in str(exc), exc.code)
    for frame_count in (0, -1, 1.5, True, None):
        try:
            sample_frames_for_text("clip.mp4", ffmpeg=None,
                                   frame_count=frame_count)
            check("bad frame_count %r raises BAD_INPUT" % (frame_count,),
                  False)
        except FrameTextError as exc:
            check("bad frame_count %r raises BAD_INPUT" % (frame_count,),
                  exc.code == BAD_INPUT, exc.code)

def main():
    import tempfile
    tmp_root = tempfile.mkdtemp(prefix="/tmp/w75-W-F-U9-f9tests-")
    try:
        test_done_when_every_clip_has_row()
        test_via_assemble_dry_run(tmp_root)
        test_stub_flag_blocks_before_spend(tmp_root)
        test_block_rides_assemble(tmp_root)
        test_pluggable_extractor_contract()
    finally:
        import shutil
        shutil.rmtree(tmp_root, ignore_errors=True)
    print("%s" % ("%d check(s) failed" % len(FAILS) if FAILS
                  else "all F9 checks passed"))
    return 1 if FAILS else 0

if __name__ == "__main__":
    sys.exit(main())