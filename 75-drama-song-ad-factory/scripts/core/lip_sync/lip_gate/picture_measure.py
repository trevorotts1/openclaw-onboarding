#!/usr/bin/env python3
"""picture_measure.py: the REAL lip-sync close-up measurement (LPG001).

Ported from the fixer window's pic_check.py. mediapipe FaceLandmarker with
blendshapes measures the picture; nothing here guesses. If mediapipe, OpenCV
or the face model is missing, `measure()` raises PictureGateUnavailable and the
caller REFUSES (never a silent pass).

Face model: <skill>/assets/face_landmarker.task (or LIPSYNC_FACE_MODEL),
installed by install_face_model.py (Google float16 model, sha256 pinned, not
committed). Heavy local work runs inside load_governor.heavy_slot.
"""
from __future__ import annotations

import os

import os as _gos, sys as _gsys
_gcore = _gos.path.abspath(_gos.path.join(_gos.path.dirname(__file__), '..', '..'))
if _gcore not in _gsys.path:
    _gsys.path.insert(0, _gcore)
import load_governor as _LG  # noqa: E402

try:
    from . import install_face_model as _IM
except ImportError:
    import install_face_model as _IM

MODEL_ENV = "LIPSYNC_FACE_MODEL"
MODEL_NAME = _IM.MODEL_NAME


class PictureGateUnavailable(Exception):
    """mediapipe / OpenCV / the face model is missing: the gate cannot measure."""


def model_path():
    """The face model, verified against the pinned sha256. A missing or wrong
    file refuses and names the install command."""
    p = os.path.abspath(os.environ.get(MODEL_ENV) or _IM.DEFAULT_DEST)
    if not _IM.is_good(p):
        raise PictureGateUnavailable(
            "face model missing or not the pinned file at %s; install it with: %s"
            % (p, _IM.INSTALL_COMMAND))
    return p


def _deps():
    try:
        import cv2, numpy as np, mediapipe as mp
        from mediapipe.tasks.python import vision, BaseOptions
    except Exception as exc:                      # ImportError and friends
        raise PictureGateUnavailable(
            "mediapipe/opencv/numpy not importable: %s: %s; install with: "
            "python3 -m pip install mediapipe opencv-python-headless numpy"
            % (type(exc).__name__, exc))
    return cv2, np, mp, vision, BaseOptions


def measure(path):
    """-> numbers dict. face_count 0 or >1 is reported, not hidden."""
    cv2, np, mp, vision, BaseOptions = _deps()
    mp_model = model_path()
    img = cv2.imread(path)
    if img is None:
        raise PictureGateUnavailable("image unreadable: %s" % path)
    H, W = img.shape[:2]
    with _LG.heavy_slot("lipsync-picture-measure"):
        lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=mp_model),
            running_mode=vision.RunningMode.IMAGE, num_faces=2,
            output_face_blendshapes=True))
        r = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                               data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
    n = len(r.face_landmarks or [])
    out = {"size": [W, H], "face_count": n}
    if n != 1:
        return out
    p = r.face_landmarks[0]
    bs = {b.category_name: b.score for b in r.face_blendshapes[0]}
    fh = abs(p[152].y - p[10].y) * H
    fw = abs(p[454].x - p[234].x) * W
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    xs = np.array([q.x * W for q in p])
    ys = np.array([q.y * H for q in p])
    fc = g[int(max(ys.min(), 0)):int(ys.max()), int(max(xs.min(), 0)):int(xs.max())]
    sharp = float(cv2.Laplacian(cv2.resize(
        fc, (256, max(int(256 * fc.shape[0] / max(fc.shape[1], 1)), 8))),
        cv2.CV_64F).var())
    el, er = p[33], p[263]
    out.update({
        "face_h_pct": round(100 * fh / H, 1),
        "face_box_px": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
        "yaw_proxy": round((p[1].x - (p[234].x + p[454].x) / 2) / (fw / W), 3),
        "roll_deg": round(float(np.degrees(np.arctan2(
            (er.y - el.y) * H, (er.x - el.x) * W))), 1),
        "smile": round((bs.get("mouthSmileLeft", 0) + bs.get("mouthSmileRight", 0)) / 2, 2),
        "jaw_open": round(bs.get("jawOpen", 0), 3),
        "inner_gap_pct": round(100 * abs(p[14].y - p[13].y) * H / fh, 2),
        "sharp_face_256": round(sharp, 1)})
    return out


def crop_to_face(path, out_path, target_pct):
    """Free local 9:16 crop centred on the face so the face is ~target_pct of
    the frame height. Returns out_path, or None when the source cannot hold
    such a crop (never pads or invents pixels)."""
    cv2, _, _, _, _ = _deps()
    m = measure(path)
    if m.get("face_count") != 1:
        return None
    img = cv2.imread(path)
    H, W = img.shape[:2]
    x0, y0, x1, y1 = m["face_box_px"]
    fh = m["face_h_pct"] / 100.0 * H
    ch = int(round(fh * 100.0 / target_pct))
    cw = int(round(ch * 9 / 16))
    if ch > H or cw > W:
        return None
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    left = min(max(cx - cw // 2, 0), W - cw)
    top = min(max(cy - ch // 2, 0), H - ch)
    cv2.imwrite(out_path, img[top:top + ch, left:left + cw])
    return out_path
