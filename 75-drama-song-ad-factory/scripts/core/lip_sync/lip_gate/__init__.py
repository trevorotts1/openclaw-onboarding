"""lip_gate package: Part H H2 measured lip-sync gate. Stdlib only, $0."""
from __future__ import annotations

from .lip_gate import (  # noqa: F401
    FAIL, FLAG, IMPROVED_INPUT, LIP_CORR_LOW, LIP_CONTROL_MARGIN,
    LIP_FACE_NOT_FOUND, LIP_NO_ONSETS, LIP_NO_RELATION, LIP_OFFSET,
    LIP_OFFSET_FAR, LIP_STILL_FACE, LIP_UNMEASURED, LIP_WRONG_AUDIO,
    MAX_TRIES, PASS, UNMEASURED, envelope, frozen_seconds, judge, measure,
    measure_file, mouth_series, onset_xcorr, qc_check, run_gate, score,
)
from .image_gate import (  # noqa: F401
    LipsyncImageRefused, check_source_image, closeup_prompt, image_size,
    require_source_image,
)
