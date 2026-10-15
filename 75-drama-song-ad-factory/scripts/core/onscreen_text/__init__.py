"""onscreen_text package: SPEC A6 — no words inside generated pictures by default.

Default is no text at all; a needed word is baked only after OCR verified the
exact spelling; the decided fallback draws the words with FFmpeg at assembly
(``TEXT_OVERLAID``). Stdlib only, no spend, OCR optional forever.
"""
from __future__ import annotations

from .onscreen_text import (  # noqa: F401
    BAD_INPUT,
    ENGINE,
    MAX_TRIES,
    NO_TEXT_BLOCK,
    OCR_FAILED,
    OCR_UNAVAILABLE,
    OCRUnavailable,
    OnscreenTextError,
    REGISTERED,
    STILL_UNAVAILABLE,
    TEXT_BAKED,
    TEXT_NOT_VERIFIED,
    TEXT_OVERLAID,
    TOOL_NAME,
    TOOL_VERSION,
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_UNAVAILABLE,
    bake_block,
    decide,
    no_text_block,
    normalize,
    read_still,
    tesseract_bin,
    tesseract_extractor,
    verify_still,
)

__all__ = [
    "BAD_INPUT",
    "ENGINE",
    "MAX_TRIES",
    "NO_TEXT_BLOCK",
    "OCR_FAILED",
    "OCR_UNAVAILABLE",
    "OCRUnavailable",
    "OnscreenTextError",
    "REGISTERED",
    "STILL_UNAVAILABLE",
    "TEXT_BAKED",
    "TEXT_NOT_VERIFIED",
    "TEXT_OVERLAID",
    "TOOL_NAME",
    "TOOL_VERSION",
    "VERDICT_FAIL",
    "VERDICT_PASS",
    "VERDICT_UNAVAILABLE",
    "bake_block",
    "decide",
    "no_text_block",
    "normalize",
    "read_still",
    "tesseract_bin",
    "tesseract_extractor",
    "verify_still",
]
