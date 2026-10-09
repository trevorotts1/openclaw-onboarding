#!/usr/bin/env python3
"""Tests for the parallel minute-lane planner (W-G-008). stdlib only, no network.

Run: python3 scripts/core/test_lane_planner.py

Required cases (unit W-G-008):
  * a 180 s plan splits into 3 lanes ON shot boundaries (48/48/84... i.e. every
    cut lands on a shot end; no shot is split, none goes missing);
  * a 90 s plan stays ONE lane;
  * the shared governor never exceeds 20 new requests per 10 s across 3 lanes
    (driven on a fake clock) and honours floor(18 / 3) = 6 per lane;
  * a ledger-known job tag is POLLED, never resubmitted.
Boundary battery: 119 stays 1, 120 splits, 179 stays 3, 180 stays 3.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

TMP = tempfile.mkdtemp(prefix="lane-planner-test-")
os.environ["DSAF_GOVERNOR_DIR"] = TMP          # never touch a real shared dir
os.environ.pop("KIE_API_KEY", None)

import lane_planner as LP  # noqa: E402
import load_governor as LG  # noqa: E402
import spend_ledger as L  # noqa: E402

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if not cond and detail else ""))
    if not cond:
        FAILS.append(name)

def check_eq(name, got, want):
    check(name, got == want, "got %r, want %r" % (got, want))

def shots_for(span, step=4.0):
    """A shot list covering [0, span] on a `step` grid (last shot ends at span)."""
    out, t, i = [], 0.0, 0
    while t < span - 1e-9:
        e = min(span, t + step)
        out.append({"shot_id": "s%02d" % i, "song_start": round(t, 3),
                    "song_end": round(e, 3)})
        t, i = e, i + 1
    return out

def lane_of(plan, shot_id):
    return [ln for ln in plan["lanes_detail"] if shot_id in ln["shot_ids"]]

def assert_lane_integrity(tag, plan, shots):
    """Union == all shots, disjoint, and EVERY shot entirely inside one lane."""
    ids = [s["shot_id"] for s in shots]
    got = [sid for ln in plan["lanes_detail"] for sid in ln["shot_ids"]]
    check("%s: every shot placed exactly once" % tag,
          sorted(got) == sorted(ids) and len(got) == len(set(got)),
          "placed=%r" % sorted(got))
    by_id = {s["shot_id"]: s for s in shots}
    inside = True
    for ln in plan["lanes_detail"]:
        for sid in ln["shot_ids"]:
            s = by_id[sid]
            if not (ln["song_start"] - 1e-6 <= s["song_start"]
                    and s["song_end"] <= ln["song_end"] + 1e-6):
                inside = False
    check("%s: every shot fully inside ONE lane (no shot split)" % tag, inside)
    cuts = [ln["song_end"] for ln in plan["lanes_detail"][:-1]]
    ends = {s["song_end"] for s in shots}
    check("%s: every lane cut is on a shot boundary" % tag,
          all(any(abs(c - e) <= 1e-6 for e in ends) for c in cuts), "cuts=%r" % cuts)

class FakeClock:
    """time.monotonic-style scalar clock; sleep() advances it instantly."""
    def __init__(self):
        self.t = 0.0
    def clock(self):
        return self.t
    def sleep(self, s):
        self.t += float(s)

def test_plane_lanes_and_boundaries():
    # 180 s -> 3 lanes, all cuts on shot boundaries.
    shots = shots_for(180.0)
    plan = LP.plan_lanes(shots, 180.0)
    check_eq("180 s plan splits into 3 lanes", plan["lanes"], 3)
    check_eq("180 s per-lane share floor(18/3)", plan["lane_share_per_10s"], 6)
    assert_lane_integrity("180s", plan, shots)
    check_eq("180 s lane 1 spans 0..60", (plan["lanes_detail"][0]["song_start"],
                                          plan["lanes_detail"][0]["song_end"]), (0.0, 60.0))
    check_eq("180 s lane 2 spans 60..120", (plan["lanes_detail"][1]["song_start"],
                                            plan["lanes_detail"][1]["song_end"]), (60.0, 120.0))
    check_eq("180 s lane 3 spans 120..180", (plan["lanes_detail"][2]["song_start"],
                                             plan["lanes_detail"][2]["song_end"]), (120.0, 180.0))
    # 90 s -> 1 lane, today's flow, one lane as today.
    p90 = LP.plan_lanes(shots_for(90.0), 90.0)
    check_eq("90 s plan stays 1 lane", p90["lanes"], 1)
    check_eq("1 lane keeps the unchanged 20/10 s budget", p90["lane_share_per_10s"], 20)
    check_eq("1 lane covers the whole song", (p90["lanes_detail"][0]["song_start"],
                                              p90["lanes_detail"][0]["song_end"]), (0.0, 90.0))
    # Boundary battery: 119 stays 1, 120 splits, 179 stays 3, 180 stays 3.
    for span, want in ((119.0, 1), (120.0, 2), (179.0, 3), (180.0, 3)):
        p = LP.plan_lanes(shots_for(span), span)
        check_eq("%g s -> %d lane(s)" % (span, want), p["lanes"], want)
        assert_lane_integrity("%gs" % span, p, shots_for(span))
        if p["lanes"] > 1:
            check("share floor(18/%d)=%d at %g s" % (p["lanes"], LP.lane_share(p["lanes"]), span),
                  p["lane_share_per_10s"] == LP.lane_share(p["lanes"]))
    check_eq("lane_count 119 s", LP.lane_count(119.0), 1)
    check_eq("lane_count 120 s splits", LP.lane_count(120.0), 2)
    check_eq("lane_count 179 s", LP.lane_count(179.0), 3)
    check_eq("lane_count 180 s", LP.lane_count(180.0), 3)
    # Shared steps run ONCE, before the split; fan-in once, after the lanes.
    check_eq("shared steps before the split are named once",
             sorted(plan["shared_steps_before"]), sorted(LP.SHARED_STEPS_BEFORE))
    check("shared steps are unique (never per lane)",
          len(plan["shared_steps_before"]) == len(set(plan["shared_steps_before"])))
    check("wrapper/fan-in steps are unique too",
          len(plan["shared_steps_after"]) == len(set(plan["shared_steps_after"])))
    for named in ("song", "song-checker", "plan-shot-list", "character",
                  "closeup-picture-gate"):
        check("shared step present: %s" % named, named in plan["shared_steps_before"])
    for named in ("one-edit-full-song", "one-independent-checker-whole-ad", "one-repair"):
        check("fan-in step present: %s" % named, named in plan["shared_steps_after"])

def test_fail_closed():
    def raises(code, fn):
        try:
            fn()
        except LP.LanePlanError as e:
            return e.code == code, "code=%s" % e.code
        return False, "no error"
    ok, d = raises("NO_SHOTS", lambda: LP.plan_lanes([], 180.0))
    check("empty shot list fails closed", ok, d)
    ok, d = raises("LANES_OVER_SHOTS", lambda: LP.plan_lanes(shots_for(180.0)[:2], 180.0))
    check("fewer shots than lanes fails closed", ok, d)
    tight = [{"shot_id": "a", "song_start": 0.0, "song_end": 10.0},
             {"shot_id": "b", "song_start": 10.0, "song_end": 50.0},
             {"shot_id": "c", "song_start": 50.0, "song_end": 179.0}]
    ok, d = raises("LANE_BOUNDARY_INSIDE_SHOT", lambda: LP.plan_lanes(tight, 179.0))
    check("a cut that would split a shot fails closed (never cuts mid-shot)", ok, d)

def test_shared_governor_fake_clock():
    fc = FakeClock()
    gov = LP.SharedGovernor(3, clock=fc.clock, sleep=fc.sleep)
    check_eq("3-lane per-lane share", gov.lane_share, 6)
    stamps = []
    for i in range(60):                      # 3 lanes x 20 requests, bursting
        lane = i % 3
        gov.acquire(lane)
        stamps.append((fc.t, lane))
    # Never more than 20 new requests in ANY rolling 10 s window...
    worst = max(sum(1 for t, _ in stamps if t0 <= t < t0 + 10.0 - 1e-9)
                for t0, _ in stamps)
    check("shared governor <= 20 per 10 s across 3 lanes", worst <= 20, "worst=%d" % worst)
    # ... and never more than the per-lane share inside any lane's window.
    for lane in range(3):
        mine = [(t, l) for t, l in stamps if l == lane]
        worst_lane = max(sum(1 for t, _ in mine if t0 <= t < t0 + 10.0 - 1e-9)
                         for t0, _ in mine)
        check("lane %d <= floor(18/3)=6 per 10 s" % lane, worst_lane <= 6,
              "worst=%d" % worst_lane)
    # 429 is resubmitted, never dropped: first answer rate-limits, second runs.
    fc2 = FakeClock()
    gov2 = LP.SharedGovernor(3, clock=fc2.clock, sleep=fc2.sleep)
    calls = []
    def flaky():
        calls.append(fc2.t)
        return "HTTP 429 too many requests" if len(calls) == 1 else {"ok": 1}
    res = gov2.submit(0, flaky, label="lane-0/lipsync-429")
    check_eq("a 429 is resubmitted and the job still runs", res, {"ok": 1})
    check_eq("429 path took exactly 2 calls (not dropped)", len(calls), 2)
    check("429 backoff waited (>0 s on the fake clock)", calls[1] > calls[0])
    # The heavy local gate is the EXISTING machine-wide governor, cap 2.
    check("lanes use the existing heavy gate (one identity)",
          LP.heavy_slot is LG.heavy_slot)
    check_eq("heavy gate cap is 2 across all lanes", LG.slot_cap(), 2)

def test_ledger_known_tag_is_polled():
    db = os.path.join(TMP, "lane-ledger.sqlite")
    run = "run-lane-1"
    init = L.init_run(db, run, ceiling=5000)
    check_eq("ledger run created", init["outcome"], "ok")
    plan = L.plan(db, run, "lane0-shot07-lipsync", "att-1", "digest-1",
                  estimated_cost=100, stage="lipsync")
    check_eq("tag planned into the ledger", plan["outcome"], "ok")
    check_eq("ledger-known tag is POLLED, not resubmitted",
             LP.classify_tag(db, run, "lane0-shot07-lipsync"), "poll")
    art = os.path.join(TMP, "lane0-shot07.mp4")
    with open(art, "wb") as f:
        f.write(b"fake clip")
    check_eq("ledger-known tag with a finished file is REUSED",
             LP.classify_tag(db, run, "lane0-shot07-lipsync", art), "reuse")
    check_eq("an unknown tag is a genuinely new submit",
             LP.classify_tag(db, run, "lane1-shot22-lipsync"), "submit")
    check_eq("no file + no tag still submits",
             LP.classify_tag(db, run, "lane2-shot40-motion",
                             os.path.join(TMP, "missing.mp4")), "submit")
    try:
        LP.classify_tag(os.path.join(TMP, "nope.sqlite"), run, "x")
        check("missing ledger fails closed", False, "no error")
    except LP.LanePlanError as e:
        check("missing ledger fails closed", e.code == "NO_LEDGER", e.code)

def main():
    test_plane_lanes_and_boundaries()
    test_fail_closed()
    test_shared_governor_fake_clock()
    test_ledger_known_tag_is_polled()
    if FAILS:
        print("FAILED: %d check(s): %s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("ALL PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main())
