"""3J severity levels for every check (N-100). Stdlib only, no spend.

Only a MAJOR stops or remakes anything. The MAJOR list is fixed: a checker
cannot call something MAJOR that is not on it, and cannot downgrade
something that is. Anything not on the list is MEDIUM at most, and every
MEDIUM is listed on the receipt for the run owner.
"""
from __future__ import annotations

MAJOR = "MAJOR"
MEDIUM = "MEDIUM"
MINOR = "MINOR"

#: 3J.1, the whole MAJOR list, by item number, under its finding code.
MAJOR_ITEMS = {
    1: "NON_ENGLISH_SCRIPT",
    2: "NEW_TEXT_LIPSYNC",
    3: "NEW_TEXT_FEATURED_OBJECT",
    4: "PLANNED_WORDS_WRONG",
    5: "WRONG_CHARACTER",
    6: "STYLE_MISMATCH",
    7: "EMOTION_CONTRADICTION",
    8: "LIPSYNC_WRONG_SINGER",
    9: "STORY_LOGIC_BREAK",
    10: "LYRIC_LINE_MISMATCH",
    11: "MISSING_SCENE_OR_PLACEHOLDER",
    12: "EMPTY_ROOM",
    13: "BROKEN_FACE_OR_BODY",
    14: "MASTER_NO_AUDIO",
    15: "CHECK_UNAVAILABLE",
    16: "CONFUSING_DIRECTION",
    17: "STORY_PROP_CONTINUITY",
    18: "BROWSER_LEAK",
    19: "PROP_FACING_CAMERA",
}

#: Codes that are the same MAJOR item under another name. Item 14 is "no
#: audio stream, silent audio, or the wrong length".
MAJOR_ALIASES = {code: n for n, code in MAJOR_ITEMS.items()}
MAJOR_ALIASES.update({"MASTER_SILENT": 14, "MASTER_WRONG_LENGTH": 14})

def item_of(code):
    """The MAJOR item number a finding code names, else None."""
    return MAJOR_ALIASES.get(str(code or "").upper())

def severity_of(code):
    """MAJOR only for a code on the fixed list; everything else MEDIUM.

    An unknown code is MEDIUM, never MAJOR (3J: unsure takes the lower one).
    """
    return MAJOR if item_of(code) is not None else MEDIUM

def gate(findings):
    """The take gate and the delivery gate verdict for a list of findings.

    ``findings`` is a list of dicts carrying at least ``code`` (and usually
    ``detail`` and the shot id). Returns::

        {"pass": bool, "major": [...], "medium": [...], "minor": [...]}

    Pass is False only when a finding is MAJOR. Every MEDIUM is kept in the
    result, which is what the receipt lists. A MINOR finding counts only.
    """
    out = {"pass": True, "major": [], "medium": [], "minor": []}
    for finding in findings or ():
        row = dict(finding) if isinstance(finding, dict) else {
            "code": str(finding)}
        level = row.get("severity") or severity_of(row.get("code"))
        if level == MAJOR and item_of(row.get("code")) is None:
            level = MEDIUM                 # the list is fixed; never promoted
        row["severity"] = level
        out[level.lower()].append(row)
        if level == MAJOR:
            out["pass"] = False
    return out

def scan_times(duration_s, new_ranges=(), fps=1.0, small_box=False):
    """Frame times the master scan reads (N-100, 10D reduced scan).

    On a small box every frame inside ``new_ranges`` ((start_s, end_s)
    pairs: transitions, end card, captions) is read at ``fps``, and one
    frame per second of the rest. On a full box the whole master is read at
    ``fps``. Returns sorted, de-duplicated times in seconds.
    """
    duration = float(duration_s)
    if not duration > 0 or not fps > 0:
        raise ValueError("duration_s and fps must be positive")
    if not small_box:
        n = int(duration * fps)
        return [round(i / fps, 6) for i in range(n)]
    step = 1.0 / fps
    times = set()
    for start, end in new_ranges or ():
        t, stop = max(0.0, float(start)), min(duration, float(end))
        while t < stop:
            times.add(round(t, 6))
            t += step
    t = 0.0
    while t < duration:
        times.add(round(t, 6))
        t += 1.0
    return sorted(times)
