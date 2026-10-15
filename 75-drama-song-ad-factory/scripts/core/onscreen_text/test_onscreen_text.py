#!/usr/bin/env python3
"""A6 tests: no words in pictures by default, an OCR-verified bake, the overlay fallback.

DONE-WHEN: the default block is the exact decided sentence; a baked word is only
ever "verified" after OCR read the exact spelling back (one wrong letter FAILs,
an extra word FAILs, an unreadable still is UNAVAILABLE and is NEVER a PASS);
3 misses decide the OVERLAY fallback with receipt TEXT_OVERLAID and a try past
the cap never bakes; the tesseract extractor is registered with frame_text at
import. Injected extractors everywhere except ONE real tesseract read of a
fixture PNG drawn here in stdlib (SKIPPED, never counted as PASS, when the
binary is missing). No network, no spend, no client file.

Run: python3 core/onscreen_text/test_onscreen_text.py   (or python3 -m pytest -q ...)
"""
from __future__ import annotations

import os
import shutil
import struct
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import onscreen_text as OST                            # noqa: E402  (the package)
import onscreen_text.onscreen_text as OSTMOD           # noqa: E402  (the seam lives here)

# The fixture word. Its letters are the only glyphs drawn below.
WORD = "SALE"
FONT = {                              # 5x7 uppercase, one word, no more
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
}


# ------------------------------------------------- the stdlib fixture PNG ---

def _png_gray(path, word, scale=12, pad=None):
    """Draw `word` in black on white and write it as a grayscale PNG (stdlib).

    Big blocky glyphs: the one real tesseract read below must be a fair test
    of the OCR path, not a test of tesseract's patience with antialiasing.

    pad is a fraction of the glyph height, not a token border. The old fixed
    8px margin left the raster hard against the frame, where tesseract read
    "SHALE" for "SALE" (and returned nothing at all under --psm 3) — the same
    read that failed this suite in CI. A third of the glyph height clears the
    cliff: below roughly a quarter the read flips, at and above it the word
    reads clean under --psm 3, 6, 7, 11 and 12 on every tesseract build tested.
    """
    step, gh = 6 * scale, 7 * scale
    if pad is None:
        pad = gh // 3
    w = pad * 2 + len(word) * step - scale
    h = pad * 2 + gh
    rows = [[255] * w for _ in range(h)]
    x0 = pad
    for ch in word:
        for r, bits in enumerate(FONT[ch]):
            for c, bit in enumerate(bits):
                if bit != "1":
                    continue
                for dy in range(scale):
                    for dx in range(scale):
                        rows[pad + r * scale + dy][x0 + c * scale + dx] = 0
        x0 += step
    raw = b"".join(b"\x00" + bytes(r) for r in rows)

    def chunk(tag, data):
        body = tag + data
        return (struct.pack(">I", len(data)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n"
                 + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw, 9))
                 + chunk(b"IEND", b""))
    return path


class _tmp(object):
    """A scratch folder BESIDE the test file (removed however the test ends).

    The one real tesseract read must find the fixture wherever the suite is
    run, and nothing of it may stay in the tree afterwards.
    """

    def __enter__(self):
        self.path = tempfile.mkdtemp(prefix="onscreen-text-", dir=HERE)
        return self.path

    def __exit__(self, *exc):
        shutil.rmtree(self.path, ignore_errors=True)
        return False


def _still(folder, name="still.png"):
    """A throwaway file the injected extractors never open (only hashed)."""
    p = os.path.join(folder, name)
    with open(p, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\nnot-a-real-pixel")
    return p


def _fake(text):
    def extractor(paths):
        return [text] * len(paths)
    extractor.__name__ = "fake-ocr"
    return extractor


def _with_no_engine(fn):
    """Run fn with the OCR binary reported missing; always restore.

    The seam is the module global, so it is patched where the lookup
    happens -- a patch on the package export would never be seen.
    """
    real, asked = OSTMOD.tesseract_bin, []

    def missing():
        asked.append(True)
        return None

    OSTMOD.tesseract_bin = missing
    try:
        fn()
    finally:
        OSTMOD.tesseract_bin = real
    return asked


# ------------------------------------------------------- the decided words ---

def test_no_text_block_is_the_exact_decided_sentence():
    assert OST.no_text_block() == (
        "No words, letters, numbers, logos or signage anywhere in the image.")
    assert OST.NO_TEXT_BLOCK == OST.no_text_block()


def test_bake_block_quotes_the_exact_words_and_forbids_the_rest():
    block = OST.bake_block("OPEN 24 HOURS")
    assert '"OPEN 24 HOURS"' in block        # the exact words, verbatim
    assert "No other words" in block
    assert "signage" in block
    try:
        OST.bake_block("   ")
    except OST.OnscreenTextError as exc:
        assert exc.code == OST.BAD_INPUT
    else:
        raise AssertionError("bake_block accepted no words")


def test_normalize_ignores_case_spacing_and_punctuation_only():
    assert OST.normalize("  Open!! ") == "open"
    assert OST.normalize("OPEN 24-HOURS") == "open 24 hours"
    assert OST.normalize("sale") != OST.normalize("sall")   # a letter still matters
    assert OST.normalize("sale") != OST.normalize("sale now")


# ----------------------------------------------- verify_still (injected) ----

def test_verify_still_exact_text_passes():
    with _tmp() as td:
        row = OST.verify_still(_still(td), WORD, extractor=_fake("sale!"))
        assert row["verdict"] == OST.VERDICT_PASS
        assert row["reason_code"] is None
        assert row["read"] == "sale!"
        assert row["expected"] == WORD
        assert len(row["sha256"]) == 64
        assert row["engine"] == "fake-ocr"


def test_verify_still_one_wrong_letter_fails():
    with _tmp() as td:
        row = OST.verify_still(_still(td), WORD, extractor=_fake("salle"))
        assert row["verdict"] == OST.VERDICT_FAIL
        assert row["reason_code"] == OST.TEXT_NOT_VERIFIED
        assert row["read_norm"] == "salle" and row["expected_norm"] == "sale"


def test_verify_still_extra_word_fails():
    with _tmp() as td:
        row = OST.verify_still(_still(td), WORD, extractor=_fake("sale now"))
        assert row["verdict"] == OST.VERDICT_FAIL
        assert row["reason_code"] == OST.TEXT_NOT_VERIFIED


def test_verify_still_empty_read_is_never_a_pass():
    """A read that says nothing is not a clean picture; it is a FAIL."""
    with _tmp() as td:
        row = OST.verify_still(_still(td), WORD, extractor=_fake(""))
        assert row["verdict"] == OST.VERDICT_FAIL
        assert row["read"] == "" and row["reason_code"] == OST.TEXT_NOT_VERIFIED


def test_verify_still_missing_file_and_bad_expected():
    with _tmp() as td:
        row = OST.verify_still(os.path.join(td, "gone.png"), WORD,
                               extractor=_fake("sale"))
        assert row["verdict"] == OST.VERDICT_UNAVAILABLE
        assert row["reason_code"] == OST.STILL_UNAVAILABLE
        row = OST.verify_still(_still(td), "  ", extractor=_fake("sale"))
        assert row["verdict"] == OST.VERDICT_UNAVAILABLE
        assert row["reason_code"] == OST.BAD_INPUT


def test_verify_still_crashing_extractor_is_unavailable():
    def boom(paths):
        raise RuntimeError("pixel soup")

    with _tmp() as td:
        row = OST.verify_still(_still(td), WORD, extractor=boom)
        assert row["verdict"] == OST.VERDICT_UNAVAILABLE
        assert row["reason_code"] == OST.OCR_FAILED


def test_verify_still_without_an_engine_is_unavailable_never_pass():
    def run():
        with _tmp() as td:
            row = OST.verify_still(_still(td), WORD)     # the real engine
            assert row["verdict"] == OST.VERDICT_UNAVAILABLE
            assert row["reason_code"] == OST.OCR_UNAVAILABLE
            assert row["read"] == "" and row["sha256"]      # hashed, never read

    asked = _with_no_engine(run)
    assert asked, "the module must ask for the binary, not assume it"


def test_extractor_raises_ocr_unavailable_without_a_binary():
    def run():
        try:
            OST.tesseract_extractor(["/does/not/matter.png"])
        except OST.OCRUnavailable as exc:
            assert exc.code == OST.OCR_UNAVAILABLE
        else:
            raise AssertionError("no binary must raise, never report no text")

    _with_no_engine(run)


# ------------------------------------------------------------- decide() -----

def _pass(**kw):
    row = dict(verdict=OST.VERDICT_PASS, read=WORD, expected=WORD)
    row.update(kw)
    return row


def test_decide_bakes_a_verified_bake_within_three_tries():
    shot = {"text": WORD}
    out = OST.decide(shot, [_pass(verdict=OST.VERDICT_FAIL), _pass()])
    assert out["decision"] == "BAKED" and out["receipt"] == OST.TEXT_BAKED
    assert out["verified"] is True and out["reason_code"] is None
    assert out["overlay_hook"] is None


def test_decide_overlays_after_three_fails():
    fails = [_pass(verdict=OST.VERDICT_FAIL, read="sall")] * OST.MAX_TRIES
    out = OST.decide({"on_screen_text": WORD}, fails)
    assert out["decision"] == "OVERLAY"
    assert out["receipt"] == OST.TEXT_OVERLAID        # the decided receipt
    assert out["reason_code"] == OST.TEXT_NOT_VERIFIED
    assert out["verified"] is False
    assert out["overlay_hook"] == "final_assembler.captions_burn.overlay_excerpt"


def test_decide_never_bakes_past_the_cap():
    """A clean read on the fourth try is outside the free tries: still OVERLAY."""
    fails = [_pass(verdict=OST.VERDICT_FAIL, read="sall")] * OST.MAX_TRIES
    out = OST.decide(WORD, fails + [_pass()])
    assert out["decision"] == "OVERLAY" and out["receipt"] == OST.TEXT_OVERLAID
    assert out["tries_used"] == OST.MAX_TRIES and out["tries_total"] == 4


def test_decide_unavailable_is_never_a_pass():
    rows = [dict(verdict=OST.VERDICT_UNAVAILABLE,
                 reason_code=OST.OCR_UNAVAILABLE)] * OST.MAX_TRIES
    out = OST.decide({"text": WORD}, rows)
    assert out["decision"] == "OVERLAY" and out["verified"] is False
    assert out["reason_code"] == OST.OCR_UNAVAILABLE


def test_decide_with_no_first_try_is_the_fallback():
    out = OST.decide({"text": WORD}, [])
    assert out["decision"] == "OVERLAY" and out["tries_used"] == 0
    try:
        OST.decide({"text": ""}, [])
    except OST.OnscreenTextError as exc:
        assert exc.code == OST.BAD_INPUT
    else:
        raise AssertionError("decide() accepted a shot with no words")


# ------------------------------------------- the frame gate's extractor -----

def test_tesseract_extractor_is_registered_with_frame_text_at_import():
    # The suite conftest drops skill-tree modules from sys.modules between
    # collections, so a body-time re-import of frame_text can bind a NEWER
    # module generation than the one this file's OST registered with — the
    # identity check must read the exact module object registration ran on.
    FT = OSTMOD._FT
    assert FT is not None, "onscreen_text must have loaded frame_text"
    assert OST.REGISTERED is True, "import must register the OCR extractor"
    assert FT.EXTRACTORS[OST.ENGINE] is OST.tesseract_extractor
    # and the frame gate can hand it a frame list and get one entry per frame
    assert FT.EXTRACTORS[OST.ENGINE].__name__ == "tesseract_extractor"


# ------------------------------------------- the ONE real tesseract read ----

def test_real_tesseract_reads_the_generated_fixture():
    if OST.tesseract_bin() is None:
        msg = "SKIPPED: tesseract not installed"
        print(msg)
        sys.__stderr__.write(msg + "\n")   # said out loud even under pytest -q
        return
    with _tmp() as td:
        still = _png_gray(os.path.join(td, "word.png"), WORD)
        row = OST.verify_still(still, WORD)             # no injected extractor
        assert row["engine"] == OST.ENGINE
        assert row["verdict"] == OST.VERDICT_PASS, row
        assert row["read_norm"] == OST.normalize(WORD)
        wrong = OST.verify_still(still, "SALL")
        assert wrong["verdict"] == OST.VERDICT_FAIL, wrong
        out = OST.decide({"text": WORD}, [row])
        assert out["decision"] == "BAKED" and out["receipt"] == OST.TEXT_BAKED


def main():
    failures = 0
    for name in sorted(n for n in globals() if n.startswith("test_")):
        try:
            globals()[name]()
            print("ok   %s" % name)
        except Exception as exc:                        # noqa: BLE001
            failures += 1
            print("FAIL %s: %s: %s" % (name, type(exc).__name__, exc))
    print("%d test(s), %d failure(s)" % (
        len([n for n in globals() if n.startswith("test_")]), failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
