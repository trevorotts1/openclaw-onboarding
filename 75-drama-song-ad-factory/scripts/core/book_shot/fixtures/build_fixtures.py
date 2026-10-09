#!/usr/bin/env python3
"""Deterministic book-shot fixtures, generated locally (no network, no spend).

Fixtures are GENERATED, never committed as images: the packaging check counts
media binaries in the skill folder, so shipping PNGs would fail clean-install
discovery. Every caller builds them into a temp dir instead.

  cover        a correct front cover (art + title + author), upright
  cover_flip   the HORIZONTAL MIRROR of the cover (the defect the checker hunts)
  back_cover   unrelated art (a back cover / invented cover)
  leaf frames  a synthetic leaf moving left (right-to-left) and right
  pages frames a PRINTED page (dense serif lines, paragraph blocks, page
               numbers) and a WHITE page (the defect U11's BOOK_BLANK_PAGES
               hunts). Both are the same size and paper colour, so the only
               difference the checker can see is the printed ink.

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

def pages_frame(cv2, np, kind="printed", w=FRAME_W, h=FRAME_H):
    """An OPEN book's double page: "printed" (dense type) or "white" (blank).

    U11's BOOK_BLANK_PAGES hunts the empty page. Both kinds share the same
    paper colour and the same gutter, so the only signal the checker may use
    is the printed ink itself.
    """
    f = np.full((h, w, 3), 245, np.uint8)
    f[:, int(w * 0.5):int(w * 0.5) + 2] = (120, 120, 120)        # gutter
    if kind == "white":
        return f
    rng = np.random.default_rng(11)
    # Two columns of dense serif-ish text lines, with paragraph blocks.
    for col_x in (int(w * 0.06), int(w * 0.54)):
        y = int(h * 0.10)
        col_w = int(w * 0.38)
        while y < int(h * 0.92):
            n_lines = int(rng.integers(3, 7))                    # a paragraph
            for _ in range(n_lines):
                if y >= int(h * 0.90):
                    break
                cv2.line(f, (col_x, y), (col_x + col_w, y), (25, 25, 25), 2)
                y += 9
            y += 12                                              # paragraph gap
    # Page numbers at the foot of each page.
    cv2.putText(f, "142", (int(w * 0.30), int(h * 0.95)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (30, 30, 30), 1, cv2.LINE_AA)
    cv2.putText(f, "143", (int(w * 0.78), int(h * 0.95)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (30, 30, 30), 1, cv2.LINE_AA)
    return f

def open_book_frames(cv2, np, printed=True, count=6, w=FRAME_W, h=FRAME_H):
    """FU-U11 page fixtures (onboarding half): an OPEN book, printed or blank.

    printed=True   two page regions filled with dense printed text lines
    printed=False  the same two regions blank white (the FAIL control)

    Same geometry in both (gutter, page edges, shading), so the ONLY thing
    that differs between the pair is ink: a page check that cannot sort these
    two is broken. Kept as a second, independent fixture family, so the grid
    check is proven on generator styles it was not calibrated against.
    """
    # The page fills the frame: check_pages measures a 8x6 grid over the WHOLE
    # frame, so a printed fixture with paper margins outside the type block
    # reads as blank grid cells (a real printed page fills its frame). Both
    # kinds share this geometry -- only the ink differs.
    frames = []
    for i in range(count):
        f = np.full((h, w, 3), 235, np.uint8)
        cv2.rectangle(f, (2, 2), (w - 3, h - 3), (250, 250, 250), -1)
        f[:, int(w * 0.5) - 1:int(w * 0.5) + 1] = (150, 150, 150)   # gutter
        for x0, y0, x1, y1 in ((0.04, 0.05, 0.48, 0.95),
                               (0.52, 0.05, 0.96, 0.95)):
            px0, py0 = int(x0 * w), int(y0 * h)
            px1, py1 = int(x1 * w), int(y1 * h)
            if printed:
                rows = 24
                for r in range(rows):
                    y = py0 + int((py1 - py0) * (r + 0.5) / rows)
                    span = (px1 - px0) - (2 * (12 if r == rows - 1 else 0))
                    cv2.rectangle(f, (px0, y), (px0 + span, y + 3),
                                  (25, 25, 25), -1)
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
        "pages_printed": pages_frame(cv2, np, "printed"),
        "pages_white": pages_frame(cv2, np, "white"),
    }
    paths = write_pngs(tmpdir, cv2, imgs)
    return {"paths": paths, "images": imgs,
            "leaf_left": leaf_frames(cv2, np, "left"),
            "leaf_right": leaf_frames(cv2, np, "right"),
            "printed_page": imgs["pages_printed"],
            "white_page": imgs["pages_white"],
            "title": TITLE, "author": AUTHOR}
