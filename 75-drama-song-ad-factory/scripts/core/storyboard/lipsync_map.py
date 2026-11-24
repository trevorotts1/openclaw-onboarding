"""lipsync_map.py: the lip-sync map (row N-06, plan section 3.3). Stdlib only.

Section 3.3: "Lip-sync is planned in the storyboard, never bolted on afterward.
Every sung or spoken line gets one of five labels." This module is where the
storyboard builder writes that map: one entry per sung or spoken line, each
carrying exactly one of the five labels in ``LABELS``.

Written artifact: ``storyboard/lipsync-map.json``.

Refusals before any spend:

* ``LIPSYNC_MAP_MISSING``   -- a plan with sung or spoken lines and no map.
* ``LIPSYNC_MAP_LABEL_MISSING`` -- a labelled line the builder could not place.
* ``LIPSYNC_MAP_LABEL_INVALID`` -- a label that is not one of the five.

N-117 (story half, section 3N.3): every lip-sync picture's record names each
face in it -- the character, the role it has in this piece (lead or backing)
and its place from left to right -- and shows only the people singing that
stretch. ``check_picture_faces`` refuses a missing or wrong record.

No provider call, no spend, no picture. Read-only over the plan.
"""
from __future__ import annotations

SCHEMA_VERSION = "blackceo.lipsync-map/v1"
MAP_NAME = "lipsync-map.json"

#: Section 3.3's table, in its own words. The one place these five live.
LABELS = (
    "lead",
    "choir",
    "lead inside the choir",
    "other speaker",
    "over picture",
)
_LABEL_SET = frozenset(LABELS)

LIPSYNC_MAP_MISSING = "LIPSYNC_MAP_MISSING"
LIPSYNC_MAP_LABEL_MISSING = "LIPSYNC_MAP_LABEL_MISSING"
LIPSYNC_MAP_LABEL_INVALID = "LIPSYNC_MAP_LABEL_INVALID"

#: Section 3N.3: the one or two roles a face can have in a piece.
FACE_ROLES = ("lead", "backing")
LIPSYNC_PICTURE_RECORD_INCOMPLETE = "LIPSYNC_PICTURE_RECORD_INCOMPLETE"
LIPSYNC_WRONG_FACES = "LIPSYNC_WRONG_FACES"

#: Ensemble / voice-over labels that are directions, never cast members (3.3).
_OVER_PICTURE_SPEAKERS = frozenset({"narrator", "narrator-voiceover",
                                    "instrumental"})
_CHOIR_SPEAKERS = frozenset({"choir", "ensemble", "backing"})
_LEAD_IN_CHOIR = frozenset({"lead inside the choir", "lead_inside_choir",
                            "lead-in-choir"})

LIPSYNC_ROUTES = frozenset({"kling_lipsync", "lipsync", "lip_sync", "lip-sync",
                            "omnihuman"})


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _rows(shots):
    if isinstance(shots, dict):
        shots = shots.get("shots") or shots.get("rows") or []
    return [s for s in shots or [] if isinstance(s, dict)]


def _sid(row, i):
    return str(row.get("shot_id") or "shot[%d]" % i)


def _cast(row):
    for key in ("character_ids", "characters", "cast", "cast_ids"):
        value = row.get(key)
        if isinstance(value, list):
            return [str(x) for x in value]
    return []


def _lines(row):
    ids = row.get("lyric_line_ids")
    out = [str(x) for x in ids] if isinstance(ids, list) else []
    text = _text(row.get("lyric"))
    if not out and text:
        out = [text]
    return out


def _is_lipsync(row):
    if row.get("lip_sync") is True:
        return True
    return _text(row.get("route")).lower() in LIPSYNC_ROUTES


def label_for(row, lead_id=None):
    """The one label this row earns, by section 3.3's table.

    ``lead`` -- the lead character mouths it; ``choir`` -- one or two choir
    singers large in a choir-row shot; ``lead inside the choir`` -- the lead in
    choir wardrobe with the choir behind; ``other speaker`` -- another named
    character; ``over picture`` -- nobody mouths it.
    """
    declared = _text(row.get("lipsync_label") or row.get("label")).lower()
    declared = declared.replace("_", " ").replace("-", " ")
    for label in LABELS:                       # a declared label is kept as written
        if declared == label.replace("-", " "):
            return label
    speaker = _text(row.get("speaker")).lower()
    if speaker in _CHOIR_SPEAKERS:
        return "choir"
    if speaker in _LEAD_IN_CHOIR:
        return "lead inside the choir"
    if speaker in _OVER_PICTURE_SPEAKERS or not speaker:
        return "over picture"
    if speaker in [c.lower() for c in _cast(row)]:
        if lead_id is None or speaker == str(lead_id).lower():
            return "lead"
        return "other speaker"
    return ""                                  # a singer absent from the cast


def build_map(shots, *, lead_id=None):
    """The map the storyboard builder writes: one entry per sung or spoken line."""
    pieces, findings, by_label = [], [], {label: 0 for label in LABELS}
    for i, row in enumerate(_rows(shots)):
        line_ids = _lines(row)
        if not line_ids and not _is_lipsync(row):
            continue                           # wordless story shot: not a line
        label = label_for(row, lead_id=lead_id)
        sid = _sid(row, i)
        if not label:
            findings.append({
                "code": LIPSYNC_MAP_LABEL_MISSING, "shot_id": sid,
                "detail": "speaker %r is not in this shot's cast, so the line "
                          "carries no label (section 3.3)" % row.get("speaker")})
            continue
        if label not in _LABEL_SET:
            findings.append({
                "code": LIPSYNC_MAP_LABEL_INVALID, "shot_id": sid,
                "detail": "label %r is not one of %r" % (label, list(LABELS))})
            continue
        by_label[label] += 1
        pieces.append({"shot_id": sid, "line_ids": line_ids, "label": label,
                       "speaker": _text(row.get("speaker")) or None,
                       "lip_sync": _is_lipsync(row),
                       "faces": row.get("character_ids")
                       or row.get("characters") or []})
    return {"schema_version": SCHEMA_VERSION,
            "pieces": pieces,
            "by_label": by_label,
            "findings": findings,
            "outcome": "fail" if findings else "pass"}


def check_map(shots, lipsync_map=None, *, lead_id=None):
    """Refuse a plan of sung or spoken lines that carries no map (N-06)."""
    has_lines = any(_lines(row) or _is_lipsync(row) for row in _rows(shots))
    if not has_lines:
        return []
    if not isinstance(lipsync_map, dict):
        return [{"code": LIPSYNC_MAP_MISSING, "shot_id": None,
                 "detail": "the plan carries sung or spoken lines but no "
                           "lip-sync map; every line must carry one of the "
                           "five labels (section 3.3)"}]
    return [dict(f) for f in lipsync_map.get("findings") or []]


# --------------------------------------------------------------------------
# N-117 (story half): the lip-sync picture record (plan section 3N.3).
# --------------------------------------------------------------------------
def picture_record(row):
    """The record section 3N.3 says every lip-sync picture carries.

    Each face: the character, its role in this piece (``lead`` or
    ``backing``) and its place from left to right. A person who is silent in
    the piece is not in the picture at all.
    """
    faces = row.get("picture_faces")
    if not isinstance(faces, list):
        return None
    out = []
    for face in faces:
        if not isinstance(face, dict):
            return None
        character = _text(face.get("character") or face.get("character_id"))
        role = _text(face.get("role")).lower()
        place = face.get("place")
        if not character or role not in FACE_ROLES \
                or not isinstance(place, int) or isinstance(place, bool):
            return None
        out.append({"character": character.lower(), "role": role,
                    "place": place})
    return sorted(out, key=lambda f: f["place"])


def check_picture_faces(shots, voice_map):
    """A lip-sync picture shows exactly the faces the Voice Map sings (3N.3).

    ``voice_map`` is a list of ``{start_s, end_s, singers [ids]}`` stretches.
    A lip-sync shot whose picture record is absent, unshaped, or shows a face
    the map does not give that stretch is refused before any spend.
    """
    findings = []
    for i, row in enumerate(_rows(shots)):
        if not _is_lipsync(row):
            continue
        sid = _sid(row, i)
        record = picture_record(row)
        if record is None:
            findings.append({
                "code": LIPSYNC_PICTURE_RECORD_INCOMPLETE, "shot_id": sid,
                "detail": "lip-sync picture has no face record; every face "
                          "needs its character, its role and its place from "
                          "left to right (section 3N.3)"})
            continue
        if record and [f["place"] for f in record] != list(range(len(record))):
            findings.append({
                "code": LIPSYNC_PICTURE_RECORD_INCOMPLETE, "shot_id": sid,
                "detail": "face places are %r; they must run 0..n-1 left to "
                          "right" % [f["place"] for f in record]})
            continue
        singers = _singers_at(row, voice_map)
        if singers is None:
            continue
        shown = {f["character"] for f in record}
        if shown != singers:
            findings.append({
                "code": LIPSYNC_WRONG_FACES, "shot_id": sid,
                "detail": "picture shows %s but the Voice Map sings %s; a "
                          "silent person is not in the picture (section 3N.3)"
                          % (sorted(shown), sorted(singers))})
    return findings


def _singers_at(row, voice_map):
    if not isinstance(voice_map, (list, tuple)):
        return None
    start = row.get("song_start")
    end = row.get("song_end")
    if not isinstance(start, (int, float)) or isinstance(start, bool) \
            or not isinstance(end, (int, float)) or isinstance(end, bool):
        return None
    mid = (start + end) / 2.0
    for stretch in voice_map:
        if not isinstance(stretch, dict):
            continue
        a, b = stretch.get("start_s"), stretch.get("end_s")
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
                and not isinstance(a, bool) and not isinstance(b, bool) \
                and a <= mid <= b:
            return {str(x).lower() for x in stretch.get("singers") or []}
    return None
