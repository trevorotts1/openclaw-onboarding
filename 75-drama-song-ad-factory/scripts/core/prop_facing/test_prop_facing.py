#!/usr/bin/env python3
"""Section 3P F1 to F5: the Prop Facing contract, its sentences and its checks.

Proves, behaviourally, the first-run tests the plan names:

  F1  a person facing the camera, reading a phone, drawn with the fixed
      sentence: the camera sees the back of the phone (PASS).
  F2  the over-the-shoulder insert of the same phone: the balance reads
      exactly, from her side (PASS; the wrong-side insert FAILs
      INSERT_WRONG_SIDE).
  F3  a person signing a form across a desk: the form's words are upright
      to the signer (the form sentence faces the user; a camera-facing
      form FAILs PROP_FACES_CAMERA).
  F4  an H3 clip from the F1 still: the phone does not turn to the lens
      in the clip (a held clip PASSes; a turned clip FAILs
      PROP_TURNED_TO_CAMERA).
  F5  the check on F1 and on the old camera-facing picture of the same
      beat: it passes the first and fails the second.

Plus the contract edges: the fixed sentence wording per prop kind, rule
P5 (a shown prop may face the camera), rule P4 (an offered prop turns to
them), viewer_must_read=yes needs an insert, the record seam fails
closed, the calibration pair must sort or the check is UNAVAILABLE, and
the qc record (a PASS without calibration is UNAVAILABLE).

Run: HOME=$(mktemp -d) python3 scripts/core/prop_facing/test_prop_facing.py
stdlib + cv2/numpy (PREREQS python-mediapipe); no network, no spend.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import prop_facing as PF                                    # noqa: E402
import prop_facing.prop_facing as PFM                       # noqa: E402 (module)
import prop_facing.calibrate_prop as CAL                   # noqa: E402
from prop_facing.fixtures import build_fixtures as FIX      # noqa: E402

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % (detail,)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

TMP = tempfile.mkdtemp(prefix="prop-facing-")
FX = FIX.build(TMP)

PHONE = {"user": "her", "faces": "user", "viewer_must_read": "yes"}
PHONE_QUIET = {"user": "her", "faces": "user", "viewer_must_read": "no"}
FORM = {"user": "the signer", "faces": "user", "viewer_must_read": "no"}
SHOWN = {"user": "the viewer", "faces": "camera", "viewer_must_read": "yes"}
OFFERED = {"user": "the recipient", "faces": "other person",
           "viewer_must_read": "no"}

# ------------------------------------------------------------------- F1 -----
def test_f1_phone_back_to_camera():
    """F1: the phone-back picture PASSes; the screen-facing one FAILs."""
    spec = {"record": dict(PHONE_QUIET), "kind": "phone",
            "shot": "main", "prop_is_subject": True}
    good = PF.check_picture(None, spec, image=FX["images"]["good_frame"])
    check("F1: phone back to camera PASSes",
          good["verdict"] == "PASS", good)
    bad = PF.check_picture(None, spec, image=FX["images"]["bad_frame"])
    check("F1: phone screen to camera FAILs PROP_FACES_CAMERA",
          bad["verdict"] == "FAIL"
          and bad["reason_code"] == PF.PROP_FACES_CAMERA, bad)
    check("F1: the subject prop FAILs MAJOR, a non-subject MEDIUM",
          bad["checks"]["level"] == "MAJOR", bad["checks"])
    small = PF.check_picture(
        None, {"record": dict(PHONE_QUIET), "kind": "phone",
               "shot": "main", "prop_is_subject": False},
        image=FX["images"]["bad_frame"])
    check("F1: a non-subject prop FAILs MEDIUM",
          small["verdict"] == "FAIL" and small["checks"]["level"] == "MEDIUM",
          small["checks"])

# ------------------------------------------------------------------- F2 -----
def test_f2_insert_from_user_side():
    """F2: the insert from her side reads exactly; the wrong side FAILs."""
    spec = {"record": dict(PHONE), "kind": "phone", "shot": "insert",
            "expected_words": FX["word"], "prop_is_subject": True}
    good = PF.check_picture(None, spec, image=FX["images"]["insert_good"])
    check("F2: the insert from her side PASSes",
          good["verdict"] == "PASS", good)
    bad = PF.check_picture(None, spec,
                           image=FX["images"]["insert_wrong_side"])
    check("F2: the wrong-side insert FAILs INSERT_WRONG_SIDE, MAJOR",
          bad["verdict"] == "FAIL"
          and bad["reason_code"] == PF.INSERT_WRONG_SIDE
          and bad["checks"]["level"] == "MAJOR", bad)
    wrong = PF.check_picture(None, spec,
                             image=FX["images"]["insert_wrong_words"])
    check("F2: readable but wrong words FAIL PICTURE_TEXT_WRONG",
          wrong["verdict"] == "FAIL"
          and wrong["reason_code"] == PF.PICTURE_TEXT_WRONG
          and wrong["checks"]["level"] == "MAJOR", wrong)

# ------------------------------------------------------------------- F3 -----
def test_f3_form_faces_signer():
    """F3: a form's words upright to the signer; camera-facing FAILs."""
    sent = PF.facing_sentence(FORM, kind="form", user_ref="their")
    check("F3: the form sentence faces the signer",
          "toward their own eyes" in sent and "not readable" in sent, sent)
    good = PF.check_picture(
        None, {"record": dict(FORM), "kind": "form", "shot": "main"},
        image=FX["images"]["good_frame"])
    check("F3: the signer-side form PASSes", good["verdict"] == "PASS", good)
    bad = PF.check_picture(
        None, {"record": dict(FORM), "kind": "form", "shot": "main"},
        image=FX["images"]["bad_frame"])
    check("F3: a camera-facing form FAILs PROP_FACES_CAMERA",
          bad["reason_code"] == PF.PROP_FACES_CAMERA, bad)

# ------------------------------------------------------------------- F4 -----
def test_f4_clip_holds_facing():
    """F4: a clip that holds facing PASSes; a turned clip FAILs."""
    spec = {"record": dict(PHONE_QUIET), "kind": "phone",
            "shot": "main", "prop_is_subject": True}
    held = PF.check_clip("in-memory", spec, frames=FX["frames_good"])
    check("F4: the clip that holds facing PASSes", held["verdict"] == "PASS",
          held)
    turned = PF.check_clip("in-memory", spec, frames=FX["frames_turn"])
    check("F4: the clip that turns to the lens FAILs PROP_TURNED_TO_CAMERA",
          turned["verdict"] == "FAIL"
          and turned["reason_code"] == PF.PROP_TURNED_TO_CAMERA, turned)

# ------------------------------------------------------------------- F5 -----
def test_f5_calibration_pair_sorts():
    """F5: the check passes F1 and fails the old camera-facing picture."""
    rec = CAL.calibrate()
    check("F5: calibration sorts good=PASS bad=FAIL",
          rec["good"]["verdict"] == "PASS" and rec["bad"]["verdict"] == "FAIL",
          (rec["good"], rec["bad"]))
    check("F5: the calibration receipt says calibrated",
          rec["calibrated"] is True, rec["reason_code"])
    check("F5: is_calibrated accepts the receipt",
          CAL.is_calibrated(rec) is True)

    saved = PFM.SCREEN_WHITE_MIN
    try:
        PFM.SCREEN_WHITE_MIN = 10.0     # no picture can ever clear this
        broken = CAL.calibrate()
        check("F5: an insensitive checker makes the control NOT calibrated",
              broken["calibrated"] is False
              and broken["reason_code"] == PF.PROP_CHECK_UNAVAILABLE,
              (broken["calibrated"], broken["reason_code"]))
    finally:
        PFM.SCREEN_WHITE_MIN = saved
    check("F5: the calibration receipt carries the pair it sorted",
          CAL.calibrate()["calibrated"] is True)

# -------------------------------------------------------- fixed sentences ---

def test_fixed_sentences():
    """The plan's fixed sentences, verbatim per prop kind."""
    phone = PF.facing_sentence(PHONE_QUIET, kind="phone", user_ref="her")
    check("phone sentence: screen toward her own face, back to camera",
          "screen toward her own face" in phone
          and "camera sees the back of the phone" in phone
          and "not visible in this shot" in phone, phone)
    page = PF.facing_sentence(PHONE_QUIET, kind="page", user_ref="her")
    check("page sentence: reading side toward her eyes, back to camera",
          "reading side toward her own eyes" in page
          and "back or the edge of the page" in page, page)
    calc = PF.facing_sentence(PHONE_QUIET, kind="calculator", user_ref="her")
    check("calculator sentence: keys from the far side",
          "keys from the far side" in calc, calc)
    env = PF.facing_sentence(PHONE_QUIET, kind="envelope", user_ref="her")
    check("envelope sentence: address toward her eyes",
          "address toward her own eyes" in env, env)
    insert = PF.insert_sentence(PHONE, kind="phone", user_ref="her",
                                words=FX["word"])
    check("insert sentence quotes the exact words from her side",
          FX["word"] in insert and "from her side" in insert
          and "over her shoulder" in insert, insert)
    h3 = PF.h3_facing_block(PHONE_QUIET, kind="phone", user_ref="her")
    check("the H3 prop-facing block carries the fixed sentence",
          phone in h3, h3)
    shown = PF.facing_sentence(SHOWN, kind="sign", user_ref="the viewer")
    check("P5: a shown prop's sentence faces the camera",
          "made to be shown" in shown and "faces the camera" in shown, shown)
    offered = PF.facing_sentence(OFFERED, kind="form")
    check("P4: an offered prop's sentence turns to them",
          "offered" in offered and "turns to them" in offered, offered)
    pass_shown = PF.check_picture(
        None, {"record": dict(SHOWN), "kind": "sign", "shot": "main"},
        image=FX["images"]["bad_frame"])
    check("P5: a camera-facing shown prop PASSes",
          pass_shown["verdict"] == "PASS", pass_shown)
    # Rule T-1 narrowed: a P5 prop the viewer must read but that shows no
    # words is a blank sign, the same defect in the other direction.
    blank_shown = PF.check_picture(
        None, {"record": dict(SHOWN), "kind": "sign", "shot": "main"},
        image=FX["images"]["good_frame"])
    check("P5: a shown prop the viewer must read, with no words, FAILs",
          blank_shown["verdict"] == "FAIL"
          and blank_shown["reason_code"] == PF.PICTURE_TEXT_WRONG, blank_shown)
    pass_offered = PF.check_picture(
        None, {"record": dict(OFFERED), "kind": "form", "shot": "main"},
        image=FX["images"]["bad_frame"])
    check("P4: an offered prop still near the camera PASSes",
          pass_offered["verdict"] == "PASS", pass_offered)

def test_needs_insert_and_record_seam():
    """Rule P3 fires only for a user-facing prop the viewer must read."""
    check("viewer_must_read=yes + faces=user needs an insert",
          PF.needs_insert(PHONE) is True)
    check("viewer_must_read=no needs no insert",
          PF.needs_insert(PHONE_QUIET) is False)
    check("a shown prop never needs the insert",
          PF.needs_insert(SHOWN) is False)
    for bad in ({"user": "her", "faces": "sideways", "viewer_must_read": "no"},
                {"user": "", "faces": "user", "viewer_must_read": "no"},
                {"user": "her", "faces": "user", "viewer_must_read": "maybe"},
                "not a dict"):
        try:
            PF.normalize_record(bad)
            check("a bad record raises PROP_INPUT_INVALID", False, bad)
        except PF.PropFacingError as exc:
            check("a bad record raises PROP_INPUT_INVALID",
                  exc.code == PF.PROP_INPUT_INVALID, exc.code)
    try:
        PF.insert_sentence(PHONE, kind="phone")
        check("an insert with no words raises", False)
    except PF.PropFacingError as exc:
        check("an insert with no words raises PROP_INPUT_INVALID",
              exc.code == PF.PROP_INPUT_INVALID, exc.code)

# -------------------------------------------------------- contract & QC -----

def test_contract_text_present():
    """The six rules P1 to P6 ship in the module, not in a doc."""
    t = PF.PROP_FACING_CONTRACT
    for needle in ("P1 A prop faces its user", "P2 The camera gets what",
                   "P3 When the viewer must read", "P4 A prop that is offered",
                   "P5 Something made to be shown", "P6 A person looks"):
        check("contract carries: %s" % needle[:30], needle in t, t[:80])

def test_qc_record_requires_calibration():
    """Acceptance: no PASS record without a CALIBRATED checker."""
    reviewer = {"identity": "qc", "session": "s1", "authority": "qc"}
    good = PF.check_picture(
        None, {"record": dict(PHONE_QUIET), "kind": "phone", "shot": "main"},
        image=FX["images"]["good_frame"])
    rec = PF.qc_record(good, "s1", reviewer, calibrated=True, run_id="r1")
    check("calibrated PASS becomes a PASS record",
          rec["verdict"] == "PASS" and rec["check"] == "prop_facing",
          (rec["verdict"], rec["check"]))
    uncal = PF.qc_record(good, "s1", reviewer, calibrated=False, run_id="r1")
    check("an UNcalibrated PASS never becomes a PASS record",
          uncal["verdict"] == "UNAVAILABLE", uncal["verdict"])
    bad = PF.check_picture(
        None, {"record": dict(PHONE_QUIET), "kind": "phone", "shot": "main"},
        image=FX["images"]["bad_frame"])
    rec2 = PF.qc_record(bad, "s1", reviewer, calibrated=True, run_id="r1")
    check("a FAIL stays a FAIL record", rec2["verdict"] == "FAIL",
          rec2["verdict"])

def test_unreadable_picture_is_unavailable():
    """A picture that decodes to nothing is UNAVAILABLE, never a pass."""
    r = PF.check_picture("/nonexistent/picture.png",
                         {"record": dict(PHONE_QUIET), "kind": "phone",
                          "shot": "main"})
    check("an unreadable picture is UNAVAILABLE",
          r["verdict"] == "UNAVAILABLE"
          and r["reason_code"] == PF.PROP_FRAMES_UNAVAILABLE,
          (r["verdict"], r["reason_code"]))

def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    shutil.rmtree(TMP, ignore_errors=True)
    print("-" * 60)
    if FAILS:
        print("FAILED %d: %s" % (len(FAILS), "; ".join(FAILS)))
        return 1
    print("ALL PASS: prop facing contract, prompts and measured checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
