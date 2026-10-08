"""lip_gate package: Part H H2 measured lip-sync gate. Stdlib only, $0."""
from __future__ import annotations

from .lip_gate import (  # noqa: F401
    IMPROVED_INPUT, KEPT, LIP_UNMEASURED, MAX_TRIES, NOT_SYNCED, SYNCED,
    UNMEASURABLE, WEAK, LipTryLimit, envelope, event_sync, events, judge,
    kling_prompt, mouth_series, qc_check, run_gate, score, selftest,
    voiced_runs,
)
from .image_gate import (  # noqa: F401
    LipsyncImageRefused, check_source_image, closeup_prompt, image_size,
    require_source_image,
)
