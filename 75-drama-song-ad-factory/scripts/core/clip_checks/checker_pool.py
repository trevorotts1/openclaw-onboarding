#!/usr/bin/env python3
"""checker_pool.py: one checker per 3 items, and the side-by-side pass (N-78).

Two binding rules from section 10B, in one place:

  * CHECKER RATIO. One checker per 3 pictures and one checker per 3 clips.
    ``checker_count`` is the fan-out for a stage; ``fan_out`` runs the checks
    with that many workers (or fewer, when the caller's memory reading says so).
  * SIDE-BY-SIDE PASS. One final pass per stage, on contact sheets of the
    WHOLE picked set, asking only whether the same people, the same wardrobe
    and the same look hold from first to last. The picture pass gates the
    video burst; the clip pass runs beside the remake burst.

The side-by-side pass reports ONLY MAJOR items 5 (the same people and wardrobe)
and 6 (the same look). Anything else it notices is MEDIUM and is logged, never
a remake (3J: levels do not add up).

stdlib only; the vision model is injected.
"""
from __future__ import annotations

try:
    from .severity import MAJOR, MEDIUM, finding
except ImportError:                     # script import (tests run from here)
    from severity import MAJOR, MEDIUM, finding

TOOL_NAME = "clip_checks.checker_pool"
TOOL_VERSION = "1.0.0"

#: Trevor, binding (10B): one checker per 3 pictures and per 3 clips.
ITEMS_PER_CHECKER = 3

#: The only questions the side-by-side pass may answer with a MAJOR.
SIDE_BY_SIDE_QUESTIONS = (
    "Is this the same person, face, age, hair and build, as in the other "
    "frames of this strip?",
    "Is this person wearing the same wardrobe and the same named accessories "
    "as in the other frames of this strip?",
    "Is this frame in the same locked look as the other frames of this strip?",
)

#: The MAJOR items the side-by-side pass may raise (3J.3).
SIDE_BY_SIDE_ITEMS = (5, 6)


def checker_count(n_items):
    """How many checkers a stage of ``n_items`` needs: one per 3 items."""
    try:
        n = int(n_items)
    except (TypeError, ValueError):
        return 0
    if n <= 0:
        return 0
    return (n + ITEMS_PER_CHECKER - 1) // ITEMS_PER_CHECKER


def _workers(n_items, max_workers=None):
    want = checker_count(n_items)
    if max_workers is None:
        return max(want, 1)
    try:
        cap = max(int(max_workers), 1)
    except (TypeError, ValueError):
        cap = 1
    return max(min(want, cap), 1)


def fan_out(items, check_fn, max_workers=None):
    """Run ``check_fn(item)`` for every item with one worker per 3 items.

    Returns ``{"workers", "rows", "findings", "errors"}``. ``check_fn`` must
    return a list of finding rows; one item's crash is recorded as an error
    row and never lost (it does not abort the other items).
    Threads are used because a checker waits on a network call, not on local
    work; local heavy jobs keep their own governor.
    """
    from concurrent.futures import ThreadPoolExecutor

    items = list(items or [])
    workers = _workers(len(items), max_workers)
    findings, errors = [], []

    def one(item):
        try:
            return check_fn(item)
        except Exception as exc:            # noqa: BLE001  an item never hides
            return [{"code": "CHECK_CRASHED", "level": MEDIUM, "item": None,
                     "message": "check crashed: %s" % exc, "crashed": True}]

    if workers <= 1:
        rows = [one(item) for item in items]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(one, items))
    for group in rows:
        for row in group or []:
            (errors if isinstance(row, dict) and row.get("crashed")
             else findings).append(row)
    return {"workers": workers, "rows": rows, "findings": findings,
            "errors": errors}


def side_by_side_pass(strips, ask):
    """One pass over the whole picked set, a strip per character.

    ``strips``: {character id: [frame path, ...]} — every appearance of that
    character in the picked set, in order.
    ``ask(images, questions) -> {"answers": {question: bool|None}}``.

    Returns ``{"findings", "pass", "strips"}``. A strip that cannot be read
    fails closed: the pass reports unavailable rather than passing unseen.
    """
    findings, rows = [], {}
    for character, frames in (strips or {}).items():
        frames = list(frames or [])
        if len(frames) < 2:
            rows[character] = {"frames": len(frames), "checked": False}
            continue
        try:
            got = ask(images=frames, questions=list(SIDE_BY_SIDE_QUESTIONS))
            answers = (got or {}).get("answers") or {}
        except Exception as exc:            # noqa: BLE001  fail closed
            findings.append(finding(
                "CONSISTENCY_CHECK_UNAVAILABLE",
                "the side-by-side pass could not run for %s: %s"
                % (character, exc)))
            rows[character] = {"frames": len(frames), "checked": False}
            continue
        rows[character] = {"frames": len(frames), "checked": True,
                           "answers": {q: answers.get(q)
                                       for q in SIDE_BY_SIDE_QUESTIONS}}
        for question in SIDE_BY_SIDE_QUESTIONS:
            answer = answers.get(question)
            if answer is None:
                findings.append(finding(
                    "CONSISTENCY_CHECK_UNAVAILABLE",
                    "no answer for %r on %s" % (question, character)))
            elif answer is False:
                item = (6 if "look" in question.lower() else 5)
                findings.append(finding(
                    "CHARACTER_MISMATCH" if item == 5 else "STYLE_MISMATCH",
                    "%s is not the same from first to last: %s"
                    % (character, question), item=item, character=character))
    pass_ = not any(f.get("stops") for f in findings)
    return {"findings": findings, "pass": pass_, "strips": rows}


if __name__ == "__main__":
    # Control: the ratio is arithmetic, and a blind pass is unavailable-first.
    assert checker_count(0) == 0 and checker_count(1) == 1
    assert checker_count(3) == 1 and checker_count(4) == 2
    assert checker_count(9) == 3
    out = fan_out([1, 2, 3, 4, 5, 6], lambda x: [], max_workers=2)
    assert out["workers"] == 2 and len(out["rows"]) == 6

    def truth(images, questions):
        return {"answers": {q: True for q in questions}}

    ok = side_by_side_pass({"lead": ["a", "b", "c"]}, truth)
    assert ok["pass"] and ok["strips"]["lead"]["checked"]

    def liar(images, questions):
        return {"answers": {questions[0]: False,
                            questions[1]: True, questions[2]: True}}

    bad = side_by_side_pass({"lead": ["a", "b"]}, liar)
    assert not bad["pass"] and bad["findings"][0]["item"] == 5

    blind = side_by_side_pass({"lead": ["a", "b"]},
                              lambda images, questions: {"answers": {}})
    assert not blind["pass"]
    print("checker_pool: control PASS")
