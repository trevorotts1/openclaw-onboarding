"""logo_check.py - F-EOC-2: the logo intake spec and its validation.

A logo is refused at intake, before any spend, unless it can sit on an end
card cleanly: a PNG with a transparent background and at least MIN_LOGO_SIDE
pixels on each side. The known 350 px opaque file fails both rules.

Reads the PNG header only (stdlib); never decodes pixels, never writes.

ponytail: "has an alpha channel" is not "every background pixel is
transparent". A real fully opaque RGBA file will pass this check; add a zlib
IDAT alpha scan when one shows up.
"""
import json
import os
import struct

PNG_SIG = b"\x89PNG\r\n\x1a\n"
MIN_LOGO_SIDE = 512          # plan default; Trevor can change this line
CODE = "LOGO_UNUSABLE"

#: color type -> has an alpha channel of its own
_ALPHA_TYPES = {4, 6}        # 4 = gray+alpha, 6 = RGBA


def _probe_png(path):
    """Return header facts from a PNG file without decoding its pixels."""
    out = {"path": path, "format": None, "width": None, "height": None,
           "color_type": None, "has_alpha": False, "has_trns": False,
           "error": None}
    try:
        with open(path, "rb") as fh:
            if fh.read(8) != PNG_SIG:
                out["error"] = "not a PNG"
                return out
            out["format"] = "png"
            pos = 8
            first = True
            for _ in range(64):                     # bounded chunk walk
                hdr = fh.read(8)
                if len(hdr) < 8:
                    break
                length, ctype = struct.unpack(">I4s", hdr)
                if first:
                    first = False
                    data = fh.read(13)
                    if ctype != b"IHDR" or len(data) < 13:
                        out["error"] = "first chunk is not IHDR"
                        return out
                    (out["width"], out["height"], _depth,
                     out["color_type"], _comp, _filt, _inter) = struct.unpack(
                        ">IIBBBBB", data)
                    out["has_alpha"] = out["color_type"] in _ALPHA_TYPES
                    fh.seek(length - 13 + 4, os.SEEK_CUR)   # rest of data + CRC
                    continue
                if ctype == b"tRNS":
                    out["has_trns"] = True
                fh.seek(length + 4, os.SEEK_CUR)
                if ctype == b"IEND":
                    break
    except OSError as exc:
        out["error"] = str(exc)[:200]
    return out


def validate_logo(path):
    """Validate one client-supplied logo file.

    Returns {"ok", "code", "reasons", "facts"}. ``reasons`` is a plain-words
    list naming every rule the file broke at once, never just the first.
    """
    if not path or not os.path.isfile(path):
        return {"ok": False, "code": CODE, "reasons": ["logo file is missing"],
                "facts": {"path": path}}
    facts = _probe_png(path)
    reasons = []
    if facts["error"]:
        reasons.append("logo is not a readable PNG: %s" % facts["error"])
    else:
        if not (facts["has_alpha"] or facts["has_trns"]):
            reasons.append("logo has an opaque background (no alpha channel)")
        w, h = facts["width"] or 0, facts["height"] or 0
        if w < MIN_LOGO_SIDE or h < MIN_LOGO_SIDE:
            reasons.append("logo is too small (%sx%s; needs at least %sx%s)"
                           % (w, h, MIN_LOGO_SIDE, MIN_LOGO_SIDE))
    return {"ok": not reasons, "code": None if not reasons else CODE,
            "reasons": reasons, "facts": facts}


def carry_to_end_card(logo_path, control_dir):
    """Write the validated logo path into control/logo.json for F-EOC-1.

    The end card reads its logo only from this record, so a render can never
    pick up an unvalidated file.
    """
    check = validate_logo(logo_path)
    if not check["ok"]:
        return {"ok": False, "code": check["code"], "reasons": check["reasons"]}
    os.makedirs(control_dir, exist_ok=True)
    rec = {"schema": "blackceo.logo/v1", "path": os.path.abspath(logo_path),
           "width": check["facts"]["width"], "height": check["facts"]["height"],
           "transparent": True, "validated": True}
    tmp = os.path.join(control_dir, ".logo.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, os.path.join(control_dir, "logo.json"))
    return {"ok": True, "record": rec, "code": None, "reasons": []}


if __name__ == "__main__":
    import sys
    print(json.dumps(validate_logo(sys.argv[1] if len(sys.argv) > 1 else ""),
                     indent=2, sort_keys=True))
