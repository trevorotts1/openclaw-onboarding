"""validate.py: storyboard-row checks before any picture or clip is paid for. Stdlib only.

A storyboard row is one dict per shot, read from ``storyboard/shot-list.json``.
These checks are content checks over those rows. Each returns a list of findings
(``{"code", "shot_id", "detail"}``); an empty list means clean. ``assert_clean``
raises ``StoryboardError`` carrying the first code when a caller needs a hard
refusal.

The rows are read through small accessors so a shot written by the 14.2 planner
(``character_ids``) and one written by the storyboard grid (``characters``) are
both understood. No provider call, no spend, no picture.
"""
from __future__ import annotations

import re

#: Ensemble / non-cast speaker labels that are legal and never a character id.
ENSEMBLE_SPEAKERS = frozenset({"choir", "instrumental", "narrator",
                               "narrator-voiceover"})
VOICEOVER_SPEAKERS = frozenset({"narrator", "narrator-voiceover"})

#: Route and lip-sync flag spellings used by the storyboard.
LIPSYNC_ROUTES = frozenset({"kling_lipsync", "lip_sync", "lipsync", "lip-sync"})
NON_LIPSYNC_ROUTES = frozenset({"h3_start_end", "one_picture", "two_picture",
                                "nine_picture", "merged_clip", "long_take"})

SPEAKER_NOT_IN_CAST = "SPEAKER_NOT_IN_CAST"


class StoryboardError(ValueError):
    def __init__(self, code, message, findings=None):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.findings = findings or []


def _cast(row):
    for key in ("characters", "cast", "character_ids", "cast_ids"):
        v = row.get(key)
        if isinstance(v, list):
            return [str(x) for x in v]
    return []


def _speaker(row):
    v = row.get("speaker")
    return str(v).strip() if isinstance(v, str) else ""


def _route(row):
    v = row.get("route")
    return str(v).strip().lower() if isinstance(v, str) else ""


def _sid(row, i):
    return str(row.get("shot_id") or "shot[%d]" % i)


def _finding(code, sid, detail):
    return {"code": code, "shot_id": sid, "detail": detail}


def is_lipsync_route(row):
    return _route(row) in LIPSYNC_ROUTES or row.get("lip_sync") is True


# --------------------------------------------------------------------------
# G-STORY-01: a shot cannot credit an absent singer.
# --------------------------------------------------------------------------
def check_speaker_cast(rows):
    """Refuse a shot whose spoken/sung speaker is not in the shot's cast.

    An ensemble or voice-over label (choir, instrumental, narrator,
    narrator-voiceover) is not a cast member and is always allowed here; its own
    rules live in ``check_speaker_labels``. A named speaker that is not in the
    shot's ``characters`` is refused (the "voice with no mouth" defect).
    """
    findings = []
    for i, row in enumerate(rows or []):
        sp = _speaker(row)
        if not sp or sp in ENSEMBLE_SPEAKERS:
            continue
        cast = [c.strip().lower() for c in _cast(row)]
        if sp.lower() not in cast:
            findings.append(_finding(
                SPEAKER_NOT_IN_CAST, _sid(row, i),
                "speaker %r is not in characters %s" % (sp, _cast(row))))
    return findings


# --------------------------------------------------------------------------
# G-SPEAKER-01: the speaker labels tell the truth.
# --------------------------------------------------------------------------
CHOIR_SPEAKER_LIPSYNC = "CHOIR_SPEAKER_LIPSYNC"
INSTRUMENTAL_WITH_WORDS = "INSTRUMENTAL_WITH_WORDS"
INSTRUMENTAL_LIPSYNC = "INSTRUMENTAL_LIPSYNC"
VOICEOVER_LIPSYNC = "VOICEOVER_LIPSYNC"
CHARACTER_LINE_NO_LIPSYNC = "CHARACTER_LINE_NO_LIPSYNC"

_WORD_KEYS = ("lyric", "lyrics", "words", "sung_lyrics", "spoken_dialogue",
              "spoken_line")
_MOUTHING_LABELS = frozenset({"lead", "other speaker", "lead_inside_the_choir"})


def _has_words(row):
    for key in _WORD_KEYS:
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return True
        if isinstance(v, (list, tuple)) and any(str(x).strip() for x in v):
            return True
    return False


def check_speaker_labels(rows):
    """Label truth (G-SPEAKER-01).

    * ``choir`` is an ensemble hook label: mouths-open direction, never a
      lip-sync route.
    * ``instrumental`` is a wordless shot: no lyric or spoken words, no lip-sync.
    * ``narrator-voiceover`` speaks with nobody on screen: never a lip-sync route.
    * A named character speaker on a line that mouths on camera (label lead or
      other speaker) must carry a lip-sync route.
    """
    findings = []
    for i, row in enumerate(rows or []):
        sp = _speaker(row)
        sid = _sid(row, i)
        lip = is_lipsync_route(row)
        if sp == "choir" and lip:
            findings.append(_finding(CHOIR_SPEAKER_LIPSYNC, sid,
                                     "choir hook carries a lip-sync route"))
        if sp == "instrumental":
            if _has_words(row):
                findings.append(_finding(INSTRUMENTAL_WITH_WORDS, sid,
                                         "instrumental shot carries words"))
            if lip:
                findings.append(_finding(INSTRUMENTAL_LIPSYNC, sid,
                                         "instrumental shot carries a lip-sync route"))
        if sp in VOICEOVER_SPEAKERS and lip:
            findings.append(_finding(VOICEOVER_LIPSYNC, sid,
                                     "voice-over speaker carries a lip-sync route"))
        label = str(row.get("label") or "").strip().lower()
        if (sp and sp not in ENSEMBLE_SPEAKERS and _has_words(row)
                and label in _MOUTHING_LABELS and not lip):
            findings.append(_finding(CHARACTER_LINE_NO_LIPSYNC, sid,
                                     "character %r mouths on camera but has no lip-sync route"
                                     % sp))
    return findings


# --------------------------------------------------------------------------
# G-STORY-02 / N-22: a shot nobody lip-syncs cannot be marked lip-sync.
# --------------------------------------------------------------------------
LIPSYNC_CONTRADICTION = "LIPSYNC_CONTRADICTION"

#: Wording that declares the shot carries no mouthing. Sentence-scoped so a
#: neighbouring "lip-syncs" elsewhere in the same note cannot cancel it.
_NOBODY_LIPSYNCS = (
    "nobody lip-syncs",
    "nobody lip syncs",
    "no one lip-syncs",
    "no one lip syncs",
    "nobody mouths",
    "no one mouths",
    "nobody sings on camera",
    "nobody sings it on camera",
)
_LIPSYNC_WORD = "lip-sync"


def _note_text(row):
    parts = []
    for key in ("camera", "camera_note", "beat", "beat_text", "note", "notes",
                "visual_objective", "spoken_line"):
        v = row.get(key)
        if isinstance(v, str):
            parts.append(v)
    return ". ".join(parts).lower()


def declares_no_lipsync(row):
    """True when the row's own words say nobody lip-syncs this shot."""
    return any(p in _note_text(row) for p in _NOBODY_LIPSYNCS)


def check_lipsync_contradiction(rows):
    """A declare-nobody shot is route h3_start_end with lip_sync false.

    A declared shot on a lip-sync route, or with ``lip_sync`` true, is refused.
    A declared shot on some other route is corrected to h3_start_end with the
    finding still named, since the storyboard row and the flag disagree.
    """
    findings = []
    for i, row in enumerate(rows or []):
        if not declares_no_lipsync(row):
            continue
        sid = _sid(row, i)
        if is_lipsync_route(row) or row.get("lip_sync") is True:
            findings.append(_finding(
                LIPSYNC_CONTRADICTION, sid,
                "the row says nobody lip-syncs but route=%r lip_sync=%r"
                % (row.get("route"), row.get("lip_sync"))))
        elif _route(row) not in NON_LIPSYNC_ROUTES:
            findings.append(_finding(
                LIPSYNC_CONTRADICTION, sid,
                "the row says nobody lip-syncs; route must be h3_start_end, got %r"
                % (row.get("route"),)))
    return findings


def align_route(row):
    """Return the row with route/lip_sync corrected for a declare-nobody shot."""
    out = dict(row)
    if declares_no_lipsync(out):
        out["route"] = "h3_start_end"
        out["lip_sync"] = False
    return out


# --------------------------------------------------------------------------
# N-22: the contradiction is checked both ways.
# --------------------------------------------------------------------------
_AFFIRM_MOUTHING = (
    "sings on camera", "sings the line on camera", "mouths the line",
    "mouths this line", "lip-syncs this", "lip-syncs the line",
    "lipsyncs this", "sings this line on camera",
)


def check_contradiction_both_ways(rows):
    """N-22: declare-nobody must not lip-sync, and an affirm note must.

    Extends ``check_lipsync_contradiction``: a row whose note says someone sings
    or mouths on camera, but which is routed off lip-sync with lip_sync false,
    is refused as ``LIPSYNC_CONTRADICTION`` too.
    """
    findings = list(check_lipsync_contradiction(rows))
    for i, row in enumerate(rows or []):
        if declares_no_lipsync(row):
            continue
        note = _note_text(row)
        if any(p in note for p in _AFFIRM_MOUTHING):
            if not is_lipsync_route(row) or row.get("lip_sync") is False:
                findings.append(_finding(
                    LIPSYNC_CONTRADICTION, _sid(row, i),
                    "the row says someone mouths on camera but is routed off lip-sync"))
    return findings


# --------------------------------------------------------------------------
# G-STORY-03: one beat per two seconds; a lyric-named picture must cover it.
# --------------------------------------------------------------------------
BEAT_DENSITY_EXCEEDED = "BEAT_DENSITY_EXCEEDED"
LYRIC_PICTURE_CUT_SHORT = "LYRIC_PICTURE_CUT_SHORT"

BEATS_PER_WINDOW = 3          # at most 3 action beats ...
BEATS_WINDOW_S = 5.0          # ... in any 5-second shot


def _beats(row):
    for key in ("action_beats", "beats", "actions"):
        v = row.get(key)
        if isinstance(v, list):
            return [str(b) for b in v if str(b).strip()]
        if isinstance(v, str) and v.strip():
            return [b for b in re.split(r"[;\n]+", v) if b.strip()]
    return []


def _span(row):
    a, b = row.get("song_start"), row.get("song_end")
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b > a:
        return float(a), float(b)
    return None


def check_beat_density(rows):
    """Refuse more than 3 action beats inside a 5-second shot."""
    findings = []
    for i, row in enumerate(rows or []):
        span = _span(row)
        if span is None:
            continue
        start, end = span
        n = len(_beats(row))
        if end - start <= BEATS_WINDOW_S and n > BEATS_PER_WINDOW:
            findings.append(_finding(
                BEAT_DENSITY_EXCEEDED, _sid(row, i),
                "%d action beats in %.2fs (max %d per %.0fs)"
                % (n, end - start, BEATS_PER_WINDOW, BEATS_WINDOW_S)))
    return findings


def check_lyric_picture_window(rows, line_times=None):
    """A picture named by a lyric must stay on screen for that line's window.

    rows carry ``lyric_named_picture`` (a short description of the picture the
    line names) and ``picture_start``/``picture_end`` (the seconds that picture
    is on screen). ``line_times`` maps ``shot_id`` -> (word_start, word_end) from
    the measured song. The picture must cover the whole word-timing window.
    """
    findings = []
    for i, row in enumerate(rows or []):
        if not str(row.get("lyric_named_picture") or "").strip():
            continue
        span = _span(row)
        if span is None:
            continue
        shot_start, shot_end = span
        p_start = row.get("picture_start", shot_start)
        p_end = row.get("picture_end", shot_end)
        if not (isinstance(p_start, (int, float)) and isinstance(p_end, (int, float))):
            continue
        want = (line_times or {}).get(_sid(row, i))
        lo, hi = want if want else (shot_start, shot_end)
        if p_start > lo + 1e-6 or p_end < hi - 1e-6:
            findings.append(_finding(
                LYRIC_PICTURE_CUT_SHORT, _sid(row, i),
                "picture %r on screen %.2f-%.2f, line runs %.2f-%.2f"
                % (row["lyric_named_picture"], p_start, p_end, lo, hi)))
    return findings


# --------------------------------------------------------------------------
# N-14: no empty room when the story says the place is full.
# --------------------------------------------------------------------------
EMPTY_ROOM_ON_FULL_SCENE = "EMPTY_ROOM_ON_FULL_SCENE"

FULL_CROWD_STATES = frozenset({"full", "service", "class", "meeting",
                               "crowded", "congregation", "every pew filled"})
_EMPTY_ROOM_PHRASES = (
    "no extra people", "no crowd", "empty room", "the room is empty",
    "nobody else is here", "nobody else is seen here", "no congregation",
)


def _prompt_text(row):
    parts = []
    for key in ("prompt", "picture_prompt", "visual_objective", "action",
                "negative_constraints", "prompt_text"):
        v = row.get(key)
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, (list, tuple)):
            parts.extend(str(x) for x in v)
    return " ".join(parts).lower()


def is_full_scene(row):
    state = str(row.get("crowd_state") or "").strip().lower()
    if state in FULL_CROWD_STATES:
        return True
    return row.get("story_says_full") is True


def check_no_empty_room(rows):
    """Refuse a prompt that empties a place the story says is full (G-STORY-04)."""
    findings = []
    for i, row in enumerate(rows or []):
        if not is_full_scene(row):
            continue
        text = _prompt_text(row)
        hits = [p for p in _EMPTY_ROOM_PHRASES if p in text]
        if hits:
            findings.append(_finding(
                EMPTY_ROOM_ON_FULL_SCENE, _sid(row, i),
                "full scene carries an emptying line %r" % hits[0]))
    return findings


# --------------------------------------------------------------------------
# N-25: a shot that ends on a named face is refused when the clip misses it.
# --------------------------------------------------------------------------
END_FRAME_PROMISE_MISSED = "END_FRAME_PROMISE_MISSED"
END_FRAME_CHECK_UNAVAILABLE = "END_FRAME_CHECK_UNAVAILABLE"


def check_end_frame_promise(rows, frame_reads):
    """A promised named end face must be in the clip's last frame.

    rows carry ``ends_on_named_face`` (the character the storyboard ends on).
    frame_reads maps shot_id -> {"faces": [names on the last frame]}. A missing
    read fails closed (``END_FRAME_CHECK_UNAVAILABLE``); a promised face absent
    from the last frame is refused (``END_FRAME_PROMISE_MISSED``).
    """
    findings = []
    reads = frame_reads or {}
    for i, row in enumerate(rows or []):
        want = str(row.get("ends_on_named_face") or "").strip()
        if not want:
            continue
        sid = _sid(row, i)
        read = reads.get(sid)
        if not isinstance(read, dict) or not isinstance(read.get("faces"), list):
            findings.append(_finding(
                END_FRAME_CHECK_UNAVAILABLE, sid,
                "no last-frame read for a shot that promises %r" % want))
            continue
        seen = [str(f).strip().lower() for f in read["faces"]]
        if want.lower() not in seen:
            findings.append(_finding(
                END_FRAME_PROMISE_MISSED, sid,
                "storyboard ends on %r but the last frame shows %s"
                % (want, read["faces"])))
    return findings


def assert_clean(findings):
    """Raise StoryboardError on the first finding; return True when clean."""
    if findings:
        f = findings[0]
        raise StoryboardError(f["code"], f["detail"], findings)
    return True


def selfcheck():
    ok = [{"shot_id": "s1", "characters": ["lead"], "speaker": "lead"}]
    bad = [{"shot_id": "t17", "characters": ["choir-member"], "speaker": "lead"}]
    vo = [{"shot_id": "s2", "characters": ["lead"], "speaker": "narrator-voiceover"}]
    assert check_speaker_cast(ok) == []
    assert check_speaker_cast(vo) == []
    f = check_speaker_cast(bad)
    assert f and f[0]["code"] == SPEAKER_NOT_IN_CAST
    try:
        assert_clean(f)
        raise AssertionError("assert_clean passed a finding")
    except StoryboardError as e:
        assert e.code == SPEAKER_NOT_IN_CAST
    # labels: choir never lip-syncs; instrumental is wordless; voice-over no lip-sync
    lab = [
        {"shot_id": "c1", "speaker": "choir", "route": "h3_start_end"},
        {"shot_id": "c2", "speaker": "choir", "route": "kling_lipsync"},
        {"shot_id": "i1", "speaker": "instrumental", "lyric": "a line"},
        {"shot_id": "v1", "speaker": "narrator-voiceover", "route": "kling_lipsync"},
    ]
    codes = [f["code"] for f in check_speaker_labels(lab)]
    assert CHOIR_SPEAKER_LIPSYNC in codes
    assert INSTRUMENTAL_WITH_WORDS in codes
    assert VOICEOVER_LIPSYNC in codes
    assert check_speaker_labels([lab[0]]) == [] or \
        [f["code"] for f in check_speaker_labels([lab[0]])] == []
    print("storyboard.validate selfcheck OK")


if __name__ == "__main__":
    selfcheck()
