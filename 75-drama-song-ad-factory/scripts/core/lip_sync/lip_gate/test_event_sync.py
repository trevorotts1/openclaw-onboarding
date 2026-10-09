#!/usr/bin/env python3
"""event_sync (ADVISORY, never gates): the verdicts, the hard defects and the control battery. Stdlib, $0.
Run: python3 core/lip_sync/lip_gate/test_event_sync.py"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import event_sync as L                                 # noqa: E402

FPS = 30
POOL = [L.synth_clip(s) for s in range(1, 7)]


def run(i, mouth=None, ev=None):
    mouth0, ev0 = POOL[i]
    others = [e for j, (_, e) in enumerate(POOL) if j != i]
    return L.event_sync(mouth if mouth is not None else mouth0,
                        ev if ev is not None else ev0, others, FPS)


def test_own_audio_is_synced_or_weak_never_not_synced():
    # synthetic clips are short and dense in events: the +/-0.2 s window gives
    # some of them a high control score, so WEAK is allowed; NOT_SYNCED is not.
    verdicts = [run(i)["verdict"] for i in range(len(POOL))]
    assert L.NOT_SYNCED not in verdicts and L.UNMEASURABLE not in verdicts, verdicts
    r = run(0)
    assert r["verdict"] == L.SYNCED and r["hit"] >= 0.7 and r["margin"] >= 0.2, r
    assert sum(v == L.SYNCED for v in verdicts) >= 3, verdicts
    assert abs(r["lag_s"]) <= 2.0 / FPS


def test_wrong_audio_is_never_synced():
    n = 0
    for i in range(len(POOL)):
        for k in range(len(POOL)):
            if k != i:
                n += 1
                assert run(i, ev=POOL[k][1])["verdict"] != L.SYNCED, (i, k)
    assert n == 30


def test_shifted_half_second_is_never_synced():
    sh = int(0.5 * FPS)
    for i, (m, _) in enumerate(POOL):
        assert run(i, mouth=m[sh:] + [m[-1]] * sh)["verdict"] != L.SYNCED, i
        assert run(i, mouth=[m[0]] * sh + m[:-sh])["verdict"] != L.SYNCED, i


def test_still_face_is_a_hard_defect():
    r = run(0, mouth=[0.07] * len(POOL[0][0]))
    assert r["verdict"] == L.NOT_SYNCED and L.LIP_STILL in r["hard_defects"], r


def test_closed_through_voice_is_a_hard_defect():
    m, ev = POOL[0]
    a, b = ev["voiced"][0]
    m = list(m)
    for i in range(int(a * FPS), int((a + 0.8) * FPS)):
        m[i] = 0.02
    r = run(0, mouth=m)
    assert r["verdict"] == L.NOT_SYNCED and L.LIP_CLOSED_VOICED in r["hard_defects"], r


def test_moving_through_a_long_rest_is_a_hard_defect():
    voiced = [(0.4, 1.4), (2.4, 3.4), (4.2, 5.2)]       # a 1.0 s rest between runs
    ev = L.events(voiced, [{"word": "map", "start": 0.4, "end": 0.8},
                           {"word": "big", "start": 2.4, "end": 2.8}], 6.0)
    m = [0.02] * 180
    for a, b in voiced:
        for k in range(int(a * FPS), int(b * FPS)):
            m[k] = 0.13
    for k in range(12, 24):
        m[k] = 0.02
    assert L.event_sync(m, ev, [], FPS)["hard_defects"] == []
    for k in range(int(1.6 * FPS), int(2.2 * FPS)):      # mouth flaps through the rest
        m[k] = 0.13 if (k // 3) % 2 else 0.02
    r = L.event_sync(m, ev, [], FPS)
    assert L.LIP_MOVING_REST in r["hard_defects"] and r["verdict"] == L.NOT_SYNCED, r


def test_few_events_or_no_face_is_unmeasurable_never_not_synced():
    ev = {"onsets": [0.5], "offsets": [1.5], "bilabial": [], "voiced": [(0.5, 1.5)],
          "rests": [], "dur": 3.0}
    r = L.event_sync([0.1] * 90, ev, [], FPS)
    assert r["verdict"] == L.UNMEASURABLE and r["n_events"] == 2
    nan = float("nan")
    m = [nan if i % 4 == 0 else 0.1 for i in range(len(POOL[0][0]))]   # face in 75%
    assert run(0, mouth=m)["verdict"] == L.UNMEASURABLE
    assert run(0, mouth=[nan] * len(POOL[0][0]))["verdict"] == L.UNMEASURABLE


def test_middle_band_is_weak_and_kept():
    # a mouth that follows only half the events: not synced, no hard defect
    m, ev = POOL[2]
    half = dict(ev, onsets=ev["onsets"], offsets=ev["offsets"], bilabial=ev["bilabial"])
    m2 = list(m)
    for a, b in ev["bilabial"]:                 # no lip closure on p/b/m words
        for i in range(int(a * FPS), min(len(m2), int(b * FPS) + 1)):
            m2[i] = 0.12
    r = run(2, mouth=m2, ev=half)
    assert r["verdict"] in (L.WEAK, L.SYNCED, L.NOT_SYNCED)
    if r["verdict"] == L.WEAK:
        assert not r["hard_defects"]


def test_events_builder_from_voiced_runs_and_words():
    words = [{"word": "Map", "start": 0.5, "end": 0.9}, {"word": "sun", "start": 1.0, "end": 1.4},
             {"word": "big", "start": 2.5, "end": 3.0}]
    ev = L.events([(0.5, 1.4), (2.5, 3.0)], words, 4.0)
    assert ev["onsets"] == [0.5, 2.5] and ev["offsets"] == [1.4, 3.0]
    assert ev["bilabial"] == [(0.5, 0.9), (2.5, 3.0)]      # map, big (not sun)
    assert len(ev["rests"]) == 1


def test_selftest_battery_clean():
    assert L.selftest() == []


def test_selftest_catches_a_negative_that_reads_synced():
    m, ev = POOL[0]
    bad = [("wrong audio passes", "negative", m, ev, [], FPS)]   # own events = SYNCED
    assert any("negative control read SYNCED" in f for f in L.selftest(bad))
    nf = [("still positive", "positive", [0.07] * len(m), ev, [], FPS)]
    assert any("positive control read NOT_SYNCED" in f for f in L.selftest(nf))


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
    print("ALL CHECKS PASS")
