"""DEL-16 shot brief builder — every brief carries the full vocabulary.

Stdlib only. One camera move per clip; clips of about four to six seconds;
text and logos are added in post; prompts carry "shallow depth of field"
rather than an f-stop number because lens and f-stop words act as style
cues; lens and aperture matched to emotion; every scene starts on an
establishing wide.
"""
from __future__ import annotations

try:
    from . import vocabulary as V
except ImportError:  # running the folder as a script directory
    import vocabulary as V  # type: ignore


class BriefError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def aperture_intent(f_number):
    """Map an f-number to wide_open | mid | stopped_down. None when unknown."""
    if isinstance(f_number, bool) or not isinstance(f_number, (int, float)):
        return None
    return V.APERTURE_INTENT.get(float(f_number))


def aperture_phrase(f_number):
    """Plain-language aperture phrase; never an f-stop number in a prompt."""
    f = float(f_number)
    for val, label in V.APERTURES:
        if abs(val - f) < 1e-9:
            return label
    return "mid"


def shot_length_planning_range(framing):
    """Planning-range seconds for a framing; None when framing unknown."""
    return V.FRAMING_SECONDS_PLANNING_RANGE.get(framing)


def default_shot_length(framing):
    """Midpoint of the framing's planning range (planning range, not a
    measured standard)."""
    r = shot_length_planning_range(framing)
    if r is None:
        return None
    return round((r[0] + r[1]) / 2.0, 2)


def build_shot_brief(shot_id, framing, angle, camera_move, lens_mm,
                     f_number, emotion, content_mode, duration_seconds=None,
                     coverage_role=None, lighting=None, eyeline=None,
                     camera_side="a", screen_direction=None, scene_id="scene-1",
                     character_ids=None, subject_id=None,
                     dialogue_or_narration=False,
                     text_overlay_post=None, logo_overlay_post=None,
                     transition_from=None, rack_focus_from=None):
    """Build one shot brief carrying the full DEL-16 vocabulary.

    content_mode is music | dialogue | narration — the same rules apply for
    music and for dialogue or narration alike. Text and logos are added in
    post: overlay strings live on the brief's *_overlay_post fields and never
    enter the generation prompt.

    duration_seconds defaults to the framing's planning-range midpoint.
    Raises BriefError on vocabulary or rule violations at build time so a
    bad brief cannot be planned.
    """
    if content_mode not in V.CONTENT_MODES:
        raise BriefError("BAD_CONTENT_MODE",
                         "content_mode must be one of %s"
                         % (V.CONTENT_MODES,))
    if framing not in V.SHOT_TYPES:
        raise BriefError("BAD_FRAMING", "framing %r not in shot vocabulary"
                         % (framing,))
    if angle not in V.ANGLES:
        raise BriefError("BAD_ANGLE", "angle %r not in angle vocabulary"
                         % (angle,))
    # One camera move per clip. Whip pans and fast orbits are edit
    # transitions between two clips, never a single generated move.
    if camera_move in V.EDIT_TRANSITION_MOVES:
        raise BriefError(
            "EDIT_TRANSITION_NOT_A_MOVE",
            "%r fails in AI video models as a single generated move; build "
            "it as an edit transition between two clips" % (camera_move,))
    if camera_move not in V.CAMERA_MOVES:
        raise BriefError("BAD_CAMERA_MOVE",
                         "camera_move %r not in move vocabulary"
                         % (camera_move,))
    if lens_mm not in V.LENSES_MM:
        raise BriefError("BAD_LENS", "lens %r not in %s mm vocabulary"
                         % (lens_mm, V.LENSES_MM))
    intent = aperture_intent(f_number)
    if intent is None:
        raise BriefError("BAD_APERTURE",
                         "f_number %r not in the wide-open-to-stopped-down "
                         "vocabulary" % (f_number,))
    # Lens and aperture matched to emotion.
    match = V.EMOTION_LENS_APERTURE.get(emotion)
    if match is None:
        raise BriefError("BAD_EMOTION", "emotion %r not in %s"
                         % (emotion, V.EMOTIONS))
    if lens_mm not in match["lenses"]:
        raise BriefError(
            "LENS_EMOTION_MISMATCH",
            "%s mm is not the lens matched to %s (matched: %s mm)"
            % (lens_mm, emotion, ", ".join(str(x) for x in match["lenses"])))
    if intent != match["aperture_intent"]:
        raise BriefError(
            "APERTURE_EMOTION_MISMATCH",
            "aperture intent %s does not match emotion %s (matched: %s)"
            % (intent, emotion, match["aperture_intent"]))
    if duration_seconds is None:
        duration_seconds = default_shot_length(framing)
    if isinstance(duration_seconds, bool) or not isinstance(
            duration_seconds, (int, float)) or duration_seconds <= 0:
        raise BriefError("BAD_DURATION",
                         "duration_seconds must be a positive number")
    duration_seconds = float(duration_seconds)
    if coverage_role is None:
        coverage_role = V.COVERAGE_ROLE_BY_FRAMING.get(framing, "medium")
    if coverage_role not in V.COVERAGE_ROLES:
        raise BriefError("BAD_COVERAGE_ROLE",
                         "coverage_role %r not in %s"
                         % (coverage_role, V.COVERAGE_ROLES))
    if lighting is None:
        lighting = V.LIGHTING_CHOICES[0]
    if lighting not in V.LIGHTING_CHOICES:
        raise BriefError("BAD_LIGHTING", "lighting %r not in lighting choices"
                         % (lighting,))
    if eyeline is None:
        eyeline = V.EYE_LINES[0]
    if eyeline not in V.EYE_LINES:
        raise BriefError("BAD_EYELINE", "eyeline %r not in eyeline vocabulary"
                         % (eyeline,))
    if camera_side not in V.CAMERA_SIDES:
        raise BriefError("BAD_CAMERA_SIDE",
                         "camera_side must be one of %s" % (V.CAMERA_SIDES,))
    if screen_direction is None:
        screen_direction = V.SCREEN_DIRECTIONS[0]
    if screen_direction not in V.SCREEN_DIRECTIONS:
        raise BriefError("BAD_SCREEN_DIRECTION",
                         "screen_direction %r not in %s"
                         % (screen_direction, V.SCREEN_DIRECTIONS))
    if rack_focus_from is not None and not str(rack_focus_from).strip():
        raise BriefError("RACK_FOCUS_NO_ORIGIN",
                         "rack_focus_from must be a non-empty focus origin")

    # The generation prompt: no f-stop number and no lens word (lens and
    # f-stop words act as style cues — the lens and aperture live in the
    # brief's structured fields), no text or logos (added in post), one
    # move only.
    dof_phrase = ("shallow depth of field" if intent == "wide_open"
                  else ("deep depth of field" if intent == "stopped_down"
                        else "moderate depth of field"))
    prompt = "%s %s, %s camera move, %s, %s light, %s" % (
        framing.replace("_", " "), angle, camera_move, dof_phrase,
        lighting, emotion)
    if rack_focus_from is not None:
        prompt += ", rack focus from %s" % (rack_focus_from,)

    brief = {
        "schema_version": V.SCHEMA_VERSION,
        "shot_id": shot_id,
        "scene_id": scene_id,
        "content_mode": content_mode,
        "duration_seconds": duration_seconds,
        "duration_planning_range": list(
            V.FRAMING_SECONDS_PLANNING_RANGE[framing]),
        "duration_planning_range_label": V.PLANNING_RANGE_LABEL,
        "framing": framing,
        "angle": angle,
        "camera_move": camera_move,
        "lens_mm": lens_mm,
        "f_number": float(f_number),
        "aperture_intent": intent,
        "aperture_phrase": aperture_phrase(f_number),
        "depth_of_field": ("shallow" if intent == "wide_open" else
                           ("deep" if intent == "stopped_down" else "moderate")),
        "emotion": emotion,
        "coverage_role": coverage_role,
        "lighting": lighting,
        "eyeline": eyeline,
        "camera_side": camera_side,
        "screen_direction": screen_direction,
        "subject_id": (subject_id
                       if subject_id else
                       ((list(character_ids)[0]) if character_ids else
                        "screen")),
        "character_ids": list(character_ids or []),
        "dialogue_or_narration": bool(dialogue_or_narration),
        "transition_from": transition_from,
        "rack_focus_from": rack_focus_from,
        # Text and logos are added in post; they never enter the prompt.
        "text_overlay_post": text_overlay_post,
        "logo_overlay_post": logo_overlay_post,
        "vocabulary": V.full_vocabulary(),
        "prompt": prompt,
    }
    return brief
