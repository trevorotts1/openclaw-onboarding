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

The excerpt seam is measured, never assumed: named by
book_shot.EXCERPT_OVERLAY_HOOK and called from
final_assembler.assembler.excerpt_overlay_stage, which reports a PENDING
row while U9's final_assembler/captions_burn.py is absent and the burn
once it lands. This test passes in either world; it never asserts a
file's absence.

Run: python3 scripts/core/book_shot/test_book_pages_d1.py
"""
from __future__ import annotations

import json
import os
import re
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
    # The SECOND fixture family (the 999 half's generator, ported for parity):
    # the same calibrated check must sort a generator it was NOT calibrated on.
    pf_print = FIX.pages_frame(cv2, np, "printed")
    pf_white = FIX.pages_frame(cv2, np, "white")
    r_pf_print = BS.check_pages(frames=[pf_print, pf_print, pf_print], calibrated=cal)
    r_pf_white = BS.check_pages(frames=[pf_white, pf_white, pf_white], calibrated=cal)
    check("(a) the second fixture family printed page PASSes the same check",
          r_pf_print["verdict"] == "PASS", r_pf_print["reason_code"])
    check("(a) the second fixture family white page FAILs BOOK_BLANK_PAGES",
          r_pf_white["verdict"] == "FAIL"
          and r_pf_white["reason_code"] == BS.BOOK_BLANK_PAGES,
          r_pf_white["reason_code"])
    # ONE blank page among printed ones is a chapter break: only MORE THAN
    # ONE blank fails. Paint the right page white inside a printed frame.
    half = printed[2].copy()
    half[:, half.shape[1] // 2 + 2:] = (250, 250, 250)
    r_half = BS.check_pages(frames=[half, printed[3]], calibrated=cal)
    check("(a) exactly one blank page does not fail (chapter-break rule)",
          r_half["verdict"] == "PASS"
          and len(r_half["checks"]["pages"]["blanks"]) == 1,
          (r_half["verdict"], r_half["checks"]["pages"]["blanks"]))
    # The blank-page FAIL names the measured blank count, not a bare code.
    check("(a) the blank-page FAIL names the measured blank count",
          "blank pages among" in (r_white.get("detail") or "")
          and "threshold" in (r_white.get("detail") or ""), r_white.get("detail"))
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
    burn_py = os.path.join(CORE, "final_assembler", "captions_burn.py")
    row_seam = AS.excerpt_overlay_stage(
        {"excerpt_overlay": {"lines": list(lines)}})
    check("(d) the seam row names U9's hook in either world",
          bool(row_seam["rows"])
          and row_seam["rows"][0]["hook"] == "captions_burn.overlay_excerpt",
          row_seam)
    if os.path.isfile(burn_py):
        # U9 landed: the call site calls overlay_excerpt; the burn is its.
        check("(d) with captions_burn.py present the seam reports the burn",
              row_seam["pending"] is False
              and row_seam["reason_code"] is None
              and row_seam["rows"][0]["burned"] is True, row_seam)
    else:
        # U9 not in this tree yet: the call site reports PENDING, no burn.
        check("(d) with no captions_burn.py the call site reports PENDING",
              row_seam["pending"] is True
              and row_seam["reason_code"] == "BOOK_OVERLAY_UNAVAILABLE"
              and row_seam["rows"][0]["burned"] is False, row_seam)
    check("(d) no overlay -> no row at all",
          AS.excerpt_overlay_stage({}) == {"rows": [], "pending": False,
                                           "reason_code": None},
          AS.excerpt_overlay_stage({}))
    # No SECOND burn module: the excerpt burn entry point may live only in
    # final_assembler/captions_burn.py (U9's artifact, present or not).
    strays = []
    for _dp, _dns, _fns in os.walk(CORE):
        for _fn in _fns:
            if not _fn.endswith(".py") or _fn.startswith("test_"):
                continue
            _path = os.path.join(_dp, _fn)
            if _fn == "captions_burn.py":
                if os.path.dirname(_path) != os.path.join(
                        CORE, "final_assembler"):
                    strays.append(os.path.relpath(_path, CORE))
                continue
            try:
                _txt = open(_path, encoding="utf-8").read()
            except OSError:
                continue
            if any(_ln.startswith(("def overlay_excerpt", "def burn_"))
                   for _ln in _txt.splitlines()):
                strays.append(os.path.relpath(_path, CORE))
    check("(d) no second burn module (only final_assembler/captions_burn.py)",
          strays == [], strays)
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
    # The pending row names the artifact U9 must land (not a wire-up).
    r0 = row_seam["rows"][0]
    check("(d) the pending row names captions_burn.py as the U9 artifact",
          r0.get("artifact", "").endswith("final_assembler/captions_burn.py"),
          r0)

# ---- (d) the assembled prompt never leaks excerpt words ---------------------
def test_prompt_never_carries_excerpt_words():
    """The video model's prompt is built from subject only; excerpt is DATA."""
    import prompt_templates as PT
    lines = ["Mrs. Abernathy's secret ledger of the harbor",
             "She read it twice before the storm",
             "The tide keeps every promise"]
    spec_path = (PT.TEMPLATES_DIR / "fixtures" / "h3-specs"
                 / "product-book-S09.json")
    spec = json.loads(spec_path.read_text("utf-8"))
    check("(d) the H3 spec carries no excerpt key at all",
          "excerpt" not in spec, sorted(spec))
    # Assemble the video prompt with the excerpt present in the plan payload.
    chars = json.loads((PT.TEMPLATES_DIR / "fixtures" / "h3-specs"
                        / "sample-characters.json").read_text("utf-8"))
    plan = dict(spec, excerpt_overlay={"lines": lines})
    prompt, sections = PT.assemble_h3(plan, chars)
    check("(d) the video prompt never reads the overlay key",
          "overlay" not in prompt.lower() and "excerpt" not in sections,
          prompt)
    # Distinctive-word proof: every distinctive excerpt word is absent.
    distinctive = ("abernathy", "ledger", "harbor", "storm", "tide",
                   "promise", "secret")
    leaked = [w for w in distinctive if w in prompt.lower()]
    check("(d) the assembled prompt never carries excerpt words",
          not leaked, leaked)
    # No whole excerpt line appears in the template prompt.
    whole = [ln for ln in lines if ln.lower() in prompt.lower()]
    check("(d) no whole excerpt line appears in the template prompt",
          not whole, whole)

# ---- (d) intake excerpt surface (fail closed) -------------------------------
def test_intake_excerpt_fail_closed():
    """>3 lines or a typo is REFUSED at intake; spell-clean lines survive."""
    import importlib
    IB = importlib.import_module("intake_book.book")
    clean = ["She read the old letter twice", "The rain kept falling all night",
             "He closed the door and waited"]
    lines, prov, errs = IB.excerpt_lines({"excerpt_lines": clean})
    check("intake excerpt_lines: provided lines come back verbatim",
          lines == clean and prov == "provided" and errs == [],
          (lines, prov, errs))
    lines2, prov2, errs2 = IB.excerpt_lines({})
    check("intake excerpt_lines: no excerpt key -> missing, no error",
          lines2 == [] and prov2 == "missing" and errs2 == [], (lines2, prov2))
    lines3, prov3, errs3 = IB.excerpt_lines(
        {"excerpt_lines": clean + ["a fourth line"]})
    check("intake excerpt_lines: >3 lines truncated and reports an error",
          len(lines3) == 3 and errs3, (len(lines3), errs3))
    # evaluate() refuses a bad excerpt with a reason_code, no questions burned.
    bad = IB.evaluate({"excerpt_lines": clean + ["a fourth line"],
                       "book_title": "T", "author": "A",
                       "buy_link": "https://x.example/b", "audience": "a",
                       "pain_or_transformation": "p"})
    check("intake evaluate: >3 excerpt lines is REFUSED EXCERPT_INVALID",
          bad.get("outcome") == "rejected"
          and bad.get("reason_code") == IB.EXCERPT_INVALID
          and bad.get("questions") == [], bad)
    bad2 = IB.evaluate({"excerpt_lines": ["The kitchn was empty"],
                        "book_title": "T", "author": "A",
                        "buy_link": "https://x.example/b", "audience": "a",
                        "pain_or_transformation": "p"})
    check("intake evaluate: a misspelled excerpt is REFUSED EXCERPT_INVALID",
          bad2.get("outcome") == "rejected"
          and bad2.get("reason_code") == IB.EXCERPT_INVALID, bad2)

# ---- (d) card block carries the hash, never a new choice --------------------
def test_card_block_carries_plan_hash():
    """plan_card_rows / card_render / intake_card all show APPROVED hash."""
    import importlib
    CR = importlib.import_module("catalog_calculator.card_render")
    IC = importlib.import_module("choice_card.intake_card.intake_card")
    plan = {"pages": "texture", "book_title": "The Harbor Ledger",
            "author": "A. Author", "excerpt_lines": ["A short line"]}
    h = BS.plan_sha256(plan)
    appr = dict(plan, approved_book_plan_sha256=h, approved_at="2026-10-09")
    rows = BS.plan_card_rows(appr, None)
    texts = " ".join(t for _, t in rows)
    check("card: plan_card_rows shows the APPROVED plan hash",
          h[:12] in texts and "APPROVED" in texts
          and "NOT APPROVED" not in texts, texts)
    check("card: plan_card_rows shows no numbered options",
          not re.search(r"\b[1-9]\d*\.", texts), texts)
    unapp = BS.plan_card_rows(plan, None)
    check("card: an unapproved plan shows NOT APPROVED",
          "NOT APPROVED" in " ".join(t for _, t in unapp),
          " ".join(t for _, t in unapp))
    # The calculator card block requires campaign_type == "book".
    rendered, _ = CR.render({"length": "60 seconds", "campaign_type": "book",
                             "book_plan": appr}, None)
    check("card: calculator card carries the Book block + hash",
          "Book shots" in rendered and h[:12] in rendered, rendered)
    rendered2, _ = CR.render({"length": "60 seconds"}, None)
    check("card: non-book calculator card has no Book block",
          "Book shots" not in rendered2, rendered2)
    # The intake card carries the same block via render_card(plan=, excerpt=).
    ic_card = IC.render_card(None, plan=appr, excerpt={"lines": ["A short line"]})
    check("card: intake card carries the Book block + hash",
          "Book shots" in ic_card and h[:12] in ic_card, ic_card)
    ic_plain = IC.render_card(None)
    check("card: plain intake card has no Book block",
          "Book shots" not in ic_plain, ic_plain)
    check("card: intake card keeps 6 questions in / 6 out",
          ic_card.count("Question") == 6 and ic_plain.count("Question") == 6,
          (ic_card.count("Question"), ic_plain.count("Question")))
    check("card: CLOSING_LINE is present in both cards",
          IC.CLOSING_LINE in ic_card and IC.CLOSING_LINE in ic_plain, "")

def main():
    if not hasattr(BS, "check_pages"):
        print("FAIL: U11 missing: book_shot has no check_pages (base tree)")
        return 1
    test_printed_vs_white()
    test_plan_hash_gate()
    test_excerpt_never_reaches_a_video_model()
    test_prompt_never_carries_excerpt_words()
    test_intake_excerpt_fail_closed()
    test_card_block_carries_plan_hash()
    print("-" * 60)
    if FAILS:
        print("%d checks failed:" % len(FAILS))
        for name in FAILS:
            print("  FAILED: %s" % name)
        return 1
    print("ALL PASS: printed pages, plan hash, card block, excerpt seam (FU-U11 D1).")
    return 0

# ---- pytest no-silent-pass guard (check() records, never raises) ------------
def test_no_failed_checks():
    """pytest entry: raise if any check() failed, so a bare pytest run cannot
    report green on a red suite (check() only records into FAILS)."""
    assert not FAILS, "failed checks: %s" % FAILS

if __name__ == "__main__":
    sys.exit(main())
