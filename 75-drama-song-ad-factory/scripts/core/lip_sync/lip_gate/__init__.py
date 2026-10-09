"""lip_gate package: Part H H2 measured lip-sync gate (sync_check.py is the measurement; event_sync.py is advisory). Stdlib only, $0."""
from __future__ import annotations

from .lip_gate import (  # noqa: F401
    FAIL, FLAG, IMPROVED_INPUT, KEPT, LIP_HELD_FOR_PERSON, LIP_TRY_LIMIT,
    LIP_UNMEASURED, MAX_TRIES, PASS, UNDETERMINED, UNMEASURABLE, UNMEASURED,
    LipTryLimit, advisory_file, envelope, judge, kling_prompt, measure,
    measure_file, qc_check, run_gate, score,
)
from .lip_process import (  # noqa: F401
    edit_plan, mouth_strip_argv, pick_kept, placement_s, receipt_row,
    retry_allowed, strip_path,
)
from .image_gate import (  # noqa: F401
    LipsyncImageRefused, check_source_image, closeup_prompt, image_size,
    require_source_image,
)
from .picture_gate import (  # noqa: F401
    LipsyncPictureNotGated, REGEN_PROMPT, check_numbers, gate_picture,
    make_regenerate, require_receipt, require_upload_bound, upload_measured,
)
