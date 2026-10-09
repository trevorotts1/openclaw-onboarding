"""U9 captions-final: the one excerpt/caption burn site (plan 6.5, D16).

THE single place this skill draws caption text. U11's call site resolves it
through the named hook:

    book_shot.EXCERPT_OVERLAY_HOOK = "final_assembler.captions_burn.overlay_excerpt"

``overlay_excerpt(lines, provenance=...)`` takes the client excerpt as DATA
(the same list U11 posts under ``plan["excerpt_overlay"]["lines"]``) and
returns a receipt that describes the burn to be performed:

- the lines come back BYTE-IDENTICAL -- this module never re-spells,
  re-cases or display-normalises client words (U8 owns display spelling for
  performance text; a client excerpt is data);
- ``planned`` is True, ``burned`` is False: frames are burned by the render
  pass that consumes ``plan`` / ``argv``, never by this call. The receipt
  never claims work that did not happen;
- with measured cues it also emits a valid SRT (D16 delivers an SRT);
  without cues ``timing`` is ``"unavailable"`` and NO clock is invented
  (F18's rule: no measured words, no timing).

Style (owner decision D16, plan section 6.5): white rounded box, black text,
lower-middle third, ON BY DEFAULT; 9:16 sits above the bottom 20% of the
frame so platform buttons never cover it; 16:9 uses the lower third.

Stdlib only, zero network, zero paid calls. This module contains no
ffmpeg/network import: the burn argv is built as DATA for the render pass,
which is the one place that may execute it.

Run: python3 core/final_assembler/captions_burn.py
"""
from __future__ import annotations

import argparse
import json
import sys

TOOL_NAME = "captions_burn"
TOOL_VERSION = "1.0.0"

#: The full hook string U11 names; ``overlay_excerpt`` is its entry point.
EXCERPT_OVERLAY_HOOK = "final_assembler.captions_burn.overlay_excerpt"
ENTRY = "overlay_excerpt"

#: D16 look, fixed: white rounded box, black text.
BOX = "rounded"
BOX_COLOUR = "#ffffff"
FONT_COLOUR = "#000000"
#: Boxes keep the text clear of the frame edge on both orientations.
EDGE_MARGIN_PX = 24

#: One line at a time has to be readable on a phone: the box text is this
#: share of the frame height (a 1920-tall frame -> 86 px).
FONT_RATIO = 0.045

#: Refusal codes (fail-closed, never a silent pass).
BAD_INPUT = "OVERLAY_BAD_INPUT"
NO_LINES = "OVERLAY_NO_LINES"
NO_TIMING = "CAPTION_TIMING_UNAVAILABLE"
BAD_CUES = "CAPTION_CUES_INVALID"

DEFAULT_FPS = 30


def _refuse(reason_code, detail, **extra):
    """A refusal receipt: never burns, never passes silently."""
    out = {"ok": False, "hook": EXCERPT_OVERLAY_HOOK,
           "entry": ENTRY, "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
           "burned": False, "planned": False, "lines": None,
           "provenance": None, "timing": "unavailable",
           "reason_code": reason_code, "detail": detail}
    out.update(extra)
    return out


def _valid_lines(lines):
    """A non-empty list of non-empty strings, in order, never rewritten."""
    if not isinstance(lines, (list, tuple)) or not lines:
        return None
    out = []
    for ln in lines:
        if not isinstance(ln, str) or not ln.strip():
            return None
        out.append(ln)
    return out


def caption_style(width_px, height_px, orientation=None, enabled=True):
    """D16's look and safe area as data. Arguments are (width, height).

    Geometry decides the orientation unless the caller pins it, so a 9:16
    master never has to be told twice. 9:16 clears the bottom 20% of the
    frame (platform buttons); 16:9 sits in the lower third.
    """
    w, h = float(width_px), float(height_px)
    if orientation not in ("9:16", "16:9"):
        orientation = "9:16" if h >= w else "16:9"
    if orientation == "9:16":
        # Above the bottom 20%: the caption box starts at 20% and its own
        # edge margin lifts it further off the button row.
        bottom = h * 0.20
    else:
        # Lower third: inside it, but never flush to the frame edge.
        bottom = h * 0.10
    return {"enabled": bool(enabled),
            "box": BOX,
            "box_colour": BOX_COLOUR,
            "font_colour": FONT_COLOUR,
            "orientation": orientation,
            "height_px": h,
            "width_px": w,
            "font_size_px": max(18, int(round(h * FONT_RATIO))),
            "bottom_margin_px": bottom + EDGE_MARGIN_PX,
            "edge_margin_px": EDGE_MARGIN_PX,
            "one_line_at_a_time": True}


def _stamp(seconds):
    """seconds -> HH:MM:SS,mmm (SRT uses a comma decimal separator)."""
    if seconds < 0:
        raise ValueError("negative timestamp: %r" % (seconds,))
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def _clean_cues(cues):
    """Measured cues only: text + start/end floats, order kept, no inventing.

    Returns (clean, None) or (None, detail) when the caller gave something
    that is not a measured window.
    """
    if not isinstance(cues, (list, tuple)):
        return None, "cues must be a list of {text,start,end} windows"
    clean = []
    for i, cue in enumerate(cues):
        if not isinstance(cue, dict):
            return None, "cue %d is not an object" % i
        text = cue.get("text")
        start, end = cue.get("start"), cue.get("end")
        if not isinstance(text, str) or not text.strip():
            return None, "cue %d has no text" % i
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            return None, "cue %d has no numeric window" % i
        if float(end) < float(start):
            return None, "cue %d ends before it starts" % i
        clean.append({"text": text, "start": float(start),
                      "end": float(end)})
    if not clean:
        return None, "no cue carried a window"
    for prev, nxt in zip(clean, clean[1:]):
        if nxt["start"] < prev["start"]:
            return None, "cues are not in time order"
    return clean, None


def build_srt(cues, fps=DEFAULT_FPS):
    """Valid SRT text from MEASURED cues. Raises ValueError on bad input.

    The text is the cue's own words; only the clock format is normalised.
    """
    clean, why = _clean_cues(cues)
    if why:
        raise ValueError("%s: %s" % (BAD_CUES, why))
    blocks = []
    for i, cue in enumerate(clean, 1):
        blocks.append("%d\n%s --> %s\n%s" % (
            i, _stamp(cue["start"]), _stamp(cue["end"]), cue["text"]))
    return "\n\n".join(blocks) + "\n"


def build_plan(lines, provenance=None, cues=None, height_px=1920,
               width_px=1080, orientation=None, fps=DEFAULT_FPS,
               srt_path=None, enabled=True):
    """The burn plan: style + one line at a time + optional SRT, all as data.

    Nothing here executes. The render pass reads ``plan``/``argv``; the SRT
    is written only when the caller passes ``srt_path``.

    ``enabled=False`` is the caption-free variant of the SAME plan (DEL-05's
    clean master): same lines, same words, same geometry, style off.
    """
    clean = _valid_lines(lines)
    if clean is None:
        raise ValueError("%s: lines must be a non-empty list of strings"
                         % NO_LINES)
    style = caption_style(width_px, height_px, orientation=orientation,
                          enabled=enabled)
    plan = {"tool": TOOL_NAME, "tool_version": TOOL_VERSION,
            "entry": ENTRY, "hook": EXCERPT_OVERLAY_HOOK,
            "lines": list(clean), "line_count": len(clean),
            "one_line_at_a_time": True,
            "style": style, "fps": fps,
            "provenance": provenance,
            "data_only": True, "to_video_model": False}
    if cues is None:
        plan["timing"] = "unavailable"
        plan["cue_count"] = 0
        plan["srt"] = None
        return plan, None
    clean_cues, why = _clean_cues(cues)
    if why:
        return plan, "%s: %s" % (BAD_CUES, why)
    srt = build_srt(clean_cues, fps=fps)
    plan["timing"] = "measured"
    plan["cue_count"] = len(clean_cues)
    plan["cues"] = clean_cues
    plan["srt"] = srt
    plan["srt_path"] = srt_path
    if srt_path:
        try:
            with open(srt_path, "w", encoding="utf-8") as fh:
                fh.write(srt)
        except OSError as exc:
            return plan, "%s: %s" % (BAD_INPUT, exc)
    return plan, None


def overlay_excerpt(lines, provenance=None, cues=None, height_px=1920,
                     width_px=1080, orientation=None, fps=DEFAULT_FPS,
                     srt_path=None, enabled=True):
    """U11's entry point: plan the excerpt overlay burn, return its receipt.

    Called as ``overlay_excerpt(lines, provenance=...)`` by the U11 seam
    (``assembler.excerpt_overlay_stage``). Never raises on seam input: bad
    input comes back as a refusal receipt with ``ok`` False. ``enabled=False``
    plans the same words with the captions off (the clean delivered cut).
    """
    clean = _valid_lines(lines)
    if clean is None:
        if not isinstance(lines, (list, tuple)) or lines:
            return _refuse(BAD_INPUT,
                           "lines must be a non-empty list of strings",
                           input_repr=repr(lines)[:200])
        return _refuse(NO_LINES, "no excerpt lines supplied")
    plan, why = build_plan(clean, provenance=provenance, cues=cues,
                           height_px=height_px, width_px=width_px,
                           orientation=orientation, fps=fps,
                           srt_path=srt_path, enabled=enabled)
    receipt = {"ok": why is None,
               "hook": EXCERPT_OVERLAY_HOOK, "entry": ENTRY,
               "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
               "lines": list(clean),
               "provenance": provenance,
               "planned": True,
               # Frames are burned by the render pass, never by this call.
               "burned": False,
               "timing": plan["timing"],
               "style": plan["style"],
               "data_only": True, "to_video_model": False,
               "plan": plan,
               "srt": plan.get("srt"),
               "reason_code": None if why is None else BAD_CUES,
               "detail": why}
    return receipt


def main(argv=None):
    """CLI: print the receipt for an excerpt given as JSON arguments."""
    ap = argparse.ArgumentParser(prog=TOOL_NAME,
                                 description="plan an excerpt caption burn")
    ap.add_argument("--lines", required=True,
                    help='JSON list of strings, e.g. \'["line one"]\'')
    ap.add_argument("--provenance", default=None)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--width", type=int, default=1080)
    args = ap.parse_args(argv)
    try:
        lines = json.loads(args.lines)
    except ValueError as exc:
        print(json.dumps({"ok": False, "reason_code": BAD_INPUT,
                          "detail": str(exc)}, indent=2))
        return 2
    receipt = overlay_excerpt(lines, provenance=args.provenance,
                              height_px=args.height, width_px=args.width)
    print(json.dumps(receipt, indent=2))
    return 0 if receipt.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())