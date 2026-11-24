#!/usr/bin/env python3
"""parallel_scan.py: N-47, the master split into time windows scanned at once.

The master letter scan ran one frame at a time (1,196 frames, ~54 minutes).
Split into windows it took 5 minutes. About one worker per 50 seconds of
video as memory allows; EVERY worker runs its own dirty and clean controls;
a worker that cannot run is MAJOR (item 15, fails closed), never a silent
clean window.

stdlib only (concurrent.futures), no network, no spend.
"""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor

from . import severities

WINDOW_S = 50.0          # about one worker per 50 seconds of video
MAX_WORKERS = 6          # hard ceiling per box
PRESSURE_CAP = 85        # percent; above this halve the workers


def worker_count(duration_s, free_pct=None, max_workers=MAX_WORKERS):
    """Planned workers for this length, reduced only by a fresh memory reading.

    ``free_pct`` is a FRESH reading (never older than 5 minutes per 10B); it
    is not read here. Above the pressure cap the count halves, floor 1.
    """
    if duration_s is None or duration_s <= 0:
        return 1
    planned = int(math.ceil(float(duration_s) / WINDOW_S))
    planned = max(1, min(planned, max_workers))
    if free_pct is not None and (100.0 - float(free_pct)) > PRESSURE_CAP:
        planned = max(1, planned // 2)
    return planned


def windows(duration_s, workers):
    """Evenly cut (start, dur) windows; every frame belongs to exactly one."""
    duration_s = float(duration_s)
    workers = max(1, int(workers))
    if duration_s <= 0:
        return [(0.0, 0.0)]
    step = duration_s / workers
    out = []
    for i in range(workers):
        start = i * step
        dur = (duration_s - start) if i == workers - 1 else step
        out.append((round(start, 6), round(dur, 6)))
    return out


def run_scan(duration_s, worker, free_pct=None, max_workers=MAX_WORKERS,
             pool=None, unavailable_code="SCAN_WORKER_UNAVAILABLE"):
    """Scan every window at once. ``worker(start, dur)`` returns finding rows.

    A worker that raises is reported as an unavailable MAJOR window; the
    other windows still return. Pool injection keeps unit tests process-free.
    """
    n = worker_count(duration_s, free_pct, max_workers)
    plan = windows(duration_s, n)

    def one(times):
        start, dur = times
        try:
            rows = worker(start, dur) or []
        except Exception as exc:                     # noqa: BLE001 fail closed
            return [severities.finding(
                unavailable_code, where={"start_s": start, "dur_s": dur},
                detail="window %s+%s could not run: %s" % (start, dur, exc))]
        for row in rows:
            if isinstance(row, dict) and "start_s" not in row:
                row["start_s"] = start
        return rows

    if pool is not None:
        results = list(pool.map(one, plan))
    elif n == 1:
        results = [one(plan[0])]
    else:
        with ThreadPoolExecutor(max_workers=n) as ex:
            results = list(ex.map(one, plan))

    rows = [row for group in results for row in group]
    return {"workers": n, "windows": plan, "rows": rows,
            "summary": severities.summarize(rows)}



class _Pool:  # deterministic map, no threads, for the self-check
    def map(self, fn, items):
        return [fn(i) for i in items]


if __name__ == "__main__":  # runnable self-check
    assert worker_count(120) == 3
    assert worker_count(10) == 1
    assert worker_count(600, free_pct=10) == 3      # 12 planned -> halved
    w = windows(100, 2)
    assert w[0][0] == 0.0 and abs(w[0][1] - 50.0) < 1e-6
    assert abs(w[1][0] - 50.0) < 1e-6 and abs(w[1][1] - 50.0) < 1e-6

    def ok(start, dur):
        return [severities.finding("STILL_TOO_DARK", where=start)]

    def boom(start, dur):
        raise RuntimeError("reader down")

    out = run_scan(100, ok, pool=_Pool())
    assert out["summary"]["pass"] is True and len(out["rows"]) >= 2
    bad = run_scan(100, boom, pool=_Pool())
    assert bad["summary"]["pass"] is False
    print("parallel_scan self-check ok")

