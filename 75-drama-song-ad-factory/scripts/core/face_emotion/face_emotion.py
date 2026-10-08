"""face_emotion.py: face cues follow the line's emotion, never the light (Part G G6).

Root cause (LeAnne O3, redo-v3-20261008): the "warm" brand rule (warm LIGHT,
no dark backgrounds) was written into face wording in every clip prompt
("professional smile", "small fading smile") under pain lines. "Warm" is a
LIGHTING token only; a face's emotion comes from the story arc's emotional
arc for the line being sung/spoken.

Three pieces, stdlib only, no network, no paid calls:

1. ``line_emotion``: derive the emotion for a shot's lines from the story
   arc. Each of the twelve canonical beats carries a canonical emotion, and
   pain-keyword override catches specific lyric text (pain lines are lines
   with exhaustion/burden/buried/weariness words, whatever beat they sit on).
   Joyful lines may show a smile; a pain line never may.

2. ``strip_warm_face``: prompt sweep. "warm" lands in lighting tokens only —
   face wording with warm/happy/smile under a non-joyful emotion is rewritten
   to the emotion's own cue.

3. ``qc_frame_gate``: deterministic frame-sampling QC hook. Frames may come
   from a detector (or a stub); the gate fails a clip when a sampled frame
   shows a happy/smiling face under a pain line (FACE_EMOTION_MISMATCH).
"""
from __future__ import annotations

import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.dirname(_HERE)
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

try:
    from story_arc.story_arc import BEATS
except ImportError:                                    # imported as core.face_emotion
    from ..story_arc.story_arc import BEATS            # type: ignore

#: beat -> visible emotion the FACE carries. Lighting is separate.
BEAT_EMOTION = {
    "ordinary_world":   "weary-striving",
    "humiliation":      "hurt",
    "wound_deepens":    "hurt",
    "frozen":           "stuck",
    "seeing_it_too":    "wary",
    "failed_solutions": "resigned",
    "mentor":           "hopeful-cautious",
    "product_intro":    "curious",
    "doubt":            "uncertain",
    "climb":            "determined",
    "vindication":      "proud-joyful",
    "return_cta":       "invited-joyful",
}

#: the only emotions allowed to carry a smile/happy face.
JOYFUL = frozenset({"proud-joyful", "invited-joyful"})

#: pain-line keywords; a line carrying any of these is NEVER a smile line,
#: whatever beat it sits on.
PAIN_KEYWORDS = (
    "exhaustion", "exhausted", "buried", "burden", "holding me", "holding it",
    "tired", "weary", "weariness", "couch", "nobody claps", "cape",
    "straight face", "fades", "exhale",
    "rescue", "supposed to", "alone", "heavy", "sink", "wound",
)

#: face-cue wording per emotion, used when rewriting prompt face text.
EMOTION_CUES = {
    "weary-striving": "a tired steady gaze",
    "hurt": "eyes lowered, jaw tight",
    "stuck": "a still, blank stare",
    "wary": "a guarded sideways glance",
    "resigned": "a slow exhale, eyes down",
    "hopeful-cautious": "a careful half-lit gaze lifting",
    "curious": "an attentive brow, lips at rest",
    "uncertain": "lips pressed, brow drawn",
    "determined": "a set jaw, steady eyes",
    "proud-joyful": "an open proud smile",
    "invited-joyful": "a warm open smile",
}

# "warm" belongs to LIGHT, never to the face.
WARM_LIGHT_TOKEN = "warm bright golden light"

# smile/happy face wording the O3 prompts actually carried.
FACE_SMILE_RES = (
    "smile", "smiling", "smiles", "grin", "beaming", "cheerful",
    "happy", "joyful",
)

REASON_HAPPY_PAIN = "FACE_EMOTION_MISMATCH"   # QC: happy face under a pain line
REASON_WARM_FACE = "WARM_FACE_WORDING"        # sweep: warm/happy face off-joyful


class FaceEmotionError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _norm(text):
    return (text or "").strip().lower()


def is_pain_line(text):
    """A line is a pain line when it carries a pain keyword."""
    low = _norm(text)
    return any(k in low for k in PAIN_KEYWORDS)


def line_emotion(story_stage, lyric_text="", beats=None):
    """The emotion the FACE should carry for this shot's line.

    Derived from the story arc (the emotional arc), separately from
    lighting. A pain line (lyric text carries a pain keyword) forces a
    non-joyful emotion no matter the beat; a joyful beat keeps its joyful
    emotion only on a non-pain line. Unknown stage fails closed as "wary".
    """
    beats = list(beats or BEATS)
    if story_stage not in BEAT_EMOTION:
        return "wary"
    emotion = BEAT_EMOTION[story_stage]
    if is_pain_line(lyric_text):
        return "hurt" if emotion in JOYFUL else emotion
    return emotion


def find_face_smile(prompt):
    """Face-wording matches in a prompt: [(phrase,)] for smile/happy words."""
    low = _norm(prompt)
    return [w for w in FACE_SMILE_RES if w in low]


def strip_warm_face(prompt, emotion):
    """Sweep a clip prompt: "warm" stays in lighting; face wording obeys emotion.

    - Any smile/happy face wording is removed unless the emotion is joyful.
    - "warm" is never attached to face wording (warm = LIGHT token only);
      lighting tokens keep their warm wording untouched.
    Returns (clean_prompt, [reasons]). Raises FaceEmotionError on non-string
    prompts.
    """
    if not isinstance(prompt, str):
        raise FaceEmotionError("PROMPT_NOT_TEXT", repr(prompt))
    reasons = []
    out = prompt
    if emotion not in JOYFUL:
        cue = EMOTION_CUES.get(emotion, "a steady gaze")
        # sweep EVERY smile/happy wording — a prompt can carry two phrases
        # ("professional smile ... small fading smile"); count=1 + break
        # left the second one in, violating the zero-token done-when.
        for word in sorted(FACE_SMILE_RES, key=len, reverse=True):
            pattern = re.compile(r"\b(\w+\s+)?%s\w*\b" % word, re.IGNORECASE)
            while True:
                m = pattern.search(out)
                if not m:
                    break
                out = pattern.sub(cue, out, count=1)
                if REASON_WARM_FACE not in reasons:
                    reasons.append(REASON_WARM_FACE)
    # never leave "warm" bound to a face word even on joyful lines —
    # warm is a lighting token; the joyful cue carries its own wording.
    m = re.search(r"\bwarm\s+(smile|smiling|face)\b", out, re.IGNORECASE)
    if m:
        out = out[:m.start()] + EMOTION_CUES.get(emotion, "a steady gaze") \
            + out[m.end():]
        if REASON_WARM_FACE not in reasons:
            reasons.append(REASON_WARM_FACE)
    # collapse doubled articles left by a cue replacing "a <smile>" phrases
    # ("a a still, blank stare" -> "a still, blank stare").
    out = re.sub(r"\b(a|an|the)\s+\1\b", r"\1", out, flags=re.IGNORECASE)
    return out, reasons


def face_allowance(emotion):
    """True when the emotion may carry a smile/happy face."""
    return emotion in JOYFUL


# ---------------------------------------------------------------- QC hook ---
def qc_frame_gate(shots, frames_by_shot, lyrics=None):
    """Fail a clip whose sampled frames show a happy/smiling face under a
    pain line (G6 QC gate).

    shots: list of shot dicts carrying shot_id, story_stage and the 14.3
    contract (visible_emotion via contract["visible_emotion"] or the shot's
    own "visible_emotion"), plus lyric_text on the contract when present.
    frames_by_shot: {shot_id: [frame dicts]} — frame dicts carry
    {"happy": bool} (deterministic stub for tests; the real sampler swaps in
    a detector under the same shape). A frame may also carry "source":
    "detector" | "stub" for the receipt.
    lyrics: optional {lyric_line_id: text}; when a shot's contract lacks
    lyric_text the shot's joined line ids are looked up here.

    Returns {outcome, reason_code, findings[], steps} — qc_gate-shaped.
    """
    findings = []
    for shot in shots or []:
        if not isinstance(shot, dict):
            continue
        sid = shot.get("shot_id")
        contract = shot.get("contract") if isinstance(shot.get("contract"), dict) else shot
        lyric = _norm(contract.get("lyric_text"))
        if not lyric and lyrics and shot.get("lyric_line_ids"):
            lyric = " ".join(_norm(lyrics.get(lid, ""))
                             for lid in shot["lyric_line_ids"])
        emotion = _norm(contract.get("visible_emotion")) \
            or line_emotion(shot.get("story_stage"), lyric)
        # the pain line overrides any contract label: pain is derivable
        # from the lyric alone, so a mislabelled joyful contract emotion
        # can never whitelist a happy frame under it.
        if is_pain_line(lyric) and emotion in JOYFUL:
            emotion = "hurt"
        if face_allowance(emotion) or not is_pain_line(lyric):
            continue
        for frame in (frames_by_shot or {}).get(sid) or []:
            if isinstance(frame, dict) and frame.get("happy") is True:
                findings.append({
                    "shot_id": sid,
                    "code": REASON_HAPPY_PAIN,
                    "detail": "happy/smiling face sampled under a pain line "
                              "(emotion=%s, line=%r)"
                              % (emotion, lyric[:60]),
                    "frame_source": frame.get("source", "stub"),
                })
                break   # one finding per shot is enough to fail it
    return {
        "outcome": "ok" if not findings else "rejected",
        "reason_code": "G6_FACE_GATES_PASS" if not findings
        else REASON_HAPPY_PAIN,
        "findings": findings,
        "steps": ["face_emotion_match"],
    }


def selftest():
    """Assert-based self-check (no frameworks). Returns exit code."""
    fails = []

    def check(name, cond, detail=""):
        if not cond:
            fails.append("%s (%s)" % (name, detail))

    # 1. pain line under a joyful beat still refuses joy
    emo = line_emotion("return_cta", "so the exhaustion went quiet, "
                       "the smile got professional")
    check("pain-line overrides joyful beat", emo not in JOYFUL, emo)
    # 2. joyful line on joyful beat allows a smile
    emo2 = line_emotion("vindication", "you set it down and came home")
    check("joyful beat keeps smile", face_allowance(emo2), emo2)
    # 3. warm = light only: happy face wording under pain line gets swept
    p = ("she nods politely with a professional smile. "
         "cinematic 3D, warm bright golden light, lips closed.")
    swept, reasons = strip_warm_face(p, "resigned")
    check("smile swept off pain shot", "smile" not in swept.lower(), swept)
    check("warm light token untouched", WARM_LIGHT_TOKEN in swept, swept)
    check("sweep reason recorded", REASON_WARM_FACE in reasons, reasons)
    # 4. joyful shot keeps its smile
    kept, reasons2 = strip_warm_face(p, "proud-joyful")
    check("joyful keeps smile", "smile" in kept.lower(), kept)
    check("warm never binds to face", "warm smile" not in kept.lower()
          and "warmly" not in kept.lower().split("light")[0], kept)
    # 5. QC gate: happy face under pain line fails
    shot = {"shot_id": "K11", "story_stage": "frozen",
            "lyric_line_ids": ["L1"],
            "contract": {"lyric_text": "her smile slowly fades into weariness",
                         "visible_emotion": "stuck"}}
    res = qc_frame_gate([shot], {"K11": [{"happy": True, "source": "stub"}]})
    check("happy face under pain line fails",
          res["outcome"] == "rejected"
          and res["reason_code"] == REASON_HAPPY_PAIN, res["reason_code"])
    # 6. QC gate: matching face passes
    res2 = qc_frame_gate([shot], {"K11": [{"happy": False, "source": "stub"}]})
    check("matching face passes", res2["outcome"] == "ok", res2["reason_code"])
    # 7. QC gate: happy face under a JOYFUL line is fine
    shot_joy = {"shot_id": "K18", "story_stage": "vindication",
                "lyric_line_ids": ["L2"],
                "contract": {"lyric_text": "you set it down and came home",
                             "visible_emotion": "proud-joyful"}}
    res3 = qc_frame_gate([shot_joy], {"K18": [{"happy": True}]})
    check("happy face under joyful line passes", res3["outcome"] == "ok",
          res3["reason_code"])
    # 8. arc-derived emotion covers every beat
    for b in BEATS:
        check("emotion for %s" % b, b in BEAT_EMOTION, "missing")

    print("face_emotion selftest: %s (%d failures)"
          % ("PASS" if not fails else "FAIL", len(fails)))
    for f in fails:
        print(" -", f)
    return 0 if not fails else 1


if __name__ == "__main__":
    import sys
    sys.exit(selftest())
