#!/usr/bin/env python3
"""book_shot.py: the book orientation contract for book campaigns (plan FU-U10).

Root cause this closes: no book shape or motion rule existed anywhere. Every
compiled clip prompt appended "[MOTION] The subject moves naturally through
the frame; limbs, head and camera stay in gentle continuous motion." -- for a
book that instruction is wrong (a moving camera plus object rotation is what
produces mirrored covers and invented covers). Nothing measured the cover
against the client's cover file and nothing measured page-turn direction.

Two seams, both stdlib + the cv2/numpy already declared in PREREQS
(python-mediapipe):

  prompt_blocks(spec, action)  the exact contract wording, fixed blocks in a
                               fixed order (subject, action, camera, light,
                               constraints), no model-chosen wording.
  check_clip(clip, spec)       measured verdicts: cover match + mirror
                               detection (ORB + RANSAC homography inliers,
                               compared against the HORIZONTAL MIRROR of the
                               real cover), title OCR in reading order, and
                               Farneback optical-flow direction over the
                               planned open/flip window. PASS / FAIL /
                               UNAVAILABLE -- UNAVAILABLE never passes.

Pixel work runs inside load_governor (same rule as every other heavy local
job); a governor timeout is UNAVAILABLE, never a pass. Left/right are always
from the CAMERA's view. Right-to-left languages mirror the expectations BY
RULE from brief.language, never by what a model happened to produce.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

_gcore = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _gcore not in sys.path:
    sys.path.insert(0, _gcore)
import load_governor as _LG  # noqa: E402
TOOL_NAME = "book_shot"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.book-shot/v1"

# ---------------------------------------------------------------- contract --

BOOK_ORIENTATION_CONTRACT = (
    "BOOK ORIENTATION CONTRACT (left/right always from the CAMERA's view)\n"
    "1. Front cover faces the camera when closed. The back cover is never "
    "shown unless the shot plan says so.\n"
    "2. Left-to-right languages (English default; brief.language): spine on "
    "the LEFT edge, fore-edge on the RIGHT. Right-to-left languages: "
    "everything mirrored by rule, chosen from brief.language, never by the "
    "model.\n"
    "3. Opening: the front cover hinges on the left spine; its right edge "
    "lifts first and swings LEFT (opens right-to-left as the viewer sees "
    "it).\n"
    "4. Page turns: each page lifts from the RIGHT stack, arcs LEFT, settles "
    "on the LEFT stack.\n"
    "5. Never mirrored: cover art, title and author read left-to-right, "
    "upright, exactly as the supplied cover file.\n"
    "6. Camera: static, or one slow push-in; no orbit, no rotation of the "
    "book over 15 degrees, one continuous shot, no cut.\n"
    "7. Source of truth for the cover: the client's cover file (sha256 from "
    "intake_book). The first frame of every book clip is an image-to-video "
    "start frame made FROM that file (composited or image-to-image), never a "
    "cover the model invents."
)

#: Fixed prompt blocks (plan section 4). Wording is never model-chosen.
ORIENTATION = (
    "Left and right are from the camera's view. A closed hardcover book, "
    "front cover facing the camera, upright. The spine is on the left edge "
    "of the frame; the fore-edge is on the right. Preserve the cover exactly "
    "as in the reference image: same art, same title and author lettering, "
    "reading left to right, not mirrored."
)
ACTION_OPEN = (
    "The right edge of the front cover lifts first and swings leftward "
    "around the spine; the book opens from right to left and comes to rest "
    "open, both pages facing the camera."
)
ACTION_FLIP = (
    "One page at a time lifts from the right-hand stack, arcs leftward, and "
    "settles on the left-hand stack; slow, even page turns."
)
CAMERA = "Static camera, one continuous shot."
CAMERA_SHOT_TAG = "[Static shot]"
CAMERA_PLAIN = "Static camera."
CONSTRAINTS = (
    "No mirroring, no reversed lettering, no back cover, no duplicated "
    "covers, no extra books, no scene cut."
)

#: Reasoning block the video model sees after the fixed blocks (light, mood).
DEFAULT_LIGHT = "Soft even key light on the cover; no flare, no blown highlights."

#: Right-to-left scripts: the whole contract mirrors BY RULE.
RTL_LANGUAGES = frozenset({"ar", "he", "fa", "ur", "yi", "dv", "ps", "sd"})

#: H3 / Hailuo image-to-video: bracket commands are UNVERIFIED there, so the
#: plan asks for the bracket tag AND the plain-words camera line.
BRACKET_TAG_MODELS = ("minimax-h3", "hailuo")

#: Prompt blocks in the order the builder joins them.
BLOCK_ORDER = ("subject", "action", "camera", "light", "constraints")

# ------------------------------------------------------------ reason codes --

BOOK_MIRRORED = "BOOK_MIRRORED"
BOOK_COVER_NOT_FRONT = "BOOK_COVER_NOT_FRONT"
BOOK_SPINE_WRONG_SIDE = "BOOK_SPINE_WRONG_SIDE"
BOOK_WRONG_DIRECTION = "BOOK_WRONG_DIRECTION"
BOOK_NO_MOTION = "BOOK_NO_MOTION"
BOOK_TITLE_WRONG = "BOOK_TITLE_WRONG"
BOOK_OCR_UNAVAILABLE = "BOOK_OCR_UNAVAILABLE"
BOOK_BLANK_PAGES = "BOOK_BLANK_PAGES"
BOOK_PAGES_UNAVAILABLE = "BOOK_PAGES_UNAVAILABLE"
BOOK_EXCERPT_OVERLAY_DEFERRED = "BOOK_EXCERPT_OVERLAY_DEFERRED"
BOOK_CALIBRATION_FAILED = "BOOK_CALIBRATION_FAILED"
BOOK_INPUT_INVALID = "BOOK_INPUT_INVALID"
BOOK_FRAMES_UNAVAILABLE = "BOOK_FRAMES_UNAVAILABLE"

#: ORB + RANSAC inlier floor. Measured on the shipped fixtures: an upright
#: cover against itself scores 1000+ inliers; a perspective-warped cover 700+;
#: the same cover against unrelated art (back cover) under 100. The floor sits
#: far from both, so the control must fail when the check is broken.
COVER_INLIER_MIN = 120
#: Loose ceiling on the matching distance for the ratio-free crossCheck match.
#: Kept in one place: both the true and the mirror comparison use it.
ORB_FEATURES = 2000

#: Farneback defaults (dense optical flow over the booked region).
FB_PARAMS = dict(pyr_scale=0.5, levels=3, winsize=15, iterations=3,
                 poly_n=5, poly_sigma=1.2, flags=0)
#: Below this mean flow magnitude (pixels/frame) nothing moved.
MOTION_EPS = 0.05
#: Fraction of the frame's height/width that must actually move to count.
MOTION_PIXEL_FRAC = 0.0005

class BookShotError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code

def _cv2():
    """cv2 is declared in PREREQS python-mediapipe; a missing one is a loud
    UNAVAILABLE at the caller, never a silent stub pass."""
    try:
        import cv2  # noqa: PLC0415
        return cv2
    except Exception as exc:  # noqa: BLE001
        raise BookShotError(BOOK_FRAMES_UNAVAILABLE,
                            "cv2 unavailable: %s" % exc) from exc

def _np():
    try:
        import numpy as _n  # noqa: PLC0415
        return _n
    except Exception as exc:  # noqa: BLE001
        raise BookShotError(BOOK_FRAMES_UNAVAILABLE,
                            "numpy unavailable: %s" % exc) from exc

# ------------------------------------------------------------- direction ----

def reading_direction(language):
    """'rtl' for a right-to-left brief.language, else 'ltr' (English default).

    The direction is chosen from the brief, never from what a model produced.
    """
    lang = (language or "en").strip().lower().split("-")[0].split("_")[0]
    return "rtl" if lang in RTL_LANGUAGES else "ltr"

# ------------------------------------------------------------- prompting ----

def _spec_str(spec, key, default=None):
    v = (spec or {}).get(key)
    return v.strip() if isinstance(v, str) and v.strip() else default

def prompt_blocks(spec, action):
    """The fixed blocks, in order: subject, action, camera, light, constraints.

    ``action`` is "open" or "flip" (the shot plan's words for this clip).
    ``spec`` carries the subject line, the light line, the language and the
    model. Nothing here is generated by a model; the caller joins them.
    """
    if action not in ("open", "flip"):
        raise BookShotError(BOOK_INPUT_INVALID,
                            "action must be 'open' or 'flip', got %r" % (action,))
    spec = spec or {}
    rtl = reading_direction(spec.get("language")) == "rtl"
    subject = _spec_str(spec, "subject") or (
        "The client's hardcover book on a plain surface, cover toward camera.")
    orientation = ORIENTATION
    cons = CONSTRAINTS
    if rtl:
        # Rule 2: mirrored BY RULE for a right-to-left brief.
        orientation = orientation.replace(
            "The spine is on the left edge of the frame; the fore-edge is on "
            "the right.",
            "The spine is on the right edge of the frame; the fore-edge is on "
            "the left (right-to-left book).")
        orientation = orientation.replace(
            "reading left to right, not mirrored",
            "reading right to left, not mirrored")
        cons = cons.replace("No mirroring, no reversed lettering",
                            "No mirroring of the cover art, no reversed lettering")
    action_text = {"open": ACTION_OPEN, "flip": ACTION_FLIP}[action]
    if rtl:
        action_text = {
            "open": ("The left edge of the front cover lifts first and swings "
                     "rightward around the spine; the book opens from left to "
                     "right and comes to rest open, both pages facing the "
                     "camera."),
            "flip": ("One page at a time lifts from the left-hand stack, arcs "
                     "rightward, and settles on the right-hand stack; slow, "
                     "even page turns."),
        }[action]
    camera = CAMERA
    if any(t in str(spec.get("model", "")).lower() for t in BRACKET_TAG_MODELS):
        camera = CAMERA_SHOT_TAG + " " + CAMERA_PLAIN + " " + CAMERA
    return {
        "subject": "%s %s" % (subject, orientation),
        "action": "Start: closed cover. End: %s" % action_text,
        "camera": camera,
        "light": _spec_str(spec, "light") or DEFAULT_LIGHT,
        "constraints": cons,
    }

def build_prompt(spec, action, blocks=None):
    """Join the fixed blocks in order. One string, no model-chosen wording."""
    b = blocks if isinstance(blocks, dict) else prompt_blocks(spec, action)
    missing = [k for k in BLOCK_ORDER if not b.get(k)]
    if missing:
        raise BookShotError(BOOK_INPUT_INVALID,
                            "blocks missing: %s" % ", ".join(missing))
    return " ".join(b[k] for k in BLOCK_ORDER)

def image_model_blocks(spec):
    """Keyframe / start frame: ORIENTATION plus CONSTRAINTS only.

    The plan's image-model wording ("front cover facing the camera, spine on
    the left") is already inside ORIENTATION, so the block is reused verbatim
    rather than restated in a second dialect the two could drift apart on.
    Right-to-left briefs mirror it by rule like the video blocks do.
    """
    rtl = reading_direction((spec or {}).get("language")) == "rtl"
    orientation = ORIENTATION if not rtl else ORIENTATION.replace(
        "spine is on the left edge", "spine is on the right edge")
    return {"orientation": orientation, "constraints": CONSTRAINTS}

# ------------------------------------------------------------ cover match ---

def _orb_match(cover_bgr, frame_bgr):
    """(inliers, homography) of cover -> frame. (0, None) when no match."""
    cv2 = _cv2()
    np = _np()
    orb = cv2.ORB_create(ORB_FEATURES)
    kpc, dc = orb.detectAndCompute(cv2.cvtColor(cover_bgr, cv2.COLOR_BGR2GRAY), None)
    kpf, df = orb.detectAndCompute(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY), None)
    if dc is None or df is None or len(kpc) < 8 or len(kpf) < 8:
        return 0, None
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    m = bf.match(dc, df)
    if len(m) < 8:
        return 0, None
    src = np.float32([kpc[x.queryIdx].pt for x in m]).reshape(-1, 1, 2)
    dst = np.float32([kpf[x.trainIdx].pt for x in m]).reshape(-1, 1, 2)
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if H is None or mask is None:
        return 0, None
    return int(mask.sum()), H

def detect_cover(frame_bgr, cover_path):
    """True-vs-mirror cover match. Returns a measurement dict.

    ``mirror_score > true_score`` means the frame shows a mirrored cover;
    the homography's sign tells which side the spine is on.
    """
    cv2 = _cv2()
    cover = cv2.imread(cover_path)
    if cover is None:
        raise BookShotError(BOOK_INPUT_INVALID, "cover unreadable: %s" % cover_path)
    mirrored = cv2.flip(cover, 1)
    true_score, TRUE_H = _orb_match(cover, frame_bgr)
    mirror_score, _ = _orb_match(mirrored, frame_bgr)
    spine_side = None
    if TRUE_H is not None:
        det = float(_np().linalg.det(TRUE_H[:2, :2]))
        spine_side = "left" if det > 0 else "right"
    return {"true_score": true_score, "mirror_score": mirror_score,
            "spine_side": spine_side,
            "cover_hits": true_score >= COVER_INLIER_MIN,
            "mirror_hits": mirror_score >= COVER_INLIER_MIN}

# ------------------------------------------------------------- direction ----

def optical_flow_direction(frames, region=None, expect="ltr"):
    """Farneback flow inside the book region over the clip's window.

    Returns {mean_dx, moved, crossed, direction}. For an ltr book the moving
    leaf must flow right-to-left (mean_dx < 0) AND cross the right half to the
    left half; an rtl book mirrors BY RULE.
    """
    cv2 = _cv2()
    np = _np()
    if not isinstance(frames, (list, tuple)) or len(frames) < 3:
        raise BookShotError(BOOK_INPUT_INVALID, "need at least 3 frames")
    h, w = frames[0].shape[:2]
    x0, y0, rw, rh = region if region else (0, 0, w, h)
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    rw, rh = min(int(rw), w - x0), min(int(rh), h - y0)
    gray = [cv2.cvtColor(f[y0:y0 + rh, x0:x0 + rw], cv2.COLOR_BGR2GRAY)
            for f in frames]
    dxs, cents = [], []
    for a, b in zip(gray, gray[1:]):
        flow = cv2.calcOpticalFlowFarneback(a, b, None, **FB_PARAMS)
        fx = flow[..., 0]
        dxs.append(float(fx.mean()))
        mag = np.sqrt(fx ** 2 + flow[..., 1] ** 2)
        strong = mag > 0.5
        if strong.sum() < max(4, int(MOTION_PIXEL_FRAC * rw * rh)):
            continue
        xs = np.nonzero(strong)[1]
        cents.append(float(xs.mean()) / max(1, rw))
    mean_dx = sum(dxs) / len(dxs) if dxs else 0.0
    moved = bool(dxs) and abs(mean_dx) > MOTION_EPS
    crossed = False
    if len(cents) >= 2:
        start, end = cents[0], cents[-1]
        crossed = (start > 0.5 and end < 0.5) if expect == "ltr" \
            else (start < 0.5 and end > 0.5)
    direction = "unknown"
    if moved:
        direction = "ltr" if mean_dx < 0 else "rtl"
    return {"mean_dx": round(mean_dx, 4), "moved": moved, "crossed": crossed,
            "direction": direction, "frames": len(frames),
            "window": [x0, y0, rw, rh]}

# ------------------------------------------------------------------- OCR ----

OCR_ENGINE = "tesseract"

def ocr_text(image_path, engine=None):
    """Title OCR. Missing engine raises BOOK_OCR_UNAVAILABLE (never a pass).

    ``engine`` defaults to the module-level OCR_ENGINE at CALL time, so a
    caller that swaps the engine (or proves the missing-engine path) is
    respected.
    """
    engine = engine if isinstance(engine, str) and engine else OCR_ENGINE
    if shutil.which(engine) is None:
        raise BookShotError(BOOK_OCR_UNAVAILABLE,
                            "%s not installed (PREREQS ocr-engine)" % engine)
    try:
        r = subprocess.run([engine, str(image_path), "stdout"],
                           capture_output=True, text=True, timeout=60,
                           check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BookShotError(BOOK_OCR_UNAVAILABLE, "tesseract failed: %s" % exc) from exc
    if r.returncode != 0:
        raise BookShotError(BOOK_OCR_UNAVAILABLE,
                            "tesseract rc=%d: %s" % (r.returncode, r.stderr.strip()[:160]))
    return r.stdout

def _words(text):
    return re.findall(r"[A-Za-z0-9']+", (text or "").lower())

def title_reads_correctly(ocr_text, title):
    """Title words present, in reading order (left to right)."""
    want = _words(title)
    got = _words(ocr_text)
    if not want:
        return False
    i = 0
    for w in got:
        if i < len(want) and w == want[i]:
            i += 1
    return i == len(want)

# ----------------------------------------------------------------- gate -----

def _read_clip_frames(clip, max_frames=48):
    """Decode a clip to frames with cv2 (light) inside the load governor."""
    cv2 = _cv2()
    cap = cv2.VideoCapture(str(clip))
    if not cap.isOpened():
        return []
    frames = []
    try:
        while len(frames) < max_frames:
            ok, f = cap.read()
            if not ok:
                break
            frames.append(f)
    finally:
        cap.release()
    return frames

def _verdict(v, reason, checks, detail="", calibrated=None):
    return {"schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION, "verdict": v, "reason_code": reason,
            "checks": checks, "calibrated": calibrated, "detail": detail}

def check_clip(clip, spec, frames=None, calibrated=None):
    """Measured book-orientation verdict for one clip.

    PASS / FAIL / UNAVAILABLE. UNAVAILABLE never passes: a missing engine, a
    missing governor slot or an unreadable clip can never become PASS.
    """
    spec = spec or {}
    checks = {}
    expect = reading_direction(spec.get("language"))
    front_visible = bool(spec.get("front_cover_visible", True))
    action = spec.get("action", "closed")
    cover_path = spec.get("cover_path")
    try:
        with _LG.heavy_slot("book-shot-frames"):
            if frames is None:
                frames = _read_clip_frames(clip)
    except _LG.HeavyJobTimeout as exc:
        return _verdict("UNAVAILABLE", BOOK_FRAMES_UNAVAILABLE, checks,
                        str(exc), calibrated)
    if not frames:
        return _verdict("UNAVAILABLE", BOOK_FRAMES_UNAVAILABLE, checks,
                        "no frames decoded from %s" % clip, calibrated)

    # 1. cover match + mirror detection on the first frame (and any frame the
    #    plan says shows the closed cover).
    if cover_path:
        try:
            cov = detect_cover(frames[0], cover_path)
        except BookShotError as exc:
            return _verdict("UNAVAILABLE", exc.code, checks, str(exc), calibrated)
        checks["cover"] = cov
        if cov["mirror_score"] > cov["true_score"] and cov["mirror_hits"]:
            return _verdict("FAIL", BOOK_MIRRORED, checks,
                            "mirror inliers %d > true %d"
                            % (cov["mirror_score"], cov["true_score"]), calibrated)
        if cov["true_score"] < COVER_INLIER_MIN and front_visible:
            return _verdict("FAIL", BOOK_COVER_NOT_FRONT, checks,
                            "no front-cover match (%d inliers < %d); the frame "
                            "shows the back cover or an invented cover"
                            % (cov["true_score"], COVER_INLIER_MIN), calibrated)
        if cov["true_score"] >= COVER_INLIER_MIN and cov["spine_side"] == "right" \
                and expect == "ltr" and action == "closed":
            return _verdict("FAIL", BOOK_SPINE_WRONG_SIDE, checks,
                            "homography sign puts the spine on the right for a "
                            "left-to-right book", calibrated)
    # 2. title reads correctly.
    if spec.get("title") and cover_path:
        try:
            import tempfile
            cv2 = _cv2()
            fd, tmp = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            cv2.imwrite(tmp, frames[0])
            text = ocr_text(tmp)
            os.unlink(tmp)
        except BookShotError as exc:
            checks["title"] = {"ocr": "unavailable", "detail": str(exc)}
            if exc.code == BOOK_OCR_UNAVAILABLE:
                return _verdict("UNAVAILABLE", BOOK_OCR_UNAVAILABLE, checks,
                                str(exc), calibrated)
            raise
        ok = title_reads_correctly(text, spec["title"])
        checks["title"] = {"ocr": "ok" if ok else "wrong", "title": spec["title"],
                           "read": " ".join(_words(text))[:120]}
        if not ok:
            return _verdict("FAIL", BOOK_TITLE_WRONG, checks,
                            "OCR did not find the title in reading order: %r"
                            % checks["title"]["read"], calibrated)
    # 3. open / flip direction over the planned window.
    window = spec.get("window")
    win_frames = frames[window[0]:window[1]] if isinstance(window, (list, tuple)) \
        and len(window) == 2 else frames
    if action in ("open", "flip"):
        if len(win_frames) < 3:
            return _verdict("UNAVAILABLE", BOOK_FRAMES_UNAVAILABLE, checks,
                            "the %s window has %d frames; flow needs 3"
                            % (action, len(win_frames)), calibrated)
        flow = optical_flow_direction(win_frames, spec.get("region"), expect)
        checks["direction"] = flow
        if not flow["moved"]:
            return _verdict("FAIL", BOOK_NO_MOTION, checks,
                            "no measurable motion over the %s window" % action,
                            calibrated)
        if (flow["direction"] != expect) or not flow["crossed"]:
            return _verdict("FAIL", BOOK_WRONG_DIRECTION, checks,
                            "mean dx %.4f (%s), crossed=%s; expected %s"
                            % (flow["mean_dx"], flow["direction"],
                               flow["crossed"], expect), calibrated)
    return _verdict("PASS", "BOOK_ORIENTATION_OK", checks, "", calibrated)

# --------------------------------------------------------------- receipt ----

def qc_record(verdict, shot_id, reviewer, calibrated=False, refs=None,
              run_id=""):
    """The qc_gate record for the shots stage (check book_orientation).

    A PASS without calibrated=True is not a valid record: the acceptance rule
    is 'no book clip is accepted without a PASS book_orientation record from a
    CALIBRATED checker'.
    """
    ok = verdict.get("verdict") == "PASS" and bool(calibrated)
    if not calibrated and verdict.get("verdict") == "PASS":
        verdict = dict(verdict, verdict="UNAVAILABLE",
                       reason_code=BOOK_CALIBRATION_FAILED)
    summary = ("book orientation %s: %s (calibrated=%s, checker=%s v%s)"
               % (verdict.get("verdict"), verdict.get("reason_code"),
                  "true" if calibrated else "false", TOOL_NAME, TOOL_VERSION))
    return {
        "schema_version": "1.0.0",
        "check_id": "book-orientation-%s" % shot_id,
        "run_id": run_id or verdict.get("run_id", ""),
        "stage": "shots",
        "check": "book_orientation",
        "verdict": "PASS" if ok else (
            "FAIL" if verdict.get("verdict") == "FAIL" else "UNAVAILABLE"),
        "evidence": {"summary": summary,
                     "refs": list(refs or [])},
        "checker_version": "%s v%s" % (TOOL_NAME, TOOL_VERSION),
        "reviewer": dict(reviewer or {}),
    }

def dumps(d):
    return json.dumps(d, sort_keys=True, ensure_ascii=True)

# ============================================================================
# FU-U11: printed pages, the book plan hash, the plan card rows and the
# excerpt overlay (DATA ONLY).
# ============================================================================

#: The excerpt cap (U11): the client supplies at most three lines, verbatim.
EXCERPT_MAX_LINES = 3

#: FU-U11: the ONE named hook U9 owns. This module never burns a caption and
#: never reads frame text; it names the artifact and hands over data.
EXCERPT_OVERLAY_HOOK = "final_assembler.captions_burn.overlay_excerpt"

#: Grayscale below this counts as ink when measuring a page region.
PAGE_INK_DARK = 128
#: Calibration margin: the printed control must beat the white control by
#: this ink fraction, or the calibration itself is broken.
PAGE_INK_MARGIN = 0.002
#: The left and right page regions of an open book, as frame fractions
#: (x0, y0, x1, y1). The gutter (0.5 w) sits between them on purpose: the
#: gutter line is never counted as printed text on a blank-page control.
PAGE_REGIONS = ((0.10, 0.25, 0.47, 0.75), (0.53, 0.25, 0.90, 0.75))

def pages_block(spec):
    """The PRINTED_PAGES fragment, CONSUMED verbatim from the H3 template.

    U11 authors no prompt wording: the text is the ``PRINTED_PAGES`` fragment
    of references/prompt-templates/models/minimax-h3.json. Returns the text
    when the shot's pages mode is "texture", else None. A missing template
    file is a loud BookShotError naming the path, never invented text.
    """
    if str((spec or {}).get("pages") or "").strip() != "texture":
        return None
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    path = os.path.join(root, "references", "prompt-templates", "models",
                        "minimax-h3.json")
    try:
        with open(path, encoding="utf-8") as fh:
            frag = (json.load(fh).get("fragments") or {})["PRINTED_PAGES"]
    except (OSError, ValueError, KeyError) as exc:
        raise BookShotError(BOOK_PAGES_UNAVAILABLE,
                            "PRINTED_PAGES fragment unreadable at %s (%s)"
                            % (path, exc)) from exc
    return frag

def _page_ink(frame, regions=None):
    """Ink fraction for each page region of one frame (0.0..1.0 each)."""
    cv2 = _cv2()
    np = _np()
    gray = frame if getattr(frame, "ndim", 3) == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    out = []
    for x0, y0, x1, y1 in (regions or PAGE_REGIONS):
        p = gray[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
        out.append(float(np.count_nonzero(p < PAGE_INK_DARK)) / float(p.size)
                   if p.size else 0.0)
    return out

def _median(values):
    v = sorted(values)
    if not v:
        return 0.0
    mid = len(v) // 2
    return v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2.0

def calibrate_pages():
    """The printed-vs-white control the page check must pass first.

    Builds the two shipped page fixtures locally (no network, no spend),
    measures their ink fractions and returns the receipt the check requires.
    Refuses BOOK_CALIBRATION_FAILED when the pair does not sort: a check that
    cannot tell printed pages from blank ones proves nothing.
    """
    cv2, np = _cv2(), _np()
    try:
        from .fixtures import build_fixtures as _FIX
    except ImportError:                              # script import
        from fixtures import build_fixtures as _FIX   # type: ignore
    printed = [ink for f in _FIX.open_book_frames(cv2, np, printed=True)
               for ink in _page_ink(f)]
    white = [ink for f in _FIX.open_book_frames(cv2, np, printed=False)
             for ink in _page_ink(f)]
    p_ink, w_ink = _median(printed), _median(white)
    if not (p_ink > w_ink + PAGE_INK_MARGIN):
        raise BookShotError(
            BOOK_CALIBRATION_FAILED,
            "printed control %.5f does not beat white control %.5f (margin "
            "%.3f): the page check cannot discriminate and every verdict it "
            "would return is UNAVAILABLE" % (p_ink, w_ink, PAGE_INK_MARGIN))
    return {"schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION, "control": "printed-vs-white",
            "printed_ink": round(p_ink, 6), "white_ink": round(w_ink, 6),
            "threshold": round((p_ink + w_ink) / 2.0, 6),
            "margin": PAGE_INK_MARGIN, "sorted": True}

def check_pages(clip=None, spec=None, frames=None, calibrated=None):
    """Measured printed-vs-blank verdict for the open-book frames of a clip.

    A page whose ink fraction sits under the CALIBRATED threshold is blank.
    MORE THAN ONE blank page among the sampled open frames is FAIL
    BOOK_BLANK_PAGES (a book's pages are printed pages). One blank page can
    be a chapter break or a right-hand page not yet turned. UNAVAILABLE never
    passes: no calibration receipt, an unsorted receipt, or no frames.
    """
    spec = spec or {}
    checks = {}
    if not isinstance(calibrated, dict) or not calibrated.get("sorted"):
        return _verdict("UNAVAILABLE", BOOK_PAGES_UNAVAILABLE, checks,
                        "no printed-vs-white calibration receipt; run "
                        "calibrate_pages() first")
    try:
        with _LG.heavy_slot("book-shot-pages"):
            if frames is None:
                frames = _read_clip_frames(clip, max_frames=24)
    except _LG.HeavyJobTimeout as exc:
        return _verdict("UNAVAILABLE", BOOK_FRAMES_UNAVAILABLE, checks,
                        str(exc), calibrated)
    if not frames:
        return _verdict("UNAVAILABLE", BOOK_FRAMES_UNAVAILABLE, checks,
                        "no frames decoded from %s" % (clip,), calibrated)
    window = spec.get("window")
    win = frames[window[0]:window[1]] if isinstance(window, (list, tuple)) \
        and len(window) == 2 else frames
    regions = spec.get("page_regions")
    threshold = float(calibrated.get("threshold") or 0.0)
    inks, blanks = [], []
    for i, f in enumerate(win):
        for j, ink in enumerate(_page_ink(f, regions)):
            inks.append(round(ink, 6))
            if ink < threshold:
                blanks.append({"frame": i, "page": "left" if j == 0 else "right",
                               "ink": round(ink, 6)})
    checks["pages"] = {"sampled_frames": len(win), "pages": len(inks),
                       "threshold": threshold, "inks": inks, "blanks": blanks}
    if len(blanks) > 1:
        return _verdict("FAIL", BOOK_BLANK_PAGES, checks,
                        "%d blank pages among %d sampled (ink under the "
                        "calibrated threshold %.5f): a book's visible pages "
                        "are printed pages" % (len(blanks), len(inks),
                                               threshold), calibrated)
    return _verdict("PASS", "BOOK_PAGES_OK", checks, "", calibrated)

#: Plan keys that are the APPROVAL, not the plan: the hash is of the plan
#: content, so the approval fields are excluded or the hash would chase
#: itself every time a client approves.
PLAN_HASH_EXCLUDED = ("approved_book_plan_sha256", "approved_at")

def plan_sha256(plan):
    """The canonical sha256 of a book plan's content (the producer's hash).

    Stable across key order; the approval fields are excluded (see
    PLAN_HASH_EXCLUDED). Jobs carry this value as ``book_plan_sha256`` and
    kie_dispatch refuses a book video job whose hash is absent or differs
    from ``approved_book_plan_sha256`` (BOOK_PLAN_NOT_APPROVED).
    """
    doc = {k: v for k, v in (plan or {}).items() if k not in PLAN_HASH_EXCLUDED}
    blob = json.dumps(doc, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

def plan_card_rows(plan, excerpt=None):
    """The Book shots block for the card: APPROVALS AND NOTICES only.

    Trevor's locked rule: the card never offers a new choice here. Rows are
    (label, text) pairs, in card row style. The approval row compares the
    plan's own hash with the approved hash, so a plan edited after approval
    shows NOT APPROVED, not a stale tick.
    """
    plan = plan if isinstance(plan, dict) else {}
    rows = []
    current, approved = plan_sha256(plan), plan.get("approved_book_plan_sha256")
    if approved and str(approved) == current:
        when = (" on %s" % plan["approved_at"]) if plan.get("approved_at") else ""
        rows.append(("Book shots:",
                     "APPROVED, plan %s%s. Book video jobs carry this hash."
                     % (current[:12], when)))
    else:
        rows.append(("Book shots:",
                     "NOT APPROVED -- no approved plan hash matches this "
                     "plan. Book video jobs refuse (BOOK_PLAN_NOT_APPROVED) "
                     "until the client approves the plan."))
    if str(plan.get("pages") or "") == "texture":
        rows.append(("Book pages:",
                     "printed page texture -- every visible page carries "
                     "printed text; a blank page fails review."))
    ex = excerpt if isinstance(excerpt, dict) else {}
    if ex.get("lines"):
        rows.append(("Excerpt:",
                     "%d client-supplied line(s) overlay the page; the "
                     "client's own words, spelling checked, and the excerpt "
                     "never reaches a video model." % len(ex["lines"])))
    else:
        rows.append(("Excerpt:",
                     ex.get("note") or "no excerpt supplied -- the pages carry "
                     "no overlay text."))
    return rows

def excerpt_overlay(lines, page=1):
    """The client's excerpt as DATA ONLY, for U9's burn artifact.

    Never a prompt: this dict is not part of any video-model request, and
    nothing here reads text out of a frame. Lines stay the client's words,
    verbatim and in order. ``hook`` names U9's entry point -- the ONE named
    hook in this codebase; the call itself lives in
    ``final_assembler.assembler.excerpt_overlay_stage``.
    """
    clean = [str(l).strip() for l in (lines or ())
             if isinstance(l, str) and str(l).strip()]
    return {"kind": "book-excerpt-overlay", "schema_version": SCHEMA_VERSION,
            "lines": clean[:EXCERPT_MAX_LINES], "page": int(page or 1),
            "hook": EXCERPT_OVERLAY_HOOK, "to_video_model": False,
            "note": "data only: never part of any video-model prompt; burning "
                    "it into frames belongs to U9's captions_burn.overlay_excerpt."}
