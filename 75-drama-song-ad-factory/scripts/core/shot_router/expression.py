"""expression.py: the lip-sync picture comes from the matching expression sheet (N-73).

Section 3G.5, binding. The Shot Router's picture list for a lip-sync shot NAMES
the expression sheet that matches the line's emotion as a required reference for
the lip-sync keyframe; the keyframe is made image-to-image from the master, the
scene's wardrobe picture and that sheet. A job whose picture does not carry the
line's emotion is refused BEFORE it is paid for: ``LIPSYNC_EXPRESSION_MISMATCH``.
A sad line is never sung from a smiling picture.

Sheet vocabulary (3G.2): pain uses sad; worry uses worried; exhaustion uses
tired; hope and relief use hopeful; joy uses joyful; resolve and pride use
determined; tenderness uses hopeful. Anger gets an angry sheet; any intensity-3
emotion without an exact sheet gets its own (angry, tender, proud, relieved).

On a pain line at intensity 2 or 3 the picture starts ONE STEP STRONGER than the
tag (3G.6 lever 2): mouth corners clearly down, brows drawn, no teeth. The model
drifts toward the music, so it starts further from the grin.

Stdlib only. No network, no spend.
"""
from __future__ import annotations

from .common import ShotRouterError

LIPSYNC_EXPRESSION_MISMATCH = "LIPSYNC_EXPRESSION_MISMATCH"

#: The seven expression pictures every main character's reference set carries,
#: plus the extras 3G.2 allows. Names match the sheet file stems.
SHEETS = ("neutral", "sad", "worried", "tired", "hopeful", "joyful",
          "determined", "angry", "tender", "proud", "relieved")

#: 3G.2's mapping from the Emotion Track's tags to a sheet.
EMOTION_SHEET = {
    "neutral": "neutral",
    "pain": "sad",
    "worry": "worried",
    "exhaustion": "tired",
    "hope": "hopeful",
    "relief": "hopeful",
    "joy": "joyful",
    "resolve": "determined",
    "pride": "determined",
    "tenderness": "hopeful",
    "anger": "angry",
}

#: Emotions whose picture must start one step stronger (3G.6 lever 2).
PAIN_LIKE = frozenset({"pain", "worry", "exhaustion", "resolve"})
#: Words a picture under a pain-like line must never carry (3G.3).
CONTRADICTING = frozenset({"smiling", "smile", "grin", "grinning", "beaming",
                           "laughing", "cheerful", "teeth"})


def _norm(value):
    return str(value or "").strip().lower().replace("-", "_")


def sheet_for_emotion(emotion, intensity=None):
    """The expression sheet a line's emotion requires (3G.2), or raise."""
    tag = _norm(emotion)
    if tag not in EMOTION_SHEET:
        raise ShotRouterError(
            "EMOTION_UNKNOWN",
            "%r is not an Emotion Track tag; expected one of %s"
            % (emotion, ", ".join(sorted(EMOTION_SHEET))),
        )
    strong = isinstance(intensity, int) and not isinstance(intensity, bool) \
        and intensity >= 3
    if strong and tag == "tenderness":
        return "tender"
    if strong and tag == "pride":
        return "proud"
    if strong and tag == "relief":
        return "relieved"
    return EMOTION_SHEET[tag]


def starts_stronger(emotion, intensity):
    """3G.6 lever 2: a pain-like line at intensity 2 or 3 starts one step harder."""
    tag = _norm(emotion)
    return tag in PAIN_LIKE and isinstance(intensity, int) \
        and not isinstance(intensity, bool) and intensity >= 2


def _refs(record):
    for picture in record.get("pictures") or []:
        if picture.get("kind") in ("lip_sync_keyframe", "keyframe"):
            return picture
    return None


def assign_sheet(record, shot):
    """Name the matching sheet on a lip-sync record; mutate and return it.

    The sheet becomes a required reference of the lip-sync keyframe and is
    written to ``record['lip_sync']['expression_sheet']``.
    """
    if record.get("route") != "lip_sync":
        return record
    sheet = sheet_for_emotion(shot.get("emotion"), shot.get("emotion_intensity"))
    picture = _refs(record)
    if picture is not None:
        refs = picture.setdefault("refs", [])
        token = "expression_sheet:%s" % sheet
        if token not in refs:
            refs.append(token)
        picture["expression_sheet"] = sheet
    lip = record.setdefault("lip_sync", {})
    lip["expression_sheet"] = sheet
    lip["starts_stronger"] = starts_stronger(shot.get("emotion"),
                                             shot.get("emotion_intensity"))
    return record


def apply_sheets(shot_routes, shots):
    """Name the sheet on every lip-sync shot of a run; ``shots`` keyed by id."""
    index = {shot.get("shot_id"): shot for shot in shots or [] if isinstance(shot, dict)}
    for record in shot_routes.get("shots") or []:
        shot = index.get(record.get("shot_id"))
        if shot is not None:
            assign_sheet(record, shot)
    return shot_routes


def validate_lipsync_expression(shot):
    """Refuse a lip-sync picture whose emotion does not match its line (3G.5).

    Fires when the picture was drawn for a different emotion, or when a pain-like
    line's picture is described as smiling or showing teeth.
    """
    line_emotion = shot.get("emotion")
    if not line_emotion:
        raise ShotRouterError(
            LIPSYNC_EXPRESSION_MISMATCH,
            "shot %s has no Emotion Track tag; a lip-sync picture cannot be "
            "chosen without one" % shot.get("shot_id"),
        )
    wanted = sheet_for_emotion(line_emotion, shot.get("emotion_intensity"))
    picture_emotion = shot.get("lip_sync_picture_emotion")
    if picture_emotion:
        got = sheet_for_emotion(picture_emotion, shot.get("lip_sync_picture_intensity"))
        if got != wanted:
            raise ShotRouterError(
                LIPSYNC_EXPRESSION_MISMATCH,
                "shot %s sings %r from a %r picture; the line needs %r"
                % (shot.get("shot_id"), line_emotion, got, wanted),
            )
    words = {_norm(w) for w in (shot.get("lip_sync_picture_words") or [])}
    if _norm(line_emotion) in PAIN_LIKE and words & CONTRADICTING:
        raise ShotRouterError(
            LIPSYNC_EXPRESSION_MISMATCH,
            "shot %s is a %r line but its lip-sync picture carries %s; a sad line "
            "is never sung from a smiling picture"
            % (shot.get("shot_id"), line_emotion,
               ", ".join(sorted(words & CONTRADICTING))),
        )
    return True


def check_before_paid_job(shot):
    """The gate the dispatcher calls before paying for a lip-sync job (3G.5)."""
    return validate_lipsync_expression(shot)
