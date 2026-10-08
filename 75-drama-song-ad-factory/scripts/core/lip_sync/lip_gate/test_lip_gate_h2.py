#!/usr/bin/env python3
"""H2 tests: measured lip-sync gate run (LSL002). Stdlib only, $0, mocked providers.

DONE-WHEN: each verdict path (PASS, ACCEPT_WITH_FLAG, FAIL, UNDETERMINED,
UNMEASURABLE) is reached, a sung line that is not a PASS is held for a person with
NO paid redo, the 2-try cap holds, and a missing mediapipe is reported, never
passed. The measurement itself is tested in test_sync_check.py. No client video.

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

FPS = 30.0


def speech(seed, n=150):
    r, out = random.Random(seed), []
    while len(out) < n:
        out += [r.uniform(.6, 1.0)] * r.randint(3, 6) + [.05] * r.randint(2, 4)
    return out[:n]


VOICE, OTHERS = speech(1), [speech(2), speech(3)]
GOOD = VOICE                                  # mouth follows the audio: SYNCED
WRONG = OTHERS[0]                             # mouth follows another line: NOT_SYNCED
WRONG2 = OTHERS[1]


def m_of(mouth):
    return L.measure(mouth, VOICE, OTHERS, FPS)


def weak():
    """A measurement graded WEAK (margin 0 to 0.05)."""
    return dict(m_of(GOOD), margin=0.02)


def test_judge_maps_every_verdict():
    assert L.judge(m_of(GOOD))["verdict"] == L.PASS
    j = L.judge(weak())
    assert j["verdict"] == L.FLAG and j["flags"] and j["reasons"] == [], j
    j = L.judge(m_of(WRONG))
    assert j["verdict"] == L.FAIL and "LIP_MARGIN" in j["reasons"], j
    j = L.judge(m_of(WRONG), sung=True)
    assert j["verdict"] == L.UNDETERMINED and L.LIP_HELD_FOR_PERSON in j["reasons"], j
    j = L.judge(weak(), sung=True)
    assert j["verdict"] == L.UNDETERMINED and j["flags"] == [], j
    assert L.judge(L.measure([.3] * 150, VOICE, OTHERS, FPS))["verdict"] == L.UNMEASURABLE


def _mock(table):
    """generate() returns a name; measure_clip() returns canned measurements."""
    calls = []

    def gen(provider, spec):
        calls.append((provider, "improved" if "lead_in_s" in spec else "base"))
        return "%s-%s" % calls[-1]
    return calls, gen, lambda clip: m_of(table[clip])


PIC = {"source_image": "closeup.png",
       "image_check": lambda img: {"pass": True}}   # picture gate has its own test


def test_pass_first_try_one_paid_job():
    calls, gen, meas = _mock({"kling-base": GOOD})
    row = L.run_gate("L1", gen, meas, {}, **PIC)
    assert row["verdict"] == L.PASS and row["paid_jobs"] == 1 and len(calls) == 1
    assert set(row["numbers"]) == {"offset_s", "lag_frames", "corr",
                                   "control_corr", "margin", "pct"}


def test_weak_first_try_is_accepted_with_flag_no_second_job():
    calls = []

    def gen(provider, spec):
        calls.append(provider)
        return "c"
    row = L.run_gate("L1", gen, lambda c: weak(), {}, **PIC)
    assert row["verdict"] == L.FLAG and row["flags"] and len(calls) == 1
    assert L.qc_check([row])["pass"]               # accepted and used


def test_spoken_fail_then_pass_on_second_try():
    calls, gen, meas = _mock({"kling-base": WRONG, "kling-improved": GOOD})
    row = L.run_gate("L1", gen, meas, {}, **PIC)
    assert row["verdict"] == L.PASS and row["paid_jobs"] == 2
    assert calls == [("kling", "base"), ("kling", "improved")]


def test_two_try_cap_keeps_best_measured_take():
    calls, gen, meas = _mock({"kling-base": WRONG2, "kling-improved": WRONG})
    row = L.run_gate("L1", gen, meas, {}, **PIC)
    assert len(calls) == 2 == row["paid_jobs"]     # never a third paid job
    assert row["verdict"] == "FAIL_REPLACE" and not row["infinitalk_ab"]
    assert row["kept_clip"] in ("kling-base", "kling-improved")
    assert not L.qc_check([row])["pass"]


def test_sung_not_pass_is_held_for_a_person_with_no_paid_redo():
    calls, gen, meas = _mock({"kling-base": WRONG, "kling-improved": GOOD})
    row = L.run_gate("L1", gen, meas, {}, sung=True, **PIC)
    assert row["verdict"] == L.UNDETERMINED and len(calls) == 1 == row["paid_jobs"], row
    q = L.qc_check([row])
    assert not q["pass"] and q["held_for_person"] == ["L1"]
    assert L.qc_check([dict(row, person_verdict=L.PASS)])["pass"]     # a person looked, it is fine
    calls, gen, meas = _mock({"kling-base": GOOD})
    assert L.run_gate("L1", gen, meas, {}, sung=True, **PIC)["verdict"] == L.PASS


def test_unmeasured_is_reported_not_passed_and_not_retried():
    calls = []

    def gen(provider, spec):
        calls.append(provider)
        return "c"

    def meas(clip):
        raise ValueError(L.LIP_UNMEASURED + ": mediapipe/opencv/numpy not importable")
    row = L.run_gate("L1", gen, meas, {}, **PIC)
    assert row["verdict"] == L.UNMEASURABLE and len(calls) == 1
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


def test_qc_check_fails_replaced_unmeasured_undetermined_or_unnumbered():
    ok = {"line_id": "a", "verdict": L.PASS, "numbers": {}}
    assert L.qc_check([ok, dict(ok, verdict=L.FLAG)])["pass"]
    for v in ("FAIL_REPLACE", L.UNMEASURABLE, L.UNDETERMINED):
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
