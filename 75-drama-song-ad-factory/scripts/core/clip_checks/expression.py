#!/usr/bin/env python3
"""expression.py: the sixth question on pictures, clips and lip-sync takes (N-72).

The consistency check of section 3C.7 answers five items; the sixth is the
face's emotion (3G.4): "Does this face express <emotion> at this intensity,
with no smile where the tag says no smile?" A "no" is ``EXPRESSION_MISMATCH``
and the item is remade; a check that cannot run is UNAVAILABLE and never a
pass; every answer is written to the ledger.

Where it runs (section 3G.4): every keyframe, three frames of every clip
(start, middle, end), every lip-sync source picture, and every lip-sync take
at its first frame, its last frame and one frame every 3 seconds.

The question text and the fail-closed judgement live in ``vision``; this
module only runs them over the right frames and writes the ledger rows.
stdlib only; the vision model is injected.
"""
from __future__ import annotations

from . import severity as _SV
from . import vision as _V

TOOL_NAME = "clip_checks.expression"
TOOL_VERSION = "1.0.0"

EXPRESSION_MISMATCH = "EXPRESSION_MISMATCH"
EXPRESSION_CHECK_UNAVAILABLE = "EXPRESSION_CHECK_UNAVAILABLE"
QUESTION = _V.expression_question


def targets(kind, frames=None, duration_s=None):
    """The frames the sixth question runs on, by target kind.

    ``kind``: keyframe | clip | lipsync_source | lipsync_take. A clip yields
    start, middle and end; a lip-sync take yields first and last plus one
    every 3 seconds (``vision.sample_points``). Callers that already hold
    frames pass them; otherwise this returns the times to sample.
    """
    if frames:
        return {"kind": kind, "frames": list(frames)}
    if kind in ("keyframe", "lipsync_source"):
        return {"kind": kind, "frames": [], "times": None}
    times = [0.0]
    if duration_s is not None:
        d = float(duration_s)
        if kind == "clip":
            times = [0.0, d / 2.0, max(0.0, d - 0.04)]
        else:
            times = _V.sample_points(d)
            if d > 0:
                times = sorted(set(times + [max(0.0, d - 0.04)]))
    return {"kind": kind, "frames": [], "times": times}


def check(frames, emotion, intensity, ask, shot=None, character=None,
          checking_model=None, at=None):
    """Ask the sixth question of every frame; one row per frame, plus a ledger row.

    ``ask(frame, question) -> bool | None`` (True = expresses, False = does
    not, None = could not answer). Any "no" is ``EXPRESSION_MISMATCH`` at the
    fixed level (3J item 7, condition by intensity); any None is
    ``EXPRESSION_CHECK_UNAVAILABLE`` (item 15).
    """
    question = QUESTION(emotion, intensity)
    findings, answers = [], {}
    for frame in frames or []:
        try:
            answer = ask(frame, question)
        except Exception:                      # noqa: BLE001  fail closed
            answer = None
        answers[str(frame)] = answer
        if answer is None:
            findings.append({"code": EXPRESSION_CHECK_UNAVAILABLE,
                             "level": _SV.MAJOR, "item": 15,
                             "text": "the expression question was not answered "
                                     "for %s" % frame})
        elif answer is False:
            # 3J item 7 is a plain contradiction at intensity 2 or 3 only.
            # At intensity 1 it is a flag (MEDIUM, logged, not remade), and
            # N-89 widens that: intensity 1 only flags.
            try:
                strong = int(intensity) >= 2
            except (TypeError, ValueError):
                strong = True
            findings.append(_SV.finding(
                EXPRESSION_MISMATCH,
                "the face does not express %s at intensity %s"
                % (emotion, intensity),
                item=7 if strong else None,
                level=None if strong else _SV.MEDIUM,
                intensity=intensity, flagged=not strong))
    ledger = _V.ledger_row(shot, None, character, None,
                           {"expression": answers}, checking_model, at,
                           findings)
    return {"findings": findings, "answers": answers, "ledger": ledger,
            "pass": not _SV.only_major(findings)}


if __name__ == "__main__":
    # N-72: the sixth question. A "no" at intensity 2 or 3 is MAJOR item 7; at
    # intensity 1 it only flags (N-89); an unanswered frame is item 15; a clean
    # take passes; the frame plan matches 3G.4.
    no = lambda frame, q: False
    yes = lambda frame, q: True
    i1 = check(["f.png"], "pain", 1, no)
    assert i1["pass"] and i1["findings"][0]["level"] == "MEDIUM"
    i2 = check(["f.png"], "pain", 2, no)
    assert not i2["pass"] and i2["findings"][0]["item"] == 7
    i3 = check(["f.png"], "joy", 3, no)
    assert i3["findings"][0]["item"] == 7
    unanswered = check(["f.png"], "pain", 2, lambda f, q: None)
    assert unanswered["findings"][0]["item"] == 15
    assert check(["a.png", "b.png"], "joy", 2, yes)["pass"]
    assert check(["f.png"], "pain", 2, lambda f, q: 1/0)["findings"][0]["item"] \
        == 15                                        # a crash fails closed
    assert targets("clip", duration_s=6.0)["times"] == [0.0, 3.0, 5.96]
    take = targets("lipsync_take", duration_s=7.0)["times"]
    assert take[0] == 0.0 and max(take) < 7.0 and 3.0 in take
    assert len(take) >= 4                          # first, last and every 3 s
    ledger = check(["f.png"], "pain", 2, no, shot="S12")["ledger"]
    assert ledger["shot"] == "S12" and ledger["findings"]
    print("expression: control PASS")
