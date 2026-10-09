#!/usr/bin/env python3
"""Deterministic book-shot fixtures, generated locally (no network, no spend).

Fixtures are GENERATED, never committed as images: the packaging check counts
media binaries in the skill folder, so shipping PNGs would fail clean-install
discovery. Every caller builds them into a temp dir instead.

  cover        a correct front cover (art + title + author), upright
  cover_flip   the HORIZONTAL MIRROR of the cover (the defect the checker hunts)
  back_cover   unrelated art (a back cover / invented cover)
  leaf frames  a synthetic leaf moving left (right-to-left) and right

All shapes are seeded, so two runs on the same machine produce byte-equal
frames.
"""
from __future__ import annotations

import os

TITLE = "THE SUNDAY COOKBOOK"
AUTHOR = "MARIA HALL"
COVER_W, COVER_H = 600, 420
FRAME_W, FRAME_H = 640, 480

def make_cover(cv2, np):
    rng = np.random.default_rng(7)
    cover = np.full((COVER_H, COVER_W, 3), 240, np.uint8)
    cv2.circle(cover, (150, 300), 70, (60, 90, 200), -1)
    cv2.rectangle(cover, (250, 240), (470, 360), (30, 160, 60), -1)
    cv2.line(cover, (40, 60), (560, 60), (0, 0, 0), 4)
    cv2.putText(cover, TITLE, (40, 140), cv2.FONT_HERSHEY_SIMPLEX, 1.2,
                (20, 20, 20), 3, cv2.LINE_AA)
    cv2.putText(cover, AUTHOR, (40, 400), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                (20, 20, 20), 2, cv2.LINE_AA)
    for _ in range(30):
        x, y = int(rng.integers(0, COVER_W)), int(rng.integers(0, COVER_H))
        cv2.circle(cover, (x, y), int(rng.integers(3, 9)), (10, 10, 10), -1)
    return cover

def make_back_cover(cv2, np):
    back = np.full((COVER_H, COVER_W, 3), 250, np.uint8)
    cv2.putText(back, "PRAISE FOR THE BOOK", (40, 120), cv2.FONT_HERSHEY_SIMPLEX,
                0.9, (40, 40, 40), 2, cv2.LINE_AA)
    cv2.putText(back, "A STORY ABOUT DINNER", (40, 200), cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (60, 60, 60), 2, cv2.LINE_AA)
    cv2.rectangle(back, (60, 260), (540, 380), (200, 200, 200), -1)
    return back

def paste_into_frame(cv2, np, cover):
    """The cover upright in a plain frame, front facing the camera."""
    frame = np.full((FRAME_H, FRAME_W, 3), 230, np.uint8)
    frame[30:30 + COVER_H, 20:20 + COVER_W] = cover
    return frame

def leaf_frames(cv2, np, direction="left", count=8, w=FRAME_W, h=FRAME_H):
    """A plain leaf sliding across an open book's right half toward the left.

    direction="left"  the leaf travels from the right half to the left half
                      (correct for a left-to-right book)
    direction="right" the same leaf travels the wrong way.
    """
    frames = []
    y0, y1 = int(h * 0.25), int(h * 0.75)
    leaf_w = int(w * 0.22)
    for i in range(count):
        f = np.full((h, w, 3), 245, np.uint8)
        f[:, int(w * 0.5):int(w * 0.5) + 2] = (120, 120, 120)   # gutter
        t = i / float(count - 1)
        if direction == "left":
            x = int((w * 0.90 - t * (w * 0.80)))               # right -> left
        else:
            x = int((w * 0.10 + t * (w * 0.80)))               # left -> right
        cv2.rectangle(f, (x, y0), (x - leaf_w, y1), (70, 70, 70), -1)
        frames.append(f)
    return frames

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
    cover = make_cover(cv2, np)
    imgs = {
        "cover": cover,
        "cover_flip": cv2.flip(cover, 1),
        "back_cover": make_back_cover(cv2, np),
        "front_frame": paste_into_frame(cv2, np, cover),
        "flip_frame": cv2.flip(paste_into_frame(cv2, np, cover), 1),
        "back_frame": paste_into_frame(cv2, np, make_back_cover(cv2, np)),
    }
    paths = write_pngs(tmpdir, cv2, imgs)
    return {"paths": paths, "images": imgs,
            "leaf_left": leaf_frames(cv2, np, "left"),
            "leaf_right": leaf_frames(cv2, np, "right"),
            "title": TITLE, "author": AUTHOR}
