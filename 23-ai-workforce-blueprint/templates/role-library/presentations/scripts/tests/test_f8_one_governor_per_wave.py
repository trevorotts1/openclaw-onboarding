"""F8 -- ONE GOVERNOR PER WAVE (SWARM correctness).

Broken before this fix: `parallel_prompt_worker._run_wave` ran the wave's slide
units in `multiprocessing.get_context("spawn").Pool`.  `presentation_job.governor`
keeps its token bucket, in-flight counter, rolling-10s event list and the
`report_429` halving in MODULE-LEVEL state (`governor._state`), and a spawn child
does NOT inherit it -- every child re-imported governor with an EMPTY bucket.

Consequence: `max_inflight`, the 10 s window ceiling and the 429 penalty bound one
CHILD, never the wave.  At 100 workers against deepseek (`burst: 20`) that is up to
2,000 admissions per 10 s at one account bucket, and a 429 seen by one child never
slowed its 99 peers -- the account bucket is over-subscribed, and the leases are
not actually shared.

Fix: `_run_wave` uses `concurrent.futures.ThreadPoolExecutor` (the unit of work is
an HTTPS round trip, so the GIL is irrelevant), keeping the inline path for n <= 1.
`dispatcher._govern_acquire` already keys its re-entrancy depth per thread, so the
nested-lease accounting stays exact.

The two tests below fail on pristine origin/main and pass on the fix:

  A. test_wave_units_share_one_governor -- the SEMANTIC proof.  Four slide units
     run through the REAL `_run_one` with a provider seam that takes a governor
     lease and holds it on a 4-way barrier.  On the fix, THIS process's governor
     records peak in-flight 4 and 4 window acquisitions for the wave.  On main the
     units run in spawn children with their own private governor, so the parent's
     governor records ZERO -- exactly the defect.
  B. test_wave_never_uses_a_process_pool -- the MECHANISM proof, no subprocesses:
     `_run_wave` must never reach `multiprocessing.get_context`.

Flat file inside tests/, manages its own import path -- matching every sibling in
this directory (test_fanout_pool.py, test_wave_contract_three_seams.py).
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import governor  # noqa: E402
from presentation_job import parallel_prompt_worker as ppw  # noqa: E402

# A provider id that is absent from providers.yaml on purpose: it resolves to the
# `defaults` block (rps 1.0, burst 10, max_inflight 50), which admits the 4
# concurrent leases this wave takes.
PROBE_PROVIDER = "f8-governor-probe"
N_SLIDES = 4


def _reset_governor(provider: str) -> None:
    """Clear this provider's module-level bucket and pre-fill its tokens so the
    wave's admissions are not serialised by the 1 rps default refill."""
    with governor._lock:
        governor._state.pop(provider, None)
        state = governor._state_for(provider)
        state.tokens = float(governor.provider_config(provider)["burst"])
        state.last_refill = time.time()


def _slides(n: int):
    return [
        {"slide_id": f"s{i:02d}", "ordinal": i, "copy": [f"Headline {i}"]}
        for i in range(1, n + 1)
    ]


def _cfg(run_dir: Path, n: int, capacity: int = 8, inline: bool = False):
    return {
        "run_dir": run_dir,
        "routing": {"provider": "deepseek-direct", "model": "v4-flash",
                    "mode": "standard", "measured_capacity": capacity},
        "n_slides": n,
        "owning_role": "director-of-presentations",
        "attempts_log": run_dir / "working" / "checkpoints" / "f8-attempts",
        "prompt_constraints": {"min_chars": 1, "max_chars": 100000,
                               "required_blocks": ["LAYOUT"]},
        "requested_workers": None,
        "inline": inline,
    }


@pytest.fixture
def wave_env(tmp_path, monkeypatch):
    """Isolated run dir + governor log; no network, no engine, no real provider."""
    run_dir = tmp_path / "pres-f8-probe"
    (run_dir / "working" / "prompts").mkdir(parents=True)
    (run_dir / "working" / "checkpoints").mkdir(parents=True)
    saved_log = governor.log_path()
    governor.set_log_path(str(tmp_path / "governor_log.jsonl"))
    # If the units DO leak into spawn children (the pristine-main behaviour),
    # this stub keeps them off the network and off the real dispatcher: the
    # child resolves the provider seam from the env, gets a non-retryable auth
    # error on attempt 1, and returns a failed row without sleeping.
    stub = tmp_path / "provider-stub.json"
    stub.write_text('{"default": "fail_auth"}', encoding="utf-8")
    monkeypatch.setenv(ppw._STUB_ENV, str(stub))
    _reset_governor(PROBE_PROVIDER)
    try:
        yield run_dir
    finally:
        governor.set_log_path(saved_log)
        _reset_governor(PROBE_PROVIDER)


def test_wave_units_share_one_governor(wave_env, monkeypatch):
    """Every unit of one wave must hold its lease against ONE governor -- the
    governor living in the process that launched the wave."""
    run_dir = wave_env
    barrier = threading.Barrier(N_SLIDES)
    seen_lock = threading.Lock()
    seen_pids: list[int] = []
    seen_threads: set[int] = set()

    def _governed_provider(slide, routing, attempt, run_dir_, owning_role,
                           n_slides):
        lease = governor.acquire(PROBE_PROVIDER, timeout_s=20)
        try:
            with seen_lock:
                seen_pids.append(os.getpid())
                seen_threads.add(threading.get_ident())
            # Every unit holds its lease until all N are in flight: the peak
            # in-flight the governor records IS the wave's real concurrency.
            barrier.wait(timeout=20)
            return f"F8 probe body for slide {slide['ordinal']}"
        finally:
            governor.release(lease)

    def _accept(slide, prompt_text, run_dir_, constraints):
        ppw._atomic_write_bytes(
            ppw._prompt_path(Path(run_dir_), int(slide["ordinal"])),
            prompt_text.encode("utf-8"))
        return True, []

    monkeypatch.setattr(ppw, "provider_call", _governed_provider)
    monkeypatch.setattr(ppw, "_verify_prompt", _accept)

    slides = _slides(N_SLIDES)
    results = ppw._run_wave(slides, _cfg(run_dir, N_SLIDES), {})

    # THE F8 ASSERTION: ONE governor -- the launching process's -- saw the
    # whole wave. Spawn children each held a private, empty bucket, so this
    # process's governor recorded nothing at all.
    assert governor.max_inflight_seen(PROBE_PROVIDER) == N_SLIDES, (
        "F8: the launching process's governor recorded peak in-flight "
        f"{governor.max_inflight_seen(PROBE_PROVIDER)} for a {N_SLIDES}-wide "
        "wave -- the leases are not shared, so max_inflight, the rolling 10 s "
        "window and the report_429 halving bind one worker, not the wave")
    assert governor.window_counts(PROBE_PROVIDER) == N_SLIDES, (
        "F8: the rolling 10 s window did not count the wave's admissions")

    # The units ran where the governor lives, and really ran concurrently.
    assert seen_pids == [os.getpid()] * N_SLIDES, (
        "F8: wave units did not run in the launching process, so "
        "governor._state (module-level) is not shared across the wave")
    assert len(seen_threads) == N_SLIDES, (
        "F8: the wave did not actually run its units concurrently")

    # The wave itself still behaves: input order preserved, every unit finished.
    assert [r["ordinal"] for r in results] == [1, 2, 3, 4]
    assert [r["status"] for r in results] == ["succeeded"] * N_SLIDES


def test_wave_never_uses_a_process_pool(wave_env, monkeypatch):
    """The wave must not build a multiprocessing context at all -- a process
    pool is exactly what splits the governor into one bucket per child."""
    run_dir = wave_env
    calls: list[int] = []

    class _ForbiddenMultiprocessing:
        def __getattr__(self, name):
            raise AssertionError(
                "F8: _run_wave reached multiprocessing." + name +
                " -- the wave must share one in-process governor")

    def _record_one(task):
        calls.append(int(task["slide"]["ordinal"]))
        return {"slide_id": task["slide"]["slide_id"],
                "ordinal": int(task["slide"]["ordinal"]),
                "status": "succeeded"}

    monkeypatch.setattr(ppw, "multiprocessing", _ForbiddenMultiprocessing(),
                        raising=False)
    monkeypatch.setattr(ppw, "_run_one", _record_one)

    slides = _slides(3)
    results = ppw._run_wave(slides, _cfg(run_dir, 3), {})

    assert [r["ordinal"] for r in results] == [1, 2, 3]
    assert sorted(calls) == [1, 2, 3], (
        "F8: the in-process _run_one seam was not used by every wave unit")


def test_single_unit_wave_stays_inline(wave_env, monkeypatch):
    """Guard on the part F8 keeps: n <= 1 still runs inline, no pool at all."""
    run_dir = wave_env
    calls: list[int] = []

    def _record_one(task):
        calls.append(int(task["slide"]["ordinal"]))
        return {"slide_id": task["slide"]["slide_id"],
                "ordinal": int(task["slide"]["ordinal"]),
                "status": "succeeded"}

    monkeypatch.setattr(ppw, "_run_one", _record_one)
    results = ppw._run_wave(_slides(1), _cfg(run_dir, 1), {})
    assert [r["ordinal"] for r in results] == [1]
    assert calls == [1]
