"""face_emotion.py: face cues follow the line's emotion, never the light (Part G G6).

Root cause (client O3, redo-v3-20261008): the "warm" brand rule (warm LIGHT,
no dark backgrounds) was written into face wording in every clip prompt
("professional smile", "small fading smile") under pain lines. "Warm" is a
LIGHTING token only; a face's emotion comes from the story arc's emotional
arc for the line being sung/spoken.

Three pieces, stdlib only, no network, no paid calls:

1. ``line_emotion``: the emotion for a shot's lines. The sentence's Emotion
   Track tag (3G.1: pain, worry, exhaustion, anger, hope, relief, joy, pride,
   tenderness, resolve) is read first; the fixed twelve-beat table is the
   fallback. A pain-keyword override catches specific lyric text (pain lines
   carry exhaustion/burden/buried/weariness words, whatever beat they sit
   on). Joyful lines may show a smile; a pain line never may.

2. ``strip_warm_face``: prompt sweep. "warm" lands in lighting tokens only —
   face wording with warm/happy/smile under a non-joyful emotion is rewritten
   to the emotion's own cue.

3. ``qc_frame_gate``: the Emotion Hold check (3G.6, N-118). Fed every take's
   frames (4 per second, the whole frame), it judges both directions — no
   smile or teeth held where the tag says none, the tagged feeling in at
   least half the frames with no pinched brows through most of the piece —
   and returns the second the drift starts. Fails ``EMOTION_DRIFT``; MAJOR at
   intensity 2 or 3, MEDIUM at intensity 1.

Lever helpers (3G.6): ``stronger_direction`` (lever 2), ``takes_for_piece``
(lever 3) and ``remake_steps`` (lever 5). The picture and the chain are
U-LIPGATE's files; these are the values they read.
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

# -------------------------------------------------- Emotion Track (3G.1) ---
#: the ten Emotion tags the beat sheet's Emotion column carries (3G.1).
EMOTION_TAGS = frozenset({
    "pain", "worry", "exhaustion", "anger", "hope",
    "relief", "joy", "pride", "tenderness", "resolve",
})
#: tags on which a held smile or teeth-grin is a drift (3G.1: no smile; the
#: pain-ward direction of 3G.6). Anger sits here too: 3G.1 allows it no smile,
#: so a grin still fails the hold.
NO_SMILE_TAGS = frozenset({"pain", "worry", "exhaustion", "anger", "resolve"})
#: tags whose feeling must fill at least half the frames (3G.6 pass mark).
FEELING_TAGS = frozenset({"hope", "relief", "joy", "pride", "tenderness"})
#: 3G.1: every beat-sheet row must carry a valid tag, or the sheet is refused.
REASON_EMOTION_MISSING = "EMOTION_MISSING"
#: lever 2: drawn one step stronger at intensity 2 or 3 (3G.6).
STRONGER_TAGS = frozenset({"pain", "worry", "exhaustion", "resolve"})
STRONGER_DIRECTION = "mouth corners clearly down, brows drawn, no teeth"

#: the contact sheet samples the whole frame 4 times a second (3G.6).
FPS_CONTACT_SHEET = 4
#: a feeling "held for half a second or more" is two frames in a row (3G.6).
HOLD_FRAMES = 2

SEVERITY_MAJOR = "MAJOR"
SEVERITY_MEDIUM = "MEDIUM"

# "warm" belongs to LIGHT, never to the face.
WARM_LIGHT_TOKEN = "warm bright golden light"

# smile/happy face wording the O3 prompts actually carried.
FACE_SMILE_RES = (
    "smile", "smiling", "smiles", "grin", "beaming", "cheerful",
    "happy", "joyful",
)

REASON_EMOTION_DRIFT = "EMOTION_DRIFT"         # 3G.6: the take left its feeling
REASON_HAPPY_PAIN = "FACE_EMOTION_MISMATCH"   # storyboard card: happy under pain
REASON_WARM_FACE = "WARM_FACE_WORDING"        # sweep: warm/happy face off-joyful


class FaceEmotionError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _norm(text):
    return (text or "").strip().lower()


def _intensity(value, default=2):
    """1, 2 or 3 from a tag's intensity; anything else is ``default``."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n in (1, 2, 3) else default


def is_pain_line(text):
    """A line is a pain line when it carries a pain keyword."""
    low = _norm(text)
    return any(k in low for k in PAIN_KEYWORDS)


#: legacy arc-emotion name -> 3G.1 tag, so the fixed table's answer is
#: judged by the same tag rules when no tag was recorded.
LEGACY_TAG = {
    "weary-striving": "exhaustion", "hurt": "pain", "stuck": "pain",
    "wary": "worry", "resigned": "exhaustion", "hopeful-cautious": "hope",
    "curious": "worry", "uncertain": "worry", "determined": "resolve",
    "proud-joyful": "joy", "invited-joyful": "joy",
}


def emotion_tag(shot_or_contract):
    """The 3G.1 Emotion tag on a shot or its contract, or "" when absent.

    The beat sheet's Emotion column is the sentence's own tag; the fixed
    twelve-beat table is only the fallback (3G.6 required change).
    """
    if not isinstance(shot_or_contract, dict):
        return ""
    c = shot_or_contract.get("contract") \
        if isinstance(shot_or_contract.get("contract"), dict) else shot_or_contract
    for key in ("emotion_tag", "emotion", "tag"):
        t = _norm(c.get(key))
        if t in EMOTION_TAGS:
            return t
    return ""


def emotion_intensity(shot_or_contract, default=2):
    """The 3G.1 intensity 1..3 on a shot or contract (default: plain to see)."""
    if not isinstance(shot_or_contract, dict):
        return default
    c = shot_or_contract.get("contract") \
        if isinstance(shot_or_contract.get("contract"), dict) else shot_or_contract
    for key in ("intensity", "emotion_intensity"):
        if c.get(key) is not None:
            return _intensity(c.get(key), default)
    return default


def line_emotion(story_stage, lyric_text="", beats=None, shot=None):
    """The emotion the FACE should carry for this shot's line.

    The sentence's Emotion Track tag is read first (3G.1, passed as ``shot``
    or ``shot["contract"]``); the fixed twelve-beat table is the fallback.
    A pain line (lyric text carries a pain keyword) forces a non-joyful
    emotion no matter the beat; a joyful beat keeps its joyful emotion only
    on a non-pain line. Unknown stage fails closed as "wary".
    """
    tag = emotion_tag(shot)
    if tag:
        return tag
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
    if not face_allowance(emotion):
        cue = EMOTION_CUES.get(_norm(emotion), "a steady gaze")
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
    return emotion in JOYFUL or emotion in FEELING_TAGS


#: 3G.1 facial cues per tag, compressed to the six cue slots (eyes, brows,
#: mouth, smile or no smile, teeth showing or not, tears). Fed to the
#: lip-sync picture prompt so the start "looks" like its line (lever 1).
TAG_EXPRESSION = {
    "pain": "eyes glassy or shut, brows drawn up and together, mouth pressed "
            "or trembling, no smile, no teeth, tears at intensity 3",
    "worry": "eyes searching, brows knit, lips pressed, no smile, no teeth",
    "exhaustion": "heavy lids, slack brows, mouth slightly open, shoulders "
                  "low, no smile, no teeth",
    "anger": "hard eyes, brows down, jaw set, no smile",
    "hope": "eyes lifting, brows soft, corners of the mouth just rising, "
            "small closed smile, no teeth",
    "relief": "eyes closing then opening, brows released, a breath out, small "
              "smile, no teeth",
    "joy": "bright eyes, raised cheeks, open smile",
    "pride": "chin up, steady eyes, small closed smile, no teeth",
    "tenderness": "soft eyes, head slightly tilted, soft closed smile, no teeth",
    "resolve": "level eyes, brows set, mouth firm, no smile, no teeth",
}


def picture_expression(emotion, intensity=2):
    """The facial wording a lip-sync picture prompt carries for its line.

    Lever 1 (3G.6): the sentence's own emotion and cues, never one template
    for every line. Lever 2: on a pain-side tag at intensity 2 or 3, one step
    stronger than the tag so the take starts further from a grin. Returns ""
    for an unknown emotion (the caller then has no expression to write).
    """
    tag = emotion if emotion in EMOTION_TAGS else LEGACY_TAG.get(_norm(emotion), "")
    if not tag:
        return ""
    text = TAG_EXPRESSION.get(tag, "")
    strong = stronger_direction(tag, intensity)
    return (text + ", " + strong) if strong else text


def stronger_direction(emotion, intensity=2):
    """Lever 2 (3G.6): extra picture wording on a pain-side line.

    Pain, worry, exhaustion and resolve at intensity 2 or 3 are drawn one
    step stronger than the tag: mouth corners clearly down, brows drawn, no
    teeth. Returns "" for every other tag or intensity.
    """
    if _norm(emotion) in STRONGER_TAGS and _intensity(intensity) in (2, 3):
        return STRONGER_DIRECTION
    return ""


def takes_for_piece(emotion, intensity=2):
    """Lever 3 (3G.6): two takes of every pain-line piece, one otherwise.

    "Pain-line piece" is the same four tags lever 2 names — pain, worry,
    exhaustion, resolve — at any intensity. Stays inside the two-try rule, so
    never more than two; ``intensity`` is accepted so callers pass the row's
    value once and read both levers from it.
    """
    tag = emotion if emotion in EMOTION_TAGS else LEGACY_TAG.get(_norm(emotion), "")
    return 2 if tag in STRONGER_TAGS else 1


REMAKE_LADDER = ("the other take", "a new picture one step stronger",
                 "plan the piece again so it ends before the drift")


def remake_steps(drift_start_s=None):
    """Lever 5 (3G.6), in order. ``drift_start_s`` names the second the
    drift began, so the replan step knows where the piece must end."""
    steps = list(REMAKE_LADDER)
    if drift_start_s is not None:
        steps[-1] += " (before %.2fs)" % float(drift_start_s)
    return steps


# ---------------------------------------------------------------- QC hook ---
def _frame_smiles(frame):
    """A frame shows a smile (detector or stub shape). Teeth are separate."""
    return frame.get("happy") is True or frame.get("smile") is True


def _frame_teeth(frame):
    return frame.get("teeth") is True


def _frame_pinched(frame):
    return frame.get("pinched") is True or frame.get("anxious") is True \
        or frame.get("brows_pinched") is True


def _frame_shows_tag(frame, tag):
    """True / False when the frame answers; None when it carries no signal."""
    if "tagged" in frame:
        return frame.get("tagged") is True
    if "emotion" in frame:
        seen = _norm(str(frame.get("emotion")))
        return bool(seen) and (seen == tag or tag in seen)
    if "happy" in frame or "smile" in frame:
        return frame.get("happy") is True or frame.get("smile") is True
    return None


def _longest_run(flags):
    """(start, length) of the longest True run in ``flags``."""
    best = (0, 0)
    run_start, run = 0, 0
    for i, flag in enumerate(flags):
        if flag:
            if run == 0:
                run_start = i
            run += 1
            if run > best[1]:
                best = (run_start, run)
        else:
            run = 0
    return best


def _emotion_hold(sid, tag, intensity, frames):
    """3G.6 Emotion Hold on a tagged lip-sync take: both directions.

    Pain side: a smile or teeth-grin held for half a second or more fails.
    Feeling side: the tagged feeling in at least half the frames, and no
    pinched brows held through most of the piece. Returns findings.
    """
    hold = max(1, HOLD_FRAMES)                       # 2 frames at 4 fps
    if tag in NO_SMILE_TAGS:
        # 3G.1: anger's teeth are "clenched at intensity 3 only", so a bare
        # teeth flag there is not by itself the grin this check hunts.
        teeth_counts = not (tag == "anger" and intensity >= 3)
        bad = [(_frame_smiles(f)
                or (teeth_counts and _frame_teeth(f))) for f in frames]
        start, run = _longest_run(bad)
        if run >= hold:
            return [{
                "shot_id": sid, "code": REASON_EMOTION_DRIFT,
                "severity": SEVERITY_MAJOR if intensity >= 2 else SEVERITY_MEDIUM,
                "drift_start_s": round(start / float(FPS_CONTACT_SHEET), 2),
                "detail": "a smile or teeth-grin held %.2fs under a %s line"
                          % (run / float(FPS_CONTACT_SHEET), tag),
                "frame_source": frames[start].get("source", "stub"),
            }]
        return []
    # feeling side (hope, relief, joy, pride, tenderness)
    answers = [_frame_shows_tag(f, tag) for f in frames]
    known = [a for a in answers if a is not None]
    if known and sum(1 for a in known if a) * 2 < len(known):
        first_missing = next(i for i, a in enumerate(answers) if a is False)
        return [{
            "shot_id": sid, "code": REASON_EMOTION_DRIFT,
            "severity": SEVERITY_MAJOR if intensity >= 2 else SEVERITY_MEDIUM,
            "drift_start_s": round(first_missing / float(FPS_CONTACT_SHEET), 2),
            "detail": "the %s feeling shows in %d of %d frames (needs half)"
                      % (tag, sum(1 for a in known if a), len(known)),
            "frame_source": frames[first_missing].get("source", "stub"),
        }]
    pinched = [_frame_pinched(f) for f in frames]
    start, run = _longest_run(pinched)
    if pinched and run * 2 > len(pinched):           # held through most
        return [{
            "shot_id": sid, "code": REASON_EMOTION_DRIFT,
            "severity": SEVERITY_MAJOR if intensity >= 2 else SEVERITY_MEDIUM,
            "drift_start_s": round(start / float(FPS_CONTACT_SHEET), 2),
            "detail": "pinched, anxious brows held through a %s line" % tag,
            "frame_source": frames[start].get("source", "stub"),
        }]
    return []


def qc_frame_gate(shots, frames_by_shot, lyrics=None):
    """The Emotion Hold check on every take (3G.6, N-118).

    A shot carrying a 3G.1 Emotion tag is judged by ``_emotion_hold``: both
    directions, the second the drift starts, and ``EMOTION_DRIFT`` (MAJOR at
    intensity 2 or 3, MEDIUM at 1). A shot with no tag is a storyboard card
    and keeps the older G6 judgment: a happy face under a pain line fails
    ``FACE_EMOTION_MISMATCH``. ponytail: legacy branch removed once every
    caller passes the sentence's Emotion tag.

    shots: shot dicts (shot_id, story_stage, contract with lyric_text,
    visible_emotion, and the 3G.1 emotion tag + intensity when known).
    frames_by_shot: {shot_id: [frame dicts]} — the whole-frame contact sheet,
    4 frames per second. A frame carries the detector's read ({"happy",
    "teeth", "pinched", "tagged", "emotion"}) or the stub {"happy": bool};
    "source" is "detector" | "stub".
    lyrics: optional {lyric_line_id: text} for shots whose contract lacks
    lyric_text.

    Returns {outcome, reason_code, severity, findings[], steps}.
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
        frames = [f for f in (frames_by_shot or {}).get(sid) or []
                  if isinstance(f, dict)]
        if not frames:
            continue
        declared = _norm(contract.get("emotion_tag") or contract.get("tag"))
        if declared and declared not in EMOTION_TAGS:
            # 3G.1: every beat-sheet row carries one of the ten tags, or the
            # sheet is refused EMOTION_MISSING. Fail closed here too (3J.1
            # item 15: a check that could not run is MAJOR).
            findings.append({
                "shot_id": sid, "code": REASON_EMOTION_MISSING,
                "severity": SEVERITY_MAJOR,
                "detail": "the Emotion Track tag %r is not one of the ten "
                          "(3G.1)" % declared,
            })
            continue
        tag = emotion_tag(shot)
        if tag:
            findings.extend(_emotion_hold(sid, tag,
                                          emotion_intensity(shot), frames))
            continue
        # storyboard card: no Emotion Track tag, older G6 judgment only.
        emotion = _norm(contract.get("visible_emotion")) \
            or line_emotion(shot.get("story_stage"), lyric)
        if is_pain_line(lyric) and emotion in JOYFUL:
            emotion = "hurt"
        if face_allowance(emotion) or not is_pain_line(lyric):
            continue
        for frame in frames:
            if _frame_smiles(frame):
                findings.append({
                    "shot_id": sid, "code": REASON_HAPPY_PAIN,
                    "severity": (SEVERITY_MAJOR
                                 if emotion_intensity(shot) >= 2
                                 else SEVERITY_MEDIUM),
                    "detail": "happy/smiling face sampled under a pain line "
                              "(emotion=%s, line=%r)"
                              % (emotion, lyric[:60]),
                    "frame_source": frame.get("source", "stub"),
                })
                break   # one finding per shot is enough to fail it
    severity = SEVERITY_MAJOR if any(
        f.get("severity") == SEVERITY_MAJOR for f in findings) else (
        SEVERITY_MEDIUM if findings else None)
    # S-39: only MAJOR stops and repairs; MEDIUM passes and is logged.
    blocked = severity == SEVERITY_MAJOR
    return {
        "outcome": "rejected" if blocked else "ok",
        "reason_code": findings[0]["code"] if blocked
        else "G6_FACE_GATES_PASS",
        "severity": severity,
        "findings": findings,
        "steps": ["face_emotion_match", "emotion_hold"],
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
    # 9. the sentence's Emotion Track tag wins over the fixed table (3G.6)
    tagged = {"shot_id": "T1", "story_stage": "vindication",
              "contract": {"emotion_tag": "pain", "intensity": 3,
                           "lyric_text": "you set it down and came home"}}
    check("tag beats the beat table",
          line_emotion("vindication", "", shot=tagged) == "pain")
    # 10. Emotion Hold, pain side: a grin held two frames fails, MAJOR at 3
    pain_take = dict(tagged)
    grins = ([{"happy": False}] * 8 + [{"happy": True}] * 4
             + [{"happy": False}] * 8)
    res = qc_frame_gate([pain_take], {"T1": grins})
    check("held grin fails the hold",
          res["outcome"] == "rejected"
          and res["findings"][0]["code"] == REASON_EMOTION_DRIFT, res)
    check("drift second recorded",
          res["findings"][0]["drift_start_s"] == 2.0,
          res["findings"][0]["drift_start_s"])
    check("MAJOR at intensity 3",
          res["findings"][0]["severity"] == SEVERITY_MAJOR, res["severity"])
    # 11. one frame of grin is under half a second: passes
    blip = [{"happy": False}] * 8 + [{"happy": True}] + [{"happy": False}] * 7
    check("one-frame grin passes", qc_frame_gate([pain_take], {"T1": blip})
          ["outcome"] == "ok")
    # 12. intensity 1 lowers the same drift to MEDIUM
    soft = {"shot_id": "T2", "contract": {"emotion_tag": "pain", "intensity": 1}}
    check("MEDIUM at intensity 1",
          qc_frame_gate([soft], {"T2": grins})["findings"][0]["severity"]
          == SEVERITY_MEDIUM)
    # 13. Emotion Hold, feeling side: a joy line needs the feeling in half
    joy_take = {"shot_id": "T3", "contract": {"emotion_tag": "joy",
                                              "intensity": 2}}
    blank = [{"tagged": False}] * 10
    check("missing joy fails the hold",
          qc_frame_gate([joy_take], {"T3": blank})["outcome"] == "rejected")
    check("joy in half the frames passes",
          qc_frame_gate([joy_take], {"T3": [{"tagged": True}] * 5
                                     + [{"tagged": False}] * 5})["outcome"]
          == "ok")
    # 14. pinched brows through most of a joyful piece fail
    pinched = [{"tagged": True, "pinched": True}] * 9 + [{"tagged": True}] * 3
    check("pinched brows held fail",
          qc_frame_gate([joy_take], {"T3": pinched})["outcome"] == "rejected")
    # 15. levers: stronger start, two takes, remake ladder order
    check("pain at 2 drawn stronger",
          stronger_direction("pain", 2) == STRONGER_DIRECTION)
    check("pain at 1 not stronger", stronger_direction("pain", 1) == "")
    check("joy never stronger", stronger_direction("joy", 3) == "")
    check("two takes of a pain piece", takes_for_piece("pain", 3) == 2)
    check("one take of a joy piece", takes_for_piece("joy", 3) == 1)
    check("remake ladder order",
          remake_steps(4.25)[0] == "the other take"
          and remake_steps(4.25)[1].startswith("a new picture")
          and remake_steps(4.25)[2].endswith("(before 4.25s)"),
          remake_steps(4.25))
    # 16. one picture template for every line is refused: pain vs joy differ
    check("expression follows the tag",
          picture_expression("pain", 3) != picture_expression("joy", 2)
          and "no teeth" in picture_expression("pain", 3),
          picture_expression("pain", 3))

    print("face_emotion selftest: %s (%d failures)"
          % ("PASS" if not fails else "FAIL", len(fails)))
    for f in fails:
        print(" -", f)
    return 0 if not fails else 1


if __name__ == "__main__":
    import sys
    sys.exit(selftest())
