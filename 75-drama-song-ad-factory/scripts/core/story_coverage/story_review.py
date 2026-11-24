#!/usr/bin/env python3
"""The story-logic review by a different model (N-67, section 3F.3).

Before any picture is drawn, a model that did NOT write the beat sheet reads
the Story Beats first, then the story script, cold, with one instruction: list
everything a viewer would find confusing, impossible or out of order. It
answers a fixed list for every scene change (who, where, when, wearing what,
doing what, why now) and asks the Emotion Track fit question (N-69): does each
line's emotion fit its words, and does it move in a way a viewer would believe
from line to line?

The review runs ONCE, plus once more after fixes. It is not a loop: a third
run is refused with ``REVIEW_BUDGET_EXCEEDED``. Each finding is fixed in the
beat sheet or answered in one line, so every finding carries a resolution. The
report is stored with the approval package for the run owner.

This module never calls a model and never touches the network. ``build_request``
compiles the reviewer brief; the run dispatches it to ``reviewer_model`` and
hands the result to ``record_result``. The writer and reviewer model must
differ: a same-model review is refused with ``REVIEW_MODEL_NOT_DIFFERENT``.

Severity of the review's findings is added by the story severity layer (N-99).
Standard library only; pure functions over loaded dicts.
"""

from __future__ import annotations

import json

__all__ = [
    "EMOTION_QUESTIONS",
    "REVIEW_MAX_RUNS",
    "REVIEW_SCHEMA",
    "ReviewError",
    "SCENE_QUESTIONS",
    "attach_to_approval_package",
    "build_request",
    "record_result",
    "review_once",
    "scene_changes",
    "write_report",
    "selftest",
]

REVIEW_SCHEMA = "blackceo.story-review/v1"

#: one review, plus one more after the fixes; never a loop (3F.3)
REVIEW_MAX_RUNS = 2

#: the fixed list answered for every scene change (3F.3)
SCENE_QUESTIONS = (
    "who",
    "where",
    "when",
    "wearing what",
    "doing what",
    "why now",
)

#: the Emotion Track fit questions the review also asks (N-69)
EMOTION_QUESTIONS = (
    "does each line's emotion fit its words",
    "does the emotion move in a way a viewer would believe from line to line",
)

INSTRUCTION = (
    "Read the Story Beats first, then the story script. List everything a "
    "viewer would find confusing, impossible or out of order. Answer the fixed "
    "list for every scene change and the emotion-fit questions. Fix each "
    "finding in the beat sheet or answer it in one line."
)


class ReviewError(ValueError):
    """A structurally unusable review request or result."""


def _fault(code, message):
    return {"code": code, "message": message}


def _beats_list(beats):
    if isinstance(beats, dict):
        rows = beats.get("beats")
    else:
        rows = beats
    if not isinstance(rows, list):
        raise ReviewError("beats must be a list or a {'beats': [...]} record")
    return rows


def _start(beat):
    value = beat.get("start_s", beat.get("lyric_window", {}).get("start_s")
                    if isinstance(beat.get("lyric_window"), dict) else 0.0)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _beat_number(beat):
    return beat.get("beat_number", beat.get("beat", {}).get("number")
                    if isinstance(beat.get("beat"), dict) else None)


def _place(beat):
    where = beat.get("where_when") if isinstance(beat.get("where_when"), dict) else beat
    return where.get("place_id", beat.get("location_id"))


def _time_of_day(beat):
    where = beat.get("where_when") if isinstance(beat.get("where_when"), dict) else beat
    return where.get("time_of_day")


def scene_changes(beats):
    """Every place or time-of-day change between consecutive beats, in order."""
    ordered = sorted(_beats_list(beats), key=_start)
    changes = []
    for prev, cur in zip(ordered, ordered[1:]):
        prev_place, cur_place = _place(prev), _place(cur)
        prev_time, cur_time = _time_of_day(prev), _time_of_day(cur)
        if prev_place == cur_place and prev_time == cur_time:
            continue
        kinds = []
        if prev_place != cur_place:
            kinds.append("place")
        if prev_time != cur_time:
            kinds.append("time_of_day")
        changes.append({
            "from_beat": _beat_number(prev),
            "to_beat": _beat_number(cur),
            "at_s": _start(cur),
            "kind": kinds,
            "from_place": prev_place,
            "to_place": cur_place,
            "from_time_of_day": prev_time,
            "to_time_of_day": cur_time,
        })
    return changes


def build_request(*, writer_model, reviewer_model, beats, script=None, run=1):
    """Compile the reviewer brief. Returns ``{"outcome", "reason_code", ...}``.

    ``outcome`` is ``"ok"`` with a ``request`` payload, or ``"rejected"`` with an
    ``errors`` list. Same writer and reviewer model is refused; a third run is
    refused (the review is once plus once after fixes, never a loop).
    """
    errors = []
    if not (isinstance(writer_model, str) and writer_model.strip()):
        errors.append(_fault("REVIEW_MODEL_UNKNOWN", "the writer model is unknown"))
    if not (isinstance(reviewer_model, str) and reviewer_model.strip()):
        errors.append(_fault("REVIEW_MODEL_UNKNOWN", "the reviewer model is unknown"))
    if (isinstance(writer_model, str) and isinstance(reviewer_model, str)
            and writer_model.strip() and writer_model.strip() == reviewer_model.strip()):
        errors.append(_fault(
            "REVIEW_MODEL_NOT_DIFFERENT",
            "the story-logic review must run on a different model than the writer",
        ))
    if run not in range(1, REVIEW_MAX_RUNS + 1):
        errors.append(_fault(
            "REVIEW_BUDGET_EXCEEDED",
            "the review runs once, plus once after fixes; it is not a loop",
        ))
    try:
        beats_rows = _beats_list(beats)
    except ReviewError as exc:
        errors.append(_fault("REVIEW_INPUT_MISSING", str(exc)))
        beats_rows = []
    if not beats_rows:
        errors.append(_fault("REVIEW_INPUT_MISSING", "the Story Beats are absent"))

    if errors:
        return {"schema": REVIEW_SCHEMA, "outcome": "rejected",
                "reason_code": errors[0]["code"], "errors": errors, "request": None}

    request = {
        "schema": REVIEW_SCHEMA,
        "run": run,
        "instruction": INSTRUCTION,
        "reading_order": ["story_beats", "story_script"],
        "writer_model": writer_model.strip(),
        "reviewer_model": reviewer_model.strip(),
        "questions": list(SCENE_QUESTIONS),
        "emotion_questions": list(EMOTION_QUESTIONS),
        "scene_changes": scene_changes(beats_rows),
        "beats": [
            {"beat_number": _beat_number(b), "place_id": _place(b),
             "time_of_day": _time_of_day(b), "start_s": _start(b)}
            for b in sorted(beats_rows, key=_start)
        ],
        "script_rows": len(script) if isinstance(script, list) else None,
    }
    return {"schema": REVIEW_SCHEMA, "outcome": "ok", "reason_code": None,
            "errors": [], "request": request}


def _validate_finding(index, finding):
    errors = []
    if not isinstance(finding, dict):
        return [_fault("REVIEW_FINDING_INVALID", "finding %d is not an object" % index)]
    for key in ("beat_number", "code", "question", "note"):
        if finding.get(key) in (None, ""):
            errors.append(_fault(
                "REVIEW_FINDING_INVALID",
                "finding %d is missing %r" % (index, key),
            ))
    resolution = finding.get("resolution")
    if not (isinstance(resolution, dict)
            and (resolution.get("fixed_in") in ("beats", "script")
                 or (isinstance(resolution.get("answered"), str)
                     and resolution["answered"].strip()))):
        errors.append(_fault(
            "REVIEW_FINDING_UNRESOLVED",
            "finding %d is neither fixed in the beat sheet nor answered in one line"
            % index,
        ))
    return errors


def record_result(request, findings):
    """Validate a reviewer's findings and assemble the stored report.

    Every finding names a beat number, a finding code (the severity layer reads
    it, N-99), a question, a note and a resolution (a fix location or a one-line
    answer). The report is returned ready to store with the approval package.
    """
    # Accept either the build_request result or its inner ``request`` payload.
    if isinstance(request, dict) and "request" in request:
        if request.get("outcome") != "ok":
            raise ReviewError("record_result needs an accepted review request")
        req = request["request"]
    else:
        req = request
    if not isinstance(req, dict) or "reviewer_model" not in req:
        raise ReviewError("record_result needs an accepted review request")
    if not isinstance(findings, list):
        raise ReviewError("findings must be a list")
    errors = []
    for i, finding in enumerate(findings):
        errors.extend(_validate_finding(i, finding))
    if errors:
        return {"schema": REVIEW_SCHEMA, "outcome": "rejected",
                "reason_code": errors[0]["code"], "errors": errors, "report": None}
    return {
        "schema": REVIEW_SCHEMA,
        "outcome": "ok",
        "run": req.get("run"),
        "writer_model": req.get("writer_model"),
        "reviewer_model": req.get("reviewer_model"),
        "questions": req.get("questions"),
        "emotion_questions": req.get("emotion_questions"),
        "scene_changes": req.get("scene_changes"),
        "findings": findings,
        "finding_count": len(findings),
        "completed": req.get("run") == REVIEW_MAX_RUNS,
        "report": {
            "run": req.get("run"),
            "findings": findings,
        },
    }


def review_once(state):
    """Advance the run counter; refuse a third run. ``state`` is {"runs": n}."""
    runs = int((state or {}).get("runs", 0))
    if runs >= REVIEW_MAX_RUNS:
        return {"outcome": "rejected", "reason_code": "REVIEW_BUDGET_EXCEEDED",
                "runs": runs}
    return {"outcome": "ok", "runs": runs + 1, "after_fixes": runs == 1}


def attach_to_approval_package(package, review):
    """Store the review report with the approval package (3F.3).

    The package is a plain dict; the review lands under ``story_review`` with
    one entry per run. The same run number replaces its earlier entry, so a
    re-recorded run never doubles up.
    """
    if not isinstance(package, dict):
        raise ReviewError("the approval package is a dict")
    if not isinstance(review, dict) or review.get("outcome") != "ok":
        raise ReviewError("only an accepted review is stored")
    slot = package.setdefault("story_review", {"schema": REVIEW_SCHEMA, "runs": []})
    run = review.get("run")
    slot["runs"] = [r for r in slot.get("runs", []) if r.get("run") != run]
    slot["runs"].append({
        "run": run,
        "writer_model": review.get("writer_model"),
        "reviewer_model": review.get("reviewer_model"),
        "findings": review.get("findings", []),
        "completed": review.get("completed", False),
    })
    slot["runs"].sort(key=lambda r: r.get("run") or 0)
    slot["complete"] = any(r.get("run") == REVIEW_MAX_RUNS for r in slot["runs"])
    return package


def write_report(path, review):
    """Write the review report as JSON at ``path`` and return the path."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(review, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def selftest():
    beats = {"beats": [
        {"beat_number": 1, "start_s": 0.0, "location_id": "kitchen",
         "time_of_day": "dawn"},
        {"beat_number": 2, "start_s": 6.0, "location_id": "kitchen",
         "time_of_day": "dawn"},
        {"beat_number": 3, "start_s": 12.0, "location_id": "church",
         "time_of_day": "morning"},
    ]}

    same = build_request(writer_model="m1", reviewer_model="m1", beats=beats)
    assert same["outcome"] == "rejected"
    assert same["reason_code"] == "REVIEW_MODEL_NOT_DIFFERENT"

    ok = build_request(writer_model="m1", reviewer_model="m2", beats=beats)
    assert ok["outcome"] == "ok"
    assert len(ok["request"]["scene_changes"]) == 1
    assert ok["request"]["reading_order"] == ["story_beats", "story_script"]

    third = build_request(writer_model="m1", reviewer_model="m2",
                          beats=beats, run=3)
    assert third["reason_code"] == "REVIEW_BUDGET_EXCEEDED"

    review = record_result(ok["request"], [
        {"beat_number": 1, "code": "DOUBLE_ENTRANCE", "question": "where",
         "note": "she is in two rooms", "resolution": {"fixed_in": "beats"}},
    ])
    assert review["outcome"] == "ok", review

    bad = record_result(ok["request"], [
        {"beat_number": 1, "code": "DOUBLE_ENTRANCE", "question": "where",
         "note": "unresolved"},
    ])
    assert bad["reason_code"] == "REVIEW_FINDING_UNRESOLVED"

    package = attach_to_approval_package({}, review)
    assert package["story_review"]["runs"][0]["run"] == 1

    state = {"runs": 0}
    assert review_once(state)["runs"] == 1
    assert review_once({"runs": 2})["reason_code"] == "REVIEW_BUDGET_EXCEEDED"
    return True


if __name__ == "__main__":  # pragma: no cover
    assert selftest()
    print("story_review selftest OK")
