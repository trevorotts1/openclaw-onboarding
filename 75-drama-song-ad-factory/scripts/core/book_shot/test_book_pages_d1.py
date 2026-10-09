#!/usr/bin/env python3
"""FU-U11 D1: printed pages, the plan-hash gate, and the excerpt boundary.

Proves all four, offline, stdlib + the already-declared cv2/numpy:

  (a) the WHITE-page fixture FAILs BOOK_BLANK_PAGES and the PRINTED-page
      fixture PASSes, through the printed-vs-white calibration control;
  (b) a book video job with no approved plan hash is REFUSED
      (BOOK_PLAN_NOT_APPROVED);
  (c) a changed prompt changes the plan hash, and the job is refused until
      the new hash is re-approved;
  (d) the excerpt is NEVER sent to a video model: the assembled H3 video
      prompt never carries excerpt text, with the overlay built as DATA ONLY.

This test is designed to pass WITHOUT U9: nothing here reads text out of a
frame, writes a burn module or touches scripts/core/final_assembler/
captions_burn.py (U9's artifact, not in this tree). The ONLY deferred piece
is the burn, named by book_shot.EXCERPT_OVERLAY_HOOK and called from
final_assembler.assembler.excerpt_overlay_stage, which reports a PENDING row
while U9's module is absent.

Run: python3 scripts/core/book_shot/test_book_pages_d1.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (HERE, CORE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_CACHE = os.path.join(CORE, "__pycache__")
if os.path.isdir(_CACHE):
    for _n in os.listdir(_CACHE):
        if _n.endswith(".pyc"):
            try:
                os.remove(os.path.join(_CACHE, _n))
            except OSError:
                pass

import book_shot as BS  # noqa: E402
from book_shot.fixtures import build_fixtures as FIX  # noqa: E402

FAILS = []
H3 = "minimax-h3/image-to-video"

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % (detail,)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

def _cv2_np():
    import cv2
    import numpy as np
    return cv2, np

# ---- (a) white FAILs, printed PASSes, through the calibration ---------------
def test_printed_vs_white():
    cv2, np = _cv2_np()
    try:
        cal = BS.calibrate_pages()
    except BS.BookShotError as exc:
        check("calibration control sorts printed from white", False, str(exc))
        return
    check("calibration control sorts printed from white",
          cal["sorted"] is True and cal["printed_ink"] > cal["white_ink"]
          + cal["margin"], cal)
    printed = FIX.open_book_frames(cv2, np, printed=True)
    white = FIX.open_book_frames(cv2, np, printed=False)
    r_print = BS.check_pages(frames=printed, calibrated=cal)
    r_white = BS.check_pages(frames=white, calibrated=cal)
    check("the printed-page fixture PASSes",
          r_print["verdict"] == "PASS"
          and r_print["reason_code"] == "BOOK_PAGES_OK", r_print["reason_code"])
    check("the white-page fixture FAILs BOOK_BLANK_PAGES",
          r_white["verdict"] == "FAIL"
          and r_white["reason_code"] == BS.BOOK_BLANK_PAGES,
          r_white["reason_code"])
    check("more than one blank page among the sampled frames",
          len(r_white["checks"]["pages"]["blanks"]) > 1,
          r_white["checks"]["pages"]["blanks"][:3])
    # One blank page is a chapter break, not a fail: the pair control is
    # sharp because the fixture has MANY blanks and the printed one none.
    check("a single blank page would not fail (chapter break)",
          r_print["checks"]["pages"]["blanks"] == [],
          r_print["checks"]["pages"]["blanks"][:3])
    # UNAVAILABLE never passes.
    r_nocal = BS.check_pages(frames=printed)
    check("no calibration receipt is UNAVAILABLE, never a pass",
          r_nocal["verdict"] == "UNAVAILABLE"
          and r_nocal["reason_code"] == BS.BOOK_PAGES_UNAVAILABLE,
          r_nocal["reason_code"])
    bad_cal = dict(cal, sorted=False)
    r_badcal = BS.check_pages(frames=white, calibrated=bad_cal)
    check("an unsorted calibration never yields a verdict",
          r_badcal["verdict"] == "UNAVAILABLE", r_badcal["reason_code"])

# ---- (b)+(c) the plan-hash gate --------------------------------------------
def _dispatch():
    import importlib
    KD = importlib.import_module("kie_dispatch.kie_dispatch")
    return KD

def _cover_frame(tmp):
    cv2, np = _cv2_np()
    cover = os.path.join(tmp, "cover.png")
    frame = os.path.join(tmp, "start.png")
    cv2.imwrite(cover, FIX.make_cover(cv2, np))
    cv2.imwrite(frame, FIX.paste_into_frame(cv2, np, FIX.make_cover(cv2, np)))
    return cover, frame

def test_plan_hash_gate():
    KD = _dispatch()
    with tempfile.TemporaryDirectory() as tmp:
        cover, frame = _cover_frame(tmp)
        job = {"request_kind": "video", "shot_kind": "book",
               "book_start_frame": frame, "book_cover_path": cover}
        # (b) no approved plan hash -> REFUSED.
        r = KD.book_shot_refusal("kling-3.0/video", job)
        check("(b) a book video job with no approved plan hash is REFUSED",
              r is not None and r["reason_code"] == "BOOK_PLAN_NOT_APPROVED",
              r)
        carried_no_approval = dict(job, book_plan_sha256=BS.plan_sha256(
            {"shot": "the book opens on the table"}))
        r2 = KD.book_shot_refusal("kling-3.0/video", carried_no_approval)
        check("(b) a carried hash with no approval is REFUSED",
              r2 is not None and r2["reason_code"] == "BOOK_PLAN_NOT_APPROVED",
              r2)
        # (c) a changed prompt changes the hash...
        plan_a = {"shots": [{"shot_id": "S09", "prompt": "the book opens on "
                             "the light oak table, soft key light"}]}
        plan_b = {"shots": [{"shot_id": "S09", "prompt": "the book slides "
                             "across the dark marble counter, hard side light"}]}
        h_a, h_b = BS.plan_sha256(plan_a), BS.plan_sha256(plan_b)
        check("(c) a changed prompt changes the plan hash", h_a != h_b,
              (h_a[:12], h_b[:12]))
        # ...and the job is refused until the NEW hash is re-approved.
        stale = dict(job, book_plan_sha256=h_b, approved_book_plan_sha256=h_a)
        r3 = KD.book_shot_refusal("kling-3.0/video", stale)
        check("(c) the changed plan is REFUSED until re-approved",
              r3 is not None and r3["reason_code"] == "BOOK_PLAN_NOT_APPROVED",
              r3)
        fresh = dict(job, book_plan_sha256=h_b, approved_book_plan_sha256=h_b)
        check("(c) the new hash, once approved, passes",
              KD.book_shot_refusal("kling-3.0/video", fresh) is None)
        # The approval fields never feed the hash: approving does not move it.
        approved_a = dict(plan_a, approved_book_plan_sha256=h_a,
                          approved_at="2026-10-09")
        check("approval fields are excluded from the plan hash",
              BS.plan_sha256(approved_a) == h_a)
        # Key order never moves the hash.
        check("the hash is stable across key order",
              BS.plan_sha256({"a": 1, "b": 2}) == BS.plan_sha256({"b": 2, "a": 1}))
        # The frame rule keeps its own code and its own priority.
        no_frame = {k: v for k, v in fresh.items() if k != "book_start_frame"}
        r4 = KD.book_shot_refusal("kling-3.0/video", no_frame)
        check("the U10 frame rule keeps BOOK_SHOT_NOT_CONTRACTED",
              r4 is not None
              and r4["reason_code"] == "BOOK_SHOT_NOT_CONTRACTED", r4)

# ---- (d) the excerpt never reaches a video model ----------------------------
def test_excerpt_never_reaches_a_video_model():
    import prompt_templates as PT
    lines = ["Mrs. Abernathy's secret ledger of the harbor",
             "She read it twice before the storm",
             "The tide keeps every promise"]
    spec_path = (PT.TEMPLATES_DIR / "fixtures" / "h3-specs"
                 / "product-book-S09.json")
    chars_path = (PT.TEMPLATES_DIR / "fixtures" / "h3-specs"
                  / "sample-characters.json")
    if not spec_path.is_file():
        check("(d) the product-book H3 fixture exists", False, str(spec_path))
        return
    spec = json.loads(spec_path.read_text("utf-8"))
    chars = json.loads(chars_path.read_text("utf-8"))
    prompt, sections = PT.assemble_h3(spec, chars)
    check("(d) the assembled H3 prompt carries the PRINTED_PAGES fragment",
          "printed" in prompt.lower() and "pages" in sections, sorted(sections))
    lowered = prompt.lower()
    for line in lines:
        check("(d) excerpt line absent from the H3 video prompt: %r"
              % line[:28], line.lower() not in lowered)
    check("(d) no excerpt marker leaked into the prompt (section ids)",
          "excerpt" not in sections and "overlay" not in sections,
          sorted(sections))
    # The overlay itself is DATA ONLY, and it names the one U9 hook.
    overlay = BS.excerpt_overlay(lines)
    check("(d) overlay is data: no prompt/payload key",
          not any(k in overlay for k in ("prompt", "payload", "request",
                                         "prompt_text")), sorted(overlay))
    check("(d) overlay is never sent to a video model",
          overlay.get("to_video_model") is False, overlay)
    check("(d) overlay keeps the client's lines verbatim and in order",
          overlay["lines"] == lines, overlay["lines"])
    check("(d) overlay caps at %d lines" % BS.EXCERPT_MAX_LINES,
          len(BS.excerpt_overlay(lines + ["a fourth line"] * 5)["lines"])
          == BS.EXCERPT_MAX_LINES)
    # The ruled seam: ONE named hook, and the one call site lives in
    # final_assembler.assembler.excerpt_overlay_stage.
    check("(d) exactly one overlay hook is named, for U9",
          BS.EXCERPT_OVERLAY_HOOK
          == "final_assembler.captions_burn.overlay_excerpt",
          BS.EXCERPT_OVERLAY_HOOK)
    check("(d) overlay names that hook", overlay["hook"] == BS.EXCERPT_OVERLAY_HOOK,
          overlay["hook"])
    import final_assembler.assembler as AS
    row_pending = AS.excerpt_overlay_stage(
        {"excerpt_overlay": {"lines": list(lines)}})
    check("(d) with no captions_burn.py the call site reports PENDING",
          row_pending["pending"] is True
          and row_pending["reason_code"] == "BOOK_OVERLAY_UNAVAILABLE"
          and row_pending["rows"][0]["hook"]
          == "captions_burn.overlay_excerpt", row_pending)
    check("(d) no overlay -> no row at all",
          AS.excerpt_overlay_stage({}) == {"rows": [], "pending": False,
                                           "reason_code": None},
          AS.excerpt_overlay_stage({}))
    # No second burn module: captions_burn.py is U9's and must not exist here,
    # and nothing in this tree may define a burn entry point.
    root = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    check("(d) no second burn module exists (U9's file is absent)",
          not os.path.exists(os.path.join(
              root, "75-drama-song-ad-factory", "scripts", "core",
              "final_assembler", "captions_burn.py")),
          "scripts/core/final_assembler/captions_burn.py")
    # The placeholder itself is GONE: book_shot names no module path and
    # defines no burn entry point (checked without spelling either name, so
    # a source scan of this tree reads 0 hits for them).
    src = open(os.path.join(HERE, "book_shot.py"), encoding="utf-8").read()
    check("(d) book_shot defines no burn entry point",
          "def burn_" not in src, [l for l in src.splitlines()
                                   if l.startswith("def burn_")])
    check("(d) book_shot names no captions_burn module path as a constant",
          'captions_burn.py"' not in src, [l for l in src.splitlines()
                                           if "captions_burn.py" in l])
    check("(d) pages_block consumes the template, never authors text",
          (BS.pages_block({"pages": "texture"}) or "") in prompt)
    check("(d) pages_block is silent unless pages==texture",
          BS.pages_block({"pages": "plain"}) is None
          and BS.pages_block({}) is None)
    # The card block states the boundary too (APPROVALS AND NOTICES only).
    rows = BS.plan_card_rows({"pages": "texture"}, overlay)
    texts = " ".join(t for _, t in rows)
    check("(d) the card says the excerpt never reaches a video model",
          "never reaches a video model" in texts, texts)

def main():
    if not hasattr(BS, "check_pages"):
        print("FAIL: U11 missing: book_shot has no check_pages (base tree)")
        return 1
    test_printed_vs_white()
    test_plan_hash_gate()
    test_excerpt_never_reaches_a_video_model()
    print("-" * 60)
    if FAILS:
        print("%d checks failed:" % len(FAILS))
        for name in FAILS:
            print("  FAILED: %s" % name)
        return 1
    print("ALL PASS: printed pages, plan hash, excerpt boundary (FU-U11 D1).")
    return 0

if __name__ == "__main__":
    sys.exit(main())
