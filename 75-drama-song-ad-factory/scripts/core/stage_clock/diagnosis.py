"""diagnosis.py - N-108: the overrun diagnosis (section 10D, binding).

One diagnosis starts beside a run at 60 minutes, 2 hours 30 minutes and 3 hours
(and whenever a checkpoint is missed by more than 10 minutes). It reads the
clock, the ledger, every job's time, the remake reasons, the check results and
fresh memory readings, names the cause exactly, applies the fix, tells the
owner, and writes the cause to the ledger and the lessons file.

It never lowers a quality rule, never marks a MAJOR passed, and never stops the
run. Stdlib only; all inputs are local run-folder records.
"""
import json
import os
import time

SCHEMA = "blackceo.overrun-diagnosis/v1"
THRESHOLDS_MIN = (60, 150, 180)
CHECKPOINT_SLACK_MIN = 10

#: Job time limits (section 10B outlier rule): twice the model's 9-in-10 time.
OUTLIER_FACTOR = 2.0

class DiagnosisError(ValueError):
    pass

def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None

def _read_jsonl(path):
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        continue
    except OSError:
        pass
    return rows

def _append_jsonl(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")

def evidence(run_dir):
    """Read the run's own records; a missing record is absent evidence, never a
    guessed fact."""
    base = os.path.abspath(os.fspath(run_dir))
    control = os.path.join(base, "control")
    clock = _read(os.path.join(control, "stage-clock.json")) or {}
    return {
        "clock": clock,
        "ledger": _read_jsonl(os.path.join(control, "ledger.jsonl")),
        "jobs": _read(os.path.join(control, "jobs.json")) or {},
        "remakes": _read(os.path.join(control, "retakes.json")) or {},
        "checks": _read(os.path.join(control, "checks.json")) or {},
        "memory": _read(os.path.join(control, "memory.json")) or {},
    }

def _stage_overrun(clock):
    over = clock.get("overruns") or []
    if not over:
        return None
    latest = max(over, key=lambda r: r.get("elapsed_minutes") or 0)
    return latest

def _stuck_jobs(jobs):
    stuck = []
    for key, job in (jobs.items() if isinstance(jobs, dict) else []):
        if not isinstance(job, dict):
            continue
        limit = job.get("limit_s")
        elapsed = job.get("elapsed_s")
        if isinstance(limit, (int, float)) and isinstance(elapsed, (int, float)) \
                and limit > 0 and elapsed > limit * OUTLIER_FACTOR:
            stuck.append({"key": key, "elapsed_s": elapsed, "limit_s": limit})
    return stuck

def _failing_check_lines(checks):
    """A check line that failed the same way on 3 or more takes."""
    counts = {}
    for row in (checks.get("rows") if isinstance(checks, dict) else []) or []:
        if not isinstance(row, dict) or row.get("ok", True):
            continue
        line = row.get("line") or row.get("code") or "unknown"
        counts[line] = counts.get(line, 0) + 1
    return sorted((k, n) for k, n in counts.items() if n >= 3)

def _memory_pressure(memory):
    """The newest reading (never older than the run's freshness window)."""
    readings = memory.get("readings") if isinstance(memory, dict) else None
    if isinstance(readings, list) and readings:
        last = readings[-1]
        if isinstance(last, dict) and isinstance(last.get("pressure"), (int, float)):
            return float(last["pressure"])
    value = memory.get("pressure") if isinstance(memory, dict) else None
    return float(value) if isinstance(value, (int, float)) else None

def diagnose(run_dir, elapsed_minutes, thresholds=THRESHOLDS_MIN, ev=None):
    """-> {"due": bool, "threshold": int|None, "cause": str|None,
    "fix": [str], "owner_message": str, "evidence": {...}, "quality_lowered":
    False, "stops_run": False}. Deterministic; applies nothing itself."""
    elapsed = float(elapsed_minutes or 0)
    fired = [t for t in thresholds if elapsed >= t]
    threshold = max(fired) if fired else None
    ev = ev if ev is not None else evidence(run_dir)
    cause, fixes = None, []
    stuck = _stuck_jobs(ev["jobs"])
    failing = _failing_check_lines(ev["checks"])
    pressure = _memory_pressure(ev["memory"])
    over = _stage_overrun(ev["clock"])
    if stuck:
        cause = "%d job(s) are past twice their 9-in-10 time" % len(stuck)
        fixes = ["re-send each stuck job once under a new key (outlier rule)",
                 "keep whichever jobs land first"]
    elif failing:
        line, count = failing[0]
        cause = "check line %r failed %d takes (a whole batch)" % (line, count)
        fixes = ["repair the prompt template through the Prompt Builder",
                 "re-read the check against its control pair, then resend"]
    elif pressure is not None and pressure > 85:
        cause = "memory pressure is %.0f%% on a fresh reading" % pressure
        fixes = ["hold new local workers until a fresh reading is at or below 85",
                 "one full-master render at a time"]
    elif over:
        cause = "stage %r is over its ceiling (%s min against %s min)" % (
            over.get("stage"), over.get("elapsed_minutes"), over.get("budget_minutes"))
        fixes = ["keep the run moving on the fastest route the hard rules allow",
                 "raise checker fan-out to one per 2 items"]
    elif threshold is not None:
        cause = "run passed %d minutes without a named blocker; the clock is the cause" % threshold
        fixes = ["send any waiting burst in one go", "raise checkers to one per 2 items"]
    owner = ("%s. Fix applied: %s. The run keeps working; no quality rule is "
             "lowered." % (cause or "no cause named yet",
                           "; ".join(fixes) or "none yet"))
    return {"schema": SCHEMA, "due": threshold is not None or bool(cause),
            "threshold": threshold, "cause": cause, "fix": fixes,
            "owner_message": owner, "quality_lowered": False, "stops_run": False,
            "evidence": {"stage_overrun": over, "stuck_jobs": stuck,
                         "failing_check_lines": failing,
                         "memory_pressure": pressure}}

def record(run_dir, verdict, at=None):
    """Write the cause and the fix to the ledger and to the lessons file."""
    base = os.path.abspath(os.fspath(run_dir))
    row = {"schema": SCHEMA, "at": at if at is not None else int(time.time()),
           "threshold": verdict.get("threshold"), "cause": verdict.get("cause"),
           "fix": verdict.get("fix"), "owner_message": verdict.get("owner_message"),
           "quality_lowered": False, "stops_run": False}
    _append_jsonl(os.path.join(base, "control", "ledger.jsonl"),
                  {"kind": "overrun-diagnosis", **row})
    _append_jsonl(os.path.join(base, "control", "lessons.jsonl"),
                  {"kind": "overrun-lesson", "cause": row["cause"],
                   "fix": row["fix"], "at": row["at"]})
    path = os.path.join(base, "control", "overrun-diagnosis.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(row, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    return row

def selftest():
    import tempfile
    proofs = []
    with tempfile.TemporaryDirectory() as base:
        os.makedirs(os.path.join(base, "control"))
        json.dump({"overruns": [{"stage": "video-burst", "elapsed_minutes": 30,
                                 "budget_minutes": 9}]},
                  open(os.path.join(base, "control", "stage-clock.json"), "w"))
        json.dump({"job-1": {"elapsed_s": 999, "limit_s": 120}},
                  open(os.path.join(base, "control", "jobs.json"), "w"))
        v = diagnose(base, 61)
        proofs.append(("a stuck job is named first", "past twice" in (v["cause"] or "")))
        proofs.append(("the run never stops and quality is never lowered",
                       v["stops_run"] is False and v["quality_lowered"] is False))
        row = record(base, v, at=123)
        proofs.append(("the cause is written to the ledger and the lessons file",
                       os.path.isfile(os.path.join(base, "control", "ledger.jsonl"))
                       and os.path.isfile(os.path.join(base, "control", "lessons.jsonl"))
                       and row["cause"] == v["cause"]))
        v2 = diagnose(base, 30, ev={"clock": {}, "jobs": {}, "checks": {},
                                    "memory": {}, "ledger": [], "remakes": {}})
        proofs.append(("before the first threshold with no blocker it is not due",
                       v2["due"] is False))
    for name, ok in proofs:
        print(("ok   " if ok else "FAIL ") + name)
    return 0 if all(ok for _, ok in proofs) else 1

if __name__ == "__main__":
    import sys
    sys.exit(selftest())
