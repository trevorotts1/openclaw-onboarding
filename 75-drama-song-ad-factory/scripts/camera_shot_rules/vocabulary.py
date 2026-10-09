"""DEL-16 camera vocabulary — the data layer every shot brief carries (PKG-07-U2).

Stdlib only. Nothing here reads a network, an operator path or a Downloads
folder: the shipped reference is the skill's own
``references/camera-vocabulary.json`` (PKG-07-U1) and it is optional — the
DEL-16 set below is self-contained, the reference only enriches the brief.

Every percentage-sized number in this module carries
:data:`PLANNING_RANGE_LABEL`: the numbers are planning ranges, not measured
standards.
"""
from __future__ import annotations

import json
import os

SCHEMA_VERSION = "blackceo.shot-planner/v1"
TOOL_VERSION = "1.0.0"

PLANNING_RANGE_LABEL = "planning range, not a measured standard"

# ---------------------------------------------------------------- vocabulary
# Shot-size ladder, widest to tightest. Shot length shrinks down this ladder.
SHOT_SIZE_LADDER = (
    "extreme_wide", "wide", "medium", "medium_close", "close", "extreme_close",
)
# Full framing vocabulary: "establishing wide through insert and detail".
SHOT_TYPES = ("establishing_wide",) + SHOT_SIZE_LADDER + ("insert", "detail")

# Angle vocabulary: eye, low, high, bird's-eye and dutch.
ANGLES = ("eye", "low", "high", "bird's-eye", "dutch")

# Camera-move vocabulary: static through crane moves. One move per clip.
CAMERA_MOVES = (
    "static", "pan", "tilt", "dolly-in", "dolly-out", "tracking", "pedestal",
    "zoom", "handheld", "crane", "orbit", "push-in", "pull-back", "rack-focus",
)
# Whip pans and fast orbits are EDIT transitions between two clips. AI video
# models fail them as a single generated move, so they are never a shot move.
EDIT_TRANSITION_MOVES = ("whip-pan", "fast-orbit")

# Lens vocabulary: twenty-four, thirty-five, fifty and eighty-five millimeter.
LENSES_MM = (24, 35, 50, 85)

# Aperture range from wide open to stopped down. The numbers live in the
# brief's structured fields; prompts carry the shallow-depth-of-field PHRASE
# instead of an f-stop number (lens and f-stop words act as style cues).
APERTURES = (
    (1.4, "wide open"), (2.0, "wide open"), (2.8, "wide open"),
    (4.0, "mid"), (5.6, "mid"),
    (8.0, "stopped down"), (11.0, "stopped down"), (16.0, "stopped down"),
)
APERTURE_INTENT = {
    1.4: "wide_open", 2.0: "wide_open", 2.8: "wide_open",
    4.0: "mid", 5.6: "mid",
    8.0: "stopped_down", 11.0: "stopped_down", 16.0: "stopped_down",
}
APERTURE_WIDE_OPEN = (1.4, 2.0, 2.8)
APERTURE_STOPPED_DOWN = (8.0, 11.0, 16.0)

# Coverage vocabulary: master, medium, close-up, reverse, insert and cutaway.
COVERAGE_ROLES = ("master", "medium", "close_up", "reverse", "insert", "cutaway")
REQUIRED_COVERAGE_ROLES = COVERAGE_ROLES

DEPTH_OF_FIELD = ("shallow", "moderate", "deep", "rack")
LIGHTING_CHOICES = ("golden-hour", "low-key", "daylight", "night",
                    "studio-soft", "overcast")
EYE_LINES = ("screen-left", "screen-right", "center")
CAMERA_SIDES = ("a", "b")
SCREEN_DIRECTIONS = ("left", "right")
# For music and for dialogue or narration alike.
CONTENT_MODES = ("music", "dialogue", "narration")

EMOTIONS = ("intimate", "joyful", "tense", "calm", "epic", "nostalgic")
# Lens and aperture matched to emotion.
EMOTION_LENS_APERTURE = {
    "intimate":  {"lenses": (50, 85), "aperture_intent": "wide_open"},
    "joyful":    {"lenses": (35, 50), "aperture_intent": "mid"},
    "tense":     {"lenses": (24, 35), "aperture_intent": "mid"},
    "calm":      {"lenses": (35, 50), "aperture_intent": "mid"},
    "epic":      {"lenses": (24,),    "aperture_intent": "stopped_down"},
    "nostalgic": {"lenses": (50, 85), "aperture_intent": "wide_open"},
}

# ------------------------------------------------- pacing planning ranges
# "clips of about four to six seconds" — planning range, not a measured
# standard; the per-framing ladder below is authoritative when the framing
# is not medium.
DEFAULT_CLIP_SECONDS_PLANNING_RANGE = (4.0, 6.0)
# "shot length shrinks as shots get closer, about eight seconds for extreme
# wides down to about two and a half seconds for extreme close-ups" — every
# band is a planning range, not a measured standard. Both endpoints decrease
# strictly down SHOT_SIZE_LADDER (checked by the self-check).
FRAMING_SECONDS_PLANNING_RANGE = {
    "establishing_wide": (6.5, 9.0),
    "extreme_wide": (6.5, 9.0),
    "wide": (5.0, 8.0),
    "medium": (4.0, 6.0),
    "medium_close": (3.5, 5.5),
    "close": (3.0, 5.0),
    "extreme_close": (2.0, 3.5),
    "insert": (2.0, 4.0),
    "detail": (2.0, 4.0),
}
# "medium shots dominate narrative film" — planning range, not a measured
# standard; the floor is what the check enforces.
MEDIUM_SHARE_PLANNING_RANGE = (0.5, 0.7)
# "close-ups at most thirty-five percent of coverage" — enforced cap; docs
# label it a planning range, not a measured standard.
CLOSE_UP_SHARE_CAP = 0.35
# "at most two identical framings in a row"
MAX_IDENTICAL_FRAMINGS_IN_A_ROW = 2
# "videos of two minutes or more carry at least five shot types and three
# angles"
LONG_VIDEO_SECONDS = 120.0
LONG_VIDEO_MIN_SHOT_TYPES = 5
LONG_VIDEO_MIN_ANGLES = 3

CLOSE_UP_FRAMINGS = ("close", "extreme_close")
MEDIUM_FRAMINGS = ("medium", "medium_close")
# framing -> coverage role when the shot does not declare one. reverse and
# cutaway are relational, so they are always declared.
COVERAGE_ROLE_BY_FRAMING = {
    "establishing_wide": "master",
    "extreme_wide": "master",
    "wide": "master",
    "medium": "medium",
    "medium_close": "medium",
    "close": "close_up",
    "extreme_close": "close_up",
    "insert": "insert",
    "detail": "insert",
}
DEFAULT_CLIP_FRAMINGS = ("medium", "medium_close", "close", "insert", "detail")

# --------------------------------------------------------- shipped reference
_SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
SHIPPED_REFERENCE_REL = os.path.join("references", "camera-vocabulary.json")


def shipped_reference_path():
    """Skill-relative path of the PKG-07-U1 camera vocabulary, or None."""
    p = os.path.join(_SKILL_ROOT, SHIPPED_REFERENCE_REL)
    return p if os.path.isfile(p) else None


def shipped_reference_entries():
    """Names from the shipped reference, by category. Optional enrichment.

    Absent or malformed reference -> {}: the DEL-16 vocabulary below is the
    source the rule checks judge against, so an optional enrichment never
    changes a verdict.
    """
    p = shipped_reference_path()
    if not p:
        return {}
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for cat in ("shot_types", "angles", "moves", "lenses", "apertures"):
        rows = data.get(cat)
        if isinstance(rows, list):
            names = [r.get("name") for r in rows
                     if isinstance(r, dict) and isinstance(r.get("name"), str)]
            if names:
                out[cat] = names
    return out


def missing_from(vocab):
    """Tokens a shot brief's vocabulary block must carry and does not.

    The DEL-16 list: establishing wide through insert and detail; eye, low,
    high, bird's-eye and dutch angles; static through crane moves; twenty-
    four, thirty-five, fifty and eighty-five millimeter lenses; aperture
    range from wide open to stopped down.
    """
    if not isinstance(vocab, dict):
        return ["vocabulary-not-a-record"]
    missing = []

    def want_list(key, required):
        got = vocab.get(key)
        got_set = set(got) if isinstance(got, list) else set()
        for item in required:
            if item not in got_set:
                missing.append("%s:%s" % (key, item))

    want_list("shot_types", SHOT_TYPES)
    want_list("angles", ANGLES)
    want_list("camera_moves", CAMERA_MOVES)
    want_list("edit_transition_moves", EDIT_TRANSITION_MOVES)
    want_list("lenses_mm", LENSES_MM)
    want_list("coverage_roles", COVERAGE_ROLES)
    want_list("depth_of_field", DEPTH_OF_FIELD)
    want_list("lighting_choices", LIGHTING_CHOICES)
    apertures = vocab.get("apertures")
    got_f = set()
    got_labels = set()
    if isinstance(apertures, list):
        for row in apertures:
            if isinstance(row, dict):
                if isinstance(row.get("f"), (int, float)) \
                        and not isinstance(row.get("f"), bool):
                    got_f.add(float(row["f"]))
                if isinstance(row.get("label"), str):
                    got_labels.add(row["label"])
    for f, _label in APERTURES:
        if f not in got_f:
            missing.append("apertures:%s" % f)
    if "wide open" not in got_labels:
        missing.append("apertures:wide open")
    if "stopped down" not in got_labels:
        missing.append("apertures:stopped down")
    ranges = vocab.get("planning_ranges")
    if not isinstance(ranges, dict) \
            or "planning range" not in str(ranges.get("label", "")).lower():
        missing.append("planning_ranges:label")
    return missing


def full_vocabulary():
    """The complete DEL-16 vocabulary a shot brief carries.

    Every category the order names is present: establishing wide through
    insert and detail; eye, low, high, bird's-eye and dutch angles; static
    through crane moves; twenty-four, thirty-five, fifty and eighty-five
    millimeter lenses; aperture range from wide open to stopped down.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "shot_types": list(SHOT_TYPES),
        "shot_size_ladder": list(SHOT_SIZE_LADDER),
        "angles": list(ANGLES),
        "camera_moves": list(CAMERA_MOVES),
        "edit_transition_moves": list(EDIT_TRANSITION_MOVES),
        "lenses_mm": list(LENSES_MM),
        "apertures": [{"f": f, "label": label,
                       "intent": APERTURE_INTENT[f]} for f, label in APERTURES],
        "coverage_roles": list(COVERAGE_ROLES),
        "depth_of_field": list(DEPTH_OF_FIELD),
        "lighting_choices": list(LIGHTING_CHOICES),
        "eyelines": list(EYE_LINES),
        "camera_sides": list(CAMERA_SIDES),
        "screen_directions": list(SCREEN_DIRECTIONS),
        "emotions": list(EMOTIONS),
        "content_modes": list(CONTENT_MODES),
        "emotion_lens_aperture": {
            k: {"lenses": list(v["lenses"]),
                "aperture_intent": v["aperture_intent"]}
            for k, v in EMOTION_LENS_APERTURE.items()},
        "planning_ranges": {
            "label": PLANNING_RANGE_LABEL,
            "default_clip_seconds": list(DEFAULT_CLIP_SECONDS_PLANNING_RANGE),
            "framing_seconds": {k: list(v) for k, v in
                                FRAMING_SECONDS_PLANNING_RANGE.items()},
            "medium_share": {"floor": MEDIUM_SHARE_PLANNING_RANGE[0],
                             "ceiling": MEDIUM_SHARE_PLANNING_RANGE[1],
                             "label": PLANNING_RANGE_LABEL},
            "close_up_share_cap": CLOSE_UP_SHARE_CAP,
            "long_video_seconds": LONG_VIDEO_SECONDS,
            "long_video_min_shot_types": LONG_VIDEO_MIN_SHOT_TYPES,
            "long_video_min_angles": LONG_VIDEO_MIN_ANGLES,
        },
        "shipped_reference": (SHIPPED_REFERENCE_REL
                              if shipped_reference_path() else None),
        "shipped_reference_entries": shipped_reference_entries(),
    }
