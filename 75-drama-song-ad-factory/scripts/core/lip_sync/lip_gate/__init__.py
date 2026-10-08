"""lip_gate package: Part H H2 measured lip-sync gate (sync_check.py is the measurement). Stdlib only, $0."""
from __future__ import annotations

from .lip_gate import (  # noqa: F401
    FAIL, FLAG, IMPROVED_INPUT, LIP_HELD_FOR_PERSON, LIP_UNMEASURED, MAX_TRIES,
    PASS, UNDETERMINED, UNMEASURABLE, UNMEASURED, envelope, judge, measure,
    measure_file, qc_check, run_gate, score,
)
from .image_gate import (  # noqa: F401
    LipsyncImageRefused, check_source_image, closeup_prompt, image_size,
    require_source_image,
)
