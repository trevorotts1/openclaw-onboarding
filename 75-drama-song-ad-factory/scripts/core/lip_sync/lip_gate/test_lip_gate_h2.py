#!/usr/bin/env python3
"""H2 tests: measured lip-sync gate. Stdlib only, $0, mocked providers.

DONE-WHEN: each verdict path (PASS, ACCEPT_WITH_FLAG, FAIL, UNMEASURED) is
reached, a held sung note does not sink a good clip, the 2-try cap holds, and
a missing mediapipe is reported, never passed. No client video needed.

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


def judged(mouth, voice=VOICE, **kw):
    return L.judge(L.measure(mouth, voice, [CONTROL, speech(3)], FPS, **kw))


def test_good_passes():
    j = judged(VOICE)
    assert j["verdict"] == L.PASS and j["offset_s"] == 0 and j["corr"] > .9, j


def test_borderline_timing_is_flagged_and_used():
    j = judged(lead(VOICE, 6))                 # 0.2 s early: over 4, under 8 frames
    assert j["verdict"] == L.FLAG and L.LIP_OFFSET in j["flags"], j
    assert j["reasons"] == [] and abs(j["shift_s"] - 0.2) < 1e-6


def test_far_off_timing_fails():
    # three isolated bursts 45 frames apart; mouth 12 frames early (> window)
    v = [.05] * 150
    for s0 in (20, 65, 110):
        v[s0:s0 + 6] = [.9] * 6
    j = judged(lead(v, 12), v)
    assert j["verdict"] == L.FAIL, j


def test_random_mouth_fails():
    r = random.Random(9)
    j = judged([r.random() for _ in VOICE])
    assert j["verdict"] == L.FAIL, j


def test_wrong_audio_fails():
    # the mouth follows ANOTHER line's audio: the other audio matches better
    j = L.judge(L.measure(CONTROL, VOICE, [CONTROL, speech(3)], FPS))
    assert j["verdict"] == L.FAIL and L.LIP_WRONG_AUDIO in j["reasons"], j


def test_still_or_missing_face_fails():
    j = judged(VOICE, mouth_range=0.001)
    assert j["verdict"] == L.FAIL and L.LIP_STILL_FACE in j["reasons"], j
    j = judged(VOICE, face_found=False)
    assert j["verdict"] == L.FAIL and L.LIP_FACE_NOT_FOUND in j["reasons"], j


def test_held_note_still_passes():
    # sung: a 60-frame held note. Voice steady, mouth held open with a little
    # drift. Only the changing frames are scored, so the plateau cannot sink it.
    r = random.Random(4)
    head, tail = speech(1, n=60), speech(5, n=60)
    voice = head + [.8] * 60 + tail
    mouth = head + [.8 + r.uniform(-.15, .15) for _ in range(60)] + tail
    j = judged(mouth, voice)
    assert j["verdict"] == L.PASS, j
    # the plateau frames carry no weight: none of them is a "voice changing" frame
    import lip_gate.lip_gate as LG
    act = LG._active(LG._diff(LG._prep(voice)))
    assert not any(act[66:114]), "held-note frames must be skipped"


def test_no_changing_voice_is_unmeasured():
    j = L.judge(L.measure([.5] * 90, [.8] * 90, [CONTROL], FPS))
    assert j["verdict"] == L.UNMEASURED, j


def _mock(table):
    """generate() returns a name; measure_clip() returns canned series."""
    calls = []

    def gen(provider, spec):
        calls.append((provider, "improved" if "lead_in_s" in spec else "base"))
        return "%s-%s" % calls[-1]
    return calls, gen, lambda clip: L.measure(table[clip], VOICE,
                                              [CONTROL, speech(3)], FPS)


PIC = {"source_image": "closeup.png",
       "image_check": lambda img: {"pass": True}}   # picture gate has its own test
GOOD, FLAGGED = VOICE, lead(VOICE, 6)
BAD, BAD2 = [random.Random(9).random() for _ in VOICE], [random.Random(10).random() for _ in VOICE]


def test_pass_first_try_one_paid_job():
    calls, gen, meas = _mock({"kling-base": GOOD})
    row = L.run_gate("L1", gen, meas, {}, **PIC)
    assert row["verdict"] == L.PASS and row["paid_jobs"] == 1 and len(calls) == 1
    assert set(row["numbers"]) == {"offset_s", "lag_frames", "corr",
                                   "control_corr", "margin", "frozen_s"}


def test_flag_first_try_is_accepted_no_second_job():
    calls, gen, meas = _mock({"kling-base": FLAGGED})
    row = L.run_gate("L1", gen, meas, {}, **PIC)
    assert row["verdict"] == L.FLAG and row["flags"] and len(calls) == 1
    assert L.qc_check([row])["pass"]               # accepted and used


def test_fail_then_pass_on_second_try():
    calls, gen, meas = _mock({"kling-base": BAD, "kling-improved": GOOD})
    row = L.run_gate("L1", gen, meas, {}, **PIC)
    assert row["verdict"] == L.PASS and row["paid_jobs"] == 2
    assert calls == [("kling", "base"), ("kling", "improved")]


def test_two_try_cap_keeps_best_measured_take():
    calls, gen, meas = _mock({"kling-base": BAD2, "kling-improved": BAD})
    row = L.run_gate("L1", gen, meas, {}, **PIC)
    assert len(calls) == 2 == row["paid_jobs"]     # never a third paid job
    assert row["verdict"] == "FAIL_REPLACE" and not row["infinitalk_ab"]
    assert row["kept_clip"] in ("kling-base", "kling-improved")
    assert not L.qc_check([row])["pass"]


def test_unmeasured_is_reported_not_passed_and_not_retried():
    calls = []

    def gen(provider, spec):
        calls.append(provider)
        return "c"

    def meas(clip):
        raise ValueError(L.LIP_UNMEASURED + ": mediapipe/opencv/numpy not importable")
    row = L.run_gate("L1", gen, meas, {}, **PIC)
    assert row["verdict"] == L.UNMEASURED and len(calls) == 1
    assert not L.qc_check([row])["pass"]


def test_missing_mediapipe_or_model_raises_unmeasured():
    import mouth_landmarks as ML
    os.environ["LIPSYNC_FACE_MODEL"] = "/nonexistent/face_landmarker.task"
    try:
        ML.mouth_series("nope.mp4")
    except ML.Unmeasured as e:
        assert str(e).startswith(L.LIP_UNMEASURED)
    else:
        raise AssertionError("must not return a series")


def test_qc_check_fails_replaced_unmeasured_or_unnumbered():
    ok = {"line_id": "a", "verdict": L.PASS, "numbers": {}}
    assert L.qc_check([ok, dict(ok, verdict=L.FLAG)])["pass"]
    for v in ("FAIL_REPLACE", L.UNMEASURED):
        assert not L.qc_check([ok, dict(ok, line_id="b", verdict=v)])["pass"]
    assert not L.qc_check([{"line_id": "c", "verdict": L.PASS}])["pass"]


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
