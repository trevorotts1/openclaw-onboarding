"""endcard_overlay: the ONE sanctioned end-card/logo/caption render stage (F-EOC).

The final-assembly delivery path had exactly one thing to draw text and it
never ran: `excerpt_overlay_stage` was called with `dry_run=True` only, and
`build_argv` carried trim/setpts/crop/concat/xfade only. This module plans
that stage as DATA (ffmpeg filter chains + text files) so `build_argv` can
append it and the render pass is the one thing that executes it.

Inputs, each read from the run's OWN records -- nothing invented:
  * the end-card title:  creative/script.json -> brief.json -> music/req.json
  * the end-card website (optional): brief.json "website"
  * the logo (optional):  brief.json "logo" (run-relative) or brand/logo.png
  * the caption cues:     the plan's own "lines" (measured word windows and
                          the approved sheet's words), styled and SRT'd by
                          final_assembler.captions_burn -- the ONE burn module

Refusals (fail closed, never a silent pass):
  ENDCARD_INPUT_MISSING   a card is scheduled but no record names its title
  LOGO_UNUSABLE           a recorded logo is absent, not a PNG, opaque
                          (no alpha), or below the minimum edge
  CAPTION_BURN_MISSING    captions are on but nothing can burn them (no
                          cues, no captions_burn module, no font)
  CAPTION_ZERO_DURATION   a cue's end equals its start (captions_burn)
  DRAWTEXT_UNAVAILABLE    the box's ffmpeg has no drawtext filter

Stdlib only, zero network, zero paid calls, no ffmpeg import.
"""
from __future__ import annotations

import json
import os
import struct

TOOL_NAME = "endcard_overlay"
TOOL_VERSION = "1.0.0"

ENDCARD_INPUT_MISSING = "ENDCARD_INPUT_MISSING"
LOGO_UNUSABLE = "LOGO_UNUSABLE"
CAPTION_BURN_MISSING = "CAPTION_BURN_MISSING"
CAPTION_ZERO_DURATION = "CAPTION_ZERO_DURATION"
#: The card and the captions are drawn text: a build without drawtext can
#: never carry them, so the stage refuses before the render instead of
#: dying in ffmpeg after the spend (same rule cover_image applies).
DRAWTEXT_UNAVAILABLE = "DRAWTEXT_UNAVAILABLE"

#: The card holds 4-5 s (ending_qc.CARD_MIN_S/MAX_S); plan the middle.
ENDCARD_HOLD_S = 4.5
#: The card starts this long after the final sung/spoken word ends.
ENDCARD_GAP_S = 0.25
#: A logo smaller than this on its shortest edge cannot sit on the card.
LOGO_MIN_EDGE = 128
#: Card text and logo never touch the frame edge.
EDGE_MARGIN_PX = 48

_PNG_SIG = b"\x89PNG\r\n\x1a\n"
#: IHDR colour types that carry an alpha channel (4 = grey+alpha, 6 = RGBA).
_PNG_ALPHA_TYPES = (4, 6)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def ad_title(run_dir):
    """The ad's title from the run's own records, or None (never invented).

    Order: the approved script, then the brief, then the music request that
    named the song. The first non-empty title wins.
    """
    if not run_dir:
        return None
    for rel in ("creative/script.json", "brief.json", "music/req.json"):
        doc = _read_json(os.path.join(run_dir, rel))
        if isinstance(doc, dict):
            value = doc.get("title")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def logo_usable(path):
    """(True, "") for a transparent PNG logo, else (False, why).

    Measured from the file's own bytes: PNG signature, IHDR colour type with
    an alpha channel, and both edges at or above LOGO_MIN_EDGE. A logo on a
    solid white background (no alpha) refuses -- it would paint a white box
    over the card.
    """
    if not isinstance(path, str) or not path.strip() or not os.path.isfile(path):
        return False, "logo file not found: %r" % (path,)
    try:
        with open(path, "rb") as fh:
            head = fh.read(33)
    except OSError as exc:
        return False, "cannot read logo: %s" % exc
    if len(head) < 26 or not head.startswith(_PNG_SIG) or head[12:16] != b"IHDR":
        return False, "logo is not a PNG (%s)" % os.path.basename(path)
    width, height = struct.unpack(">II", head[16:24])
    depth, colour = head[24], head[25]
    if depth != 8:
        return False, "logo bit depth %d (8 required)" % depth
    if colour not in _PNG_ALPHA_TYPES:
        return False, ("logo colour type %d has no alpha channel; a "
                       "transparent PNG is required" % colour)
    if width < LOGO_MIN_EDGE or height < LOGO_MIN_EDGE:
        return False, ("logo is %dx%d; at least %d px on each edge is required"
                       % (width, height, LOGO_MIN_EDGE))
    return True, ""


def _logo_path(run_dir):
    """The logo the run recorded, or None. Never a guess at a search path."""
    if not run_dir:
        return None
    brief = _read_json(os.path.join(run_dir, "brief.json"))
    value = brief.get("logo") if isinstance(brief, dict) else None
    if isinstance(value, str) and value.strip():
        return value if os.path.isabs(value) else os.path.join(run_dir, value)
    default = os.path.join(run_dir, "brand", "logo.png")
    return default if os.path.isfile(default) else None


def _text_file(folder, name, text):
    """Write one card/caption text file (drawtext reads it as data)."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _esc(path):
    """One path inside a filtergraph argument (colons and commas escaped)."""
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace(",", "\\,")


def _drawtext(textfile, fontfile, fontsize, fontcolour, y_expr, box, enable):
    """One drawtext filter; the words travel as a text file, never inline."""
    parts = ["drawtext=fontfile=%s" % _esc(fontfile),
             "textfile=%s" % _esc(textfile),
             "expansion=none",
             "fontcolor=%s" % fontcolour,
             "fontsize=%s" % fontsize,
             "x=(w-text_w)/2",
             "y=%s" % y_expr,
             "text_align=center"]
    if box:
        parts += ["box=1", "boxcolor=black@0.45", "boxborderw=18"]
    parts += ["enable='%s'" % enable,
              "shadowcolor=black@0.6", "shadowx=2", "shadowy=2"]
    return ":".join(parts)


def plan_overlay(plan, dry_run=False, ffmpeg="ffmpeg"):
    """Plan the sanctioned overlay stage. Returns a dict, never raises.

    Keys:
      rows       evidence rows (end card, logo, captions), receipt-readable
      chains     filter chains for build_argv; each body consumes the token
                 ``{in}`` (the upstream video label) and may consume
                 ``{logo}``; a ``source`` entry adds one image input
      refusal    {"reason_code", "next_action"} or None
      files      text files written (empty on a dry run)
    """
    fps = float(plan.get("fps") or 30)
    w, h = int(plan.get("width") or 1920), int(plan.get("height") or 1080)
    run_dir = plan.get("run_dir")
    folder = os.path.join(run_dir or ".", "overlay")
    rows, chains, files = [], [], []

    def refuse(code, why):
        return {"rows": rows, "chains": [], "files": files,
                "refusal": {"reason_code": code, "next_action": why}}

    # Text files land inside the run; a plan with no run folder has nowhere
    # to put them, so the stage refuses rather than writing beside the cwd.
    if not run_dir and (plan.get("captions") is True
                        or plan.get("endcard_start_s") is not None):
        return refuse(ENDCARD_INPUT_MISSING if plan.get("endcard_start_s")
                      is not None else CAPTION_BURN_MISSING,
                      "the plan carries no run_dir; there is nowhere to write "
                      "the card/caption text files")

    # --- the font every text draw shares (measured, never assumed) ---------
    try:
        from delivery_variants import cover_image as _CI   # noqa: PLC0415
        font = _CI.resolve_font()
    except Exception:                                      # noqa: BLE001
        font = None

    def _drawtext_missing():
        """True when this box's ffmpeg has no drawtext (measured, not assumed)."""
        if plan.get("drawtext") is not None:
            return not plan["drawtext"]
        try:
            from delivery_variants import cover_image as _CI   # noqa: PLC0415
            return not _CI.has_filter("drawtext", ffmpeg=ffmpeg)
        except Exception:                                  # noqa: BLE001
            return True

    # --- captions (F-EOC-1/F-EOC-5): one burn module owns the cues ---------
    if plan.get("captions") is True:
        cues = [{"text": ln["text"], "start": float(ln["start_s"]),
                 "end": float(ln["end_s"])}
                for ln in (plan.get("lines") or [])
                if isinstance(ln, dict) and str(ln.get("text") or "").strip()
                and isinstance(ln.get("start_s"), (int, float))
                and isinstance(ln.get("end_s"), (int, float))]
        if not cues:
            return refuse(CAPTION_BURN_MISSING,
                          "captions are on but the plan carries no measured "
                          "line windows to burn")
        try:
            from . import captions_burn as _CB
        except ImportError:
            import captions_burn as _CB                    # noqa: PLC0415
        receipt = _CB.overlay_excerpt([c["text"] for c in cues], cues=cues,
                                      height_px=h, width_px=w, fps=fps)
        if not receipt.get("ok"):
            return refuse(receipt.get("reason_code") or CAPTION_BURN_MISSING,
                          receipt.get("detail") or "caption cues refused")
        if font is None:
            return refuse(CAPTION_BURN_MISSING,
                          "no system font found; captions cannot be burned")
        if _drawtext_missing():
            return refuse(DRAWTEXT_UNAVAILABLE,
                          "this ffmpeg build has no drawtext filter, so the "
                          "captions cannot be burned; install an ffmpeg with "
                          "drawtext (libfreetype) and re-run")
        style = receipt.get("style") or {}
        for i, cue in enumerate((receipt.get("plan") or {}).get("cues") or []):
            name = "cue%03d.txt" % i
            tf = os.path.join(folder, name)
            if not dry_run:
                files.append(_text_file(folder, name, cue["text"]))
            chains.append({"body": "{in}" + _drawtext(
                tf, font, style.get("font_size_px", 86),
                style.get("font_colour", "#000000"),
                "h-%d" % int(style.get("bottom_margin_px", 408)), True,
                "between(t,%.3f,%.3f)" % (cue["start"], cue["end"]))})
        rows.append({"stage": "captions", "burned": not dry_run,
                     "cues": receipt.get("cue_count"),
                     "timing": receipt.get("timing"),
                     "srt": bool(receipt.get("srt")),
                     "data_only": receipt.get("data_only")})

    # --- the end card (F-EOC-1): title (+ website) from the run's records --
    ec = plan.get("endcard_start_s")
    if ec is not None:
        title = ad_title(run_dir)
        if not title:
            return refuse(ENDCARD_INPUT_MISSING,
                          "a card is scheduled at %gs but no run record "
                          "(creative/script.json, brief.json, music/req.json) "
                          "names its title" % float(ec))
        if font is None:
            return refuse(CAPTION_BURN_MISSING,
                          "no system font found; the end card text cannot "
                          "be burned")
        if _drawtext_missing():
            return refuse(DRAWTEXT_UNAVAILABLE,
                          "this ffmpeg build has no drawtext filter, so the "
                          "end card cannot carry its title; install an ffmpeg "
                          "with drawtext (libfreetype) and re-run")
        brief = _read_json(os.path.join(run_dir or ".", "brief.json")) or {}
        website = brief.get("website") if isinstance(brief, dict) else None
        words = [title] + ([website] if isinstance(website, str)
                           and website.strip() else [])
        tf = os.path.join(folder, "endcard.txt")
        if not dry_run:
            files.append(_text_file(folder, "endcard.txt", "\n".join(words)))
        enable = "gte(t,%.3f)" % float(ec)
        band = ("drawbox=x=0:y=ih*0.55:w=iw:h=ih*0.45:color=black@0.60"
                ":t=fill:enable='%s'" % enable)
        draw = _drawtext(
            tf, font,
            "min(h*0.062\\,w*%.2f/%d)" % (1.6, max(len(title), 1)),
            "#ffffff", "h*0.60", False, enable)
        chains.append({"body": "{in}" + band + "," + draw})
        rows.append({"stage": "endcard", "start_s": float(ec),
                     "hold_s": plan.get("endcard_hold_s"),
                     "title": title, "website": website,
                     "burned": not dry_run})

        # --- the logo (F-EOC-2), only when the run recorded one -------------
        logo = _logo_path(run_dir)
        if logo:
            ok, why = logo_usable(logo)
            rows.append({"stage": "logo", "path": logo, "usable": ok,
                         "detail": why})
            if not ok:
                return refuse(LOGO_UNUSABLE, why)
            lh = max(1, int(h * 0.10))
            chains.append({"source": logo,
                           "body": "scale=-1:%d{out}" % lh})
            chains.append({"body": "{in}{logo}overlay=W-w-%d:H-h-%d:enable='%s'"
                           % (EDGE_MARGIN_PX, EDGE_MARGIN_PX, enable)})

    return {"rows": rows, "chains": chains, "refusal": None, "files": files}


__all__ = ["TOOL_NAME", "TOOL_VERSION", "ENDCARD_INPUT_MISSING",
           "LOGO_UNUSABLE", "CAPTION_BURN_MISSING", "CAPTION_ZERO_DURATION",
           "DRAWTEXT_UNAVAILABLE",
           "ENDCARD_HOLD_S", "ENDCARD_GAP_S", "LOGO_MIN_EDGE",
           "ad_title", "logo_usable", "plan_overlay"]
