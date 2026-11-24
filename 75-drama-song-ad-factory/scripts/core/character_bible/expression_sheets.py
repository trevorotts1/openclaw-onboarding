#!/usr/bin/env python3
"""expression_sheets.py: seven expression pictures per main character (N-70, section 3G.2). Stdlib only.

Every main character's reference set carries seven expression pictures:
neutral, sad, worried, tired, hopeful, joyful, determined. Each is made
image-to-image from that character's master picture, so it is the same face,
and each is fingerprinted and listed in the lock file like every other
reference. An emotion a beat uses that has no exact sheet gets one more sheet,
made the same way; nothing is improvised from a sheet that does not match.

``validate_reference_set_expressions`` is called by
``reference_sets.validate_reference_set`` when the set is a main character's.

Stdlib only, no provider call and no network.
"""
from __future__ import annotations

SCHEMA_VERSION = "blackceo.expression-sheets/v1"

#: The seven sheets of 3G.2, in the plan's order.
EXPRESSION_SHEETS = ("neutral", "sad", "worried", "tired",
                     "hopeful", "joyful", "determined")

#: Which sheet serves which Emotion Track tag (3G.2).
EMOTION_TO_SHEET = {
    "pain": "sad",
    "worry": "worried",
    "exhaustion": "tired",
    "anger": "determined",
    "hope": "hopeful",
    "relief": "hopeful",
    "joy": "joyful",
    "pride": "determined",
    "tenderness": "hopeful",
    "resolve": "determined",
}

EXPRESSION_SHEETS_INCOMPLETE = "EXPRESSION_SHEETS_INCOMPLETE"
EXPRESSION_UNHASHED = "EXPRESSION_UNHASHED"
EXPRESSION_NOT_FROM_MASTER = "EXPRESSION_NOT_FROM_MASTER"
UNKNOWN_EMOTION = "UNKNOWN_EMOTION"


def _defect(code, character_id, detail):
    return {"code": code, "character_id": character_id, "detail": detail}


def sheet_for_emotion(emotion):
    """The expression sheet that serves an Emotion Track tag (3G.2)."""
    return EMOTION_TO_SHEET.get(str(emotion or "").strip().lower())


def build_expression_sheets(character_id, paths, master=None,
                            source="image_to_image", extra=None):
    """Build the seven sheets (plus any extra sheet) from named files.

    paths: {sheet_name: {"path": ... , "digest": ...}} for the seven sheets.
    master: the master picture record ({"path", "digest"}) the sheets were made
    from. A sheet made any other way is refused by validation.
    """
    cid = character_id.strip() if isinstance(character_id, str) else ""
    if not cid:
        raise ValueError("EXPRESSION_SHEETS_INCOMPLETE: character_id")
    sheets = dict(paths or {})
    for name, row in (extra or {}).items():
        sheets[str(name)] = row
    return {
        "schema_version": SCHEMA_VERSION,
        "character_id": cid,
        "source": source,
        "master": master,
        "sheets": sheets,
    }


def validate_expression_sheets(entry):
    """All seven sheets present and hashed, made image-to-image from the master."""
    defects = []
    if not isinstance(entry, dict):
        return [_defect(EXPRESSION_SHEETS_INCOMPLETE, None,
                        "expression sheet record is not an object")]
    cid = entry.get("character_id")
    if entry.get("source") != "image_to_image":
        defects.append(_defect(EXPRESSION_NOT_FROM_MASTER, cid,
                               "sheets must be made image-to-image from the master"))
    master = entry.get("master") or {}
    if not isinstance(master, dict) or not (master.get("digest") or master.get("path")):
        defects.append(_defect(EXPRESSION_NOT_FROM_MASTER, cid,
                               "no master picture is recorded for the sheets"))
    sheets = entry.get("sheets")
    if not isinstance(sheets, dict):
        return defects + [_defect(EXPRESSION_SHEETS_INCOMPLETE, cid,
                                  "no sheets map")]
    for name in EXPRESSION_SHEETS:
        row = sheets.get(name)
        if not isinstance(row, dict) or not (row.get("path") or row.get("digest")):
            defects.append(_defect(EXPRESSION_SHEETS_INCOMPLETE, cid,
                                   "no %s expression sheet" % name))
            continue
        if not row.get("digest"):
            defects.append(_defect(EXPRESSION_UNHASHED, cid,
                                   "%s sheet is not fingerprinted" % name))
    return defects


def validate_reference_set_expressions(reference_set):
    """N-70 hook for reference_sets.validate_reference_set on a main character."""
    if not isinstance(reference_set, dict):
        return [_defect(EXPRESSION_SHEETS_INCOMPLETE, None,
                        "reference set is not an object")]
    main = reference_set.get("main")
    if not main:
        return []
    entry = reference_set.get("expressions")
    if not isinstance(entry, dict):
        return [_defect(EXPRESSION_SHEETS_INCOMPLETE,
                        reference_set.get("character_id"),
                        "main character's set carries no expression sheets")]
    if not entry.get("character_id"):
        entry = dict(entry, character_id=reference_set.get("character_id"))
    return validate_expression_sheets(entry)


__all__ = [
    "SCHEMA_VERSION", "EXPRESSION_SHEETS", "EMOTION_TO_SHEET",
    "EXPRESSION_SHEETS_INCOMPLETE", "EXPRESSION_UNHASHED",
    "EXPRESSION_NOT_FROM_MASTER", "UNKNOWN_EMOTION", "sheet_for_emotion",
    "build_expression_sheets", "validate_expression_sheets",
    "validate_reference_set_expressions",
]
