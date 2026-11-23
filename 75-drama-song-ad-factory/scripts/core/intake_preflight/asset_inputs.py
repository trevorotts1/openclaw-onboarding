"""asset_inputs.py - intake-time validation of client-supplied pictures.

F-EOC-2: a logo must be a minimum-size PNG with a transparent background.
An opaque file (the known 350px opaque logo) or a full-white-background file
is refused ``LOGO_UNUSABLE`` at intake, before any spend. G-FACE-02 (the
lip-source still floor) lives in ``still_provenance.py``.

Stdlib only. No third-party image library is assumed: PNG IHDR/alpha is read
from the chunk stream, a compact 8-bit non-interlaced decoder samples the
border for a full-white background, and JPEG SOF markers give the dimensions.
Failures are records, never silent passes.
"""
import os
import struct
import zlib

#: Smallest accepted logo edge. The known bad file is 350 px wide, so 512
#: refuses it on both size and opacity.
MIN_LOGO_EDGE_PX = 512

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_PNG_ALPHA_COLOR_TYPES = (4, 6)          # gray+alpha, truecolor+alpha


def _problem(code, path, detail):
    return {"code": code, "path": path, "detail": detail}


def parse_png_chunks(data):
    """Return (info, idat, palette, transparency) from a full PNG byte string."""
    if not data.startswith(PNG_MAGIC):
        return None, b"", None, None
    pos, idat, plte, trns = 8, bytearray(), None, None
    info = None
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if typ == b"IHDR":
            w, h = struct.unpack(">II", body[:8])
            info = (w, h, body[8], body[9], body[12])
        elif typ == b"PLTE":
            plte = body
        elif typ == b"tRNS":
            trns = body
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
    return info, bytes(idat), plte, trns


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def _unfilter(raw, width, height, channels):
    """Undo PNG scanline filters; returns a list of bytearrays."""
    stride = width * channels
    rows, prev = [], bytearray(stride)
    at = 0
    for _ in range(height):
        if at >= len(raw):
            break
        ftype = raw[at]
        at += 1
        scan = bytearray(raw[at:at + stride])
        at += stride
        for i in range(stride):
            left = scan[i - channels] if i >= channels else 0
            up = prev[i]
            upleft = prev[i - channels] if i >= channels else 0
            if ftype == 1:
                scan[i] = (scan[i] + left) & 0xFF
            elif ftype == 2:
                scan[i] = (scan[i] + up) & 0xFF
            elif ftype == 3:
                scan[i] = (scan[i] + ((left + up) >> 1)) & 0xFF
            elif ftype == 4:
                scan[i] = (scan[i] + _paeth(left, up, upleft)) & 0xFF
        rows.append(scan)
        prev = scan
    return rows


def _pixel_sampler(info, raw, plte, trns):
    """Return fn(x, y) -> (r, g, b, a) for an 8-bit non-interlaced PNG, or None."""
    width, height, bit, color, interlace = info
    if bit != 8 or interlace != 0:
        return None
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
    if channels is None:
        return None
    try:
        rows = _unfilter(zlib.decompress(raw), width, height, channels)
    except zlib.error:
        return None
    if len(rows) < height:
        return None
    trns_rgb = None
    if color == 0 and trns and len(trns) >= 2:
        trns_rgb = struct.unpack(">H", trns[:2])            # (gray,)
    elif color == 2 and trns and len(trns) >= 6:
        trns_rgb = struct.unpack(">HHH", trns[:6])          # (r, g, b)

    def sample(x, y):
        row = rows[y]
        i = x * channels
        if color in (4, 6):
            if color == 4:
                return row[i], row[i], row[i], row[i + 1]
            return row[i], row[i + 1], row[i + 2], row[i + 3]
        if color == 2:
            r, g, b = row[i], row[i + 1], row[i + 2]
            a = 0 if trns_rgb == (r, g, b) else 255
            return r, g, b, a
        if color == 0:
            v = row[i]
            a = 0 if trns_rgb == (v,) else 255
            return v, v, v, a
        # palette
        idx = row[i]
        if not plte or idx * 3 + 2 >= len(plte):
            return 0, 0, 0, 255
        r, g, b = plte[idx * 3], plte[idx * 3 + 1], plte[idx * 3 + 2]
        a = trns[idx] if trns and idx < len(trns) else 255
        return r, g, b, a

    return sample


def _border_samples(sample, width, height):
    xs = sorted({0, width - 1, width // 2, width // 4, (3 * width) // 4})
    ys = sorted({0, height - 1, height // 2, height // 4, (3 * height) // 4})
    for y in ys:
        for x in xs:
            yield sample(x, y)


def validate_logo(path, min_edge=MIN_LOGO_EDGE_PX):
    """A logo passes only as a minimum-size PNG with a transparent background.

    Returns ``{"ok": bool, "problems": [ ... ], "facts": {...}}``; the refusal
    code is ``LOGO_UNUSABLE`` (shared with F-EOC-1).
    """
    problems, facts = [], {"path": path}
    if not path or not os.path.isfile(path):
        return {"ok": False, "facts": facts,
                "problems": [_problem("LOGO_UNUSABLE", path, "logo file is missing")]}
    if os.path.splitext(path)[1].lower() != ".png":
        return {"ok": False, "facts": facts,
                "problems": [_problem("LOGO_UNUSABLE", path,
                                      "logo must be a PNG with a transparent "
                                      "background, not %r" % os.path.splitext(path)[1])]}
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        return {"ok": False, "facts": facts,
                "problems": [_problem("LOGO_UNUSABLE", path, "unreadable: %s" % exc)]}
    info, idat, plte, trns = parse_png_chunks(data)
    if info is None:
        return {"ok": False, "facts": facts,
                "problems": [_problem("LOGO_UNUSABLE", path, "not a valid PNG file")]}
    width, height, _bit, color, _interlace = info
    facts.update(width=width, height=height, color_type=color,
                 has_alpha_chunk=bool(trns) or color in _PNG_ALPHA_COLOR_TYPES)
    if width < min_edge or height < min_edge:
        problems.append(_problem(
            "LOGO_UNUSABLE", path,
            "logo is %dx%d; the minimum edge is %d px" % (width, height, min_edge)))
    has_alpha = color in _PNG_ALPHA_COLOR_TYPES or (color == 3 and bool(trns)) \
        or (color in (0, 2) and bool(trns))
    if not has_alpha:
        problems.append(_problem(
            "LOGO_UNUSABLE", path,
            "logo has no transparency: a flat background (the known 350px "
            "opaque file) cannot be placed on the end card"))
        return {"ok": False, "facts": facts, "problems": problems}
    sample = _pixel_sampler(info, idat, plte, trns)
    if sample is None:
        # Alpha channel is present; the white-background read is unverified
        # and recorded, never silently claimed clean.
        facts["white_background"] = "unverified"
        return {"ok": not problems, "facts": facts, "problems": problems}
    pixels = list(_border_samples(sample, width, height))
    white = sum(1 for r, g, b, a in pixels
                if a >= 250 and r >= 245 and g >= 245 and b >= 245)
    transparent = sum(1 for _r, _g, _b, a in pixels if a < 250)
    facts.update(border_samples=len(pixels), white_border=white,
                 transparent_border=transparent)
    if pixels and white == len(pixels):
        problems.append(_problem(
            "LOGO_UNUSABLE", path,
            "logo has a full-white background: the border is opaque white on "
            "every sampled edge"))
    elif transparent == 0:
        problems.append(_problem(
            "LOGO_UNUSABLE", path,
            "logo is fully opaque: no transparent pixel on the border"))
    else:
        facts["white_background"] = "clear"
    return {"ok": not problems, "facts": facts, "problems": problems}


def validate_intake_assets(brief):
    """Validate any client-supplied logo and lip-source stills on a brief.

    Returns ``{"ok": bool, "problems": [...], "facts": {...}}``. Absent
    assets are not an error here (the interview asks for them); a supplied
    asset that is unusable is.
    """
    brief = brief or {}
    problems, facts = [], {}
    logo = brief.get("logo_path") or brief.get("logo")
    if isinstance(logo, str) and logo:
        res = validate_logo(logo)
        facts["logo"] = res["facts"]
        problems.extend(res["problems"])
    return {"ok": not problems, "problems": problems, "facts": facts}
