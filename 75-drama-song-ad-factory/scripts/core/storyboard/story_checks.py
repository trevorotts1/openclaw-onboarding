"""story_checks.py: storyboard row checks for the story rows of plan 06. Stdlib only.

These are content checks over the storyboard rows (``storyboard/shot-list.json``)
that the speaker/route module does not cover. Each check returns a list of
findings ``{"code", "shot_id", "detail", "severity"}``; an empty list is clean.
``check_all(shots, **kw)`` runs them together and returns ``{"outcome",
"findings"}``. A MAJOR finding fails the plan; MEDIUM is logged and passes.

Rows:
* N-05  opening passage: a lead lip-sync piece inside the first 15 seconds,
        starting by second 3, at least 8 seconds of it.
* N-06  lip-sync map carries one of the five labels of section 3.3.
* N-07  one lip-sync piece carries 1 to 3 faces.
* N-13  wardrobe ledger names every accessory a shot wears.
* N-25  a shot whose storyboard ends on a named face is refused when the clip
        never gets there.
* N-54  lip pieces are placed first and no story shot is under 2.5 seconds.
* N-103 Cinematic Flow: per-shot grammar fields, and neighbours' exit matched
        to entry in one scene.
* N-117 the lip-sync picture shows only the people the Voice Map says sing.
* N-121 World Bible: crowd count, choir count, set pieces, story clock.

No provider call, no spend, no picture.
"""
from __future__ import annotations

MAJOR = "MAJOR"
MEDIUM = "MEDIUM"

OPENING_PASSAGE_MISSING = "OPENING_PASSAGE_MISSING"
LIPSYNC_MAP_LABEL_INVALID = "LIPSYNC_MAP_LABEL_INVALID"
LIPSYNC_FACE_COUNT = "LIPSYNC_FACE_COUNT"
WARDROBE_ACCESSORY_MISSING = "WARDROBE_ACCESSORY_MISSING"
END_FRAME_NOT_REACHED = "END_FRAME_NOT_REACHED"
LIP_PIECES_NOT_FIRST = "LIP_PIECES_NOT_FIRST"
SHOT_TOO_SHORT = "SHOT_TOO_SHORT"
CINEMATIC_FLOW_INCOMPLETE = "CINEMATIC_FLOW_INCOMPLETE"
LIPSYNC_WRONG_FACES = "LIPSYNC_WRONG_FACES"
CROWD_MISMATCH = "CROWD_MISMATCH"
CHOIR_COUNT_MISMATCH = "CHOIR_COUNT_MISMATCH"
SET_PIECE_MISSING = "SET_PIECE_MISSING"
LIGHT_OFF_CLOCK = "LIGHT_OFF_CLOCK"

LIPSYNC_LABELS = (
    "lead",
    "choir",
    "lead inside the choir",
    "other speaker",
    "over picture",
)
_LIPSYNC_LABEL_SET = frozenset(l.lower() for l in LIPSYNC_LABELS)
LIPSYNC_ROUTES = frozenset({"kling_lipsync", "lipsync", "lip_sync", "lip-sync",
                            "omnihuman"})

OPENING_WINDOW_S = 15.0
OPENING_FIRST_BY_S = 3.0
OPENING_MIN_S = 8.0
MIN_STORY_SHOT_S = 2.5
MAX_LIPSYNC_FACES = 3

#: Cinematic Flow fields a shot must carry (plan 3K, F1 to F7).
FLOW_FIELDS = (
    "shot_size",
    "side_of_line",
    "screen_sides",
    "entry_state",
    "exit_state",
    "camera_move",
    "camera_move_reason",
    "transition",
)

#: A shot's exit must match the next shot's entry in the same scene (3K F4).
EXIT_ENTRY_MISMATCH = "EXIT_ENTRY_MISMATCH"


def _text(v):
    return v if isinstance(v, str) else ""


def _num(v):
    if isinstance(v, bool):
        return None
    return float(v) if isinstance(v, (int, float)) else None


def _finding(code, shot_id, detail, severity=MAJOR):
    return {"code": code, "shot_id": shot_id, "detail": detail,
            "severity": severity}


def _rows(shots):
    return [s for s in shots or [] if isinstance(s, dict)]


def _shot_id(row, i):
    sid = row.get("shot_id")
    return sid if isinstance(sid, str) and sid else "shot_%d" % (i + 1)


def _is_lipsync(row):
    if row.get("lip_sync") is True:
        return True
    return _text(row.get("route")).strip().lower() in LIPSYNC_ROUTES


def _dur(row):
    a, b = _num(row.get("song_start")), _num(row.get("song_end"))
    if a is None or b is None:
        return None
    return b - a


# --- N-05: the opening passage ---------------------------------------------

def _is_lead(row, lead_id=None):
    """True when the row's own data says the lead mouths this line (3.3)."""
    label = _text(row.get("lipsync_label") or row.get("label")).strip().lower()
    label = label.replace("_", " ")
    speaker = _text(row.get("speaker")).strip().lower()
    if label:
        return label == "lead"
    if not speaker:
        return True
    if lead_id is not None:
        return speaker == str(lead_id).lower()
    return speaker in ("lead", "Lead".lower())


def check_opening(shots, lead_id=None):
    """A lead lip-sync inside the first 15s, first one by second 3, >= 8s.

    ``lead_id`` names the lead whose passage section 3.2 demands. When it is
    None the row's own ``lipsync_label``/``label`` decides, and a named
    ``speaker: lead`` still counts."""
    rows = _rows(shots)
    pieces = []
    for row in rows:
        if not _is_lipsync(row):
            continue
        a = _num(row.get("song_start"))
        b = _num(row.get("song_end"))
        if a is None or b is None:
            continue
        pieces.append((a, b, _is_lead(row, lead_id=lead_id)))
    inside = [(a, b) for a, b, lead in pieces
              if lead and a < OPENING_WINDOW_S]
    first = min((a for a, _ in inside), default=None)
    seconds = sum(min(b, OPENING_WINDOW_S) - a for a, b in inside)
    findings = []
    if first is None:
        findings.append(_finding(
            OPENING_PASSAGE_MISSING, None,
            "no lead lip-sync inside the first 15 seconds (section 3.2)"))
    else:
        if first > OPENING_FIRST_BY_S:
            findings.append(_finding(
                OPENING_PASSAGE_MISSING, None,
                "first lead lip-sync starts at %.2fs (must start by %.1fs)"
                % (first, OPENING_FIRST_BY_S)))
        if seconds < OPENING_MIN_S:
            findings.append(_finding(
                OPENING_PASSAGE_MISSING, None,
                "opening passage holds %.2fs of lip-sync (needs %.1fs)"
                % (seconds, OPENING_MIN_S)))
    return findings


# --- N-06: the five lip-sync map labels ------------------------------------

def check_lipsync_labels(shots):
    """A shot that carries a map label must use one of the five labels."""
    findings = []
    for i, row in enumerate(_rows(shots)):
        label = row.get("lipsync_label", row.get("label"))
        if label is None or _text(label).strip() == "":
            continue
        if _text(label).strip().lower().replace("_", " ") not in _LIPSYNC_LABEL_SET:
            findings.append(_finding(
                LIPSYNC_MAP_LABEL_INVALID, _shot_id(row, i),
                "label %r is not one of the five labels %r"
                % (label, list(LIPSYNC_LABELS))))
    return findings


# --- N-07: one lip-sync piece carries 1 to 3 faces -------------------------

def check_face_count(shots):
    findings = []
    for i, row in enumerate(_rows(shots)):
        if not _is_lipsync(row):
            continue
        faces = row.get("faces")
        if isinstance(faces, list):
            n = len(faces)
        elif isinstance(faces, int) and not isinstance(faces, bool):
            n = faces
        else:
            n = len(row.get("character_ids") or row.get("characters") or [])
        if n > MAX_LIPSYNC_FACES:
            findings.append(_finding(
                LIPSYNC_FACE_COUNT, _shot_id(row, i),
                "lip-sync piece carries %d faces (max %d); one lip-sync job "
                "takes 1 to 3 faces" % (n, MAX_LIPSYNC_FACES)))
    return findings


# --- N-13: wardrobe accessories lock ---------------------------------------

def check_wardrobe_accessories(shots, wardrobe_ledger):
    """Every wardrobe entry names its accessories; a worn accessory must be
    listed. ``wardrobe_ledger`` is ``{character_id: {wardrobe_id: {accessories:
    [...]}}}`` (or a flat ``{wardrobe_id: {accessories: [...]}}``)."""
    findings = []
    ledger = wardrobe_ledger if isinstance(wardrobe_ledger, dict) else {}
    flat = {}
    for key, value in ledger.items():
        if isinstance(value, dict):
            if "accessories" in value:
                flat[key] = value
            else:
                for wid, entry in value.items():
                    if isinstance(entry, dict):
                        flat[wid] = entry
    for wid, entry in flat.items():
        if not isinstance(entry, dict):
            continue
        if "accessories" not in entry:
            findings.append(_finding(
                WARDROBE_ACCESSORY_MISSING, None,
                "wardrobe %r does not name its accessories (stole, head wrap, "
                "glasses)" % wid))
    for i, row in enumerate(_rows(shots)):
        worn = set(str(a) for a in row.get("accessory_ids") or [])
        if not worn:
            continue
        listed = set()
        for wid in row.get("wardrobe_ids") or []:
            entry = flat.get(wid) or flat.get(str(wid)) or {}
            for a in entry.get("accessories") or []:
                listed.add(str(a))
        missing = worn - listed
        if missing:
            findings.append(_finding(
                WARDROBE_ACCESSORY_MISSING, _shot_id(row, i),
                "shot wears accessories not in the wardrobe ledger: %s"
                % sorted(missing)))
    return findings


# --- N-25: the end-frame promise -------------------------------------------

def check_end_frame(shots):
    findings = []
    for i, row in enumerate(_rows(shots)):
        if not row.get("end_on_face"):
            continue
        reached = row.get("clip_ends_on_face", row.get("clip_end_on_face"))
        if reached is False:
            findings.append(_finding(
                END_FRAME_NOT_REACHED, _shot_id(row, i),
                "storyboard ends on a named face but the clip never gets there"))
    return findings


# --- N-54: lip pieces first, no story shot under 2.5s ----------------------

def check_lip_pieces_first(shots):
    rows = _rows(shots)
    pieces = [(_num(r.get("song_start")), _num(r.get("song_end")))
              for r in rows if _is_lipsync(r)]
    pieces = [(a, b) for a, b in pieces if a is not None and b is not None]
    findings = []
    for i, row in enumerate(rows):
        dur = _dur(row)
        if dur is None:
            continue
        a, b = _num(row.get("song_start")), _num(row.get("song_end"))
        squeezed = row.get("under_lip_window") is True
        if not squeezed and not _is_lipsync(row):
            # Lip-sync pieces are placed on the song first; a story shot may
            # not sit inside or across a piece's window (3.4a).
            squeezed = any(a < pe and ps < b for ps, pe in pieces)
        if squeezed:
            findings.append(_finding(
                LIP_PIECES_NOT_FIRST, _shot_id(row, i),
                "story shot is squeezed under a lip-sync piece; lip pieces are "
                "placed first (3.4a)"))
        if not _is_lipsync(row) and dur < MIN_STORY_SHOT_S:
            findings.append(_finding(
                SHOT_TOO_SHORT, _shot_id(row, i),
                "story shot is %.2fs (min %.1fs)" % (dur, MIN_STORY_SHOT_S)))
    return findings


# --- N-103: Cinematic Flow --------------------------------------------------

def check_cinematic_flow(shots):
    rows = sorted(_rows(shots),
                  key=lambda r: (_num(r.get("song_start")) or 0,
                                 _num(r.get("song_end")) or 0))
    findings = []
    for i, row in enumerate(rows):
        missing = [f for f in FLOW_FIELDS if _text(row.get(f)).strip() == ""]
        if missing:
            findings.append(_finding(
                CINEMATIC_FLOW_INCOMPLETE, _shot_id(row, i),
                "shot lacks Cinematic Flow fields: %s" % ", ".join(missing)))
    for a, b in zip(rows, rows[1:]):
        same_scene = _text(a.get("location_id")) and \
            _text(a.get("location_id")) == _text(b.get("location_id"))
        if not same_scene:
            continue
        ea, eb = _text(a.get("exit_state")).strip(), \
            _text(b.get("entry_state")).strip()
        if ea and eb and ea != eb:
            findings.append(_finding(
                EXIT_ENTRY_MISMATCH, _shot_id(b, 0),
                "%r ends on %r but %r starts on %r"
                % (a.get("shot_id"), ea, b.get("shot_id"), eb)))
    return findings


# --- N-117: the lip-sync picture shows only the singers --------------------

def check_lipsync_faces(shots, voice_map):
    """voice_map: a list of ``{start_s, end_s, singers [ids], role}`` stretches.
    A lip-sync shot inside a stretch must show exactly those singers."""
    if not isinstance(voice_map, (list, tuple)):
        return []
    findings = []
    for i, row in enumerate(_rows(shots)):
        if not _is_lipsync(row):
            continue
        a, b = _num(row.get("song_start")), _num(row.get("song_end"))
        if a is None or b is None:
            continue
        mid = (a + b) / 2.0
        stretch = None
        for s in voice_map:
            if not isinstance(s, dict):
                continue
            sa, sb = _num(s.get("start_s")), _num(s.get("end_s"))
            if sa is not None and sb is not None and sa <= mid <= sb:
                stretch = s
                break
        if stretch is None:
            continue
        singers = {str(x) for x in stretch.get("singers") or []}
        shown = {str(x) for x in
                 (row.get("character_ids") or row.get("characters") or [])}
        if singers and shown != singers:
            findings.append(_finding(
                LIPSYNC_WRONG_FACES, _shot_id(row, i),
                "picture shows %s but the Voice Map sings %s"
                % (sorted(shown), sorted(singers))))
    return findings


# --- N-121: World Bible continuity ----------------------------------------

def _places(world):
    """Index the location rows by id, whichever shape the caller hands over.

    The canonical World Bible record (world_bible/world.schema.json) carries
    ``locations`` as a LIST of rows; some callers hand a ``{location_id: row}``
    dict. Both are read here so the check can never fail open on shape alone.
    """
    raw = world.get("places")
    if raw is None:
        raw = world.get("locations")
    if isinstance(raw, dict):
        return {k: v for k, v in raw.items() if isinstance(v, dict)}
    out = {}
    for row in raw if isinstance(raw, (list, tuple)) else []:
        if isinstance(row, dict) and _text(row.get("location_id")):
            out[_text(row.get("location_id"))] = row
    return out


def check_world(shots, world):
    """World Bible continuity for one plan (N-121, section 3M.4).

    ``world`` is the World Bible record (``locations`` as a list of rows) or a
    ``{places: {location_id: ...}}`` dict: each place carries ``crowd_states``
    with a count or a min..max range, a ``choir`` count or range, its
    ``set_pieces``, and its ``clock`` (time of day to the light it wants).
    """
    if not isinstance(world, dict):
        return []
    places = _places(world)
    findings = []
    for i, row in enumerate(_rows(shots)):
        sid = _shot_id(row, i)
        lid = _text(row.get("location_id"))
        place = places.get(lid)
        if not isinstance(place, dict):
            continue
        state = _text(row.get("crowd_state")).strip().lower()
        states = place.get("crowd_states") or {}
        if state and isinstance(states, dict) and state in states:
            want = states[state]
            seen = row.get("crowd_count")
            if isinstance(want, dict) and isinstance(seen, (int, float)) \
                    and not isinstance(seen, bool):
                lo = want.get("min", want.get("count"))
                hi = want.get("max", want.get("count"))
                if (isinstance(lo, (int, float)) and seen < lo) or \
                        (isinstance(hi, (int, float)) and seen > hi):
                    findings.append(_finding(
                        CROWD_MISMATCH, sid,
                        "crowd %s is outside %r..%r for state %r"
                        % (seen, lo, hi, state)))
        choir = place.get("choir") or {}
        count = row.get("choir_count")
        if isinstance(choir, dict) and isinstance(count, (int, float)) \
                and not isinstance(count, bool):
            lo = choir.get("min", choir.get("count"))
            hi = choir.get("max", choir.get("count"))
            if (isinstance(lo, (int, float)) and count < lo) or \
                    (isinstance(hi, (int, float)) and count > hi):
                findings.append(_finding(
                    CHOIR_COUNT_MISMATCH, sid,
                    "choir of %s is outside %r..%r" % (count, lo, hi)))
        required = place.get("set_pieces") or []
        shown = set(str(x) for x in row.get("set_pieces") or [])
        missing = [p for p in required if str(p) not in shown]
        if required and row.get("shows_whole_place") and missing:
            findings.append(_finding(
                SET_PIECE_MISSING, sid,
                "place %r is missing its set pieces %s" % (lid, missing)))
        clock = place.get("clock") or {}
        tod = _text(row.get("time_of_day")).strip().lower()
        if isinstance(clock, dict) and tod in clock:
            want_light = _text(clock[tod]).strip().lower()
            got_light = _text(row.get("light")).strip().lower()
            if want_light and got_light and want_light != got_light:
                findings.append(_finding(
                    LIGHT_OFF_CLOCK, sid,
                    "time %r wants %r light but the shot is %r"
                    % (tod, want_light, got_light)))
    return findings


# --- N-17: approve once -----------------------------------------------------

#: Fields a replacement picture or clip may change without reopening approval.
_NON_STORY_FIELDS = frozenset({
    "status", "still", "still_path", "clip", "clip_path", "take",
    "take_id", "keyframe", "keyframe_id", "keyframe_ids", "cost_estimate",
    "qc_requirements", "review", "findings", "selected_take",
    "start_frame_digest", "clip_ends_on_face", "approval", "revision",
})


def approval_reopen_required(previous, current):
    """N-17: replacing a picture or clip inside the approved story does not
    reopen approval; only a changed story beat does. Returns True when the two
    rows differ in any story field (beat, cast, place, wardrobe, emotion,
    lyric, events), and False when only picture/clip fields changed."""
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return True
    keys = (set(previous) | set(current)) - _NON_STORY_FIELDS
    for key in keys:
        if previous.get(key) != current.get(key):
            return True
    return False


# --- aggregate --------------------------------------------------------------

def check_all(shots, *, wardrobe_ledger=None, voice_map=None, world=None):
    findings = []
    findings += check_opening(shots)
    findings += check_lipsync_labels(shots)
    findings += check_face_count(shots)
    if wardrobe_ledger is not None:
        findings += check_wardrobe_accessories(shots, wardrobe_ledger)
    findings += check_end_frame(shots)
    findings += check_lip_pieces_first(shots)
    findings += check_cinematic_flow(shots)
    if voice_map is not None:
        findings += check_lipsync_faces(shots, voice_map)
    if world is not None:
        findings += check_world(shots, world)
    blocking = [f for f in findings if f["severity"] == MAJOR]
    return {"outcome": "fail" if blocking else "pass",
            "findings": findings,
            "codes": sorted({f["code"] for f in findings})}
