"""camera_signatures: droppable signature-move presets and the DEL-16 rules.

Two concerns, one package, standard library only:

  presets.py  the preset library the shot planner drops at the start of a
              scene or of the whole video -- the drone family and the dolly
              family, each carrying name, plain prompt phrase, emotion,
              use-when, AI-risk and a per-model test flag.
  rules.py    the rules the planner enforces: one generated move per clip,
              whip pan refused as a single generated move, the two-minute
              drone and dolly minimums with a client-decline escape, and the
              drone placement rule.

Nothing here reads a vendor catalog, a network path or an operator
directory at run time; every value ships in this folder.
"""

from .presets import (  # noqa: F401
    DOLLY_PRESET_IDS,
    DRONE_PRESET_IDS,
    PRESET_IDS,
    PRESETS,
    UnknownPreset,
    drop_preset,
    get_preset,
)
from .rules import (  # noqa: F401
    CLIENT_GUIDE_DRONE_LINE,
    DRONE_ALLOWED_PLACEMENTS,
    EDIT_TRANSITION_MOVES,
    MAX_MOVES_PER_CLIP,
    MIN_CLIENT_PDF_POINT_SIZE,
    MODEL_TEST_FLAG,
    PLACEMENTS,
    RefusedMove,
    check_drone_placement,
    check_generated_move,
    check_one_move_per_clip,
    check_signature_minimums,
    family,
    require_generated_move,
)

__all__ = [
    "CLIENT_GUIDE_DRONE_LINE",
    "DRONE_ALLOWED_PLACEMENTS",
    "DRONE_PRESET_IDS",
    "DOLLY_PRESET_IDS",
    "EDIT_TRANSITION_MOVES",
    "MAX_MOVES_PER_CLIP",
    "MIN_CLIENT_PDF_POINT_SIZE",
    "MODEL_TEST_FLAG",
    "PLACEMENTS",
    "PRESET_IDS",
    "PRESETS",
    "RefusedMove",
    "UnknownPreset",
    "check_drone_placement",
    "check_generated_move",
    "check_one_move_per_clip",
    "check_signature_minimums",
    "drop_preset",
    "family",
    "get_preset",
    "require_generated_move",
]
