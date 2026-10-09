"""Droppable signature-move presets (DEL-16).

A preset is a complete, ready-to-drop camera move: the planner names a
placement (start of the whole video, start of a scene, a transition) and
gets the exact prompt phrase plus the surrounding judgement back.

Scope is deliberately narrow -- the signature dolly family and the
signature drone family named in the 2026-10-09 order. Angles, lenses,
apertures, shot sizes and the wider move list belong to the camera
vocabulary data layer, not here.

Field contract, every preset:
  id              stable machine name
  name            plain name for a storyboard card
  family          "drone" or "dolly"
  drop_at         tuple of placements this preset may be dropped at
  prompt_phrase   the exact phrase for the video model
  emotion         what it makes the viewer feel
  use_when        when the planner should reach for it
  ai_risk         {"level": low|medium|high, "note": "..."}
  per_model_test  bool -- sources disagree between models, so the move is
                  re-proven per model before it is trusted
  one_move        always True: one generated move per clip, no exceptions

Presets carry no model names, no vendor names and no tool names.
"""

DRONE_FAMILY = "drone"
DOLLY_FAMILY = "dolly"

# Placements a preset may be dropped at. A drone preset may only ever be
# dropped at an establishing or transition moment -- see rules.PLACEMENTS.
VIDEO_START = "video_start"
SCENE_START = "scene_start"
TRANSITION = "transition"
DIALOGUE_CLOSE_UP = "dialogue_close_up"
MID_SCENE = "mid_scene"
CLOSING = "closing"


def _preset(pid, name, family, drop_at, phrase, emotion, use_when,
            level, note, per_model_test):
    return {
        "id": pid,
        "name": name,
        "family": family,
        "drop_at": tuple(drop_at),
        "prompt_phrase": phrase,
        "emotion": emotion,
        "use_when": use_when,
        "ai_risk": {"level": level, "note": note},
        "per_model_test": bool(per_model_test),
        "one_move": True,
    }


PRESETS = (
    # ---- signature drone family -------------------------------------
    _preset(
        "drone_fly_in", "Drone fly-in", DRONE_FAMILY,
        (VIDEO_START, SCENE_START),
        "sweeping drone fly-in, slow aerial camera descending toward the scene",
        "Scale, freedom, awe; the piece arrives rather than begins.",
        "Open the whole video or open a scene.",
        "medium",
        "Fast flight warps terrain and buildings; keep the descent slow.",
        True),
    _preset(
        "aerial_reveal", "Aerial reveal", DRONE_FAMILY,
        (VIDEO_START, SCENE_START, TRANSITION),
        "slow aerial drone pull-back reveal, rising to show the whole location",
        "Geography, revelation, breathing room.",
        "Reveal a location; bridge two places.",
        "medium",
        "Revealed background is invented; keep the climb slow and even.",
        True),
    _preset(
        "drone_ascend", "Ascending drone", DRONE_FAMILY,
        (SCENE_START, TRANSITION),
        "drone ascending straight up, camera tilting down over the scene",
        "Release, overview, hope.",
        "Leave a small subject in a big world; hand off to a new scene.",
        "medium",
        "Straight vertical flight is the steepest terrain test; hold speed constant.",
        True),
    _preset(
        "drone_descend", "Descending drone", DRONE_FAMILY,
        (SCENE_START, TRANSITION),
        "drone descending from high above down toward the subject",
        "Arrival, focus closing in, decision.",
        "Drop from a wide into a specific place or person.",
        "medium",
        "Late-frame scale errors as the subject grows; stop short of close range.",
        True),
    _preset(
        "drone_orbit", "Drone orbit", DRONE_FAMILY,
        (TRANSITION,),
        "slow half-orbit from the drone, circling part way around the subject",
        "Importance, tension, hero status.",
        "Mark a pivotal beat between two scenes.",
        "high",
        "Orbits break three-dimensional consistency; half an orbit at most, slow.",
        True),
    _preset(
        "drone_fly_over", "Drone fly-over", DRONE_FAMILY,
        (VIDEO_START, SCENE_START, TRANSITION),
        "slow aerial drone fly-over, forward motion over the landscape",
        "Freedom, awe, geography, spectacle.",
        "Open a story; connect two places.",
        "medium",
        "Fast flight warps terrain; keep it slow.",
        True),
    _preset(
        "drone_pull_back_reveal", "Drone pull-back reveal", DRONE_FAMILY,
        (SCENE_START, TRANSITION),
        "drone pulling back and up, revealing how large the surroundings are",
        "Context, insignificance, perspective.",
        "End a beat on scale; cut to a new location.",
        "medium",
        "Pull-back invents the far background; keep the motion linear.",
        True),
    _preset(
        "drone_push_in", "Drone push-in", DRONE_FAMILY,
        (SCENE_START, TRANSITION),
        "drone pushing in from a wide establishing view down toward the subject",
        "Attention, arrival, the world narrowing to one thing.",
        "Start a scene wide and land on the subject.",
        "medium",
        "Do not finish on a close-up; stop at a medium distance.",
        True),

    # ---- signature dolly family -------------------------------------
    _preset(
        "dolly_in", "Dolly in", DOLLY_FAMILY,
        (SCENE_START,),
        "slow dolly in toward the subject",
        "Involvement, intimacy, realisation, rising threat.",
        "Start a scene; a character understands something.",
        "low",
        "One of the best-supported moves; plain wording such as 'camera slowly moves closer' is at least as reliable.",
        True),
    _preset(
        "dolly_out", "Dolly out", DOLLY_FAMILY,
        (TRANSITION, CLOSING),
        "slow dolly out, pulling back from the subject",
        "Withdrawal, loneliness, context revealed.",
        "Pull away after news; release the scene.",
        "low",
        "Revealed background is invented; keep it slow.",
        True),
    _preset(
        "dolly_and_track", "Dolly and track", DOLLY_FAMILY,
        (SCENE_START, TRANSITION),
        "camera tracks alongside the subject, moving with them through the space",
        "Momentum, journey, following along.",
        "Start a scene that begins in motion; travel between two beats.",
        "medium",
        "Two axes of motion invite drift; hold one speed and one height.",
        True),
    _preset(
        "dolly_zoom", "Dolly zoom", DOLLY_FAMILY,
        (TRANSITION,),
        "dolly zoom vertigo effect, background stretching behind a steady subject",
        "Dread, vertigo, reality shifting.",
        "One realisation, once per piece at most.",
        "high",
        "Often renders as a plain zoom or a plain push; unreliable.",
        True),
    _preset(
        "lateral_truck", "Lateral truck", DOLLY_FAMILY,
        (SCENE_START, TRANSITION),
        "camera trucks left, sideways move, parallax in the foreground",
        "Kinetic discovery, moving through a space.",
        "Start a scene that travels; reveal items along a wall.",
        "low",
        "Lateral parallax is well supported.",
        False),
)


PRESET_IDS = tuple(p["id"] for p in PRESETS)
DRONE_PRESET_IDS = tuple(p["id"] for p in PRESETS if p["family"] == DRONE_FAMILY)
DOLLY_PRESET_IDS = tuple(p["id"] for p in PRESETS if p["family"] == DOLLY_FAMILY)

_BY_ID = {p["id"]: p for p in PRESETS}


class UnknownPreset(KeyError):
    """Raised when a preset id is not in the shipped library."""


def get_preset(preset_id):
    """Return the preset record for `preset_id`; UnknownPreset if absent."""
    try:
        return _BY_ID[preset_id]
    except KeyError:
        raise UnknownPreset("unknown preset %r" % (preset_id,)) from None


def drop_preset(preset_id, placement):
    """Drop a preset at `placement` and return the shot brief fragment.

    Fails closed on an unknown preset, an unknown placement, and a drone
    preset dropped anywhere other than an establishing or transition
    moment (the placement half of the drone placement rule).
    """
    # imported here so presets stays readable without a circular import
    from .rules import DRONE_ALLOWED_PLACEMENTS, PLACEMENTS

    p = get_preset(preset_id)
    if placement not in PLACEMENTS:
        raise ValueError("unknown placement %r" % (placement,))
    if p["family"] == DRONE_FAMILY and placement not in DRONE_ALLOWED_PLACEMENTS:
        raise ValueError(
            "drone preset %r may not be dropped at %r; drone shots sit on "
            "establishing or transition moments only" % (preset_id, placement))
    if placement not in p["drop_at"]:
        raise ValueError(
            "preset %r does not drop at %r (drops at %s)"
            % (preset_id, placement, ", ".join(p["drop_at"])))
    return {
        "preset_id": p["id"],
        "family": p["family"],
        "placement": placement,
        "camera_move": p["id"],
        "prompt_phrase": p["prompt_phrase"],
        "moves": [p["id"]],
    }
