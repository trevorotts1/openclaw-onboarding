#!/usr/bin/env python3
"""picture_gate.py: the MEASURED lip-sync picture gate + receipt (LPG001).

Why: on 2026-10-08 two close-ups (face 28% of frame + smile; face 34% + teeth +
7.8 degree tilt) went to paid Kling lip-sync unmeasured. The check existed on
paper only. Now `measure_picture` really measures (mediapipe FaceLandmarker with
blendshapes), `gate_picture` writes a receipt keyed by the file's sha256, and
the dispatcher (kie_dispatch.picture_gate_refusal) refuses any lip-sync job
without a PASS receipt for that exact file. Missing mediapipe/model/face = FAIL
receipt or refusal, never a pass.

Free fix first (`fix_picture`): one local crop for a small face, then re-measure;
smile/teeth/tilt -> at most 2 paid regenerations (default: kie_dispatch's
make_picture_regenerator, so they reserve against the cap), then re-measure,
then refuse. Only a PASS goes on.

Thresholds are named knobs, calibrated on the real pictures: 28.1/34.4% faces
fail, the fixed 37.8% close-up (smile 0.36, roll -4.3) and the fixed 36.8% 30-Day
crop (smile 0.59, lips closed) pass. Teeth/jawOpen carry the closed-mouth check.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

TOOL_NAME = "lipsync_picture_gate"
RECEIPT_SUFFIX = ".picture-gate.json"

# ============================ CONSTANTS (ONE BLOCK) ============================
# Same names and values in onboarding skill 75 and 999-setup skill 75. Change both.
# Calibrated on the real pictures: 30-Day original 28.1% / smile 0.62 fails; Perfect
# Daughter original 34.4% / roll -7.8 / smile 0.83 fails; Perfect Daughter fix 37.8% /
# roll -4.3 / smile 0.36 passes; 30-Day crop 36.8% / smile 0.59 passes.
MIN_FACE_H_PCT = 35.0     # forehead(10)-chin(152) as % of frame height; NO upper limit
MAX_ABS_ROLL_DEG = 5.0
MAX_ABS_YAW = 0.12        # nose offset / face width
MAX_SMILE = 0.60          # mean mouthSmileL/R
MAX_JAW_OPEN = 0.15
MAX_INNER_GAP_PCT = 1.0   # lip gap / face height (the teeth check)
MIN_SHARP = 100.0         # Laplacian variance, face crop resized to 256 wide
CROP_TARGET_PCT = 37.0    # the free local crop aims here
MAX_LOCAL_CROPS = 1       # one free local crop for a small face
MAX_REGENERATIONS = 2     # Trevor's 2-try rule: paid regenerations, then refuse
REGEN_MODEL = "gpt-image-2-image-to-image"
REGEN_PROMPT = "neutral expression, lips closed, facing camera, head level"
FACE_MODEL_NAME = "face_landmarker.task"
FACE_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
                  "face_landmarker/float16/latest/face_landmarker.task")
FACE_MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
FACE_MODEL_ENV = "LIPSYNC_FACE_MODEL"
# ===============================================================================


class PictureRefused(Exception):
    def __init__(self, reasons, image=None):
        self.reasons, self.image = list(reasons), image
        super().__init__("lip-sync picture refused (%s): %s" % (image, "; ".join(
            "%s: %s" % r for r in self.reasons)))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _model_path():
    return os.environ.get(FACE_MODEL_ENV) or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), FACE_MODEL_NAME)


def install_hint():
    skill = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    return "python3 %s" % os.path.join(skill, "scripts", "install_face_model.py")


def measure_picture(path):
    """Real measurement -> dict of numbers. Raises PictureRefused when the
    measuring tools are missing (never returns a made-up pass)."""
    try:
        import cv2
        import numpy as np
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
    except Exception as e:                                  # noqa: BLE001
        raise PictureRefused([("PICTURE_MEDIAPIPE_MISSING",
                               "mediapipe/opencv/numpy not importable: %r; "
                               "pip install mediapipe opencv-python-headless numpy "
                               "(then: %s)" % (e, install_hint()))], path)
    model = _model_path()
    if not os.path.isfile(model):
        raise PictureRefused([("PICTURE_MODEL_MISSING", "%s not found at %s; install it with: %s "
                               "(or set %s)" % (FACE_MODEL_NAME, model, install_hint(), FACE_MODEL_ENV))], path)
    if not os.environ.get(FACE_MODEL_ENV) and sha256_file(model) != FACE_MODEL_SHA256:
        raise PictureRefused([("PICTURE_MODEL_CORRUPT", "%s does not match the pinned sha256; "
                               "reinstall with: %s" % (model, install_hint()))], path)
    img = cv2.imread(path)
    if img is None:
        raise PictureRefused([("PICTURE_UNREADABLE", "cannot read image")], path)
    H, W = img.shape[:2]
    import sys
    core = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if core not in sys.path:
        sys.path.insert(0, core)
    import load_governor as _LG
    with _LG.heavy_slot("lipsync-picture-gate"):
        lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model),
            running_mode=vision.RunningMode.IMAGE, num_faces=2,
            output_face_blendshapes=True))
        r = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                               data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
    n = len(r.face_landmarks or [])
    if n != 1:
        return {"faces": n, "size": [W, H]}
    p = r.face_landmarks[0]
    bs = {b.category_name: b.score for b in r.face_blendshapes[0]}
    fh = abs(p[152].y - p[10].y) * H
    fw = abs(p[454].x - p[234].x) * W
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    xs = np.array([q.x * W for q in p]); ys = np.array([q.y * H for q in p])
    fc = g[int(max(ys.min(), 0)):int(ys.max()), int(max(xs.min(), 0)):int(xs.max())]
    sharp = cv2.Laplacian(cv2.resize(fc, (256, max(int(256 * fc.shape[0] / max(fc.shape[1], 1)), 8))),
                          cv2.CV_64F).var() if fc.size else 0.0
    el, er = p[33], p[263]
    return {"faces": 1, "size": [W, H], "face_h_pct": round(100 * fh / H, 1),
            "face_cx": round(float(xs.mean()), 1), "face_cy": round(float(ys.mean()), 1),
            "roll_deg": round(float(np.degrees(np.arctan2((er.y - el.y) * H, (er.x - el.x) * W))), 1),
            "yaw": round((p[1].x - (p[234].x + p[454].x) / 2) / (fw / W), 3),
            "smile": round((bs.get("mouthSmileLeft", 0) + bs.get("mouthSmileRight", 0)) / 2, 2),
            "jaw_open": round(bs.get("jawOpen", 0), 3),
            "inner_gap_pct": round(100 * abs(p[14].y - p[13].y) * H / fh, 2),
            "sharp": round(float(sharp), 1)}


def judge_picture(n):
    """Pure rules: numbers -> (verdict, [(code, text)]). Anything not measured fails."""
    f = lambda k: n.get(k) if isinstance(n.get(k), (int, float)) and not isinstance(n.get(k), bool) else None  # noqa: E731
    if n.get("faces") != 1:
        return "FAIL", [("PICTURE_FACE_COUNT", "need exactly one face, found %s" % n.get("faces"))]
    r = []
    chk = [("face_h_pct", lambda v: v >= MIN_FACE_H_PCT, "PICTURE_FACE_SMALL", "face %.1f%% of frame height; need >= %.0f%%" % (f("face_h_pct") or 0, MIN_FACE_H_PCT)),
           ("roll_deg", lambda v: abs(v) <= MAX_ABS_ROLL_DEG, "PICTURE_HEAD_TILT", "head roll %s deg; limit +/-%.0f" % (n.get("roll_deg"), MAX_ABS_ROLL_DEG)),
           ("yaw", lambda v: abs(v) <= MAX_ABS_YAW, "PICTURE_HEAD_TURN", "head yaw %s; limit +/-%.2f" % (n.get("yaw"), MAX_ABS_YAW)),
           ("smile", lambda v: v <= MAX_SMILE, "PICTURE_SMILE", "smile %s > %.2f; neutral mouth needed" % (n.get("smile"), MAX_SMILE)),
           ("jaw_open", lambda v: v <= MAX_JAW_OPEN, "PICTURE_MOUTH_OPEN", "jawOpen %s > %.2f" % (n.get("jaw_open"), MAX_JAW_OPEN)),
           ("inner_gap_pct", lambda v: v <= MAX_INNER_GAP_PCT, "PICTURE_TEETH", "lip gap %s%% of face; teeth showing (limit %.1f)" % (n.get("inner_gap_pct"), MAX_INNER_GAP_PCT)),
           ("sharp", lambda v: v >= MIN_SHARP, "PICTURE_SOFT", "sharpness %s < %.0f" % (n.get("sharp"), MIN_SHARP))]
    for k, ok, code, text in chk:
        v = f(k)
        if v is None:
            r.append(("PICTURE_UNMEASURED", "%s was not measured" % k))
        elif not ok(v):
            r.append((code, text))
    return ("PASS" if not r else "FAIL"), r


def receipt_path(path):
    return path + RECEIPT_SUFFIX


def gate_picture(path, measure=None, steps=None):
    """Measure + judge + write the receipt (PASS or FAIL). Returns the receipt.
    A measuring failure raises PictureRefused and writes nothing."""
    n = (measure or measure_picture)(path)
    verdict, reasons = judge_picture(n)
    rec = {"tool": TOOL_NAME, "image": os.path.basename(path), "sha256": sha256_file(path),
           "verdict": verdict, "numbers": n, "reasons": reasons, "steps": steps or [],
           "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    with open(receipt_path(path), "w") as fh:
        json.dump(rec, fh, indent=1)
    return rec


def receipt_refusal(path):
    """None when a PASS receipt exists for this exact file (sha256) and its own
    numbers still judge PASS; else (code, text). This is what the dispatcher calls."""
    if not isinstance(path, str) or not os.path.isfile(path):
        return ("LIPSYNC_PICTURE_MISSING", "no local lip-sync source picture to check: %r" % (path,))
    try:
        with open(receipt_path(path)) as fh:
            rec = json.load(fh)
    except (OSError, ValueError):
        return ("LIPSYNC_PICTURE_NO_RECEIPT", "no gate receipt for %s; run picture_gate.gate_picture / fix_picture first" % path)
    if not isinstance(rec, dict) or rec.get("sha256") != sha256_file(path):
        return ("LIPSYNC_PICTURE_RECEIPT_STALE", "receipt does not match this file's sha256; re-measure")
    if rec.get("verdict") != "PASS" or judge_picture(rec.get("numbers") or {})[0] != "PASS":
        return ("LIPSYNC_PICTURE_FAILED", "picture gate verdict is %s: %s" % (rec.get("verdict"), rec.get("reasons")))
    return None


def crop_to_face(path, out, numbers, target_pct=CROP_TARGET_PCT):
    """Free local 9:16 crop centred on the face so it fills target_pct of height."""
    import cv2
    img = cv2.imread(path)
    H, W = img.shape[:2]
    win_h = min(H, int(H * numbers["face_h_pct"] / target_pct))
    win_w = min(W, int(win_h * 9 / 16))
    win_h = min(win_h, int(win_w * 16 / 9))
    y0 = int(min(max(numbers["face_cy"] - win_h / 2, 0), H - win_h))
    x0 = int(min(max(numbers["face_cx"] - win_w / 2, 0), W - win_w))
    cv2.imwrite(out, img[y0:y0 + win_h, x0:x0 + win_w])
    return out


_CROPPABLE = {"PICTURE_FACE_SMALL"}


def read_receipt(path):
    """The receipt dict for this file, or None."""
    try:
        with open(receipt_path(path)) as fh:
            rec = json.load(fh)
    except (OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) else None


def fix_picture(path, regenerate=None, measure=None, crop=None, dispatch_ctx=None):
    """Gate a picture, fixing it for free first. Returns (final_path, PASS receipt).

    Free: ONE local crop for a small face (MAX_LOCAL_CROPS). Paid: at most
    MAX_REGENERATIONS regenerations for smile / teeth / tilt, then refuse.
    regenerate(path, prompt) -> new image path. Default (regenerate=None with
    dispatch_ctx given) is kie_dispatch.make_picture_regenerator(**dispatch_ctx):
    gpt-image-2 image-to-image from the 3D character through kie_dispatch, so it
    reserves against the author's cap and the ledger. No regenerate and no
    dispatch_ctx = no paid fix. Raises PictureRefused with the last FAIL receipt."""
    if regenerate is None and dispatch_ctx:
        import sys
        core = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if core not in sys.path:
            sys.path.insert(0, core)
        from kie_dispatch import make_picture_regenerator
        regenerate = make_picture_regenerator(**dispatch_ctx)
    crop, steps, regens, crops = crop or crop_to_face, [], 0, 0
    cur = path
    while True:
        rec = gate_picture(cur, measure, steps)
        if rec["verdict"] == "PASS":
            return cur, rec
        codes = {c for c, _ in rec["reasons"]}
        n = rec["numbers"]
        if codes & _CROPPABLE and n.get("faces") == 1 and crops < MAX_LOCAL_CROPS:   # free local crop
            crops += 1
            base, ext = os.path.splitext(cur)
            cur = crop(cur, base + "-crop" + ext, n)
            steps.append("local crop")
            continue
        if regenerate is not None and regens < MAX_REGENERATIONS and n.get("faces") == 1:
            regens += 1
            cur = regenerate(cur, REGEN_PROMPT)
            crops = 0                       # a fresh picture may take its own free crop
            steps.append("regenerated %d/%d (paid, counts against cap)" % (regens, MAX_REGENERATIONS))
            continue
        raise PictureRefused(rec["reasons"], cur)
