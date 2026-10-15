"""agnes_transitions: chained Agnes segments, beat-aligned scene changes,
crossfades and one soundtrack (SPEC A5.2a)."""
from .agnes_transitions import (  # noqa: F401
    BOUNDARY_BEATS,
    INTRA_TRANSITION,
    MAX_CHAINS_IN_FLIGHT,
    SCENE_TRANSITION,
    XFADE_INTRA_S,
    XFADE_SCENE_S,
    chain_plan,
    check_joins,
    clip_duration,
    join_argv,
    last_frame,
    lipsync_offsets,
    submit_order,
)
