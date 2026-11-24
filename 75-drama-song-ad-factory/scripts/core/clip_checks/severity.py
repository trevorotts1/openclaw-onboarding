#!/usr/bin/env python3
"""severity.py: three levels for every check; only MAJOR stops or remakes (N-98).

Section 3J. The whole list of MAJOR findings is fixed here (3J.1 items 1 to 19).
A checker can never call something MAJOR that is not on this list, and can never
downgrade a finding that is. Anything not on the list is MEDIUM at most; when a
checker is unsure it takes the lower level. Levels never add up: three MEDIUMs
on one shot stay MEDIUM.

How a level is decided:
  * an unconditional MAJOR code (``CODE_TO_ITEM``) is always MAJOR with its item;
  * a conditional code (a jump cut, a crowd count, a place mismatch...) is
    MAJOR only when the check passes the MAJOR item number it maps to (3J.1);
  * otherwise the finding is MEDIUM, or MINOR when the check asks for it.

stdlib only, no spend.
"""
from __future__ import annotations

TOOL_NAME = "clip_severity"
TOOL_VERSION = "1.0.0"

MINOR = "MINOR"
MEDIUM = "MEDIUM"
MAJOR = "MAJOR"

_RANK = {MINOR: 0, MEDIUM: 1, MAJOR: 2}

#: The whole MAJOR list, 3J.1, verbatim by number.
MAJOR_ITEMS = {
    1: "non-English script on screen",
    2: "new readable text created by the lip-sync model",
    3: "new readable text by a video model on a featured object, or planned "
       "words that became wrong/unreadable on the prop the shot is about",
    4: "planned words misspelled/wrong on the prop; wrong program name or "
       "website on the end card",
    5: "wrong character; face/wardrobe/accessory not matching the lock; a "
       "visible person not on the cast list",
    6: "photoreal frame under a stylized look, or any frame in the wrong look",
    7: "plain emotion contradiction at intensity 2-3 (a smile held on a pain "
       "line, or pinched brows through a joyful line)",
    8: "lip-sync by the wrong singer, or on the wrong words",
    9: "story-logic break (second entrance, time backwards, wardrobe in scene, "
       "event repeated/off lyric, hook nobody sings)",
    10: "a lyric line with a MISMATCH verdict",
    11: "a missing required scene/shot; a placeholder left in the master; a "
        "cast member missing who the beat says is here",
    12: "an empty room where the story says it is full",
    13: "face visibly morphs, a named person vanishes, a plainly broken body "
        "part, or floaty/rubbery/sliding motion on a foreground character",
    14: "no audio stream, silent audio, or the wrong length",
    15: "a check that could not run (fails closed)",
    16: "a broken screen direction or a jump cut that confuses the story",
    17: "a prop continuity break that matters to the story",
    18: "a leftover-browser leak that threatens disk or memory (fixed at once)",
    19: "a prop the shot is about facing the camera instead of its user",
}

#: Unconditional MAJOR codes. Conditional ones (jump cut, crowd count, place
#: mismatch, prop facing, ...) are NOT here: their check passes the item.
CODE_TO_ITEM = {
    # 1
    "NON_ENGLISH_SCRIPT": 1,
    # 2
    "NEW_TEXT_IN_TAKE": 2,
    # 3
    "TEXT_CHANGED": 3,
    "PICTURE_TEXT_EXTRA": 3,
    # 4
    "PICTURE_TEXT_WRONG": 4,
    # 5
    "CHARACTER_MISMATCH": 5,
    "UNLISTED_PERSON": 5,
    "IDENTITY_BLOCK_WRONG_CHARACTER": 5,
    "CAST_LOOKALIKE": 5,
    # 6
    "STYLE_MISMATCH": 6,
    # 7
    "EXPRESSION_MISMATCH": 7,
    "EMOTION_DRIFT": 7,
    # 8
    "WRONG_SINGER": 8,
    "WRONG_VOICE_MOUTHED": 8,
    # 11
    "PLACEHOLDER_IN_MASTER": 11,
    "MISSING_SHOT": 11,
    "CAST_MEMBER_MISSING": 11,
    # 13
    "FACE_MORPH": 13,
    "WARDROBE_MORPH": 5,   # wardrobe not matching the lock (3J.1 item 5)
    "SCALE_BREAK": 13,
    "PRESENCE_BREAK": 13,
    "DRIFT_BREAK": 13,
    "MOTION_FLOATY": 13,
    "FLOATY_MOTION": 13,
    "BODY_BROKEN": 13,
    # 14
    "NO_AUDIO": 14,
    "AUDIO_SILENT": 14,
    "WRONG_LENGTH": 14,
    # 15 (fail closed: a check that could not run)
    "OCR_UNAVAILABLE": 15,
    "OCR_FAILED": 15,
    "LETTER_GATE_UNAVAILABLE": 15,
    "STYLE_CHECK_UNAVAILABLE": 15,
    "CONSISTENCY_CHECK_UNAVAILABLE": 15,
    "EXPRESSION_CHECK_UNAVAILABLE": 15,
    "PROP_CHECK_UNAVAILABLE": 15,
    "STILL_UNMEASURED": 15,
    "NATIVE_RATE_UNKNOWN": 15,
    "FRAME_EXTRACT_UNAVAILABLE": 15,
}


def level_for(code, item=None, level=None):
    """Return ``(level, item)`` for a finding, never letting a checker lie.

    An unconditional code is MAJOR with its own item. A code ending
    ``_UNAVAILABLE`` is a check that could not run: MAJOR item 15, fail closed
    (3J.1), whatever the caller says. A conditional finding is MAJOR only when
    ``item`` names a real MAJOR item; otherwise ``level`` may lower it to MINOR
    or MEDIUM but never raise it past MEDIUM.
    """
    code = str(code or "")
    if code in CODE_TO_ITEM:
        return MAJOR, CODE_TO_ITEM[code]
    if code.endswith("_UNAVAILABLE"):
        return MAJOR, 15
    if item is not None:
        try:
            n = int(item)
        except (TypeError, ValueError):
            raise ValueError("MAJOR item must be an integer: %r" % (item,))
        if n not in MAJOR_ITEMS:
            raise ValueError("item %r is not on the fixed MAJOR list" % (n,))
        return MAJOR, n
    if level is not None:
        lv = str(level).upper()
        if lv not in (MINOR, MEDIUM):
            raise ValueError("only MINOR or MEDIUM may be set without a "
                             "MAJOR item (got %r)" % (level,))
        return lv, None
    return MEDIUM, None


#: 3J.1 item 7 is a plain contradiction at intensity 2 or 3 ONLY. At intensity
#: 1 it is a flag: MEDIUM, logged, never a remake (N-89).
INTENSITY_CODES = frozenset(("EXPRESSION_MISMATCH", "EMOTION_DRIFT"))


def finding(code, message, item=None, level=None, **extra):
    """One finding row carrying its fixed level; ``stops`` is True only MAJOR.

    An expression finding passes its ``intensity``: below 2 it is MEDIUM
    (flagged), because item 7 is a contradiction at intensity 2 or 3 only.
    """
    if str(code) in INTENSITY_CODES and extra.get("intensity") is not None:
        try:
            if int(extra["intensity"]) < 2:
                # Item 7 covers intensity 2 and 3 only: a lower-intensity
                # contradiction is a flag, so it cannot be raised to MAJOR.
                row = {"code": str(code), "message": str(message),
                       "level": MEDIUM, "item": None, "stops": False,
                       "flagged": True}
                row.update(extra)
                return row
        except (TypeError, ValueError):
            pass                      # an unreadable intensity stays as asked
    lv, n = level_for(code, item=item, level=level)
    row = {"code": str(code), "message": str(message), "level": lv,
           "item": n, "stops": lv == MAJOR}
    row.update(extra)
    return row


def stops(row):
    """True when this finding stops or remakes (MAJOR only)."""
    if isinstance(row, dict):
        return str(row.get("level", "")).upper() == MAJOR
    return str(row).upper() == MAJOR


def worst(rows):
    """Highest level present, or MINOR for an empty set (nothing found)."""
    best = MINOR
    for r in rows or []:
        lv = str(r.get("level") if isinstance(r, dict) else r).upper()
        if _RANK.get(lv, 0) > _RANK[best]:
            best = lv
    return best


def only_major(rows):
    """The MAJOR rows in a set (used as ``not only_major(rows)`` = pass)."""
    return [r for r in (rows or []) if stops(r)]


def may_deliver(rows):
    """Deliverable only when nothing stops: no MAJOR anywhere."""
    return not any(stops(r) for r in rows or [])


def receipt(rows):
    """Rows with their level, item and a stable reason string, MAJOR first."""
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        out.append({k: r.get(k) for k in
                    ("code", "item", "level", "message") if k in r})
    out.sort(key=lambda r: -_RANK.get(str(r.get("level")).upper(), 0))
    return out


if __name__ == "__main__":
    # Control: a MAJOR code cannot be lowered; a conditional one needs an item.
    a = finding("NON_ENGLISH_SCRIPT", "x")
    assert a["level"] == MAJOR and a["item"] == 1 and a["stops"]
    b = finding("NON_ENGLISH_SCRIPT", "x", level=MINOR)     # ignored: MAJOR
    assert b["level"] == MAJOR
    c = finding("CROWD_MISMATCH", "x")                       # conditional: MEDIUM
    assert c["level"] == MEDIUM and not c["stops"]
    d = finding("CROWD_MISMATCH", "x", item=12)              # MAJOR when itemed
    assert d["level"] == MAJOR and d["item"] == 12
    try:
        finding("CROWD_MISMATCH", "x", item=99)
        raise SystemExit("bad item accepted")
    except ValueError:
        pass
    e = finding("SOMETHING", "x", level=MINOR)
    assert e["level"] == MINOR
    assert worst([a, c]) == MAJOR
    assert not may_deliver([a]) and may_deliver([c, e])
    print("severity: control PASS")
