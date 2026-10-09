#!/usr/bin/env python3
"""FU-STORYBOARD-SHOWS-BOTH: approval shows each shot's card AND its still.

Run: python3 core/storyboard_director/test_approval_package.py  (stdlib, no spend)
"""
import importlib
import os
import sys
import tempfile

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import storyboard_director.approval_package as AP   # noqa: E402
import kie_dispatch.model_lock as ML                # noqa: E402

KD = importlib.import_module("kie_dispatch.kie_dispatch")
VIDEO_MODEL = "kling-3.0/video"
FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name, "" if cond else " (%s)" % (detail,)))
    if not cond:
        FAILS.append(name)


def fixture():
    d = tempfile.mkdtemp(prefix="sbap-")
    shots, contracts, stills = [], {}, {}
    for i in range(3):
        sid = "s%d" % (i + 1)
        shots.append({"shot_id": sid, "song_start": i * 8.0, "song_end": i * 8.0 + 8.0,
                      "story_stage": "frozen", "location_id": "kitchen"})
        contracts[sid] = {"lyric_text": "line %d" % (i + 1),
                          "viewer_understanding": "she is stuck %d" % (i + 1),
                          "character_action": "sitting at table %d" % (i + 1),
                          "visible_emotion": "stuck"}
        stills[sid] = os.path.join(d, sid + ".png")
        open(stills[sid], "wb").write(b"png")
    return d, shots, contracts, stills


def test_card_and_image_for_every_shot():
    _, shots, contracts, stills = fixture()
    pkg = AP.build(shots, contracts, stills)
    check("one image per shot, in order", pkg["images"] == [stills["s1"], stills["s2"], stills["s3"]])
    for sid, it in zip(("s1", "s2", "s3"), pkg["items"]):
        for k in ("time", "line", "meaning", "where_action", "face_emotion", "still"):
            check("%s has %s" % (sid, k), bool(it[k]), it)
        check("%s card and picture both in the message" % sid,
              ('"%s"' % it["line"]) in pkg["message"] and it["still"] in pkg["message"])
    os.remove(stills["s2"])
    try:
        AP.build(shots, contracts, stills)
        check("missing still refuses", False)
    except AP.ApprovalError as e:
        check("missing still refuses", e.code == AP.STILL_MISSING and "s2" in str(e), e)
    del contracts["s3"]["character_action"]
    try:
        AP.build(shots, contracts, dict(stills, s2=stills["s1"]))
        check("incomplete card refuses", False)
    except AP.ApprovalError as e:
        check("incomplete card refuses", e.code == AP.CARD_INCOMPLETE, e)


def test_no_video_submit_before_approval():
    _, shots, contracts, stills = fixture()
    db = os.path.join(tempfile.mkdtemp(), "state.db")
    ML.lock_run_model(db, "r1", VIDEO_MODEL)
    sent = []

    def runner(*a, **k):
        sent.append(1)
        raise AssertionError("video submitted")

    req = {"model": VIDEO_MODEL, "request_kind": "video", "input": {"prompt": "p" * 200},
           "card_receipt": {"answers": {"video_style": "Lifelike 3D", "audio_style": "Soul Ballad",
                                        "length": 60, "video_model": "MiniMax H3 768P"},
                            "who": "t", "at": "2026-10-09T09:00:00Z"},
           "storyboard": {"shots": shots, "review": {"outcome": "pass"}}}  # shots still draft
    env = KD.dispatch(model=VIDEO_MODEL, request=req, save_dir="/tmp/sbap-x", ledger_db="/tmp/sbap-x.db",
                      run_id="r1", logical_key="k", attempt_id="a", estimated_cost=100,
                      runner=runner, state_store=db)
    check("unapproved storyboard: dispatch rejected, submit never called",
          env["outcome"] == "rejected" and env["reason_code"] == "STORYBOARD_NOT_APPROVED" and not sent,
          (env["outcome"], env["reason_code"], sent))
    approved = AP.approve(shots, contracts, stills)
    check("approve() stamps every shot", all(s["status"] == "storyboard_approved" for s in approved))
    check("entry check opens only after approve()",
          KD.check_storyboard_approval(None, None, dict(req, storyboard={
              "shots": approved, "review": {"outcome": "pass"}})) is None)
    os.remove(stills["s1"])
    try:
        AP.approve(shots, contracts, stills)
        check("approve() refuses when a still is missing", False)
    except AP.ApprovalError:
        check("approve() refuses when a still is missing", True)


def test_edit_resends_only_that_shot():
    _, shots, contracts, stills = fixture()
    made = []

    def make_still(sid, card):
        made.append(sid)
        p = stills[sid] + ".v2.png"
        open(p, "wb").write(b"png2")
        return p

    c2, s2, msg = AP.revise_shot(shots, contracts, stills, "s2",
                                 {"character_action": "standing at the sink"}, make_still)
    check("only shot 2's still regenerated", made == ["s2"], made)
    check("message names shot 2 only", "Shot 2 " in msg and "Shot 1 " not in msg and "Shot 3 " not in msg, msg)
    check("message shows new card and new picture", "standing at the sink" in msg and s2["s2"] in msg, msg)
    check("other stills untouched", s2["s1"] == stills["s1"] and s2["s3"] == stills["s3"])


if __name__ == "__main__":
    test_card_and_image_for_every_shot()
    test_no_video_submit_before_approval()
    test_edit_resends_only_that_shot()
    print("FAIL (%d): %s" % (len(FAILS), ", ".join(FAILS)) if FAILS else "ALL PASS")
    sys.exit(1 if FAILS else 0)
