#!/usr/bin/env python3
"""Deterministic prop-facing fixtures, generated locally (no network, no spend).

Fixtures are GENERATED, never committed as images: the packaging check counts
media binaries in the skill folder, so shipping PNGs would fail clean-install
discovery. Every caller builds them into a temp dir instead.

  good_frame    person facing camera, phone back to camera, screen hidden.
                The prop's reading side is toward the user (the person),
                camera sees the back. PASS control for PROP_FACES_CAMERA.
  bad_frame     the same beat, phone screen facing camera, text readable.
                The DEFECT Section 3P hunts. FAIL control.
  insert_good   over-the-shoulder insert from the user's side: the screen
                fills the lower frame and the words read exactly. PASS control
                for INSERT_WRONG_SIDE.
  insert_wrong_side    shot from behind the prop: the camera sees the back
                panel only, so no readable words exist. FAIL with
                INSERT_WRONG_SIDE (the insert was taken from the wrong side).
  insert_wrong_words   from the user's side, but the wrong words (reversed).
                FAIL with PICTURE_TEXT_WRONG.

Geometry is shared between good/bad pairs so the ONLY signal the checker can
see is the prop's facing itself. All shapes are seeded, so two runs on the
same machine produce byte-equal frames.
"""
from __future__ import annotations

import os

FACE_W, FACE_H = 640, 480
WORD = "BALANCE 14.82"
WORD_ALT = "BALANCE 83.77"

_PALE = (230, 230, 230)
_BACK = (60, 60, 60)
_SCREEN = (255, 255, 255)
_INK = (20, 20, 20)


def _font(cv2, img, text, org, scale=0.6, color=_INK, thick=2):
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color,
                thick, cv2.LINE_AA)


def person_frame(cv2, np, screen_to_camera, word=WORD):
    """Person facing the camera holding a phone.

    screen_to_camera=True  the DEFECT (screen readable from this side)
    screen_to_camera=False the rule (phone back to camera, screen toward user)
    """
    f = np.full((FACE_H, FACE_W, 3), _PALE, np.uint8)
    # Person silhouette: head circle + torso, face toward camera.
    cv2.circle(f, (FACE_W // 2, 120), 60, (120, 90, 70), -1)
    cv2.rectangle(f, (FACE_W // 2 - 90, 180), (FACE_W // 2 + 90, 420),
                  (40, 60, 120), -1)
    # Phone in the lower centre. Reading side either faces camera or not.
    px0, py0, px1, py1 = FACE_W // 2 - 60, 250, FACE_W // 2 + 60, 400
    if screen_to_camera:
        cv2.rectangle(f, (px0, py0), (px1, py1), _SCREEN, -1)
        cv2.rectangle(f, (px0, py0), (px1, py1), _BACK, 3)
        _font(cv2, f, word, (px0 + 10, py0 + 60), scale=0.55)
        # A clear readable number band the checker can measure OCR-style.
        cv2.rectangle(f, (px0 + 10, py0 + 80), (px1 - 10, py0 + 120),
                      _INK, -1)
    else:
        # Back of the phone: plain case, no readable words on this side.
        cv2.rectangle(f, (px0, py0), (px1, py1), _BACK, -1)
        cv2.rectangle(f, (px0 + 18, py0 + 18), (px1 - 18, py1 - 18),
                      (90, 90, 90), 2)
    return f


def insert_frame(cv2, np, from_user_side, words_wrong=False, word=WORD):
    """Over-the-shoulder insert: the screen fills the lower frame.

    from_user_side=True   correct: words upright to the user, readable.
    from_user_side=False  wrong side: the camera sees the back panel only.
    words_wrong=True      from the user's side but the wrong words (reversed).
    """
    f = np.full((FACE_H, FACE_W, 3), _PALE, np.uint8)
    # Shoulder mass in the upper left (the user, seen from behind).
    cv2.rectangle(f, (0, 0), (int(FACE_W * 0.35), int(FACE_H * 0.45)),
                  (40, 60, 120), -1)
    # Card occupying the lower frame.
    sx0, sy0, sx1, sy1 = 60, 240, FACE_W - 60, 440
    if not from_user_side:
        # The BACK of the device: uniform dark case, no pale screen.
        cv2.rectangle(f, (sx0, sy0), (sx1, sy1), _BACK, -1)
        cv2.rectangle(f, (sx0 + 20, sy0 + 20), (sx1 - 20, sy1 - 20),
                      (90, 90, 90), 2)
        return f
    cv2.rectangle(f, (sx0, sy0), (sx1, sy1), _SCREEN, -1)
    cv2.rectangle(f, (sx0, sy0), (sx1, sy1), _BACK, 3)
    if words_wrong:
        # Same ink, but horizontally flipped: reads wrong from this side.
        _font(cv2, f, word[::-1], (sx0 + 30, sy0 + 90), scale=1.0, thick=3)
        # A grey band where the words would be: dim, unreadable from here.
        cv2.rectangle(f, (sx0 + 30, sy0 + 110), (sx1 - 30, sy0 + 160),
                      (120, 120, 120), -1)
    else:
        _font(cv2, f, word, (sx0 + 30, sy0 + 90), scale=1.0, thick=3)
        cv2.rectangle(f, (sx0 + 30, sy0 + 110), (sx1 - 30, sy0 + 160),
                      _INK, -1)
    return f


def clip_frames(cv2, np, good, count=8):
    """A clip starting on one still; good=True holds facing, False flips it.

    good=True   every frame is the phone-back frame (facing holds).
    good=False  the prop turns toward the lens mid-clip: the early frames
                show the back, the late frames show the screen. This is
                the PROP_TURNED_TO_CAMERA defect (F4).
    """
    back = person_frame(cv2, np, screen_to_camera=False)
    if good:
        return [back.copy() for _ in range(count)]
    screen = person_frame(cv2, np, screen_to_camera=True)
    half = max(1, count // 2)
    return [back.copy() for _ in range(half)] + \
        [screen.copy() for _ in range(count - half)]


def write_pngs(tmpdir, cv2, images):
    out = {}
    for name, img in images.items():
        p = os.path.join(tmpdir, name + ".png")
        cv2.imwrite(p, img)
        out[name] = p
    return out


def build(tmpdir):
    """Write every fixture into tmpdir; returns paths + the numpy frames."""
    import cv2
    import numpy as np
    imgs = {
        "good_frame": person_frame(cv2, np, screen_to_camera=False),
        "bad_frame": person_frame(cv2, np, screen_to_camera=True),
        "insert_good": insert_frame(cv2, np, from_user_side=True),
        "insert_wrong_side": insert_frame(cv2, np, from_user_side=False),
        "insert_wrong_words": insert_frame(cv2, np, from_user_side=True,
                                           words_wrong=True),
    }
    paths = write_pngs(tmpdir, cv2, imgs)
    return {"paths": paths, "images": imgs,
            "word": WORD, "word_alt": WORD_ALT,
            "frames_good": clip_frames(cv2, np, good=True),
            "frames_turn": clip_frames(cv2, np, good=False)}
