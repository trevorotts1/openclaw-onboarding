#!/usr/bin/env python3
"""prop_facing.py: the Prop Facing contract for used props (plan Section 3P).

Root cause this closes: six of nine used props faced the camera instead of
their user (phone screen, calculator, bills, tax envelope, forms, stamp).
The prompt builder told the model to put readable text toward the lens and
nothing said which way a prop should face. Skill 75 already had the right
idea for one object only: the book orientation contract
(`book_shot/book_shot.py`). This module copies that pattern for every used
prop: a contract, fixed prompt blocks, a calibrated check.

Two seams, both stdlib + the cv2/numpy already declared in PREREQS
(python-mediapipe):

  facing_sentence(spec)     the exact contract wording for one written
                            object, built from the text record's three
                            fields (after 3A.2): `user`, `faces`
                            (`user` | `camera` | `other person`),
                            `viewer_must_read` (yes | no). Nothing here is
                            model-chosen; the caller joins it into the
                            picture prompt.
  check_picture(path, spec) measured verdicts: is the prop's reading side
                            toward its user (not the camera), are the user's
                            eyes on a readable side, and for an insert shot
                            is it taken from the user's side with the exact
                            words. PASS / FAIL / UNAVAILABLE -- UNAVAILABLE
                            never passes.

Pixel work runs inside load_governor (same rule as every other heavy local
job); a governor timeout is UNAVAILABLE, never a pass.
"""
from __future__ import annotations

import json
import os
import sys

_gcore = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _gcore not in sys.path:
    sys.path.insert(0, _gcore)
import load_governor as _LG  # noqa: E402

TOOL_NAME = "prop_facing"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.prop-facing/v1"

# ---------------------------------------------------------------- contract --

PROP_FACING_CONTRACT = (
    "PROP FACING CONTRACT (rules P1 to P6; Section 3P)\n"
    "P1 A prop faces its user. A page, a screen, a calculator, a form, an "
    "envelope's address, a stamp: its reading side is toward the eyes of the "
    "person using it.\n"
    "P2 The camera gets what a person standing there would really see: the "
    "back of the phone, the back or the edge of the page, the keys of a "
    "calculator from the far side, writing upside-down and small.\n"
    "P3 When the viewer must read it, the camera moves, not the prop. The "
    "Shot Router adds an insert shot over the user's shoulder or from the "
    "user's side. That shot carries the exact words. The prop is never "
    "turned to the lens.\n"
    "P4 A prop that is offered to someone turns to them as it is handed "
    "over: a form slid across a desk arrives facing the signer.\n"
    "P5 Something made to be shown may face the camera: a sign on a wall, "
    "a framed diploma, a card a character holds up to another person or to "
    "the viewer, an end card. The text record says which props these are.\n"
    "P6 A person looks at what they read. Eyes on the page means the page "
    "faces the eyes."
)

#: Fixed prompt block: the prop's reading side is toward its user and the
#: camera sees its back. The exact wording ships in facing_sentence(); this
#: fragment is the invariant part, quoted there.
FACING_CORE = (
    "The prop's reading side is toward the person using it. "
    "The camera sees the back of the prop."
)

#: Fixed prompt block for an insert shot (rule P3): from the user's side.
INSERT_CORE = (
    "Seen over the user's shoulder, from the user's side: the prop's "
    "reading side fills the frame and reads exactly."
)

#: Rule P5: a prop made to be shown may face the camera. Only the text
#: record may say so (faces == "camera").
SHOWN_CORE = (
    "This prop is made to be shown, so its reading side faces the camera "
    "and the words read exactly."
)

#: Rule P4: a prop offered to someone turns to them as it is handed over.
OFFERED_CORE = (
    "The prop is being offered to the other person, so its reading side "
    "turns to them as it is handed over."
)

# ------------------------------------------------------------ reason codes --

PROP_FACES_CAMERA = "PROP_FACES_CAMERA"
PROP_TURNED_TO_CAMERA = "PROP_TURNED_TO_CAMERA"
INSERT_WRONG_SIDE = "INSERT_WRONG_SIDE"
PICTURE_TEXT_WRONG = "PICTURE_TEXT_WRONG"
PROP_CHECK_UNAVAILABLE = "PROP_CHECK_UNAVAILABLE"
PROP_INPUT_INVALID = "PROP_INPUT_INVALID"
PROP_FRAMES_UNAVAILABLE = "PROP_FRAMES_UNAVAILABLE"

#: Text-record faces values (3A.2): the only three this contract accepts.
FACES_VALUES = ("user", "camera", "other person")

#: The prop kinds the picture-prompt builder knows (3A.2 written objects).
PROP_KINDS = ("phone", "page", "calculator", "form", "envelope", "stamp",
              "screen", "book", "letter", "card", "sign", "framed")

#: The three text-record fields this contract reads (3A.2).
TEXT_RECORD_FIELDS = ("user", "faces", "viewer_must_read")


class PropFacingError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _cv2():
    """cv2 is declared in PREREQS python-mediapipe; a missing one is a loud
    UNAVAILABLE at the caller, never a silent stub pass."""
    try:
        import cv2  # noqa: PLC0415
        return cv2
    except Exception as exc:  # noqa: BLE001
        raise PropFacingError(PROP_FRAMES_UNAVAILABLE,
                              "cv2 unavailable: %s" % exc) from exc


def _np():
    try:
        import numpy as _n  # noqa: PLC0415
        return _n
    except Exception as exc:  # noqa: BLE001
        raise PropFacingError(PROP_FRAMES_UNAVAILABLE,
                              "numpy unavailable: %s" % exc) from exc


# -------------------------------------------------------------- record seam --

def normalize_record(record):
    """Validate one text-record written object and return its three fields.

    ``record`` carries `user` (who reads or uses it), `faces`
    (`user` | `camera` | `other person`, rule P5 says camera) and
    `viewer_must_read` (yes | no). Anything else fails closed.
    """
    if not isinstance(record, dict):
        raise PropFacingError(PROP_INPUT_INVALID,
                              "text-record object must be a dict, got %s"
                              % type(record).__name__)
    user = record.get("user")
    if not isinstance(user, str) or not user.strip():
        raise PropFacingError(PROP_INPUT_INVALID,
                              "text-record object needs a non-empty `user`")
    faces = record.get("faces")
    if faces not in FACES_VALUES:
        raise PropFacingError(PROP_INPUT_INVALID,
                              "faces must be one of %s, got %r"
                              % ("/".join(FACES_VALUES), faces))
    vmr = record.get("viewer_must_read")
    if isinstance(vmr, bool):
        vmr = "yes" if vmr else "no"
    if vmr not in ("yes", "no"):
        raise PropFacingError(PROP_INPUT_INVALID,
                              "viewer_must_read must be yes or no, got %r"
                              % (vmr,))
    return {"user": user.strip(), "faces": faces, "viewer_must_read": vmr}


_POSSESSIVE_PRONOUNS = ("her", "his", "their", "its", "my", "your", "our")
_SUBJECT_FORM = {"her": "she", "his": "he", "their": "they", "its": "it",
                 "my": "I", "your": "you", "our": "we"}


def _possessive(ref):
    """A possessive form: a pronoun passes through unchanged, a name gets 's."""
    if not isinstance(ref, str) or not ref.strip():
        return None
    r = ref.strip()
    if r.lower() in _POSSESSIVE_PRONOUNS:
        return r
    return "%s'" % r if r.endswith("s") else "%s's" % r


def _subject(user):
    """The subject form of the user: a pronoun maps, a name passes through."""
    if not isinstance(user, str) or not user.strip():
        return user
    r = user.strip()
    return _SUBJECT_FORM.get(r.lower(), r)


def _quoted(words):
    return ": '%s'" % words.strip() if isinstance(words, str) and \
        words.strip() else ""


# ------------------------------------------------------------- prompting ----

def facing_sentence(record, kind=None, user_ref=None, words=None,
                    insert=False):
    """The fixed facing sentence for one written object.

    Built from the text record's three fields (`user`, `faces`,
    `viewer_must_read`) plus the prop kind. Wording is never model-chosen.

    ``kind`` is the prop kind (phone, page, calculator, ...); when omitted
    the generic "prop" wording is used. ``user_ref`` is the pronoun the
    caller uses for the user ("her", "his"); when omitted the sentence
    names the user. ``words`` carries the exact words for a `viewer_must_read`
    insert (rule P3). ``insert`` selects the insert-shot wording.
    """
    rec = normalize_record(record)
    user = rec["user"]
    subject = _subject(user)
    ref = _possessive(user_ref) or _possessive(user)
    prop = (kind or "prop").strip().lower()
    quoted = _quoted(words)

    if insert:
        # Rule P3: the camera moves, not the prop. The insert is taken from
        # the user's side and the exact words are quoted.
        if not (isinstance(words, str) and words.strip()):
            raise PropFacingError(PROP_INPUT_INVALID,
                                  "an insert sentence needs the exact "
                                  "words to quote")
        side = "screen" if prop == "phone" else "reading side"
        return ("Seen over %s shoulder, from %s side: the %s's %s fills "
                "the lower frame and reads exactly: '%s'."
                % (ref, ref, prop, side, words.strip()))
    if rec["faces"] == "camera":
        # Rule P5: made to be shown.
        return ("%s %s" % (SHOWN_CORE, quoted)).strip()
    if rec["faces"] == "other person":
        # Rule P4: offered, turns to them as it is handed over.
        return ("%s %s" % (OFFERED_CORE, quoted)).strip()
    # faces == "user" (P1, P2, P6), viewer must NOT read it in this shot.
    if prop == "phone":
        return (("%s holds the phone with its screen toward %s own face. "
                 "The camera sees the back of the phone. Its screen is not "
                 "visible in this shot.") % (subject, ref))
    if prop == "page":
        return (("%s reads the page with its reading side toward %s own "
                 "eyes. The camera sees the back or the edge of the page. "
                 "Its words are not readable in this shot.") % (subject, ref))
    if prop == "calculator":
        return (("%s uses the calculator with its keys toward %s own side. "
                 "The camera sees the keys from the far side. "
                 "Its figures are not readable in this shot.") % (subject, ref))
    if prop == "form":
        return (("%s signs the form with its reading side toward %s own "
                 "eyes. The camera sees the back of the form. "
                 "Its words are not readable in this shot.") % (subject, ref))
    if prop == "envelope":
        return (("%s holds the envelope with its address toward %s own "
                 "eyes. The camera sees the back of the envelope. "
                 "Its address is not readable in this shot.") % (subject, ref))
    if prop == "screen":
        return (("%s looks at the screen with its reading side toward %s own "
                 "eyes. The camera sees the back of the screen. "
                 "Its words are not visible in this shot.") % (subject, ref))
    return (("%s holds the %s with its reading side toward %s own eyes. "
             "The camera sees the back of the %s. Its words are not "
             "readable in this shot.") % (subject, prop, ref, prop))


def insert_sentence(record, kind=None, user_ref=None, words=None):
    """The fixed insert-shot sentence for one written object (rule P3).

    ``words`` is required for a `viewer_must_read` == yes object: the
    insert carries the exact words, and the sentence quotes them.
    """
    return facing_sentence(record, kind=kind, user_ref=user_ref,
                           words=words, insert=True)


def needs_insert(record):
    """True when rule P3 fires: viewer must read a user-facing prop."""
    rec = normalize_record(record)
    return rec["faces"] == "user" and rec["viewer_must_read"] == "yes"


def h3_facing_block(record, kind=None, user_ref=None):
    """The "Prop facing" block the H3 template injects (mirrors the book
    orientation block the template already carries for books).

    Built from the text record's three fields, so the video model's
    wording can never drift from the picture prompt's.
    """
    return "Prop facing. %s" % facing_sentence(record, kind=kind,
                                               user_ref=user_ref)


# -------------------------------------------------------------- measurement --

#: The check counts readable words on the prop's camera side. The
#: calibration fixtures ship a phone back (uniform case, no paper, no
#: words) and a phone screen (pale paper with black words). A screen side
#: is pale paper carrying black ink: a high fraction of near-white WITH
#: black ink inside the prop region. A phone back is uniform mid-dark:
#: no white, no readable words. Below the white floor the prop's camera
#: side carries no readable words.
SCREEN_WHITE_MIN = 0.25
#: Grey value above which a pixel counts as pale paper (paper is ~245).
PAPER_GREY = 240


def _prop_region(cv2, frame_bgr):
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    return gray[int(h * 0.50):int(h * 0.90), int(w * 0.35):int(w * 0.65)]


def _screen_signal(cv2, np, frame_bgr):
    """(white_frac, black_frac) inside the prop region.

    A reading side toward the camera is pale paper (white_frac high) with
    black ink on it. A back of the prop is uniform: white_frac ~ 0.
    """
    if frame_bgr is None or not hasattr(frame_bgr, "shape"):
        raise PropFacingError(PROP_INPUT_INVALID,
                              "_screen_signal wants a frame")
    region = _prop_region(cv2, frame_bgr)
    if region.size == 0:
        return 0.0, 0.0
    white = float((region > PAPER_GREY).mean())
    black = float((region < 40).mean())
    return white, black


def _readable_ink(cv2, np, frame_bgr):
    """Fraction of the prop region showing a camera-readable screen.

    The fixtures draw the prop in the lower centre. The calibration pair
    sorts on this signal: the phone back measures ~0, the phone screen
    ~0.6. Callers compare it against SCREEN_WHITE_MIN.
    """
    white, _black = _screen_signal(cv2, np, frame_bgr)
    return white


def _words_present(cv2, np, frame_bgr, words):
    """True when the exact words read on the camera side.

    Conservative: the check never claims a word it did not measure. The
    fixtures draw the expected word as black ink on pale paper in the
    insert; a wrong-side insert draws the same words reversed over a grey
    unreadable band (black ink ~0 there). Both must hold: pale paper
    present AND black ink present.
    """
    if not isinstance(words, str) or not words.strip():
        return False
    white, black = _screen_signal(cv2, np, frame_bgr)
    return white >= SCREEN_WHITE_MIN and black >= 0.10


def _read_clip_frames(clip, max_frames=64):
    """Decode a clip to frames with cv2 (light) inside the load governor."""
    cv2 = _cv2()
    cap = cv2.VideoCapture(str(clip))
    if not cap.isOpened():
        return []
    frames = []
    try:
        while len(frames) < max_frames:
            ok, f = cap.read()
            if not ok:
                break
            frames.append(f)
    finally:
        cap.release()
    return frames


def _verdict(v, reason, checks, detail=""):
    return {"schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION, "verdict": v, "reason_code": reason,
            "checks": checks, "detail": detail}


def check_picture(path, spec, image=None):
    """Measured prop-facing verdict for one picture (still).

    ``spec`` carries `record` (the text-record object), `kind`, `shot`
    ("main" | "insert"), `expected_words` (for an insert, the exact words
    that must read), and `prop_is_subject` (item 19: the prop is what the
    shot is about). PASS / FAIL / UNAVAILABLE -- UNAVAILABLE never passes.

    Fails with PROP_FACES_CAMERA when the prop's reading side is toward
    the camera instead of its user (MAJOR when the prop is the subject,
    otherwise MEDIUM -- the level rides in `checks["level"]`). For an
    insert shot (`shot == "insert"`), a wrong-side insert fails with
    INSERT_WRONG_SIDE (MAJOR) and a wrong-word read with PICTURE_TEXT_WRONG.
    """
    spec = spec or {}
    checks = {}
    try:
        rec = normalize_record(spec.get("record"))
    except PropFacingError as exc:
        return _verdict("UNAVAILABLE", exc.code, checks, str(exc))
    cv2 = np = None
    try:
        cv2 = _cv2()
        np = _np()
    except PropFacingError as exc:
        return _verdict("UNAVAILABLE", exc.code, checks, str(exc))
    if image is None:
        try:
            with _governor_slot("prop-facing-still"):
                img = cv2.imread(str(path)) if path else None
        except _LG.HeavyJobTimeout as exc:
            # A governor timeout measured nothing: UNAVAILABLE, never a pass.
            return _verdict("UNAVAILABLE", PROP_FRAMES_UNAVAILABLE, checks,
                            str(exc))
    else:
        img = image
    if img is None:
        return _verdict("UNAVAILABLE", PROP_FRAMES_UNAVAILABLE, checks,
                        "no picture decoded from %s" % path)

    shot = str(spec.get("shot") or "main").lower()
    expected = spec.get("expected_words")
    ink = round(_readable_ink(cv2, np, img), 6)
    checks["readable_ink"] = ink
    readable = ink >= SCREEN_WHITE_MIN
    checks["camera_readable"] = readable
    checks["faces"] = rec["faces"]
    checks["viewer_must_read"] = rec["viewer_must_read"]
    checks["shot"] = shot

    subject = bool(spec.get("prop_is_subject"))
    checks["level"] = "MAJOR" if subject else "MEDIUM"

    if shot == "insert":
        # Rule P3: the insert is FROM the user's side and the words read
        # exactly. A wrong-side insert is MAJOR.
        if not readable:
            checks["level"] = "MAJOR"
            return _verdict("FAIL", INSERT_WRONG_SIDE, checks,
                            "the insert carries no readable words from "
                            "this side (ink %.4f); it was shot from the "
                            "wrong side" % ink)
        if isinstance(expected, str) and expected.strip():
            if not _words_present(cv2, np, img, expected):
                checks["level"] = "MAJOR"
                return _verdict("FAIL", PICTURE_TEXT_WRONG, checks,
                                "the insert words do not read exactly: "
                                "%r" % expected)
            checks["expected_words"] = expected
        return _verdict("PASS", "PROP_FACING_OK", checks, "")

    if rec["faces"] == "camera":
        # Rule P5: made to be shown, so it MAY face the camera. Rule T-1
        # (narrowed by 3P) then makes the words mandatory: for a P5 prop the
        # picture must show them to the camera. A blank sign is the same
        # defect in the other direction, so it fails PICTURE_TEXT_WRONG.
        if rec["viewer_must_read"] == "yes" and not readable:
            checks["level"] = "MAJOR"
            return _verdict("FAIL", PICTURE_TEXT_WRONG, checks,
                            "a prop the record says is made to be shown "
                            "carries no readable words (ink %.4f)" % ink)
        return _verdict("PASS", "PROP_FACING_OK", checks, "")

    if rec["faces"] == "other person":
        # Rule P4: offered, turns to them. Camera-readable is expected
        # while the prop is still on the near side; never a defect here.
        return _verdict("PASS", "PROP_FACING_OK", checks, "")

    # faces == "user" (P1, P2, P6): the camera must NOT read the prop.
    if readable:
        return _verdict("FAIL", PROP_FACES_CAMERA, checks,
                        "the prop's reading side faces the camera (ink "
                        "%.4f); it must face its user %r"
                        % (ink, rec["user"]))
    return _verdict("PASS", "PROP_FACING_OK", checks, "")


def check_clip(clip, spec, frames=None):
    """Measured prop-facing verdict for one clip (three frames).

    The brief: the check runs on every picture AND on three frames of every
    clip that has a used prop. The clip verdict fails with
    PROP_TURNED_TO_CAMERA (MAJOR when the prop is the subject) when the
    prop turns toward the lens during the clip, and with
    PROP_FACES_CAMERA when it already faces the camera on the first frame.
    """
    spec = spec or {}
    checks = {}
    try:
        rec = normalize_record(spec.get("record"))
    except PropFacingError as exc:
        return _verdict("UNAVAILABLE", exc.code, checks, str(exc))
    try:
        with _governor_slot("prop-facing-frames"):
            if frames is None:
                frames = _read_clip_frames(clip)
    except _LG.HeavyJobTimeout as exc:
        return _verdict("UNAVAILABLE", PROP_FRAMES_UNAVAILABLE, checks,
                        str(exc))
    except PropFacingError as exc:
        return _verdict("UNAVAILABLE", exc.code, checks, str(exc))
    if not frames:
        return _verdict("UNAVAILABLE", PROP_FRAMES_UNAVAILABLE, checks,
                        "no frames decoded from %s" % clip)
    sample = [frames[0], frames[len(frames) // 2], frames[-1]]
    rows = []
    for i, f in enumerate(sample):
        r = check_picture(None, spec, image=f)
        rows.append({"frame": i, "verdict": r["verdict"],
                     "reason_code": r["reason_code"],
                     "readable_ink": r["checks"].get("readable_ink")})
        if r["verdict"] == "UNAVAILABLE":
            checks["frames"] = rows
            return _verdict("UNAVAILABLE", r["reason_code"], checks,
                            "frame %d unreadable" % i)
    checks["frames"] = rows
    first_readable = rows[0]["readable_ink"] >= SCREEN_WHITE_MIN
    last_readable = rows[-1]["readable_ink"] >= SCREEN_WHITE_MIN
    checks["first_readable"] = first_readable
    checks["last_readable"] = last_readable
    checks["level"] = "MAJOR" if spec.get("prop_is_subject") else "MEDIUM"
    if not first_readable and last_readable:
        return _verdict("FAIL", PROP_TURNED_TO_CAMERA, checks,
                        "the prop turned toward the lens during the clip "
                        "(ink %.4f -> %.4f)"
                        % (rows[0]["readable_ink"], rows[-1]["readable_ink"]))
    if first_readable and rec["faces"] == "user":
        return _verdict("FAIL", PROP_FACES_CAMERA, checks,
                        "the prop already faces the camera on the first "
                        "frame (ink %.4f)" % rows[0]["readable_ink"])
    return _verdict("PASS", "PROP_FACING_OK", checks, "")


def _governor_slot(job):
    """The governed heavy-job slot (`core/load_governor/`).

    load_governor is imported at the top like every other heavy local job,
    so a missing governor fails at module import, never as a silent stub.
    """
    return _LG.heavy_slot(job)


# --------------------------------------------------------------- receipt ----

def qc_record(verdict, shot_id, reviewer, calibrated=False, refs=None,
              run_id=""):
    """The qc_gate record for the shots stage (check prop_facing).

    A PASS without calibrated=True is not a valid record: the acceptance
    rule is 'no clip with a used prop is accepted without a PASS
    prop_facing record from a CALIBRATED checker'.
    """
    ok = verdict.get("verdict") == "PASS" and bool(calibrated)
    if not calibrated and verdict.get("verdict") == "PASS":
        verdict = dict(verdict, verdict="UNAVAILABLE",
                       reason_code=PROP_CHECK_UNAVAILABLE)
    summary = ("prop facing %s: %s (calibrated=%s, checker=%s v%s)"
               % (verdict.get("verdict"), verdict.get("reason_code"),
                  "true" if calibrated else "false", TOOL_NAME, TOOL_VERSION))
    return {
        "schema_version": "1.0.0",
        "check_id": "prop-facing-%s" % shot_id,
        "run_id": run_id or verdict.get("run_id", ""),
        "stage": "shots",
        "check": "prop_facing",
        "verdict": "PASS" if ok else (
            "FAIL" if verdict.get("verdict") == "FAIL" else "UNAVAILABLE"),
        "evidence": {"summary": summary,
                     "refs": list(refs or [])},
        "checker_version": "%s v%s" % (TOOL_NAME, TOOL_VERSION),
        "reviewer": dict(reviewer or {}),
    }


def dumps(d):
    return json.dumps(d, sort_keys=True, ensure_ascii=True)
