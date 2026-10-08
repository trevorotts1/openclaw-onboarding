#!/usr/bin/env python3
"""I5 test: an abrupt cut fails, a resolved ending passes. $0, stdlib only.

Run: python3 ending_qc/test_ending_qc.py   (from scripts/core)
"""
import math
import os
import struct
import sys
import tempfile
import wave

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)
import ending_qc as E  # noqa: E402

RATE = 8000


def make_wav(path, secs, fade_from=None):
    """440 Hz tone; if fade_from is set the level decays to 0 from there."""
    frames = []
    for i in range(int(secs * RATE)):
        t = i / RATE
        g = 1.0 if fade_from is None or t < fade_from else max(
            0.0, 1 - (t - fade_from) / (secs - fade_from))
        frames.append(struct.pack("<h", int(12000 * g * math.sin(6.2832 * 440 * t))))
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(b"".join(frames))


def main():
    d = tempfile.mkdtemp()
    cliff, fade = os.path.join(d, "cliff.wav"), os.path.join(d, "fade.wav")
    make_wav(cliff, 53.0)                    # loud right up to the cut
    make_wav(fade, 53.0, fade_from=50.5)     # resolves over the last 2.5 s
    good = dict(last_word_end_s=49.0, endcard_start_s=52.0, endcard_end_s=56.5,
                target_s=60, picture_fade_s=0.5)
    r = E.check_ending(fade, **good)
    assert r["verdict"] == "PASS", r
    r = E.check_ending(cliff, **good)
    assert r["verdict"] == "FAIL" and "ENDING_ABRUPT_AUDIO" in r["reasons"], r
    r = E.check_ending(fade, **dict(good, last_word_end_s=52.9))
    assert "ENDING_CUT_MID_WORD" in r["reasons"], r
    r = E.check_ending(fade, **dict(good, picture_fade_s=0.0))
    assert "ENDING_NO_PICTURE_FADE" in r["reasons"], r
    r = E.check_ending(fade, **dict(good, endcard_start_s=54.0, endcard_end_s=59.0))
    assert "ENDING_CARD_PAST_LIMIT" in r["reasons"], r      # 59 > 58
    r = E.check_ending(fade, **dict(good, endcard_end_s=54.0))
    assert "ENDING_CARD_LENGTH" in r["reasons"], r          # 2 s card
    # lyric sheet / style ask for a real ending
    assert E.check_sheet_ending("[Verse]\nI love it", "pop") == ["ENDING_TAG_MISSING"]
    lyr, sty = E.with_clean_ending("[Verse]\nI love it", "pop")
    assert E.check_sheet_ending(lyr, sty) == []
    assert E.with_clean_ending(lyr, sty) == (lyr, sty)      # idempotent
    print("ending_qc test: PASS")


if __name__ == "__main__":
    main()
