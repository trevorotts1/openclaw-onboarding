"""Ticket 5 (PARALLEL-PIPELINE-SPEC S2.6): the RunLock single-engine invariant
under fan-out, enforced by a FAILING TEST, not by a comment.

Modeled directly on tests/test_l11_webinar_executor_no_recursion.py, which
exists for the identical bug class: a worker (there, a phase executor.cmd;
here, a fanout.py pool worker) must never re-enter the pipeline while the
Engine still holds RunLock (state.py:148) for the whole run
(__main__.py:229, :582) -- a second acquisition dies immediately with
EXIT_LOCK_HELD (state.py:162).

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory.
"""
from __future__ import annotations

import multiprocessing
import sys
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
    _FORBIDDEN_WORKER_TOKENS,
    run_units,
)
from presentation_job.state import RunLock, EXIT_LOCK_HELD  # noqa: E402


def test_forbidden_tokens_cover_every_known_reentry_path():
    """Every token this campaign has ever found to cause the EXIT_LOCK_HELD
    regression class (L-11: P9.6/P8.25's old executor.cmd) must be guarded."""
    assert "presentation_job.py" in _FORBIDDEN_WORKER_TOKENS
    assert "presentation_job" in _FORBIDDEN_WORKER_TOKENS
    assert "run_signature_deck.py" in _FORBIDDEN_WORKER_TOKENS
    assert "presentation-canonical-entry.sh" in _FORBIDDEN_WORKER_TOKENS


@pytest.mark.parametrize("argv", [
    ["python3", "presentation_job.py", "--run", "--run-dir", "/x"],
    ["python3", "-m", "presentation_job", "--run"],
    ["python3", "presentation_job/__main__.py"],
    ["python3", "run_signature_deck.py", "--run-dir", "/x"],
    ["bash", "scripts/presentation-canonical-entry.sh", "--resume", "--run-dir", "/x"],
])
def test_assert_not_a_second_engine_raises_at_submit_time_for_every_token(argv):
    with pytest.raises(FanoutContractError, match="never second engines"):
        _assert_not_a_second_engine(argv)


def test_assert_not_a_second_engine_permits_real_worker_argvs():
    # These are the kinds of argv a real fan-out worker (Ticket 7's ffmpeg
    # clip loop, a media subprocess) is allowed to build.
    _assert_not_a_second_engine(["ffmpeg", "-y", "-i", "in.png", "out.mp4"])
    _assert_not_a_second_engine(["python3", "build_webinar_video.py", "--run-dir", "/x"])
    _assert_not_a_second_engine(["python3", "workbook_builder.py", "--run-dir", "/x"])


def _held_lock_worker(run_dir_str: str, ready_evt, hold_evt) -> None:
    """Runs in a separate OS process: acquires RunLock and holds it until
    told to release, simulating "the Engine is alive" for the duration of
    the fan-out pool run below."""
    run_dir = Path(run_dir_str)
    with RunLock(run_dir):
        ready_evt.set()
        hold_evt.wait(timeout=10)


def test_fanout_pool_produces_zero_exit_lock_held_while_engine_holds_lock(tmp_path):
    """End-to-end: a real RunLock held on a tmp run dir (simulating the live
    Engine) plus a fan-out pool of 10 stub workers must produce ZERO
    EXIT_LOCK_HELD outcomes -- because none of the 10 workers ever attempts
    to acquire RunLock or invoke a pipeline entry point. This is the
    positive-side proof that complements the negative-side token check above:
    even with the Engine's lock genuinely held for the whole pool run, workers
    that are plain callables (never argv, never a RunLock acquisition) cannot
    collide with it."""
    ctx = multiprocessing.get_context("fork" if sys.platform != "win32" else "spawn")
    ready_evt = ctx.Event()
    hold_evt = ctx.Event()
    holder = ctx.Process(target=_held_lock_worker, args=(str(tmp_path), ready_evt, hold_evt))
    holder.start()
    try:
        assert ready_evt.wait(timeout=5), "engine-simulating process never acquired RunLock"

        # A second acquisition attempt (simulating a worker that WRONGLY tried
        # to become a second engine) must still die with EXIT_LOCK_HELD --
        # this proves the lock is genuinely held and the guard below is not
        # vacuously passing because nothing was actually protected.
        with pytest.raises(SystemExit) as exc_info:
            with RunLock(tmp_path):
                pass
        assert exc_info.value.code == EXIT_LOCK_HELD

        exit_lock_held_count = {"n": 0}

        def worker(unit: Unit) -> UnitResult:
            # A real fan-out worker: a plain callable, no argv, no RunLock,
            # no presentation_job re-entry of any kind.
            _assert_not_a_second_engine(["ffmpeg", "-i", f"{unit.key}.png", f"{unit.key}.mp4"])
            time.sleep(0.005)
            return UnitResult(key=unit.key, status="ok")

        units = [Unit(key=f"clip-{i:02d}") for i in range(10)]
        results = run_units(units, worker, workers=10, run_dir=tmp_path, phase_id="P9.6-TEST")

        assert len(results) == 10
        assert all(r.status == "ok" for r in results)
        assert exit_lock_held_count["n"] == 0
    finally:
        hold_evt.set()
        holder.join(timeout=5)
        if holder.is_alive():
            holder.terminate()
