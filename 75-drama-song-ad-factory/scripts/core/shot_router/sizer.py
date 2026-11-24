"""sizer.py: the Clip Sizer's hard rules, signals and the fastest-finish choice (N-95).

Section 3I. The Clip Sizer runs inside the Shot Router, right after a shot's
route is known. For every shot it decides the clip's length and whether the
shot stands alone, is merged with its neighbours, or is part of a long take.
It chooses for the fastest finished video and never trades a quality rule to
get it.

**Hard rules first (3I.2).** H1 to H8 are checked before any scoring and are
never scored away.

**Then the choice (3I.3).** For each option the hard rules still allow, the
sizer works out one number: the minutes the option is expected to add. Job
time is the 9-in-10 time for the route and length; it only counts when it is
the slowest thing in the burst, because a burst takes as long as its slowest
job. Remake risk is multiplied in. Rendered-but-unused seconds cost credits,
not minutes, and break a tie.

**The signals and their thresholds (3I.3a)** are checked in a fixed order,
and the first one that decides ends the decision.

**The record (3I.4).** Per clip: route, model, length asked for, pieces, the
window the edit uses, expected minutes and credits, and the hard rule or the
choice that decided it. One report per run gives rendered seconds against used
seconds, per route and in total.

Stdlib only. No network, no spend.
"""
from __future__ import annotations

from .common import ShotRouterError, ceil_seconds, clamp

#: The hard rules of 3I.2, in the order they are checked.
HARD_RULES = (
    ("H1", "Readable writing on a prop: a SHORT one-picture clip from its own "
           "checked still, 4 to 6 seconds. Never merged into a nine-picture "
           "clip, never in a long take."),
    ("H2", "A shot that must land on a word: SHORT, cut to the lyric."),
    ("H3", "A change of room, outfit or time of day: separate clips."),
    ("H4", "A lip-sync piece is whole sentences, 5 to 30 seconds long; never "
           "starts or ends inside a sentence; a passage over 30 seconds is "
           "stitched from consecutive pieces of the same picture; never padded "
           "with silence, never cut."),
    ("H5", "Many people, hugs or hands in frame: 4 to 6 seconds, so a remake "
           "is cheap."),
    ("H6", "The run owner's model choice is never changed to get a different "
           "length."),
    ("H7", "More pictures is better: when two options tie, the one with more "
           "checked pictures wins."),
    ("H8", "A camera move needs room to play out: at least 6 seconds; 8 to 10 "
           "for a slow move across a room, a choir or a group; up to 15 when "
           "the move is the point. The move starts in the first half second "
           "and finishes before the used window ends."),
)

SHORT_MIN_S = 4.0
SHORT_MAX_S = 6.0
MOVE_MIN_S = 6.0
MOVE_SLOW_MIN_S = 8.0
MOVE_SLOW_MAX_S = 10.0
MOVE_POINT_MAX_S = 15.0
LONG_TAKE_MIN_S = 8.0
LONG_TAKE_MAX_S = 15.0
MERGED_MIN_S = 5.0
MERGED_MAX_S = 10.0
DRIFT_ONE_PICTURE_MAX_S = 10.0
LIPSYNC_MIN_S = 5.0
LIPSYNC_MAX_S = 30.0

#: 9-in-10 job times in seconds (3I.3: KIE's 119 tasks, the full-line run and
#: the 27-piece OmniHuman test). A length past 8 s is an estimate until stamped.
JOB_SECONDS_9_IN_10 = {
    "picture": 55,
    "one_picture_4s": 96,
    "one_picture_8s": 265,
    "one_picture_10s": 306,
    "two_picture": 306,
    "nine_picture": 667,
    "lip_sync": 204,
}
#: Measured credits (3E.4).
CREDITS = {
    "one_picture_4s": 32, "one_picture_5s": 40, "one_picture_6s": 48,
    "one_picture_7s": 56, "one_picture_8s": 64,
    "nine_picture_4s": 32, "nine_picture_5s": 56, "nine_picture_6s": 64,
    "nine_picture_7s": 72, "nine_picture_8s": 64,
    "lip_sync_per_second": 14,
}
USD_PER_CREDIT = 0.005
#: Remake risk planning numbers (3I.3a); each run's stamps replace them.
REMAKE_RISK = {
    "few_people_short": 0.1,
    "many_people_or_8_10s": 0.2,
    "hugs_close_hands_or_over_10s": 0.4,
}
#: 3I.3a thresholds.
THRESHOLDS = {
    "readable_writing": "any -> SHORT one-picture from the checked still; ends "
                        "the decision",
    "word_exact_lyric": "any -> SHORT, cut to the word",
    "lyric_cues": "0 -> a long take up to 15 s is allowed; 1 or more -> no clip "
                  "over 10 s",
    "stretch_length": "under 3 s -> 4 s or merge; 3 to 8 -> SHORT; neighbours "
                      "adding to 5 to 10 -> MERGED; 8+ continuous -> LONG TAKE "
                      "8 to 10; 10+ with no cue -> up to 15",
    "places_in_stretch": "1 -> merge or run long; 2 or more -> separate clips",
    "people": "1 or 2 -> one-picture; 3 or more or a group -> nine-picture; hugs "
              "or hands close to the lens -> 6 s at most unless one ordered action",
    "camera_move": "none -> length follows the shot; any move -> at least 6 s; "
                   "slow across a room, choir or group -> 8 to 10; the move is "
                   "the point -> up to 15",
    "drift_risk": "a one-picture clip is most faithful near its picture: 10 s "
                  "at most; a nine-picture clip pins no frame: every used piece "
                  "checked alone, every 3 s",
    "remake_cost": "0.1 for 1 or 2 people up to 6 s; 0.2 for 3+ people or 8 to "
                   "10 s; 0.4 for hugs and close hands or over 10 s",
    "edit_returns_to_wide": "2 or more returns in one scene -> a master wide: "
                            "one long take cut into pieces",
    "time_budget": "trending past 60 minutes -> nothing over 10 s",
}

CAMERA_MOVE_WORDS = frozenset({
    "pan", "zoom", "push", "push_in", "dolly", "crane", "truck", "track",
    "tracking", "orbit", "arc", "tilt", "handheld", "steadicam", "drone",
})


def _words(value):
    return {w for w in str(value or "").lower().replace("-", "_").split() if w}


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _window(shot):
    start = shot.get("start", shot.get("song_start"))
    end = shot.get("end", shot.get("song_end"))
    if not _num(start) or not _num(end) or float(end) <= float(start):
        raise ShotRouterError("SHOT_INVALID",
                              "shot %r needs a non-empty time window"
                              % shot.get("shot_id"))
    return round(float(end) - float(start), 3)


def camera_move_kind(shot):
    """'none', 'move', 'slow_move' or 'move_is_point' (rule H8)."""
    words = _words(shot.get("camera_move"))
    if not words & CAMERA_MOVE_WORDS:
        return "none"
    if shot.get("move_is_point"):
        return "move_is_point"
    if shot.get("slow_move") or words & {"slow", "across", "sweep"}:
        return "slow_move"
    return "move"


def hard_rules_first(shot, route):
    """H1 to H8 that end the decision. Returns a dict or None."""
    if shot.get("readable_writing"):
        return {"rule": "H1", "shape": "SHORT", "route": "one_picture",
                "seconds": clamp(_window(shot), SHORT_MIN_S, SHORT_MAX_S),
                "reason": "readable writing: correct only in a checked still"}
    if route == "lip_sync":
        audio = shot.get("lipsync_audio_seconds")
        if not _num(audio):
            raise ShotRouterError(
                "LIPSYNC_AUDIO_TOO_SHORT",
                "lip-sync shot %r has no measured audio length"
                % shot.get("shot_id"))
        if audio < LIPSYNC_MIN_S:
            raise ShotRouterError(
                "LIPSYNC_AUDIO_TOO_SHORT",
                "%.2fs of audio is under the %.1fs whole-sentence floor"
                % (audio, LIPSYNC_MIN_S))
        if shot.get("cuts_sentence"):
            raise ShotRouterError(
                "LIPSYNC_CUTS_SENTENCE",
                "lip-sync piece %r starts or ends inside a sentence"
                % shot.get("shot_id"))
        if audio > LIPSYNC_MAX_S:
            return {"rule": "H4", "shape": "LIP_STITCHED",
                    "seconds": float(ceil_seconds(audio)),
                    "pieces": ceil_seconds(audio / LIPSYNC_MAX_S),
                    "reason": "passage over 30 s: stitched from consecutive "
                              "pieces of the same picture"}
        return {"rule": "H4", "shape": "LIP_SYNC",
                "seconds": float(ceil_seconds(audio)),
                "audio_seconds": float(audio),
                "reason": "whole sentences, 5 to 30 s"}
    if shot.get("word_exact"):
        return {"rule": "H2", "shape": "SHORT", "seconds": SHORT_MIN_S,
                "reason": "must land on a word: cut to the lyric"}
    if shot.get("hugs_or_hands") and not shot.get("continuous_ordered_action"):
        return {"rule": "H5", "shape": "SHORT", "seconds": SHORT_MAX_S,
                "reason": "hugs or hands in frame: keep the remake cheap"}
    if shot.get("room_or_outfit_change"):
        return {"rule": "H3", "shape": "SHORT",
                "seconds": clamp(_window(shot), SHORT_MIN_S, SHORT_MAX_S),
                "reason": "a change of room, outfit or time of day: separate clip",
                "separate": True}
    return None


def _risk(shot, seconds):
    if shot.get("hugs_or_hands") or seconds > 10:
        return REMAKE_RISK["hugs_close_hands_or_over_10s"]
    if len(shot.get("cast_ids") or ()) >= 3 or seconds >= 8:
        return REMAKE_RISK["many_people_or_8_10s"]
    return REMAKE_RISK["few_people_short"]


def _job_seconds(route, seconds):
    if route == "lip_sync":
        return JOB_SECONDS_9_IN_10["lip_sync"]
    if route in ("nine_picture", "long_take"):
        return JOB_SECONDS_9_IN_10["nine_picture"]
    if route == "two_picture":
        return JOB_SECONDS_9_IN_10["two_picture"]
    if seconds <= 4:
        return JOB_SECONDS_9_IN_10["one_picture_4s"]
    if seconds <= 8:
        return JOB_SECONDS_9_IN_10["one_picture_8s"]
    return JOB_SECONDS_9_IN_10["one_picture_10s"]


def _credits(route, seconds):
    if route == "lip_sync":
        return CREDITS["lip_sync_per_second"] * ceil_seconds(seconds)
    whole = int(clamp(round(seconds), 4, 8))
    key = "%s_%ds" % ("nine_picture" if route in ("nine_picture", "long_take")
                      else "one_picture", whole)
    return CREDITS[key] * (2 if route == "two_picture" else 1)


def _option(route, shape, seconds, shot, pieces=1):
    job = _job_seconds(route, seconds)
    risk = _risk(shot, seconds)
    return {
        "shape": shape,
        "route": route,
        "seconds": round(float(seconds), 3),
        "pieces": pieces,
        "rendered_seconds": round(pieces * float(seconds), 3),
        "job_seconds_9_in_10": job,
        "remake_risk": risk,
        "expected_seconds": round(job * (1 + risk), 1),
        "credits": _credits(route, seconds),
    }


def _burst_note(option, burst):
    """It only counts if it is the slowest thing in the burst (3I.3)."""
    slowest = max([_job_seconds(route, option["seconds"])
                   for route in (burst or ())] + [0])
    if slowest and option["job_seconds_9_in_10"] <= slowest:
        option["burst_note"] = ("does not lengthen the burst: a slower route is "
                                "already in it")
        option["expected_seconds"] = round(
            option["remake_risk"] * option["job_seconds_9_in_10"], 1)
    return option


def _finish(option, shot, window):
    option["window_seconds"] = window
    if option.get("route") == "lip_sync":
        option["used_seconds"] = float(option.get("audio_seconds") or window)
    else:
        option["used_seconds"] = float(window)
    option["dollars"] = round(option["credits"] * USD_PER_CREDIT, 4)
    move = camera_move_kind(shot)
    option["camera_move"] = move
    if move != "none":
        option["move_starts_by_s"] = 0.5
        option["move_fits_used_window"] = option["seconds"] >= option["used_seconds"]
        if not option["move_fits_used_window"]:
            option["edit_note"] = ("the edit uses the final part of the move, or "
                                   "the shot is made static")
    if option.get("route") in ("one_picture",) and option["seconds"] > DRIFT_ONE_PICTURE_MAX_S:
        option["drift_note"] = ("a one-picture clip is most faithful near its "
                                "picture: 10 s at most")
    return option


def size_shot(shot, route, *, neighbours=None, burst=None, run=None):
    """Choose one shot's clip. Hard rules first, then the fastest finish.

    ``neighbours``: the following shots in song order. ``burst``: routes
    already in this run's video burst. ``run``: the stage-clock reading.
    """
    if not isinstance(shot, dict):
        raise ShotRouterError("SHOT_INVALID", "a shot must be an object")
    window = _window(shot)
    run = run or {}
    fixed = hard_rules_first(shot, route)
    if fixed is not None:
        option = _option(fixed.get("route") or route, fixed["shape"],
                         fixed["seconds"], shot, pieces=fixed.get("pieces", 1))
        option.update({"rule": fixed["rule"], "reason": fixed["reason"]})
        if "audio_seconds" in fixed:
            option["audio_seconds"] = fixed["audio_seconds"]
        if fixed.get("separate"):
            option["separate_clip"] = True
        return _finish(_burst_note(option, burst), shot, window)

    # The 3I.3 choice table, in order.
    if run.get("trending_past_60_minutes"):
        cap = MERGED_MAX_S
        cap_reason = "run trending past 60 minutes: nothing over 10 s (10D)"
    else:
        cap = MOVE_POINT_MAX_S
        cap_reason = None

    instrumental = (bool(shot.get("instrumental_stretch"))
                    and not (shot.get("lyric_cues") or 0)
                    and not shot.get("readable_writing"))
    if (shot.get("continuous_ordered_action") or instrumental
            or shot.get("master_wide")) and not shot.get("readable_writing"):
        high = MERGED_MAX_S if cap_reason else (
            MOVE_POINT_MAX_S if (instrumental or shot.get("master_wide"))
            else MERGED_MAX_S)
        seconds = clamp(max(window, LONG_TAKE_MIN_S), LONG_TAKE_MIN_S, high)
        option = _option("long_take", "LONG_TAKE", seconds, shot)
        option.update({
            "rule": "2b",
            "reason": cap_reason or ("one continuous ordered action, an "
                                     "instrumental stretch with no cue and no "
                                     "writing, or a master wide"),
        })
        if instrumental:
            option["checked_every_3s"] = True
        return _finish(_burst_note(option, burst), shot, window)

    floor, ceiling = move_floor(shot)
    low = max(SHORT_MIN_S, floor or SHORT_MIN_S)
    high = max(low, min(cap, ceiling or SHORT_MAX_S))
    seconds = clamp(max(window + 1.0, low), low, high)
    option = _option(route, "SHORT", seconds, shot)
    option.update({
        "rule": "H8" if floor else "shortest",
        "reason": ("camera move played out inside the clip (rule H8)" if floor
                   else "shortest job time; nearest the checked picture"),
    })
    if floor:
        option["move_floor_s"] = floor
    return _finish(_burst_note(option, burst), shot, window)


def move_floor(shot):
    """Rule H8's floor and ceiling for this shot's camera move (N-102)."""
    kind = camera_move_kind(shot)
    if kind == "move_is_point":
        return MOVE_MIN_S, MOVE_POINT_MAX_S
    if kind == "slow_move":
        return MOVE_SLOW_MIN_S, MOVE_SLOW_MAX_S
    if kind == "move":
        return MOVE_MIN_S, SHORT_MAX_S
    return None, None


def decide_clip(shot, route, **kwargs):
    """Alias kept for callers that read the section's own verb."""
    return size_shot(shot, route, **kwargs)


def camera_move_plan(shot):
    """Rule H8 in one record: how long a camera move needs and when it lands.

    Any move gets at least 6 s; a slow move across a room, a choir or a group
    gets 8 to 10 s; a move that is the point of the shot may run to 15 s. The
    move starts in the first half second and must finish before the used
    window ends, so the edit never cuts it off mid-move.
    """
    kind = camera_move_kind(shot)
    floor, ceiling = move_floor(shot)
    return {
        "kind": kind,
        "min_seconds": floor,
        "max_seconds": ceiling,
        "starts_by_s": 0.5,
        "rule": "H8",
        "applies": kind != "none",
    }


def camera_move_fit(shot, clip_seconds, used_window):
    """Does the move end inside the used window? If not, name the fallback.

    Rule H8: when the used window is shorter than the move, the edit uses the
    final part of the move, or the shot is made static. A move is never cut
    off mid-way and the picture is never changed to hide it.
    """
    plan = camera_move_plan(shot)
    if not plan["applies"]:
        return {"fits": True, "rule": "H8", "applies": False}
    # The move needs its own floor inside the clip; clipping the move's length
    # to the (often shorter) used window would wave through a move cut off
    # mid-way. The move starts by 0.5 s, so it needs 0.5 + floor of clip time.
    move_needs_s = plan["starts_by_s"] + float(plan["min_seconds"])
    fits = float(clip_seconds) + 1e-9 >= move_needs_s
    verdict = {
        "fits": fits,
        "rule": "H8",
        "applies": True,
        "move_kind": plan["kind"],
        "starts_by_s": plan["starts_by_s"],
        "min_seconds": plan["min_seconds"],
        "move_needs_seconds": move_needs_s,
        "clip_seconds": float(clip_seconds),
        "used_window_seconds": float(used_window),
    }
    if not fits:
        verdict["fallback"] = ("the edit uses the final part of the move, or "
                              "the shot is made static")
    return verdict


#: The only situations a long take of 8 to 15 seconds is allowed (N-91).
LONG_TAKE_REASONS = (
    "one continuous ordered action in one place",
    "an instrumental stretch with no lyric cue and no writing",
    "a master wide the edit returns to between lip close-ups",
)


def long_take_allowed(shot):
    """N-91: a long take is for these three situations only."""
    if shot.get("readable_writing"):
        return False, "readable writing stays on a one-picture clip"
    if shot.get("continuous_ordered_action"):
        return True, LONG_TAKE_REASONS[0]
    if (shot.get("instrumental_stretch") and not (shot.get("lyric_cues") or 0)
            and not shot.get("readable_writing")):
        return True, LONG_TAKE_REASONS[1]
    if shot.get("master_wide"):
        return True, LONG_TAKE_REASONS[2]
    return False, "not one of the three long-take situations"


def length_mix(shot, decision):
    """N-91's policy on one clip, as data a checker can read.

    * readable writing is always on a one-picture clip from its checked still;
    * a long take of 8 to 15 s only for one of the three reasons;
    * every used piece is checked alone (a long generation has more time to
      drift from the references).
    """
    allowed, reason = long_take_allowed(shot)
    writing = bool(shot.get("readable_writing"))
    long_take = decision.get("shape") == "LONG_TAKE"
    return {
        "one_picture_from_checked_still": writing,
        "long_take": long_take,
        "long_take_allowed": allowed,
        "long_take_reason": reason if long_take else None,
        "checked_alone": bool(long_take or decision.get("seconds", 0) > 8),
        "checked_every_3s": bool(long_take or decision.get("seconds", 0) > 8),
        "route_changed": False,
    }


def first_15s_trial(records):
    """The FIRST 15-second take is a measured trial beside its short version.

    N-91: nothing over 8 seconds has been measured, so the first 15-second
    take is bought alongside the short version of the same stretch; its time,
    price, failure and drift are stamped and the better result is used. Every
    later 15-second take is charged the planning risk of a long clip.
    """
    for record in records:
        clip = record.get("clip") or {}
        if clip.get("shape") != "LONG_TAKE" or float(clip.get("seconds") or 0) < 15:
            continue
        clip["trial"] = True
        clip["trial_reason"] = ("first true 15-second take: bought beside the "
                                "short version, both results compared")
        clip["short_version"] = {
            "seconds": MERGED_MAX_S,
            "bought_beside_trial": True,
            "use": "the better result wins",
        }
        clip["stamp_required"] = ["job_seconds", "credits", "failed", "drift"]
        record["clip"] = clip
        break
    return records


#: A 15-second take is bought once; its short version is 10 s or less.
SHORT_VERSION_SECONDS = 10.0


def takes_for(record):
    """N-93: how many takes a clip is bought as.

    Two takes of every nine-picture clip of up to 10 seconds, in the burst;
    the better one is used. A 15-second take is bought once, beside the short
    version of the same stretch. Every other clip is one take.
    """
    clip = record.get("clip") or {}
    route = clip.get("route") or record.get("route")
    seconds = float(clip.get("seconds") or 0)
    if seconds >= 15:
        return 1
    if route in ("nine_picture", "long_take") and seconds <= 10:
        return 2
    return 1


def apply_takes(records):
    """Set each clip's take count and what the pick is judged on."""
    for record in records:
        clip = record.get("clip") or {}
        if not clip:
            continue
        takes = takes_for(record)
        clip["takes"] = takes
        if takes == 2:
            clip["take_pick"] = ("the better take: no MAJOR, then the fewest "
                                 "MEDIUM, then the one carrying the planned words")
            clip.setdefault("notes", []).append(
                "two takes bought together in the burst")
        if float(clip.get("seconds") or 0) >= 15:
            if not clip.get("short_version"):
                clip["short_version"] = {
                    "seconds": SHORT_VERSION_SECONDS,
                    "bought_beside_trial": True,
                    "use": "the better result wins",
                }
            clip.setdefault("notes", []).append(
                "a 15-second take is bought once, beside its short version")
        record["clip"] = clip
    return records
