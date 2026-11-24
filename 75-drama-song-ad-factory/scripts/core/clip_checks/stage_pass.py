#!/usr/bin/env python3
"""stage_pass.py: one final pass per stage, for the same people, wardrobe and look (N-78).

Two rules from 10B, beyond the per-item checker ratio (``checker_pool``):

  * one FINAL pass per stage on contact sheets of the whole picked set;
  * the picture pass GATES the video burst, and the clip pass runs beside the
    remake burst.

The pass asks only the side-by-side questions -- same people, same wardrobe,
same look from first to last -- and reports only MAJOR items 5 and 6.
Anything else is MEDIUM and is logged, never a remake (3J.3).
"""
from __future__ import annotations

from . import severity as _SV
from . import vision as _V

TOOL_NAME = "clip_checks.stage_pass"
TOOL_VERSION = "1.0.0"

STAGE_PASS_FAILED = "STAGE_PASS_FAILED"
STAGE_PASS_UNAVAILABLE = "STAGE_PASS_UNAVAILABLE"

QUESTIONS = (
    "Same people throughout: does every character look like the same person "
    "from the first picked item to the last?",
    "Same wardrobe throughout: is each character in the same outfit and the "
    "same accessories from first to last?",
    "Same look throughout: is the whole picked set in the one locked look?",
)

#: The picture pass must finish before the video burst; the clip pass rides
#: beside the remake burst. Anything else is the caller's choice.
GATES = {"pictures": "video burst", "clips": "none (beside the remake burst)"}


def planned(stage):
    return {"stage": stage, "gates": GATES.get(stage, "none")}


def run(stage, strips, ask, controls=(None, None)):
    """Ask the three questions over every character's strip.

    ``strips``: {character id: [frame, ...]}. ``ask(images, questions)``
    returns ``{"answers": {question: bool|None}}``. A missing answer or a
    failed control pair is UNAVAILABLE at item 15, never a pass.
    """
    gate = _V.control_gate(controls[0], controls[1], STAGE_PASS_UNAVAILABLE)
    if gate:
        return {"stage": stage, "findings": [gate], "pass": False,
                "gates": GATES.get(stage, "none"), "rows": {}}
    findings, rows = [], {}
    for character, frames in (strips or {}).items():
        frames = list(frames or [])
        if len(frames) < 2:
            rows[character] = {"frames": len(frames), "checked": False}
            continue
        try:
            got = ask(frames, list(QUESTIONS))
            answers = (got or {}).get("answers") or {}
        except Exception as exc:               # noqa: BLE001  fail closed
            findings.append({"code": STAGE_PASS_UNAVAILABLE, "level": _SV.MAJOR,
                             "item": 15,
                             "text": "the %s pass could not run for %s: %s"
                                     % (stage, character, exc)})
            rows[character] = {"frames": len(frames), "checked": False}
            continue
        rows[character] = {"frames": len(frames), "checked": True,
                           "answers": {q: answers.get(q) for q in QUESTIONS}}
        for q in QUESTIONS:
            answer = answers.get(q)
            if answer is None:
                findings.append({"code": STAGE_PASS_UNAVAILABLE,
                                 "level": _SV.MAJOR, "item": 15,
                                 "text": "no answer for %r on %s"
                                         % (q, character)})
            elif answer is False:
                look = "look" in q.lower()
                findings.append({"code": STAGE_PASS_FAILED,
                                 "level": _SV.MAJOR, "item": 6 if look else 5,
                                 "text": "%s differs across the picked set: %s"
                                         % (character, q)})
    return {"stage": stage, "findings": findings,
            "pass": not _SV.only_major(findings),
            "gates": GATES.get(stage, "none"), "rows": rows}


if __name__ == "__main__":
    # Control: no control pair = unavailable; a "no" on look is item 6, on the
    # people or wardrobe it is item 5; a strip of one frame is skipped, not
    # failed.
    def truth(images, questions):
        return {"answers": {q: True for q in questions}}

    assert run("pictures", {"lead": ["a", "b"]}, truth, (True, False))["pass"]
    blind = run("pictures", {"lead": ["a", "b"]}, truth, (None, None))
    assert not blind["pass"] and blind["findings"][0]["item"] == 15
    out = run("pictures", {"lead": ["a", "b"]}, truth, (True, False))
    assert out["gates"] == "video burst"
    assert run("clips", {"lead": ["a", "b"]}, truth, (True, False))["gates"] \
        .startswith("none")
    single = run("pictures", {"lead": ["a"]}, truth, (True, False))
    assert single["pass"] and single["rows"]["lead"]["checked"] is False
    print("stage_pass: control PASS")
