"""core.prop_facing -- the Prop Facing contract for used props (Section 3P).

Six of nine used props faced the camera instead of their user. The prompts
asked for it and nothing measured the facing. This package owns:
  * PROP_FACING_CONTRACT (rules P1 to P6) + the fixed facing sentences
    (facing_sentence, insert_sentence, h3_facing_block)
  * the text-record seam (normalize_record): user, faces, viewer_must_read
  * measured checks (check_picture, check_clip): PROP_FACES_CAMERA,
    PROP_TURNED_TO_CAMERA, INSERT_WRONG_SIDE, PICTURE_TEXT_WRONG
  * the calibration control (calibrate_prop) that must sort a known-good
    picture from the camera-facing picture of the same beat before any
    verdict counts
  * qc_record(): the shots-stage record the QC gate requires for shots
    with a used prop
"""
from __future__ import annotations

from .prop_facing import (
    FACING_CORE,
    FACES_VALUES,
    INSERT_CORE,
    INSERT_WRONG_SIDE,
    PICTURE_TEXT_WRONG,
    PROP_CHECK_UNAVAILABLE,
    PROP_FACES_CAMERA,
    PROP_FRAMES_UNAVAILABLE,
    PROP_FACING_CONTRACT,
    PROP_INPUT_INVALID,
    PROP_KINDS,
    PROP_TURNED_TO_CAMERA,
    SCHEMA_VERSION,
    SHOWN_CORE,
    TOOL_NAME,
    TOOL_VERSION,
    PropFacingError,
    check_clip,
    check_picture,
    dumps,
    facing_sentence,
    h3_facing_block,
    insert_sentence,
    needs_insert,
    normalize_record,
    qc_record,
)

__all__ = [
    "FACING_CORE", "FACES_VALUES", "INSERT_CORE", "INSERT_WRONG_SIDE",
    "PICTURE_TEXT_WRONG", "PROP_CHECK_UNAVAILABLE", "PROP_FACES_CAMERA",
    "PROP_FRAMES_UNAVAILABLE", "PROP_FACING_CONTRACT",
    "PROP_INPUT_INVALID", "PROP_KINDS", "PROP_TURNED_TO_CAMERA",
    "SCHEMA_VERSION", "SHOWN_CORE", "TOOL_NAME", "TOOL_VERSION",
    "PropFacingError", "check_clip", "check_picture", "dumps",
    "facing_sentence", "h3_facing_block", "insert_sentence",
    "needs_insert", "normalize_record", "qc_record",
]
