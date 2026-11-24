"""beat_sheet.story_severity: section 3J levels for the story checks (N-99).

Plan 3J. Every story check and every story-review finding carries one of three
levels, read from the fixed section 3J table and never from a checker's mood:

  * **MAJOR** -- stop that one item and repair only it. Items 8 to 12 of the
    fixed MAJOR list are the story ones (wrong singer, story-logic break, a
    lyric line with a MISMATCH, a missing required scene, a broken screen
    direction that confuses the story); a MAJOR in 8 to 12 gates the pictures.
  * **MEDIUM** -- pass and log. WEAK verdicts and the reviewer's taste notes
    are MEDIUM and are shown to the run owner.
  * **MINOR** -- count only.

Anything not on the MAJOR list is MEDIUM at most (3J). Three MEDIUM findings of
the same kind still do not add up. The truth-keeper's own MAJOR (a false built,
passed or merged) is not a story check and is judged elsewhere.

Stdlib only; data in, levels out; no model call, no write.
"""
from __future__ import annotations

from .beat_sheet import MAJOR, MEDIUM, MINOR, severity

#: items 8 to 12 are the story checks; a MAJOR among them gates the pictures
STORY_GATE_ITEMS = (8, 9, 10, 11, 12)

#: MEDIUM codes that are still shown to the run owner (3J.2)
OWNER_SHOWN_MEDIUM = ("WEAK", "WEAK_CAP_EXCEEDED", "TASTE_NOTE",
                      "REVIEW_FINDING_OPEN", "EMOTION_FIT_NOTE")


def level_of(finding):
    """One finding's level and item, filled from the fixed 3J table."""
    result = dict(finding or {})
    result.update(severity(result.get("code")))
    return result


def classify(findings):
    """Split findings into MAJOR / MEDIUM / MINOR and decide what blocks."""
    out = {"major": [], "medium": [], "minor": [], "owner_notes": [],
           "blocks_pictures": False}
    for finding in findings or []:
        record = level_of(finding)
        level = record.get("level")
        if level == MAJOR:
            out["major"].append(record)
            if record.get("item") in STORY_GATE_ITEMS:
                out["blocks_pictures"] = True
        elif level == MINOR:
            out["minor"].append(record)
        else:
            out["medium"].append(record)
            if record.get("code") in OWNER_SHOWN_MEDIUM:
                out["owner_notes"].append(record)
    return out


def gates_pictures(findings):
    """True when a MAJOR item 8 to 12 is present: nothing is drawn until fixed."""
    return classify(findings)["blocks_pictures"]


def owner_notes(findings):
    """The MEDIUM findings the run owner must see: WEAK lines and taste notes."""
    return classify(findings)["owner_notes"]


def review_levels(review):
    """Every story-review finding, levelled. Taste notes and open answers MEDIUM."""
    findings = []
    if isinstance(review, dict):
        findings = list(review.get("findings") or [])
        for note in review.get("taste_notes") or []:
            findings.append({"code": "TASTE_NOTE", "detail": note})
        for answer in review.get("answers") or []:
            if isinstance(answer, dict) and answer.get("open"):
                findings.append({"code": "REVIEW_FINDING_OPEN",
                                 "detail": answer.get("question")})
    return classify(findings)


def check_story_severity(findings):
    """Result envelope: whether the pictures gate and whether the run owner sees."""
    verdict = classify(findings)
    return {"ok": not verdict["blocks_pictures"],
            "blocks_pictures": verdict["blocks_pictures"],
            "defects": list(verdict["major"]) + list(verdict["medium"]),
            "owner_notes": verdict["owner_notes"],
            "counts": {"MAJOR": len(verdict["major"]),
                       "MEDIUM": len(verdict["medium"]),
                       "MINOR": len(verdict["minor"])}}


def _selfcheck():
    major = classify([{"code": "MISMATCH"}])
    assert major["blocks_pictures"] is True
    assert major["major"][0]["item"] == 10
    weak = classify([{"code": "WEAK"}])
    assert weak["blocks_pictures"] is False
    assert weak["owner_notes"][0]["code"] == "WEAK"
    assert weak["medium"][0]["level"] == MEDIUM
    # a MAJOR outside items 8 to 12 never gates the pictures
    other = classify([{"code": "DELIVERY_NO_AUDIO"}])
    assert other["blocks_pictures"] is False
    assert gates_pictures([{"code": "HOOK_NOT_SUNG"}]) is True


if __name__ == "__main__":
    _selfcheck()
    print("beat_sheet.story_severity selfcheck: OK")
