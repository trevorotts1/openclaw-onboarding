"""lip_gate package: Part H H2 measured lip-sync gate. Stdlib only, $0."""
from __future__ import annotations

from .lip_gate import (  # noqa: F401
    IMPROVED_INPUT, LIP_CONTROL_MARGIN, LIP_CORR_LOW, LIP_FROZEN_FACE,
    LIP_OFFSET, LIP_UNMEASURED, MAX_FROZEN_S, MAX_OFFSET_S,
    MIN_CONTROL_MARGIN, MIN_CORR, envelope, frozen_seconds, judge, measure,
    mouth_series, qc_check, run_gate, score,
)
