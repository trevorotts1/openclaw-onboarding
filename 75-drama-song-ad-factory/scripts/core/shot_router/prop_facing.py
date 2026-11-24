"""prop_facing.py: a prop faces its user, and the camera moves for an insert (N-120).

Section 3P. The Shot Router's part of Prop Facing:

* P1 a prop faces its user (the reading side toward the eyes of the person
  using it);
* P2 the camera gets what a person standing there would really see;
* P3 when the viewer must read it, the camera moves, not the prop: the router
  adds an insert shot, over the user's shoulder or from the user's side, and
  that shot carries the exact words;
* P4 a prop offered to someone turns to them as it is handed over;
* P5 something made to be shown may face the camera (a wall sign, a framed
  diploma, a card held up, an end card), named by the text record;
* P6 a person looks at what they read.

The text record gains three fields per written object: ``user``, ``faces``
(``user``, ``camera`` or ``other_person``) and ``viewer_must_read`` (bool).
Rule T-1 is narrowed here: a prop carries its real words on the side its user
reads, and the camera must read them only in an insert shot or for a rule P5
prop. Everywhere else, a prop whose words the camera cannot read is correct,
not blank.

The router never turns a prop toward the lens. The calibrated check that reads
a picture (PROP_FACES_CAMERA, PROP_TURNED_TO_CAMERA, INSERT_WRONG_SIDE) is
owned by the picture check unit; this module supplies the fixed sentences it
reads against, its known-good/known-bad calibration, and the insert shot.

Stdlib only. No network, no spend, no picture.
"""
from __future__ import annotations

from .common import ShotRouterError

PROP_FACING_RULES = (
    ("P1", "A prop faces its user: the reading side is toward the eyes of the "
           "person using it"),
    ("P2", "The camera gets what a person standing there would really see: the "
           "back of the phone, the back or edge of the page, writing "
           "upside-down and small"),
    ("P3", "When the viewer must read it, the camera moves, not the prop: an "
           "insert shot over the user's shoulder or from the user's side "
           "carries the exact words"),
    ("P4", "A prop offered to someone turns to them as it is handed over"),
    ("P5", "Something made to be shown may face the camera: a wall sign, a "
           "framed diploma, a card held up to another person or the viewer, "
           "an end card"),
    ("P6", "A person looks at what they read: eyes on the page means the page "
           "faces the eyes"),
)

#: The values ``faces`` may take in the text record.
FACES_VALUES = frozenset({"user", "camera", "other_person"})

#: Reading-side nouns per prop kind, used only to phrase the fixed sentence.
READING_SIDE = {
    "phone": "screen",
    "tablet": "screen",
    "calculator": "display and keys",
    "page": "printed side",
    "form": "printed side",
    "letter": "written side",
    "bill": "printed side",
    "envelope": "addressed side",
    "diploma": "printed side",
    "sign": "printed side",
    "card": "printed side",
    "book": "open page",
}

BACK_SIDE = {
    "phone": "the back of the phone",
    "tablet": "the back of the tablet",
    "calculator": "the far side of the calculator",
    "envelope": "the blank back of the envelope",
}
DEFAULT_BACK = "the back or the edge of it"


class PropFacingError(ShotRouterError):
    pass


def _word(value):
    return str(value or "").strip()


def validate_text_object(prop):
    """One text-record row, checked for the three Prop Facing fields.

    Returns the normalised row. Raises PROP_FACING_FIELDS_INVALID when a written
    object has no user, no facing or no ``viewer_must_read`` decision, because
    the router cannot place an insert shot without them.
    """
    if not isinstance(prop, dict):
        raise PropFacingError("PROP_FACING_FIELDS_INVALID",
                              "a text-record row must be an object")
    user = _word(prop.get("user"))
    faces = _word(prop.get("faces")).lower()
    must_read = prop.get("viewer_must_read")
    if not user:
        raise PropFacingError(
            "PROP_FACING_FIELDS_INVALID",
            "written object %r has no user" % prop.get("id"))
    if faces not in FACES_VALUES:
        raise PropFacingError(
            "PROP_FACING_FIELDS_INVALID",
            "written object %r faces %r; must be one of %s"
            % (prop.get("id"), prop.get("faces"), sorted(FACES_VALUES)))
    if not isinstance(must_read, bool):
        raise PropFacingError(
            "PROP_FACING_FIELDS_INVALID",
            "written object %r has no viewer_must_read boolean" % prop.get("id"))
    if faces == "user" and must_read and prop.get("insert_allowed") is False:
        raise PropFacingError(
            "INSERT_WRONG_SIDE",
            "written object %r must be read by the viewer but its insert is "
            "disabled; the prop is never turned to the lens" % prop.get("id"))
    return prop


def t1_camera_must_read(prop):
    """Rule T-1 narrowed: the camera must read the words only here."""
    validate_text_object(prop)
    return bool(prop["viewer_must_read"])


def insert_required(prop):
    """P3: an insert shot is added when the viewer must read a user-facing prop."""
    validate_text_object(prop)
    return bool(prop["viewer_must_read"]) and prop["faces"].lower() == "user"


def _words(prop):
    words = prop.get("words")
    if isinstance(words, (list, tuple)):
        words = " ".join(str(w) for w in words)
    return _word(words)


def facing_sentence(prop):
    """The fixed sentence the Prompt Builder sends for this prop.

    Three forms, chosen by the text record and nothing else: the user-facing
    sentence, the over-the-shoulder insert, and the rule P5 shown-to-camera
    sentence.
    """
    validate_text_object(prop)
    user = _word(prop.get("user"))
    kind = _word(prop.get("kind")).lower()
    words = _words(prop)
    side = READING_SIDE.get(kind, "reading side")
    if prop["faces"].lower() == "camera":
        if not words:
            raise PropFacingError(
                "PICTURE_TEXT_WRONG",
                "rule P5 prop %r faces the camera but carries no words" % prop.get("id"))
        return ("%s faces the camera and its %s reads exactly: “%s”."
                % (_word(prop.get("name")) or "The prop", side, words))
    if insert_required(prop):
        return (f"Seen over {user}'s shoulder, from {user}'s side: the "
                f"{_word(prop.get('name')) or kind or 'prop'} fills the lower "
                f"frame and reads exactly: “{words}”.")
    back = BACK_SIDE.get(kind, DEFAULT_BACK)
    return (f"{user} holds the {_word(prop.get('name')) or kind or 'prop'} "
            f"with its {side} toward {user}'s own face. The camera sees {back}. "
            f"Its words are not visible in this shot.")


def _shot_id(shot, suffix):
    base = shot.get("shot_id") or "shot"
    return "%s-%s" % (base, suffix)


def plan_prop_inserts(shot, *, song_start=None, song_end=None):
    """P3: one insert shot per user-facing prop the viewer must read.

    Insert shots are one-picture shots from their own checked still (rule H1
    of the Clip Sizer), so writing stays correct: a nine-picture clip pins no
    frame and would let the model draw the words itself.
    """
    props = shot.get("text_objects") or []
    inserts = []
    for index, prop in enumerate(props, start=1):
        validate_text_object(prop)
        if not insert_required(prop):
            continue
        user = _word(prop.get("user"))
        inserts.append({
            "shot_id": _shot_id(shot, "insert-%d" % index),
            "beat_id": shot.get("beat_id"),
            "route": "one_picture",
            "rule": "P3",
            "purpose": "insert shot so the viewer reads %r from %s's side"
                       % (_word(prop.get("name")) or prop.get("id"), user),
            "model_role": "story_clip",
            "written_object": prop.get("id"),
            "user": user,
            "faces": "user",
            "viewer_must_read": True,
            "fixed_sentence": facing_sentence(prop),
            "checked_still": True,
            "readable_writing": True,
            "song_window_seconds": [song_start, song_end],
            "notes": ["rule P3: the camera moves, the prop never turns to the lens"],
        })
    return inserts


def attach_inserts(records, shots):
    """Add each shot's Prop Facing insert shots to its route record."""
    by_id = {shot.get("shot_id"): shot for shot in shots}
    for record in records:
        shot = by_id.get(record.get("shot_id")) or {}
        inserts = plan_prop_inserts(
            shot,
            song_start=(record.get("song_window_seconds") or [None, None])[0],
            song_end=(record.get("song_window_seconds") or [None, None])[1],
        )
        if inserts:
            record["insert_shots"] = inserts
    return records


def calibrated_check(judge, known_good, known_bad):
    """The check's calibration gate (section 3P).

    ``judge(picture)`` returns True when the picture obeys Prop Facing. The
    check runs once on a known-good and once on a known-bad picture; if it
    cannot tell them apart it reports itself unavailable and never passes.
    """
    if judge(known_good) is not True:
        raise ShotRouterError(
            "PROP_CHECK_UNAVAILABLE",
            "the Prop Facing check fails its known-good picture; it is "
            "unavailable and never passes")
    if judge(known_bad) is not False:
        raise ShotRouterError(
            "PROP_CHECK_UNAVAILABLE",
            "the Prop Facing check passes its known-bad picture; it is "
            "unavailable and never passes")
    return True
