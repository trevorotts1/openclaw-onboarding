"""Tests for presentation_job/fanout.py (Ticket 1, PARALLEL-PIPELINE-SPEC).

Ticket 1's exit condition is that this module has ZERO importers elsewhere in
the pipeline yet -- these tests exercise it in isolation with deterministic
stub workers, exactly as the spec's Ticket 1 test plan requires:

  (a) workers=1 result order equals workers=50 result order (both equal the
      INPUT order -- fanout.run_units never reorders by completion time).
  (b) 3 failing units out of 50 yield 47 "ok" + 3 "failed", with NO
      cancellation of in-flight units (every submitted unit completes).
  (c) a phase deadline stops NEW submissions without killing in-flight ones.
  (d) run_units never runs more than `workers` concurrent callables.

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory (test_l11_webinar_executor_no_recursion.py, etc.).
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.fanout import (  # noqa: E402
    FanoutContractError,
    Unit,
    UnitResult,
    _assert_not_a_second_engine,
    resolve_effective_workers,
    run_units,
)


def _ok_worker(unit: Unit) -> UnitResult:
    return UnitResult(key=unit.key, status="ok", target=f"working/x/{unit.key}.txt")


def test_order_identical_at_workers_1_and_workers_50(tmp_path):
    units = [Unit(key=f"slide-{i:02d}") for i in range(1, 26)]

    serial = run_units(units, _ok_worker, workers=1, run_dir=tmp_path, phase_id="P-TEST")
    parallel = run_units(units, _ok_worker, workers=50, run_dir=tmp_path, phase_id="P-TEST")

    assert [r.key for r in serial] == [u.key for u in units]
    assert [r.key for r in parallel] == [u.key for u in units]
    assert all(r.status == "ok" for r in serial)
    assert all(r.status == "ok" for r in parallel)


def test_partial_failure_no_cancellation(tmp_path):
    failing_keys = {"slide-07", "slide-21", "slide-45"}
    completed = []
    lock = threading.Lock()

    def worker(unit: Unit) -> UnitResult:
        time.sleep(0.01)
        with lock:
            completed.append(unit.key)
        if unit.key in failing_keys:
            return UnitResult(key=unit.key, status="failed", reasons=["stubbed failure"])
        return UnitResult(key=unit.key, status="ok")

    units = [Unit(key=f"slide-{i:02d}") for i in range(1, 51)]
    results = run_units(units, worker, workers=10, run_dir=tmp_path, phase_id="P-TEST")

    ok = [r for r in results if r.status == "ok"]
    failed = [r for r in results if r.status == "failed"]
    assert len(ok) == 47
    assert len(failed) == 3
    assert {r.key for r in failed} == failing_keys
    # No cancellation: every one of the 50 units actually ran its worker body.
    assert len(completed) == 50


def test_deadline_stops_new_submissions_not_in_flight(tmp_path, monkeypatch):
    """Deterministic version of the deadline race, not a wall-clock one: the
    submission loop's `time.monotonic()` calls are scripted so exactly the
    first 2 of 5 units are submitted before the deadline reads as passed --
    no timing-dependent sleep/race is involved in the pass/fail decision."""
    import presentation_job.fanout as fanout_mod

    started = []
    lock = threading.Lock()
    release = threading.Event()

    def slow_worker(unit: Unit) -> UnitResult:
        with lock:
            started.append(unit.key)
        release.wait(timeout=5.0)
        return UnitResult(key=unit.key, status="ok")

    units = [Unit(key=f"slide-{i:02d}") for i in range(1, 6)]

    # call 0: deadline_at = 0 + deadline_s(=5) -> 5
    # calls 1,2 (units 1,2): 1, 2  (< 5 -> submitted)
    # calls 3,4,5 (units 3,4,5): 6, 7, 8  (>= 5 -> skipped at submission time)
    fake_clock = iter([0, 1, 2, 6, 7, 8, 9, 10, 11, 12])
    monkeypatch.setattr(fanout_mod.time, "monotonic", lambda: next(fake_clock))

    result_holder = {}

    def run_and_capture():
        result_holder["results"] = run_units(
            units, slow_worker, workers=2, run_dir=tmp_path,
            phase_id="P-TEST", deadline_s=5)

    t = threading.Thread(target=run_and_capture)
    t.start()
    # Give the 2 submitted workers a moment to actually enter slow_worker
    # (real wall-clock wait -- unrelated to the patched deadline clock above).
    deadline = time.time() + 2.0
    while len(started) < 2 and time.time() < deadline:
        time.sleep(0.01)
    release.set()
    t.join(timeout=5)

    results = result_holder["results"]
    assert len(results) == 5
    skipped = [r for r in results if r.status == "skipped"]
    non_skipped = [r for r in results if r.status != "skipped"]
    assert len(non_skipped) == 2
    assert len(skipped) == 3
    assert set(started) == {r.key for r in non_skipped}
    for r in skipped:
        assert r.key not in started


def test_never_exceeds_workers_concurrent_callables(tmp_path):
    max_seen = {"value": 0}
    active = {"value": 0}
    lock = threading.Lock()

    def worker(unit: Unit) -> UnitResult:
        with lock:
            active["value"] += 1
            max_seen["value"] = max(max_seen["value"], active["value"])
        time.sleep(0.02)
        with lock:
            active["value"] -= 1
        return UnitResult(key=unit.key, status="ok")

    units = [Unit(key=f"u-{i:03d}") for i in range(40)]
    run_units(units, worker, workers=5, run_dir=tmp_path, phase_id="P-TEST")

    assert max_seen["value"] <= 5


def test_worker_exception_retried_then_marked_failed(tmp_path):
    attempts = {"count": 0}

    def always_raises(unit: Unit) -> UnitResult:
        attempts["count"] += 1
        raise RuntimeError("simulated transport fault")

    units = [Unit(key="only-one")]
    results = run_units(units, always_raises, workers=1, run_dir=tmp_path,
                         phase_id="P-TEST", retry_cap=3)

    assert len(results) == 1
    assert results[0].status == "failed"
    assert results[0].attempts == 3
    assert attempts["count"] == 3


def test_worker_returned_failed_status_is_not_double_retried(tmp_path):
    """A worker_fn that already owns its own retry policy (like the real
    _author_one_slide, Ticket 4) and returns a definitive "failed" verdict
    must be called exactly ONCE by the pool -- see fanout.py's RETRY DESIGN
    NOTE. Only an unexpected exception gets the pool's own outer retry."""
    calls = {"count": 0}

    def definitive_failure(unit: Unit) -> UnitResult:
        calls["count"] += 1
        return UnitResult(key=unit.key, status="failed", attempts=3,
                           reasons=["exhausted its own internal retries"])

    units = [Unit(key="only-one")]
    results = run_units(units, definitive_failure, workers=1, run_dir=tmp_path,
                         phase_id="P-TEST", retry_cap=3)

    assert calls["count"] == 1
    assert results[0].status == "failed"
    assert results[0].attempts == 3  # preserved from the worker, not overwritten


def test_empty_units_returns_empty(tmp_path):
    assert run_units([], _ok_worker, workers=10, run_dir=tmp_path, phase_id="P-TEST") == []


def test_assert_not_a_second_engine_raises_for_every_forbidden_token():
    forbidden_argvs = [
        ["python3", "presentation_job.py", "--run"],
        ["python3", "-m", "presentation_job", "--run"],
        ["python3", "run_signature_deck.py", "--run-dir", "/x"],
        ["bash", "presentation-canonical-entry.sh", "--resume"],
    ]
    for argv in forbidden_argvs:
        with pytest.raises(FanoutContractError):
            _assert_not_a_second_engine(argv)


def test_assert_not_a_second_engine_allows_normal_workers():
    _assert_not_a_second_engine(["ffmpeg", "-i", "clip.mp4", "-y", "out.mp4"])
    _assert_not_a_second_engine(["python3", "build_webinar_video.py", "--run-dir", "/x"])


@pytest.mark.parametrize(
    "phase_workers,unit_count,env_val,capacity_available,expected",
    [
        (50, 25, None, None, 25),          # min'd to unit count (spec S3.3 example)
        (1, 25, None, None, 1),            # absent/1 -> serial ceiling of 1
        (50, 100, "10", None, 10),         # env override tightens further
        (50, 100, None, 8, 8),             # measured CAP_TABLE ceiling (e.g. ollama-cloud)
    ],
)
def test_resolve_effective_workers_resolution_order(
    monkeypatch, phase_workers, unit_count, env_val, capacity_available, expected
):
    env_var = "PRESENTATION_PHASE_WORKERS_P_TEST"
    monkeypatch.delenv(env_var, raising=False)
    if env_val is not None:
        monkeypatch.setenv(env_var, env_val)
    result = resolve_effective_workers(
        phase_workers, unit_count, env_var=env_var, capacity_available=capacity_available)
    assert result == expected


def test_resolve_effective_workers_unbounded_capacity_drops_out(monkeypatch):
    from presentation_job import capacity as _capacity
    result = resolve_effective_workers(50, 25, capacity_available=_capacity.UNBOUNDED)
    assert result == 25  # UNBOUNDED never becomes the effective width; unit_count wins
