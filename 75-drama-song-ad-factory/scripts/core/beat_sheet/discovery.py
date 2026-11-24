"""beat_sheet.discovery -- who is seen in every beat (N-123, U-SCRIPT half).

Section 3C.11 puts Cast Discovery in three steps; this module carries the part
the beats own: every beat either names the people a viewer would see (the lead,
the named cast, and the ancillary people the place needs) or says, in the one
sentinel sentence, that nobody else is seen. Two discovery lists, one per song
section and one from a cold reader, are compared; a person on one list and not
the other is settled before the completeness gate.

The Character Bible, the World Bible and the profiles are U-STORY and U-WORLD;
this module only refuses beats that leave the question blank.

Pure data checks. Stdlib only, no IO, no model call, no mutation.
"""
from __future__ import annotations

from .beat_sheet import _defect, _norm

#: the one sentence a beat uses when nobody else is seen (Story Beats table)
NOBODY_ELSE = "nobody else is seen here"


def _beats(record):
    if isinstance(record, dict):
        value = record.get("beats")
        return value if isinstance(value, list) else []
    return record if isinstance(record, list) else []


def _seen(beat):
    """The 'who else is seen' value, from either beats schema in this unit."""
    who = beat.get("who") if isinstance(beat, dict) else None
    if isinstance(who, dict) and "else_seen" in who:
        return who.get("else_seen")
    return beat.get("who_else_seen") if isinstance(beat, dict) else None


def seen_field_defects(record):
    """Every beat answers 'who would a viewer see here' (CAST_DISCOVERY_INCOMPLETE)."""
    defects = []
    beats = _beats(record)
    if not beats:
        defects.append(_defect("CAST_DISCOVERY_INCOMPLETE", "/beats",
                               "the beats carry no cast discovery"))
        return defects
    for index, beat in enumerate(beats):
        number = beat.get("beat_number", index) if isinstance(beat, dict) else index
        value = _seen(beat)
        pointer = "/beats/%s/who_else_seen" % (number,)
        if isinstance(value, str):
            names = [value]
        elif isinstance(value, list):
            names = value
        else:
            defects.append(_defect("CAST_DISCOVERY_INCOMPLETE", pointer,
                                   "beat %s does not say who else is seen" % (number,)))
            continue
        names = [item for item in names if isinstance(item, str) and item.strip()]
        if not names:
            defects.append(_defect("CAST_DISCOVERY_INCOMPLETE", pointer,
                                   "beat %s leaves the question blank; name the people "
                                   "or say '%s'" % (number, NOBODY_ELSE)))
            continue
        normalized = [_norm(item) for item in names]
        if NOBODY_ELSE in normalized and len(normalized) > 1:
            defects.append(_defect("CAST_DISCOVERY_INCOMPLETE", pointer,
                                   "beat %s mixes '%s' with named people"
                                   % (number, NOBODY_ELSE)))
    return defects


def compare_lists(section_lists, cold_reader):
    """The two discovery lists must agree before the completeness gate (3C.11)."""
    def _names(value):
        if isinstance(value, dict):
            value = value.get("names") or value.get("people") or []
        return {_norm(item): item for item in (value or []) if isinstance(item, str)}

    first = _names(section_lists)
    second = _names(cold_reader)
    only_first = sorted(first[key] for key in set(first) - set(second))
    only_second = sorted(second[key] for key in set(second) - set(first))
    defects = []
    if only_first or only_second:
        defects.append(_defect(
            "CAST_DISCOVERY_INCOMPLETE", "/cast-discovery",
            "the lists disagree: only in the section list %s; only in the cold "
            "reader %s" % (only_first, only_second)))
    return {"ok": not defects, "only_section": only_first,
            "only_cold": only_second, "defects": defects}


def _selfcheck():
    record = {"beats": [
        {"beat_number": 1, "who": {"else_seen": NOBODY_ELSE}},
        {"beat_number": 2, "who_else_seen": ["cashier", "truck driver"]},
    ]}
    assert seen_field_defects(record) == []
    broken = {"beats": [{"beat_number": 1, "who": {"else_seen": []}},
                        {"beat_number": 2, "who_else_seen": [NOBODY_ELSE, "janitor"]}]}
    verdict = seen_field_defects(broken)
    assert len(verdict) == 2 and all(d["code"] == "CAST_DISCOVERY_INCOMPLETE" for d in verdict)
    compared = compare_lists(["lead", "cashier"], ["lead", "janitor"])
    assert compared["only_section"] == ["cashier"] and compared["only_cold"] == ["janitor"]
    assert compare_lists(["lead"], ["lead"])["ok"] is True


if __name__ == "__main__":
    _selfcheck()
    print("beat_sheet.discovery selfcheck: OK")
