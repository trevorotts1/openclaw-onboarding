"""lip_gate package: Part H H2 measured lip-sync gate (sync_check.py is the measurement; event_sync.py is advisory). Stdlib only, $0."""
from __future__ import annotations

from .lip_gate import (  # noqa: F401
    CLOSEUP_FACE_H_PCT, EMOTION_DRIFT, FAIL, FLAG, IMPROVED_INPUT, KEPT,
    LIP_HELD_FOR_PERSON, LIP_MODEL, LIP_TAKE_NOT_EYE_CHECKED, LIP_TRY_LIMIT,
    LIP_UNMEASURED, LIPSYNC_NO_CLOSEUP, MAX_TRIES, PASS, PAIN_EMOTIONS,
    PROVIDER, THIRD_JOB_RULE, UNDETERMINED, UNMEASURABLE, UNMEASURED,
    WRONG_VOICE_MOUTHED,
    LipTryLimit, advisory_file, closeup_landed, envelope, eye_recorded, judge,
    kling_prompt, measure, measure_file, qc_check, run_gate, score,
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
