#!/usr/bin/env python3
"""mouth_landmarks.py: real mouth-opening measurement (face landmarks).

Ported from the fixer window's lipsync_check (2026-10-08). Per frame: outer-lip
height (landmarks 0-17) / face height (landmarks 10-152), found with the
mediapipe FaceLandmarker; the face is cropped, upscaled 3x and re-detected
(small faces give coarse landmarks). NaN = no face in that frame.

Heavy work (frame decode + landmarks) runs inside load_governor.heavy_slot.
mediapipe / opencv / numpy / the model file are imported or looked up lazily:
if any is missing, mouth_series() raises Unmeasured (reason code LIP_UNMEASURED).
That is "unmeasured, report", NEVER a silent pass; lip_gate turns it into an
UNMEASURABLE verdict that qc_check refuses.

Model file (Google face_landmarker, float16, ~4 MB): env LIPSYNC_FACE_MODEL,
else <this folder>/face_landmarker.task. Not committed; see DEPENDENCY-MANIFEST.md.
"""
from __future__ import annotations

import os as _os
import sys as _sys

_core = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
if _core not in _sys.path:
    _sys.path.insert(0, _core)
import load_governor as _LG  # noqa: E402

LIP_UNMEASURED = "LIP_UNMEASURED"
GEO = (0.55, 0.85)   # where the mouth sits inside the face box (human proportions)
MIN_FACE = 0.95      # share of frames that must have a face


class Unmeasured(Exception):
    """The measurement could not be made. Message starts with LIP_UNMEASURED."""


def model_path():
    p = _os.environ.get("LIPSYNC_FACE_MODEL") or _os.path.join(
        _os.path.dirname(__file__), "face_landmarker.task")
    return p if _os.path.isfile(p) else None


def mouth_series(clip):
    """-> dict(fps, opening=[float|None per frame], face_found, mouth_pos).
    Raises Unmeasured when mediapipe, opencv, numpy or the model is missing."""
    try:
        import cv2
        import numpy as np
        import mediapipe as mp
        from mediapipe.tasks.python import vision, BaseOptions
    except Exception as e:  # ImportError and broken native installs alike
        raise Unmeasured("%s: mediapipe/opencv/numpy not importable (%s)"
                         % (LIP_UNMEASURED, type(e).__name__))
    model = model_path()
    if not model:
        raise Unmeasured("%s: face model not found (set LIPSYNC_FACE_MODEL)"
                         % LIP_UNMEASURED)

    def detect(lm, bgr):
        return lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                                  data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))

    def ratio(p):
        return abs(p[17].y - p[0].y) / max(abs(p[152].y - p[10].y), 1e-6)

    with _LG.heavy_slot("lip-landmarks"):
        cap = cv2.VideoCapture(clip)
        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        lm = vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=model),
                running_mode=vision.RunningMode.IMAGE, num_faces=1))
        out, geo = [], []
        while True:
            ok, f = cap.read()
            if not ok:
                break
            r = detect(lm, f)
            H, W = f.shape[:2]
            if not r.face_landmarks:
                out.append(None)
                continue
            p = r.face_landmarks[0]
            v = ratio(p)
            xs = np.array([q.x * W for q in p])
            ys = np.array([q.y * H for q in p])
            s = max(np.ptp(xs), np.ptp(ys)) * 0.8
            x0, y0 = int(max(xs.mean() - s, 0)), int(max(ys.mean() - s, 0))
            x1, y1 = int(min(xs.mean() + s, W)), int(min(ys.mean() + s, H))
            if x1 - x0 > 20 and y1 - y0 > 20:
                r2 = detect(lm, cv2.resize(f[y0:y1, x0:x1], None, fx=3, fy=3,
                                           interpolation=cv2.INTER_CUBIC))
                if r2.face_landmarks:
                    p = r2.face_landmarks[0]
                    v = ratio(p)
            out.append(float(v))
            geo.append((p[13].y - p[10].y) / max(p[152].y - p[10].y, 1e-6))
        cap.release()
    found = sum(v is not None for v in out) / len(out) if out else 0.0
    return {"fps": float(fps), "opening": out, "face_found": round(found, 3),
            "mouth_pos": float(np.median(geo)) if geo else 0.0}


def usable(series):
    """-> (opening list with gaps filled, None) or (None, reason) when the face
    is missing / not human-proportioned (UNMEASURABLE, never a pass). Reasons feed the UNMEASURABLE verdict."""
    op = series["opening"]
    if len(op) < 12 or series["face_found"] < MIN_FACE:
        return None, "face not found in %.0f%% of frames (< %.0f%%)" % (
            100 * series["face_found"], 100 * MIN_FACE)
    if not GEO[0] <= series["mouth_pos"] <= GEO[1]:
        return None, "landmarks implausible (mouth at %.2f of face height)" % (
            series["mouth_pos"])
    known = [i for i, v in enumerate(op) if v is not None]
    filled = []
    for i, v in enumerate(op):
        if v is None:   # linear fill between the nearest known frames
            a = max((k for k in known if k < i), default=None)
            b = min((k for k in known if k > i), default=None)
            if a is None or b is None:
                v = op[b if a is None else a]
            else:
                v = op[a] + (op[b] - op[a]) * (i - a) / (b - a)
        filled.append(v)
    return filled, None
