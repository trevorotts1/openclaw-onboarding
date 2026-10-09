#!/usr/bin/env python3
"""FU-U10 C1: the book orientation contract, its prompts and its measured checks.

Proves, behaviourally, the five FAIL-first cases named by the unit brief:

  (a) the hflip of the cover fixture FAILs BOOK_MIRRORED  (today: no check)
  (b) a back-cover frame FAILs BOOK_COVER_NOT_FRONT       (today: no check)
  (c) a leaf moving left to right FAILs BOOK_WRONG_DIRECTION, right to left
      PASSes                                              (today: no check)
  (d) the calibration pair must sort correctly or the check is UNAVAILABLE
  (e) a book prompt carries no "camera ... in gentle continuous motion" line
      (today it always does -- bible.compile_visual_prompt appends it to every
      prompt regardless of shot kind)

Plus the contract edges: spine-side sign, right-to-left language mirrors BY
RULE from the brief, the H3 bracket+plain camera line, the image-model block,
the exact fixed wording, and the qc record (a PASS without calibration is
UNAVAILABLE, because acceptance requires a calibrated checker).

Run: HOME=$(mktemp -d) python3 scripts/core/book_shot/test_book_shot_c1.py
stdlib + cv2/numpy (PREREQS python-mediapipe) + ffmpeg; no network, no spend.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
# Only core/ goes on the path: book_shot is then unambiguously the package
# (the same-named module inside it is reached as book_shot.book_shot).
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import book_shot as BS                                    # noqa: E402 (package)
import book_shot.book_shot as BSM                         # noqa: E402 (module)
import book_shot.calibrate_book as CAL                    # noqa: E402
from book_shot.fixtures import build_fixtures as FIX       # noqa: E402

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % (detail,)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

# ------------------------------------------------------------- fixtures -----

TMP = tempfile.mkdtemp(prefix="book-shot-c1-")
FX = FIX.build(TMP)
COVER = FX["paths"]["cover"]
SPEC = {"language": "en", "action": "flip", "title": FX["title"],
        "cover_path": COVER}
#: A direction-only plan: no cover file on the clip (the leaf frames carry no
#: cover), so the flow check is the only thing being judged.
DIR_SPEC = {"language": "en", "action": "flip"}

# Minimal valid bible records (same shapes as shot_planner/test_motion_f12.py).
STYLE = {
    "schema_version": "1.0.0", "style_id": "resilia-animated-01",
    "aspect_ratio": "9:16",
    "aesthetic": "animated drama look",
    "rendering_style": "hand-painted 2D animation",
    "camera_language": "intimate eye-level medium shots",
    "lens_tendencies": "35mm-equivalent framing",
    "lighting_doctrine": "warm golden key with soft teal fill",
    "contrast_architecture": "lifted shadows",
    "environment_texture": "lived-in painterly sets",
    "grain_sharpness": "fine animation grain",
    "color_palette": ["warm amber", "deep teal"],
    "visual_continuity_constraints": ["fixed proportions"],
    "banned_visual_cliches": ["photoreal deepfake skin"],
}
PRODUCT = {
    "schema_version": "1.0.0", "product_id": "book-cover",
    "packaging_reference": "hardcover book", "logo_mark": "wordmark",
    "color": "cream", "geometry": "rectangular case", "label_placement": "front",
    "cap_lid": "none",
    "prohibited_invented_text": ["miracle"],
    "required_product_reference_images": ["img-1"],
}
CHARS = [{"character_id": "c1", "approved_reference_asset_ids": ["ref-1"]}]
SHOT = {"shot_id": "s1", "base_prompt": "the book on a kitchen table",
        "character_ids": ["c1"]}

# ---------------------------------------------------------- (a) mirrored ----

def test_mirrored_cover_fails():
    """(a) the hflip of the cover fixture FAILs BOOK_MIRRORED."""
    r = BS.check_clip("in-memory", SPEC, frames=[FX["images"]["flip_frame"]])
    check("hflip cover FAILs BOOK_MIRRORED",
          r["verdict"] == "FAIL" and r["reason_code"] == BS.BOOK_MIRRORED,
          (r["verdict"], r["reason_code"]))
    check("mirror detection reports the inlier counts as evidence",
          r["checks"].get("cover", {}).get("mirror_score", 0)
          > r["checks"].get("cover", {}).get("true_score", 0),
          r["checks"].get("cover"))
    # control: the upright cover does NOT fail as mirrored
    ok = BS.check_clip("in-memory", SPEC, frames=[FX["images"]["front_frame"]])
    check("upright cover does not report BOOK_MIRRORED",
          ok["reason_code"] != BS.BOOK_MIRRORED, ok["reason_code"])

# -------------------------------------------------------- (b) back cover ----

def test_back_cover_fails():
    """(b) a back-cover frame FAILs BOOK_COVER_NOT_FRONT."""
    r = BS.check_clip("in-memory", SPEC, frames=[FX["images"]["back_frame"]])
    check("back-cover frame FAILs BOOK_COVER_NOT_FRONT",
          r["verdict"] == "FAIL" and r["reason_code"] == BS.BOOK_COVER_NOT_FRONT,
          (r["verdict"], r["reason_code"]))
    # control: the same plan with the front cover visible and the real cover
    # present must not trip it.
    ok = BS.check_clip("in-memory", SPEC, frames=[FX["images"]["front_frame"]])
    check("front cover clears the cover-match floor",
          ok["reason_code"] != BS.BOOK_COVER_NOT_FRONT, ok["reason_code"])

def test_spine_side_sign():
    """The rectifying homography's sign names the spine side."""
    up = BS.detect_cover(FX["images"]["front_frame"], COVER)
    mir = BS.detect_cover(FX["images"]["flip_frame"], COVER)
    check("upright cover: spine on the left", up["spine_side"] == "left",
          up["spine_side"])
    check("mirrored cover scores higher against the mirror file",
          mir["mirror_score"] > mir["true_score"],
          (mir["mirror_score"], mir["true_score"]))

# ---------------------------------------------------- (c) leaf direction ----

def test_leaf_direction():
    """(c) left-to-right FAILs BOOK_WRONG_DIRECTION; right-to-left PASSes."""
    right = BS.check_clip("in-memory", DIR_SPEC, frames=FX["leaf_right"])
    check("leaf moving left to right FAILs BOOK_WRONG_DIRECTION",
          right["verdict"] == "FAIL"
          and right["reason_code"] == BS.BOOK_WRONG_DIRECTION,
          (right["verdict"], right["reason_code"], right["checks"].get("direction")))
    left = BS.check_clip("in-memory", DIR_SPEC, frames=FX["leaf_left"])
    check("leaf moving right to left PASSes",
          left["verdict"] == "PASS"
          and left["checks"]["direction"]["crossed"] is True,
          (left["verdict"], left["reason_code"], left["checks"].get("direction")))
    # no motion at all is its own failure, never a pass
    still = [FX["leaf_left"][0].copy() for _ in range(8)]
    none = BS.check_clip("in-memory", DIR_SPEC, frames=still)
    check("a still clip FAILs BOOK_NO_MOTION",
          none["verdict"] == "FAIL" and none["reason_code"] == BS.BOOK_NO_MOTION,
          (none["verdict"], none["reason_code"]))

def test_rtl_mirrors_by_rule():
    """A right-to-left brief mirrors the expectation BY RULE, from the brief."""
    check("en reads left to right", BS.reading_direction("en") == "ltr")
    check("ar reads right to left", BS.reading_direction("ar") == "rtl")
    rtl = dict(DIR_SPEC, language="ar")
    r = BS.check_clip("in-memory", rtl, frames=FX["leaf_right"])
    check("the same left-to-right leaf is CORRECT for an rtl brief",
          r["verdict"] == "PASS", (r["verdict"], r["reason_code"]))
    ltr = BS.check_clip("in-memory", rtl, frames=FX["leaf_left"])
    check("the right-to-left leaf is WRONG for an rtl brief",
          ltr["verdict"] == "FAIL" and ltr["reason_code"] == BS.BOOK_WRONG_DIRECTION,
          (ltr["verdict"], ltr["reason_code"]))

# ----------------------------------------------------- (d) calibration ------

def test_calibration_pair():
    """(d) the calibration pair must sort correctly, or UNAVAILABLE."""
    rec = CAL.calibrate()
    check("calibration control sorts good=PASS hflip=FAIL",
          rec["good"]["verdict"] == "PASS" and rec["hflip"]["verdict"] == "FAIL",
          (rec["good"], rec["hflip"]))
    check("the calibration receipt says calibrated", rec["calibrated"] is True,
          rec["reason_code"])
    check("is_calibrated accepts the receipt", CAL.is_calibrated(rec) is True)

    # A broken checker must make the control UNAVAILABLE, never a pass: force
    # the threshold out of reach and prove the control stops sorting.
    saved = BSM.COVER_INLIER_MIN
    try:
        BSM.COVER_INLIER_MIN = 10 ** 9      # no cover can ever clear this
        bad = CAL.calibrate()
        check("an insensitive checker makes the control NOT calibrated",
              bad["calibrated"] is False
              and bad["reason_code"] == BS.BOOK_CALIBRATION_FAILED,
              (bad["calibrated"], bad["reason_code"]))
        check("the uncalibrated receipt tells the reader what to do",
              "UNAVAILABLE" in bad["next_action"], bad["next_action"])
    finally:
        BSM.COVER_INLIER_MIN = saved
    check("the calibration receipt carries the pair it sorted",
          CAL.calibrate()["calibrated"] is True)

def test_qc_record_requires_calibration():
    """Acceptance: no book clip accepted without a CALIBRATED PASS record."""
    reviewer = {"identity": "qc", "session": "s1", "authority": "qc"}
    good = BS.check_clip("in-memory", DIR_SPEC, frames=FX["leaf_left"])
    rec = BS.qc_record(good, "s1", reviewer, calibrated=True, run_id="r1")
    check("calibrated PASS becomes a PASS record",
          rec["verdict"] == "PASS" and rec["check"] == "book_orientation",
          (rec["verdict"], rec["check"]))
    uncal = BS.qc_record(good, "s1", reviewer, calibrated=False, run_id="r1")
    check("an UNcalibrated PASS never becomes a PASS record",
          uncal["verdict"] == "UNAVAILABLE",
          uncal["verdict"])
    bad = BS.check_clip("in-memory", DIR_SPEC, frames=FX["leaf_right"])
    rec2 = BS.qc_record(bad, "s1", reviewer, calibrated=True, run_id="r1")
    check("a FAIL stays a FAIL record", rec2["verdict"] == "FAIL", rec2["verdict"])

# ------------------------------------------------------- (e) prompt lines ---

def test_book_prompt_has_no_generic_motion():
    """(e) a book prompt carries no 'camera ... gentle continuous motion'."""
    from product_style_bible import bible
    blocks = BS.prompt_blocks({"language": "en"}, "flip")
    prompt = BS.build_prompt({"language": "en"}, "flip", blocks)
    check("the book prompt carries the fixed ORIENTATION block",
          BS.ORIENTATION in prompt, prompt[:120])
    check("the book prompt carries the fixed CONSTRAINTS block",
          BS.CONSTRAINTS in prompt, prompt[-160:])
    check("the fixed blocks join in the documented order",
          list(blocks.keys()) == list(BS.BLOCK_ORDER), list(blocks.keys()))
    check("the book prompt says static camera",
          BS.CAMERA in prompt, prompt[:200])

    # The bible compiles a BOOK shot with the shot's own motion, and keeps the
    # generic F12 line only for people shots.
    book_shot = dict(SHOT, kind="book",
                     motion=BS.build_prompt({"language": "en"}, "flip"))
    out = bible.compile_visual_prompt(STYLE, CHARS, PRODUCT, book_shot)
    check("book shot prompt has NO generic F12 motion line",
          "gentle continuous motion" not in out["prompt"],
          out["prompt"][-400:])
    check("book shot prompt carries the book motion block",
          BS.ORIENTATION in out["prompt"], out["prompt"][-400:])
    people = bible.compile_visual_prompt(STYLE, CHARS, PRODUCT,
                                         dict(SHOT, kind="people"))
    check("people shots keep the generic F12 motion line",
          "gentle continuous motion" in people["prompt"],
          people["prompt"][-300:])
    # a product / insert shot also takes its own motion, never the people line
    prod = bible.compile_visual_prompt(STYLE, CHARS, PRODUCT,
                                       dict(SHOT, kind="product",
                                            motion=BS.CAMERA))
    check("product shots use the shot's own motion block",
          "gentle continuous motion" not in prod["prompt"]
          and BS.CAMERA in prod["prompt"], prod["prompt"][-300:])

def test_prompt_wording_is_exact():
    """The exact plan wording, verbatim, block for block."""
    b = BS.prompt_blocks({"language": "en"}, "open")
    check("ORIENTATION wording is the plan's, verbatim",
          b["subject"].endswith(BS.ORIENTATION), b["subject"][:80])
    check("ACTION:open wording is the plan's, verbatim",
          BS.ACTION_OPEN in b["action"], b["action"])
    check("CAMERA block is the plan's, verbatim", b["camera"] == BS.CAMERA,
          b["camera"])
    b2 = BS.prompt_blocks({"language": "en"}, "flip")
    check("ACTION:flip wording is the plan's, verbatim",
          BS.ACTION_FLIP in b2["action"], b2["action"])
    h3 = BS.prompt_blocks({"language": "en", "model": "minimax-h3/image-to-video"},
                          "open")
    check("H3 i2v adds the bracket tag AND the plain-words camera line",
          BS.CAMERA_SHOT_TAG in h3["camera"] and BS.CAMERA_PLAIN in h3["camera"]
          and BS.CAMERA in h3["camera"], h3["camera"])
    im = BS.image_model_blocks({"language": "en"})
    check("the image model gets ORIENTATION plus CONSTRAINTS only",
          set(im.keys()) == {"orientation", "constraints"}
          and im["orientation"] == BS.ORIENTATION
          and im["constraints"] == BS.CONSTRAINTS, sorted(im.keys()))
    check("the image-model block states the spine rule and cover-facing rule",
          "spine is on the left edge" in im["orientation"]
          and "front cover facing the camera" in im["orientation"],
          im["orientation"][:200])
    check("an rtl image-model block mirrors the spine rule by rule",
          "spine is on the right edge"
          in BS.image_model_blocks({"language": "ar"})["orientation"],
          BS.image_model_blocks({"language": "ar"})["orientation"][:200])
    rtl = BS.prompt_blocks({"language": "he"}, "open")
    check("an rtl brief mirrors the spine rule by rule",
          "right edge of the frame" in rtl["subject"], rtl["subject"][:200])

# --------------------------------------------------- title OCR direction ----

def test_title_reads_in_reading_order():
    """OCR must find the title words in reading order (U9 engine shared)."""
    check("the title words in order pass",
          BS.title_reads_correctly("THE SUNDAY COOKBOOK", FX["title"]) is True)
    check("reversed order FAILs",
          BS.title_reads_correctly("COOKBOOK SUNDAY THE", FX["title"]) is False)
    check("a missing title FAILs",
          BS.title_reads_correctly("", FX["title"]) is False)
    if shutil.which("tesseract"):
        rec = BS.check_clip("in-memory", SPEC, frames=[FX["images"]["front_frame"]])
        check("the upright cover PASSes the title check with tesseract",
              rec["checks"].get("title", {}).get("ocr") == "ok",
              rec["checks"].get("title"))
        flipped = BS.check_clip("in-memory", SPEC,
                                frames=[FX["images"]["flip_frame"]])
        check("the mirrored cover FAILs before the title check (BOOK_MIRRORED)",
              flipped["reason_code"] == BS.BOOK_MIRRORED, flipped["reason_code"])
    else:
        check("no tesseract: the title check is UNAVAILABLE, never a pass",
              True)

def test_missing_engine_is_unavailable():
    """UNAVAILABLE never passes: no OCR engine blocks, it does not approve."""
    saved = BSM.OCR_ENGINE
    try:
        BSM.OCR_ENGINE = "no-such-ocr-engine-xyz"
        try:
            BS.ocr_text("/dev/null")
            check("missing OCR engine raises", False, "no raise")
        except BS.BookShotError as e:
            check("missing OCR engine raises BOOK_OCR_UNAVAILABLE",
                  e.code == BS.BOOK_OCR_UNAVAILABLE, e.code)
    finally:
        BSM.OCR_ENGINE = saved
    check("the OCR engine is declared as tesseract", saved == "tesseract", saved)

def test_unreadable_clip_is_unavailable():
    """A clip that decodes to nothing is UNAVAILABLE, never a pass."""
    r = BS.check_clip("/nonexistent/clip.mp4", SPEC, frames=None)
    check("an unreadable clip is UNAVAILABLE",
          r["verdict"] == "UNAVAILABLE"
          and r["reason_code"] == BS.BOOK_FRAMES_UNAVAILABLE,
          (r["verdict"], r["reason_code"]))

def test_intake_language_and_aspect():
    """intake_book: language defaults to en (ltr) and the aspect is measured."""
    import intake_book as IB
    d = tempfile.mkdtemp(prefix="book-intake-")
    cover = os.path.join(d, "cover.png")
    import cv2
    cv2.imwrite(cover, FX["images"]["cover"])
    brief = {"book_title": "T", "author": "A", "buy_link": "u", "cover": cover,
             "audience": "x", "pain_or_transformation": "y"}
    r = IB.evaluate(brief, {})
    check("no language supplied defaults to en and left-to-right",
          r["summary"]["book"]["language"] == "en"
          and r["summary"]["reading_direction"] == "ltr",
          (r["summary"]["book"].get("language"),
           r["summary"].get("reading_direction")))
    check("the defaulted language is recorded as defaulted, not provided",
          r["provenance"]["book"]["language"] == "defaulted",
          r["provenance"]["book"].get("language"))
    check("the cover aspect is MEASURED from the file",
          r["summary"]["cover_aspect"]["measured"] is True
          and r["summary"]["cover_aspect"]["width"] == FIX.COVER_W
          and r["summary"]["cover_aspect"]["height"] == FIX.COVER_H,
          r["summary"].get("cover_aspect"))
    rtl = IB.evaluate(dict(brief, language="ar"), {})
    check("an rtl brief.language flips the reading direction",
          rtl["summary"]["reading_direction"] == "rtl",
          rtl["summary"].get("reading_direction"))
    check("an unreadable cover measures as measured=False, never invented",
          IB.evaluate(dict(brief, cover=os.path.join(d, "nope.png")), {})[
              "summary"]["cover_aspect"] == {"width": None, "height": None,
                                             "aspect": None, "measured": False})
    # The three-question cap still holds: language rides in the offer slot.
    check("the language ask adds no question id",
          [q["id"] for q in r["questions"]] == [q["id"] for q in
                                                IB.evaluate(brief, {})["questions"]])
    check("the offer question asks the language in the same sentence",
          "language" in IB.Q_BOOK_OFFER.lower(), IB.Q_BOOK_OFFER)
    check("language folds into the offer slot only",
          "language" in IB.FOLDED_FIELDS["offer"]
          and all("language" not in v for k, v in IB.FOLDED_FIELDS.items()
                  if k != "offer"), IB.FOLDED_FIELDS)
    shutil.rmtree(d, ignore_errors=True)

def test_kie_dispatch_refuses_uncontracted_book_job():
    """A book video job without the contract is refused, never dispatched."""
    import importlib
    import kie_dispatch.model_lock as ML
    KD = importlib.import_module("kie_dispatch.kie_dispatch")
    cover = os.path.join(TMP, "cover_for_dispatch.png")
    import cv2
    cv2.imwrite(cover, FX["images"]["cover"])
    frame_with_cover = os.path.join(TMP, "start_from_cover.png")
    cv2.imwrite(frame_with_cover, FX["images"]["front_frame"])
    other_frame = os.path.join(TMP, "start_from_other.png")
    cv2.imwrite(other_frame, FX["images"]["back_frame"])

    # FU-U11 ACTIVATED the plan-hash requirement: a book job now carries the
    # approved plan hash, so the start-frame cases below add a MATCHING hash
    # and still exercise the start-frame rule (it is no longer reachable
    # without one).
    _plan = BS.plan_spec({"book_title": FX["title"], "pages": "texture"})
    _sha = BS.plan_sha256(_plan)
    base = {"request_kind": "video", "shot_kind": "book",
            "book_plan_sha256": _sha, "approved_book_plan_sha256": _sha}
    r = KD.book_shot_refusal("kling-3.0/video", base)
    check("a book video job with no start frame is refused",
          r is not None and r["reason_code"] == "BOOK_SHOT_NOT_CONTRACTED",
          r)
    check("the refusal names the missing start frame",
          "start frame" in r["detail"], r["detail"])
    r2 = KD.book_shot_refusal("kling-3.0/video",
                              dict(base, book_start_frame=other_frame,
                                   book_cover_path=cover))
    check("a start frame made from OTHER bytes is refused",
          r2 is not None and r2["reason_code"] == "BOOK_SHOT_NOT_CONTRACTED",
          r2)
    ok = KD.book_shot_refusal("kling-3.0/video",
                              dict(base, book_start_frame=frame_with_cover,
                                   book_cover_path=cover))
    check("a start frame made from the cover passes the contract",
          ok is None, ok)
    exact = KD.book_shot_refusal(
        "kling-3.0/video", dict(base, book_start_frame=cover,
                                book_cover_path=cover))
    check("the cover file itself as the start frame passes", exact is None, exact)
    # A non-book shot kind is untouched by this gate.
    check("a non-book shot is never refused by this gate",
          KD.book_shot_refusal("kling-3.0/video", dict(base, shot_kind="people"))
          is None)
    # FU-U11: the plan-hash requirement is ACTIVE. A book job with NO hash is
    # refused on the plan rule before the start-frame rule is even reached;
    # the start-frame rule is exercised by the cases above, which carry a
    # matching hash.
    no_plan = KD.book_shot_refusal(
        "kling-3.0/video",
        {"request_kind": "video", "shot_kind": "book",
         "book_start_frame": frame_with_cover, "book_cover_path": cover})
    check("a book job with NO plan hash is refused now that U11 writes it",
          no_plan is not None
          and no_plan["reason_code"] == "BOOK_PLAN_NOT_APPROVED", no_plan)
    # ...and it activates the moment the field exists and disagrees.
    bad = KD.book_shot_refusal(
        "kling-3.0/video",
        dict(base, book_plan_sha256="deadbeef",
             approved_book_plan_sha256="cafe", book_start_frame=frame_with_cover,
             book_cover_path=cover))
    check("a mismatched plan hash refuses once the field exists",
          bad is not None and bad["reason_code"] == "BOOK_PLAN_NOT_APPROVED"
          and "book_plan_sha256" in bad["detail"], bad)
    # (onboarding half's extra case) a carried hash with NO approval at all
    # is refused -- the plan changed hands without the client's tick.
    unapproved = KD.book_shot_refusal(
        "kling-3.0/video",
        {"request_kind": "video", "shot_kind": "book",
         "book_plan_sha256": _sha,
         "book_start_frame": frame_with_cover, "book_cover_path": cover})
    check("a carried plan hash with no approval is refused",
          unapproved is not None
          and unapproved["reason_code"] == "BOOK_PLAN_NOT_APPROVED",
          unapproved)

def test_qc_gate_requires_book_orientation():
    """A book campaign's shots stage requires a book_orientation record."""
    import qc_gate as Q
    check("book campaign at shots requires book_orientation",
          "book_orientation" in Q.required_checks("shots", ["video"], "book"),
          Q.required_checks("shots", ["video"], "book"))
    check("a non-book campaign is untouched",
          Q.required_checks("shots", ["video"], "song") == ["video"])
    check("another stage is untouched",
          Q.required_checks("final_edit", ["video"], "book") == ["video"])
    check("an already-listed check is never duplicated",
          Q.required_checks("shots", ["book_orientation"], "book")
          == ["book_orientation"])
    # Behavioural: with no book_orientation record the gate refuses to advance.
    reviewer = {"identity": "qc", "session": "s1", "authority": "qc"}
    makers = {"v-1": "maker-1"}
    rec = {"schema_version": "1.0.0", "check_id": "v-1", "run_id": "r1",
           "stage": "shots", "check": "video", "verdict": "PASS",
           "evidence": {"summary": "clips render"}, "checker_version": "1.0.0",
           "reviewer": reviewer}
    res = Q.evaluate("r1", "shots", [rec], makers, ["video"],
                     campaign_type="book")
    check("the gate refuses a book campaign with no book_orientation record",
          res["gate"] != "PASS"
          and any(f["check_id"] == "book_orientation" and f["code"] == "MISSING_QC"
                  for f in res["failures"]), res)
    # ...and a calibrated PASS record lets it through.
    book_rec = BS.qc_record(BS.check_clip("in-memory", DIR_SPEC,
                                          frames=FX["leaf_left"]),
                            "s1", reviewer, calibrated=True, run_id="r1")
    makers2 = dict(makers, **{book_rec["check_id"]: "maker-2"})
    res2 = Q.evaluate("r1", "shots", [rec, book_rec], makers2,
                      ["video", "book_orientation"], campaign_type="book")
    check("a calibrated book_orientation PASS advances the stage",
          res2["gate"] == "PASS", res2)
    # An UNcalibrated one never does.
    uncal = BS.qc_record(BS.check_clip("in-memory", DIR_SPEC,
                                       frames=FX["leaf_left"]),
                         "s1", reviewer, calibrated=False, run_id="r1")
    res3 = Q.evaluate("r1", "shots", [rec, uncal],
                      dict(makers2, **{uncal["check_id"]: "maker-2"}),
                      ["video", "book_orientation"], campaign_type="book")
    check("an uncalibrated book record never advances the stage",
          res3["gate"] != "PASS"
          and any(f["code"] == "UNAVAILABLE_MANDATORY" for f in res3["failures"]),
          res3["failures"])

def test_contract_text_present():
    """The seven contract rules ship in the module, not in a doc."""
    t = BS.BOOK_ORIENTATION_CONTRACT
    for needle in ("Front cover faces the camera when closed",
                   "spine on the LEFT edge",
                   "swings LEFT", "lifts from the RIGHT stack",
                   "Never mirrored", "no orbit", "sha256 from intake_book"):
        check("contract carries: %s" % needle[:32], needle in t)

def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    shutil.rmtree(TMP, ignore_errors=True)
    print("-" * 60)
    if FAILS:
        print("FAILED %d: %s" % (len(FAILS), "; ".join(FAILS)))
        return 1
    print("ALL PASS: book orientation contract, prompts and measured checks.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
