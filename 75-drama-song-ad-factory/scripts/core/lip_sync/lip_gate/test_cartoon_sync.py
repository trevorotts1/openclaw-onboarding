#!/usr/bin/env python3
"""Cartoon sync-floor tests: the look-aware corr floor and the no-teeth close-up
wording (BUILD-PLAN W1-method-lipsync-U1; SPEC A7; conflict C12).
Stdlib only, $0, no client media, no provider call. Run:
  python3 test_cartoon_sync.py
  python3 -m pytest -q test_cartoon_sync.py

The measurement dicts are copied from the trial-oct13 gate outputs (read
2026-10-13):
  * REAL cartoon audio: corr 0.3911, control_corr 0.2342, margin +0.157,
    lag 0, face found in 100% of frames, mouth_pos 0.704, 216 frames,
    chance test PASSED, "FAIL (only LIP_CORR)" against the 0.40 floor;
  * the three MISMATCHED lines: corr 0.1705 / 0.1795 / 0.1161, control_corr
    0.3092 / 0.3335 / 0.4824, margins -0.139 / -0.154 / -0.366, lag -3 / +10 /
    +10, chance test FAILED on all three ("corr, chance, margin");
  * the CLOSED-MOUTH cartoon (trial B): corr 0.3124, control_corr 0.3423,
    margin -0.0299, lag 0, face 100%, mouth_pos 0.753, 112 frames,
    chance FAILED (reasons LIP_CORR, LIP_CHANCE, LIP_MARGIN).
The outputs printed each chance test as pass/fail, never as a share, so `pct`
carries that printed outcome: 0.0 for a pass (no roll beat the real corr; the
trial's own roll check topped out at 0.229 < 0.3911) and 0.21 for a failure
(a failure is pct > CHANCE_PCT_MAX = 0.20).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sync_check as S  # noqa: E402
import lip_gate as L  # noqa: E402
import lip_process as P  # noqa: E402

CARTOON = ("2d-hand-painted", "canvas-to-life", "canvas-to-3d")
LOOKS = CARTOON + ("lifelike-3d", "sketch-to-life")


def _m(corr, control_corr, margin, pct, lag=0, mouth_pos=0.704, frames=216):
    return {"corr": corr, "control_corr": control_corr, "margin": margin,
            "pct": pct, "lag_frames": lag, "offset_s": lag / 30.0,
            "frames_used": frames, "face_found": 1.0, "mouth_pos": mouth_pos,
            "unmeasurable": None}


C_REAL = _m(0.3911, 0.2342, 0.157, 0.0)            # trial C, real audio
C_WRONG = [_m(0.1705, 0.3092, -0.139, 0.21, -3),
           _m(0.1795, 0.3335, -0.154, 0.21, 10),
           _m(0.1161, 0.4824, -0.366, 0.21, 10)]    # trial C, three wrong lines
B_REAL = _m(0.3124, 0.3423, -0.0299, 0.21, 0, 0.753, 112)   # trial B, closed mouth


def test_constants_block_unchanged_plus_the_cartoon_floor():
    assert (S.MAX_LAG_FRAMES, S.CORR_FLOOR, S.MARGIN_FLOOR, S.SYNCED_MARGIN) == (10, .40, 0.0, .05)
    assert (S.CHANCE_PCT_MAX, S.ROLL_MIN_FRAMES, S.LOOKALIKE_CORR, S.MIN_FRAMES) == (.20, 15, .85, 45)
    assert S.CARTOON_CORR_FLOOR == 0.35 and S.CARTOON_LOOKS == CARTOON


def test_real_audio_passes_on_a_cartoon_look():
    for look in CARTOON:
        assert S.fail_tests(C_REAL, look) == [], (look, S.fail_tests(C_REAL, look))
        assert S.grade(C_REAL, look) == S.SYNCED, look
        assert S.verdict(C_REAL, look=look) == S.PASS, look
        assert S.verdict(C_REAL, True, look) == S.PASS, look
        j = L.judge(dict(C_REAL), look=look)
        assert (j["verdict"], j["grade"], j["reasons"]) == (L.PASS, S.SYNCED, []), look


def test_real_audio_still_fails_the_040_floor_on_every_other_look():
    for look in ("lifelike-3d", "sketch-to-life", None):
        assert S.fail_tests(C_REAL, look) == [S.R_CORR], look
        assert S.grade(C_REAL, look) == S.NOT_SYNCED, look
        assert S.verdict(C_REAL, look=look) == S.FAIL, look       # spoken line
        assert S.verdict(C_REAL, True, look) == S.UNDETERMINED, look
        j = L.judge(dict(C_REAL), look=look)
        assert (j["verdict"], j["reasons"]) == (L.FAIL, ["LIP_CORR"]), look


def test_wrong_audio_fails_every_look():
    for m in C_WRONG:
        for look in LOOKS:
            assert set(S.fail_tests(m, look)) == {S.R_CORR, S.R_CHANCE, S.R_MARGIN}, (m["corr"], look)
            assert S.grade(m, look) == S.NOT_SYNCED, (m["corr"], look)
            assert S.verdict(m, look=look) == S.FAIL, (m["corr"], look)
            assert S.verdict(m, True, look) == S.UNDETERMINED, (m["corr"], look)
            assert L.judge(dict(m), look=look)["verdict"] == L.FAIL, (m["corr"], look)


def test_trial_b_closed_mouth_still_fails_under_the_cartoon_floor():
    for look in LOOKS:
        assert set(S.fail_tests(B_REAL, look)) == {S.R_CORR, S.R_CHANCE, S.R_MARGIN}, look
        assert S.grade(B_REAL, look) == S.NOT_SYNCED, look
        assert S.verdict(B_REAL, look=look) == S.FAIL, look
        j = L.judge(dict(B_REAL), look=look)
        assert (j["verdict"], j["reasons"]) == (
            L.FAIL, ["LIP_CORR", "LIP_CHANCE", "LIP_MARGIN"]), look


def test_only_the_corr_test_moves():
    # corr clears 0.35: a lead under the SYNCED margin is still WEAK -> FLAG
    weak = dict(C_REAL, corr=0.36, margin=0.03, pct=0.0)
    assert S.fail_tests(weak, "2d-hand-painted") == [], weak
    assert S.grade(weak, "2d-hand-painted") == S.WEAK
    assert S.verdict(weak, look="2d-hand-painted") == L.FLAG
    assert S.verdict(weak, True, "2d-hand-painted") == L.UNDETERMINED
    # a negative lead fails on a cartoon look too
    assert S.fail_tests(dict(C_REAL, corr=0.50, margin=-0.02), "2d-hand-painted") == [S.R_MARGIN]
    # a chance share over the ceiling fails on a cartoon look too
    assert S.fail_tests(dict(C_REAL, pct=0.21), "2d-hand-painted") == [S.R_CHANCE]
    # an unmeasurable measurement is never a pass on any look
    m = dict(C_REAL, unmeasurable="face")
    assert S.verdict(m, look="2d-hand-painted") == S.UNMEASURABLE
    assert L.judge(m, look="2d-hand-painted")["verdict"] == L.UNMEASURABLE


def test_closeup_input_says_no_teeth_and_nothing_over_the_mouth():
    image = L.IMPROVED_INPUT["image"]
    for need in ("front-facing head-and-shoulders",
                 "lips gently closed or slightly parted",
                 "no teeth showing", "nothing over the mouth"):
        assert need in image, (need, image)
    assert "teeth" in image and "relaxed" not in image


def test_run_gate_passes_the_run_look_to_the_judge():
    seen = []

    def measure_clip(clip):
        return dict(C_REAL)

    def generate(provider, spec):
        seen.append(spec)
        return "clip"

    pic = {"source_image": "still.png",
           "image_check": lambda i: {"pass": True, "reasons": []}}
    rows = []
    for look in ("2d-hand-painted", "lifelike-3d", None):
        rows.append(L.run_gate("L1", generate, measure_clip, look=look,
                               acquire=lambda: None, **pic))
    judged = [r["attempts"][0]["judge"] for r in rows]
    assert [j["verdict"] for j in judged] == [L.PASS, L.FAIL, L.FAIL], judged
    assert [j["grade"] for j in judged] == [S.SYNCED, S.NOT_SYNCED, S.NOT_SYNCED], judged
    assert [j["reasons"] for j in judged] == [[], ["LIP_CORR"], ["LIP_CORR"]], judged
    assert len(seen) == 3 and all(s["try"] == 1 for s in seen), seen


def test_lip_process_passes_the_run_look_to_the_floors():
    weak = {"corr": 0.42, "pct": 0.0, "margin": 0.03, "unmeasurable": None}
    meas = lambda p: dict(C_REAL) if p == "cartoon.mp4" else dict(weak)  # noqa: E731
    takes = [{"path": "cartoon.mp4"}, {"path": "weak.mp4"}]
    # no look: the 0.40 floor holds, so the WEAK take outranks the cartoon take
    assert P.pick_kept(takes, meas, False)["take"] == "weak.mp4"
    # the run's look: the cartoon take is SYNCED and becomes the kept best
    for look in CARTOON:
        c = P.pick_kept(takes, meas, False, look=look)
        assert (c["take"], c["tag"], c["flag"]) == ("cartoon.mp4", P.KEPT_BEST, None), look
    # lifelike-3d keeps today's ranking
    assert P.pick_kept(takes, meas, False, look="lifelike-3d")["take"] == "weak.mp4"
    # a stub measure (verdict only, no numbers) keeps its own verdict, no crash
    stub = lambda p: {"verdict": "NOT_SYNCED", "corr": 0.1}  # noqa: E731
    c = P.pick_kept([{"path": "cartoon.mp4"}], stub, False, look="2d-hand-painted")
    assert (c["take"], c["tag"]) == ("cartoon.mp4", P.TAG_SPOKEN), c


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
