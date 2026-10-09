"""core.book_shot -- the book orientation contract for book campaigns (FU-U10).

No book shape or motion rule existed anywhere before this unit: every clip
prompt carried the generic "[MOTION] ... camera stay in gentle continuous
motion" line (wrong for a book, and the named cause of mirrored and invented
covers), and nothing measured the cover or the page-turn direction.

This package owns:
  * BOOK_ORIENTATION_CONTRACT + the fixed prompt blocks (prompt_blocks)
  * measured checks (check_clip): cover match vs the HORIZONTAL MIRROR of the
    client's cover file, title OCR in reading order, Farneback flow direction
  * the calibration control (calibrate_book) that must sort a known-good clip
    from its ffmpeg hflip before any verdict counts
  * qc_record(): the shots-stage record the QC gate requires for book campaigns
"""
from __future__ import annotations

from .book_shot import (
    ACTION_FLIP,
    ACTION_OPEN,
    BLOCK_ORDER,
    SCHEMA_VERSION,
    TOOL_NAME,
    TOOL_VERSION,
    BOOK_BLANK_PAGES,
    BOOK_CALIBRATION_FAILED,
    BOOK_COVER_NOT_FRONT,
    BOOK_EXCERPT_INVALID,
    BOOK_FRAMES_UNAVAILABLE,
    BOOK_INPUT_INVALID,
    BOOK_MIRRORED,
    BOOK_NO_MOTION,
    BOOK_OCR_UNAVAILABLE,
    BOOK_ORIENTATION_CONTRACT,
    BOOK_OVERLAY_UNAVAILABLE,
    BOOK_PAGES_UNAVAILABLE,
    BOOK_PLAN_NOT_APPROVED,
    BOOK_SPINE_WRONG_SIDE,
    BOOK_TITLE_WRONG,
    BOOK_WRONG_DIRECTION,
    CAMERA,
    CAMERA_PLAIN,
    CAMERA_SHOT_TAG,
    CONSTRAINTS,
    COVER_INLIER_MIN,
    EXCERPT_MAX_LINES,
    EXCERPT_OVERLAY_HOOK,
    EXCERPT_PROVENANCE,
    OCR_ENGINE,
    ORIENTATION,
    PAGE_MAX_BLANK_FRAMES,
    RTL_LANGUAGES,
    BookShotError,
    build_prompt,
    check_clip,
    check_pages,
    check_pages_sequence,
    detect_cover,
    dumps,
    excerpt_overlay,
    image_model_blocks,
    normalize_excerpt,
    ocr_text,
    optical_flow_direction,
    pages_block,
    plan_card_block,
    plan_card_rows,
    plan_card_text,
    plan_sha256,
    plan_spec,
    prompt_blocks,
    qc_record,
    reading_direction,
    title_reads_correctly,
)

__all__ = [
    "ACTION_FLIP", "ACTION_OPEN", "BLOCK_ORDER", "BOOK_BLANK_PAGES",
    "BOOK_CALIBRATION_FAILED", "BOOK_COVER_NOT_FRONT", "BOOK_EXCERPT_INVALID",
    "BOOK_FRAMES_UNAVAILABLE", "BOOK_INPUT_INVALID",
    "BOOK_MIRRORED", "BOOK_NO_MOTION", "BOOK_OCR_UNAVAILABLE",
    "BOOK_ORIENTATION_CONTRACT", "BOOK_OVERLAY_UNAVAILABLE",
    "BOOK_PAGES_UNAVAILABLE",
    "BOOK_PLAN_NOT_APPROVED", "BOOK_SPINE_WRONG_SIDE", "BOOK_TITLE_WRONG",
    "BOOK_WRONG_DIRECTION", "CAMERA", "CAMERA_PLAIN", "CAMERA_SHOT_TAG",
    "CONSTRAINTS", "COVER_INLIER_MIN", "EXCERPT_MAX_LINES",
    "EXCERPT_OVERLAY_HOOK", "EXCERPT_PROVENANCE",
    "OCR_ENGINE", "ORIENTATION", "PAGE_MAX_BLANK_FRAMES",
    "RTL_LANGUAGES", "SCHEMA_VERSION", "TOOL_NAME",
    "TOOL_VERSION", "BookShotError", "build_prompt", "check_clip",
    "check_pages", "check_pages_sequence",
    "detect_cover", "dumps", "excerpt_overlay", "image_model_blocks",
    "normalize_excerpt", "ocr_text",
    "optical_flow_direction", "pages_block", "plan_card_block", "plan_card_rows",
    "plan_card_text", "plan_sha256", "plan_spec",
    "prompt_blocks", "qc_record", "reading_direction",
    "title_reads_correctly",
]
