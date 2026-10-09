"""delivery_docs package: the standard-library page layout behind the
client-facing delivery PDFs (DEL-03 and its siblings)."""
from .pdf_writer import (  # noqa: F401
    ACCENT, BAR, GREY, HAIR, INK, MIN_PT, PAGE_H, PAGE_W, Layout, fit,
    text_width, wrap,
)

__all__ = ["ACCENT", "BAR", "GREY", "HAIR", "INK", "MIN_PT", "PAGE_H",
           "PAGE_W", "Layout", "fit", "text_width", "wrap"]