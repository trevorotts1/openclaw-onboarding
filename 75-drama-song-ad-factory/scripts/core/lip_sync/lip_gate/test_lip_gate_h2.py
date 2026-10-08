#!/usr/bin/env python3
"""H2 tests: measured lip-sync gate. Stdlib only, $0, mocked providers.

DONE-WHEN: a deliberately shifted clip FAILS and a good clip PASSES; the
receipt row carries the numbers; InfiniTalk runs only as a one-time A/B and
the better-measuring clip is kept.

Run: python3 core/lip_sync/lip_gate/test_lip_gate_h2.py
"""
import os
import random
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIP = os.path.dirname(HERE)
if LIP not in sys.path:
    sys.path.insert(0, LIP)

import lip_gate as L                                   # noqa: E402

FPS = 30


def speech(seed, n=150, gap=None):
    """Bursty speech-like envelope; optional (start, end) silent gap."""
    r, out = random.Random(seed), []
    while len(out) < n:
        out += [r.uniform(.6, 1.0)] * r.randint(3, 6) + [.05] * r.randint(2, 4)
    out = out[:n]
    if gap:
        out[gap[0]:gap[1]] = [.05] * (gap[1] - gap[0])
    return out


VOICE, CONTROL = speech(1), speech(2)


def lead(x, frames):          # mouth moves `frames` BEFORE the sound
    return x[frames:] + [.05] * frames


def judged(mouth, voice=VOICE):
    return L.judge(L.measure(mouth, voice, CONTROL, FPS))


def test_good_passes():
    j = judged(VOICE)
    assert j["verdict"] == "PASS" and j["offset_s"] == 0 and j["corr"] > .9, j


def test_shifted_fails_and_shift_fixes():
    j = judged(lead(VOICE, 6))                 # 0.2 s early
    assert j["verdict"] == "FAIL" and L.LIP_OFFSET in j["reasons"], j
    assert abs(j["offset_s"] + 0.2) < 1e-6 and abs(j["shift_s"] - 0.2) < 1e-6
    fixed = ([.05] * 6) + lead(VOICE, 6)[:-6]          # delay clip by shift_s
    assert judged(fixed)["verdict"] == "PASS"


def test_random_mouth_fails_corr():
    r = random.Random(9)
    j = judged([r.random() for _ in VOICE])
    assert j["verdict"] == "FAIL" and L.LIP_CORR_LOW in j["reasons"], j


def test_wrong_audio_control_margin():
    # mouth follows the CONTROL audio: correlates with itself but the
    # wrong-audio control matches as well -> margin fails.
    j = L.judge(L.measure(CONTROL, VOICE, CONTROL, FPS))
    assert L.LIP_CONTROL_MARGIN in j["reasons"] and j["verdict"] == "FAIL", j


def test_frozen_face_fails():
    v = speech(1, gap=(60, 90))                # 1.0 s pause inside the line
    mouth = [0.0 if 60 <= i < 90 else x for i, x in enumerate(v)]
    j = L.judge(L.measure(mouth, v, CONTROL, FPS))
    assert j["frozen_s"] > L.MAX_FROZEN_S and L.LIP_FROZEN_FACE in j["reasons"], j
    short = speech(1, gap=(60, 70))            # 0.33 s pause is fine
    m2 = [0.0 if 60 <= i < 70 else x for i, x in enumerate(short)]
    assert L.measure(m2, short, CONTROL, FPS)["frozen_s"] < L.MAX_FROZEN_S


def _mock(table):
    """generate() returns a name; measure_clip() returns canned series."""
    calls = []

    def gen(provider, spec):
        calls.append((provider, "improved" if spec else "base"))
        return "%s-%s" % calls[-1]
    return calls, gen, lambda clip: L.measure(table[clip], VOICE, CONTROL, FPS)


GOOD, BAD, BAD2 = VOICE, lead(VOICE, 6), lead(VOICE, 9)


def test_regenerate_once_then_pass_no_infinitalk():
    calls, gen, meas = _mock({"kling-base": BAD, "kling-improved": GOOD})
    row = L.run_gate("L1", gen, meas, {})
    assert row["verdict"] == "PASS" and row["kept"] == "kling"
    assert calls == [("kling", "base"), ("kling", "improved")]
    assert not row["infinitalk_ab"]
    assert set(row["numbers"]) == {"offset_s", "corr", "control_corr",
                                   "margin", "frozen_s"}


def test_infinitalk_one_time_ab_keeps_better():
    state = {}
    t = {"kling-base": BAD2, "kling-improved": BAD,
         "infinitalk-improved": GOOD}
    calls, gen, meas = _mock(t)
    row = L.run_gate("L1", gen, meas, state)
    assert row["infinitalk_ab"] and row["kept"] == "infinitalk"
    assert row["verdict"] == "PASS"
    # second failing line: the A/B is spent, InfiniTalk is not called again
    calls.clear()
    row2 = L.run_gate("L2", gen, meas, state)
    assert [c[0] for c in calls] == ["kling", "kling"] and not row2["infinitalk_ab"]
    assert row2["verdict"] == "FAIL_REPLACE" and row2["kept"] == "kling"
    assert row2["numbers"]["offset_s"] == -0.2     # kept the better of the two


def test_ab_keeps_kling_when_infinitalk_measures_worse():
    t = {"kling-base": BAD, "kling-improved": BAD,
         "infinitalk-improved": BAD2}
    _, gen, meas = _mock(t)
    row = L.run_gate("L1", gen, meas, {})
    assert row["kept"] == "kling" and row["verdict"] == "FAIL_REPLACE"


def test_qc_check_fails_replaced_or_unnumbered():
    ok = {"line_id": "a", "verdict": "PASS", "numbers": {}}
    assert L.qc_check([ok])["pass"]
    assert not L.qc_check([ok, {"line_id": "b", "verdict": "FAIL_REPLACE",
                               "numbers": {}}])["pass"]
    assert not L.qc_check([{"line_id": "c", "verdict": "PASS"}])["pass"]


def test_envelope_ffmpeg():
    ff = shutil.which("ffmpeg")
    if not ff:
        print("skip envelope (no ffmpeg)")
        return
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "t.wav")
        subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i",
                        "sine=f=300:d=1,apad=pad_dur=1", "-t", "2", wav,
                        "-y"], check=True)
        env = L.envelope(wav, fps=FPS, ffmpeg=ff)
    assert abs(len(env) - 60) <= 2
    assert sum(env[:25]) / 25 > 20 * (sum(env[40:]) / 20 + 1e-9)


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
