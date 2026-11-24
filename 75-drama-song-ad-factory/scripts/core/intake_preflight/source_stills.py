"""source_stills.py - G-FACE-02: minimum provenance for a lip-source still.

A lip-source still under 720 by 1280 is refused before any paid lip job.
Small crops are re-rendered, never scored and sent. Reads headers only,
stdlib only, writes nothing.
"""
import os
import struct

MIN_STILL_W = 720
MIN_STILL_H = 1280
CODE = "LIPSYNC_STILL_TOO_SMALL"

_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _jpeg_size(path):
    try:
        with open(path, "rb") as fh:
            if fh.read(2) != b"\xff\xd8":
                return None
            while True:
                byte = fh.read(1)
                if not byte:
                    return None
                if byte != b"\xff":
                    continue
                marker = fh.read(1)
                while marker == b"\xff":
                    marker = fh.read(1)
                if not marker:
                    return None
                m = marker[0]
                if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7:
                    continue
                raw = fh.read(2)
                if len(raw) < 2:
                    return None
                seg_len = struct.unpack(">H", raw)[0]
                if m in _SOF:
                    data = fh.read(5)
                    if len(data) < 5:
                        return None
                    h, w = struct.unpack(">HH", data[1:5])
                    return (w, h)
                fh.seek(seg_len - 2, os.SEEK_CUR)
    except OSError:
        return None


def image_size(path):
    """Return (width, height) from a PNG or JPEG header, or None."""
    try:
        from .logo_check import _probe_png
    except ImportError:                       # solo-file invocation
        from logo_check import _probe_png
    facts = _probe_png(path)
    if facts.get("width") and facts.get("height"):
        return (facts["width"], facts["height"])
    return _jpeg_size(path)


def check_lip_source_still(path):
    """Refuse a lip-source still smaller than 720 by 1280."""
    size = image_size(path) if path and os.path.isfile(path) else None
    if size is None:
        return {"ok": False, "code": CODE, "width": None, "height": None,
                "next_action": "re-render the lip-source still at %dx%d or larger"
                               % (MIN_STILL_W, MIN_STILL_H)}
    w, h = size
    if w < MIN_STILL_W or h < MIN_STILL_H:
        return {"ok": False, "code": CODE, "width": w, "height": h,
                "next_action": "re-render the lip-source still at %dx%d or larger"
                               % (MIN_STILL_W, MIN_STILL_H)}
    return {"ok": True, "code": None, "width": w, "height": h,
            "next_action": None}


def check_storyboard_stills(shot_list, run_dir="."):
    """Refuse every lip-source still in a shot list that is too small.

    ``shot_list`` is the parsed storyboard/shot-list.json. A shot is a
    lip-source shot when ``kind`` or ``role`` names it, or it carries a
    ``lip_source_still``. All offenders are returned at once.
    """
    bad = []
    shots = shot_list.get("shots", []) if isinstance(shot_list, dict) else (shot_list or [])
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        is_lip = (str(shot.get("kind", "")).lower() in ("lip", "lip-sync", "lipsync")
                  or str(shot.get("role", "")).lower() in ("lip", "lip-sync", "lipsync")
                  or shot.get("lip_source_still"))
        if not is_lip:
            continue
        rel = shot.get("lip_source_still") or shot.get("still") or shot.get("picture")
        if not rel:
            continue
        path = rel if os.path.isabs(rel) else os.path.join(run_dir, rel)
        res = check_lip_source_still(path)
        if not res["ok"]:
            res["shot_id"] = shot.get("id") or shot.get("shot_id")
            bad.append(res)
    return {"ok": not bad, "code": None if not bad else CODE, "failures": bad}


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(check_lip_source_still(sys.argv[1] if len(sys.argv) > 1 else ""),
                     indent=2, sort_keys=True))
