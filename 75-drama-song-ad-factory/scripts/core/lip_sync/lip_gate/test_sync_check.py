#!/usr/bin/env python3
"""sync_check tests: Trevor's looser verdict map on the validated measurement.
Stdlib only, $0, no client media. Run: python3 test_sync_check.py (empty HOME is fine)."""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sync_check as S  # noqa: E402

FPS = 30.0


def speech(seed, n=150):
    r, out = random.Random(seed), []
    while len(out) < n:
        out += [r.uniform(.6, 1.0)] * r.randint(3, 6) + [.05] * r.randint(2, 4)
    return out[:n]


VOICE, OTHERS = speech(1), [speech(2), speech(3)]


def meas(mouth=VOICE, voice=VOICE, others=OTHERS, **kw):
    return S.measure_sync(mouth, voice, others, FPS, **kw)


def num(margin, corr=.6, pct=0.0, unmeasurable=None):
    return {"corr": corr, "pct": pct, "margin": margin, "unmeasurable": unmeasurable}


def test_constants_block():
    assert (S.MAX_LAG_FRAMES, S.CORR_FLOOR, S.MARGIN_FLOOR, S.SYNCED_MARGIN) == (10, .40, 0.0, .05)
    assert (S.CHANCE_PCT_MAX, S.ROLL_MIN_FRAMES, S.LOOKALIKE_CORR, S.MIN_FRAMES) == (.20, 15, .85, 45)


def test_matching_mouth_is_synced_pass():
    m = meas()
    assert m["grade"] == S.SYNCED and m["lag_frames"] == 0 and m["pct"] <= S.CHANCE_PCT_MAX, m
    assert S.verdict(m) == S.PASS == S.verdict(m, sung=True)


def test_lag_is_searched_not_failed():
    m = meas(mouth=[.05] * 8 + VOICE[:-8])           # mouth 8 frames LATE
    assert m["lag_frames"] == 8 and m["grade"] == S.SYNCED, m


def test_verdict_map_spoken_and_sung():
    for margin, spoken, sung in ((.20, S.PASS, S.PASS), (.05, S.PASS, S.PASS),
                                 (.03, S.FLAG, S.UNDETERMINED), (0.0, S.FLAG, S.UNDETERMINED),
                                 (-.01, S.FAIL, S.UNDETERMINED)):
        m = num(margin)
        assert (S.verdict(m), S.verdict(m, True)) == (spoken, sung), (margin, S.grade(m))
    for m in (num(.2, corr=.39), num(.2, pct=.21)):    # corr floor, chance test
        assert (S.grade(m), S.verdict(m), S.verdict(m, True)) == (S.NOT_SYNCED, S.FAIL, S.UNDETERMINED)
    assert S.grade(num(.2, corr=.40, pct=.20)) == S.SYNCED   # the floors are inclusive


def test_unmeasurable_is_never_a_pass():
    m = num(.9, unmeasurable="face")
    assert S.verdict(m) == S.verdict(m, True) == S.UNMEASURABLE


def test_wrong_audio_never_passes():
    m = meas(mouth=OTHERS[0])                          # mouth follows ANOTHER line
    assert m["grade"] == S.NOT_SYNCED and m["margin"] < 0, m
    assert S.verdict(m) == S.FAIL and S.verdict(m, True) == S.UNDETERMINED


def test_random_mouth_not_synced():
    r = random.Random(9)
    assert meas(mouth=[r.random() for _ in VOICE])["grade"] == S.NOT_SYNCED


def test_lookalike_hook_is_dropped_from_controls():
    hook = [v * 1.01 + .001 for v in VOICE]            # the same hook sung again
    m = meas(others=OTHERS + [hook])
    assert m["others_dropped"] == 1 and m["grade"] == S.SYNCED, m
    m = meas(others=[hook, hook])
    assert m["grade"] == S.UNMEASURABLE and "lookalike" in m["unmeasurable"], m


def test_clip_is_cut_to_the_audio_length():
    m = meas(mouth=VOICE + [.9] * 40, voice=VOICE)     # padded video tail
    assert m["frames_used"] == len(VOICE) + 1 and m["grade"] == S.SYNCED, m


def test_unmeasurable_rules():
    assert meas(face_found=.94)["grade"] == S.UNMEASURABLE
    assert meas(mouth_pos=.40)["grade"] == S.UNMEASURABLE
    assert meas(mouth=[.3] * 150)["grade"] == S.UNMEASURABLE          # still face
    assert meas(voice=[0.0] * 150)["grade"] == S.UNMEASURABLE         # silent
    assert meas(others=[OTHERS[0]])["grade"] == S.UNMEASURABLE        # < 2 other lines
    assert meas(mouth=VOICE[:44], voice=VOICE[:44])["grade"] == S.UNMEASURABLE   # < 45 frames
    assert meas(mouth=VOICE[:46], voice=VOICE[:46])["grade"] != S.UNMEASURABLE


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
