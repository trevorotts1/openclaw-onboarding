"""I2 acceptance: a smiling face under a pain line and an off-topic scene both fail.

Run: python3 core/scene_match/test_scene_match_i2.py   (stdlib, no spend)
"""
import os
import sys

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)
import scene_match.scene_match as SM

SHOTS = [
    {"shot_id": "K11", "story_stage": "frozen", "location_id": "kitchen",
     "visual_objective": "woman at kitchen table staring at unpaid bills"},
    {"shot_id": "K12", "story_stage": "climb", "location_id": "storefront",
     "visual_objective": "owner unlocking the shop door at sunrise"},
    {"shot_id": "K18", "story_stage": "vindication", "location_id": "storefront",
     "visual_objective": "owner greeting a full line of customers"},
]
CONTRACTS = {
    "K11": {"lyric_text": "her smile slowly fades into weariness",
            "viewer_understanding": "she is exhausted by the bills",
            "character_action": "sitting at the kitchen table, head down over bills",
            "visible_emotion": "stuck"},
    "K12": {"lyric_text": "she unlocks the door anyway",
            "viewer_understanding": "she opens the shop",
            "character_action": "unlocking the shop door",
            "visible_emotion": "determined"},
    "K18": {"lyric_text": "you set it down and came home",
            "viewer_understanding": "customers are lining up",
            "character_action": "greeting customers in the shop",
            "visible_emotion": "proud-joyful"},
}
ON_K11 = [{"seen": "woman at kitchen table with bills", "happy": False}] * 3
ON_K12 = [{"seen": "hand unlocking shop door at sunrise", "happy": False}] * 3
ON_K18 = [{"seen": "owner smiling with customers in the shop", "happy": True}] * 3
FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append("%s (%s)" % (name, detail))


# complete storyboard cards pass; a missing action is named
check("cards complete", SM.check_cards(SHOTS, CONTRACTS)["outcome"] == "ok")
bad = dict(CONTRACTS, K12=dict(CONTRACTS["K12"], character_action=""))
r = SM.check_cards(SHOTS, bad)
check("card missing action fails", r["outcome"] == "rejected" and r["findings"][0]["shot_id"] == "K12")

# good footage passes (smile under the joyful line is fine)
good = SM.qc_scene_match(SHOTS, CONTRACTS, {"K11": ON_K11, "K12": ON_K12, "K18": ON_K18})
check("matching footage passes", good["outcome"] == "ok", good["findings"])

# smiling face under a pain line fails, only that shot is redone
smile = [{"seen": "woman at kitchen table with bills", "happy": True}] * 3
r = SM.qc_scene_match(SHOTS, CONTRACTS, {"K11": smile, "K12": ON_K12, "K18": ON_K18})
check("smile under pain line fails", r["outcome"] == "rejected"
      and r["reason_code"] == "FACE_EMOTION_MISMATCH", r)
check("only K11 regenerated", r["regenerate_shot_ids"] == ["K11"], r["regenerate_shot_ids"])

# off-topic scene fails, only that shot is redone
off = [{"seen": "city skyline at night with traffic", "happy": False}] * 3
r = SM.qc_scene_match(SHOTS, CONTRACTS, {"K11": ON_K11, "K12": off, "K18": ON_K18})
check("off-topic scene fails", r["reason_code"] == "SCENE_OFF_TOPIC", r)
check("only K12 regenerated", r["regenerate_shot_ids"] == ["K12"], r["regenerate_shot_ids"])

# a shot with too few sampled frames is never passed unseen
r = SM.qc_scene_match(SHOTS, CONTRACTS, {"K11": ON_K11[:1], "K12": ON_K12, "K18": ON_K18})
check("unsampled shot fails", r["regenerate_shot_ids"] == ["K11"]
      and r["findings"][0]["code"] == "SCENE_FRAMES_MISSING", r)

print("scene_match I2 test: %s (%d failures)" % ("PASS" if not FAILS else "FAIL", len(FAILS)))
for f in FAILS:
    print(" -", f)
sys.exit(1 if FAILS else 0)
