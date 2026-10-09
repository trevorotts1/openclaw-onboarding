#!/usr/bin/env python3
"""image_gate.py: lip-sync SOURCE PICTURE check for run_gate (LSC001: one rule set).

Runs on every lip-sync source picture BEFORE any paid lip-sync job
(`lip_gate.run_gate` calls it first). It refuses LOUDLY, with every reason, and
never passes silently: a measurement that could not be made is a refusal
(`LIPSYNC_IMAGE_UNMEASURED:<field>`), not a pass.

ONE RULE SET for close-ups: every number (face count, face height %, roll, yaw,
jaw open, smile, lip gap, sharpness) is judged by `picture_gate.check_numbers`,
the calibrated gate the dispatcher enforces (kie_dispatch.lipsync_picture_refusal),
with its constants. This module only adds what that gate does not measure:
  * file size: at least 720x1280 and 9:16 (a crop is fine when it passes)
  * nothing over the mouth or jaw (mouth_occluded / jaw_occluded)
  * no hard shadow across the mouth (mouth_hard_shadow)
  * soft even light, background separated from the head
  * same 3D character as the storyboard (reference_similarity)
  * provenance (an upscaled picture is refused)
picture_gate FAILs refuse; its FLAGS (smile, teeth, small face, mild tilt,
...) are carried in numbers["flags"] and never refuse.

The analysis dict (injected `analyze(path)`; stdlib only, no network, no spend)
is picture_measure.measure()'s numbers (face_count, face_h_pct, roll_deg,
yaw_proxy, jaw_open, smile, inner_gap_pct, sharp_face_256) plus the extra
fields above.

Also holds `closeup_prompt()`: the image-generation prompt template for the
lip-sync close-up, so the picture is MADE this way and not only checked.
"""
from __future__ import annotations

import os
import struct

try:
    from . import picture_gate as PG
except ImportError:                    # script import (tests run from here)
    import picture_gate as PG

TOOL_NAME = "lipsync_image_gate"

# --- thresholds this module owns (the close-up numbers live in picture_gate) --
MIN_W, MIN_H = 720, 1280              # Kling standard outputs 720p
ASPECT = 9.0 / 16.0
ASPECT_TOL = 0.02
MIN_LIGHT_EVENNESS = 0.70               # dim-side / bright-side face luma
MIN_BG_SEPARATION = 0.15                # head-vs-background luma/colour gap
MIN_REF_SIMILARITY = 0.80               # same character as the storyboard ref
BAD_PROVENANCE = ("upscaled",)          # a crop is allowed when it passes every check

# --- reason codes -----------------------------------------------------------
IMAGE_MISSING = "LIPSYNC_IMAGE_MISSING"
IMAGE_UNCHECKED = "LIPSYNC_IMAGE_UNCHECKED"
UNMEASURED = "LIPSYNC_IMAGE_UNMEASURED"
RESOLUTION = "LIPSYNC_IMAGE_RESOLUTION"
NOT_PORTRAIT = "LIPSYNC_IMAGE_NOT_9X16"
FACE_SIZE = "LIPSYNC_IMAGE_FACE_SIZE"
NOT_FRONTAL = "LIPSYNC_IMAGE_NOT_FRONTAL"
MOUTH_OPEN = "LIPSYNC_IMAGE_MOUTH_OPEN"
OCCLUDED = "LIPSYNC_IMAGE_MOUTH_OR_JAW_COVERED"
LIGHT = "LIPSYNC_IMAGE_LIGHT_UNEVEN"
MOUTH_SHADOW = "LIPSYNC_IMAGE_MOUTH_SHADOW"
BACKGROUND = "LIPSYNC_IMAGE_BACKGROUND_NOT_SEPARATED"
WRONG_CHARACTER = "LIPSYNC_IMAGE_NOT_SAME_CHARACTER"
SOFT = "LIPSYNC_IMAGE_NOT_SHARP"
CROPPED = "LIPSYNC_IMAGE_CROPPED_OR_UPSCALED"


class LipsyncImageRefused(Exception):
    """Raised before any paid job. .reasons is the full list of (code, text)."""

    def __init__(self, reasons, image=None):
        self.reasons = list(reasons)
        self.image = image
        super().__init__("lip-sync source picture refused (%s): %s" % (
            image, "; ".join("%s: %s" % r for r in self.reasons)))


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def image_size(path):
    """(width, height) from a PNG or JPEG header, stdlib only; None if not
    readable (caller treats that as UNMEASURED, never as a pass)."""
    try:
        with open(path, "rb") as f:
            head = f.read(26)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                return struct.unpack(">II", head[16:24])
            if head[:2] != b"\xff\xd8":
                return None
            f.seek(2)
            while True:
                b = f.read(1)
                while b and b != b"\xff":
                    b = f.read(1)
                m = f.read(1)
                while m == b"\xff":
                    m = f.read(1)
                if not m:
                    return None
                if m[0] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", f.read(7)[3:7])
                    return w, h
                if m[0] in (0xD8, 0x01) or 0xD0 <= m[0] <= 0xD7:
                    continue
                n = struct.unpack(">H", f.read(2))[0]
                f.seek(n - 2, 1)
    except (OSError, struct.error, IndexError):
        return None


_PG_CODE = {"FACE_COUNT": UNMEASURED, "UNMEASURED": UNMEASURED, "FACE_SIZE": FACE_SIZE,
            "HEAD_ROLL": NOT_FRONTAL, "HEAD_YAW": NOT_FRONTAL, "MOUTH_OPEN": MOUTH_OPEN,
            "SOFT": SOFT}


def check_image(size, a):
    """Pure rules. size=(w, h) or None; a = analysis dict (see module doc).
    -> (reasons, nums). The close-up numbers are picture_gate.check_numbers."""
    r, nums, flags = [], {}, []

    def need(field, ok=_num):
        v = a.get(field)
        if v is None or not ok(v):
            r.append((UNMEASURED, "%s was not measured" % field))
            return None
        return v

    def flag(field):
        v = a.get(field)
        if not isinstance(v, bool):
            r.append((UNMEASURED, "%s was not measured" % field))
            return None
        return v

    if not size:
        r.append((UNMEASURED, "image size could not be read"))
    else:
        w, h = size
        nums.update(width=w, height=h)
        if w < MIN_W or h < MIN_H:
            r.append((RESOLUTION, "%dx%d is below %dx%d" % (w, h, MIN_W, MIN_H)))
        if abs(w / float(h) - ASPECT) > ASPECT_TOL:
            r.append((NOT_PORTRAIT, "%dx%d is not portrait 9:16" % (w, h)))
    fails, pflags = PG.check_numbers(a)             # the ONE close-up rule set
    for code, text in fails:
        r.append((_PG_CODE.get(code, UNMEASURED), "%s: %s" % (code, text)))
    flags.extend("%s: %s" % f for f in pflags)
    for k in ("face_h_pct", "roll_deg", "yaw_proxy", "jaw_open", "smile",
              "inner_gap_pct", "sharp_face_256"):
        if _num(a.get(k)):
            nums[k] = a[k]
    if flag("mouth_occluded") or flag("jaw_occluded"):
        r.append((OCCLUDED, "something covers the mouth or jaw (hand, "
                  "microphone, hair or hat brim)"))
    le = need("light_evenness")
    if le is not None:
        nums["light_evenness"] = le
        if le < MIN_LIGHT_EVENNESS:
            r.append((LIGHT, "light evenness %.2f < %.2f; use soft even light"
                      % (le, MIN_LIGHT_EVENNESS)))
    if flag("mouth_hard_shadow"):
        r.append((MOUTH_SHADOW, "hard shadow across the mouth"))
    bg = need("background_separation")
    if bg is not None:
        nums["background_separation"] = bg
        if bg < MIN_BG_SEPARATION:
            r.append((BACKGROUND, "background not separated from the head "
                      "(%.2f < %.2f)" % (bg, MIN_BG_SEPARATION)))
    sim = need("reference_similarity")
    if sim is not None:
        nums["reference_similarity"] = sim
        if sim < MIN_REF_SIMILARITY:
            r.append((WRONG_CHARACTER, "similarity to the storyboard "
                      "character reference %.2f < %.2f" % (sim, MIN_REF_SIMILARITY)))
    prov = a.get("provenance")
    if not isinstance(prov, str) or not prov:
        r.append((UNMEASURED, "provenance was not recorded"))
    elif prov in BAD_PROVENANCE:
        r.append((CROPPED, "picture is %s; use a native or cropped 9:16 "
                  "picture of at least %dx%d" % (prov, MIN_W, MIN_H)))
    nums["flags"] = flags
    return r, nums


def check_source_image(image, analyze, size=None):
    """Gate one source picture. image: a file path (or a reference-set entry
    dict with "path"). analyze(path) -> analysis dict (injected detector).
    Returns {"pass", "image", "reasons": [(code, text)], "numbers"}; a detector
    that raises or returns a non-dict is a refusal, never a pass."""
    path = image.get("path") if isinstance(image, dict) else image
    if not isinstance(path, str) or not path:
        return {"pass": False, "image": path, "numbers": {},
                "reasons": [(IMAGE_MISSING, "no source picture given")]}
    try:
        a = analyze(image)
    except Exception as exc:                      # fail closed, say why
        a = None
        err = "%s: %s" % (type(exc).__name__, exc)
    else:
        err = "detector returned no analysis"
    if not isinstance(a, dict):
        return {"pass": False, "image": path, "numbers": {},
                "reasons": [(UNMEASURED, err)]}
    reasons, nums = check_image(size or image_size(path), a)
    return {"pass": not reasons, "image": path, "reasons": reasons,
            "numbers": nums}


def require_source_image(image, analyze, size=None):
    """check_source_image, but raises LipsyncImageRefused on any reason. Call
    before every paid lip-sync job; returns the passing result."""
    res = check_source_image(image, analyze, size)
    if not res["pass"]:
        raise LipsyncImageRefused(res["reasons"], res["image"])
    return res


def closeup_prompt(character, style_clause="", reference_note="", mode=None):
    """Image-generation prompt for the lip-sync close-up (the picture is MADE
    this way). character: the approved character description from the
    storyboard reference; style_clause: the look's style bible line.

    U15e: pass ``mode`` (a render mode id) and the identity line and style
    clause come from that mode's `keyframe_clause` (design 5.2: the close-up
    picture carries the same mode as the clip and the Kling avatar prompt). A
    realism close-up says "photoreal", never "same 3D character". With no mode
    the wording is unchanged for older callers.
    """
    if not isinstance(character, str) or not character.strip():
        raise ValueError("character description is required")
    if mode:
        import sys as _sys
        _core = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if _core not in _sys.path:
            _sys.path.insert(0, _core)
        import prompt_templates as _PT
        clause = (_PT.load("mode", mode).get("keyframe_clause") or "").strip()
        if not clause:
            raise ValueError("mode %r carries no keyframe_clause" % (mode,))
        identity = clause
        style_clause = style_clause or clause
    else:
        identity = ("same 3D character, face and styling as the approved "
                    "storyboard reference")
    parts = [
        character.strip().rstrip("."),
        identity + (" (%s)" % reference_note.strip() if reference_note.strip() else ""),
        "portrait 9:16, 720x1280 or larger",
        "chest-up portrait, the face filling about 30-40 percent of the "
        "frame height, head centred",
        "face looking straight into the camera, eyes to lens, shoulders "
        "square, no head turn or tilt",
        "lips relaxed and very slightly parted, calm neutral expression, "
        "no big toothy smile, no teeth showing",
        "nothing covering the mouth or jaw: no hands, no microphone, no "
        "hair across the face, no hat brim, no scarf",
        "soft even light across the whole face, no hard shadow on the mouth "
        "or under the nose, gentle fill from the front",
        "plain background clearly separated from the head in tone and "
        "colour, with room around the hair",
        "sharp focus on the eyes and lips, high detail, no motion blur",
    ]
    if style_clause and style_clause.strip():
        parts.append(style_clause.strip())
    return ". ".join(p.rstrip(".") for p in parts) + "."
