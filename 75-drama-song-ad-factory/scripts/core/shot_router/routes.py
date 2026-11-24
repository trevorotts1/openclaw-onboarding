"""routes.py: the Shot Router's four routes, decision rules, adjustments and record (N-60).

Section 3E. While the storyboard is written, every shot gets one route and an
exact picture list. Nothing is drawn or bought for a shot until it is routed.

Four routes (3E.1): ONE-PICTURE, TWO-PICTURE, NINE-PICTURE and LIP-SYNC.
MERGED CLIP (rule 2a) and LONG TAKE (rule 2b) are cut by the edit and carry
the route their shots already had (merged) or a nine-picture call (long take).

Decision rules (3E.2, first rule that fits wins), adjusted by N-82: when two
rules could apply, the route with more pictures wins. A shot carrying readable
writing on a prop stays a one-picture clip from its own checked still (rule
T-1 applied to routing); the lip-sync route always begins from a checked
still too, so a lip-sync line is never forced onto an unpinned frame.

Stdlib only. No network, no spend.
"""
from __future__ import annotations

import json
import re

from .common import SCHEMA_VERSION, TOOL_VERSION, ShotRouterError, as_number

def _norm(value):
    """Lower, one-word-normalised role/label spelling (``lead-in-choir`` -> role)."""
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")

ROUTES = (
    "lip_sync",
    "nine_picture",
    "merged",
    "long_take",
    "two_picture",
    "one_picture",
)

ROUTE_LABELS = {
    "one_picture": "ONE-PICTURE (start frame)",
    "two_picture": "TWO-PICTURE (start plus end)",
    "nine_picture": "NINE-PICTURE",
    "lip_sync": "LIP-SYNC",
    "merged": "MERGED CLIP (rule 2a, cut by the edit)",
    "long_take": "LONG TAKE (rule 2b, cut by the edit)",
}

LIPSYNC_ROLES = frozenset(
    {"lead", "choir", "lead_in_choir", "other_speaker", "spoken"}
)

DEFAULT_STORY_CLIP_MODEL = "minimax-h3/image-to-video"
DEFAULT_REFERENCE_MODEL = "minimax-h3/reference-to-video"
#: The lip-sync model is fixed on every run and is never a run-owner choice.
DEFAULT_LIPSYNC_MODEL = "omnihuman-2-0"

MIN_STORY_SHOT_S = 2.5
MIN_STORY_CLIP_S = 4
NINE_PICTURE_MAX = 9
KEYFRAME_CANDIDATES = 2

#: Rule order from 3E.2; used only to break a picture-count tie (N-82).
RULE_RANK = {
    "lip_sync": 1.0,
    "nine_picture": 2.0,
    "merged": 2.1,
    "long_take": 2.2,
    "two_picture": 3.0,
    "one_picture": 4.0,
}

#: Picture weight used by the "more pictures is better" tie-break (N-82).
ROUTE_PICTURE_WEIGHT = {
    "nine_picture": 9,
    "long_take": 9,
    "two_picture": 2,
    "merged": 2,
    "one_picture": 1,
    "lip_sync": 1,
}


def _shot_start(shot):
    return shot.get("start", shot.get("song_start"))


def validate_shot(shot):
    """A shot must be identifiable and bound to a non-empty time window."""
    if not isinstance(shot, dict):
        raise ShotRouterError("SHOT_INVALID", "a shot must be a dict")
    shot_id = shot.get("shot_id")
    if not shot_id:
        raise ShotRouterError("SHOT_INVALID", "shot_id is required")
    start = as_number(_shot_start(shot), "shot %s start" % shot_id)
    end = as_number(shot.get("end", shot.get("song_end")), "shot %s end" % shot_id)
    if end <= start:
        raise ShotRouterError(
            "SHOT_INVALID", "shot %s ends at or before its start" % shot_id
        )
    return shot_id, start, end


def check_shot_off_beat(shot, beat):
    """A shot must keep its beat's cast and place (3E gate, SHOT_OFF_BEAT)."""
    if not beat:
        raise ShotRouterError(
            "SHOT_OFF_BEAT",
            "shot %s names beat %r, which the story beats do not carry"
            % (shot.get("shot_id"), shot.get("beat_id")),
        )
    beat_cast = set(beat.get("cast_ids") or [])
    shot_cast = set(shot.get("cast_ids") or [])
    if shot_cast and not shot_cast.issubset(beat_cast):
        extra = sorted(shot_cast - beat_cast)
        raise ShotRouterError(
            "SHOT_OFF_BEAT",
            "shot %s casts %s, not in its beat's cast"
            % (shot.get("shot_id"), ", ".join(extra)),
        )
    beat_place = beat.get("location_id")
    shot_place = shot.get("location_id")
    if beat_place and shot_place and shot_place != beat_place:
        raise ShotRouterError(
            "SHOT_OFF_BEAT",
            "shot %s is in %s, its beat is in %s"
            % (shot.get("shot_id"), shot_place, beat_place),
        )
    return True


def _owner_choices(ctx):
    choices = (ctx or {}).get("owner_choices") or {}
    if not isinstance(choices, dict):
        raise ShotRouterError("OWNER_CHOICES_INVALID", "owner_choices must be a dict")
    return choices


def supports_start_plus_end(model, video_capabilities):
    """Does this model take a start and an end picture in ONE request?

    Read from the run's capability map (N-61). No model table lives here:
    when the registry changes, the routing follows. An unknown model is
    treated as NOT supporting both, so the chained path is the safe default.
    """
    if not model or not video_capabilities:
        return False
    cap = video_capabilities.get(model)
    if cap is None:
        return False
    if isinstance(cap, bool):
        return cap
    if isinstance(cap, dict):
        return bool(cap.get("start_plus_end_in_one_request"))
    return False


def _model_for(route, choices):
    if route == "lip_sync":
        # Never overridable: the lip-sync model is fixed on every run.
        return DEFAULT_LIPSYNC_MODEL, "lip_sync"
    if route in ("nine_picture", "long_take"):
        return (
            choices.get("reference_model") or DEFAULT_REFERENCE_MODEL,
            "reference",
        )
    return choices.get("story_clip_model") or DEFAULT_STORY_CLIP_MODEL, "story_clip"


def _reference_list(shot):
    refs = []

    def add(value):
        if value and value not in refs:
            refs.append(value)

    for ref in shot.get("reference_ids") or []:
        add(ref)
    for ref in shot.get("wardrobe_reference_ids") or []:
        add(ref)
    add(shot.get("location_reference_id"))
    add(shot.get("group_reference_id"))
    add(shot.get("expression_sheet_reference_id"))
    return refs


def _keyframe(purpose, refs, **extra):
    entry = {
        "purpose": purpose,
        "kind": "keyframe",
        "image_to_image": True,
        "refs": list(refs),
        "candidates": KEYFRAME_CANDIDATES,
    }
    entry.update(extra)
    return entry


def _stills(route, shot, refs):
    if route == "one_picture":
        return [_keyframe("keyframe", refs)]
    if route == "two_picture":
        return [
            _keyframe("keyframe_start", refs),
            _keyframe("keyframe_end", refs),
        ]
    if route in ("nine_picture", "long_take"):
        model_refs = refs[:NINE_PICTURE_MAX]
        pictures = [
            {
                "purpose": "model_references",
                "kind": "reference_set",
                "refs": model_refs,
            }
        ]
        # N-82: every nine-picture (and long-take) shot also gets a
        # composition keyframe so exact framing never rides on chance.
        pictures.append(_keyframe("composition_keyframe", model_refs))
        return pictures
    if route == "lip_sync":
        faces = shot.get("lip_faces", 1)
        if not isinstance(faces, int) or isinstance(faces, bool) or not 1 <= faces <= 3:
            raise ShotRouterError(
                "LIPSYNC_FACES_INVALID",
                "a lip-sync picture carries 1 to 3 faces, got %r" % (faces,),
            )
        return [
            _keyframe(
                "lip_sync_keyframe",
                refs,
                faces=faces,
                singers_only=True,
            )
        ]
    raise ShotRouterError("ROUTE_INVALID", "no picture list for route %r" % (route,))


#: Lip labels whose line also earns a nine-picture wide placed just before it
#: (3E.2 rule 1: "a choir line also gets a NINE-PICTURE wide shot placed just
#: before it"; section 3.4 says choir energy is the wide first, then the close).
CHOIR_WIDE_LABELS = frozenset({"choir", "lead_in_choir"})

def choir_wide_companion(shot, refs, choices):
    """The nine-picture wide a choir lip-sync line gets just before it.

    Returns a record the caller places immediately before the lip-sync shot,
    or None for a non-choir line. It never replaces the lip-sync route: the
    line is still lip-synced, the wide only sets the energy first (3.4).
    """
    label = _norm(shot.get("lyric_role") or shot.get("lipsync_role") or "")
    if label not in CHOIR_WIDE_LABELS:
        return None
    model, model_role = _model_for("nine_picture", choices)
    return {
        "shot_id": "%s-wide" % shot.get("shot_id"),
        "beat_id": shot.get("beat_id"),
        "route": "nine_picture",
        "route_label": ROUTE_LABELS["nine_picture"],
        "rule": 1,
        "rule_rank": RULE_RANK["nine_picture"],
        "role": "preceding_wide",
        "purpose": "choir wide placed just before the lip close-up",
        "model": model,
        "model_role": model_role,
        "pictures": _stills("nine_picture", shot, refs),
        "readable_writing": False,
        "notes": ["3E.2 rule 1: wide choir energy first, then the close "
                  "lip-sync piece (3.4); never one wide lip-sync job"],
    }

def _rule_number(route):
    return {
        "lip_sync": 1,
        "nine_picture": 2,
        "merged": "2a",
        "long_take": "2b",
        "two_picture": 3,
        "one_picture": 4,
    }[route]


def _wants_nine_picture(shot):
    return bool(
        (shot.get("named_people") or 0) >= 3
        or shot.get("has_group")
        or shot.get("wide_full_room")
        or shot.get("traveling_camera")
    )


def _wants_long_take(shot):
    instrumental_ok = (
        bool(shot.get("instrumental_stretch"))
        and not (shot.get("lyric_cues") or 0)
        and not shot.get("readable_writing")
    )
    return bool(
        shot.get("continuous_ordered_action")
        or instrumental_ok
        or shot.get("master_wide")
    )


def _pick_route(shot):
    """Pick among the fitting rules: more pictures wins, then rule order (N-82)."""
    if shot.get("readable_writing"):
        # T-1 on routing: writing is correct only in a checked still.
        return "one_picture"
    candidates = ["one_picture"]
    if _wants_nine_picture(shot):
        candidates.append("nine_picture")
    if _wants_long_take(shot):
        candidates.append("long_take")
    if shot.get("merge_group_id"):
        candidates.append("merged")
    if shot.get("ending_exact"):
        candidates.append("two_picture")
    return min(
        candidates,
        key=lambda route: (-ROUTE_PICTURE_WEIGHT[route], RULE_RANK[route]),
    )


def route_shot(shot, ctx=None):
    """Return one shot's routing record: route, rule, model and picture list.

    ctx keys (all optional):
      owner_choices: story_clip_model, reference_model, picture_provider,
                     quality_mode. The lip-sync model is never one of them.
      video_capabilities: model -> capability dict from the live registry.
    """
    shot_id, start, end = validate_shot(shot)
    _owner_choices(ctx)
    ctx = ctx or {}

    notes = []
    label = shot.get("lyric_role") or "none"
    readable = bool(shot.get("readable_writing"))
    refs = _reference_list(shot)
    known_character = bool(shot.get("cast_ids"))
    if known_character and not refs:
        raise ShotRouterError(
            "CAST_REFERENCE_MISSING",
            "shot %s has cast but no locked reference picture; "
            "the Shot Router never orders a text-to-image picture of a "
            "known character" % shot_id,
        )

    lip_chosen = bool(shot.get("lipsync_chosen")) and label in LIPSYNC_ROLES
    if lip_chosen:
        route = "lip_sync"
    else:
        route = _pick_route(shot)

    choices = _owner_choices(ctx)

    if route == "merged":
        # A merged clip carries the pictures its shots already had.
        base = dict(shot)
        base.pop("merge_group_id", None)
        inner = route_shot(base, ctx=ctx)
        return {
            "shot_id": shot_id,
            "beat_id": shot.get("beat_id"),
            "route": "merged",
            "route_label": ROUTE_LABELS["merged"],
            "rule": _rule_number("merged"),
            "rule_rank": RULE_RANK["merged"],
            "model": inner["model"],
            "model_role": inner["model_role"],
            "underlying_route": inner["route"],
            "merged_from": list(shot.get("merge_group_shots") or []),
            "pictures": inner["pictures"],
            "readable_writing": readable,
            "clip_window_seconds": [5, 10],
            "cut_by_edit": True,
            "notes": ["merged clip: one job, the edit cuts its pieces"],
        }

    model, model_role = _model_for(route, choices)
    pictures = _stills(route, shot, refs)
    record = {
        "shot_id": shot_id,
        "beat_id": shot.get("beat_id"),
        "route": route,
        "route_label": ROUTE_LABELS[route],
        "rule": _rule_number(route),
        "rule_rank": RULE_RANK[route],
        "model": model,
        "model_role": model_role,
        "pictures": pictures,
        "readable_writing": readable,
        "song_window_seconds": [start, end],
        "notes": notes,
    }

    if route == "lip_sync":
        audio_seconds = shot.get("lipsync_audio_seconds")
        record["lip_sync"] = {
            "model": DEFAULT_LIPSYNC_MODEL,
            "prompt": None,
            "watermark": False,
            "faces": shot.get("lip_faces", 1),
            "singers_only": True,
            "silent_people": list(shot.get("silent_people") or []),
            "audio_seconds": audio_seconds,
            "expression_sheet": shot.get("expression_sheet_reference_id"),
            "song_window_seconds": [start, end],
        }
        notes.append("lip-sync is OmniHuman 2.0 on every run; no option menu")

    if route == "two_picture":
        mode = (
            "single_request"
            if supports_start_plus_end(model, ctx.get("video_capabilities"))
            else "chained"
        )
        record["two_picture_mode"] = mode
        if mode == "chained":
            notes.append(
                "model takes one picture per request: the end keyframe becomes "
                "the next clip's start picture; both keyframes exist before the "
                "burst, so nothing waits"
            )

    # 3E.2 adjustment: a shot shorter than the model's shortest clip is made
    # at that shortest length and trimmed in time; no story shot is planned
    # under 2.5 seconds.
    duration = end - start
    if duration < MIN_STORY_SHOT_S:
        notes.append(
            "shot window %.2fs is under the %.1fs story floor; the edit retimes"
            % (duration, MIN_STORY_SHOT_S)
        )
    if route in ("one_picture", "two_picture", "nine_picture", "long_take") and (
        duration < MIN_STORY_CLIP_S
    ):
        record["clip_seconds_hint"] = MIN_STORY_CLIP_S
        notes.append(
            "rendered at the %.0fs floor and trimmed to the %.2fs window"
            % (MIN_STORY_CLIP_S, duration)
        )

    record["text_objects"] = list(shot.get("text_objects") or [])
    record["image_to_image"] = True
    return record


def apply_adjustments(records, shots):
    """3E.2 adjustments after the route is set; mutates and returns records.

    - A set appearing in 3 or more shots gets one location reference picture,
      added to each of those shots' lists.
    - Written objects come from the text record, on the keyframe.
    """
    by_id = {shot.get("shot_id"): shot for shot in shots}
    counts = {}
    for shot in shots:
        loc = shot.get("location_id")
        if loc:
            counts[loc] = counts.get(loc, 0) + 1
    for record in records:
        shot = by_id.get(record.get("shot_id")) or {}
        loc = shot.get("location_id")
        if loc and counts.get(loc, 0) >= 3:
            token = "location_reference:%s" % loc
            for picture in record.get("pictures") or []:
                refs = picture.get("refs")
                if refs is not None and token not in refs:
                    refs.append(token)
            record.setdefault("notes", []).append(
                "location appears in %d shots; one location reference added"
                % counts[loc]
            )
        record["text_objects"] = list(shot.get("text_objects") or [])
    return records


def _beat_index(beats):
    if not beats:
        return {}
    if isinstance(beats, dict):
        return beats
    return {beat.get("beat_id"): beat for beat in beats if isinstance(beat, dict)}


def build_shot_routes(shots, *, beats=None, ctx=None):
    """Route every shot and return the run's `storyboard/shot-routes.json` body."""
    if not isinstance(shots, list) or not shots:
        raise ShotRouterError("SHOTS_INVALID", "shots must be a non-empty list")
    index = _beat_index(beats)
    records = []
    seen = set()
    for shot in shots:
        shot_id, _start, _end = validate_shot(shot)
        if shot_id in seen:
            raise ShotRouterError("SHOT_DUPLICATE", "shot id %s repeats" % shot_id)
        seen.add(shot_id)
        if index:
            check_shot_off_beat(shot, index.get(shot.get("beat_id")))
        record = route_shot(shot, ctx=ctx)
        if record["route"] == "lip_sync":
            # 3E.2 rule 1: a choir line's wide is placed just before it (3.4).
            choices = _owner_choices(ctx)
            wide = choir_wide_companion(
                shot, _reference_list(shot), choices)
            if wide is not None:
                records.append(wide)
        records.append(record)
    apply_adjustments(records, shots)
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "record": "storyboard/shot-routes.json",
        "shots": records,
    }


def write_shot_routes(path, record):
    """Write the route record as JSON. The caller owns the path."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, sort_keys=False)
        handle.write("\n")
    return path


def route_summary(record):
    """Counts by route and rule for a quick read before spend."""
    summary = {"shots": 0, "by_route": {}, "by_rule": {}}
    for shot in record.get("shots") or []:
        summary["shots"] += 1
        summary["by_route"][shot["route"]] = summary["by_route"].get(shot["route"], 0) + 1
        rule = str(shot["rule"])
        summary["by_rule"][rule] = summary["by_rule"].get(rule, 0) + 1
    return summary
