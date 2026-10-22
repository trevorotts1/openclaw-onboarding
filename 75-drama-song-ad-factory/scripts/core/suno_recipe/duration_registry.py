"""duration_registry.py: THE canonical duration and profile registry (W05-U3).

ONE table (``DURATION_REGISTRY``) carries the six canonical durations -- 60,
90, 120, 180, 300 and 600 seconds -- and every supported shape from it
(D12, spec 6.2). Every profile name (``drama-<shape>-<seconds>s``) is derived
from this table, never spelled out anywhere else, and the preflight profile
fixes in W07 consume ``preflight_profiles()`` instead of their own tuple (the
one that silently dropped the two-minute 120 s entry).

Duration is a TARGET unless the destination carries a real limit; the table is
registry data only -- the accept/edit/repair decisions live in
``suno_recipe.judge_duration_correction`` (spec 6.2), which reads the ONE
overshoot allowance from ``master_length``.

This module imports NOTHING, so every consumer (suno_recipe, music_styles,
prompt_templates, style_defaults, words_fit, intake_preflight, ...) can read it
in any import order without an import cycle. ``suno_recipe`` re-exports it.
"""
from __future__ import annotations

#: Registry version. W07's preflight profiles and W05-U2's constraint policy
#: are wired against this data; a shape or duration change bumps it here once.
REGISTRY_VERSION = "blackceo.duration-registry/v1"

#: The six canonical durations (seconds, ascending). The two-minute 120 s
#: profile sits between 90 s and 180 s (F15 owner order 2026-08-08; D12).
CANONICAL_DURATION_S = (60, 90, 120, 180, 300, 600)

#: Every supported delivery shape. The profile name embeds the shape verbatim.
SUPPORTED_SHAPES = ("9x16", "16x9")

#: The card's own label spellings (style_defaults F15). The two-minute label
#: is the one the scattered copies dropped.
DURATION_LABELS_S = {
    60: "60 seconds",
    90: "90 seconds",
    120: "2 minutes",
    180: "3 minutes",
    300: "5 minutes",
    600: "10-minute long version",
}

#: 60 s stays the RECOMMENDED default (card default decision 32).
RECOMMENDED_DURATION_S = 60

#: THE one table: one row per canonical duration, each row carrying every
#: supported shape and the profile name derived from (shape, seconds).
DURATION_REGISTRY = tuple(
    {
        "seconds": secs,
        "label": DURATION_LABELS_S[secs],
        "profiles": tuple(
            (shape, "drama-%s-%ss" % (shape, secs)) for shape in SUPPORTED_SHAPES
        ),
    }
    for secs in CANONICAL_DURATION_S
)


def _row(seconds):
    for row in DURATION_REGISTRY:
        if row["seconds"] == seconds:
            return row
    raise ValueError("BAD_DURATION: %r is not in the canonical registry %s"
                     % (seconds, list(CANONICAL_DURATION_S)))


def durations():
    """Every canonical duration in seconds (the registry's own order)."""
    return CANONICAL_DURATION_S


def shapes():
    """Every supported shape (the registry's own order)."""
    return SUPPORTED_SHAPES


def duration_row(seconds):
    """The one registry row for a duration: {seconds, label, profiles}."""
    return _row(seconds)


def profiles():
    """Every supported profile name, derived from the one table."""
    return tuple(name for row in DURATION_REGISTRY for _, name in row["profiles"])


def profiles_for(seconds):
    """The profile names one duration owns, one per supported shape."""
    return tuple(name for _, name in _row(seconds)["profiles"])


def profile_row(name):
    """{name, shape, seconds, label} for one profile name (fail closed)."""
    for row in DURATION_REGISTRY:
        for shape, pname in row["profiles"]:
            if pname == name:
                return {"name": pname, "shape": shape,
                        "seconds": row["seconds"], "label": row["label"]}
    raise ValueError("BAD_PROFILE: %r is not derived from the canonical "
                     "registry; known profiles: %s" % (name, list(profiles())))


def preflight_profiles():
    """The delivery-profile names preflight must allow (W07's feed).

    This replaces preflight's own ``PROFILE_LENGTHS_S``-derived tuple, which
    dropped the two-minute 120 s profile (D12: ``drama-9x16-120s`` was
    rejected as delivery-profile-unknown).
    """
    return profiles()
