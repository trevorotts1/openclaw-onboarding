#!/usr/bin/env python3
"""timing.py -- S75-T26 post-music timed storyboard. Stdlib only.

Contract sources (read-only):
  * WORLD-AND-CONTINUITY.md "Late production-continuity schema" and
    "Change impact and preservation".
  * SPEC.md pipeline row 8 (refine the timed visual storyboard after the
    selected music) and the "Artifact lineage" / "Safe change propagation"
    hard gates.

A pre-song scene plan carries duration ESTIMATES. This module refines them
against the SELECTED track and produces ``timed_storyboard``: contiguous,
non-overlapping picture intervals whose sum is the track duration.

Fail-closed binding (S75-A26 clause 1): a timeline drafted against one track
cannot be bound to a different track, or to a different version of the same
track. ``bind_track`` refuses with MUSIC_TRACK_MISMATCH or
MUSIC_VERSION_MISMATCH. There is deliberately no silent re-time path: a caller
that really did select a different song must author a NEW storyboard revision,
which leaves the old timeline intact as historical evidence.

No provider call, no spend, no media file, no client write.

Run: python3 scripts/core/storyboard/timing.py
"""
from __future__ import annotations

import hashlib
import json
import pathlib

TOOL_NAME = "timed_storyboard"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.timed-storyboard/v1"
SOURCE = ("WORLD-AND-CONTINUITY.md late production continuity + change impact; "
          "SPEC.md pipeline row 8; artifact lineage and safe change propagation")

#: Endpoints closer than this are the same endpoint.
TIME_TOLERANCE_S = 0.05

#: Output kinds a timeline can push stale, per the change-impact table's
#: "Select a different intended song" row.
TIMING_OUTPUT_KINDS = (
    "timed_storyboard",
    "audio_alignment",
    "lipsync_timecodes",
)

FIXTURE_RELATIVE = ("tests", "fixtures", "timed_continuity.json")


class TimingError(ValueError):
    """Machine-readable refusal. A caller bug is BAD_INPUT, never a verdict."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def _num(value, name, positive=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TimingError("BAD_INPUT",
                          "%s must be a number, got %r" % (name, value))
    if positive and value <= 0:
        raise TimingError("BAD_INPUT",
                          "%s must be > 0, got %r" % (name, value))
    return float(value)


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise TimingError("BAD_INPUT",
                          "%s must be a non-empty string, got %r"
                          % (name, value))
    return value.strip()


def _canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"))


def _digest(obj):
    return "sha256:" + hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def track_identity(track):
    """Normalise a selected-track record.

    ``revision`` is the track's content digest -- not its display name and not
    a timestamp. Two versions of one song share ``track_id`` and differ here,
    which is what makes a version mismatch detectable at all.
    """
    if not isinstance(track, dict):
        raise TimingError("BAD_TRACK",
                          "track must be a record, got %s"
                          % type(track).__name__)
    return {
        "track_id": _text(track.get("track_id"), "track_id"),
        "revision": _text(track.get("revision"), "revision"),
        "duration_s": _num(track.get("duration_s"), "duration_s"),
    }


def bind_track(storyboard, selected_track):
    """Bind a drafted timeline to the selected track, or refuse.

    A mismatch is a REFUSAL, not a re-timing. The drafted intervals belong to
    the track the draft was authored against; silently scaling them onto a
    different song would hand back a timeline nobody planned. Callers that
    genuinely changed the song author a new storyboard revision.

    Returns the binding record on success.
    Raises MUSIC_TRACK_MISMATCH / MUSIC_VERSION_MISMATCH on a mismatch.
    """
    if not isinstance(storyboard, dict):
        raise TimingError("BAD_TIMELINE", "storyboard must be a record")

    planned_raw = storyboard.get("planned_against")
    if not isinstance(planned_raw, dict):
        raise TimingError(
            "BAD_TIMELINE",
            "storyboard.planned_against is required; an unbound timeline "
            "cannot be proven to match the selected song")
    planned = track_identity(planned_raw)
    selected = track_identity(selected_track)

    if planned["track_id"] != selected["track_id"]:
        raise TimingError(
            "MUSIC_TRACK_MISMATCH",
            "timeline was planned against %r, selected track is %r"
            % (planned["track_id"], selected["track_id"]))
    if planned["revision"] != selected["revision"]:
        raise TimingError(
            "MUSIC_VERSION_MISMATCH",
            "timeline was planned against %s revision %r, selected revision "
            "is %r" % (planned["track_id"], planned["revision"],
                       selected["revision"]))
    if abs(planned["duration_s"] - selected["duration_s"]) > TIME_TOLERANCE_S:
        raise TimingError(
            "MUSIC_VERSION_MISMATCH",
            "timeline was planned for %.3fs of %s, selected track runs %.3fs"
            % (planned["duration_s"], planned["track_id"],
               selected["duration_s"]))

    return {
        "track_id": selected["track_id"],
        "revision": selected["revision"],
        "duration_s": selected["duration_s"],
        "planned_against": dict(planned),
        "timeline_revision": _text(storyboard.get("timeline_revision"),
                                   "timeline_revision"),
        "bound": True,
    }


def _scene_weights(scenes):
    weights = []
    for scene in scenes:
        weights.append((_text(scene.get("scene_id"), "scene_id"),
                        _num(scene.get("duration_estimate_s"),
                             "duration_estimate_s")))
    ids = [sid for sid, _ in weights]
    if len(set(ids)) != len(ids):
        raise TimingError("DUPLICATE_SCENE_ID",
                          "scene_id values must be unique: %r" % (ids,))
    return weights


def _proportional(weights, total_s):
    """Scale pre-song estimates onto the real track length.

    ponytail: proportional is the fallback when no beat anchors exist; pass
    anchors (real audio timecodes) and the guess stops being used.
    """
    sum_estimate = sum(weight for _, weight in weights)
    scale = total_s / sum_estimate
    intervals, cursor = [], 0.0
    for _, weight in weights:
        end = cursor + weight * scale
        intervals.append((cursor, end))
        cursor = end
    intervals[-1] = (intervals[-1][0], total_s)   # float drift only
    return intervals


def _anchored(weights, anchors, total_s):
    """Use real audio timecodes as scene starts."""
    if not isinstance(anchors, list) or len(anchors) != len(weights):
        raise TimingError("BAD_ANCHORS",
                          "anchors must supply one start per scene")
    order = [sid for sid, _ in weights]
    starts = []
    for anchor, sid in zip(anchors, order):
        if not isinstance(anchor, dict):
            raise TimingError("BAD_ANCHORS", "each anchor must be a record")
        if _text(anchor.get("scene_id"), "scene_id") != sid:
            raise TimingError("BAD_ANCHORS",
                              "anchor order must match scene order at %r"
                              % (sid,))
        starts.append(_num(anchor.get("start_s"), "start_s",
                           positive=False))
    if abs(starts[0]) > TIME_TOLERANCE_S:
        raise TimingError("BAD_ANCHORS",
                          "first scene must start at 0.0s, got %r"
                          % (starts[0],))
    for previous, current in zip(starts, starts[1:]):
        if current - previous <= TIME_TOLERANCE_S:
            raise TimingError("BAD_ANCHORS",
                              "anchors must strictly advance; %r then %r"
                              % (previous, current))
    if starts[-1] >= total_s - TIME_TOLERANCE_S:
        raise TimingError("BAD_ANCHORS",
                          "last scene starts at %r with total %r; no room "
                          "left for the closing picture" % (starts[-1], total_s))
    intervals = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else total_s
        intervals.append((start, end))
    return intervals


def _assert_contiguous(intervals, total_s):
    if not intervals:
        raise TimingError("EMPTY_TIMELINE", "no intervals")
    if abs(intervals[0]["start_s"]) > TIME_TOLERANCE_S:
        raise TimingError("TIMELINE_GAP",
                          "timeline starts at %r, not 0.0"
                          % intervals[0]["start_s"])
    for previous, current in zip(intervals, intervals[1:]):
        if previous["end_s"] - current["start_s"] > TIME_TOLERANCE_S:
            raise TimingError(
                "TIMELINE_OVERLAP",
                "%s ends %r, %s starts %r"
                % (previous["scene_id"], previous["end_s"],
                   current["scene_id"], current["start_s"]))
        if current["start_s"] - previous["end_s"] > TIME_TOLERANCE_S:
            raise TimingError(
                "TIMELINE_GAP",
                "%s ends %r, %s starts %r"
                % (previous["scene_id"], previous["end_s"],
                   current["scene_id"], current["start_s"]))
    for interval in intervals:
        if interval["duration_s"] <= 0:
            raise TimingError("TIMELINE_ZERO_SCENE",
                              "%s has duration %r"
                              % (interval["scene_id"],
                                 interval["duration_s"]))
    if abs(intervals[-1]["end_s"] - total_s) > TIME_TOLERANCE_S:
        raise TimingError(
            "TIMELINE_SHORT",
            "timeline ends at %r but the track runs %r"
            % (intervals[-1]["end_s"], total_s))


def time_scenes(storyboard, selected_track, anchors=None):
    """Refine a pre-song scene plan into a track-bound timed storyboard.

    Estimates become actual intervals. ``anchors`` are real audio timecodes
    (one per scene, in scene order); without them the estimates are scaled
    proportionally onto the track length.
    """
    binding = bind_track(storyboard, selected_track)      # refuse first
    scenes = storyboard.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise TimingError("BAD_TIMELINE",
                          "storyboard.scenes must be a non-empty list")

    weights = _scene_weights(scenes)
    total_s = binding["duration_s"]
    pairs = (_anchored(weights, anchors, total_s) if anchors is not None
             else _proportional(weights, total_s))

    timed = []
    for (scene_id, estimate), (start, end) in zip(weights, pairs):
        timed.append({
            "scene_id": scene_id,
            "start_s": round(start, 6),
            "end_s": round(end, 6),
            "duration_s": round(end - start, 6),
            "estimate_s": estimate,
            "estimate_delta_s": round((end - start) - estimate, 6),
        })
    _assert_contiguous(timed, total_s)

    return {
        "schema_version": SCHEMA_VERSION,
        "timeline_revision": binding["timeline_revision"],
        "binding": binding,
        "track_id": binding["track_id"],
        "track_revision": binding["revision"],
        "total_s": round(total_s, 6),
        "scenes": timed,
        "digest": _digest(timed),
    }


def _intervals(scenes):
    return {scene["scene_id"]: (round(float(scene["start_s"]), 6),
                                round(float(scene["end_s"]), 6))
            for scene in scenes}


def stale_timing_outputs(previous, current):
    """Which timing outputs a re-timed storyboard actually invalidates.

    A different track revision invalidates every timeline output -- audio
    alignment and lip-sync timecodes are made against that audio. On the same
    track, only scenes whose bound interval moved go stale; a scene that kept
    its start and end keeps its alignment, its lip-sync timecodes and any
    approval recorded against them.
    """
    before, after = _intervals(previous["scenes"]), _intervals(current["scenes"])
    track_changed = previous["track_revision"] != current["track_revision"]
    stale, preserved = [], []
    for scene_id in sorted(set(before) | set(after)):
        if track_changed or before.get(scene_id) != after.get(scene_id):
            stale.append(scene_id)
        else:
            preserved.append(scene_id)

    stale_outputs = [{"kind": kind, "scene_id": scene_id}
                     for scene_id in stale for kind in TIMING_OUTPUT_KINDS]
    preserved_outputs = [{"kind": kind, "scene_id": scene_id}
                         for scene_id in preserved
                         for kind in TIMING_OUTPUT_KINDS]
    return {
        "track_changed": track_changed,
        "stale_scenes": stale,
        "preserved_scenes": preserved,
        "stale_outputs": stale_outputs,
        "preserved_outputs": preserved_outputs,
        "deleted": [],                 # never: retain as historical evidence
        "auto_regeneration": [],       # no provider call is made by this unit
    }


# -- self-check --------------------------------------------------------------

def _fixture():
    path = pathlib.Path(__file__).resolve()
    for parent in (path.parent, path.parents[1], path.parents[2], path.parents[3]):
        candidate = parent.joinpath(*FIXTURE_RELATIVE)
        if candidate.exists():
            return json.loads(candidate.read_text())
    raise TimingError("NO_FIXTURE", "tests/fixtures/timed_continuity.json absent")


def selfcheck():
    fixture = _fixture()
    intended = fixture["track"]["intended"]
    plan = fixture["scene_plan"]

    binding = bind_track(plan, intended)
    assert binding["bound"] and binding["track_id"] == intended["track_id"]

    for name in ("same_song_new_version", "different_song"):
        try:
            bind_track(plan, fixture["track"][name])
        except TimingError as exc:
            assert exc.code in ("MUSIC_TRACK_MISMATCH",
                                "MUSIC_VERSION_MISMATCH"), exc.code
        else:
            raise AssertionError("binding accepted %r" % (name,))

    try:
        bind_track(plan, fixture["track"]["duration_only_drift"])
    except TimingError as exc:
        assert exc.code == "MUSIC_VERSION_MISMATCH", exc.code
    else:
        raise AssertionError("duration drift accepted")

    scaled = time_scenes(plan, intended)
    expected = fixture["expected_proportional"]
    assert scaled["total_s"] == expected["total_s"]
    assert [s["duration_s"] for s in scaled["scenes"]] == expected["durations_s"]
    assert scaled["digest"] == expected["digest"]

    timed = time_scenes(plan, intended, anchors=fixture["anchors"])
    expected_anchored = fixture["expected_anchored"]
    assert [s["duration_s"] for s in timed["scenes"]] == \
        expected_anchored["durations_s"]
    assert timed["digest"] == expected_anchored["digest"]
    assert timed["binding"]["revision"] == intended["revision"]

    moved = time_scenes(plan, intended, anchors=fixture["retime_anchors"])
    affected = stale_timing_outputs(timed, moved)
    assert affected["stale_scenes"] == fixture["retime_expected_stale_scenes"]
    assert affected["preserved_scenes"] == \
        fixture["retime_expected_preserved_scenes"]
    assert affected["auto_regeneration"] == []
    assert affected["deleted"] == []

    other = time_scenes(dict(plan, planned_against=fixture["track"]["different_song"],
                             timeline_revision="tl_other_song"),
                        fixture["track"]["different_song"])
    whole = stale_timing_outputs(timed, other)
    assert whole["track_changed"] and whole["preserved_scenes"] == []
    assert whole["stale_scenes"] == [s["scene_id"] for s in plan["scenes"]]

    print("storyboard.timing selfcheck OK -- %d scenes bound to %s"
          % (len(timed["scenes"]), intended["track_id"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(selfcheck())
