#!/usr/bin/env python3
"""H2 tests (LSR001 rewrite): the lip-sync gate's TRY RULE, receipts, QC and prompt.
Stdlib only, $0, mocked providers.

DONE-WHEN: at most 2 Kling jobs per segment (every name variant counted); try 2
only on a HARD defect and only with a CHANGED input; after that the best take is
kept and the receipt says KEPT_BEST_OF_2; WEAK never re-triggers; no InfiniTalk;
paid submits go through kie_request and landmarks through heavy_slot.

Run: python3 core/lip_sync/lip_gate/test_lip_gate_h2.py
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import lip_gate as L                                   # noqa: E402

FPS = 30


def res(verdict, hit=0.8, margin=0.3, defects=(), lag=0.0):
    return {"verdict": verdict, "hit": hit, "control_hit": round(hit - margin, 4),
            "margin": margin, "lag_s": lag, "n_events": 10, "face_frac": 1.0,
            "hard_defects": list(defects), "fps": FPS}


def hard(hit=0.2):
    return res(L.NOT_SYNCED, hit, -0.1, [L.LIP_STILL])


class Env:
    """Mock provider + measurer + KIE pacing counter."""

    def __init__(self, table):
        self.table, self.calls, self.acquired = table, [], 0

    def gen(self, provider, spec):
        self.calls.append((provider, spec["try"]))
        return "clip-t%d" % spec["try"]

    def meas(self, clip):
        return self.table[clip]

    def acquire(self):
        self.acquired += 1

    def run(self, line="L1", **kw):
        kw.setdefault("source_image", "closeup.png")
        kw.setdefault("image_check", lambda img: {"pass": True})
        return L.run_gate(line, self.gen, self.meas, acquire=self.acquire, **kw)


CHANGED = {"window": "next-best", "lead_in_s": 0.30, "tail_s": 0.20}


def test_try1_synced_is_one_job_and_pass():
    e = Env({"clip-t1": res(L.SYNCED)})
    row = e.run(retry_input=CHANGED)
    assert row["verdict"] == "PASS" and row["jobs_used"] == 1 and e.calls == [("kling", 1)]
    assert e.acquired == 1, "every paid submit goes through kie_request"
    assert set(row["numbers"]) == {"hit", "control_hit", "margin", "lag_s",
                                   "n_events", "face_frac"}


def test_try1_is_the_padded_cut_by_default():
    assert L.IMPROVED_INPUT["lead_in_s"] == 0.30 and L.IMPROVED_INPUT["tail_s"] == 0.20
    e = Env({"clip-t1": res(L.SYNCED)})
    row = e.run()
    assert row["attempts"][0]["input"]["lead_in_s"] == 0.30


def test_hard_defect_gets_try2_with_changed_input_then_keeps_best():
    e = Env({"clip-t1": hard(0.30), "clip-t2": hard(0.35)})
    row = e.run(retry_input=CHANGED)
    assert e.calls == [("kling", 1), ("kling", 2)] and row["jobs_used"] == 2
    assert row["verdict"] == L.KEPT == "KEPT_BEST_OF_2"
    assert row["kept_try"] == 2 and row["flag"] and "KEPT_BEST_OF_2 (t2)" in row["receipt"]
    assert row["attempts"][1]["input"]["window"] == "next-best"


def test_try2_better_synced_wins_and_passes():
    e = Env({"clip-t1": hard(), "clip-t2": res(L.SYNCED)})
    row = e.run(retry_input=CHANGED)
    assert row["verdict"] == "PASS" and row["kept_try"] == 2 and row["flag"] is None


def test_never_a_third_job():
    e = Env({"clip-t1": hard(), "clip-t2": hard()})
    e.run(retry_input=CHANGED)
    assert len(e.calls) == 2 and {c[0] for c in e.calls} == {"kling"}


def test_weak_and_unmeasurable_never_trigger_try2():
    for v in (res(L.WEAK, 0.55, 0.05), res(L.UNMEASURABLE, 0.0, 0.0)):
        e = Env({"clip-t1": v})
        row = e.run(retry_input=CHANGED)
        assert e.calls == [("kling", 1)], v["verdict"]
        assert row["verdict"] == L.KEPT and "UNDETERMINED" in row["flag"]


def test_identical_or_missing_retry_input_is_refused_not_spent():
    for retry in (None, dict(L.IMPROVED_INPUT)):
        e = Env({"clip-t1": hard()})
        row = e.run(retry_input=retry)
        assert e.calls == [("kling", 1)] and "RETRY_REFUSED" in row["flag"]


def test_prior_jobs_count_against_the_two_tries():
    e = Env({"clip-t1": hard()})
    row = e.run(prior_jobs=1, retry_input=CHANGED)     # one try left
    assert e.calls == [("kling", 1)] and row["jobs_total"] == 2
    e2 = Env({})
    try:
        e2.run(prior_jobs=2, retry_input=CHANGED)
    except L.LipTryLimit as ex:
        assert ex.code == L.LIP_TRY_LIMIT
    else:
        raise AssertionError("a 3rd paid job was allowed")
    assert e2.calls == [] and e2.acquired == 0


def test_score_ranking_order():
    synced = res(L.SYNCED)
    weak = res(L.WEAK, 0.6, 0.1)
    unm = res(L.UNMEASURABLE, 0, 0)
    ns = hard(0.3)
    order = sorted([ns, unm, weak, synced], key=L.score, reverse=True)
    assert [o["verdict"] for o in order] == [L.SYNCED, L.WEAK, L.UNMEASURABLE, L.NOT_SYNCED]
    # a weak take with an eye-spotted hard defect loses to a clean unmeasurable one
    flawed = res(L.WEAK, 0.6, 0.1, defects=["GARBLED_FACE"])
    assert L.score(unm) > L.score(flawed)
    # same tier: more hit, then smaller |lag|
    assert L.score(res(L.WEAK, 0.7, 0.1)) > L.score(res(L.WEAK, 0.6, 0.1))
    assert L.score(res(L.WEAK, 0.6, 0.1, lag=0.03)) > L.score(res(L.WEAK, 0.6, 0.1, lag=0.2))


def test_qc_check_accepts_pass_and_flagged_kept_rows_only():
    ok = {"line_id": "a", "verdict": "PASS", "numbers": {}}
    kept = {"line_id": "k", "verdict": L.KEPT, "numbers": {}, "flag": "WEAK",
            "mouth_strip": "k-strip.png", "jobs_total": 2}
    assert L.qc_check([ok, kept])["pass"]
    for broken in (dict(kept, flag=None), dict(kept, mouth_strip=None),
                   {k: v for k, v in kept.items() if k != "numbers"},
                   dict(kept, jobs_total=3), dict(kept, verdict="FAIL_REPLACE")):
        assert not L.qc_check([ok, broken])["pass"], broken
    assert not L.qc_check([{"line_id": "c", "verdict": "PASS"}])["pass"]


def test_kept_row_carries_the_mouth_strip():
    e = Env({"clip-t1": hard(0.2), "clip-t2": hard(0.3)})
    row = e.run(retry_input=CHANGED, make_strip=lambda clip: clip + ".strip.png")
    assert row["mouth_strip"] == "clip-t2.strip.png" and L.qc_check([row])["pass"]


def test_no_infinitalk_anywhere():
    src = open(os.path.join(HERE, "lip_gate.py"), encoding="utf-8").read()
    assert "ab_state" not in src and "infinitalk_ab" not in src
    assert 'generate("kling"' in src and 'generate("infinitalk"' not in src


def test_wiring_kie_request_and_heavy_slot():
    src = open(os.path.join(HERE, "lip_gate.py"), encoding="utf-8").read()
    assert "_LG.kie_request(" in src and "generation=True" in src
    assert 'heavy_slot("lip-gate-landmarks")' in src and "run_ffmpeg" in src


def test_kling_prompt_sings_or_says_one_emotion_steady_camera():
    s = L.kling_prompt("sung", "woman", "calm, earnest")
    assert " sings this line" in s and "speaks" not in s
    assert "Minimal head movement, steady locked camera" in s
    assert "exact time" not in s and "open and close" not in s
    t = L.kling_prompt("spoken", "man", "warm and direct")
    assert " says this line" in t and "sings" not in t and t.count("His") == 1
    try:
        L.kling_prompt("shouted")
    except ValueError:
        pass
    else:
        raise AssertionError


def test_selftest_passes_and_fails_a_rubber_stamp():
    assert L.selftest() == []
    real = L.event_sync
    try:
        L.event_sync = lambda *a, **k: res(L.SYNCED)      # the old v2 bug
        fails = L.selftest()
    finally:
        L.event_sync = real
    assert any("negative control read SYNCED" in f for f in fails)


def test_voiced_runs_and_envelope_ffmpeg():
    env = [0.0] * 5 + [1.0] * 30 + [0.0] * 3 + [1.0] * 10 + [0.0] * 20
    runs = L.voiced_runs(env, FPS)
    assert len(runs) == 1, runs                  # the 0.1 s gap is merged (< 0.12 s)
    ff = shutil.which("ffmpeg")
    if not ff:
        print("skip envelope (no ffmpeg)")
        return
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "t.wav")
        subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i",
                        "sine=f=300:d=1,apad=pad_dur=3", "-t", "4", wav,
                        "-y"], check=True)
        env = L.envelope(wav, fps=FPS, ffmpeg=ff, start=0.0, dur=2.0)
    assert abs(len(env) - 60) <= 2
    assert sum(env[:25]) / 25 > 20 * (sum(env[40:]) / 20 + 1e-9)


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
