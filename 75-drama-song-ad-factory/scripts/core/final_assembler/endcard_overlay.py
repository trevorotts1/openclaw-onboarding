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


def transparent_copy(path, out_dir=None):
    """(copy_path, "") for a transparent copy of an OPAQUE logo, else (None, why).

    N-09: an opaque logo is caught at pre-flight, not refused at render. A
    transparent copy is made beside the original (the original is never
    touched); the copy paints the original's own pixels with the alpha of a
    white-background cut: a pixel equal to the corner colour becomes clear,
    everything else keeps its colour and gains an opaque alpha.

    Only 8-bit truecolour (colour type 2, RGB) and grey (type 0) opaque PNGs
    are converted; anything else falls through to logo_usable's own refusal.
    Returns the copy's path, which the caller draws instead of the original.
    """
    if not isinstance(path, str) or not os.path.isfile(path):
        return None, "logo file not found: %r" % (path,)
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        return None, "cannot read logo: %s" % exc
    if not data.startswith(_PNG_SIG) or data[12:16] != b"IHDR":
        return None, "logo is not a PNG (%s)" % os.path.basename(path)
    width, height = struct.unpack(">II", data[16:24])
    depth, colour = data[24], data[25]
    if depth != 8 or colour not in (0, 2):
        return None, ("logo colour type %d depth %d is not a plain opaque "
                      "PNG (types 0 and 2 only)" % (colour, depth))
    channels = 1 if colour == 0 else 3
    stride = width * channels
    # Walk the IDAT chunks in order; nothing else in the stream is ours.
    raw, pos = b"", 8
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b"IEND":
            break
        if ctype == b"IDAT":
            raw += body
    try:
        import zlib as _zlib
        pixels = _zlib.decompress(raw)
    except Exception as exc:                    # noqa: BLE001 - fail closed
        return None, "logo pixels unreadable: %s" % exc
    if len(pixels) < height * (stride + 1):
        return None, "logo pixel stream is short"
    # Undo the scanline filters (PNG spec 9.2) so every row is raw pixels.
    out, prev = bytearray(), bytearray(stride)
    for y in range(height):
        base = y * (stride + 1)
        ftype, row = pixels[base], bytearray(pixels[base + 1:base + 1 + stride])
        for x in range(stride):
            a = row[x - channels] if x >= channels else 0
            b = prev[x]
            c = prev[x - channels] if x >= channels else 0
            if ftype == 1:
                row[x] = (row[x] + a) & 0xFF
            elif ftype == 2:
                row[x] = (row[x] + b) & 0xFF
            elif ftype == 3:
                row[x] = (row[x] + ((a + b) >> 1)) & 0xFF
            elif ftype == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                row[x] = (row[x] + pred) & 0xFF
        out += row
        prev = row
    key = tuple(out[0:channels])             # the corner pixel is the backdrop
    rgba = bytearray()
    for y in range(height):
        for x in range(width):
            base = y * stride + x * channels
            px = tuple(out[base:base + channels])
            opaque = 0 if px == key else 255
            rgba += bytes(px * 3 if channels == 1 else px) + bytes((opaque,))
    def _chunk(kind, body):
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", _zlib.crc32(kind + body) & 0xFFFFFFFF))
    scan = b"".join(b"\x00" + bytes(rgba[y * width * 4:(y + 1) * width * 4])
                    for y in range(height))
    png = (_PNG_SIG
           + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6,
                                         0, 0, 0))
           + _chunk(b"IDAT", _zlib.compress(scan, 9))
           + _chunk(b"IEND", b""))
    folder = out_dir or os.path.dirname(os.path.abspath(path))
    stem = os.path.splitext(os.path.basename(path))[0]
    target = os.path.join(folder, stem + ".transparent.png")
    if os.path.abspath(target) == os.path.abspath(path):
        return None, "the transparent copy would overwrite the original"
    try:
        os.makedirs(folder, exist_ok=True)
        with open(target, "wb") as fh:
            fh.write(png)
    except OSError as exc:
        return None, "cannot write the transparent copy: %s" % exc
    return target, ""


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


#: N-09: the lower band is a SOFT scrim, not the old hard 60%-black block.
#: It is drawn as a stack of thin strips whose alpha ramps from almost
#: clear at the top to the deepest shade at the bottom, so the card text
#: sits on a gradient instead of a visible edge.
SCRIM_TOP = 0.55          # band starts at 55% of the frame height
SCRIM_STRIPS = 8          # ramp resolution (more = smoother)
SCRIM_MAX_ALPHA = 0.55    # deepest shade at the frame bottom


def _soft_scrim(enable):
    """A stepped, fading lower scrim as drawbox strips (N-09)."""
    span = 1.0 - SCRIM_TOP
    boxes = []
    for k in range(SCRIM_STRIPS):
        y = SCRIM_TOP + span * k / SCRIM_STRIPS
        hgt = span / SCRIM_STRIPS + 0.001          # overlap to avoid seams
        alpha = SCRIM_MAX_ALPHA * (k + 1) / SCRIM_STRIPS
        boxes.append(
            "drawbox=x=0:y=ih*%.4f:w=iw:h=ih*%.4f:color=black@%.3f"
            ":t=fill:enable='%s'" % (y, hgt, alpha, enable))
    return ",".join(boxes)


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
        # N-09: the system-name line comes from the end-card record too, not
        # from prose. Only a recorded, non-empty value is drawn.
        system_name = brief.get("system_name") if isinstance(brief, dict) else None
        words = [title]
        if isinstance(system_name, str) and system_name.strip():
            words.append(system_name.strip())
        if isinstance(website, str) and website.strip():
            words.append(website)
        tf = os.path.join(folder, "endcard.txt")
        if not dry_run:
            files.append(_text_file(folder, "endcard.txt", "\n".join(words)))
        enable = "gte(t,%.3f)" % float(ec)
        # N-09: soft scrim, never the old hard black band (S-11).
        band = _soft_scrim(enable)
        draw = _drawtext(
            tf, font,
            "min(h*0.062\\,w*%.2f/%d)" % (1.6, max(len(title), 1)),
            "#ffffff", "h*0.60", False, enable)
        chains.append({"body": "{in}" + band + "," + draw})
        # F-EOC-8 receipt honesty: the burn has no upper bound, so the card
        # runs from its start to the master end. Print the MEASURED burn, not
        # the declared hold (v11 declared 4.5 s but burned 4.000 s).
        _total = plan.get("total_dur")
        _measured = (round(float(_total) - float(ec), 3)
                     if isinstance(_total, (int, float)) and _total > ec
                     else plan.get("endcard_hold_s"))
        rows.append({"stage": "endcard", "start_s": float(ec),
                     "hold_s": _measured,
                     "declared_hold_s": plan.get("endcard_hold_s"),
                     "title": title, "website": website,
                     "burned": not dry_run})

        # --- the logo (F-EOC-2), only when the run recorded one -------------
        logo = _logo_path(run_dir)
        if logo:
            ok, why = logo_usable(logo)
            if not ok:
                # N-09: an opaque logo is not a render refusal -- a transparent
                # copy is made here, at pre-flight, and the original is never
                # touched. Only a logo that cannot be converted at all refuses.
                # A dry run writes nothing; it says the copy will be made.
                copy, cwhy = ((None, "dry run: copy deferred")
                              if dry_run else transparent_copy(logo, folder))
                if copy:
                    rows.append({"stage": "logo", "path": logo,
                                 "usable": True, "transparent_copy": copy,
                                 "detail": "opaque logo: transparent copy made "
                                           "at pre-flight; original untouched"})
                    logo = copy
                elif dry_run:
                    rows.append({"stage": "logo", "path": logo, "usable": True,
                                 "transparent_copy": None,
                                 "detail": "opaque logo: a transparent copy "
                                           "will be made at render; original "
                                           "untouched"})
                else:
                    rows.append({"stage": "logo", "path": logo, "usable": False,
                                 "detail": why, "copy_detail": cwhy})
                    return refuse(LOGO_UNUSABLE, "%s (%s)" % (why, cwhy))
            else:
                rows.append({"stage": "logo", "path": logo, "usable": True,
                             "detail": why})
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
           "ad_title", "logo_usable", "transparent_copy", "plan_overlay"]
