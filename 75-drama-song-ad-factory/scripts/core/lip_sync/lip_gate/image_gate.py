#!/usr/bin/env python3
"""image_gate.py: lip-sync SOURCE PICTURE gate (owner order, Trevor 2026-10-08).

Runs on every lip-sync source picture BEFORE any paid lip-sync job
(`lip_gate.run_gate` calls it first). It refuses LOUDLY, with every reason, and
never passes silently: a measurement that could not be made is a refusal
(`LIPSYNC_IMAGE_UNMEASURED:<field>`), not a pass.

What a good lip-sync picture is, and how each point is checked:

  1. face looks straight at the camera   yaw/pitch from the injected detector
  2. head-and-shoulders, portrait 9:16,   image size + face box height / frame
     face ~35-40% of frame height          height (accept 30-45%), face centred
  3. mouth closed or slightly parted,     mouth_open_ratio, teeth_smile flag
     neutral, no big toothy smile
  4. nothing over mouth or jaw            mouth_occluded / jaw_occluded flags
  5. soft even light, no hard shadow      light_evenness, mouth_hard_shadow;
     across the mouth, background           background_separation
     separated from the head
  6. same 3D character as the storyboard  reference_similarity vs the reference
  7. sharp, >= 1080x1920, never cropped   size, sharpness, provenance

Stdlib only, no network, no spend. The face detector / pose estimator is
INJECTED (`analyze(path) -> dict`, fields below) so tests run at $0 and the
real detector can be swapped without touching the rules. Resolution and aspect
are read from the file header itself when a path is given.

Also holds `closeup_prompt()`: the image-generation prompt template for the
lip-sync close-up, so the picture is MADE this way and not only checked.
"""
from __future__ import annotations

import struct

TOOL_NAME = "lipsync_image_gate"

# --- thresholds (calibrate on first real runs; every one is a named knob) ----
MIN_W, MIN_H = 1080, 1920
ASPECT = 9.0 / 16.0
ASPECT_TOL = 0.02
FACE_H_TARGET = (0.35, 0.40)            # the aim; the prompt asks for this
FACE_H_ACCEPT = (0.30, 0.45)            # the gate accepts this
MAX_YAW_DEG = 10.0
MAX_PITCH_DEG = 10.0
CENTER_X = (0.35, 0.65)                 # face centre, share of frame width
MAX_MOUTH_OPEN = 0.15                   # lip gap / mouth width: closed..parted
MIN_LIGHT_EVENNESS = 0.70               # dim-side / bright-side face luma
MIN_BG_SEPARATION = 0.15                # head-vs-background luma/colour gap
MIN_SHARPNESS = 100.0                   # Laplacian variance on the face crop
MIN_REF_SIMILARITY = 0.80               # same character as the storyboard ref
BAD_PROVENANCE = ("cropped_from_wide", "upscaled")

# --- reason codes -----------------------------------------------------------
IMAGE_MISSING = "LIPSYNC_IMAGE_MISSING"
IMAGE_UNCHECKED = "LIPSYNC_IMAGE_UNCHECKED"
UNMEASURED = "LIPSYNC_IMAGE_UNMEASURED"
RESOLUTION = "LIPSYNC_IMAGE_RESOLUTION"
NOT_PORTRAIT = "LIPSYNC_IMAGE_NOT_9X16"
FACE_SIZE = "LIPSYNC_IMAGE_FACE_SIZE"
FRAMING = "LIPSYNC_IMAGE_FRAMING"
NOT_FRONTAL = "LIPSYNC_IMAGE_NOT_FRONTAL"
MOUTH_OPEN = "LIPSYNC_IMAGE_MOUTH_OPEN"
TOOTHY_SMILE = "LIPSYNC_IMAGE_TOOTHY_SMILE"
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


def check_image(size, a):
    """Pure rules. size=(w, h) or None; a = analysis dict. -> (reasons, nums).

    a keys: face_box [x, y, w, h] px; yaw_deg; pitch_deg; mouth_open_ratio;
    teeth_smile (bool); mouth_occluded (bool); jaw_occluded (bool);
    light_evenness 0-1; mouth_hard_shadow (bool); background_separation 0-1;
    reference_similarity 0-1 (vs the storyboard character reference);
    sharpness; provenance (str, e.g. "generated").
    """
    r, nums = [], {}

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
    box = a.get("face_box")
    if not (isinstance(box, (list, tuple)) and len(box) == 4
            and all(_num(x) for x in box) and box[2] > 0 and box[3] > 0):
        r.append((UNMEASURED, "face_box was not measured (no face found?)"))
    elif size:
        share = box[3] / float(size[1])
        cx = (box[0] + box[2] / 2.0) / float(size[0])
        nums.update(face_height_share=round(share, 4), face_center_x=round(cx, 4))
        if not FACE_H_ACCEPT[0] <= share <= FACE_H_ACCEPT[1]:
            r.append((FACE_SIZE, "face is %.0f%% of frame height; need about "
                      "%d-%d%% (accept %d-%d%%)" % (
                          share * 100, FACE_H_TARGET[0] * 100,
                          FACE_H_TARGET[1] * 100, FACE_H_ACCEPT[0] * 100,
                          FACE_H_ACCEPT[1] * 100)))
        if not CENTER_X[0] <= cx <= CENTER_X[1]:
            r.append((FRAMING, "face centre is at %.0f%% of the width; keep "
                      "the head centred (head and shoulders)" % (cx * 100)))
    yaw, pitch = need("yaw_deg"), need("pitch_deg")
    if yaw is not None and pitch is not None:
        nums.update(yaw_deg=yaw, pitch_deg=pitch)
        if abs(yaw) > MAX_YAW_DEG or abs(pitch) > MAX_PITCH_DEG:
            r.append((NOT_FRONTAL, "head turned yaw %.1f / pitch %.1f deg; "
                      "must look straight at the camera (+/-%d)" % (
                          yaw, pitch, MAX_YAW_DEG)))
    mo = need("mouth_open_ratio")
    if mo is not None:
        nums["mouth_open_ratio"] = mo
        if mo > MAX_MOUTH_OPEN:
            r.append((MOUTH_OPEN, "mouth open ratio %.2f > %.2f; closed or "
                      "slightly parted only" % (mo, MAX_MOUTH_OPEN)))
    if flag("teeth_smile"):
        r.append((TOOTHY_SMILE, "big toothy smile; neutral expression needed"))
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
    sh = need("sharpness")
    if sh is not None:
        nums["sharpness"] = sh
        if sh < MIN_SHARPNESS:
            r.append((SOFT, "face sharpness %.0f < %.0f" % (sh, MIN_SHARPNESS)))
    prov = a.get("provenance")
    if not isinstance(prov, str) or not prov:
        r.append((UNMEASURED, "provenance was not recorded"))
    elif prov in BAD_PROVENANCE:
        r.append((CROPPED, "picture is %s; generate it natively at 9:16"
                  % prov))
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


def closeup_prompt(character, style_clause="", reference_note=""):
    """Image-generation prompt for the lip-sync close-up (the picture is MADE
    this way). character: the approved 3D character description from the
    storyboard reference; style_clause: the look's style bible line."""
    if not isinstance(character, str) or not character.strip():
        raise ValueError("character description is required")
    parts = [
        character.strip().rstrip("."),
        "same 3D character, face and styling as the approved storyboard "
        "reference" + (" (%s)" % reference_note.strip() if reference_note.strip() else ""),
        "portrait 9:16, 1080x1920 or larger, generated natively at this "
        "frame, not cropped from a wide shot",
        "head-and-shoulders portrait, the face filling about 35-40 percent "
        "of the frame height, head centred",
        "face looking straight into the camera, eyes to lens, shoulders "
        "square, no head turn or tilt",
        "mouth closed or very slightly parted, calm neutral expression, "
        "lips relaxed, no big toothy smile, no teeth showing",
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
