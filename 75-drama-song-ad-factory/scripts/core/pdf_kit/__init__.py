"""pdf_kit package: the shared standard-library PDF writer for client delivery
documents (the DEL package). Bright pages, a 12 pt floor, no third-party
dependency. See ``pdf_kit.pdf_kit``."""
from __future__ import annotations

from .pdf_kit import (
    ACCENT,
    BODY_PT,
    INK,
    LEADING,
    MARGIN,
    MIN_PT,
    MUTED,
    PAGE_H,
    PAGE_W,
    PAPER,
    RULE,
    Canvas,
    PdfError,
    extract_text,
    text_width,
    wrap,
)

__all__ = [
    "ACCENT", "BODY_PT", "INK", "LEADING", "MARGIN", "MIN_PT", "MUTED",
    "PAGE_H", "PAGE_W", "PAPER", "RULE", "Canvas", "PdfError", "extract_text",
    "text_width", "wrap",
]
