"""DEL-16 camera rules: one move per clip, signature minimums, drone placement.

Every check returns a list of machine-stable error codes and never raises
for an ordinary rule violation, so the planner can collect every problem in
one pass and fail closed before any video is generated. The one exception
is `require_generated_move`, which raises for callers that want a hard stop.

Rules enforced here
-------------------
1. ONE MOVE PER CLIP. Exactly one generated camera move per clip
   (`MAX_MOVES_PER_CLIP`). Clips run about four to six seconds. Stacked
   moves drift and jitter.
2. WHIP PAN IS NEVER A SINGLE GENERATED MOVE. Whip pan is built as an edit
   transition between two clips (`EDIT_TRANSITION_MOVES`).
3. TWO-MINUTE SIGNATURE MINIMUMS. A video of two minutes or more carries
   at least one drone or aerial shot and at least two dolly shots -- unless
   the client declines the signature moves.
4. DRONE PLACEMENT. A drone shot sits on an establishing or transition
   moment and never on a dialogue close-up, mid-scene action or a closing
   beat.
5. PER-MODEL TEST FLAG. Sources disagree between models, so every move
   carries `MODEL_TEST_FLAG` and is re-proven per model before trust.

Client-facing text carried by this contract
--------------------------------------------
CLIENT_GUIDE_DRONE_LINE is shipped verbatim in the client guide. It is
English, it names no model and no tool, and any client-facing document
built from it renders at MIN_CLIENT_PDF_POINT_SIZE points or larger.
"""

from .presets import (
    DIALOGUE_CLOSE_UP,
    DOLLY_FAMILY,
    DRONE_FAMILY,
    MID_SCENE,
    VIDEO_START,
    SCENE_START,
    TRANSITION,
    CLOSING,
    PRESETS,
    get_preset,
)

# --------------------------------------------------------------------------- #
# 1-2. one generated move per clip; whip pan refused as one
# --------------------------------------------------------------------------- #
MAX_MOVES_PER_CLIP = 1
CLIP_SECONDS_MIN = 4.0
CLIP_SECONDS_MAX = 6.0

# Moves that are an edit transition, never one generated clip.
EDIT_TRANSITION_MOVES = frozenset({"whip_pan"})

REFUSED_AS_GENERATED_MOVE = "REFUSED_WHIP_PAN_AS_GENERATED_MOVE"
TOO_MANY_MOVES = "TOO_MANY_MOVES_PER_CLIP"
CLIP_TOO_LONG = "CLIP_TOO_LONG_FOR_ONE_MOVE"


class RefusedMove(RuntimeError):
    """Raised when a move may not be generated as a single clip."""


def check_generated_move(move_id):
    """[] when `move_id` may be one clip's single generated move."""
    if move_id in EDIT_TRANSITION_MOVES:
        return [REFUSED_AS_GENERATED_MOVE]
    return []


def require_generated_move(move_id):
    """Hard-stop form of check_generated_move; raises RefusedMove."""
    if move_id in EDIT_TRANSITION_MOVES:
        raise RefusedMove(
            "%r is an edit transition between two clips, never a single "
            "generated move" % (move_id,))
    return move_id


def _moves_of(clip):
    """The move list of a clip record, tolerating a bare `move` field."""
    if not isinstance(clip, dict):
        return []
    moves = clip.get("moves")
    if isinstance(moves, (list, tuple)):
        return [m for m in moves if isinstance(m, str) and m]
    single = clip.get("move") or clip.get("camera_move")
    if isinstance(single, str) and single:
        return [single]
    return []


def check_one_move_per_clip(clips):
    """[] when every clip carries at most one generated move.

    Also reports a clip longer than six seconds: a clip that long cannot
    hold one move without morphing.
    """
    errs = []
    if not isinstance(clips, (list, tuple)):
        return [TOO_MANY_MOVES]
    for clip in clips:
        cid = clip.get("clip_id") or clip.get("shot_id") or "?" \
            if isinstance(clip, dict) else "?"
        moves = _moves_of(clip)
        if len(moves) > MAX_MOVES_PER_CLIP:
            errs.append("%s:%s" % (TOO_MANY_MOVES, cid))
        for m in moves:
            for code in check_generated_move(m):
                errs.append("%s:%s" % (code, cid))
        if isinstance(clip, dict):
            start, end = clip.get("start"), clip.get("end")
            if isinstance(start, (int, float)) and isinstance(end, (int, float)) \
                    and not isinstance(start, bool) and not isinstance(end, bool) \
                    and end - start > CLIP_SECONDS_MAX:
                errs.append("%s:%s" % (CLIP_TOO_LONG, cid))
    return errs


# --------------------------------------------------------------------------- #
# 3. two-minute drone and dolly minimums
# --------------------------------------------------------------------------- #
TWO_MINUTE_SECONDS = 120
MIN_DRONE_SHOTS = 1
MIN_DOLLY_SHOTS = 2

MISSING_DRONE_SHOT = "MISSING_DRONE_SHOT_AT_LEAST_120S"
MISSING_DOLLY_SHOT = "MISSING_DOLLY_SHOT_AT_LEAST_120S"


def family(move_id):
    """"drone", "dolly" or "other" for a preset id."""
    try:
        return get_preset(move_id)["family"]
    except KeyError:
        return "other"


def _move_ids(shots):
    ids = []
    for sh in shots or ():
        if isinstance(sh, str):
            ids.append(sh)
        elif isinstance(sh, dict):
            ids.extend(_moves_of(sh))
    return ids


def check_signature_minimums(duration_seconds, shots, client_declined=False):
    """[] when a video of two minutes or more meets the drone/dolly floors.

    duration_seconds  running time of the video
    shots             shot records, clip records, or bare move ids
    client_declined   True when the client declined the signature moves;
                      the rule then does not apply

    Under two minutes the rule does not apply and this returns [].
    """
    if client_declined:
        return []
    if not isinstance(duration_seconds, (int, float)) \
            or isinstance(duration_seconds, bool):
        return []
    if duration_seconds < TWO_MINUTE_SECONDS:
        return []
    ids = _move_ids(shots)
    drone = [m for m in ids if family(m) == DRONE_FAMILY]
    dolly = [m for m in ids if family(m) == DOLLY_FAMILY]
    errs = []
    if len(drone) < MIN_DRONE_SHOTS:
        errs.append(MISSING_DRONE_SHOT)
    if len(dolly) < MIN_DOLLY_SHOTS:
        errs.append(MISSING_DOLLY_SHOT)
    return errs


# --------------------------------------------------------------------------- #
# 4. drone placement
# --------------------------------------------------------------------------- #
PLACEMENTS = (
    VIDEO_START, SCENE_START, TRANSITION,
    DIALOGUE_CLOSE_UP, MID_SCENE, CLOSING,
)

# A drone shot sits on an establishing moment (the video opening, a scene
# opening) or a transition moment. Nothing else. Closing is not one of
# them: a closing beat belongs to a pull-back or a dolly out on the ground.
DRONE_ALLOWED_PLACEMENTS = frozenset({VIDEO_START, SCENE_START, TRANSITION})

DRONE_MISPLACED = "DRONE_MISPLACED"
UNKNOWN_PLACEMENT = "UNKNOWN_PLACEMENT"


def check_drone_placement(shots):
    """[] when every drone shot sits on an establishing or transition moment.

    A drone shot on a dialogue close-up, mid-scene action or any unknown
    placement is an error. Non-drone shots are not judged by this rule.
    """
    errs = []
    for sh in shots or ():
        if not isinstance(sh, dict):
            continue
        moves = _moves_of(sh)
        if not any(family(m) == DRONE_FAMILY for m in moves):
            continue
        sid = sh.get("shot_id") or sh.get("clip_id") or "?"
        placement = sh.get("placement")
        if placement not in PLACEMENTS:
            errs.append("%s:%s:%s" % (UNKNOWN_PLACEMENT, sid, placement))
        elif placement not in DRONE_ALLOWED_PLACEMENTS:
            errs.append("%s:%s:%s" % (DRONE_MISPLACED, sid, placement))
    return errs


# --------------------------------------------------------------------------- #
# 5. per-model test flag
# --------------------------------------------------------------------------- #
MODEL_TEST_FLAG = "per_model_test"

# Moves whose wording is actively disputed between guides: one guide warns
# that this jargon is less reliable than plain wording, another lists it as
# a primary control. These may never ship with the per-model test flag
# cleared. Lateral truck is deliberately absent -- no guide disputes it.
DISPUTED_BETWEEN_MODELS = frozenset({
    "dolly_in", "dolly_out", "dolly_and_track", "dolly_zoom",
    "push_in", "pull_out", "crane",
})


def check_model_test_flag(entries=None):
    """[] when every move entry carries a boolean per-model test flag."""
    errs = []
    for e in (PRESETS if entries is None else entries):
        if not isinstance(e, dict):
            errs.append("BAD_ENTRY")
            continue
        eid = e.get("id", "?")
        if MODEL_TEST_FLAG not in e:
            errs.append("MISSING_PER_MODEL_TEST_FLAG:%s" % eid)
        elif not isinstance(e[MODEL_TEST_FLAG], bool):
            errs.append("BAD_PER_MODEL_TEST_FLAG:%s" % eid)
        elif e[MODEL_TEST_FLAG] is False and e.get("id") in DISPUTED_BETWEEN_MODELS:
            errs.append("DISPUTED_MOVE_NOT_FLAGGED:%s" % eid)
    return errs


# --------------------------------------------------------------------------- #
# client-facing contract
# --------------------------------------------------------------------------- #
CLIENT_GUIDE_DRONE_LINE = "Your video can open with a sweeping drone fly-in."

# Client-facing documents, including any PDF rendering of the client guide,
# set their body type at no smaller than this.
MIN_CLIENT_PDF_POINT_SIZE = 12
