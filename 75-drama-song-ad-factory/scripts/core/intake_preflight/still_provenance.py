"""still_provenance.py - G-FACE-02: the lip-source still size floor.

A lip-source still must be at least 720x1280. Stills as small as 212x377,
155x275 or 147x261 score far under the sharpness floor and then burn paid lip
jobs, so they are refused at intake and re-rendered instead of scored-and-sent.

Stdlib only: PNG IHDR and JPEG SOF markers give the dimensions; no image
library is assumed. Non-lip stills are not judged here.
"""
import os
import struct

MIN_STILL_W, MIN_STILL_H = 720, 1280
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _jpeg_size(data):
    if not data.startswith(b"\xff\xd8"):
        return None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg_len = int.from_bytes(data[i + 2:i + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                      0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            height = int.from_bytes(data[i + 5:i + 7], "big")
            width = int.from_bytes(data[i + 7:i + 9], "big")
            return width, height
        i += 2 + seg_len
    return None


def image_size(path):
    """(width, height) for a PNG or JPEG, or None."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(64)
            if head.startswith(_PNG_MAGIC) and len(head) >= 24:
                return struct.unpack(">II", head[16:24])
            if head.startswith(b"\xff\xd8"):
                fh.seek(0)
                return _jpeg_size(fh.read())
    except (OSError, struct.error, ValueError):
        return None
    return None


def validate_source_still(path, *, is_lip_source=True):
    """A lip-source still under 720x1280 is refused before any paid lip job.

    Returns ``{"ok", "problems", "facts"}`` with refusal code
    ``SOURCE_STILL_TOO_SMALL``.
    """
    facts = {"path": path, "is_lip_source": bool(is_lip_source)}
    if not is_lip_source:
        return {"ok": True, "facts": facts, "problems": []}
    if not path or not os.path.isfile(path):
        return {"ok": False, "facts": facts, "problems": [{
            "code": "SOURCE_STILL_TOO_SMALL", "path": path,
            "detail": "lip-source still is missing"}]}
    size = image_size(path)
    if size is None:
        return {"ok": False, "facts": facts, "problems": [{
            "code": "SOURCE_STILL_TOO_SMALL", "path": path,
            "detail": "cannot read the still's dimensions"}]}
    width, height = size
    facts.update(width=width, height=height)
    if width < MIN_STILL_W or height < MIN_STILL_H:
        return {"ok": False, "facts": facts, "problems": [{
            "code": "SOURCE_STILL_TOO_SMALL", "path": path,
            "detail": "lip-source still is %dx%d; it must be re-rendered at "
                      "720x1280 or larger before any paid lip job"
                      % (width, height)}]}
    return {"ok": True, "facts": facts, "problems": []}


def validate_stills(stills):
    """Validate a list of ``{path, purpose}`` records; returns a problems list."""
    problems, facts = [], []
    for entry in stills or []:
        if not isinstance(entry, dict) or not entry.get("path"):
            continue
        res = validate_source_still(
            entry["path"], is_lip_source=entry.get("purpose", "lip_source") == "lip_source")
        facts.append(res["facts"])
        problems.extend(res["problems"])
    return {"ok": not problems, "problems": problems, "facts": facts}
