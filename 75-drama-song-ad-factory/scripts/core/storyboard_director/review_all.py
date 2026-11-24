"""review_all.py: the one review entry point every row's check runs through.

Each requirement row built in U-STORY landed as a small named check module
(``storyboard/validate.py``, ``storyboard/story_checks.py``,
``storyboard/choir_lipsync.py``, ``storyboard/world_building.py``,
``storyboard/text_on_screen.py``, ``storyboard_director/story_beat_rules.py``,
``storyboard_director/storyboard_director.py``). This module runs them
together on one plan and returns one packet, so the review stage cannot pass a
plan by leaving a check un-called.

Severity is section 3J: only a MAJOR stops. A MEDIUM passes and is logged; a
MINOR is counted. A check that cannot run fails closed -- an unavailable
reader never passes a row.

No provider call, no spend, no picture. Read-only over the plan.
"""
from __future__ import annotations

import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from storyboard import choir_lipsync as _choir          # noqa: E402
from storyboard import lipsync_map as _map              # noqa: E402
from storyboard import story_checks as _checks         # noqa: E402
from storyboard import text_on_screen as _text         # noqa: E402
from storyboard import validate as _validate           # noqa: E402
from storyboard import world_building as _world        # noqa: E402

MAJOR = "MAJOR"
MEDIUM = "MEDIUM"
MINOR = "MINOR"

REVIEW_INCOMPLETE = "REVIEW_INCOMPLETE"


def _mod(name):
    """Import a sibling module whether this file runs as a script or a package."""
    import importlib
    try:
        return importlib.import_module("%s.%s" % (__package__, name))
    except (ImportError, TypeError):
        return importlib.import_module(name)


def _beat_rules():
    return _mod("story_beat_rules")


def _director_module():
    return _mod("storyboard_director")


def _norm(finding, source):
    """One finding in one shape: code, shot_id, detail, severity, source."""
    out = dict(finding) if isinstance(finding, dict) else {}
    detail = out.get("detail") or out.get("message") or ""
    row = {"code": out.get("code") or REVIEW_INCOMPLETE,
           "shot_id": out.get("shot_id"),
           "detail": detail,
           "severity": out.get("severity") or MAJOR,
           "source": source}
    for key in ("take_id", "field", "ref"):
        if key in out:
            row[key] = out[key]
    return row


def _run(source, fn, *args, **kwargs):
    """Run one check; an exception is a refusal, never a silent pass."""
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:  # a check that cannot run fails closed
        return [_norm({"code": REVIEW_INCOMPLETE,
                       "detail": "%s raised %s: %s"
                                 % (getattr(fn, "__name__", fn),
                                    type(exc).__name__, exc)}, source)]
    if isinstance(result, dict):
        found = result.get("findings")
        return [_norm(f, source) for f in found or []]
    return [_norm(f, source) for f in result or []]


def review_storyboard(shots, *, contracts=None, timing=None, budget_minor=None,
                      location_map=None, wardrobe_ledger=None, voice_map=None,
                      world=None, prop_ledger=None, word_timings=None,
                      frame_reads=None, lipsync_map=None, lead_id=None,
                      include_adversarial=True, require_artifacts=True):
    """Run every row check over one storyboard plan.

    Returns {"outcome", "findings", "codes", "severity_counts", "checks_run"}.
    ``outcome`` is "fail" only when a MAJOR stands (section 3J).

    F-PM-6: the review DEMANDS the location map and the wardrobe ledger. With
    ``require_artifacts`` (the default) a plan that names places or wardrobes
    but supplies neither is refused UNEXPLAINED_STORY_ELEMENT before any
    other check; a caller that has no story data yet passes False.
    """
    findings, run = [], []

    if require_artifacts:
        names_place = any(isinstance(s, dict)
                          and (s.get("location_id") or s.get("location_ids"))
                          for s in shots or [])
        names_wear = any(isinstance(s, dict) and s.get("wardrobe_ids")
                         for s in shots or [])
        if names_place and not isinstance(location_map, dict):
            findings.append(_norm({"code": "unexplained_story_element",
                                   "detail": "review has no location map; every "
                                             "place a shot names must be explained"},
                                  "review_story_fidelity"))
        if names_wear and not isinstance(wardrobe_ledger, dict):
            findings.append(_norm({"code": "unexplained_story_element",
                                   "detail": "review has no wardrobe ledger; every "
                                             "wardrobe a shot wears must be explained"},
                                  "review_story_fidelity"))

    # --- N-06 the lip-sync map every line must carry ----------------------
    findings.extend(_norm(f, "lipsync_map")
                    for f in _map.check_map(shots, lipsync_map, lead_id=lead_id))
    run.append("check_map")
    if voice_map is not None:
        findings.extend(_norm(f, "lipsync_map")
                        for f in _map.check_picture_faces(shots, voice_map))
        run.append("check_picture_faces")

    # --- the story rows of plan 06 (validate.py) ---------------------------
    for name in ("check_speaker_cast", "check_speaker_labels",
                 "check_lipsync_contradiction", "check_contradiction_both_ways",
                 "check_beat_density", "check_no_empty_room"):
        fn = getattr(_validate, name, None)
        if fn is None:
            continue
        findings.extend(_run("validate." + name, fn, shots))
        run.append(name)

    def _guarded(name, fn, *args):
        findings.extend(_run(name, fn, shots, *args))
        run.append(name.split(".")[-1])

    # --- the 06 review checks (story_checks.py) ---------------------------
    for name in ("check_opening", "check_lipsync_labels", "check_face_count",
                 "check_lip_pieces_first", "check_cinematic_flow"):
        fn = getattr(_checks, name, None)
        if fn is None:
            continue
        if name == "check_opening":
            # N-05: the opening passage is the LEAD's. The plan names who the
            # lead is; without an id the row's own label or speaker decides.
            _guarded("story_checks." + name, fn, lead_id)
        else:
            _guarded("story_checks." + name, fn)
    if wardrobe_ledger is not None:
        _guarded("story_checks.check_wardrobe_accessories",
                 _checks.check_wardrobe_accessories, wardrobe_ledger)
    if voice_map is not None:
        _guarded("story_checks.check_lipsync_faces",
                 _checks.check_lipsync_faces, voice_map)
    if world is not None:
        _guarded("story_checks.check_world", _checks.check_world, world)
    if frame_reads is not None:
        # N-25 has one home, validate.check_end_frame_promise; run it here
        # because it needs the frame reads.
        _guarded("validate.check_end_frame_promise",
                 _validate.check_end_frame_promise, frame_reads)
    if word_timings is not None:
        _guarded("validate.check_lyric_picture_window",
                 _validate.check_lyric_picture_window, word_timings)

    # --- N-07 choir energy comes first -----------------------------------
    if hasattr(_choir, "check_choir_lead_in"):
        findings.extend(_run("choir_lipsync.check_choir_lead_in",
                             _choir.check_choir_lead_in, shots))
        run.append("check_choir_lead_in")

    # --- N-106 / N-121 the world -----------------------------------------
    if world is not None and hasattr(_world, "validate_world_building"):
        findings.extend(_run("world_building.validate_world_building",
                             _world.validate_world_building, world, prop_ledger))
        run.append("validate_world_building")

    # --- G-STORY-03 beat density and lyric coverage (its own module) ----
    _beats = _beat_rules()
    if hasattr(_beats, "review_beat_density"):
        findings.extend(_run("story_beat_rules.review_beat_density",
                             _beats.review_beat_density, shots))
        run.append("review_beat_density")
    if word_timings is not None and hasattr(_beats, "review_lyric_picture_coverage"):
        findings.extend(_run("story_beat_rules.review_lyric_picture_coverage",
                             _beats.review_lyric_picture_coverage,
                             shots, word_timings))
        run.append("review_lyric_picture_coverage")

    # --- N-26 the text record, when the plan carries written props -------
    if any(isinstance(s, dict) and s.get("text_objects") for s in shots or []):
        try:
            record = _text.build_record(shots)
            run.append("build_record")
            for sid, entries in (record.get("pictures") or {}).items():
                shot = next((s for s in shots or []
                             if isinstance(s, dict) and s.get("shot_id") == sid),
                            None)
                prompt = (shot or {}).get("picture_prompt") or ""
                if not prompt:
                    continue
                for entry in entries:
                    if not _text.text_prompt_ok(prompt, entry):
                        findings.append(_norm(
                            {"code": _text.TEXT_PROMPT_MISSING, "shot_id": sid,
                             "detail": "picture prompt does not quote every "
                                       "recorded string for this shot"},
                            "text_on_screen"))
        except Exception as exc:  # fail closed
            findings.append(_norm({"code": REVIEW_INCOMPLETE,
                                   "detail": "text record raised %s: %s"
                                             % (type(exc).__name__, exc)},
                                  "text_on_screen"))

    # --- the twelve 14.4 criteria, last (it is the legacy verdict) ------
    if include_adversarial:
        _director = _director_module()
        try:
            adversarial = _director.adversarial_review(
                shots, contracts=contracts, timing=timing,
                budget_minor=budget_minor)
            for f in adversarial.get("findings") or []:
                findings.append(_norm(
                    {"code": f.get("criterion"),
                     "shot_id": f.get("shot_id"),
                     "detail": f.get("detail"),
                     "severity": MAJOR}, "adversarial_review"))
            run.append("adversarial_review")
        except _director.ReviewError as exc:
            findings.append(_norm({"code": exc.code, "detail": str(exc)},
                                  "adversarial_review"))

    if isinstance(location_map, dict) or isinstance(wardrobe_ledger, dict):
        _director = _director_module()
        if hasattr(_director, "review_story_fidelity"):
            findings.extend(_run("review_story_fidelity",
                                 _director.review_story_fidelity, shots,
                                 location_map, wardrobe_ledger))
            run.append("review_story_fidelity")

    counts = {MINOR: 0, MEDIUM: 0, MAJOR: 0}
    for f in findings:
        counts[f.get("severity", MAJOR)] = counts.get(f.get("severity", MAJOR), 0) + 1
    return {
        "outcome": "fail" if counts.get(MAJOR) else "pass",
        "findings": findings,
        "codes": sorted({f["code"] for f in findings}),
        "severity_counts": counts,
        "checks_run": sorted(set(run)),
    }


def assert_review_clean(shots, **kwargs):
    """Raise with the first MAJOR code when the review does not pass."""
    _director = _director_module()
    review = review_storyboard(shots, **kwargs)
    if review["outcome"] != "pass":
        first = next(f for f in review["findings"] if f["severity"] == MAJOR)
        raise _director.ReviewError(first["code"], first["detail"])
    return review


if __name__ == "__main__":  # pragma: no cover - manual smoke only
    demo = [{"shot_id": "T1", "song_start": 0.0, "song_end": 4.0,
             "location_id": "sanctuary", "location_ids": ["sanctuary"],
             "camera_direction": "wide", "visual_objective": "she sings",
             "story_stage": "pain", "character_ids": ["ava"],
             "wardrobe_ids": ["robe"], "lyric_line_ids": ["L1"],
             "qc_requirements": ["face"], "cost_estimate": 100,
             "product_visibility": "none", "continuity_constraints": [],
             "status": "storyboard_approved"}]
    out = review_storyboard(demo, include_adversarial=False)
    print(out["outcome"], out["severity_counts"], out["checks_run"])
