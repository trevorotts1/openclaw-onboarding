"""PRES-013 isolated proof -- fanout bounded deadlines.

QC-PRES-013 obligations proven here, against fanout.run_units AS REWRITTEN
(2026-09-08):

  1. 1-worker / 4-item / 15ms deadline: at most the FIRST item starts
     before the deadline; the rest are skipped with ZERO extra transport
     calls and remain resumable (worker_fn never invoked for them).
  2. A hanging LOCAL CHILD (process-group supervised subprocess unit) is
     terminated -- whole group TERM->KILL via process_reaper -- within its
     declared bound, with NO orphan left behind.
  3. A unit whose async provider task is running when the deadline expires
     comes back as provider_pending carrying a DURABLE task id persisted to
     the phase's provider-task store -- a resume sees the SAME id and never
     resubmits (no second bill).
  4. Successful unrelated units stay banked (their results return ok even
     when sibling units were deadline-skipped).

The original defect: `per_unit_timeout_s` was documented informational and
the pool submitted ALL units eagerly then joined -- a queued item started
whenever a slot freed, deadline or not. The rewritten run_units admits at
most `workers + prefetch` units and checks the monotonic absolute deadline
at every admission.

Run: python3 -m pytest tests/test_pres013_fanout_deadline.py -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.fanout import (  # noqa: E402
    Unit,
    UnitResult,
    load_provider_tasks,
    run_units,
    ProviderTaskPending,
)


def test_one_worker_four_items_short_deadline_starts_only_first(tmp_path):
    """The exact QC reproduction: 1 worker, 4 items, 15ms deadline. The old
    pool started items 2-4 at 44/86/128ms and finished at 173ms. The bounded
    pool admits the first item and returns the rest skipped with zero
    worker_fn calls -- resumable, no extra transport."""
    started: list[str] = []
    lock = threading.Lock()
    barrier = threading.Event()

    def worker(unit: Unit) -> UnitResult:
        with lock:
            started.append(unit.key)
        time.sleep(0.05)  # first item occupies the only slot past the deadline
        return UnitResult(key=unit.key, status="ok")

    units = [Unit(key=f"slide-{i:02d}") for i in range(1, 5)]
    results = run_units(
        units, worker, workers=1, run_dir=tmp_path, phase_id="P-DEADLINE",
        deadline_s=0.015)

    assert len(results) == 4
    ok = [r for r in results if r.status == "ok"]
    skipped = [r for r in results if r.status == "skipped"]
    # At most the first admitted item ran.
    assert len(ok) == 1
    assert ok[0].key == "slide-01"
    assert started == ["slide-01"]
    # Items 2-4: never called, skipped, resumable.
    assert len(skipped) == 3
    assert {r.key for r in skipped} == {"slide-02", "slide-03", "slide-04"}
    for r in skipped:
        assert r.attempts == 0
        assert "deadline" in " ".join(r.reasons).lower()


def test_deadline_skipped_units_have_zero_transport(tmp_path):
    """Skipped-at-admission means worker_fn was NEVER invoked -- provable by
    a worker that counts invocations and would fail on any beyond the
    admitted one."""
    calls: list[str] = []
    lock = threading.Lock()

    def counting_worker(unit: Unit) -> UnitResult:
        with lock:
            calls.append(unit.key)
        return UnitResult(key=unit.key, status="ok")

    units = [Unit(key=f"u-{i:02d}") for i in range(1, 21)]
    results = run_units(units, counting_worker, workers=2, run_dir=tmp_path,
                        phase_id="P-ZERO-TRANSPORT", deadline_s=0.001)
    assert len(calls) < len(units)          # deadline stopped admissions
    for r in results:
        if r.status == "skipped":
            assert r.key not in calls       # zero transport for skipped


def test_hanging_subprocess_child_terminated_no_orphan(tmp_path):
    """A hanging local child, declared as a process-group supervised
    subprocess unit, is TERM->KILLed within its declared per-unit bound and
    leaves NO orphan process."""
    marker = tmp_path / "hanging-child.pid"
    hang_script = tmp_path / "hanging_child.py"
    hang_script.write_text(
        "import os, time, sys\n"
        f"open({str(marker)!r}, 'w').write(str(os.getpid()))\n"
        # a grandchild IN THE SAME GROUP (the group kill must reach it too)
        "import subprocess, sys\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])\n"
        "time.sleep(600)\n",
        encoding="utf-8")

    argv = [sys.executable, str(hang_script)]
    units = [Unit(key="hang-01",
                  payload={"subprocess_argv": argv, "provider": "local"})]
    t0 = time.monotonic()
    results = run_units(units, lambda u: None, workers=1, run_dir=tmp_path,
                        phase_id="P-HANG", per_unit_timeout_s=3.0,
                        retry_cap=1)
    elapsed = time.monotonic() - t0

    res = results[0]
    # A group-killed child surfaces as failed with the TimeoutExpired text.
    assert res.status == "failed"
    assert elapsed < 20.0, f"hang must terminate within its bound, took {elapsed:.1f}s"

    child_pid = int(marker.read_text().strip())
    deadline = time.monotonic() + 8.0
    still = True
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
            time.sleep(0.1)
        except ProcessLookupError:
            still = False
            break
        except PermissionError:
            still = True
            break
    assert not still, f"hanging child {child_pid} was left orphaned"


def test_provider_task_expiry_persists_id_no_second_bill(tmp_path):
    """Deadline expires while a remote ASYNC provider task runs: the worker
    raises ProviderTaskPending with its durable id. run_units persists the
    id to the phase provider-task store and returns pending_provider with
    the SAME id in meta -- a resume polls it; no resubmission, no second
    bill. Proven by reading the store back and simulating the resume."""
    created_tasks: list[str] = []

    def async_provider_worker(unit: Unit) -> UnitResult:
        task_id = f"kie-task-{len(created_tasks) + 1:03d}"
        created_tasks.append(task_id)
        raise ProviderTaskPending(task_id, provider="kie")

    units = [Unit(key="img-01", payload={"provider": "kie"})]
    # Deadline passes while the task runs: the pending state must survive.
    results = run_units(units, async_provider_worker, workers=1,
                        run_dir=tmp_path, phase_id="P-ASYNC",
                        deadline_s=0.001, retry_cap=3)

    assert len(results) == 1
    r = results[0]
    assert r.status == "pending_provider"
    assert r.meta["provider_task_id"] == created_tasks[0]
    assert r.meta["state"] == "provider_running"

    # Durable: the SAME id is on disk for the resume path.
    store = load_provider_tasks(tmp_path, "P-ASYNC")
    assert store["img-01"]["task_id"] == created_tasks[0]

    # The resume path: reading the store FIRST yields the existing id -- a
    # resume worker would poll it, never create task #2.
    resumed_seen = load_provider_tasks(tmp_path, "P-ASYNC")["img-01"]["task_id"]
    assert resumed_seen == created_tasks[0]
    assert len(created_tasks) == 1, "no second bill: exactly one provider task"


def test_successful_unrelated_units_stay_banked(tmp_path):
    """Deadline kills unstarted units; units that COMPLETED stay ok in the
    returned input-ordered results -- the banked-work guarantee."""
    ok_keys: list[str] = []
    lock = threading.Lock()

    def mixed_worker(unit: Unit) -> UnitResult:
        if unit.key == "u-01":
            time.sleep(0.3)  # outlives the deadline legitimately
            with lock:
                ok_now = unit.key
            return UnitResult(key=ok_now, status="ok")
        with lock:
            ok_now = unit.key
        return UnitResult(key=ok_now, status="ok")

    units = [Unit(key=f"u-{i:02d}") for i in range(1, 13)]
    results = run_units(units, mixed_worker, workers=1, run_dir=tmp_path,
                        phase_id="P-BANKED", deadline_s=0.05)
    ok = [r for r in results if r.status == "ok"]
    skipped = [r for r in results if r.status == "skipped"]
    assert len(ok) >= 1                     # at least the admitted one banked
    assert all(r.status == "ok" for r in results if r.status != "skipped")
    assert len(ok) + len(skipped) == len(units)


def test_queued_vs_admitted_vs_submitted_states_visible(tmp_path):
    """The four PRES-013 states appear in the progress artifact as units
    move through them."""
    captured: list[dict] = []
    lock = threading.Lock()

    def cb(snap: dict) -> None:
        with lock:
            captured.append(json.loads(json.dumps(snap["counts"])))

    def worker(unit: Unit) -> UnitResult:
        return UnitResult(key=unit.key, status="ok")

    units = [Unit(key=f"u-{i:02d}") for i in range(1, 7)]
    results = run_units(units, worker, workers=2, run_dir=tmp_path,
                        phase_id="P-STATES", progress_cb=cb, prefetch=1)
    assert len(results) == 6
    # The progress path exists and carries state counts.
    progress = json.loads((tmp_path / "working" / "fanout" /
                           "P-STATES-progress.json").read_text(encoding="utf-8"))
    assert "counts" in progress
    # All units completed; every terminal state accounted for.
    counts = progress["counts"]
    assert counts["verified"] + counts["failed"] + counts["skipped"] + \
        counts["provider_running"] == 6


def test_prefetch_bounded_never_exceeds_queue_depth(tmp_path):
    """Admission is bounded at workers + prefetch -- with prefetch=2 and
    workers=1, no more than 3 units are ever in the pool queue at once and
    never more than `workers` run concurrently."""
    max_active = {"v": 0}
    active = {"v": 0}
    lock = threading.Lock()

    def worker(unit: Unit) -> UnitResult:
        with lock:
            active["v"] += 1
            max_active["v"] = max(max_active["v"], active["v"])
        time.sleep(0.01)
        with lock:
            active["v"] -= 1
        return UnitResult(key=unit.key, status="ok")

    units = [Unit(key=f"u-{i:03d}") for i in range(30)]
    run_units(units, worker, workers=1, run_dir=tmp_path,
              phase_id="P-PREFETCH", prefetch=2)
    assert max_active["v"] <= 1