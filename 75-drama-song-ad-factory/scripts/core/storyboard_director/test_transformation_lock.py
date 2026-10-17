"""W1-method-story-U3: method storyboard cards (beat / cue / state), the
Transformation Lock and the paid-platform safe zones (SPEC C4, F8).

Run: python3 -m pytest -q 75-drama-song-ad-factory/scripts/core/storyboard_director/test_transformation_lock.py
(no spend, stdlib only, no Agnes and no KIE call)
"""
import atexit
import os
import shutil
import sys
import tempfile

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import scene_match.scene_match as SM                     # noqa: E402
import storyboard_director.approval_package as AP        # noqa: E402

BREAKTHROUGH_S = 42.0
LOCK_TOKEN = "cape off"
ROW = {"placement": "instagram-reels-ad",
       "safe_zone": {"top": 0.12, "bottom": 0.18, "left": 0.05, "right": 0.05}}
TODAY_CARD = ("Shot %d (%s)\nLine: \"%s\"\nViewer must understand: %s\n"
              "Place and action: %s\nFace: %s\nPicture: %s")
_TMP = []
atexit.register(lambda: [shutil.rmtree(d, ignore_errors=True) for d in _TMP])


def _clock(s):
    m, sec = divmod(int(round(s)), 60)
    return "%d:%02d" % (m, sec)


def _fixture(with_method_fields=True, safe_zone=None):
    """Three shots: pain side (before), the breakthrough, then the cape back on."""
    shots = [
        {"shot_id": "s1", "song_start": 0.0, "song_end": 20.0,
         "story_stage": "frozen", "location_id": "kitchen"},
        {"shot_id": "s2", "song_start": 20.0, "song_end": 44.0,
         "story_stage": "mentor", "location_id": "community-room"},
        {"shot_id": "s3", "song_start": 44.0, "song_end": 70.0,
         "story_stage": "climb", "location_id": "kitchen"},
    ]
    contracts = {
        "s1": {"lyric_text": "she carries it alone",
               "viewer_understanding": "she is exhausted and on her own",
               "character_action": "sitting at the kitchen table, head down",
               "visible_emotion": "stuck"},
        "s2": {"lyric_text": "someone finally answers",
               "viewer_understanding": "help arrives and she accepts it",
               "character_action": "listening to a voice on the phone",
               "visible_emotion": "hopeful"},
        "s3": {"lyric_text": "the old weight settles back",
               "viewer_understanding": "she has gone back to how she was",
               "character_action": "wearing the cape again at the kitchen table",
               "visible_emotion": "withdrawn"},
    }
    if with_method_fields:
        contracts["s1"].update({"story_beat_id": "SB-02", "music_cue_id": "PAIN_BUILD",
                                "character_state": "before"})
        contracts["s2"].update({"story_beat_id": "SB-07", "music_cue_ids": ["HERO_SHIFT"],
                                "character_state": "after"})
        contracts["s3"].update({"story_beat_id": "SB-09", "music_cue_id": "BREAKTHROUGH",
                                "character_state": "before"})
    if safe_zone:
        for sid in ("s1", "s2", "s3"):
            contracts[sid]["safe_zone"] = dict(safe_zone)
    d = tempfile.mkdtemp(prefix="W1-method-story-U3-")
    _TMP.append(d)
    stills = {}
    for sid in ("s1", "s2", "s3"):
        stills[sid] = os.path.join(d, sid + ".png")
        open(stills[sid], "wb").write(b"png")
    return d, shots, contracts, stills


def _lock(shots, contracts, token=LOCK_TOKEN, cut=BREAKTHROUGH_S):
    return SM.transformation_lock(shots, contracts, token, cut)


def test_method_card_shows_the_three_lines():
    _, shots, contracts, stills = _fixture()
    pkg = AP.build(shots, contracts, stills, method=True)
    for line in ("Story beat: SB-02", "Music: PAIN_BUILD", "State: before",
                 "Story beat: SB-07", "Music: HERO_SHIFT", "State: after",
                 "Story beat: SB-09", "Music: BREAKTHROUGH"):
        assert line in pkg["message"], line
    assert pkg["items"][0]["story_beat"] == "SB-02"
    assert pkg["items"][1]["music_cue"] == "HERO_SHIFT"
    assert pkg["items"][2]["state"] == "before"
    # the cue id list and a "Before" spelling both read as the token
    contracts["s1"]["character_state"] = "Before -- cape still on"
    cards = SM.check_cards(shots, contracts, method=True)
    assert cards["outcome"] == "ok", cards


def test_method_cards_required_only_when_method_is_asked_for():
    _, shots, _, _ = _fixture()
    plain = {s["shot_id"]: dict(
        {"lyric_text": "words", "viewer_understanding": "meaning",
         "character_action": "doing the thing", "visible_emotion": "set"})
        for s in shots}
    assert SM.check_cards(shots, plain)["outcome"] == "ok"
    r = SM.check_cards(shots, plain, method=True)
    assert r["outcome"] == "rejected", r
    details = sorted(f["detail"] for f in r["findings"])
    assert len(details) == 9, details       # three cards x three method facts
    assert "storyboard card has no story beat id" in details, details
    assert "storyboard card has no music cue" in details, details
    assert "storyboard card has no character state (before/after/neutral)" in details, details
    # a state that is not before/after/neutral is refused, never guessed
    _, shots2, contracts2, _ = _fixture()
    contracts2["s3"]["character_state"] = "cape removed as a symbol"
    r2 = SM.check_cards(shots2, contracts2, method=True)
    assert r2["outcome"] == "rejected" and r2["reason_code"] == SM.CARD_INCOMPLETE, r2
    assert any("not before/after/neutral" in f["detail"] for f in r2["findings"]), r2


def test_cape_on_shot_after_the_breakthrough_is_refused():
    _, shots, contracts, stills = _fixture()
    r = _lock(shots, contracts)
    assert r["outcome"] == "rejected" and r["reason_code"] == SM.LOCK_BROKEN, r
    assert [f["shot_id"] for f in r["findings"]] == ["s3"], r["findings"]
    assert "before-state of %s" % LOCK_TOKEN in r["findings"][0]["detail"], r["findings"]
    # the pain-side shot keeps its before state; only the one after is named
    assert "s1" not in [f["shot_id"] for f in r["findings"]]
    try:
        AP.build(shots, contracts, stills, method=True,
                 lock_token=LOCK_TOKEN, breakthrough_s=BREAKTHROUGH_S)
        raise AssertionError("cape-on shot approved")
    except AP.ApprovalError as e:
        assert e.code == SM.LOCK_BROKEN, e
        assert "s3" in str(e) and LOCK_TOKEN in str(e), str(e)
    # no breakthrough time given = the lock cannot be proved, so it refuses
    r2 = SM.transformation_lock(shots, contracts, LOCK_TOKEN, None)
    assert r2["outcome"] == "rejected" and r2["reason_code"] == SM.LOCK_BROKEN, r2


def test_flashback_tagged_with_a_reason_passes():
    _, shots, contracts, stills = _fixture()
    contracts["s3"]["continuity_tag"] = "flashback"
    contracts["s3"]["continuity_reason"] = "she remembers the night she first put it on"
    r = _lock(shots, contracts)
    assert r["outcome"] == "ok" and r["reason_code"] == SM.LOCK_HELD, r
    assert not r["findings"], r["findings"]
    pkg = AP.build(shots, contracts, stills, method=True,
                   lock_token=LOCK_TOKEN, breakthrough_s=BREAKTHROUGH_S)
    assert "Story beat: SB-09" in pkg["message"]
    # a setback counts too, and the tag may sit on the shot itself
    contracts["s3"].pop("continuity_tag")
    contracts["s3"].pop("continuity_reason")
    shots[2]["continuity_tag"] = "setback"
    shots[2]["continuity_reason"] = "the offer falls through for one scene"
    assert _lock(shots, contracts)["outcome"] == "ok"
    # a tag with no reason is not an exemption (SPEC C4: "with a reason")
    shots[2]["continuity_reason"] = ""
    refused = _lock(shots, contracts)
    assert refused["outcome"] == "rejected" and "no reason" in refused["findings"][0]["detail"], refused


def test_non_method_package_is_byte_identical_to_today():
    _, shots, contracts, stills = _fixture(with_method_fields=False)
    pkg = AP.build(shots, contracts, stills)
    cards = []
    for n, s in enumerate(shots, 1):
        c = contracts[s["shot_id"]]
        card = SM.shot_card(s, c)
        cards.append(TODAY_CARD % (n, "%s-%s" % (_clock(s["song_start"]), _clock(s["song_end"])),
                                   card["line"], card["meaning"], card["where_action"],
                                   card["face_emotion"], stills[s["shot_id"]]))
    expected = ("Storyboard: %d shots. Nothing is made into video until you say go.\n\n%s\n\n%s"
                % (len(cards), "\n\n".join(cards), AP.FOOTER))
    assert pkg["message"] == expected, pkg["message"]
    today_keys = {"n", "shot_id", "time", "line", "meaning",
                  "where_action", "face_emotion", "still"}
    assert [set(item) for item in pkg["items"]] == [today_keys] * 3, pkg["items"]
    assert pkg["images"] == [stills["s1"], stills["s2"], stills["s3"]]
    # today's callers (approval_runner) pass three arguments and nothing else
    assert AP.build(shots, contracts, stills)["message"] == expected
    assert _lock(shots, contracts)["outcome"] == "ok"   # no before-state after the breakthrough


def test_safe_zone_boxes_checked_against_the_platform_row():
    inside = {"key_action": [0.10, 0.15, 0.40, 0.50],
              "on_screen_text": [0.05, 0.70, 0.60, 0.10]}
    _, shots, contracts, stills = _fixture(safe_zone=inside)
    assert SM.check_cards(shots, contracts, platform_row=ROW)["outcome"] == "ok"
    AP.build(shots, contracts, stills, platform_row=ROW)      # no raise = inside
    # text sitting in the bottom margin is outside the row's safe zone
    contracts["s2"]["safe_zone"]["on_screen_text"] = [0.05, 0.75, 0.60, 0.12]
    r = SM.check_cards(shots, contracts, platform_row=ROW)
    assert r["outcome"] == "rejected" and r["reason_code"] == SM.SAFE_ZONE, r
    assert [f["shot_id"] for f in r["findings"]] == ["s2"], r["findings"]
    try:
        AP.build(shots, contracts, stills, platform_row=ROW)
        raise AssertionError("text outside the safe zone approved")
    except AP.ApprovalError as e:
        assert e.code == SM.SAFE_ZONE, e
    # a paid run that carries no safe_zone fields cannot be checked, so it refuses
    _, shots2, contracts2, _ = _fixture()
    missing = SM.check_cards(shots2, contracts2, platform_row=ROW)
    assert missing["outcome"] == "rejected" and missing["reason_code"] == SM.SAFE_ZONE, missing
    assert len(missing["findings"]) == 6, missing["findings"]     # 3 shots x 2 boxes
    # a row with no margin data checks nothing, and no row changes nothing
    bare = {"placement": "instagram-reels-ad"}
    assert SM.check_cards(shots2, contracts2, platform_row=bare)["outcome"] == "ok"
    assert SM.check_cards(shots2, contracts2)["outcome"] == "ok"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t()
            print("ok  %s" % t.__name__)
        except AssertionError as e:
            failed.append("%s: %s" % (t.__name__, e))
            print("FAIL %s: %s" % (t.__name__, e))
    print("TRANSFORMATION LOCK: %s" % ("PASS" if not failed else "FAIL (%d)" % len(failed)))
    sys.exit(1 if failed else 0)
