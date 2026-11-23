#!/usr/bin/env python3
"""stage_clock.clock - stamp stage start and end; log overruns; never restart.

Row N-02 (plan section 10B stage table, 10D run-time budget).

The time-budget file is the ONE place stage times live
(references/time-budgets.json). Each stage stamps a start and an end into
``control/stage-clock.json`` and an overrun is appended to
``control/stage-overruns.jsonl``. An overrun NEVER restarts a run: it is a
record, and section 10D's diagnosis runs beside the work.
"""
import json
import os
import tempfile
import time

BUDGET_REL = os.path.join("references", "time-budgets.json")


def skill_root(start=None):
    """The skill folder that holds references/time-budgets.json."""
    d = os.path.abspath(start or os.path.dirname(__file__))
    while True:
        if os.path.isfile(os.path.join(d, BUDGET_REL)):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            raise FileNotFoundError("references/time-budgets.json not found above %s"
                                    % (start or os.path.dirname(__file__)))
        d = parent


def load_budgets(path=None):
    path = path or os.path.join(skill_root(), BUDGET_REL)
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if not isinstance(doc.get("stages"), list) or not doc["stages"]:
        raise ValueError("time-budgets.json needs a non-empty `stages` list")
    doc["_stage_by_id"] = {s["id"]: s for s in doc["stages"]}
    return doc


def stage_row(stage, budgets=None):
    budgets = budgets or load_budgets()
    row = budgets.get("_stage_by_id", {}).get(stage)
    if row is None and stage not in {s["id"] for s in budgets["stages"]}:
        raise KeyError("unknown stage %r; known: %s"
                       % (stage, ", ".join(s["id"] for s in budgets["stages"])))
    return row or budgets["_stage_by_id"][stage]


def clock_path(run_dir):
    return os.path.join(run_dir, "control", "stage-clock.json")


def overrun_path(run_dir):
    return os.path.join(run_dir, "control", "stage-overruns.jsonl")


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default


def _atomic_write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".clock-", dir=os.path.dirname(path))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def _append_jsonl(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def stamp(run_dir, stage, event, budgets=None, now=None):
    """Stamp ``event`` in {"start","end"} for ``stage``. A start is never moved
    on a repeat (a stamp cannot restart a stopped clock); an end is final."""
    if event not in ("start", "end"):
        raise ValueError("event must be 'start' or 'end'")
    budgets = budgets or load_budgets()
    row = stage_row(stage, budgets)
    now = float(now if now is not None else time.time())
    path = clock_path(run_dir)
    doc = _read(path, {"schema": "blackceo.stage-clock/v1", "stages": {}})
    entry = doc.setdefault("stages", {}).setdefault(
        stage, {"started_at": None, "ended_at": None, "ceiling_min": row["ceiling_min"]})
    entry["ceiling_min"] = row["ceiling_min"]
    result = {"stage": stage, "event": event, "ceiling_min": row["ceiling_min"]}
    if event == "start":
        if entry.get("started_at") is None:
            entry["started_at"] = now
        result["started_at"] = entry["started_at"]
    else:
        if entry.get("ended_at") is None:
            entry["ended_at"] = now
        if entry.get("started_at") is None:
            entry["started_at"] = now          # an end without a start stamps both
        elapsed = max(0.0, entry["ended_at"] - entry["started_at"])
        elapsed_min = round(elapsed / 60.0, 3)
        over = elapsed_min > float(row["ceiling_min"])
        entry["elapsed_min"] = elapsed_min
        entry["overrun"] = over
        result.update({"ended_at": entry["ended_at"], "elapsed_min": elapsed_min,
                       "overrun": over})
        if over:
            rec = {"stage": stage, "elapsed_min": elapsed_min,
                   "ceiling_min": row["ceiling_min"], "overrun": True,
                   "restart": False,
                   "action": "log and diagnose; the run is never restarted for the clock"}
            _append_jsonl(overrun_path(run_dir), rec)
            result["logged_overrun"] = True
    _atomic_write(path, doc)
    return result


def elapsed_minutes(run_dir, stage, now=None):
    doc = _read(clock_path(run_dir), {"stages": {}})
    entry = (doc.get("stages") or {}).get(stage) or {}
    started = entry.get("started_at")
    if started is None:
        return None
    ended = entry.get("ended_at")
    end = float(ended) if ended is not None else float(now if now is not None else time.time())
    return round(max(0.0, end - float(started)) / 60.0, 3)


def overruns(run_dir):
    rows = []
    try:
        with open(overrun_path(run_dir), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except FileNotFoundError:
        return []
    return rows


def current_stage(run_dir):
    doc = _read(clock_path(run_dir), {"stages": {}})
    open_rows = [(s, e) for s, e in (doc.get("stages") or {}).items()
                 if e.get("started_at") is not None and e.get("ended_at") is None]
    if not open_rows:
        return None
    return max(open_rows, key=lambda pair: pair[1]["started_at"])[0]
