#!/usr/bin/env python3
"""letters.py: the burned-in-letter gate for EVERY landed take (G-LETTER-01).

The old gate scoped Kling-only, so H3 takes carrying LETTERS were admitted
(T01, T19, T25 carried letters into timeline v11 because the call never
looked at them), and box text on product shots was never asked about. This
gate:

  * runs on every landed take whatever model made it -- the model name is
    recorded, never used to skip a take;
  * adds a box-region check for product shots (the T28 class: open box plus
    brass key plus a lid mark), a fixed region the reader also looks at;
  * keeps lane-aware verdicts from ``lanes`` so a swap claim can never cite a
    clean fix lane while the landed path is lettered;
  * a lettered take fails with ``BOX_TEXT_FOUND`` / ``NEW_TEXT_IN_TAKE`` and
    is remade, never cropped or covered (section 3.8).

The reader is a callable (the OCR extractor or an eye-check model). No
reader, an empty extraction, or a take with no eye record is
``LETTER_GATE_UNAVAILABLE`` / ``LIP_TAKE_NOT_EYE_CHECKED`` -- never a pass.
stdlib only; ffmpeg for sampling, ``run`` injectable.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

_core = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _core not in sys.path:
    sys.path.insert(0, _core)
from final_assembler import frame_text as _FT  # noqa: E402
try:                                              # package member or standalone
    from . import lanes as _lanes
except ImportError:                               # pragma: no cover
    import lanes as _lanes

TOOL_NAME = "letters"
TOOL_VERSION = "1.0.0"

NEW_TEXT_IN_TAKE = "NEW_TEXT_IN_TAKE"
BOX_TEXT_FOUND = "BOX_TEXT_FOUND"
TEXT_CHANGED = "TEXT_CHANGED"
NON_ENGLISH_SCRIPT = "NON_ENGLISH_SCRIPT"
LETTER_GATE_UNAVAILABLE = "LETTER_GATE_UNAVAILABLE"
LIP_TAKE_NOT_EYE_CHECKED = "LIP_TAKE_NOT_EYE_CHECKED"

#: The product-shot box region as a fraction of the frame (x, y, w, h): the
#: open lid and its mark sit in the lower third of a chest-up product frame.
BOX_REGION = (0.15, 0.55, 0.70, 0.40)

_NON_LATIN = (
    (0x0370, 0x03FF),   # Greek
    (0x0400, 0x04FF),   # Cyrillic
    (0x0590, 0x05FF),   # Hebrew
    (0x0600, 0x06FF),   # Arabic
    (0x0900, 0x097F),   # Devanagari
    (0x3040, 0x30FF),   # kana
    (0x3400, 0x4DBF),   # CJK ext A
    (0x4E00, 0x9FFF),   # CJK
    (0xAC00, 0xD7AF),   # Hangul
)


def non_english(text):
    """True when ``text`` holds a character from a non-English script (T-4)."""
    for ch in str(text or ""):
        cp = ord(ch)
        for lo, hi in _NON_LATIN:
            if lo <= cp <= hi:
                return True
    return False


def _eye_recorded(eye):
    """An eye record is a looker and a verdict; a scan alone is never one."""
    if not isinstance(eye, dict):
        return False
    who = str(eye.get("who") or "").strip()
    verdict = str(eye.get("verdict") or "").strip().upper()
    sheets = eye.get("sheet") or eye.get("sheets")
    return bool(who) and verdict in ("CLEAN", "LETTERS") and bool(sheets)


def read_box(clip, region=BOX_REGION, extractor=None, ffmpeg="ffmpeg"):
    """Read the product-shot box region (T28 class); words found, or []."""
    x, y, w, h = region
    out = os.path.join(tempfile.mkdtemp(prefix="box-"), "box.png")
    vf = ("crop=iw*%.4f:ih*%.4f:iw*%.4f:ih*%.4f" % (w, h, x, y))
    proc = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-y", "-i",
                           str(clip), "-vf", vf, "-frames:v", "1", out],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not os.path.isfile(out):
        raise _FT.FrameTextError(_FT.FRAME_EXTRACT_UNAVAILABLE,
                                 "box crop failed: %s"
                                 % (proc.stderr or "")[-200:])
    name, fn = _FT._resolve_extractor(extractor)  # noqa: SLF001
    if name == _FT.STUB_NAME:
        raise _FT.FrameTextError(_FT.OCR_UNAVAILABLE,
                                 "the stub reads no pixels")
    reads = _FT._call_extractor(fn, [out], name)  # noqa: SLF001
    return [str(t).strip() for t in reads if t and str(t).strip()]


def gate_take(path, model, extractor, eye=None, frames=None, box_region=None,
              sample=None, ffmpeg="ffmpeg"):
    """One take's letter verdict, whatever model produced it.

    ``extractor`` is a frame_text extractor (one entry per frame path) or the
    name of a registered one. ``frames`` is the sampled frame list; when it
    is absent the caller's ``sample(path)`` must supply it. A product shot
    passes ``box_region`` to add the box-text question.
    """
    row = {"path": path, "model": str(model or ""), "lane": _lanes.classify(path),
           "verdict": "UNAVAILABLE", "reason_code": None, "tokens_seen": 0,
           "texts": [], "eye": bool(_eye_recorded(eye))}
    if not frames:
        if sample is None:
            row["reason_code"] = LETTER_GATE_UNAVAILABLE
            row["detail"] = "no frames and no sampler"
            return row
        frames = list(sample(path) or [])
    if not frames:
        row["reason_code"] = LETTER_GATE_UNAVAILABLE
        row["detail"] = "the sampler returned no frames"
        return row
    name, fn = _FT._resolve_extractor(extractor)  # noqa: SLF001
    if name == _FT.STUB_NAME:
        row["reason_code"] = LETTER_GATE_UNAVAILABLE
        row["detail"] = "the stub reads no pixels"
        return row
    try:
        reads = _FT._call_extractor(fn, frames, name)  # noqa: SLF001
    except Exception as exc:                       # noqa: BLE001  fail closed
        row["reason_code"] = LETTER_GATE_UNAVAILABLE
        row["detail"] = str(exc)
        return row
    texts = [str(t).strip() for t in reads if t and str(t).strip()]
    row["texts"] = texts
    row["tokens_seen"] = sum(len(t.split()) for t in texts)
    # The letters are read and reported FIRST: a lettered take says what the
    # scan found, so a missing eye record can never hide the refusal behind
    # another code. The eye is a second, separate requirement below.
    if any(non_english(t) for t in texts):
        row["verdict"], row["reason_code"] = "FAIL", NON_ENGLISH_SCRIPT
        return row
    if texts:
        row["verdict"], row["reason_code"] = "FAIL", NEW_TEXT_IN_TAKE
        return row
    if box_region:
        try:
            box_words = read_box(path, box_region, extractor, ffmpeg=ffmpeg)
        except Exception as exc:                   # noqa: BLE001  fail closed
            row["reason_code"] = LETTER_GATE_UNAVAILABLE
            row["detail"] = "box region unreadable: %s" % exc
            return row
        row["box_texts"] = box_words
        if box_words:
            row["tokens_seen"] += sum(len(w.split()) for w in box_words)
            row["verdict"], row["reason_code"] = "FAIL", BOX_TEXT_FOUND
            return row
    if not _eye_recorded(eye):
        # N-28: a clean scan is not a pass. The take still needs an eye
        # record from a reader that can see pictures.
        row["reason_code"] = LIP_TAKE_NOT_EYE_CHECKED
        return row
    row["verdict"] = "PASS"
    return row


def gate_rows(rows, extractor, eye_by_path=None, sample=None, ffmpeg="ffmpeg"):
    """Gate every landed take; lane-aware, model-agnostic."""
    eye_by_path = eye_by_path or {}
    out = []
    for r in rows or []:
        out.append(gate_take(r.get("path"), r.get("model"), extractor,
                             eye=eye_by_path.get(r.get("path")),
                             frames=r.get("frames"),
                             box_region=r.get("box_region"), sample=sample,
                             ffmpeg=ffmpeg))
    findings = [{"path": o["path"], "code": o["reason_code"]}
                for o in out if o["reason_code"]]
    if out:
        sweep = _lanes.sweep_verdict(
            [{"path": o["path"],
              "verdict": "CLEAN" if o["verdict"] == "PASS" else "LETTERS",
              "tokens_seen": o["tokens_seen"]} for o in out],
            control=eye_by_path.get("__control__"))
        findings.extend(sweep["findings"])
        calibrated = sweep["calibrated"]
    else:
        calibrated = False
    return {"rows": out, "findings": findings,
            "pass": bool(out) and not findings
            and all(o["verdict"] == "PASS" for o in out),
            "calibrated": calibrated}


# --------------------------------------------------------------- sampling ---

def _ffprobe_seconds(path, ffprobe):
    proc = subprocess.run([ffprobe, "-v", "error", "-show_entries",
                           "format=duration", "-of", "default=nw=1:nk=1",
                           str(path)], capture_output=True, text=True,
                          check=False)
    try:
        return float((proc.stdout or "").strip().splitlines()[0])
    except (ValueError, IndexError):
        raise _FT.FrameTextError(_FT.FRAME_EXTRACT_UNAVAILABLE,
                                 "duration of %s unreadable" % path)


def sample_for_gate(path, ffmpeg="ffmpeg", ffprobe="ffprobe", rate=4.0,
                    workdir=None):
    """A contact-sheet sampler: ``rate`` frames per second (4 for the eye)."""
    total = _ffprobe_seconds(path, ffprobe)
    count = max(2, int(round(total * float(rate))))
    out_dir = workdir or tempfile.mkdtemp(prefix="letters-")
    return _FT._extract_frames(path, ffmpeg, count, out_dir,  # noqa: SLF001
                               ffprobe=ffprobe)


if __name__ == "__main__":
    # G-LETTER-01: the gate applies to EVERY model, the box region is read on
    # a product shot, and a clean scan is not a pass without the eye record.
    # The box reader is stubbed so no video and no ffmpeg run is needed.
    eye = {"who": "reviewer", "verdict": "CLEAN", "sheet": "sheet.png"}
    clean = lambda paths: ["" for _ in paths]
    lettered = lambda paths: ["CALL NOW" for _ in paths]

    # 1. An H3 take with burned letters: the old gate scoped itself to Kling.
    h3 = gate_take("clips/T01.mp4", "minimax-h3", lettered, eye=eye,
                   frames=["a.png"])
    assert h3["verdict"] == "FAIL" and h3["reason_code"] == NEW_TEXT_IN_TAKE
    # 2. The same words from a Kling take: identical, no model branch.
    kl = gate_take("clips/T01.mp4", "kling", lettered, eye=eye, frames=["a.png"])
    assert kl["reason_code"] == NEW_TEXT_IN_TAKE
    # 3. The T28 class: whole frame clean, the box region lettered.
    real_read_box = globals()["read_box"]
    globals()["read_box"] = lambda clip, region, extractor=None, ffmpeg="ffmpeg": \
        ["OPEN", "KEY"]
    try:
        box = gate_take("clips/T28.mp4", "minimax-h3", clean, eye=eye,
                        frames=["a.png"], box_region=BOX_REGION)
        assert box["reason_code"] == BOX_TEXT_FOUND, box
        assert box["tokens_seen"] == 2
    finally:
        globals()["read_box"] = real_read_box
    # 4. A clean whole-frame read is not a pass without the eye record.
    no_eye = gate_take("clips/T02.mp4", "kling", clean, eye=None,
                       frames=["a.png"])
    assert no_eye["reason_code"] == LIP_TAKE_NOT_EYE_CHECKED
    assert gate_take("clips/T02.mp4", "kling", clean, eye=eye,
                     frames=["a.png"])["verdict"] == "PASS"
    # 5. The stub reader and a missing sampler are unavailable, never a pass.
    assert gate_take("x.mp4", "kling", "stub", eye=eye,
                     frames=["a.png"])["reason_code"] == LETTER_GATE_UNAVAILABLE
    assert gate_take("x.mp4", "kling", clean, eye=eye)["reason_code"] == \
        LETTER_GATE_UNAVAILABLE
    # 6. Non-English script is a hard fail (T-4).
    cyr = gate_take("c.mp4", "h3", lambda p: ["Привет" for _ in p], eye=eye,
                    frames=["a.png"])
    assert cyr["reason_code"] == NON_ENGLISH_SCRIPT
    print("letters: control PASS")
