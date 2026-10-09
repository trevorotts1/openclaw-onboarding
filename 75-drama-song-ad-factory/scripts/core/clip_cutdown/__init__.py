"""clip_cutdown package: the automatic 60- and 90-second clips (3, 5 and 10 minute ads)."""
from .clip_cutdown import (  # noqa: F401
    CLIP_LENGTHS_S, MIN_CLIP_AD_S, ClipCutdownError, build_argv, clips_for,
    plan_clips, run_clips,
)
