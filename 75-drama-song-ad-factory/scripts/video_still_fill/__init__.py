"""DEL-14 still-fill path: full height by crop-in, never by a fill.

One module, three jobs:

  render    cover_crop_filter() / still_clip_filter() / still_clip_argv()
            build the ONLY legal way to reach full height -- scale up to
            cover the canvas, then crop the overhang off, top anchored.
            The final assembler uses cover_crop_filter() for every
            segment, so a master is never stretched, never letterboxed
            and never filled from a blurred copy of its own edge.

  measure   top_band() / detail_ratio() / frame_metrics() read the plain
            top off a real frame: the crop-in path carries the source's
            own detail up there, a fill does not.

  judge     is_full_height() (does the file really probe to the full
            canvas) and is_plain_top() (is that top the source's own) --
            both fail closed: an unreadable or unprobeable file raises
            instead of passing.
"""
from .video_still_fill import (
    FLAT_BAND_MAX_FLOOR,
    MID_BAND_HALF,
    PLAIN_TOP_RATIO_FLOOR,
    PORTRAIT_H,
    PORTRAIT_W,
    TOOL_NAME,
    TOP_BAND_ROWS,
    StillFillError,
    cover_crop_filter,
    detail_ratio,
    frame_gray,
    frame_metrics,
    geometry,
    is_full_height,
    is_plain_top,
    probe_size,
    still_clip_argv,
    still_clip_filter,
    top_band,
)

__all__ = [
    "FLAT_BAND_MAX_FLOOR",
    "MID_BAND_HALF",
    "PLAIN_TOP_RATIO_FLOOR",
    "PORTRAIT_H",
    "PORTRAIT_W",
    "StillFillError",
    "TOP_BAND_ROWS",
    "TOOL_NAME",
    "cover_crop_filter",
    "detail_ratio",
    "frame_gray",
    "frame_metrics",
    "geometry",
    "is_full_height",
    "is_plain_top",
    "probe_size",
    "still_clip_argv",
    "still_clip_filter",
    "top_band",
]
