#!/usr/bin/env python3
"""H2 tests: measured lip-sync gate run (LSL002 + LSR001 rules, LSC001). Stdlib only, $0, mocked providers.

DONE-WHEN: each verdict path (PASS, ACCEPT_WITH_FLAG, FAIL, UNDETERMINED,
UNMEASURABLE) is reached, a sung line that is not a PASS is held for a person with
NO paid redo, the 2-try cap holds (try 2 only on a hard defect, only with a
changed input, KEPT_BEST_OF_2 after), event_sync is advisory only, and a missing
mediapipe is reported, never passed. The measurement itself is tested in test_sync_check.py. No client video.

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
        calls.append((provider, "try%s" % spec["try"]))
        return "%s-%s" % calls[-1]
    return calls, gen, lambda clip: m_of(table[clip])


PIC = {"source_image": "closeup.png",
       "image_check": lambda img: {"pass": True},   # picture gate has its own test
       "acquire": lambda: None}                      # KIE pacing bucket, injected
RETRY = {"retry_input": {"window": "next-best"}}
PERSON = dict(RETRY, person_verdict="DEFECT")   # a person marked a visible defect (LSP001)


def test_pass_first_try_one_paid_job():
    calls, gen, meas = _mock({"kling-try1": GOOD})
    row = L.run_gate("L1", gen, meas, **PIC)
    assert row["verdict"] == L.PASS and row["paid_jobs"] == 1 and len(calls) == 1
    assert set(row["numbers"]) == {"offset_s", "lag_frames", "corr",
                                   "control_corr", "margin", "pct"}


def test_try_one_uses_the_padded_cut_by_default():
    seen = []

    def gen(provider, spec):
        seen.append(spec)
        return "c"
    L.run_gate("L1", gen, lambda c: m_of(GOOD), **PIC)
    assert seen[0]["lead_in_s"] == 0.30 and seen[0]["tail_s"] == 0.20, seen[0]
    assert L.IMPROVED_INPUT["lead_in_s"] == 0.30 and L.IMPROVED_INPUT["tail_s"] == 0.20


def test_weak_first_try_is_accepted_with_flag_no_second_job():
    calls = []

    def gen(provider, spec):
        calls.append(provider)
        return "c"
    row = L.run_gate("L1", gen, lambda c: weak(), **RETRY, **PIC)
    assert row["verdict"] == L.FLAG and row["flags"] and len(calls) == 1
    assert L.qc_check([row])["pass"]               # accepted and used


def test_person_call_then_pass_on_second_try_with_changed_input():
    calls, gen, meas = _mock({"kling-try1": WRONG, "kling-try2": GOOD})
    row = L.run_gate("L1", gen, meas, **PERSON, **PIC)
    assert row["verdict"] == L.PASS and row["paid_jobs"] == 2 and row["kept_try"] == 2
    assert calls == [("kling", "try1"), ("kling", "try2")]


def test_try_two_refused_without_a_changed_input():
    calls, gen, meas = _mock({"kling-try1": WRONG, "kling-try2": GOOD})
    row = L.run_gate("L1", gen, meas, person_verdict="DEFECT", **PIC)  # no retry_input
    assert len(calls) == 1 and row["verdict"] == L.KEPT and "RETRY_REFUSED" in row["flag"]
    same = dict(L.IMPROVED_INPUT)
    calls, gen, meas = _mock({"kling-try1": WRONG, "kling-try2": GOOD})
    row = L.run_gate("L1", gen, meas, retry_input=same, person_verdict="DEFECT", **PIC)  # identical input
    assert len(calls) == 1 and row["verdict"] == L.KEPT


def test_no_automatic_paid_retry_on_any_checker_verdict():
    for sung in (False, True):
        calls, gen, meas = _mock({"kling-try1": WRONG, "kling-try2": GOOD})
        row = L.run_gate("L1", gen, meas, sung=sung, **RETRY, **PIC)   # changed input offered
        assert len(calls) == 1 == row["paid_jobs"], (sung, calls)
    calls, gen, meas = _mock({"kling-try1": WRONG, "kling-try2": GOOD})
    row = L.run_gate("L1", gen, meas, **RETRY, **PIC)
    assert row["verdict"] == L.KEPT and row["flag"]                    # kept best, flagged
    for pv in ("NOT_SYNCED", "FAIL", "WEAK"):                          # checker words are not a person's call
        calls, gen, meas = _mock({"kling-try1": WRONG, "kling-try2": GOOD})
        L.run_gate("L1", gen, meas, person_verdict=pv, **RETRY, **PIC)
        assert len(calls) == 1, pv


def test_two_try_cap_keeps_best_take_as_kept_best_of_2():
    calls, gen, meas = _mock({"kling-try1": WRONG2, "kling-try2": WRONG})
    strips = []
    row = L.run_gate("L1", gen, meas, make_strip=lambda c: strips.append(c) or "strip.png",
                     **PERSON, **PIC)
    assert len(calls) == 2 == row["paid_jobs"]     # never a third paid job
    assert row["verdict"] == L.KEPT == "KEPT_BEST_OF_2" and row["jobs_total"] == 2
    assert row["kept_clip"] in ("kling-try1", "kling-try2") and strips == [row["kept_clip"]]
    assert row["flag"] and row["mouth_strip"] == "strip.png" and "KEPT_BEST_OF_2" in row["receipt"]
    assert L.qc_check([row])["pass"]               # flagged, numbers, strip: accepted
    assert not L.qc_check([dict(row, mouth_strip=None)])["pass"]
    assert not L.qc_check([dict(row, flag=None)])["pass"]
    assert not L.qc_check([dict(row, jobs_total=3)])["pass"]


def test_prior_jobs_count_against_the_cap_before_anything_is_spent():
    calls, gen, meas = _mock({"kling-try1": GOOD})
    try:
        L.run_gate("L1", gen, meas, prior_jobs=2, **PIC)
    except L.LipTryLimit as e:
        assert e.code == L.LIP_TRY_LIMIT
    else:
        raise AssertionError("a third job was allowed")
    assert calls == []
    calls, gen, meas = _mock({"kling-try1": WRONG, "kling-try2": GOOD})
    row = L.run_gate("L1", gen, meas, prior_jobs=1, **PERSON, **PIC)  # only one try left
    assert len(calls) == 1 and row["jobs_total"] == 2 and row["verdict"] == L.KEPT


def test_hard_defect_seen_by_a_person_is_a_fail_and_allows_try_two():
    seen = {"kling-try1": dict(m_of(GOOD), hard_defects=["GARBLED_CHEST_TEXT"]),
            "kling-try2": m_of(GOOD)}
    calls = []

    def gen(provider, spec):
        calls.append(spec["try"])
        return "kling-try%d" % spec["try"]
    row = L.run_gate("L1", gen, lambda c: seen[c], **RETRY, **PIC)
    assert calls == [1, 2] and row["verdict"] == L.PASS and row["kept_try"] == 2
    j = L.judge(seen["kling-try1"])
    assert j["verdict"] == L.FAIL and "GARBLED_CHEST_TEXT" in j["reasons"]


def test_sung_not_pass_is_held_for_a_person_with_no_paid_redo():
    calls, gen, meas = _mock({"kling-try1": WRONG, "kling-try2": GOOD})
    row = L.run_gate("L1", gen, meas, sung=True, **RETRY, **PIC)
    assert row["verdict"] == L.UNDETERMINED and len(calls) == 1 == row["paid_jobs"], row
    q = L.qc_check([row])
    assert not q["pass"] and q["held_for_person"] == ["L1"]
    assert L.qc_check([dict(row, person_verdict=L.PASS)])["pass"]     # a person looked, it is fine
    calls, gen, meas = _mock({"kling-try1": GOOD})
    assert L.run_gate("L1", gen, meas, sung=True, **PIC)["verdict"] == L.PASS


def test_unmeasured_is_reported_not_passed_and_not_retried():
    calls = []

    def gen(provider, spec):
        calls.append(provider)
        return "c"

    def meas(clip):
        raise ValueError(L.LIP_UNMEASURED + ": mediapipe/opencv/numpy not importable")
    row = L.run_gate("L1", gen, meas, **RETRY, **PIC)
    assert row["verdict"] == L.UNMEASURABLE and len(calls) == 1
    assert not L.qc_check([row])["pass"]


def test_event_sync_is_advisory_only_and_never_gates():
    import event_sync as ES
    calls, gen, _ = _mock({})
    # gate says PASS, advisory says NOT_SYNCED: the row is still PASS, advisory recorded
    row = L.run_gate("L1", gen, lambda c: m_of(GOOD),
                     advisory=lambda c: {"verdict": ES.NOT_SYNCED}, **PIC)
    assert row["verdict"] == L.PASS and len(calls) == 1
    assert row["advisory_event_sync"] == {"verdict": ES.NOT_SYNCED}
    # gate says FAIL, advisory says SYNCED: still a fail (hard defect path)
    calls, gen, meas = _mock({"kling-try1": WRONG})
    row = L.run_gate("L1", gen, meas, advisory=lambda c: {"verdict": ES.SYNCED}, **PIC)
    assert row["verdict"] == L.KEPT
    # advisory that crashes changes nothing
    def boom(c):
        raise RuntimeError("x")
    calls, gen, meas = _mock({"kling-try1": GOOD})
    assert L.run_gate("L1", gen, meas, advisory=boom, **PIC)["verdict"] == L.PASS


def test_only_the_locked_model_and_no_infinitalk():
    seen = []

    def gen(provider, spec):
        seen.append(provider)
        return "c"
    row = L.run_gate("L1", gen, lambda c: m_of(WRONG), **PERSON, **PIC)
    assert set(seen) == {"kling"} and len(seen) == 2
    assert all(a["model"] == "kling/ai-avatar-standard" for a in row["attempts"])
    assert "infinitalk_ab" not in row and "ab_state" not in L.run_gate.__code__.co_varnames


def test_paid_submits_go_through_the_kie_governor():
    paced = []
    calls, gen, meas = _mock({"kling-try1": GOOD})
    L.run_gate("L1", gen, meas, **dict(PIC, acquire=lambda: paced.append(1)))
    assert paced, "kie_request did not pace the submit"


def test_kling_prompt_sings_or_says_one_emotion():
    s = L.kling_prompt("sung", "woman")
    assert " sings " in s and "speaks" not in s and "steady locked camera" in s
    assert "open and close" not in s
    p = L.kling_prompt("spoken", "man", "tired")
    assert " says " in p and "tired" in p and p.count("His") == 1
    try:
        L.kling_prompt("rap")
    except ValueError:
        pass
    else:
        raise AssertionError


def test_missing_mediapipe_or_model_raises_unmeasured():
    import mouth_landmarks as ML
    os.environ["LIPSYNC_FACE_MODEL"] = "/nonexistent/face_landmarker.task"
    try:
        ML.mouth_series("nope.mp4")
    except ML.Unmeasured as e:
        assert str(e).startswith(L.LIP_UNMEASURED)
    else:
        raise AssertionError("must not return a series")


def test_qc_check_fails_unflagged_unmeasured_undetermined_or_unnumbered():
    ok = {"line_id": "a", "verdict": L.PASS, "numbers": {}}
    assert L.qc_check([ok, dict(ok, verdict=L.FLAG)])["pass"]
    for v in ("FAIL_REPLACE", L.KEPT, L.UNMEASURABLE, L.UNDETERMINED):
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
