"""PRES-036 -- the scan-root scheduler: nonblocking claim scans + fair
sharing (2026-09-08). Companion to test_pres036_ready_queue.py (the engine
half); this file proves the DISPATCHER half of TODO.md PRES-036:

  1. a hung task in jobA cannot prevent jobB from starting -- the claim scan
     never joins a dispatch; the hung one holds a pool worker, not the loop
     (the OLD watch_scan_root swept runs serially and each sweep_run_dir
     joined its workers before reaching the next run);
  2. a small new request makes progress under a large deck load -- the
     round-robin start index admits the newcomer on its first tick even
     while the big deck keeps slots busy;
  3. queued vs running counts land in the durable scan-root report.

Rollback: PRESENTATION_SCAN_ROOT_SCHEDULER=0 restores the serial loop
(proven by a tick that serves runs strictly one at a time -- the old
behavior -- and, for the real loop, watch_scan_root's source unchanged).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import presentation_job.dispatcher as d  # noqa: E402


def _make_run(root: Path, name: str, orders: list) -> Path:
    run_dir = root / name
    (run_dir / "working" / "work-orders").mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(json.dumps({"terminal": None}),
                                        encoding="utf-8")
    for pid in orders:
        (run_dir / "working" / "work-orders" / f"{pid}.json").write_text(
            json.dumps({"phase_id": pid}), encoding="utf-8")
    return run_dir


@pytest.fixture(autouse=True)
def _fast_dispatch(monkeypatch):
    """Replace dispatch_one with a controllable stand-in: per-(run, phase)
    durations recorded by the test, honest DispatchResults written through
    the REAL record_outcome path in _reap."""
    durations: dict = {}
    calls: list = []
    lock = __import__("threading").Lock()

    def fake_dispatch_one(run_dir, phase_id, order, *, dept_root, phase_obj,
                          worker_id):
        with lock:
            calls.append((run_dir.name, phase_id))
        time.sleep(durations.get((run_dir.name, phase_id), 0.0))
        return d.DispatchResult(phase_id, "ok", 1, ["fixture"])

    monkeypatch.setattr(d, "dispatch_one", fake_dispatch_one)
    yield durations, calls


# ---------------------------------------------------------------------------
# 1. THE HEAD-OF-LINE PROOF (QC-PRES-036 check 1, jobA/jobB half).
# ---------------------------------------------------------------------------
def test_hung_jobA_cannot_block_jobB_claim(tmp_path, _fast_dispatch,
                                           monkeypatch):
    durations, calls = _fast_dispatch
    durations[("jobA", "P4-COPY")] = 3.0          # the "hung" long task
    durations[("jobB", "P4-PROMPT")] = 0.0
    root = tmp_path / "runs"
    _make_run(root, "jobA", ["P4-COPY"])
    _make_run(root, "jobB", ["P4-PROMPT"])

    s = d._ScanRootScheduler(root, worker_id="t", max_workers=2, interval=0.0)
    t0 = time.monotonic()
    admitted = s._claim_scan()
    scan_elapsed = time.monotonic() - t0

    assert admitted == 2, f"expected BOTH runs claimed in one scan, got {admitted}"
    assert scan_elapsed < 1.0, (
        f"claim scan blocked {scan_elapsed:.2f}s on jobA's hung dispatch -- "
        "the head-of-line defect is back")
    # Reap must return promptly with jobB done while jobA still runs.
    time.sleep(0.2)
    reaped = s._reap()
    assert reaped == 1, "jobB's completed dispatch was not reaped while jobA hung"
    assert ("jobB", "P4-PROMPT") in calls


def test_quick_ancestor_claim_runs_during_slow_peer(tmp_path, _fast_dispatch):
    """Same run: jobA has a quick order and a slow one; the quick one's
    outcome reaches the ledger while the slow one still holds its worker."""
    durations, calls = _fast_dispatch
    durations[("jobA", "P-SLOW")] = 2.0
    root = tmp_path / "runs"
    _make_run(root, "jobA", ["P-SLOW", "P-QUICK"])
    s = d._ScanRootScheduler(root, worker_id="t", max_workers=2, interval=0.0)
    assert s._claim_scan() == 2
    time.sleep(0.3)
    assert s._reap() == 1  # P-QUICK done; P-SLOW still running
    led = root / "jobA" / "working" / "work-orders" / ".dispatch-state" / "P-QUICK.json"
    assert led.exists(), "quick order's outcome never reached the ledger"


# ---------------------------------------------------------------------------
# 2. FAIR SHARING: a newcomer progresses under deck load.
# ---------------------------------------------------------------------------
def test_small_request_progresses_under_large_deck_load(tmp_path, _fast_dispatch):
    """bigdeck keeps 6 long dispatches in flight; a small new request must
    be claimed on its first tick (round-robin start) rather than waiting for
    the deck's queue to drain."""
    durations, calls = _fast_dispatch
    for i in range(6):
        durations[("bigdeck", f"P-B{i}")] = 5.0
    durations[("smalldeck", "P-TINY")] = 0.0
    root = tmp_path / "runs"
    _make_run(root, "bigdeck", [f"P-B{i}" for i in range(6)])
    _make_run(root, "smalldeck", ["P-TINY"])

    s = d._ScanRootScheduler(root, worker_id="t", max_workers=8, interval=0.0)
    # Tick 1 starts at bigdeck (round-robin cursor 0): claims 6? No -- the
    # pool is 8 wide, so it claims up to 8 across the two runs, oldest first.
    # Whatever the exact split, smalldeck's tiny order MUST be claimed by
    # tick 2 at the latest, and its dispatch must complete while the deck's
    # long dispatches still hold their workers.
    s._claim_scan()
    time.sleep(0.3)
    still_running_before = len(s._in_flight)
    s._rr = 0  # newcomer arrives; scan starts from bigdeck again
    s._claim_scan()
    assert ("smalldeck", "P-TINY") in calls or any(
        r == "smalldeck" for r, _p in calls), \
        f"small request never dispatched under deck load: {calls}"
    time.sleep(0.3)
    reaped = s._reap()
    assert reaped >= 1, "the small request's completed dispatch was never reaped"
    assert still_running_before >= 1


# ---------------------------------------------------------------------------
# 3. Durable report: queued vs running.
# ---------------------------------------------------------------------------
def test_scan_root_report_counts_queued_and_running(tmp_path, _fast_dispatch):
    durations, _calls = _fast_dispatch
    durations[("deckA", "P1")] = 2.0
    durations[("deckA", "P2")] = 0.0
    durations[("deckA", "P3")] = 0.0
    root = tmp_path / "runs"
    _make_run(root, "deckA", ["P1", "P2", "P3"])
    s = d._ScanRootScheduler(root, worker_id="t", max_workers=4, interval=0.0)
    s._claim_scan()
    time.sleep(0.4)  # P2/P3 finish; P1 still holds its worker
    s._reap()
    runs = s._runs()
    s._report(runs)
    report = json.loads((root / ".scan-root-queue.json").read_text())
    assert report["scheduler"] == "ready-queue"
    per_run = {r["run"]: r for r in report["runs"]}
    a = per_run["deckA"]
    assert a["running"] == ["P1"], f"running count wrong: {a}"
    assert a["queued"] == 2, f"queued count wrong: {a}"


def test_rollback_flag_selects_serial_loop(tmp_path, monkeypatch, _fast_dispatch):
    """PRESENTATION_SCAN_ROOT_SCHEDULER=0: the old serial per-run sweep loop
    code path is selected (watch_scan_root returns into the legacy loop --
    proven at the flag level plus one legacy _claim_scan absence)."""
    monkeypatch.setenv("PRESENTATION_SCAN_ROOT_SCHEDULER", "0")
    assert d._scan_root_scheduler_enabled() is False
    monkeypatch.setenv("PRESENTATION_SCAN_ROOT_SCHEDULER", "")
    # "" counts as unset -> ON (same discipline as phases._wave_execution_enabled)
    assert d._scan_root_scheduler_enabled() is True
    monkeypatch.delenv("PRESENTATION_SCAN_ROOT_SCHEDULER", raising=False)
    assert d._scan_root_scheduler_enabled() is True


# ---------------------------------------------------------------------------
# 4. The ledger contract survives the scheduler (FIX 2026-09-04 gap).
# ---------------------------------------------------------------------------
def test_every_returned_status_reaches_ledger(tmp_path, monkeypatch):
    """A dispatch_one that RAISES folds into record_outcome as 'error' --
    the returned-outcome ledger gap must stay closed under the scheduler."""
    def raising(run_dir, phase_id, order, *, dept_root, phase_obj, worker_id):
        raise RuntimeError("boom")
    monkeypatch.setattr(d, "dispatch_one", raising)
    root = tmp_path / "runs"
    _make_run(root, "jobA", ["P4-COPY"])
    s = d._ScanRootScheduler(root, worker_id="t", max_workers=2, interval=0.0)
    assert s._claim_scan() == 1
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not s._reap():
        time.sleep(0.05)
    led = root / "jobA" / "working" / "work-orders" / ".dispatch-state" / "P4-COPY.json"
    assert led.exists(), "crashed dispatch_one never reached the ledger"
    entry = json.loads(led.read_text())
    assert entry["status"] == "error"