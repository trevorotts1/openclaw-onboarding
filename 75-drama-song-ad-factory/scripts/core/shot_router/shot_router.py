#!/usr/bin/env python3
"""Shot Router (N-60): one of four routes and an exact picture list per shot.

The router runs while the storyboard is being written, beside stage 4. Nothing
is drawn or bought for a shot until the router has routed it. Stdlib only: no
network, no spend, no media file, no client write.

Contract (section 3E):

* Four routes: ONE_PICTURE (start frame), TWO_PICTURE (start plus end),
  NINE_PICTURE (the reference-to-video route), LIP_SYNC (OmniHuman 2.0).
* Decision rules, first rule that fits wins (3E.2): a chosen lip-sync label;
  3 or more people / a group / a wide full room / a travelling camera; one
  continuous ordered action, an instrumental stretch or a master wide; an exact
  ending; anything else.
* Adjustments after the route is set: the model's shortest clip, the 2.5 s
  story floor (N-54), a location reference for a set used by 3 or more shots,
  the text record on the keyframe, and every keyframe drawn image-to-image from
  the locked character references.
* One record per run, ``storyboard/shot-routes.json``: for each shot the route,
  the rule number that chose it, the model, the beat it belongs to, the picture
  list and (added by later rows) the estimate and clip decision.

The Shot Router never invents a beat. A shot whose cast or place is not its
beat's is refused with SHOT_OFF_BEAT before any picture is drawn.

Exit codes (EXIT): ok 0, error 1, rejected 5.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

TOOL_NAME = "shot_router"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.shot-routes/v1"
EXIT = {"ok": 0, "error": 1, "rejected": 5}

#: The four routes of 3E.1, in table order.
ROUTES = ("ONE_PICTURE", "TWO_PICTURE", "NINE_PICTURE", "LIP_SYNC")
#: Clip shapes that ride on top of a route (3E.1 rule 2a and 2b).
CLIP_VARIANTS = ("MERGED_CLIP", "LONG_TAKE")

#: The lip-sync model is fixed (3C.1a, S-42): never a run-owner choice.
LIPSYNC_MODEL = "omnihuman-2-0"
H3_IMAGE_TO_VIDEO = "minimax-h3/image-to-video"
H3_REFERENCE_TO_VIDEO = "minimax-h3/reference-to-video"
DEFAULT_STORY_CLIP_MODEL = H3_IMAGE_TO_VIDEO
DEFAULT_PICTURE_PROVIDER = "gpt-image-2-6/sunburst"

#: N-54: no story shot is planned under 2.5 s.
MIN_STORY_SHOT_S = 2.5
#: H3's shortest clip is 4 s (3E.2 adjustment; rule H4 is lip-sync's floor).
H3_MIN_CLIP_S = 4.0

#: Labels that make a line a lip-sync candidate (3E.2 rule 1).
LIPSYNC_LABELS = frozenset({
    "lead", "choir", "lead_in_choir", "other_speaker", "backing",
    "call", "response", "unison", "overlap", "spoken",
})

#: Camera words that mean the camera travels (rule 2).
CAMERA_TRAVELS = frozenset({
    "crane", "push_through", "orbit", "tracking", "dolly", "pan", "zoom",
    "push_in", "truck", "arc", "handheld_walk", "steadicam",
})


class RouterError(ValueError):
    """A caller mistake or an undecidable request. Carries a stable code."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def _norm(value):
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_",
                  str(value).strip().lower())).strip("_")


def _num(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool))


def _owner(request):
    """The run owner's recorded choices. Never guessed, never overridden."""
    owner = request.get("run_owner") or {}
    if not isinstance(owner, dict):
        raise RouterError("INVALID_REQUEST", "run_owner must be an object")
    return {
        "story_clip_model": (owner.get("story_clip_model")
                             or DEFAULT_STORY_CLIP_MODEL),
        "picture_provider": (owner.get("picture_provider")
                             or DEFAULT_PICTURE_PROVIDER),
        "quality_mode": owner.get("quality_mode") or "standard",
    }


def _lipsync_label(shot):
    label = shot.get("lipsync_label")
    if label is None:
        label = shot.get("lipsync_role")
    if not isinstance(label, str) or not label.strip():
        return None
    label = _norm(label)
    return label if label in LIPSYNC_LABELS else None


def _camera_travels(shot):
    camera = shot.get("camera_move") or shot.get("camera_direction") or ""
    words = {_norm(w) for w in re.split(r"[^A-Za-z0-9]+", str(camera)) if w}
    return bool(words & CAMERA_TRAVELS)


def decide_route(shot, owner, context=None):
    """(route, rule, model, why) for one shot. First rule that fits wins."""
    label = _lipsync_label(shot)
    chosen = shot.get("lip_sync_passage")
    if label is not None and chosen is not False:
        return ("LIP_SYNC", 1, LIPSYNC_MODEL,
                "line label %r: a chosen lip-sync passage" % label)

    people = shot.get("character_ids") or []
    if (len(people) >= 3 or shot.get("group") or shot.get("crowd")
            or shot.get("wide_full_room") or _camera_travels(shot)):
        return ("NINE_PICTURE", 2, H3_REFERENCE_TO_VIDEO,
                "3 or more people, a group or crowd, a wide full room, "
                "or a travelling camera")

    if (shot.get("continuous_action") or shot.get("instrumental_stretch")
            or shot.get("master_wide")):
        return ("NINE_PICTURE", "2b", H3_REFERENCE_TO_VIDEO,
                "one continuous ordered action, an instrumental stretch, "
                "or a master wide")

    if shot.get("ending_exact"):
        return ("TWO_PICTURE", 3, owner["story_clip_model"],
                "the storyboard marks the ending as exact")

    return ("ONE_PICTURE", 4, owner["story_clip_model"], "anything else")


def _shot_references(shot):
    """The lock references a shot's pictures are drawn from."""
    references = {}
    characters = shot.get("character_ids") or []
    wardrobe = shot.get("wardrobe_ids") or []
    if characters:
        references["characters"] = list(characters)
    if wardrobe:
        references["wardrobe"] = list(wardrobe)
    if shot.get("location_id"):
        references["location"] = shot["location_id"]
    if shot.get("reference_assets"):
        references["assets"] = list(shot["reference_assets"])
    return references


def _picture_id(shot_id, kind, index=0):
    suffix = "" if index == 0 else "-%d" % index
    return "%s:%s%s" % (shot_id, kind, suffix)


def base_picture_list(shot, route):
    """The picture list a route makes. Later rows add candidates and sheets."""
    shot_id = shot["shot_id"]
    references = _shot_references(shot)
    if route == "LIP_SYNC":
        faces = shot.get("lip_sync_faces")
        if not isinstance(faces, int) or isinstance(faces, bool):
            faces = 1
        return [{
            "id": _picture_id(shot_id, "lip-sync-keyframe"),
            "purpose": "lip-sync keyframe",
            "kind": "lip_sync_keyframe",
            "faces": faces,
            "references": references,
            "image_to_image": True,
        }]
    if route == "TWO_PICTURE":
        return [
            {"id": _picture_id(shot_id, "start-keyframe"),
             "purpose": "start keyframe", "kind": "keyframe",
             "references": references, "image_to_image": True},
            {"id": _picture_id(shot_id, "end-keyframe"),
             "purpose": "end keyframe", "kind": "keyframe",
             "references": references, "image_to_image": True},
        ]
    if route == "NINE_PICTURE":
        return [{
            "id": _picture_id(shot_id, "reference-set"),
            "purpose": "nine-picture reference set (up to 9 from the lock)",
            "kind": "reference_set",
            "references": references,
            "image_to_image": True,
        }]
    return [{
        "id": _picture_id(shot_id, "keyframe"),
        "purpose": "keyframe",
        "kind": "keyframe",
        "references": references,
        "image_to_image": True,
    }]


def _attach_text(shot, pictures):
    """Text on screen comes from the text record, never from a guess (3A)."""
    texts = [t for t in (shot.get("text_on_screen") or []) if t]
    if not texts:
        return
    for picture in pictures:
        if picture["kind"] in ("keyframe", "lip_sync_keyframe"):
            picture["text"] = list(texts)


def apply_adjustments(shot, routed):
    """The adjustments of 3E.2 that hold whatever the route is."""
    start, end = shot.get("song_start"), shot.get("song_end")
    clip = routed.setdefault("clip", {})
    if _num(start) and _num(end) and end > start:
        seconds = round(float(end) - float(start), 3)
        clip["shot_seconds"] = seconds
        if seconds < MIN_STORY_SHOT_S:
            routed["warnings"].append({
                "code": "SHOT_UNDER_MIN",
                "detail": "shot is %.3fs, under the %.1fs story floor (N-54)"
                          % (seconds, MIN_STORY_SHOT_S),
            })
        if routed["route"] != "LIP_SYNC":
            clip.setdefault("seconds", max(H3_MIN_CLIP_S, seconds))
            clip.setdefault("trimmed", seconds < H3_MIN_CLIP_S)
    for picture in routed["pictures"]:
        if picture["kind"] in ("keyframe", "lip_sync_keyframe",
                               "composition_keyframe"):
            picture["image_to_image"] = True
    _attach_text(shot, routed["pictures"])


def check_beat(shot, routed):
    """SHOT_OFF_BEAT: a shot's cast or place must be its beat's (3E.2)."""
    beat_cast = shot.get("beat_cast")
    cast = shot.get("character_ids") or []
    if isinstance(beat_cast, (list, tuple, set)):
        extra = sorted(set(cast) - set(beat_cast))
        if extra:
            routed["errors"].append({
                "code": "SHOT_OFF_BEAT",
                "detail": "cast %s is not in beat %r's cast %s"
                          % (extra, shot.get("beat_id"), sorted(beat_cast)),
            })
    beat_location = shot.get("beat_location_id")
    location = shot.get("location_id")
    if beat_location and location and beat_location != location:
        routed["errors"].append({
            "code": "SHOT_OFF_BEAT",
            "detail": "location %r is not beat %r's place %r"
                      % (location, shot.get("beat_id"), beat_location),
        })


def route_shot(shot, owner, context=None):
    """Route one shot into its record row."""
    if not isinstance(shot, dict):
        raise RouterError("INVALID_REQUEST", "each shot must be an object")
    shot_id = shot.get("shot_id")
    if not isinstance(shot_id, str) or not shot_id.strip():
        raise RouterError("MISSING_SHOT_ID", "every shot needs a shot_id")
    route, rule, model, why = decide_route(shot, owner, context)
    routed = {
        "shot_id": shot_id,
        "beat_id": shot.get("beat_id"),
        "route": route,
        "rule": rule,
        "model": model,
        "why": why,
        "pictures": base_picture_list(shot, route),
        "warnings": [],
        "errors": [],
    }
    apply_adjustments(shot, routed)
    check_beat(shot, routed)
    return routed


def build_record(routed_shots, request):
    """The `storyboard/shot-routes.json` document (estimate and clip rows are
    added by the rows that own them)."""
    return {
        "schema": SCHEMA_VERSION,
        "run_id": request.get("run_id"),
        "run_owner": _owner(request),
        "shots": routed_shots,
        "totals": {
            "shots": len(routed_shots),
            "by_route": dict(Counter(r["route"] for r in routed_shots)),
        },
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
    }


def route_run(request):
    """Route every shot of one run. Returns an outcome envelope."""
    if not isinstance(request, dict):
        return {"outcome": "rejected", "code": "INVALID_REQUEST",
                "reason": "request must be a JSON object",
                "tool": TOOL_NAME, "tool_version": TOOL_VERSION}
    shots = request.get("shots")
    if not isinstance(shots, list) or not shots:
        return {"outcome": "rejected", "code": "INVALID_REQUEST",
                "reason": "request.shots must be a non-empty list",
                "tool": TOOL_NAME, "tool_version": TOOL_VERSION}
    try:
        owner = _owner(request)
        context = {"shots_by_id": {s.get("shot_id"): s for s in shots}}
        routed = [route_shot(shot, owner, context) for shot in shots]
    except RouterError as exc:
        return {"outcome": "rejected", "code": exc.code, "reason": exc.message,
                "tool": TOOL_NAME, "tool_version": TOOL_VERSION}

    # A set used by 3 or more shots gets one location reference picture.
    locations = Counter(s.get("location_id") for s in shots)
    for shot, row in zip(shots, routed):
        location = shot.get("location_id")
        if location and locations[location] >= 3:
            row["pictures"].append({
                "id": _picture_id(shot["shot_id"], "location-reference"),
                "purpose": "shared location reference (set used by 3+ shots)",
                "kind": "reference",
                "references": {"location": location},
                "image_to_image": True,
            })

    record = build_record(routed, request)
    errors = [e for row in routed for e in row["errors"]]
    envelope = {
        "outcome": "rejected" if errors else "ok",
        "errors": errors,
        "warnings": [w for row in routed for w in row["warnings"]],
        "shot_routes": record,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
    }
    return envelope


def write_record(path, record):
    """Write a record atomically (tmp in the same directory, then replace)."""
    destination = Path(os.path.expanduser(str(path)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(prefix=destination.name + ".",
                                   dir=str(destination.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(tmp, destination)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return str(destination)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Shot Router: routes and picture lists per shot (3E)")
    parser.add_argument("--request", required=True,
                        help="run request JSON file, or - for stdin")
    parser.add_argument("--out", default=None,
                        help="write the shot-routes record to this path")
    args = parser.parse_args(argv)
    try:
        if args.request == "-":
            request = json.load(sys.stdin)
        else:
            request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        payload = {"outcome": "rejected", "code": "INVALID_REQUEST",
                   "reason": "cannot read request: %s" % exc,
                   "tool": TOOL_NAME, "tool_version": TOOL_VERSION}
        print(json.dumps(payload, sort_keys=True))
        return EXIT["rejected"]
    payload = route_run(request)
    if args.out and payload.get("shot_routes"):
        write_record(args.out, payload["shot_routes"])
        payload["written"] = args.out
    print(json.dumps(payload, sort_keys=True))
    return EXIT.get(payload.get("outcome"), EXIT["error"])


if __name__ == "__main__":
    sys.exit(main())
