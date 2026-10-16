#!/usr/bin/env python3
"""test_item15_swarm_forcing.py -- FIX-PLAN Item 15: swarm FORCING.

THE FAULT (Reader E's swarm ceiling analysis). Every width in the engine
was a min() of ceilings, so the swarm could only ever slow down: the
routing stamp folded probe -> mode ceiling -> admission, the pool min()d
that against unit count and env override, and the PRES-036 ready queue
collapsed an UNBOUNDED capacity measurement to a hard-coded 8. Nothing
anywhere treated a planned width as a TARGET to reach and hold, replaced
a worker that died mid-phase, or recorded WHY the swarm ran narrower
than planned -- a deck on a strong box with an uncapped provider crawled
at fallback widths (8, 3, 12) written for safety, not speed, and "why is
it running at 3" had no answer in any record. Worse, a worker invocation
that died by raising a BaseException escaped fanout._run_one's
`except Exception` net, re-raised on the admitting thread at
fut.result(), and crashed run_units outright.

WHAT THESE TESTS PROVE (the brief's four required tests, plus the record
shapes they depend on):

  1. A planned width is REACHED AND HELD in the fanout harness: the
     pool's own concurrency tracker and the progress artifact's swarm
     block both show peak == target while work remains.
  2. A killed worker is REPLACED: a unit whose first invocation raises a
     BaseException completes ok on a fresh invocation, the death and the
     replacement are swarm events, and run_units does not raise. A unit
     whose worker ALWAYS dies fails VISIBLY with the death named (the
     pre-Item-15 behaviour was an exception escaping run_units).
  3. A capacity-bound shortfall names the CAPACITY limiter: planned 12
     against the ollama $100 tier's reserve-adjusted available (limit 10,
     reserve 2, so dispatch sees 8 -- capacity.py ACCOUNT_LIMITS) yields
     target 8, shortfall, binding capacity_cap = 8. A hardware-bound
     variant names hardware_budget instead, including through a routing
     stamp shaped like the real admission fold.
  4. MODE_OPERATOR_CEILING still refuses above it: planned 500 in ultra
     mode yields 400 named mode_operator_ceiling; planned 30 in standard
     yields 25; and a pool handed the standard decision never exceeds 25
     concurrent workers.
  5. The ready queue's UNBOUNDED width is the mode ceiling (25 standard),
     not the old hard-coded 8; a measured capacity of 3 binds as
     capacity_cap; a deepseek-scale capacity leaves the mode ceiling
     binding with no shortfall.

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory. No network, no model spend: stub workers only.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import fanout  # noqa: E402
from presentation_job import width_controller as wc  # noqa: E402
from presentation_job.capacity import UNBOUNDED  # noqa: E402


class WorkerKilled(BaseException):
    """A worker death _run_one's `except Exception` net cannot catch."""


def _units(n: int) -> list:
    return [fanout.Unit(key=f"u-{i:02d}", payload={}) for i in range(1, n + 1)]


class _Rendezvous:
    """Concurrency tracker whose workers wait until `width` of them are
    inside at once (or a timeout): peak == width is then proof the pool
    genuinely held that width, and a pool narrower than the rendezvous
    width can never fake it (it just runs slower and fails the assert)."""

    def __init__(self, width: int) -> None:
        self.width = width
        self.active = 0
        self.peak = 0
        self.lock = threading.Lock()
        self.full = threading.Event()

    def run(self, sleep_s: float = 0.02) -> None:
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            if self.active >= self.width:
                self.full.set()
        self.full.wait(timeout=5)
        time.sleep(sleep_s)
        with self.lock:
            self.active -= 1


def _progress_swarm(run_dir: Path, phase_id: str) -> dict:
    path = fanout._progress_path(run_dir, phase_id)
    assert path.is_file(), f"no fanout progress artifact at {path}"
    state = json.loads(path.read_text(encoding="utf-8"))
    assert "swarm" in state, f"progress artifact carries no swarm block: {state}"
    return state["swarm"]


# ---------------------------------------------------------------------------
# 1. A planned width is reached and held.
# ---------------------------------------------------------------------------
def test_planned_width_is_reached_and_held(tmp_path):
    decision = wc.decide_width(6, mode="standard",
                               capacity_available=UNBOUNDED,
                               hardware_budget=64, ready_work=12)
    assert decision["target_width"] == 6
    assert decision["shortfall"] is False
    assert decision["binding_constraint"] == wc.LIMITER_DECLARED

    rz = _Rendezvous(6)

    def worker(unit):
        rz.run()
        return fanout.UnitResult(key=unit.key, status="ok", attempts=1)

    events: list = []
    results = fanout.run_units(
        _units(12), worker, workers=decision["target_width"],
        run_dir=tmp_path, phase_id="P-ITEM15-HELD", retry_cap=1,
        swarm_plan=decision, swarm_event_cb=events.append)

    assert [r.status for r in results] == ["ok"] * 12
    assert rz.peak == 6, (
        f"pool peaked at {rz.peak}, not the planned width 6 -- the width "
        f"was a ceiling it approached, not a target it held")
    swarm = _progress_swarm(tmp_path, "P-ITEM15-HELD")
    assert swarm["planned_width"] == 6
    assert swarm["target_width"] == 6
    assert swarm["peak_width"] == 6
    assert swarm["achieved_width"] == 6
    assert swarm["runtime_shortfall"] is False
    assert swarm["worker_deaths"] == 0
    assert not [e for e in events if e.get("event") == "forcing_shortfall"]


# ---------------------------------------------------------------------------
# 2. A killed worker is replaced; an always-dying worker fails VISIBLY.
# ---------------------------------------------------------------------------
def test_killed_worker_is_replaced(tmp_path):
    decision = wc.decide_width(3, mode="standard",
                               capacity_available=UNBOUNDED,
                               hardware_budget=64, ready_work=9)
    rz = _Rendezvous(3)
    invocations: dict = {}
    lock = threading.Lock()

    def worker(unit):
        with lock:
            n = invocations.get(unit.key, 0)
            invocations[unit.key] = n + 1
        if unit.key == "u-03" and n == 0:
            raise WorkerKilled("simulated mid-phase worker death")
        rz.run()
        return fanout.UnitResult(key=unit.key, status="ok", attempts=1)

    events: list = []
    results = fanout.run_units(
        _units(9), worker, workers=decision["target_width"],
        run_dir=tmp_path, phase_id="P-ITEM15-REPLACE", retry_cap=1,
        swarm_plan=decision, swarm_event_cb=events.append)

    # run_units did not raise (the pre-Item-15 pool crashed here) and the
    # killed unit completed on its replacement invocation.
    assert [r.status for r in results] == ["ok"] * 9
    assert invocations["u-03"] == 2, invocations
    died = [e for e in events if e.get("event") == "worker_died"]
    replaced = [e for e in events if e.get("event") == "worker_replaced"]
    assert [e["unit"] for e in died] == ["u-03"], events
    assert [e["unit"] for e in replaced] == ["u-03"], events
    # The width recovered to the target after the death: the pool HELD 3.
    assert rz.peak == 3
    swarm = _progress_swarm(tmp_path, "P-ITEM15-REPLACE")
    assert swarm["worker_deaths"] == 1
    assert swarm["workers_replaced"] == 1
    assert swarm["runtime_shortfall"] is False


def test_always_dying_worker_fails_visibly_and_pool_survives(tmp_path):
    decision = wc.decide_width(3, mode="standard",
                               capacity_available=UNBOUNDED,
                               hardware_budget=64, ready_work=6)

    def worker(unit):
        if unit.key == "u-02":
            raise WorkerKilled("this worker never survives")
        time.sleep(0.01)
        return fanout.UnitResult(key=unit.key, status="ok", attempts=1)

    results = fanout.run_units(
        _units(6), worker, workers=3, run_dir=tmp_path,
        phase_id="P-ITEM15-DIES", retry_cap=1,
        swarm_plan=decision, swarm_event_cb=lambda e: None)

    by_key = {r.key: r for r in results}
    assert by_key["u-02"].status == "failed"
    assert any("worker died" in reason for reason in by_key["u-02"].reasons), \
        by_key["u-02"].reasons
    assert all(by_key[k].status == "ok" for k in by_key if k != "u-02")
    swarm = _progress_swarm(tmp_path, "P-ITEM15-DIES")
    assert swarm["worker_deaths"] == 2  # initial death + replacement death
    assert swarm["workers_replaced"] == 1


# ---------------------------------------------------------------------------
# 3. A capacity-bound shortfall names the capacity cap (and a
#    hardware-bound one names the hardware budget).
# ---------------------------------------------------------------------------
def test_capacity_shortfall_names_capacity_cap():
    # 8 is not arbitrary: capacity.py ACCOUNT_LIMITS gives the ollama
    # $100 tier limit 10 with reserve 2, so resolve_capacity reports
    # available == 8 to dispatch. Planned 12 against that account MUST
    # stop at 8 and say capacity_cap = 8.
    d = wc.decide_width(12, mode="standard", capacity_available=8,
                        hardware_budget=100, ready_work=40)
    assert d["target_width"] == 8
    assert d["shortfall"] is True
    assert d["binding_constraint"] == wc.LIMITER_CAPACITY_CAP
    assert d["binding_value"] == 8
    reason = wc.shortfall_reason(d)
    assert "capacity_cap" in reason and "8" in reason


def test_hardware_shortfall_names_hardware_budget():
    d = wc.decide_width(12, mode="standard", capacity_available=UNBOUNDED,
                        hardware_budget=2, ready_work=40)
    assert d["target_width"] == 2
    assert d["shortfall"] is True
    assert d["binding_constraint"] == wc.LIMITER_HARDWARE_BUDGET
    assert d["binding_value"] == 2


def test_stamp_decision_names_the_admission_fold_limiter():
    # A routing stamp shaped exactly like the real measured + admission-
    # folded stamp: deepseek-scale account capacity (2500), mode ceiling
    # 25, and the PRES-015 fold cut to 2 by the text class hardware
    # budget. The decision must name hardware_budget, not the account.
    stamp = {
        "measured_capacity": 2, "mode": "standard",
        "capacity_status": "measured+admission-folded",
        "capacity_raw_available": 2500,
        "mode_cap": {"ceiling": 25, "width": 25, "capped": False},
        "admission": {
            "width": 2, "binding": "class_hardware_budget[text]",
            "terms": [
                {"term": "class_hardware_budget[text]", "value": 2},
                {"term": "account_free_permits", "value": 2500},
            ],
        },
    }
    d = wc.decision_from_stamp(stamp, planned_width=12, ready_work=40,
                               phase_id="P-ITEM15-STAMP")
    assert d["target_width"] == 2
    assert d["shortfall"] is True
    assert d["binding_constraint"] == wc.LIMITER_HARDWARE_BUDGET
    assert d["binding_value"] == 2


def test_router_absent_stamp_is_an_unmeasured_fallback_not_a_capacity_claim():
    # The documented router-absent rollback stamp (measured_capacity =
    # DEFAULT_MAX_WORKERS) carries NO capacity evidence: the record must
    # name the fallback, never dress it up as a capacity verdict.
    d = wc.decision_from_stamp({"measured_capacity": 8, "mode": "standard"},
                               planned_width=None, ready_work=20)
    assert d["target_width"] == 8
    assert d["binding_constraint"] == wc.LIMITER_UNMEASURED_FALLBACK
    assert d["shortfall"] is False


# ---------------------------------------------------------------------------
# 4. The operator ceiling refuses above it.
# ---------------------------------------------------------------------------
def test_operator_ceiling_refuses_above_it():
    d = wc.decide_width(500, mode="ultra", capacity_available=UNBOUNDED,
                        hardware_budget=100000, ready_work=1000)
    assert d["target_width"] == 400
    assert d["binding_constraint"] == wc.LIMITER_MODE_CEILING
    assert d["binding_value"] == 400
    assert d["shortfall"] is True

    d2 = wc.decide_width(30, mode="standard", capacity_available=UNBOUNDED,
                         hardware_budget=1000, ready_work=100)
    assert d2["target_width"] == 25
    assert d2["binding_constraint"] == wc.LIMITER_MODE_CEILING


def test_pool_never_exceeds_the_operator_ceiling(tmp_path):
    decision = wc.decide_width(30, mode="standard",
                               capacity_available=UNBOUNDED,
                               hardware_budget=1000, ready_work=40)
    assert decision["target_width"] == 25
    rz = _Rendezvous(25)

    def worker(unit):
        rz.run()
        return fanout.UnitResult(key=unit.key, status="ok", attempts=1)

    results = fanout.run_units(
        _units(40), worker, workers=decision["target_width"],
        run_dir=tmp_path, phase_id="P-ITEM15-CEILING", retry_cap=1,
        swarm_plan=decision)
    assert [r.status for r in results] == ["ok"] * 40
    assert rz.peak == 25, f"pool peaked at {rz.peak}: above or below the " \
                          f"operator-ceiling-bound target 25"
    swarm = _progress_swarm(tmp_path, "P-ITEM15-CEILING")
    assert swarm["peak_width"] == 25


# ---------------------------------------------------------------------------
# 5. The ready queue: UNBOUNDED plans at the mode ceiling, not at 8.
# ---------------------------------------------------------------------------
def test_ready_queue_width_decision(monkeypatch):
    import presentation_job.hardware_budget as hb
    import presentation_job.phases as phases
    # An UNMEASURED hardware snapshot contributes no term (hardware
    # doctrine), isolating the capacity/mode axes for this test.
    monkeypatch.setattr(hb, "cached_snapshot", lambda: {"status": "UNMEASURED"})
    eng = object.__new__(phases.Engine)  # the decision reads no Engine state

    d = eng._swarm_width_decision({"available": UNBOUNDED})
    assert d is not None
    assert d["target_width"] == 25, (
        f"UNBOUNDED ready-queue width is {d['target_width']}: the old "
        f"hard-coded fallback was 8 and the standard mode ceiling is 25")
    assert d["binding_constraint"] == wc.LIMITER_MODE_CEILING
    assert d["shortfall"] is False

    d2 = eng._swarm_width_decision({"available": 3})
    assert d2["target_width"] == 3
    assert d2["binding_constraint"] == wc.LIMITER_CAPACITY_CAP
    assert d2["binding_value"] == 3
    assert d2["shortfall"] is True

    d3 = eng._swarm_width_decision({"available": 2500})
    assert d3["target_width"] == 25
    assert d3["binding_constraint"] == wc.LIMITER_MODE_CEILING
    assert d3["shortfall"] is False
