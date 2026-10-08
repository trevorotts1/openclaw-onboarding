"""G6 acceptance tests: face emotion matches the line (warm = light).

Part G G6 (Trevor order 1135). Stdlib only, no network, no paid calls.

One test per done-when clause:
  - prompt builder: a pain line produces NO smile cues and "warm" stays in
    lighting tokens only (the O3 K11/K10/K08 mismatched prompts sweep clean)
  - the arc drives the emotion separately from lighting (every beat maps;
    pain-line override beats a joyful stage)
  - QC hook: a known mismatched clip (happy face under a pain line —
    vid-K11 O3 wording) FAILS the gate; a matching clip passes; a happy
    face under a joyful line passes.

Run: python3 core/face_emotion/test_face_emotion_g6.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import face_emotion.face_emotion as FE
from story_arc.story_arc import BEATS

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# The real O3 prompts that carried face wording under pain lines
# (qualification/wuhs-leanne-soft-life/redo-v3-20261008/pics/reuse/req).
O3_K08 = ("She strides confidently toward the camera through the corridor, "
          "the plum cape flowing behind her, nods politely to a passing "
          "colleague with a professional smile. Camera tracks backward. "
          "Smooth natural character animation, cinematic 3D animated film "
          "look, warm bright golden light, lips closed and not speaking.")
O3_K11 = ("She gazes out of the sunlit window, her professional smile slowly "
          "fades into weariness, she lowers the coffee cup and exhales. "
          "Slow push-in. cinematic 3D animated film look, warm bright golden "
          "light, lips closed and not speaking.")
O3_K10 = ("The colleagues clap warmly toward the presenter at the far end "
          "while she stands at the side holding her folders, shifts them in "
          "her arms and glances down with a small fading smile. Slow push-in. "
          "warm bright golden light, lips closed.")


def test_builder_pain_lines_no_smile_warm_in_light():
    # emotion comes from the arc: these O3 lines sit on wound/frozen stages
    emo_k11 = FE.line_emotion("frozen", O3_K11)
    check("K11 emotion from arc is non-joyful", emo_k11 == "stuck", emo_k11)
    swept, reasons = FE.strip_warm_face(O3_K11, emo_k11)
    for w in ("smile", "smiling"):
        check("K11 swept: no %r" % w, w not in swept.lower(), swept[:80])
    check("K11 warm stays in lighting token",
          FE.WARM_LIGHT_TOKEN in swept and "warm" not in swept.lower().split(
              FE.WARM_LIGHT_TOKEN)[0], swept[:120])
    check("K11 sweep reason recorded", FE.REASON_WARM_FACE in reasons, reasons)

    emo_k08 = FE.line_emotion("ordinary_world", O3_K08)
    swept8, _ = FE.strip_warm_face(O3_K08, emo_k08)
    check("K08 swept: no smile under non-joyful emotion",
          "smile" not in swept8.lower(), swept8[:80])

    emo_k10 = FE.line_emotion("frozen", O3_K10)
    # K10's LYRIC is the pain line ("Nobody claps..."); the prompt is the
    # scene description and is never the emotion source.
    k10_lyric = "Nobody claps for the woman who never puts it down."
    check("K10 lyric is a pain line", FE.is_pain_line(k10_lyric), k10_lyric)
    check("K10 emotion from lyric is non-joyful",
          not FE.face_allowance(FE.line_emotion("frozen", k10_lyric)),
          FE.line_emotion("frozen", k10_lyric))
    swept10, _ = FE.strip_warm_face(O3_K10, emo_k10)
    check("K10 swept: fading smile removed", "smile" not in swept10.lower(),
          swept10[:80])


def test_arc_drives_emotion_separately():
    for b in BEATS:
        e = FE.line_emotion(b, "an ordinary line of no pain words")
        check("beat %s maps to an emotion" % b, e == FE.BEAT_EMOTION[b], e)
    check("joyful beats are only vindication/return_cta",
          FE.JOYFUL == frozenset({"proud-joyful", "invited-joyful"}),
          str(FE.JOYFUL))
    # pain-line override: a pain lyric on a joyful stage never smiles
    e = FE.line_emotion("return_cta", "the cape was heavy, i was alone")
    check("pain overrides joyful stage", not FE.face_allowance(e), e)
    # lighting is never the emotion source: same stage, different light, same face
    e2 = FE.line_emotion("frozen", "she stands in cool blue light")
    e3 = FE.line_emotion("frozen", "she stands in warm golden light")
    check("lighting does not change the face emotion", e2 == e3, "%s vs %s"
          % (e2, e3))


def test_qc_gate_mismatched_clip_fails():
    # known mismatched clip: K11 happy face sampled under a pain line
    shot = {"shot_id": "K11", "story_stage": "frozen",
            "lyric_line_ids": ["L11"],
            "contract": {"lyric_text":
                         "her professional smile slowly fades into weariness",
                         "visible_emotion": "stuck"}}
    frames = {"K11": [{"happy": True, "source": "stub"}]}
    res = FE.qc_frame_gate([shot], frames)
    check("mismatched clip rejected", res["outcome"] == "rejected",
          res["reason_code"])
    check("reason is FACE_EMOTION_MISMATCH",
          res["reason_code"] == FE.REASON_HAPPY_PAIN, res["reason_code"])
    check("finding names the shot",
          res["findings"] and res["findings"][0]["shot_id"] == "K11",
          str(res["findings"]))
    # matching clip passes
    res2 = FE.qc_frame_gate([shot], {"K11": [{"happy": False}]})
    check("matching clip passes", res2["outcome"] == "ok", res2["reason_code"])
    # happy face under a joyful line passes
    joy = {"shot_id": "K18", "story_stage": "vindication",
           "lyric_line_ids": ["L18"],
           "contract": {"lyric_text": "she set it down and came home",
                        "visible_emotion": "proud-joyful"}}
    res3 = FE.qc_frame_gate([joy], {"K18": [{"happy": True}]})
    check("happy under joyful line passes", res3["outcome"] == "ok",
          res3["reason_code"])
    # lyrics map path (no contract lyric_text): pain line found via line ids
    shot_map = {"shot_id": "K12", "story_stage": "wound_deepens",
                "lyric_line_ids": ["L12"],
                "contract": {"visible_emotion": "hurt"}}
    res4 = FE.qc_frame_gate([shot_map], {"K12": [{"happy": True}]},
                            lyrics={"L12": "the exhaustion went quiet"})
    check("lyrics-map pain line fails happy face",
          res4["outcome"] == "rejected", res4["reason_code"])


def test_qc_fixes_regression():
    # DEFECT 1 regression: a pain lyric with a MISLABELLED joyful contract
    # emotion must still fail a happy frame — pain is derivable from the
    # lyric alone and overrides the label.
    bad = {"shot_id": "K20", "story_stage": "return_cta",
           "lyric_line_ids": ["L1"],
           "contract": {"lyric_text":
                        "so the exhaustion went quiet, the smile got "
                        "professional",
                        "visible_emotion": "proud-joyful"}}
    res = FE.qc_frame_gate([bad], {"K20": [{"happy": True}]})
    check("mislabelled joyful contract under pain line still rejected",
          res["outcome"] == "rejected", res["reason_code"])
    # matched pair on a genuinely joyful line still passes
    good = {"shot_id": "K21", "story_stage": "return_cta",
            "contract": {"lyric_text": "you set it down and came home",
                         "visible_emotion": "proud-joyful"}}
    res2 = FE.qc_frame_gate([good], {"K21": [{"happy": True}]})
    check("matched joyful pair still passes", res2["outcome"] == "ok",
          res2["reason_code"])

    # DEFECT 2 regression: TWO smile phrases in one prompt both swept —
    # the done-when is "zero smile/happy face tokens".
    two = ("she nods with a professional smile, then a small fading smile. "
           "cinematic 3D, warm bright golden light, lips closed.")
    swept, reasons = FE.strip_warm_face(two, "resigned")
    check("two smile phrases both swept", "smile" not in swept.lower(),
          swept[:120])
    check("warm light token survives double sweep",
          FE.WARM_LIGHT_TOKEN in swept, swept[:120])
    check("double sweep reason recorded once",
          reasons.count(FE.REASON_WARM_FACE) == 1, reasons)
    # cosmetic: no doubled article after substitution
    one = "she glances down with a small fading smile."
    swept1, _ = FE.strip_warm_face(one, "stuck")
    import re
    check("no doubled article after sweep",
          re.search(r"\b(a|an|the)\s+\1\b", swept1, re.IGNORECASE) is None,
          swept1)


def main():
    test_builder_pain_lines_no_smile_warm_in_light()
    test_arc_drives_emotion_separately()
    test_qc_gate_mismatched_clip_fails()
    test_qc_fixes_regression()
    # selftest embedded too
    if FE.selftest() != 0:
        FAILS.append("selftest")
    print("test_face_emotion_g6: %s" % ("PASS" if not FAILS else "FAIL"))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
