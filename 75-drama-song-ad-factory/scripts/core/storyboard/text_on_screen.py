"""text_on_screen.py: the text record (row N-26, plan section 3A). Stdlib only.

Every picture carries one record of the short, correct English on its props:
``storyboard/text-on-screen.json``. The record is the single source for the
picture prompt (the words are quoted next to the phrase "reads exactly"), for
the H3 prompt, and for the check. Nobody retypes the words.

What this module does, and nothing else:

* ``build_record(shots)`` -- read the shot rows' ``text_objects`` and write the
  record. Limits that keep picture models spelling correctly: at most 3 lines
  per object, at most 6 words per line, at most 2 written objects per picture
  (3A.2). A storyboard with a written object over a limit is refused
  ``TEXT_RECORD_OVER_LIMIT``.
* ``picture_prompt_sentences(entry)`` -- one sentence per written object, in
  the wording of 3A.3, with the exact words in quotes and "reads exactly".
* ``text_prompt_ok(prompt, entry)`` -- the dispatcher's rule (3A.5.3): a picture
  prompt for a shot with a record entry must contain every recorded string in
  quotes and the phrase "reads exactly". A prompt that bypasses the builder is
  refused ``TEXT_PROMPT_MISSING``.
* ``check_picture(read_strings, entry)`` -- picture against the record (3A.4
  step 2): wrong or misspelled readable words, or extra readable writing, are
  MAJOR; a blank prop where words were planned is MEDIUM and passes (rule T-1).

Prop facing (section 3P) is carried by the record's ``user`` / ``faces`` /
``viewer_must_read`` fields so the picture prompt can say which way the object
faces. No provider call, no spend, no picture.
"""
from __future__ import annotations

SCHEMA_VERSION = "blackceo.text-on-screen/v1"
RECORD_NAME = "text-on-screen.json"

#: 3A.2 limits that keep picture models spelling correctly.
MAX_LINES_PER_OBJECT = 3
MAX_WORDS_PER_LINE = 6
MAX_OBJECTS_PER_PICTURE = 2

MAJOR = "MAJOR"
MEDIUM = "MEDIUM"

TEXT_RECORD_OVER_LIMIT = "TEXT_RECORD_OVER_LIMIT"
TEXT_PROMPT_MISSING = "TEXT_PROMPT_MISSING"
PICTURE_TEXT_WRONG = "PICTURE_TEXT_WRONG"
PICTURE_TEXT_EXTRA = "PICTURE_TEXT_EXTRA"
PROP_BLANK = "PROP_BLANK"

#: Faces of a written object, used by the Prop Facing sentence (3P).
FACES = ("user", "camera", "other person")


class TextRecordError(ValueError):
    def __init__(self, code, message, findings=None):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.findings = findings or []


def _text(value):
    return value if isinstance(value, str) else ""


def _finding(code, shot_id, detail, severity=MAJOR):
    return {"code": code, "shot_id": shot_id, "detail": detail,
            "severity": severity}


def _object_entry(raw, shot_id, index):
    """Normalise one ``text_objects`` entry; refuse a shape that cannot be a
    record (3A.2's limits), never silently truncate."""
    if not isinstance(raw, dict):
        raise TextRecordError(TEXT_RECORD_OVER_LIMIT,
                              "shot %s text object %d is not an object"
                              % (shot_id, index))
    lines = raw.get("lines")
    if not isinstance(lines, list) or not lines:
        name = _text(raw.get("object")) or "object %d" % index
        lines = [name]
    lines = [str(l) for l in lines if str(l).strip()]
    if len(lines) > MAX_LINES_PER_OBJECT:
        raise TextRecordError(
            TEXT_RECORD_OVER_LIMIT,
            "shot %s object %r has %d lines (max %d)"
            % (shot_id, raw.get("object"), len(lines), MAX_LINES_PER_OBJECT))
    for line in lines:
        if len(line.split()) > MAX_WORDS_PER_LINE:
            raise TextRecordError(
                TEXT_RECORD_OVER_LIMIT,
                "shot %s object %r line %r has %d words (max %d)"
                % (shot_id, raw.get("object"), line, len(line.split()),
                   MAX_WORDS_PER_LINE))
    faces = _text(raw.get("faces")).strip().lower()
    if faces not in FACES:
        faces = "user"
    return {
        "object": _text(raw.get("object")) or "prop",
        "lines": lines,
        "user": _text(raw.get("user")),
        "faces": faces,
        "viewer_must_read": bool(raw.get("viewer_must_read")),
    }


def build_record(shots):
    """Write ``storyboard/text-on-screen.json`` from the shot rows.

    A shot names its writing in ``text_objects``: a list of
    ``{object, lines[], user, faces, viewer_must_read}``. Shots with no written
    object are simply absent from the record. Returns the record dict.
    """
    pictures = {}
    for shot in shots or []:
        if not isinstance(shot, dict):
            continue
        sid = shot.get("shot_id")
        if not isinstance(sid, str) or not sid.strip():
            raise TextRecordError(TEXT_RECORD_OVER_LIMIT,
                                  "a shot with text has no shot_id")
        raw = shot.get("text_objects") or []
        if not isinstance(raw, list):
            raise TextRecordError(TEXT_RECORD_OVER_LIMIT,
                                  "shot %s text_objects is not a list" % sid)
        if len(raw) > MAX_OBJECTS_PER_PICTURE:
            raise TextRecordError(
                TEXT_RECORD_OVER_LIMIT,
                "shot %s names %d written objects (max %d)"
                % (sid, len(raw), MAX_OBJECTS_PER_PICTURE))
        if raw:
            pictures[sid] = [_object_entry(o, sid, i) for i, o in enumerate(raw)]
    return {"schema_version": SCHEMA_VERSION, "pictures": pictures}


def picture_prompt_sentences(entry):
    """The 3A.3 picture sentence per written object, in the record's order."""
    out = []
    for obj in entry or []:
        name = obj.get("object") or "the object"
        quoted = ", ".join('"%s"' % line for line in obj.get("lines") or [])
        out.append(
            'On %s. It reads exactly, in clear printed English: %s. '
            'The words are sharp, correctly spelled and easy to read. '
            'There is no other writing anywhere in the picture.'
            % (name, quoted))
    return out


def facing_sentence(entry):
    """The Prop Facing sentence for one object (section 3P)."""
    out = []
    for obj in entry or []:
        name = obj.get("object") or "the prop"
        faces = obj.get("faces") or "user"
        if faces == "camera":
            out.append("The camera reads the writing on %s." % name)
        else:
            who = obj.get("user") or "the person using it"
            out.append(
                "%s faces its reading side toward %s; the camera sees the back "
                "or the edge of it." % (name, who))
        if obj.get("viewer_must_read") and faces != "camera":
            out.append(
                "The viewer reads %s in an insert shot taken from the user's "
                "side." % name)
    return out


def text_prompt_ok(prompt, entry):
    """True when the prompt carries every recorded string in quotes and the
    phrase "reads exactly" (3A.5.3). No written object means nothing to carry.
    """
    if not entry:
        return True
    if not isinstance(prompt, str):
        return False
    if "reads exactly" not in prompt:
        return False
    for obj in entry:
        for line in obj.get("lines") or []:
            if '"%s"' % line not in prompt:
                return False
    return True


def check_picture(read_strings, entry):
    """Picture against the record (3A.4 step 2).

    read_strings: the strings the reader found on the prop the shot is about.
    Wrong or misspelled readable words on that prop, or extra readable writing,
    are MAJOR (redraw). A blank prop where words were planned is MEDIUM: it is
    logged and it passes (rule T-1).
    """
    findings = []
    read = [str(s).strip() for s in (read_strings or []) if str(s).strip()]
    expected = []
    for obj in entry or []:
        expected.extend(obj.get("lines") or [])
    if expected and not read:
        findings.append(_finding(
            PROP_BLANK, None,
            "the prop that carries the words is blank; logged, passes (T-1)",
            severity=MEDIUM))
        return findings
    allowed = {e.strip() for e in expected}
    for got in read:
        if got not in allowed:
            findings.append(_finding(
                PICTURE_TEXT_WRONG, None,
                "readable writing %r is not in the record (expected %r)"
                % (got, sorted(allowed))))
    for want in expected:
        if want not in read:
            findings.append(_finding(
                PICTURE_TEXT_WRONG, None,
                "recorded string %r is missing or misspelled" % want))
    return findings
