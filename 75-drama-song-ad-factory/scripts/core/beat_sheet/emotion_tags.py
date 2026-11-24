"""beat_sheet.emotion_tags -- the Emotion Track tag on every script row (N-69).

Section 3G.1: every beat-sheet row carries an emotion, an intensity of 1, 2 or 3,
and six short facial cues. A row without them is refused with EMOTION_MISSING.
Section 3G.3 also refuses a prompt whose words contradict the tag; the word
lists live here so the story-logic review can ask the fit question (3F.3, N-69)
from one place. The 3G.1 table of standard cues a writer starts from lives
here too.

Pure data checks. Stdlib only, no IO, no model call, no mutation.
"""
from __future__ import annotations

from .beat_sheet import EMOTIONS, FACIAL_CUES, INTENSITIES, _defect, _norm

#: one list per emotion, from section 3G.3
CONTRADICTING_WORDS = {
    "pain": ("smiling", "smile", "grin", "grinning", "beaming", "laughing",
             "cheerful", "teeth showing"),
    "worry": ("smiling", "smile", "grin", "grinning", "beaming", "laughing",
              "cheerful", "teeth showing"),
    "exhaustion": ("smiling", "smile", "grin", "grinning", "beaming", "laughing",
                   "cheerful", "teeth showing"),
    "anger": ("smiling", "smile", "grin", "grinning", "beaming", "laughing",
              "cheerful", "teeth showing"),
    "resolve": ("smiling", "smile", "grin", "grinning", "beaming", "laughing",
                "cheerful", "teeth showing"),
    "joy": ("frowning", "scowling", "tearful"),
}

#: pain-line emotions that also cost a second take (3G.6 lever 3)
PAIN_LINE_EMOTIONS = ("pain", "worry", "exhaustion", "resolve")

#: the standard cues a writer starts from (3G.1), one row per emotion
STANDARD_CUES = {
    "pain": {"eyes": "glassed or shut", "brows": "drawn up and together",
             "mouth": "pressed or trembling", "smile": "no", "teeth": "no",
             "tears": "at intensity 3"},
    "worry": {"eyes": "searching", "brows": "knit", "mouth": "lips pressed",
              "smile": "no", "teeth": "no", "tears": "none"},
    "exhaustion": {"eyes": "heavy lids", "brows": "slack", "mouth": "slightly open",
                   "smile": "no", "teeth": "no", "tears": "none"},
    "anger": {"eyes": "hard", "brows": "down", "mouth": "jaw set",
              "smile": "no", "teeth": "clenched at intensity 3", "tears": "none"},
    "hope": {"eyes": "lifting", "brows": "soft", "mouth": "corners just rising",
             "smile": "small, closed", "teeth": "no", "tears": "none"},
    "relief": {"eyes": "closing then opening", "brows": "released",
               "mouth": "a breath out", "smile": "small", "teeth": "no",
               "tears": "none"},
    "joy": {"eyes": "bright", "brows": "raised cheeks", "mouth": "smiling",
            "smile": "yes", "teeth": "at intensity 2 and 3", "tears": "none"},
    "pride": {"eyes": "steady", "brows": "level", "mouth": "chin up",
              "smile": "small, closed", "teeth": "no", "tears": "none"},
    "tenderness": {"eyes": "soft", "brows": "soft", "mouth": "head slightly tilted",
                   "smile": "soft, closed", "teeth": "no", "tears": "none"},
    "resolve": {"eyes": "level", "brows": "set", "mouth": "firm",
                "smile": "no", "teeth": "no", "tears": "none"},
}

#: the fixed list the story review answers about the emotion (3G.1, N-67)
FIT_QUESTIONS = (
    "does each line's emotion fit its words",
    "does the emotion move in a way a viewer would believe from line to line",
)

def standard_cues(emotion):
    """The starting cues for one emotion, or an empty map for an unknown word."""
    return dict(STANDARD_CUES.get(_norm(emotion), {}))


def row_emotion_defects(row, row_id=None):
    """The three columns of section 3G.1 on one row (EMOTION_MISSING)."""
    defects = []
    label = row_id if row_id is not None else row.get("line_id", row.get("row_id"))
    if row.get("emotion") not in EMOTIONS:
        defects.append(_defect("EMOTION_MISSING", "/script-rows/emotion",
                               "row %r has no Emotion Track emotion" % (label,)))
    intensity = row.get("intensity")
    if isinstance(intensity, bool) or intensity not in INTENSITIES:
        defects.append(_defect("EMOTION_MISSING", "/script-rows/intensity",
                               "row %r intensity is not 1, 2 or 3" % (label,)))
    cues = row.get("facial_cues")
    if not isinstance(cues, dict):
        defects.append(_defect("EMOTION_MISSING", "/script-rows/facial_cues",
                               "row %r has no facial cues" % (label,)))
    else:
        missing = [key for key in FACIAL_CUES
                   if not (isinstance(cues.get(key), str) and cues.get(key).strip())]
        if missing:
            defects.append(_defect("EMOTION_MISSING", "/script-rows/facial_cues",
                                   "row %r is missing the cue(s): %s"
                                   % (label, ", ".join(missing))))
    return defects


def emotion_rows_defects(rows):
    """Every row's tag, in order."""
    defects = []
    for index, row in enumerate(rows if isinstance(rows, list) else []):
        if isinstance(row, dict):
            defects.extend(row_emotion_defects(row, row.get("line_id", index)))
    return defects


def fit_defects(row, line_text=None):
    """The review's fit question: does the tag contradict the line's words (3G.3)?"""
    words = " " + _norm(line_text if line_text is not None else row.get("line")) + " "
    emotion = row.get("emotion")
    defects = []
    for word in CONTRADICTING_WORDS.get(emotion, ()):
        if " %s " % word in words:
            defects.append(_defect(
                "EMOTION_CONTRADICTS", "/script-rows/emotion",
                "an emotion of %r does not carry the word %r" % (emotion, word),
                line_id=row.get("line_id")))
    return defects


def error_charge_emotions(rows):
    """The emotions that need two takes on a lip-sync piece (3G.6 lever 3)."""
    return sorted({row.get("emotion") for row in (rows or [])
                   if isinstance(row, dict) and row.get("lip_sync") is True
                   and row.get("emotion") in PAIN_LINE_EMOTIONS})


def _selfcheck():
    row = {"line_id": "L1", "emotion": "pain", "intensity": 2,
           "facial_cues": {"eyes": "glass", "brows": "drawn", "mouth": "pressed",
                           "smile": "no", "teeth": "no", "tears": "at intensity 3"},
           "line": "I work all day"}
    assert row_emotion_defects(row) == []
    broken = dict(row, intensity=4)
    assert row_emotion_defects(broken)[0]["code"] == "EMOTION_MISSING"
    assert fit_defects(dict(row, line="I work all day and smile"))[0]["code"] == "EMOTION_CONTRADICTS"
    assert fit_defects(dict(row, emotion="joy", line="no frowning now"))[0]["code"] == "EMOTION_CONTRADICTS"
    assert error_charge_emotions([dict(row, lip_sync=True)]) == ["pain"]
    assert standard_cues("pain")["smile"] == "no"
    assert standard_cues("unknown") == {}


if __name__ == "__main__":
    _selfcheck()
    print("beat_sheet.emotion_tags selfcheck: OK")
